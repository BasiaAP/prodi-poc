import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prodi.config import load_config
from prodi.engine import ValidationEngine
from prodi.models import RequestState

CFG = load_config()
ENGINE = ValidationEngine(CFG)


def _state(**fields):
    s = RequestState(session_key="k", user="u", channel="#req")
    s.fields.update(fields)
    return s


def test_bug_detection():
    assert ENGINE.looks_like_bug("the app crashes on login")
    assert ENGINE.looks_like_bug("production down for all users")
    assert not ENGINE.looks_like_bug("please add a meditation library")


def test_bug_detection_catches_natural_phrasing_without_false_positives():
    # Real PoC test case: describes a bug (timing discrepancy) with none of
    # the canonical words like "bug"/"broken"/"error".
    assert ENGINE.looks_like_bug(
        "in-app messages show up a day earlier than they are set on CMS; "
        "it looks as if they went live a day early - any time discrepancies?")
    # Ordinary product-request phrasing must NOT trip the bug path just
    # because it shares generic words like "should be" / "earlier than".
    assert not ENGINE.looks_like_bug(
        "users should be able to see their weekly progress on the home screen")
    assert not ENGINE.looks_like_bug(
        "we would like this feature delivered earlier than Q4 if possible")


def test_bug_routes_to_incident_board():
    s = _state(title="login broken", description="users cannot login, service degraded")
    cls = ENGINE.validate(s)
    assert cls.kind == "incident"
    assert cls.target_board == CFG["routing"]["incident_board"]


def test_owner_assignment_by_structured_field():
    # Application(s) = HUMANOO -> Basia (first rule, structured field match).
    s = _state(title="new home screen", description="for core mobile",
               applications="HUMANOO")
    owner, _ = ENGINE.assign_owner(s)
    assert owner == "Basia"

    # Nothing matches any rule's dimensions -> falls to Julia, the catch-all.
    s2 = _state(title="a generic request", description="no signals here",
                applications="WLP")
    owner2, area2 = ENGINE.assign_owner(s2)
    assert owner2 == "Julia"
    assert area2 == "Other apps / clients"

    # client_name "CSS" -> Sofia, even with no keyword match in the text.
    s3 = _state(title="loyalty widget", description="for the app",
               client_name="CSS")
    owner3, _ = ENGINE.assign_owner(s3)
    assert owner3 == "Sofia"


def test_duplicate_detection():
    s = _state(title="Home screen refresh", description="new home screen layout")
    cls = ENGINE.validate(s)
    assert cls.duplicate_ref == "PROD-123"
    assert cls.duplicate_status == "in_development"


def test_gating_missing_fields():
    s = _state(title="x")
    missing = s.missing(ENGINE.required_fields(s))
    assert "description" in missing and "applications" in missing


def test_taxonomy_recommendation():
    s = _state(title="AI companion improvement", description="upsell premium ai coaching")
    taxo = ENGINE.recommend_taxonomy(s)
    assert taxo["category"] == "AI Layer"
    assert taxo["bucket"] == "Paid Upsell"


class _StubIdeaBoard:
    """Fake live-board checker - no network, just proves the engine
    delegates to an injected checker instead of the seeded PoC list."""
    def __init__(self, result):
        self.result = result
        self.calls = []

    def check(self, text):
        self.calls.append(text)
        return self.result


def test_duplicate_check_delegates_to_injected_idea_board():
    stub = _StubIdeaBoard({"ref": "PRODUCT-999", "title": "Something",
                           "status": "planned", "owner": "Rafia"})
    engine = ValidationEngine(CFG, idea_board=stub)
    s = _state(title="anything at all", description="doesn't matter for this test")
    cls = engine.validate(s)
    assert cls.duplicate_ref == "PRODUCT-999"
    assert cls.duplicate_status == "planned"
    assert stub.calls  # the engine actually called the injected checker

    # No idea_board injected -> falls back to the seeded PoC list, unaffected.
    assert ENGINE.idea_board is None


class _StubSquadBacklog:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def check(self, text, squad_board):
        self.calls.append((text, squad_board))
        return self.result


def test_squad_duplicate_check_delegates_to_injected_backlog():
    stub = _StubSquadBacklog({"ref": "HUM-26863", "title": "Something",
                              "board": "HUM", "owner": "bulat.islamov"})
    engine = ValidationEngine(CFG, squad_backlog=stub)
    s = _state(title="the app crashes", description="on every launch")
    cls = engine.validate(s)
    assert cls.kind == "bug"
    assert cls.duplicate_ref == "HUM-26863"
    assert cls.owner == "bulat.islamov"  # real ticket's owner, not the guess
    assert stub.calls

    assert ENGINE.squad_backlog is None
