"""Pricing plans — the single source of truth for quotas and entitlements.

Prices are in EUR. `page_quota` is the number of pages included per monthly
billing cycle. A "page" is the unit we meter: 1 page = up to 3,000 characters
of input text (roughly one dense A4 page). PDFs are metered by their real page
count when available.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .config import settings

CHARS_PER_PAGE = 3000


@dataclass(frozen=True)
class Plan:
    key: str
    name: str
    price_eur: int          # monthly price
    page_quota: int         # included pages / month
    features: List[str]
    api_access: bool = False
    custom_schemas: bool = False
    team_seats: int = 1
    webhooks: bool = False
    export_watermark: bool = True
    overage_per_page_eur: float = 0.0  # 0 => hard cap (no overage)

    def stripe_price_id(self) -> str:
        return {
            "starter": settings.stripe_price_starter,
            "pro": settings.stripe_price_pro,
            "business": settings.stripe_price_business,
        }.get(self.key, "")


PLANS: Dict[str, Plan] = {
    "free": Plan(
        key="free",
        name="Free",
        price_eur=0,
        page_quota=25,
        features=[
            "25 pages / month",
            "All extraction templates",
            "Source-grounded viewer",
            "JSON & CSV export (watermarked)",
        ],
        export_watermark=True,
        overage_per_page_eur=0.0,
    ),
    "starter": Plan(
        key="starter",
        name="Starter",
        price_eur=29,
        page_quota=500,
        features=[
            "500 pages / month",
            "All templates",
            "Clean exports (no watermark)",
            "Interactive highlighted viewer",
            "Email support",
        ],
        export_watermark=False,
        overage_per_page_eur=0.05,
    ),
    "pro": Plan(
        key="pro",
        name="Pro",
        price_eur=99,
        page_quota=2500,
        features=[
            "2,500 pages / month",
            "Custom extraction schemas",
            "REST API access",
            "Batch upload",
            "Priority support",
        ],
        api_access=True,
        custom_schemas=True,
        export_watermark=False,
        overage_per_page_eur=0.05,
    ),
    "business": Plan(
        key="business",
        name="Business",
        price_eur=299,
        page_quota=10000,
        features=[
            "10,000 pages / month",
            "Everything in Pro",
            "Up to 10 team seats",
            "Webhooks & integrations",
            "Onboarding & SLA",
        ],
        api_access=True,
        custom_schemas=True,
        team_seats=10,
        webhooks=True,
        export_watermark=False,
        overage_per_page_eur=0.05,
    ),
}

PLAN_ORDER = ["free", "starter", "pro", "business"]


def get_plan(key: str) -> Plan:
    return PLANS.get(key, PLANS["free"])


def plan_for_stripe_price(price_id: str) -> str:
    """Reverse-map a Stripe price id to a plan key. Returns 'free' if unknown."""
    for key in ("starter", "pro", "business"):
        if price_id and PLANS[key].stripe_price_id() == price_id:
            return key
    return "free"
