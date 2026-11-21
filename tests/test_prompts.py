"""The AI prompts come from fixes/ai/prompts.md (overridable with ONTOREVIEW_PROMPTS)."""

from __future__ import annotations

import json

from ontoreview.fixes.ai.prompts import prompt, prompts

NEEDED = {"system", "definition", "refine", "refine_default", "description", "domain_range", "role_domain",
          "role_range", "json_answer"}


def test_every_prompt_the_code_uses_is_in_the_file():
    assert NEEDED <= set(prompts())


def test_prompts_keep_the_wording():
    assert prompt("system").startswith("You help ontology authors.")
    assert prompt("definition", context="Term: soil pH (class)") == (
        'Term: soil pH (class)\n\nWrite one definition for this term, in the form "A <parent> that '
        '<distinguishing features>." One sentence, no circular wording.')
    assert prompt("refine", context="C", current="Old.", how=prompt("refine_default")).endswith(
        "Rewrite the definition to be clearer and more precise, in genus–differentia form, keeping its meaning. "
        "One or two sentences.")
    assert prompt("domain_range", context="C", definition="(none)", which="range", role=prompt("role_range"),
                  listing="x | X").splitlines()[-2:] == [
        "Which class is the range of this property (the values it points to)? Choose up to three from this list "
        "(IRI | label), best first, with a short reason each:", "x | X"]
    schema = {"type": "object"}
    assert prompt("json_answer", schema=json.dumps(schema)) == 'Answer with one JSON object only, matching: {"type": "object"}'


def test_override_file_replaces_only_its_sections(tmp_path, monkeypatch):
    f = tmp_path / "my-prompts.md"
    f.write_text("# Mine\n\n## definition\n\n```text\n{context}\n\nDefine it briefly.\n```\n")
    monkeypatch.setenv("ONTOREVIEW_PROMPTS", str(f))
    assert prompt("definition", context="T") == "T\n\nDefine it briefly."
    assert prompt("system").startswith("You help ontology authors.")        # not overridden: default
