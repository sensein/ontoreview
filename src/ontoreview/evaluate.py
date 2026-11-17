"""External ontology evaluators: OOPS! (web service) and ROBOT report (local or Docker).

* ROBOT (http://robot.obolibrary.org/report) runs on this machine: a ``robot`` executable on
  PATH, or the ``obolibrary/robot`` Docker image (pulled on first use). It runs by default.
* OOPS! (https://oops.linkeddata.es/webservice.html) is a web service: the ontology is sent to
  it. With ``oops = "auto"`` (default) it is the fallback when ROBOT cannot run (no Docker, or
  ROBOT failed); ``oops = "on"`` always runs it, ``oops = "off"`` never does.
"""

from __future__ import annotations

import csv
import logging
import os
import shutil
import subprocess
import tempfile
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path

from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import RDF

log = logging.getLogger(__name__)

OOPS_ENDPOINT = "https://oops.linkeddata.es/rest"
OOPS = Namespace("http://oops.linkeddata.es/def#")
# the web service documentation's RDF/XML responses use this namespace; accept both
OOPS_OEG = Namespace("http://www.oeg-upm.net/oops#")
OOPS_LEVELS = {"critical": "error", "important": "warning", "minor": "info"}
ROBOT_LEVELS = {"error": "error", "warn": "warning", "info": "info"}


@dataclass
class ExternalItem:
    code: str
    name: str
    severity: str  # error | warning | info
    description: str = ""
    affected: list[str] = field(default_factory=list)
    note: str = ""  # free-text affected elements (OOPS! sometimes returns prose)


@dataclass
class ExternalReport:
    tool: str
    url: str
    items: list[ExternalItem] = field(default_factory=list)
    error: str | None = None

    @property
    def summary(self) -> dict[str, int]:
        out = {"error": 0, "warning": 0, "info": 0}
        for i in self.items:
            out[i.severity] = out.get(i.severity, 0) + 1
        return out

    def to_dict(self) -> dict:
        return asdict(self) | {"summary": self.summary}


# ----------------------------------------------------------------------- OOPS!
def run_oops(graph: Graph, timeout: int = 90, endpoint: str = OOPS_ENDPOINT) -> ExternalReport:
    log.info("Running OOPS! pitfall scan (%s)", endpoint)
    report = ExternalReport("OOPS!", "https://oops.linkeddata.es")
    rdfxml = graph.serialize(format="xml")
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n<OOPSRequest><OntologyURI></OntologyURI>'
        f"<OntologyContent><![CDATA[{rdfxml.replace(']]>', ']]]]><![CDATA[>')}]]></OntologyContent>"
        "<Pitfalls></Pitfalls><OutputFormat>RDF/XML</OutputFormat></OOPSRequest>"
    )
    req = urllib.request.Request(endpoint, data=body.encode("utf-8"),
                                 headers={"Content-Type": "application/xml",
                                          "User-Agent": "ontoreview (ontology documentation)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        report.error = f"OOPS! request failed: {e}"
        return report
    try:
        report.items = parse_oops(text)
    except Exception as e:  # noqa: BLE001
        report.error = f"Could not parse the OOPS! response: {e}"
    return report


def parse_oops(rdfxml: str) -> list[ExternalItem]:
    items: list[ExternalItem] = []
    g = Graph()
    g.parse(data=rdfxml, format="xml")
    for ns in (OOPS, OOPS_OEG):
        items += _parse_oops_ns(g, ns)
    rank = {"error": 0, "warning": 1, "info": 2}
    items.sort(key=lambda i: (rank[i.severity], i.code))
    return items


def _parse_oops_ns(g: Graph, OOPS: Namespace) -> list[ExternalItem]:  # noqa: N803
    items: list[ExternalItem] = []
    for kind, default_sev in ((OOPS.pitfall, None), (OOPS.warning, "warning"), (OOPS.suggestion, "info")):
        for node in g.subjects(RDF.type, kind):
            code = str(g.value(node, OOPS.hasCode) or ("Warning" if default_sev == "warning" else
                                                       "Suggestion" if default_sev == "info" else ""))
            level = str(g.value(node, OOPS.hasImportanceLevel) or "").lower()
            sev = OOPS_LEVELS.get(level, default_sev or "info")
            affected, note = [], []
            for a in g.objects(node, OOPS.hasAffectedElement):
                s = str(a).strip()
                (affected if s.startswith(("http://", "https://", "urn:")) and " " not in s else note).append(s)
            for p in (OOPS.mightBeEquivalentProperty, OOPS.mightBeEquivalentAttribute, OOPS.mightNotBeInverseOf):
                for grp in g.objects(node, p):
                    affected += [str(x) for x in g.objects(grp, OOPS.hasAffectedElement)]
            items.append(ExternalItem(
                code=code, name=str(g.value(node, OOPS.hasName) or code), severity=sev,
                description=" ".join(str(g.value(node, OOPS.hasDescription) or "").split()),
                affected=sorted(set(affected)), note=" ".join(note),
            ))
    return items


# ----------------------------------------------------------------------- ROBOT
DEFAULT_ROBOT_IMAGE = "obolibrary/robot"


def _docker() -> str | None:
    """The docker executable, if the Docker daemon is reachable."""
    exe = shutil.which("docker")
    if not exe:
        return None
    try:
        ok = subprocess.run([exe, "info", "--format", "{{.ServerVersion}}"], capture_output=True,
                            text=True, timeout=15).returncode == 0
    except Exception:  # noqa: BLE001
        return None
    return exe if ok else None


def _image_present(docker: str, image: str) -> bool:
    try:
        return subprocess.run([docker, "image", "inspect", image], capture_output=True,
                              timeout=15).returncode == 0
    except Exception:  # noqa: BLE001
        return False


def robot_command(robot: str | None = None, image: str | None = None,
                  pull: bool = False) -> tuple[str, list[str]] | None:
    """Resolve how to invoke ROBOT.

    Returns ``("local", [exe])`` for a ``robot`` executable (``robot`` / ``evaluation.robot_path``
    on PATH), or ``("docker", [docker, "run", ..., image, "robot"])`` for the ROBOT Docker image.
    With ``pull=False`` the image is only used when it is already present locally, so an
    automatic run never downloads it.
    """
    for c in ([robot] if robot else []) + ["robot"]:
        exe = shutil.which(str(Path(c).expanduser()))
        if exe:
            return "local", [exe]
    image = image or os.environ.get("ROBOT_DOCKER_IMAGE") or DEFAULT_ROBOT_IMAGE
    docker = _docker()
    if docker and (pull or _image_present(docker, image)):
        return "docker", [docker, "run", "--rm", image]
    return None


def run_robot(graph: Graph, robot: str | None = None, profile: str | None = None,
              timeout: int = 900, image: str | None = None, pull: bool = True) -> ExternalReport | None:
    """Run ``robot report`` locally or in Docker. Returns None when ROBOT is not available."""
    resolved = robot_command(robot, image, pull)
    if resolved is None:
        return None
    mode, cmd = resolved
    if mode == "docker":
        log.info("Running ROBOT report in Docker (%s)", cmd[-1])
    else:
        log.info("Running ROBOT report (%s)", cmd[0])
    report = ExternalReport("ROBOT", "http://robot.obolibrary.org/report")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "ontology.owl"
        out = Path(tmp) / "report.tsv"
        graph.serialize(destination=str(src), format="xml")
        prof = None
        if profile:
            prof = Path(tmp) / "profile.tsv"
            shutil.copyfile(Path(profile).expanduser(), prof)
        if mode == "docker":
            # mount the temp dir at /work; run as the current user so output files stay removable
            run, img = cmd[:-1], cmd[-1]
            run += ["-v", f"{Path(tmp).resolve()}:/work", "-w", "/work"]
            if hasattr(os, "getuid"):
                run += ["--user", f"{os.getuid()}:{os.getgid()}"]
            base, where = run + [img, "robot"], lambda p: f"/work/{p.name}"
        else:
            base, where = cmd, str
        args = base + ["report", "--input", where(src), "--output", where(out), "--fail-on", "none",
                       "--print", "0"]
        if prof:
            args += ["--profile", where(prof)]
        try:
            proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        except Exception as e:  # noqa: BLE001
            report.error = f"ROBOT failed to run: {e}"
            return report
        if not out.is_file():
            msg = (proc.stderr or proc.stdout or "").strip().splitlines()
            report.error = "ROBOT report failed" + (f": {msg[-1]}" if msg else "")
            return report
        report.items = parse_robot_tsv(out.read_text("utf-8"))
    return report


def parse_robot_tsv(text: str) -> list[ExternalItem]:
    grouped: dict[tuple[str, str], ExternalItem] = {}
    reader = csv.DictReader(text.splitlines(), delimiter="\t")
    for row in reader:
        level = ROBOT_LEVELS.get((row.get("Level") or "").strip().lower(), "info")
        rule = (row.get("Rule Name") or "").strip()
        key = (level, rule)
        item = grouped.get(key)
        if item is None:
            item = ExternalItem(code=rule, name=rule.replace("_", " ").capitalize(), severity=level)
            grouped[key] = item
        subject = (row.get("Subject") or "").strip()
        if subject:
            item.affected.append(subject)
    rank = {"error": 0, "warning": 1, "info": 2}
    items = list(grouped.values())
    for i in items:
        i.affected = sorted(set(i.affected))
    items.sort(key=lambda i: (rank[i.severity], i.code))
    return items


def run_evaluations(graph: Graph, config) -> list[ExternalReport]:
    """ROBOT first (local or Docker); OOPS! web service as fallback, or always with oops = "on"."""
    ev = config.evaluation
    out: list[ExternalReport] = []
    robot_ok = False
    if ev.robot != "off":
        r = run_robot(graph, ev.robot_path, ev.robot_profile, image=ev.robot_image)
        if r is None:
            if ev.robot == "on":
                out.append(ExternalReport("ROBOT", "http://robot.obolibrary.org/report",
                                          error="ROBOT is not available: start Docker (image "
                                                f"{ev.robot_image}) or put `robot` on PATH."))
        else:
            out.append(r)
            robot_ok = r.error is None
    fallback = ev.oops == "auto" and ev.robot != "off" and not robot_ok
    if ev.oops == "on" or fallback:
        if fallback:
            log.info("ROBOT could not run; using the OOPS! web service instead (uploads the ontology "
                     "to oops.linkeddata.es; set evaluation.oops = \"off\" to disable).")
        out.append(run_oops(graph, ev.oops_timeout, ev.oops_endpoint or OOPS_ENDPOINT))
    for r in out:
        if r.error:
            log.warning(r.error)
    return out


def curie_for(iri: str, ontology) -> tuple[str, str | None]:
    """Display label + internal anchor for an affected element."""
    t = ontology.terms.get(iri)
    if t is not None:
        return t.label, t.anchor
    return iri, None


__all__ = ["ExternalItem", "ExternalReport", "run_oops", "run_robot", "run_evaluations", "URIRef"]
