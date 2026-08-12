"""Scripted end-to-end demo — proves the whole pipeline without any service.

Run: python demo/demo_session.py
Shows three flows through the SAME core: a product request, a bug, and the
weekly report — each driven through the CLI adapter's normalisation path.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prodi import Prodi, load_config
from prodi.models import IncomingMessage, Platform


def feed(prodi, user, thread, lines):
    print(f"\n{'='*70}\n  SESSION: {user}\n{'='*70}")
    for line in lines:
        print(f"\n{user} › {line}")
        msg = IncomingMessage(platform=Platform.CLI, channel="#req",
                              user=user, text=line, thread_id=thread)
        for reply in prodi.handle(msg):
            print(f"Prodi › {reply.text}")


def main():
    prodi = Prodi(load_config())

    # 1) A clean product request that is revenue-relevant -> business case.
    #    One trigger message, one form reply -- not one question per message.
    feed(prodi, "csm.anna", "s1", [
        "#req add an AI companion nudge for corporate onboarding",
        "affected_services: iOS\n"
        "client_type: Corporate client\n"
        "client_name: Acme Corp\n"
        "revenue_relevance: upsell\n"
        "budget_ebitda_impact: 150k EBITDA\n"
        "time: Q4 2026\n"
        "customer_value: 8 pts, boosts activation",
    ])

    # 2) Something that's really a bug -> incident board, short-circuits gate.
    #    (bug detected at intake, so the single form includes tech fields too.)
    feed(prodi, "dev.max", "s2", [
        "#req the app crashes on login after the last release",
        "affected_services: iOS\n"
        "client_type: Whitelabel\n"
        "client_name: Helsana\n"
        "revenue_relevance: churn risk\n"
        "budget_ebitda_impact: n/a\n"
        "time: urgent\n"
        "customer_value: critical for retention\n"
        "environment: production\n"
        "reproducible: yes, every login attempt\n"
        "user_impact: all iOS users blocked",
    ])

    # 3) A request that duplicates a planned item -> dedup response.
    feed(prodi, "pm.lea", "s3", [
        "#req new home screen for the mobile app",
        "affected_services: Android\n"
        "client_type: Corporate client\n"
        "client_name: Acme Corp\n"
        "revenue_relevance: new sale\n"
        "budget_ebitda_impact: 80k EBITDA uplift\n"
        "time: Q3 2026\n"
        "customer_value: 5 pts, higher engagement",
    ])

    # 4) Weekly report across everything stored.
    print(f"\n{'='*70}\n  REPORTING AGENT\n{'='*70}\n")
    print(prodi.weekly_report())


if __name__ == "__main__":
    main()
