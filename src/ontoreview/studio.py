"""ontoreview studio: a local generator UI.

A compact toolbar with *Open ontology* and *Export HTML*; once a file is loaded the generated
document is shown as a live preview. Everything runs locally; files never leave the machine.
"""

from __future__ import annotations

import base64
import http.server
import json
import mimetypes
import re
import shutil
import tempfile
import threading
import uuid
from pathlib import Path
from urllib.parse import unquote, urlparse

from .build import build, build_single_file
from .linkml import is_linkml_file

RDF_EXT = {".ttl", ".owl", ".rdf", ".xml", ".jsonld", ".json", ".nt", ".n3", ".trig", ".nq"}
YAML_EXT = {".yaml", ".yml"}
MAX_UPLOAD = 200 * 1024 * 1024

STUDIO_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ontoreview studio</title>
<style>
:root{--paper:#fbfaf7;--ink:#1c1b18;--muted:#6e6a60;--rule:#d9d4c7;--link:#1d4f91;
 --serif:"Iowan Old Style","Palatino Linotype",Palatino,Charter,Georgia,serif;
 --sans:-apple-system,BlinkMacSystemFont,"Segoe UI","Helvetica Neue",Arial,sans-serif;color-scheme:light}
@media (prefers-color-scheme:dark){:root{--paper:#1b1a17;--ink:#e9e5da;--muted:#9c968a;--rule:#3a372f;--link:#9dbbe6;color-scheme:dark}}
*{box-sizing:border-box}html,body{height:100%;margin:0}
body{background:var(--paper);color:var(--ink);font:14px/1.4 var(--sans);display:flex;flex-direction:column}
.bar{display:flex;align-items:center;gap:14px;padding:8px 16px;border-bottom:1px solid var(--rule)}
.word{font:600 16px var(--serif);margin-right:6px}
button,label.btn{font:500 13px var(--sans);color:var(--ink);background:var(--paper);border:1px solid var(--rule);padding:5px 12px;cursor:pointer}
button:hover:not(:disabled),label.btn:hover{border-color:var(--muted)}
button:disabled{color:var(--muted);cursor:default}
#file{display:none}
.name{font-family:ui-monospace,Menlo,monospace;font-size:12px;color:var(--muted);max-width:30ch;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.status{margin-left:auto;color:var(--muted);font-size:12.5px}
.status.err{color:#9a2b20}
main{flex:1;position:relative}
iframe{position:absolute;inset:0;width:100%;height:100%;border:0;background:var(--paper)}
.empty{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;padding:24px}
.empty div{max-width:34rem;font:17px/1.6 var(--serif);color:var(--muted);border:1px dashed var(--rule);padding:36px 40px}
.empty b{color:var(--ink);font-weight:600}
body.drag .empty div{border-color:var(--link);color:var(--ink)}
select{font:13px var(--sans);background:var(--paper);color:var(--ink);border:1px solid var(--rule);padding:4px}
</style></head>
<body>
<div class="bar">
  <span class="word">ontoreview</span>
  <label class="btn" for="file">Open ontology…</label>
  <input id="file" type="file" multiple accept=".ttl,.owl,.rdf,.xml,.jsonld,.json,.nt,.n3,.trig,.yaml,.yml">
  <span class="name" id="name"></span>
  <select id="layout" title="Layout"><option value="single">Single page</option><option value="multi">Multi-page</option></select>
  <button id="export" disabled>Export HTML</button>
  <span class="status" id="status"></span>
</div>
<main>
  <div class="empty" id="empty"><div>
    <b>Open an ontology</b> to preview its documentation. Turtle, RDF/XML, JSON-LD, N-Triples
    and LinkML YAML are supported. For a LinkML schema with imports, select all of its files.
    You can also drop files on this window. Nothing leaves your computer.
  </div></div>
  <iframe id="preview" title="Preview" hidden></iframe>
</main>
<script>
(function(){
  var fileInput=document.getElementById("file"),nameEl=document.getElementById("name"),statusEl=document.getElementById("status"),
      exportBtn=document.getElementById("export"),frame=document.getElementById("preview"),empty=document.getElementById("empty"),
      layout=document.getElementById("layout"),session=null,lastFiles=null;
  function status(t,err){statusEl.textContent=t;statusEl.className="status"+(err?" err":"")}
  function read(f){return new Promise(function(res,rej){var r=new FileReader();r.onload=function(){res({name:f.name,data:r.result.split(",")[1]})};r.onerror=rej;r.readAsDataURL(f)})}
  function load(files){
    if(!files||!files.length)return;lastFiles=files;
    status("Generating…");exportBtn.disabled=true;
    Promise.all(Array.prototype.map.call(files,read)).then(function(items){
      return fetch("api/build",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({files:items,layout:layout.value,session:session})});
    }).then(function(r){return r.json()}).then(function(j){
      if(j.error){status(j.error,true);return}
      session=j.id;nameEl.textContent=j.main;
      frame.hidden=false;empty.hidden=true;frame.src="s/"+j.id+"/index.html?t="+Date.now();
      exportBtn.disabled=false;
      status(j.terms+" terms · "+j.summary.error+" errors, "+j.summary.warning+" warnings");
    }).catch(function(e){status("Failed: "+e,true)});
  }
  fileInput.addEventListener("change",function(){load(fileInput.files)});
  layout.addEventListener("change",function(){if(lastFiles)load(lastFiles)});
  exportBtn.addEventListener("click",function(){if(session)location.href="api/export/"+session});
  ["dragenter","dragover"].forEach(function(t){document.addEventListener(t,function(e){e.preventDefault();document.body.classList.add("drag")})});
  ["dragleave","drop"].forEach(function(t){document.addEventListener(t,function(e){e.preventDefault();document.body.classList.remove("drag")})});
  document.addEventListener("drop",function(e){load(e.dataTransfer.files)});
  fetch("api/preload").then(function(r){return r.json()}).then(function(j){
    if(j&&j.id){session=j.id;nameEl.textContent=j.main;frame.hidden=false;empty.hidden=true;frame.src="s/"+j.id+"/index.html";exportBtn.disabled=false;
      status(j.terms+" terms · "+j.summary.error+" errors, "+j.summary.warning+" warnings")}
  }).catch(function(){});
})();
</script>
</body></html>
"""


class Studio:
    def __init__(self, preload: str | None = None):
        self.root = Path(tempfile.mkdtemp(prefix="ontoreview-studio-"))
        self.sessions: dict[str, dict] = {}
        self.lock = threading.Lock()
        self.preload: dict | None = None
        if preload:
            self.preload = self._build_from_path(Path(preload).resolve(), "single", None)

    def close(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    @staticmethod
    def _pick_main(paths: list[Path]) -> Path:
        rdf = [p for p in paths if p.suffix.lower() in RDF_EXT]
        if rdf:
            return max(rdf, key=lambda p: p.stat().st_size)
        yamls = [p for p in paths if p.suffix.lower() in YAML_EXT and is_linkml_file(p)]
        if not yamls:
            raise ValueError("No ontology file found (expected RDF or a LinkML schema).")
        # the schema that is not imported by another one is the entry point
        names = {p.stem for p in yamls}
        imported = set()
        for p in yamls:
            for m in re.finditer(r"^\s*-\s*([\w./-]+)\s*$", p.read_text("utf-8"), re.M):
                if m.group(1) in names:
                    imported.add(m.group(1))
        roots = [p for p in yamls if p.stem not in imported] or yamls
        return max(roots, key=lambda p: p.stat().st_size)

    def _build_from_path(self, main: Path, layout: str, sid: str | None) -> dict:
        sid = sid or uuid.uuid4().hex[:12]
        site = self.root / sid / "site"
        if site.exists():
            shutil.rmtree(site)
        res = build(main, out=site, layout=layout)
        info = {
            "id": sid, "main": main.name, "source": str(main), "layout": layout,
            "title": res.ontology.metadata.title, "terms": len(res.ontology.terms),
            "summary": res.report.summary if res.report else {"error": 0, "warning": 0, "info": 0},
        }
        with self.lock:
            self.sessions[sid] = info
        return info

    def build_upload(self, payload: dict) -> dict:
        files = payload.get("files") or []
        if not files:
            raise ValueError("No files received.")
        sid = payload.get("session")
        if not (isinstance(sid, str) and re.fullmatch(r"[0-9a-f]{12}", sid)):
            sid = uuid.uuid4().hex[:12]
        src = self.root / sid / "src"
        if src.exists():
            shutil.rmtree(src)
        src.mkdir(parents=True)
        paths = []
        for f in files:
            name = Path(str(f.get("name", "upload"))).name  # strip any directory parts
            if not name or name.startswith("."):
                continue
            p = src / name
            p.write_bytes(base64.b64decode(f.get("data", "")))
            paths.append(p)
        layout = payload.get("layout") if payload.get("layout") in ("single", "multi") else "single"
        return self._build_from_path(self._pick_main(paths), layout, sid)

    def export(self, sid: str) -> tuple[bytes, str]:
        info = self.sessions.get(sid)
        if info is None:
            raise KeyError(sid)
        out = self.root / sid / "export.html"
        build_single_file(info["source"], out)
        stem = re.sub(r"[^A-Za-z0-9_.-]+", "-", Path(info["main"]).stem) or "ontology"
        return out.read_bytes(), f"{stem}.html"


def make_handler(studio: Studio):
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format, *args):  # noqa: A002
            pass

        def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code: int = 200) -> None:
            self._send(code, json.dumps(obj).encode(), "application/json")

        def do_GET(self):  # noqa: N802
            path = unquote(urlparse(self.path).path)
            if path in ("/", "/index.html"):
                return self._send(200, STUDIO_HTML.encode(), "text/html; charset=utf-8")
            if path == "/api/preload":
                return self._json(studio.preload or {})
            m = re.fullmatch(r"/api/export/([0-9a-f]{12})", path)
            if m:
                try:
                    body, fname = studio.export(m.group(1))
                except KeyError:
                    return self._json({"error": "unknown session"}, 404)
                except Exception as e:  # noqa: BLE001
                    return self._json({"error": str(e)}, 500)
                return self._send(200, body, "text/html; charset=utf-8",
                                  {"Content-Disposition": f'attachment; filename="{fname}"'})
            m = re.fullmatch(r"/s/([0-9a-f]{12})/(.*)", path)
            if m:
                site = (studio.root / m.group(1) / "site").resolve()
                target = (site / (m.group(2) or "index.html")).resolve()
                if site not in target.parents and target != site:
                    return self._send(403, b"forbidden", "text/plain")
                if target.is_dir():
                    target = target / "index.html"
                if not target.is_file():
                    return self._send(404, b"not found", "text/plain")
                ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
                if target.suffix == ".ttl":
                    ctype = "text/turtle"
                return self._send(200, target.read_bytes(), ctype)
            self._send(404, b"not found", "text/plain")

        def do_POST(self):  # noqa: N802
            if urlparse(self.path).path != "/api/build":
                return self._send(404, b"not found", "text/plain")
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_UPLOAD:
                return self._json({"error": "Upload too large."}, 413)
            try:
                payload = json.loads(self.rfile.read(n) or b"{}")
                return self._json(studio.build_upload(payload))
            except Exception as e:  # noqa: BLE001
                return self._json({"error": f"{type(e).__name__}: {e}"}, 400)

    return Handler


def serve_studio(host: str = "127.0.0.1", port: int = 8000, preload: str | None = None):
    studio = Studio(preload)
    httpd = http.server.ThreadingHTTPServer((host, port), make_handler(studio))
    return studio, httpd
