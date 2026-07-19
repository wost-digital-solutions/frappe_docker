"""Usage metering & quota enforcement."""
from __future__ import annotations

import datetime as dt
import math

from sqlalchemy.orm import Session

from .db import UsageRecord, User
from .plans import CHARS_PER_PAGE, get_plan


def current_period() -> str:
    now = dt.datetime.now(dt.timezone.utc)
    return f"{now.year:04d}-{now.month:02d}"


def pages_for(char_count: int, pdf_pages: int = 0) -> int:
    """A billing 'page' = max(real PDF pages, ceil(chars / 3000)), min 1."""
    by_chars = math.ceil(char_count / CHARS_PER_PAGE) if char_count else 0
    return max(1, pdf_pages, by_chars)


def get_usage(db: Session, user: User) -> UsageRecord:
    period = current_period()
    rec = (
        db.query(UsageRecord)
        .filter(UsageRecord.user_id == user.id, UsageRecord.period == period)
        .first()
    )
    if rec is None:
        rec = UsageRecord(user_id=user.id, period=period, pages_used=0)
        db.add(rec)
        db.commit()
        db.refresh(rec)
    return rec


def usage_summary(db: Session, user: User) -> dict:
    plan = get_plan(user.plan)
    rec = get_usage(db, user)
    remaining = max(0, plan.page_quota - rec.pages_used)
    return {
        "period": rec.period,
        "plan": plan.key,
        "plan_name": plan.name,
        "quota": plan.page_quota,
        "used": rec.pages_used,
        "remaining": remaining,
        "percent_used": round(100 * rec.pages_used / plan.page_quota, 1) if plan.page_quota else 0,
        "overage_allowed": plan.overage_per_page_eur > 0,
        "overage_per_page_eur": plan.overage_per_page_eur,
    }


class QuotaExceeded(Exception):
    def __init__(self, summary: dict):
        self.summary = summary
        super().__init__("Monthly page quota exceeded")


def check_and_reserve(db: Session, user: User, pages: int) -> dict:
    """Ensure the user can run a job of `pages`. Raises QuotaExceeded on hard cap."""
    plan = get_plan(user.plan)
    rec = get_usage(db, user)
    projected = rec.pages_used + pages
    if projected > plan.page_quota and plan.overage_per_page_eur <= 0:
        raise QuotaExceeded(usage_summary(db, user))
    return {"projected": projected, "quota": plan.page_quota}


def commit_usage(db: Session, user: User, pages: int) -> dict:
    """Record `pages` of usage and report any billable overage."""
    from . import billing  # local import to avoid cycle

    plan = get_plan(user.plan)
    rec = get_usage(db, user)
    before = rec.pages_used
    rec.pages_used = before + pages
    db.add(rec)
    db.commit()
    db.refresh(rec)

    overage = max(0, rec.pages_used - plan.page_quota)
    prev_overage = max(0, before - plan.page_quota)
    new_overage = overage - prev_overage
    if new_overage > 0 and plan.overage_per_page_eur > 0:
        billing.report_overage(user, new_overage)

    return usage_summary(db, user)
