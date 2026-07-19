"""Stripe billing: checkout, customer portal, webhooks, metered overage.

The app runs fine with billing DISABLED (no Stripe keys): every user stays on
the Free plan and upgrade buttons return a clear message. Set STRIPE_SECRET_KEY
+ the price IDs in .env to enable real subscriptions.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from .config import settings
from .db import User
from .plans import PLANS, get_plan, plan_for_stripe_price

try:
    import stripe  # type: ignore
except Exception:  # pragma: no cover
    stripe = None


def _client():
    if not settings.billing_enabled or stripe is None:
        return None
    stripe.api_key = settings.stripe_secret_key
    return stripe


def ensure_customer(db: Session, user: User) -> Optional[str]:
    s = _client()
    if s is None:
        return None
    if user.stripe_customer_id:
        return user.stripe_customer_id
    customer = s.Customer.create(email=user.email, name=user.full_name or None, metadata={"user_id": str(user.id)})
    user.stripe_customer_id = customer["id"]
    db.add(user)
    db.commit()
    return customer["id"]


def create_checkout_session(db: Session, user: User, plan_key: str) -> dict:
    plan = get_plan(plan_key)
    if plan.key == "free":
        return {"error": "Free plan needs no checkout."}

    s = _client()
    if s is None:
        return {"error": "Billing is not configured on this server. Set STRIPE_SECRET_KEY to enable upgrades."}

    price_id = plan.stripe_price_id()
    if not price_id:
        return {"error": f"No Stripe price configured for the {plan.name} plan (set STRIPE_PRICE_{plan.key.upper()})."}

    customer_id = ensure_customer(db, user)
    line_items = [{"price": price_id, "quantity": 1}]
    # Attach the metered overage price if configured, so overage bills automatically.
    if settings.stripe_price_overage_metered and plan.overage_per_page_eur > 0:
        line_items.append({"price": settings.stripe_price_overage_metered})

    session = s.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=line_items,
        success_url=f"{settings.public_base_url}/app.html?checkout=success",
        cancel_url=f"{settings.public_base_url}/pricing.html?checkout=cancelled",
        client_reference_id=str(user.id),
        metadata={"user_id": str(user.id), "plan": plan.key},
        allow_promotion_codes=True,
    )
    return {"url": session["url"]}


def create_portal_session(db: Session, user: User) -> dict:
    s = _client()
    if s is None:
        return {"error": "Billing is not configured on this server."}
    customer_id = ensure_customer(db, user)
    if not customer_id:
        return {"error": "No billing account found."}
    session = s.billing_portal.Session.create(
        customer=customer_id,
        return_url=f"{settings.public_base_url}/app.html",
    )
    return {"url": session["url"]}


def report_overage(user: User, pages: int) -> None:
    """Report metered usage (overage pages) to Stripe for the user's subscription."""
    s = _client()
    if s is None or not settings.stripe_price_overage_metered or not user.stripe_subscription_id:
        return
    try:
        sub = s.Subscription.retrieve(user.stripe_subscription_id)
        item_id = None
        for item in sub["items"]["data"]:
            if item["price"]["id"] == settings.stripe_price_overage_metered:
                item_id = item["id"]
                break
        if item_id:
            s.SubscriptionItem.create_usage_record(item_id, quantity=pages, action="increment")
    except Exception:
        # Metering must never break the extraction request.
        pass


def _apply_subscription(db: Session, customer_id: str, subscription: dict) -> None:
    user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
    if user is None:
        return
    status = subscription.get("status", "active")
    user.subscription_status = status
    user.stripe_subscription_id = subscription.get("id")

    # Determine plan from the first recurring (non-metered) price.
    plan_key = "free"
    for item in subscription.get("items", {}).get("data", []):
        price = item.get("price", {})
        if price.get("recurring", {}).get("usage_type") == "metered":
            continue
        plan_key = plan_for_stripe_price(price.get("id", ""))
        break

    previous_plan = user.plan
    if status in ("active", "trialing"):
        user.plan = plan_key
    elif status in ("canceled", "unpaid", "incomplete_expired"):
        user.plan = "free"
    db.add(user)
    db.commit()

    if previous_plan == "free" and user.plan != "free":
        from . import analytics
        analytics.log(db, "upgrade", user_id=user.id, plan=user.plan)


def handle_webhook(db: Session, payload: bytes, sig_header: str) -> dict:
    s = _client()
    if s is None:
        return {"error": "billing disabled"}

    if settings.stripe_webhook_secret:
        try:
            event = s.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)
        except Exception as exc:
            return {"error": f"invalid signature: {exc}"}
    else:
        import json
        event = json.loads(payload)

    etype = event["type"]
    obj = event["data"]["object"]

    if etype == "checkout.session.completed":
        customer_id = obj.get("customer")
        sub_id = obj.get("subscription")
        if customer_id and sub_id:
            sub = s.Subscription.retrieve(sub_id)
            _apply_subscription(db, customer_id, sub)

    elif etype in ("customer.subscription.updated", "customer.subscription.created", "customer.subscription.deleted"):
        _apply_subscription(db, obj.get("customer"), obj)

    return {"received": True, "type": etype}
