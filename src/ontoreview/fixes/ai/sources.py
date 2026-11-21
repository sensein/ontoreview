"""Where AI drafts come from: a local Hugging Face model, a local Ollama server, or a provider with
an API key. The first available source in the user's priority order is used.

Every source answers ``generate(system, user, schema) -> dict`` with JSON matching ``schema`` and
reports what produced it (``describe()``: source, provider, model, revision) for provenance.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

PRESETS = {     # provider -> (OpenAI-compatible base URL, key environment variable)
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY"),
    "mistral": ("https://api.mistral.ai/v1", "MISTRAL_API_KEY"),
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "anthropic": ("https://api.anthropic.com", "ANTHROPIC_API_KEY"),
    "custom": ("", ""),
}
LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")


class AIError(RuntimeError):
    """No usable source, or a source failed; the message says what to do."""


def extract_json(text: str) -> dict:
    """The first JSON object in a model's answer (thinking blocks and code fences ignored)."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        raise ValueError("no JSON object in the answer")
    return json.loads(m.group(0))


def _post(url: str, body: dict, headers: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "ontoreview", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - user-configured endpoint
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        detail = e.read()[:300].decode("utf-8", "replace")
        raise AIError(f"{url} answered {e.code}: {detail}") from e
    except OSError as e:
        raise AIError(f"Could not reach {url} ({e}).") from e


def _get(url: str, timeout: float = 5) -> dict | None:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "ontoreview"}),  # noqa: S310
                                    timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except (OSError, ValueError):
        return None


class HFSource:
    """A local open-source model from Hugging Face (transformers), downloaded on first use."""
    name = "hf"
    _pipes: dict = {}
    _lock = threading.Lock()

    def __init__(self, model: str, token: str | None = None):
        self.model, self.token = model, token

    def available(self) -> tuple[bool, str]:
        try:
            import transformers  # noqa: F401
        except ImportError:
            return False, "Hugging Face models need pip install 'ontoreview[cdi]'"
        return True, ""

    _sizes: dict = {}

    def total_bytes(self) -> int:
        """The model's download size (from the Hugging Face API, remembered)."""
        if self.model not in self._sizes:
            try:
                from huggingface_hub import model_info
                info = model_info(self.model, files_metadata=True, token=self.token)
                self._sizes[self.model] = sum((x.size or 0) for x in info.siblings)
            except Exception:  # noqa: BLE001 - offline: unknown size
                self._sizes[self.model] = 0
        return self._sizes[self.model]

    def downloaded_bytes(self) -> int:
        """Bytes of this model already in the local Hugging Face cache (including partial files)."""
        try:
            from huggingface_hub.constants import HF_HUB_CACHE
        except Exception:  # noqa: BLE001
            return 0
        from pathlib import Path
        root = Path(HF_HUB_CACHE) / ("models--" + self.model.replace("/", "--"))
        return sum(f.stat().st_size for f in root.rglob("*") if f.is_file() and not f.is_symlink()) if root.exists() else 0

    def prepare(self) -> None:
        """Download the model (resumes a partial download); the first use only."""
        from huggingface_hub import snapshot_download
        snapshot_download(self.model, token=self.token)

    def load(self) -> None:
        """Load the model into memory (slow the first time in a session)."""
        self._pipe()

    def cached(self) -> bool:
        """Whether the model is already on this computer (no download needed)."""
        try:
            from huggingface_hub import snapshot_download
            snapshot_download(self.model, local_files_only=True, token=self.token)
            return True
        except Exception:  # noqa: BLE001 - not cached, or huggingface_hub missing
            return False

    def _pipe(self):
        with self._lock:
            if self.model not in self._pipes:
                from transformers import pipeline
                kw = {"token": self.token} if self.token else {}
                try:
                    self._pipes[self.model] = ("text", pipeline("text-generation", model=self.model, **kw))
                except Exception:  # noqa: BLE001 - multimodal checkpoints (Qwen 3.5) load as image-text-to-text
                    self._pipes[self.model] = ("vlm", pipeline("image-text-to-text", model=self.model, **kw))
            return self._pipes[self.model]

    def generate(self, system: str, user: str, schema: dict) -> dict:
        kind, pipe = self._pipe()
        from .prompts import prompt as _prompt
        prompt = f"{user}\n\n" + _prompt("json_answer", schema=json.dumps(schema))
        if kind == "text":
            msgs = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
        else:
            msgs = [{"role": "system", "content": [{"type": "text", "text": system}]},
                    {"role": "user", "content": [{"type": "text", "text": prompt}]}]
        out = pipe(text=msgs, max_new_tokens=400, do_sample=False) if kind == "vlm" else \
            pipe(msgs, max_new_tokens=400, do_sample=False)
        gen = out[0]["generated_text"]
        text = gen[-1]["content"] if isinstance(gen, list) else gen
        if isinstance(text, list):
            text = " ".join(x.get("text", "") for x in text if isinstance(x, dict))
        return extract_json(text)

    def describe(self) -> dict:
        revision = ""
        try:
            from huggingface_hub import model_info
            revision = model_info(self.model, token=self.token).sha or ""
        except Exception:  # noqa: BLE001 - offline: the revision stays unknown
            pass
        return {"source": "hf", "provider": "Hugging Face (local)", "model": self.model, "revision": revision,
                "local": True}


class OllamaSource:
    name = "ollama"

    def __init__(self, model: str, url: str = "http://localhost:11434", timeout: float = 120):
        self.model, self.url, self.timeout = model, url.rstrip("/"), timeout
        self._digest = ""

    def models(self) -> list[dict]:
        """Models installed in Ollama: name, size (bytes), digest; [] when Ollama is not running."""
        tags = _get(f"{self.url}/api/tags")
        return [{"name": m.get("name") or m.get("model"), "size": m.get("size", 0), "digest": m.get("digest", ""),
                 "family": (m.get("details") or {}).get("family", ""),
                 "parameters": (m.get("details") or {}).get("parameter_size", "")}
                for m in (tags or {}).get("models", []) if m.get("name") or m.get("model")]

    def available(self) -> tuple[bool, str]:
        tags = _get(f"{self.url}/api/tags")
        if tags is None:
            return False, f"Ollama is not running at {self.url}"
        installed = self.models()
        if not installed:
            return False, f"Ollama has no models (ollama pull {self.model or 'qwen3.5:4b'})"
        names = [m["name"] for m in installed]
        wanted = self.model or ""
        pick = wanted if wanted in names else best_local(names, wanted)
        if pick != wanted:
            self.note = (f"{wanted} is not installed; using {pick}" if wanted else f"using {pick}")
        self.model = pick
        self._digest = next(m["digest"] for m in installed if m["name"] == pick)
        return True, getattr(self, "note", "")

    def pull(self, model: str, progress=None) -> None:
        """Download a model into Ollama (``ollama pull``), reporting (status, completed, total)."""
        req = urllib.request.Request(f"{self.url}/api/pull", data=json.dumps({"model": model, "stream": True}).encode(),
                                     method="POST", headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=3600) as r:  # noqa: S310 - the user's Ollama server
                for line in r:
                    ev = json.loads(line or b"{}")
                    if ev.get("error"):
                        raise AIError(f"Ollama could not pull {model}: {ev['error']}")
                    if progress:
                        progress(ev.get("status", ""), ev.get("completed", 0), ev.get("total", 0))
        except OSError as e:
            raise AIError(f"Could not reach Ollama at {self.url} ({e}).") from e

    def generate(self, system: str, user: str, schema: dict) -> dict:
        # thinking models (qwen3.5, …) otherwise reason at length before answering: minutes per draft,
        # often past the timeout. A short annotation needs no visible reasoning, so ask them not to.
        body = {"model": self.model, "stream": False, "format": schema, "think": False,
                "options": {"temperature": 0},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        try:
            r = _post(f"{self.url}/api/chat", body, {}, self.timeout)
        except AIError as e:
            if "think" not in str(e).lower():
                raise
            body.pop("think")                        # an Ollama that does not know the option
            r = _post(f"{self.url}/api/chat", body, {}, self.timeout)
        return extract_json((r.get("message") or {}).get("content", ""))

    def describe(self) -> dict:
        return {"source": "ollama", "provider": "Ollama (local)", "model": self.model, "revision": self._digest,
                "local": True, "endpoint": self.url}


def best_local(names: list[str], wanted: str = "") -> str:
    """The installed model closest to the one asked for: same name and family (qwen3.5:*), then a general
    instruction model (qwen, gemma, llama, mistral, phi), larger before smaller, never an embedding model."""
    fam = wanted.split(":")[0] if wanted else "qwen3.5"

    def size(n: str) -> float:
        m = re.search(r"(\d+(?:\.\d+)?)b\b", n.lower())
        return float(m.group(1)) if m else 0.0

    def rank(n: str) -> tuple:
        low = n.lower()
        if "embed" in low:
            return (9, 0)
        base = low.split(":")[0]
        order = 0 if base == fam else 1 if base.startswith(fam.split(".")[0]) else 2 if any(
            k in low for k in ("qwen", "gemma", "llama", "mistral", "phi")) else 3
        return (order, -min(size(n), 14))         # prefer larger, but not huge, for drafting quality
    return sorted(names, key=rank)[0]


class OpenAICompatSource:
    name = "api"

    def __init__(self, provider: str, model: str, key: str, base: str = "", timeout: float = 120):
        self.provider, self.model, self.key, self.timeout = provider, model, key, timeout
        self.base = (base or PRESETS.get(provider, ("", ""))[0]).rstrip("/")
        self._reported = ""

    def available(self) -> tuple[bool, str]:
        if not self.base:
            return False, "set the API base URL"
        if not self.model:
            return False, "set the API model"
        local = any(h in self.base for h in LOCAL_HOSTS)
        if not self.key and not local:
            return False, f"no API key for {self.provider}"
        return True, ""

    def generate(self, system: str, user: str, schema: dict) -> dict:
        body = {"model": self.model, "temperature": 0,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "response_format": {"type": "json_schema",
                                    "json_schema": {"name": "answer", "schema": schema, "strict": False}}}
        headers = {"Authorization": f"Bearer {self.key}"} if self.key else {}
        try:
            r = _post(f"{self.base}/chat/completions", body, headers, self.timeout)
        except AIError as e:
            if "response_format" not in str(e) and "json_schema" not in str(e):
                raise
            body.pop("response_format")
            from .prompts import prompt as _prompt
            body["messages"][1]["content"] += "\n\n" + _prompt("json_answer", schema=json.dumps(schema))
            r = _post(f"{self.base}/chat/completions", body, headers, self.timeout)
        self._reported = r.get("model", "") or self.model
        return extract_json(r["choices"][0]["message"]["content"])

    def describe(self) -> dict:
        return {"source": "api", "provider": self.provider, "model": self.model, "revision": self._reported,
                "local": any(h in self.base for h in LOCAL_HOSTS), "endpoint": self.base}


class AnthropicSource:
    name = "api"

    def __init__(self, model: str, key: str, base: str = "", timeout: float = 120):
        self.model, self.key, self.timeout = model, key, timeout
        self.base = (base or PRESETS["anthropic"][0]).rstrip("/")
        self._reported = ""

    def available(self) -> tuple[bool, str]:
        if not self.model:
            return False, "set the API model"
        if not self.key:
            return False, "no API key for anthropic"
        return True, ""

    def generate(self, system: str, user: str, schema: dict) -> dict:
        r = _post(f"{self.base}/v1/messages", {
            "model": self.model, "max_tokens": 800, "system": system, "temperature": 0,
            "messages": [{"role": "user", "content": user}],
            "tools": [{"name": "answer", "description": "Give the answer.", "input_schema": schema}],
            "tool_choice": {"type": "tool", "name": "answer"}},
            {"x-api-key": self.key, "anthropic-version": "2023-06-01"}, self.timeout)
        self._reported = r.get("model", "") or self.model
        for block in r.get("content", []):
            if block.get("type") == "tool_use":
                return block.get("input") or {}
        return extract_json(" ".join(b.get("text", "") for b in r.get("content", [])))

    def describe(self) -> dict:
        return {"source": "api", "provider": "anthropic", "model": self.model, "revision": self._reported,
                "local": False, "endpoint": self.base}


def make_source(name: str, ai, hf_token: str | None = None):
    if name == "hf":
        return HFSource(ai.hf_model, hf_token or os.environ.get("HF_TOKEN"))
    if name == "ollama":
        return OllamaSource(ai.ollama_model, ai.ollama_url, ai.timeout)
    key = ai.api_key or os.environ.get(PRESETS.get(ai.api_provider, ("", ""))[1] or "_NONE_", "")
    if ai.api_provider == "anthropic":
        return AnthropicSource(ai.api_model, key, ai.api_base_url, ai.timeout)
    return OpenAICompatSource(ai.api_provider, ai.api_model, key, ai.api_base_url, ai.timeout)


def pick_source(ai, hf_token: str | None = None, only: str | None = None, quick: bool = False):
    """The first available source in priority order; raises AIError listing why each was skipped.
    ``quick``: only sources that answer without a large download (a Hugging Face model must be cached)."""
    if not ai.enabled:
        raise AIError("AI suggestions are off (Settings › AI & fixes).")
    why = []
    for name in ([only] if only else ai.priority):
        src = make_source(name, ai, hf_token)
        ok, reason = src.available()
        if ok and quick and name == "hf" and not src.cached():
            ok, reason = False, f"{ai.hf_model} is not downloaded yet (several GB on first use)"
        if ok:
            return src
        why.append(f"{name}: {reason}")
    raise AIError("No AI source available. " + "; ".join(why) + ".")


__all__ = ["AIError", "AnthropicSource", "HFSource", "OllamaSource", "OpenAICompatSource", "PRESETS", "extract_json",
           "make_source", "pick_source"]
