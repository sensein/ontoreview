"""ROBOT (http://robot.obolibrary.org) on this machine: a ``robot`` executable on PATH, or the
``obolibrary/robot`` Docker image (pulled on first use).

:func:`robot_command` / :func:`robot_invocation` resolve how to call ROBOT and are shared with
:mod:`.logical_consistency` (``robot reason``). :func:`run_robot` runs ``robot report`` and hands
the TSV to :mod:`ontoreview.report.robot`.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from rdflib import Graph

from ..report.models import ExternalReport
from ..report.robot import robot_report

log = logging.getLogger(__name__)

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


def robot_invocation(mode: str, cmd: list[str], tmp: str | Path):
    """``(base_command, where)`` for running ROBOT on files in ``tmp``.

    ``where(path)`` gives the path ROBOT sees: the same path locally, ``/work/<name>`` in Docker
    (``tmp`` is mounted at /work and the container runs as the current user so files stay removable).
    """
    if mode != "docker":
        return list(cmd), str
    run, img = cmd[:-1], cmd[-1]
    run += ["-v", f"{Path(tmp).resolve()}:/work", "-w", "/work"]
    if hasattr(os, "getuid"):
        run += ["--user", f"{os.getuid()}:{os.getgid()}"]
    return run + [img, "robot"], lambda p: f"/work/{Path(p).name}"


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
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "ontology.owl"
        out = Path(tmp) / "report.tsv"
        graph.serialize(destination=str(src), format="xml")
        prof = None
        if profile:
            prof = Path(tmp) / "profile.tsv"
            shutil.copyfile(Path(profile).expanduser(), prof)
        base, where = robot_invocation(mode, cmd, tmp)
        args = base + ["report", "--input", where(src), "--output", where(out), "--fail-on", "none",
                       "--print", "0"]
        if prof:
            args += ["--profile", where(prof)]
        try:
            proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        except Exception as e:  # noqa: BLE001
            return robot_report(None, f"ROBOT failed to run: {e}")
        if not out.is_file():
            msg = (proc.stderr or proc.stdout or "").strip().splitlines()
            return robot_report(None, "ROBOT report failed" + (f": {msg[-1]}" if msg else ""))
        return robot_report(out.read_text("utf-8"))
