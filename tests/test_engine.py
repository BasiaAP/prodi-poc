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
    s = _state(title="login broken", summary="users cannot login, service degraded")
    cls = ENGINE.validate(s)
    assert cls.kind == "incident"
    assert cls.target_board == CFG["routing"]["incident_board"]


def test_owner_by_keyword():
    owner, area = ENGINE.assign_owner("new home screen for core mobile")
    assert owner == "Basia"
    owner2, _ = ENGINE.assign_owner("white label client request from Helsana")
    assert owner2 == "Julia"


def test_duplicate_detection():
    s = _state(title="Home screen refresh", summary="new home screen layout")
    cls = ENGINE.validate(s)
    assert cls.duplicate_ref == "PROD-123"
    assert cls.duplicate_status == "in_development"


def test_gating_missing_fields():
    s = _state(title="x")
    missing = s.missing(ENGINE.required_fields(s))
    assert "summary" in missing and "customer_value" in missing


def test_taxonomy_recommendation():
    s = _state(title="AI companion improvement", summary="upsell premium ai coaching")
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
    s = _state(title="anything at all", summary="doesn't matter for this test")
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
    s = _state(title="the app crashes", summary="on every launch")
    cls = engine.validate(s)
    assert cls.kind == "bug"
    assert cls.duplicate_ref == "HUM-26863"
    assert cls.owner == "bulat.islamov"  # real ticket's owner, not the guess
    assert stub.calls

    assert ENGINE.squad_backlog is None
