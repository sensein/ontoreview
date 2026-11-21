"""The deployment kit written into every website, and pushing a website to a GitHub Pages repository
(here a local bare repository standing in for GitHub)."""

import subprocess

import pytest

import ontoreview
from ontoreview.publish import github
from ontoreview.publish.deploy import DEPLOY_FILES, nginx_server, pages_workflow


def test_website_has_deployment_kit(fixtures, tmp_path):
    ontoreview.build(fixtures / "pizza.ttl", out=tmp_path, evaluation={"oops": "off"})
    for rel in DEPLOY_FILES:
        assert (tmp_path / rel).is_file(), rel
    wf = (tmp_path / ".github/workflows/pages.yml").read_text()
    assert "actions/deploy-pages@v4" in wf and "branches: [main]" in wf and "path: ." in wf
    readme = (tmp_path / "DEPLOY.md").read_text()
    assert "GitHub Pages" in readme and "docker compose up" in readme and "content negotiation" in readme
    assert "COPY . /usr/share/nginx/html" in (tmp_path / "Dockerfile").read_text()
    assert '"~text/turtle" /ontology.ttl;' in (tmp_path / "deploy/nginx.conf").read_text()


def test_no_kit_when_turned_off(fixtures, tmp_path):
    ontoreview.build(fixtures / "pizza.ttl", out=tmp_path, deploy_files=False, evaluation={"oops": "off"})
    assert not (tmp_path / "DEPLOY.md").exists() and not (tmp_path / ".github").exists()


def test_collection_gets_one_kit(fixtures, tmp_path):
    from ontoreview.collection import build_collection
    src = tmp_path / "src"
    src.mkdir()
    for f in ("pizza.ttl", "colors-skos.ttl"):
        (src / f).write_bytes((fixtures / f).read_bytes())
    build_collection(src, tmp_path / "out", evaluation={"oops": "off"})
    assert (tmp_path / "out" / "DEPLOY.md").is_file()
    assert not list((tmp_path / "out").glob("*/DEPLOY.md"))


def test_workflow_branch_and_nginx_escaping():
    assert "branches: [gh-pages]" in pages_workflow("gh-pages")
    assert '"~application/rdf[+]xml" /o.owl;' in nginx_server([{"media": "application/rdf+xml", "file": "o.owl"}])


@pytest.mark.parametrize("url, owner, repo, pages", [
    ("https://github.com/you/onto-docs", "you", "onto-docs", "https://you.github.io/onto-docs/"),
    ("https://github.com/You/onto-docs.git", "You", "onto-docs", "https://you.github.io/onto-docs/"),
    ("git@github.com:you/you.github.io.git", "you", "you.github.io", "https://you.github.io/"),
])
def test_parse_remote(url, owner, repo, pages):
    assert github.parse_remote(url) == (owner, repo)
    assert github.pages_url(owner, repo) == pages


def test_parse_remote_rejects_other_hosts():
    with pytest.raises(github.DeployError, match="GitHub repository"):
        github.parse_remote("https://gitlab.com/you/docs")


def _git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def test_deploy_pushes_and_updates(fixtures, tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@example.org")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "test@example.org")
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(bare)], check=True, capture_output=True)
    site = tmp_path / "site"
    ontoreview.build(fixtures / "pizza.ttl", out=site, evaluation={"oops": "off"})
    work = tmp_path / "deploy"
    monkeypatch.setattr(github, "_git", _with_identity(github._git))
    r = github.deploy_site(site, "https://github.com/you/onto-docs", enable_pages=False, root=work, push_to=str(bare))
    assert r.changed and r.pages_url == "https://you.github.io/onto-docs/" and r.commit
    files = _git("ls-tree", "-r", "--name-only", "main", cwd=bare).split()
    assert "index.html" in files and ".github/workflows/pages.yml" in files and ".nojekyll" in files
    again = github.deploy_site(site, "https://github.com/you/onto-docs", enable_pages=False, root=work,
                               push_to=str(bare))
    assert not again.changed                                         # nothing new: no empty commit
    (site / "extra.txt").write_text("new")
    third = github.deploy_site(site, "https://github.com/you/onto-docs", enable_pages=False, root=work,
                               push_to=str(bare))
    assert third.changed and len(_git("log", "--oneline", "main", cwd=bare).splitlines()) == 2   # history kept
    with pytest.raises(github.DeployError, match="not a documentation website"):
        github.deploy_site(tmp_path, "https://github.com/you/onto-docs", root=work, push_to=str(bare))


def _with_identity(real):
    """Tests run without a global git identity: give commits one."""
    def wrapped(args, cwd, git="git", check=True):
        if args and args[0] in ("commit", "config") and args[:2] != ["config", "user.email"]:
            args = ["-c", "user.name=Test", "-c", "user.email=test@example.org", *args]
        if args[:2] == ["config", "user.email"]:
            args = ["-c", "user.email=test@example.org", *args]
        return real(args, cwd, git, check)
    return wrapped
