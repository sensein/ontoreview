"""Deploy a documentation website to GitHub Pages: push the folder to a repository whose workflow
(``.github/workflows/pages.yml``, written by every docs build) publishes it.

One local clone per repository is kept in the app's config folder (``deploy/<owner>-<repo>``); each
deploy replaces its files with the website's, commits and pushes. No force-push: the repository keeps
the history of every deploy. Authentication is the user's own git setup (credential helper, SSH key or
``gh auth``); nothing is stored here. With the GitHub CLI (``gh``) installed and logged in, the
repository's Pages source is set to "GitHub Actions" too; otherwise the result says how to do it once.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .deploy import PAGES_WORKFLOW, pages_workflow

GITHUB_REMOTE = re.compile(r"^(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)"
                           r"(?P<owner>[A-Za-z0-9-]+)/(?P<repo>[A-Za-z0-9._-]+?)(?:\.git)?/?$")


class DeployError(RuntimeError):
    """A deploy step failed; the message says what to do."""


@dataclass
class DeployResult:
    remote: str
    branch: str
    pages_url: str
    repo_url: str
    commit: str = ""
    changed: bool = True
    when: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def parse_remote(url: str) -> tuple[str, str]:
    """(owner, repo) of a GitHub remote: https://github.com/o/r(.git) or git@github.com:o/r.git."""
    m = GITHUB_REMOTE.match(url.strip())
    if not m:
        raise DeployError("Use a GitHub repository address, e.g. https://github.com/you/ontology-docs "
                          "or git@github.com:you/ontology-docs.git")
    return m.group("owner"), m.group("repo")


def pages_url(owner: str, repo: str) -> str:
    if repo.lower() == f"{owner.lower()}.github.io":
        return f"https://{owner.lower()}.github.io/"
    return f"https://{owner.lower()}.github.io/{repo}/"


def _git(args: list[str], cwd: Path, git: str = "git", check: bool = True) -> subprocess.CompletedProcess:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}      # never hang on a password prompt
    try:
        r = subprocess.run([git, *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=300)
    except FileNotFoundError as e:
        raise DeployError("git is not installed or not on PATH. Install it from https://git-scm.com") from e
    except subprocess.TimeoutExpired as e:
        raise DeployError(f"git {args[0]} took too long (network?).") from e
    if check and r.returncode != 0:
        msg = (r.stderr or r.stdout).strip().splitlines()
        text = msg[-1] if msg else f"git {args[0]} failed"
        if any(k in (r.stderr or "") for k in ("Authentication failed", "could not read Username",
                                               "Permission denied", "403")):
            text += (" — git could not log in to GitHub. Run `gh auth login` (GitHub CLI), set up a credential "
                     "helper, or use an SSH address with your SSH key.")
        raise DeployError(text)
    return r


def _workdir(root: Path, owner: str, repo: str) -> Path:
    return root / f"{owner}-{repo}".lower()


def _prepare_clone(work: Path, remote: str, branch: str, git: str) -> None:
    if (work / ".git").is_dir():
        _git(["remote", "set-url", "origin", remote], work, git)
        fetch = _git(["fetch", "origin", branch], work, git, check=False)
        if fetch.returncode == 0:
            _git(["checkout", "-B", branch, f"origin/{branch}"], work, git)
            _git(["reset", "--hard", f"origin/{branch}"], work, git)
        return
    work.parent.mkdir(parents=True, exist_ok=True)
    if work.exists():
        shutil.rmtree(work)
    clone = _git(["clone", remote, str(work)], work.parent, git, check=False)
    if clone.returncode != 0:
        if "not found" in clone.stderr.lower() or "does not exist" in clone.stderr.lower():
            raise DeployError(f"Repository not found: {remote}. Create it on GitHub first (it can be empty), "
                              "and check you have write access.")
        _git(["clone", remote, str(work)], work.parent, git)      # raise with git's message
    has_branch = _git(["ls-remote", "--heads", "origin", branch], work, git).stdout.strip()
    if has_branch:
        _git(["checkout", "-B", branch, f"origin/{branch}"], work, git)
    else:                                                          # empty repository or new branch
        _git(["checkout", "--orphan", branch], work, git, check=False)


def _replace_files(work: Path, site: Path) -> None:
    for item in work.iterdir():
        if item.name == ".git":
            continue
        shutil.rmtree(item) if item.is_dir() and not item.is_symlink() else item.unlink()
    for item in site.iterdir():
        target = work / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)


def _enable_pages(owner: str, repo: str) -> str:
    """Set the Pages source to GitHub Actions with the GitHub CLI; '' when done, else what to do."""
    manual = (f"Turn on GitHub Pages once: https://github.com/{owner}/{repo}/settings/pages > "
              "Build and deployment > Source: GitHub Actions.")
    gh = shutil.which("gh")
    if not gh:
        return manual + " (Install the GitHub CLI and run `gh auth login` to let OntoReview do it.)"
    base = ["api", f"repos/{owner}/{repo}/pages", "-H", "Accept: application/vnd.github+json"]
    for method in ("POST", "PUT"):                 # create; or switch an existing site to Actions
        r = subprocess.run([gh, *base, "-X", method, "-f", "build_type=workflow"], capture_output=True,
                           text=True, timeout=60)
        if r.returncode == 0:
            return ""
    return manual


def deploy_site(site: str | Path, remote: str, branch: str = "main", message: str | None = None,
                enable_pages: bool = True, root: Path | None = None, git: str = "git",
                push_to: str | None = None) -> DeployResult:
    """Push the website folder ``site`` to ``remote`` (GitHub) so its Pages workflow publishes it.
    ``push_to`` pushes somewhere else (e.g. a local bare repository in tests) under the same name."""
    site = Path(site).expanduser()
    if not (site / "index.html").is_file():
        raise DeployError(f"{site} is not a documentation website (no index.html). Deploy works for website "
                          "builds only.")
    owner, repo = parse_remote(remote)
    branch = (branch or "main").strip()
    from ..ui_core import SETTINGS_FILE
    work = _workdir(root or SETTINGS_FILE.with_name("deploy"), owner, repo)
    _prepare_clone(work, (push_to or remote).strip(), branch, git)
    _replace_files(work, site)
    wf = work / PAGES_WORKFLOW                 # older builds have no workflow; a branch other than main
    wf.parent.mkdir(parents=True, exist_ok=True)
    wf.write_text(pages_workflow(branch), "utf-8")
    (work / ".nojekyll").touch()
    _git(["add", "-A"], work, git)
    result = DeployResult(remote.strip(), branch, pages_url(owner, repo), f"https://github.com/{owner}/{repo}")
    if not _git(["status", "--porcelain"], work, git).stdout.strip():
        result.changed = False
        result.notes.append("Nothing changed since the last deploy; the site is already up to date.")
    else:
        if _git(["config", "user.email"], work, git, check=False).returncode != 0:
            raise DeployError("git does not know who you are. Run: git config --global user.name \"Your Name\" "
                              "&& git config --global user.email you@example.org")
        _git(["commit", "-m", message or f"Deploy ontology documentation ({site.name})"], work, git)
        _git(["push", "-u", "origin", f"HEAD:{branch}"], work, git)
    result.commit = _git(["rev-parse", "--short", "HEAD"], work, git, check=False).stdout.strip()
    if enable_pages:
        note = _enable_pages(owner, repo)
        if note:
            result.notes.append(note)
    result.notes.append(f"GitHub Actions publishes it in a minute or two: https://github.com/{owner}/{repo}/actions")
    return result


__all__ = ["DeployError", "DeployResult", "deploy_site", "pages_url", "parse_remote"]
