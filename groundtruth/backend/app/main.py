"""Groundtruth API — FastAPI application.

Serves the JSON API under /api/* and the static frontend (landing, pricing, app)
from the sibling `frontend/` directory.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from . import analytics, billing, exports
from .config import settings
from .db import Job, Lead, User, get_db, init_db
from .extraction import extract_text_from_pdf, run_extraction
from .plans import PLANS, PLAN_ORDER, get_plan
from .schemas import (
    CheckoutRequest,
    ExtractRequest,
    LoginRequest,
    SignupRequest,
    TokenResponse,
    TrackRequest,
    UserResponse,
    WaitlistRequest,
)
from .security import create_access_token, get_current_user, hash_password, verify_password
from .templates_lib import public_catalog
from .usage import QuotaExceeded, check_and_reserve, commit_usage, pages_for, usage_summary

app = FastAPI(title="Groundtruth API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


@app.on_event("startup")
def _startup() -> None:
    init_db()


# --------------------------------------------------------------------------- #
# Meta / config
# --------------------------------------------------------------------------- #
@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "llm_enabled": settings.llm_enabled, "billing_enabled": settings.billing_enabled}


@app.get("/api/config")
def public_config() -> dict:
    return {
        "app_name": settings.app_name,
        "llm_enabled": settings.llm_enabled,
        "billing_enabled": settings.billing_enabled,
        "stripe_publishable_key": settings.stripe_publishable_key,
        "templates": public_catalog(),
        "plans": [
            {
                "key": PLANS[k].key,
                "name": PLANS[k].name,
                "price_eur": PLANS[k].price_eur,
                "page_quota": PLANS[k].page_quota,
                "features": PLANS[k].features,
                "api_access": PLANS[k].api_access,
                "custom_schemas": PLANS[k].custom_schemas,
                "overage_per_page_eur": PLANS[k].overage_per_page_eur,
            }
            for k in PLAN_ORDER
        ],
    }


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
@app.post("/api/auth/signup", response_model=TokenResponse)
def signup(body: SignupRequest, db: Session = Depends(get_db)) -> TokenResponse:
    existing = db.query(User).filter(User.email == body.email.lower()).first()
    if existing:
        raise HTTPException(status_code=400, detail="An account with this email already exists.")
    user = User(
        email=body.email.lower(),
        hashed_password=hash_password(body.password),
        full_name=body.full_name or "",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    analytics.log(db, "signup", user_id=user.id, anon_id=body.anon_id or None)
    return TokenResponse(access_token=create_access_token(str(user.id)))


@app.post("/api/auth/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.query(User).filter(User.email == body.email.lower()).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    return TokenResponse(access_token=create_access_token(str(user.id)))


@app.get("/api/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        plan=user.plan,
        api_key=user.api_key,
        subscription_status=user.subscription_status,
    )


@app.get("/api/usage")
def get_my_usage(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return usage_summary(db, user)


@app.post("/api/api-key/rotate")
def rotate_api_key(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    import secrets

    user.api_key = "gt_" + secrets.token_urlsafe(32)
    db.add(user)
    db.commit()
    return {"api_key": user.api_key}


# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #
def _do_extract(
    db: Session,
    user: User,
    text: str,
    template: str,
    custom_fields,
    model_id,
    source_name: str,
    pdf_pages: int = 0,
) -> dict:
    text = (text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="No text found to extract from.")
    if len(text) > 600_000:
        raise HTTPException(status_code=413, detail="Document too large (600k character limit per job).")

    pages = pages_for(len(text), pdf_pages)
    try:
        check_and_reserve(db, user, pages)
    except QuotaExceeded as exc:
        raise HTTPException(status_code=402, detail={"message": "Monthly page quota exceeded.", "usage": exc.summary})

    result = run_extraction(text, template, custom_fields, model_id)

    job = Job(
        user_id=user.id,
        template=template,
        source_name=source_name,
        char_count=len(text),
        pages_charged=pages,
        mode=result["mode"],
        status="done",
        source_text=text,
        result_json=result,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    usage = commit_usage(db, user, pages)

    analytics.log_first(db, "first_extraction", user_id=user.id, template=template)
    analytics.log(db, "extraction", user_id=user.id, template=template, mode=result["mode"], pages=pages)

    return {
        "job_id": job.id,
        "template": template,
        "source_name": source_name,
        "mode": result["mode"],
        "model": result.get("model"),
        "warning": result.get("warning"),
        "pages_charged": pages,
        "text": text,
        "extractions": result["extractions"],
        "table": exports.to_table(result["extractions"]),
        "usage": usage,
    }


@app.post("/api/extract")
def extract_text(
    body: ExtractRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return _do_extract(
        db, user, body.text, body.template, body.custom_fields, body.model_id, source_name="pasted text"
    )


@app.post("/api/extract/file")
async def extract_file(
    file: UploadFile = File(...),
    template: str = Form("custom"),
    custom_fields: str = Form(""),
    model_id: str = Form(""),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    data = await file.read()
    filename = file.filename or "upload"
    pdf_pages = 0
    if filename.lower().endswith(".pdf") or (data[:5] == b"%PDF-"):
        text, pdf_pages = extract_text_from_pdf(data)
    else:
        text = data.decode("utf-8", errors="ignore")

    fields = [f.strip() for f in custom_fields.split(",") if f.strip()] or None
    return _do_extract(
        db, user, text, template, fields, model_id or None, source_name=filename, pdf_pages=pdf_pages
    )


@app.get("/api/jobs")
def list_jobs(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    jobs = db.query(Job).filter(Job.user_id == user.id).order_by(Job.id.desc()).limit(50).all()
    return {
        "jobs": [
            {
                "id": j.id,
                "template": j.template,
                "source_name": j.source_name,
                "created_at": j.created_at.isoformat() if j.created_at else None,
                "pages_charged": j.pages_charged,
                "mode": j.mode,
                "count": len(j.result_json.get("extractions", [])) if j.result_json else 0,
            }
            for j in jobs
        ]
    }


@app.get("/api/jobs/{job_id}")
def get_job(job_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    job = db.query(Job).filter(Job.id == job_id, Job.user_id == user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    result = job.result_json or {}
    return {
        "job_id": job.id,
        "template": job.template,
        "source_name": job.source_name,
        "mode": job.mode,
        "text": job.source_text,
        "extractions": result.get("extractions", []),
        "table": exports.to_table(result.get("extractions", [])),
    }


@app.get("/api/jobs/{job_id}/export.{fmt}")
def export_job(fmt: str, job_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id, Job.user_id == user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    plan = get_plan(user.plan)
    payload = {
        "source_name": job.source_name,
        "template": job.template,
        "mode": job.mode,
        "extractions": (job.result_json or {}).get("extractions", []),
    }
    if fmt == "json":
        content = exports.to_json(payload, watermark=plan.export_watermark)
        media = "application/json"
    elif fmt == "csv":
        content = exports.to_csv(payload, watermark=plan.export_watermark)
        media = "text/csv"
    else:
        raise HTTPException(status_code=400, detail="Unsupported format. Use json or csv.")
    analytics.log(db, "export", user_id=user.id, fmt=fmt)
    return Response(
        content=content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="groundtruth-{job.id}.{fmt}"'},
    )


# --------------------------------------------------------------------------- #
# Billing
# --------------------------------------------------------------------------- #
@app.post("/api/billing/checkout")
def checkout(
    body: CheckoutRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    result = billing.create_checkout_session(db, user, body.plan)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/api/billing/portal")
def portal(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    result = billing.create_portal_session(db, user)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/api/billing/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    result = billing.handle_webhook(db, payload, sig)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# --------------------------------------------------------------------------- #
# Growth: waitlist capture + funnel analytics
# --------------------------------------------------------------------------- #
@app.post("/api/waitlist")
def join_waitlist(body: WaitlistRequest, db: Session = Depends(get_db)) -> dict:
    email = body.email.lower()
    exists = db.query(Lead).filter(Lead.email == email).first()
    if not exists:
        db.add(Lead(email=email, source=body.source or "landing", note=body.note or ""))
        db.commit()
        analytics.log(db, "waitlist", email=email, source=body.source)
    return {"ok": True, "message": "You're on the list — we'll be in touch."}


@app.post("/api/track")
def track_event(body: TrackRequest, db: Session = Depends(get_db)) -> dict:
    # Public, best-effort pageview/visit tracking from the frontend.
    allowed = {"visit", "view_pricing", "start_signup", "cta_click", "lead_magnet_delivered"}
    if body.name in allowed:
        analytics.log(db, body.name, anon_id=body.anon_id or None, **(body.meta or {}))
    return {"ok": True}


def _require_admin(x_admin_token: str = Header(default="")) -> None:
    if not x_admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(status_code=403, detail="Admin token required.")


@app.get("/api/admin/funnel")
def admin_funnel(days: int = 30, _: None = Depends(_require_admin), db: Session = Depends(get_db)) -> dict:
    return analytics.funnel(db, days=days)


@app.get("/api/admin/leads")
def admin_leads(_: None = Depends(_require_admin), db: Session = Depends(get_db)) -> dict:
    return {"leads": analytics.recent_leads(db)}


# --------------------------------------------------------------------------- #
# Frontend (static) — mounted last so /api/* wins.
# --------------------------------------------------------------------------- #
@app.get("/")
def root() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
