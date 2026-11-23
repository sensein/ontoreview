"""Deploy a documentation website to GitHub Pages: push the folder to a repository whose workflow
(``.github/workflows/pages.yml``, written by every docs build) publishes it.

One local clone per repository is kept in the app's config folder (``deploy/<owner>-<repo>``); each
deploy replaces its files with the website's, commits and pushes. No force-push: the repository keeps
the history of every deploy. Authentication is the user's own git setup (credential helper, SSH key or
``gh auth``); nothing is stored here. With the GitHub CLI (``gh``) installed and logged in, the
repository's Pages source is set to "GitHub Actions" too; otherwise the result says how to do it once.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import threading
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .deploy import PAGES_WORKFLOW, pages_workflow

GITHUB_REMOTE = re.compile(r"^(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)"
                           r"(?P<owner>[A-Za-z0-9-]+)/(?P<repo>[A-Za-z0-9._-]+?)(?:\.git)?/?$")


_auth = threading.local()           # this deploy's token header, for network git commands only
NETWORK = ("clone", "fetch", "push", "ls-remote")
JUNK = (".DS_Store", "Thumbs.db", ".ontoreview-build")      # never published
LOGIN_HELP = ("git could not log in to GitHub. Paste a GitHub token in the dialog (a fine-grained token for this "
              "repository with Contents and Pages: read and write), run `gh auth login` (GitHub CLI), or use an "
              "SSH address (git@github.com:you/repo.git) with your SSH key.")


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
    header = getattr(_auth, "header", None)
    cmd = [git, *(["-c", f"http.https://github.com/.extraheader={header}"] if header and args
                  and args[0] in NETWORK else []), *args]    # the token travels as a header, never in a URL
    try:
        r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=300)
    except FileNotFoundError as e:
        raise DeployError("git is not installed or not on PATH. Install it from https://git-scm.com") from e
    except subprocess.TimeoutExpired as e:
        raise DeployError(f"git {args[0]} took too long (network?).") from e
    if check and r.returncode != 0:
        msg = (r.stderr or r.stdout).strip().splitlines()
        text = msg[-1] if msg else f"git {args[0]} failed"
        if any(k in (r.stderr or "") for k in ("Authentication failed", "could not read Username",
                                               "Permission denied", "403", "Invalid username or token")):
            text = LOGIN_HELP
        raise DeployError(text)
    return r


def _workdir(root: Path, owner: str, repo: str) -> Path:
    return root / f"{owner}-{repo}".lower()


def _prepare_clone(work: Path, remote: str, branch: str, git: str) -> None:
    if (work / ".git").is_dir():
        _git(["remote", "set-url", "origin", remote], work, git)
        if _remote_head(work, branch, git):          # raises when GitHub cannot be reached or refuses
            _git(["fetch", "origin", branch], work, git)
            _git(["checkout", "-B", branch, f"origin/{branch}"], work, git)
            _git(["reset", "--hard", f"origin/{branch}"], work, git)
        return                                       # branch not on GitHub yet: the next push creates it
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
        if item.name in JUNK:
            continue
        target = work / item.name
        if item.is_dir():
            shutil.copytree(item, target, ignore=shutil.ignore_patterns(*JUNK))
        else:
            shutil.copy2(item, target)


def _api(method: str, path: str, token: str, body: dict | None = None) -> tuple[int, dict]:
    """GitHub REST call -> (status, JSON body); status 0 when GitHub cannot be reached."""
    req = urllib.request.Request(f"https://api.github.com{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None, headers={
                                     "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                                     "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "ontoreview"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 - fixed GitHub API host
            raw = r.read()
            return r.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}
    except OSError:
        return 0, {}


def token_status(token: str) -> str:
    """Who a token belongs to and, for classic tokens, its scopes; raises DeployError when refused."""
    req = urllib.request.Request("https://api.github.com/user", headers={
        "Authorization": f"Bearer {token.strip()}", "Accept": "application/vnd.github+json", "User-Agent": "ontoreview"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310 - fixed GitHub API host
            login = json.loads(r.read()).get("login", "?")
            scopes = r.headers.get("X-OAuth-Scopes")
    except urllib.error.HTTPError as e:
        raise DeployError("GitHub refused this token (expired, revoked or mistyped)." if e.code == 401
                          else f"GitHub answered {e.code}.") from e
    except OSError as e:
        raise DeployError("Could not reach GitHub.") from e
    if scopes is None:
        return f"Works: fine-grained token of {login}. It needs Contents, Pages, Workflows and Administration " \
               "(to create repositories and allow your branch to deploy): read and write."
    have = {x.strip() for x in scopes.split(",") if x.strip()}
    missing = [x for x in ("repo", "workflow") if x not in have and not (x == "repo" and "public_repo" in have)]
    return f"Works: classic token of {login} (scopes: {', '.join(sorted(have)) or 'none'})." + \
        (f" Missing: {', '.join(missing)} — needed to push the site and its workflow." if missing else "")


def ensure_repo(owner: str, repo: str, token: str, private: bool = False, description: str = "") -> bool:
    """Create ``owner/repo`` when it does not exist (under the token's account, or the organisation
    ``owner``). True when it was created, False when it already existed."""
    status, _ = _api("GET", f"/repos/{owner}/{repo}", token)
    if status == 200:
        return False
    if status == 401:
        raise DeployError("The GitHub token was refused (expired or mistyped). Update it in Settings › General.")
    if status not in (404, 403):
        raise DeployError("Could not reach GitHub to check the repository." if status == 0 else
                          f"GitHub answered {status} when checking {owner}/{repo}.")
    _, me = _api("GET", "/user", token)
    body = {"name": repo, "private": private, "auto_init": False,
            "description": description or "Ontology documentation, published with OntoReview"}
    path = "/user/repos" if (me.get("login") or "").lower() == owner.lower() else f"/orgs/{owner}/repos"
    status, data = _api("POST", path, token, body)
    if status == 201:
        return True
    why = data.get("message", "")
    raise DeployError(f"Could not create {owner}/{repo} ({status} {why}). If your token is limited to selected "
                      "repositories, create the repository on GitHub and add it to the token, then deploy again. "
                      "To let OntoReview create repositories, use a fine-grained token for all repositories with "
                      "Administration, Contents, Pages and Workflows: read and write (or a classic token with the "
                      "repo and workflow scopes).")


def _pages_api(owner: str, repo: str, token: str) -> bool:
    """Create the Pages site (or switch it) to the GitHub Actions source with the REST API."""
    for method in ("POST", "PUT"):          # create; 409/422 = exists already, then PUT switches it
        status, _ = _api(method, f"/repos/{owner}/{repo}/pages", token, {"build_type": "workflow"})
        if status in (200, 201, 204):
            return True
        if status not in (409, 422):
            return False
    return False


ENV = "github-pages"


def allow_branch(owner: str, repo: str, branch: str, token: str) -> str:
    """Let ``branch`` deploy to the github-pages environment (its protection rules may allow only
    gh-pages, which makes the workflow fail with "Branch … is not allowed to deploy"). '' when done."""
    manual = (f"If the Actions run says \"Branch {branch} is not allowed to deploy to github-pages\": "
              f"https://github.com/{owner}/{repo}/settings/environments > github-pages > Deployment branches "
              f"and tags: add {branch} (or No restriction), then re-run the workflow.")
    base = f"/repos/{owner}/{repo}/environments/{ENV}"
    status, env = _api("GET", base, token)
    policy = (env or {}).get("deployment_branch_policy") if status == 200 else None
    if status == 200 and not policy:
        return ""                                    # no restriction: any branch may deploy
    if status == 200 and policy.get("protected_branches"):
        # protected branches only: switch to an explicit list that keeps whatever was allowed and adds ours
        st, _ = _api("PUT", base, token, {"deployment_branch_policy": {"protected_branches": False,
                                                                       "custom_branch_policies": True}})
        if st not in (200, 201):
            return manual
    elif status == 404:                              # first deploy: create it with an explicit list
        st, _ = _api("PUT", base, token, {"deployment_branch_policy": {"protected_branches": False,
                                                                       "custom_branch_policies": True}})
        if st not in (200, 201):
            return manual
    elif status != 200:
        return manual
    st, data = _api("GET", f"{base}/deployment-branch-policies?per_page=100", token)
    names = {x.get("name") for x in (data or {}).get("branch_policies", [])} if st == 200 else set()
    if branch in names:
        return ""
    st, _ = _api("POST", f"{base}/deployment-branch-policies", token, {"name": branch, "type": "branch"})
    return "" if st in (200, 201) else manual


def _enable_pages(owner: str, repo: str, token: str | None = None, branch: str = "main") -> str:
    """Set the Pages source to GitHub Actions (token: REST API; else the GitHub CLI); '' when done."""
    manual = (f"Turn on GitHub Pages once: https://github.com/{owner}/{repo}/settings/pages > "
              "Build and deployment > Source: GitHub Actions.")
    if token:
        notes = []
        if not _pages_api(owner, repo, token):
            notes.append(manual + " (The token could not do it: it needs Pages: read and write.)")
        allowed = allow_branch(owner, repo, branch, token)   # needs Administration: read and write
        if allowed:
            notes.append(allowed)
        return " ".join(notes)
    gh = shutil.which("gh")
    if not gh:
        return manual + " (Or paste a GitHub token in the dialog, or install the GitHub CLI, to let OntoReview do it.)"
    base = ["api", f"repos/{owner}/{repo}/pages", "-H", "Accept: application/vnd.github+json"]
    for method in ("POST", "PUT"):                 # create; or switch an existing site to Actions
        r = subprocess.run([gh, *base, "-X", method, "-f", "build_type=workflow"], capture_output=True,
                           text=True, timeout=60)
        if r.returncode == 0:
            return ""
    return manual


def deploy_site(site: str | Path, remote: str, branch: str = "main", message: str | None = None,
                enable_pages: bool = True, root: Path | None = None, git: str = "git",
                push_to: str | None = None, token: str | None = None, create: bool = False,
                private: bool = False) -> DeployResult:
    """Push the website folder ``site`` to ``remote`` (GitHub) so its Pages workflow publishes it.
    ``push_to`` pushes somewhere else (e.g. a local bare repository in tests) under the same name."""
    site = Path(site).expanduser()
    if not (site / "index.html").is_file():
        raise DeployError(f"{site} is not a documentation website (no index.html). Deploy works for website "
                          "builds only.")
    owner, repo = parse_remote(remote)
    branch = (branch or "main").strip()
    from .. import telemetry
    telemetry.note_feature("deploy")
    from ..ui_core import SETTINGS_FILE
    work = _workdir(root or SETTINGS_FILE.with_name("deploy"), owner, repo)
    token = (token or "").strip() or None
    _auth.header = ("AUTHORIZATION: basic " + base64.b64encode(f"x-access-token:{token}".encode()).decode()
                    if token else None)
    try:
        created = False
        if create and token and not push_to:
            created = ensure_repo(owner, repo, token, private)
        result = _deploy(site, remote, branch, message, enable_pages, work, git, push_to, token, owner, repo)
        if created:
            result.notes.insert(0, f"Created the {'private' if private else 'public'} repository {owner}/{repo}.")
        elif create and not token:
            result.notes.insert(0, "Creating repositories needs a GitHub token (Settings › General).")
        return result
    finally:
        _auth.header = None


def _remote_head(work: Path, branch: str, git: str) -> str:
    out = _git(["ls-remote", "origin", f"refs/heads/{branch}"], work, git).stdout.split()
    return out[0] if out else ""


def _deploy(site: Path, remote: str, branch: str, message: str | None, enable_pages: bool, work: Path, git: str,
            push_to: str | None, token: str | None, owner: str, repo: str) -> DeployResult:
    _prepare_clone(work, (push_to or remote).strip(), branch, git)
    _replace_files(work, site)
    wf = work / PAGES_WORKFLOW                 # older builds have no workflow; a branch other than main
    wf.parent.mkdir(parents=True, exist_ok=True)
    wf.write_text(pages_workflow(branch), "utf-8")
    (work / ".nojekyll").touch()
    _git(["add", "-A"], work, git)
    result = DeployResult(remote.strip(), branch, pages_url(owner, repo), f"https://github.com/{owner}/{repo}")
    if _git(["status", "--porcelain"], work, git).stdout.strip():
        if _git(["config", "user.email"], work, git, check=False).returncode != 0:
            raise DeployError("git does not know who you are. Run: git config --global user.name \"Your Name\" "
                              "&& git config --global user.email you@example.org")
        _git(["commit", "-m", message or f"Deploy ontology documentation ({site.name})"], work, git)
    head = _git(["rev-parse", "HEAD"], work, git, check=False).stdout.strip()
    if not head:
        raise DeployError("Nothing to deploy: the website folder is empty.")
    # "up to date" means GitHub has this commit, not just the local clone (an earlier push may have failed)
    if _remote_head(work, branch, git) == head:
        result.changed = False
        result.notes.append("GitHub already has this version; the site is up to date.")
    else:
        _git(["push", "-u", "origin", f"HEAD:{branch}"], work, git)
        if _remote_head(work, branch, git) != head:
            raise DeployError(f"The push did not arrive on GitHub ({branch} is not at {head[:7]}). Try again.")
    result.commit = head[:7]
    if enable_pages:
        note = _enable_pages(owner, repo, token, branch)
        if note:
            result.notes.append(note)
    result.notes.append(f"GitHub Actions publishes it in a minute or two: https://github.com/{owner}/{repo}/actions")
    if not token:
        result.notes.append(f"If that run says \"Branch {branch} is not allowed to deploy to github-pages\": "
                            f"https://github.com/{owner}/{repo}/settings/environments > github-pages > Deployment "
                            f"branches and tags: add {branch}, then re-run it.")
    return result


__all__ = ["DeployError", "DeployResult", "deploy_site", "pages_url", "parse_remote"]
