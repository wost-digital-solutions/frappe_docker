"""Funnel analytics — a dependency-free event log + metrics aggregation.

Tracks the funnel the growth plan says to watch:
    visit -> signup -> first_extraction -> export -> upgrade

Events are logged server-side where possible (the reliable path); the frontend
only needs to fire `visit` pageview events with an anonymous id.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from .db import Event, Lead, User

FUNNEL_STEPS = ["visit", "signup", "first_extraction", "export", "upgrade"]


def log(db: Session, name: str, user_id: Optional[int] = None, anon_id: Optional[str] = None, **meta) -> None:
    """Record a funnel event. Never raises — analytics must not break requests."""
    try:
        db.add(Event(name=name, user_id=user_id, anon_id=anon_id, meta=meta or {}))
        db.commit()
    except Exception:
        db.rollback()


def log_first(db: Session, name: str, user_id: int, **meta) -> None:
    """Log an event only the first time it happens for a user (e.g. first_extraction)."""
    try:
        exists = (
            db.query(Event.id)
            .filter(Event.name == name, Event.user_id == user_id)
            .first()
        )
        if not exists:
            log(db, name, user_id=user_id, **meta)
    except Exception:
        db.rollback()


def funnel(db: Session, days: int = 30) -> dict:
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)

    def count(name: str, distinct_by=None) -> int:
        q = db.query(func.count(func.distinct(distinct_by))) if distinct_by is not None else db.query(func.count(Event.id))
        q = q.filter(Event.name == name, Event.created_at >= since)
        return q.scalar() or 0

    visits = count("visit", Event.anon_id)
    signups = count("signup", Event.user_id)
    activated = count("first_extraction", Event.user_id)
    exports = count("export", Event.user_id)
    upgrades = count("upgrade", Event.user_id)

    total_users = db.query(func.count(User.id)).scalar() or 0
    paying = db.query(func.count(User.id)).filter(User.plan != "free").scalar() or 0
    leads = db.query(func.count(Lead.id)).scalar() or 0

    def pct(n, d):
        return round(100 * n / d, 1) if d else 0.0

    return {
        "window_days": days,
        "funnel": {
            "visit": visits,
            "signup": signups,
            "first_extraction": activated,
            "export": exports,
            "upgrade": upgrades,
        },
        "conversion": {
            "visit_to_signup": pct(signups, visits),
            "signup_to_activated": pct(activated, signups),
            "activated_to_export": pct(exports, activated),
            "signup_to_paid": pct(upgrades, signups),
            "visit_to_paid": pct(upgrades, visits),
        },
        "totals": {
            "users": total_users,
            "paying_users": paying,
            "waitlist_leads": leads,
        },
        "north_star_metrics": [
            "activation rate (signup -> first_extraction)",
            "free -> paid conversion",
            "weekly active extractors",
        ],
    }


def recent_leads(db: Session, limit: int = 100) -> list:
    rows = db.query(Lead).order_by(Lead.id.desc()).limit(limit).all()
    return [
        {"email": r.email, "source": r.source, "note": r.note, "created_at": r.created_at.isoformat() if r.created_at else None}
        for r in rows
    ]
