"""External ontology evaluators: OOPS! (web service) and ROBOT report (local, Java).

* OOPS! (https://oops.linkeddata.es) sends the ontology to a remote service, so it only runs
  when enabled (``[evaluation] oops = true`` or ``--oops``).
* ROBOT (http://robot.obolibrary.org/report) runs locally. With ``robot = "auto"`` (default)
  it runs whenever a ``robot`` executable or a configured ``robot.jar`` is available.
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
    g = Graph()
    g.parse(data=rdfxml, format="xml")
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
    rank = {"error": 0, "warning": 1, "info": 2}
    items.sort(key=lambda i: (rank[i.severity], i.code))
    return items


# ----------------------------------------------------------------------- ROBOT
def robot_command(robot: str | None = None) -> list[str] | None:
    """Resolve how to invoke ROBOT: an executable, or ``java -jar robot.jar``."""
    candidates = [robot] if robot else []
    candidates += [os.environ.get("ROBOT_JAR"), "robot"]
    for c in candidates:
        if not c:
            continue
        if c.endswith(".jar"):
            p = Path(c).expanduser()
            java = shutil.which("java")
            if p.is_file() and java:
                return [java, "-jar", str(p)]
            continue
        exe = shutil.which(c)
        if exe:
            return [exe]
    return None


def run_robot(graph: Graph, robot: str | None = None, profile: str | None = None,
              timeout: int = 600) -> ExternalReport | None:
    """Run ``robot report``. Returns None when ROBOT is not available."""
    cmd = robot_command(robot)
    if cmd is None:
        return None
    report = ExternalReport("ROBOT", "http://robot.obolibrary.org/report")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "ontology.owl"
        out = Path(tmp) / "report.tsv"
        graph.serialize(destination=str(src), format="xml")
        args = cmd + ["report", "--input", str(src), "--output", str(out), "--fail-on", "none",
                      "--print", "0"]
        if profile:
            args += ["--profile", str(profile)]
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
    ev = config.evaluation
    out: list[ExternalReport] = []
    if ev.robot != "off":
        r = run_robot(graph, ev.robot_path, ev.robot_profile)
        if r is None and ev.robot == "on":
            out.append(ExternalReport("ROBOT", "http://robot.obolibrary.org/report",
                                      error="ROBOT is not installed (set evaluation.robot_path or ROBOT_JAR)."))
        elif r is not None:
            out.append(r)
    if ev.oops:
        out.append(run_oops(graph, ev.oops_timeout))
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
