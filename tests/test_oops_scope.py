"""OOPS! alongside ROBOT: which pitfalls are requested and how the review explains it."""

import pytest

from ontoreview.quality_checks import oops
from ontoreview.report.oops import oops_scope


def _capture(monkeypatch):
    sent = {}

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'<?xml version="1.0"?><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"/>'

    def fake_urlopen(req, timeout=0):
        sent["body"] = req.data.decode()
        return Resp()
    monkeypatch.setattr(oops.urllib.request, "urlopen", fake_urlopen)
    return sent


@pytest.mark.real_evaluators          # the real run_oops; only the HTTP call is faked
def test_request_leaves_out_what_robot_covers(monkeypatch, pizza):
    loaded, _ = pizza
    sent = _capture(monkeypatch)
    rep = oops.run_oops(loaded.graph, skip=oops.ROBOT_COVERED)
    listed = sent["body"].split("<Pitfalls>")[1].split("</Pitfalls>")[0].split(",")
    assert "P08" not in listed and "P32" not in listed and "P41" not in listed
    assert "P04" in listed and "P11" in listed and len(listed) == 38
    assert "Not run here because ROBOT already checks them" in rep.scope and "P32" in rep.scope
    rep = oops.run_oops(loaded.graph, robot_state="unavailable")
    assert "<Pitfalls></Pitfalls>" in sent["body"]                     # empty list = full catalogue
    assert rep.scope == "Full pitfall catalogue (ROBOT was not available)."


def test_scope_text():
    assert oops_scope(None, "off") == "Full pitfall catalogue (ROBOT is turned off)."
    assert oops_scope(None, "ok") == "Full pitfall catalogue."
