import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prodi import Prodi, load_config
from prodi.models import Decision, IncomingMessage, Platform


def _msg(text, user="alice", channel="#req", thread="t1"):
    return IncomingMessage(platform=Platform.CLI, channel=channel, user=user,
                           text=text, thread_id=thread)


def _run(prodi, texts):
    last = []
    for t in texts:
        last = prodi.handle(_msg(t))
    return last


def test_full_product_flow_accepts_and_routes():
    prodi = Prodi(load_config())
    # First message triggers and gets back a single form (not one question
    # per message); the second message answers everything in one shot.
    answers = [
        "#req add a sleep coaching program",   # trigger (seeds title/description)
        "applications: HUMANOO\n"
        "affected_services: iOS\n"
        "client_type: Corporate Client\n"
        "client_name: Acme Corp\n"
        "revenue_relevance: Upsell\n"
        "revenue_impact: 200k EBITDA uplift",
    ]
    replies = _run(prodi, answers)
    text = " ".join(r.text for r in replies)
    assert any(r.fields.get("decision") == Decision.ACCEPTED.value for r in replies)
    assert "PREQS" in text
    assert "Basia" in text  # applications: HUMANOO
    # revenue-relevant -> a business case draft is produced
    assert any("Business Case" in r.text for r in replies)
    assert len(prodi.store.all_requests()) == 1
    assert len(prodi.store.all_business_cases()) == 1


def test_bug_flow_short_circuits_to_incident():
    prodi = Prodi(load_config())
    answers = [
        "#req login is broken and users cannot login",  # trigger -> looks like bug
        "environment: prod\n"
        "reproducible: yes, every login\n"
        "user_impact: all users blocked\n"
        "applications: HUMANOO\n"
        "affected_services: iOS\n"
        "client_type: Whitelabel\n"
        "client_name: Helsana\n"
        "revenue_relevance: Churn Risk\n"
        "revenue_impact: n/a",
    ]
    replies = _run(prodi, answers)
    assert any(r.fields.get("decision") == Decision.BUG_INCIDENT.value
               for r in replies)
    # Incident path: owner tagged, no dedup performed.
    assert any("PM" in r.text and "notified and assigned" in r.text for r in replies)


def test_bug_with_existing_squad_ticket_is_referenced_not_duplicated():
    # Matches squad_backlog_seed's CORE-88 (login-related, HUM) via
    # bug keyword "error" - not "cannot login", so this is a bug, not an
    # incident. Should reference CORE-88 instead of opening a new ticket.
    prodi = Prodi(load_config())
    answers = [
        "#req login screen shows a confusing error on iOS",
        "environment: prod\n"
        "reproducible: yes, on every attempt\n"
        "user_impact: confusing but not blocking\n"
        "applications: HUMANOO\n"
        "affected_services: iOS\n"
        "client_type: Corporate Client\n"
        "client_name: Acme\n"
        "revenue_relevance: None\n"
        "revenue_impact: n/a",
    ]
    replies = _run(prodi, answers)
    assert any(r.fields.get("decision") == Decision.BUG_INCIDENT.value for r in replies)
    text = " ".join(r.text for r in replies)
    assert "CORE-88" in text
    # The existing ticket's real owner (Rafia, per squad_backlog_seed) wins
    # over the keyword-matched guess - ground truth beats speculation, even
    # though the guess here would fall through to Julia (catch-all; nothing
    # in this text matches a structured rule).
    assert "Rafia" in text
    assert "Julia" not in text
    assert len(prodi.store.all_requests()) == 0  # no new ticket opened


def test_bug_with_no_existing_ticket_opens_a_new_squad_backlog_item():
    # Nothing here matches a structured owner rule (no CMS/marketplace, no
    # CSS/AI companion, no web app/HealthOS keywords) -> falls to Julia, the
    # catch-all. Owner assignment is now field-aware rather than a generic
    # "mobile/android/ios" keyword match, so this is NOT Basia even though
    # the bug is Android-specific - see the summary note on this tradeoff.
    prodi = Prodi(load_config())
    answers = [
        "#req the settings toggle crashes on Android",
        "environment: prod\n"
        "reproducible: yes, every time\n"
        "user_impact: settings unusable\n"
        "applications: WLP\n"
        "affected_services: Android\n"
        "client_type: Corporate Client\n"
        "client_name: Acme\n"
        "revenue_relevance: None\n"
        "revenue_impact: n/a",
    ]
    replies = _run(prodi, answers)
    assert any(r.fields.get("decision") == Decision.BUG_INCIDENT.value for r in replies)
    text = " ".join(r.text for r in replies)
    assert "HUM" in text
    assert "Julia" in text
    assert len(prodi.store.all_requests()) == 1  # a new ticket was opened


def test_owner_assignment_by_structured_field():
    # CMS/Marketplace -> Berke, via the real Affected services value "CMS".
    prodi = Prodi(load_config())
    replies = _run(prodi, [
        "#req allow bulk-editing content entries",
        "applications: WLP\n"
        "affected_services: CMS\n"
        "client_type: Corporate Client\n"
        "client_name: Acme\n"
        "revenue_relevance: None\n"
        "revenue_impact: n/a",
    ])
    text = " ".join(r.text for r in replies)
    assert "Berke" in text

    # CSS client -> Sofia, via client_name (CSS isn't a real Application(s)
    # or Client Type value, so this can only match on client_name).
    prodi2 = Prodi(load_config())
    replies2 = _run(prodi2, [
        "#req add a loyalty points widget",
        "applications: WLP\n"
        "affected_services: iOS\n"
        "client_type: Whitelabel\n"
        "client_name: CSS\n"
        "revenue_relevance: None\n"
        "revenue_impact: n/a",
    ])
    text2 = " ".join(r.text for r in replies2)
    assert "Sofia" in text2


def test_trigger_returns_a_single_form_not_one_question_at_a_time():
    prodi = Prodi(load_config())
    replies = prodi.handle(_msg("#req add a sleep coaching program"))
    assert len(replies) == 1
    text = replies[0].text
    # The one reply lists every remaining MUST HAVE at once.
    for field in ("applications", "affected_services", "client_type", "client_name",
                  "revenue_relevance", "revenue_impact"):
        assert field in text


def test_in_development_duplicate_skips_the_one_pager():
    # PRD 1.b.i: duplicate exists AND has a date -> "in development", squad
    # assigned. No fresh business case - work is already active.
    prodi = Prodi(load_config())
    replies = _run(prodi, [
        "#req new home screen for the mobile app",   # matches PROD-123 (in_development)
        "applications: HUMANOO\n"
        "affected_services: Android\n"
        "client_type: Corporate Client\n"
        "client_name: Acme Corp\n"
        "revenue_relevance: New Sale\n"
        "revenue_impact: 80k",
    ])
    assert any(r.fields.get("decision") == Decision.DUPLICATE.value for r in replies)
    assert not any("Business Case" in r.text for r in replies)


def test_planned_duplicate_still_triggers_the_one_pager():
    # PRD 1.b.ii: duplicate exists but has NO date -> "in planning", which
    # still triggers the #idea logic / one-pager generation.
    prodi = Prodi(load_config())
    replies = _run(prodi, [
        "#req insurer reporting dashboard for CSS",   # matches PROD-201 (planned)
        "applications: WLP\n"
        "affected_services: Backend\n"
        "client_type: Whitelabel\n"
        "client_name: CSS\n"
        "revenue_relevance: None\n"
        "revenue_impact: n/a",
    ])
    assert any(r.fields.get("decision") == Decision.DUPLICATE.value for r in replies)
    assert any("Business Case" in r.text for r in replies)


def test_no_duplicate_triggers_the_one_pager_even_without_revenue_relevance():
    # PRD 1.b.iii: no duplicate -> "for consideration later", which also
    # triggers the #idea logic - not gated on revenue_relevance.
    prodi = Prodi(load_config())
    replies = _run(prodi, [
        "#req add a meditation reminder feature",
        "applications: WLP\n"
        "affected_services: iOS\n"
        "client_type: Other\n"
        "client_name: none\n"
        "revenue_relevance: None\n"
        "revenue_impact: n/a",
    ])
    assert any(r.fields.get("decision") == Decision.ACCEPTED.value for r in replies)
    assert any("Business Case" in r.text for r in replies)


def test_non_trigger_is_ignored():
    prodi = Prodi(load_config())
    assert prodi.handle(_msg("good morning team")) == []


def test_weekly_report_groups_by_owner():
    prodi = Prodi(load_config())
    _run(prodi, [
        "#req new home screen for core mobile",
        "applications: HUMANOO\n"
        "affected_services: Android\n"
        "client_type: Corporate Client\n"
        "client_name: Acme\n"
        "revenue_relevance: New Sale\n"
        "revenue_impact: 100k",
    ])
    report = prodi.weekly_report()
    assert "Weekly Product Status" in report
    assert "DRAFT" in report
