# Groundtruth

**Turn any document into trustworthy structured data — with every field traced back to its source.**

Groundtruth is a no-code web app that extracts structured data (JSON / CSV / table) from PDFs and text. Its differentiator is **source grounding**: every extracted field is highlighted at its exact location in the original document, so results are verifiable and auditable — not a black box. It's built on top of Google's open-source [LangExtract](https://github.com/google/langextract) library.

This repository contains the **complete, runnable product**: FastAPI backend, static frontend (landing, pricing, app), authentication, usage metering, Stripe billing, a REST API, and a zero-config demo mode.

---

## Why this is a business

The LangExtract library is free but requires Python, API keys, and hand-written few-shot examples. The people who need document extraction most — paralegals, accountants, claims processors, analysts, researchers — don't write code. Groundtruth sells the "upstairs": a hosted, no-code, verifiable extraction product with subscription + metered billing.

- **Free** — 25 pages/mo (watermarked exports)
- **Starter €29/mo** — 500 pages
- **Pro €99/mo** — 2,500 pages + custom schemas + API
- **Business €299/mo** — 10,000 pages + team + webhooks
- Overage: €0.05/page

---

## Run it in 60 seconds (demo mode, no keys)

The app runs **fully functional out of the box** with no API keys and no payment processor. In demo mode a built-in heuristic engine performs the extraction and still grounds every field to the source.

```bash
cd groundtruth/backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                    # optional; defaults are fine
uvicorn app.main:app --reload --port 8000
```

Open **http://localhost:8000** → sign up → paste an invoice (see `sample_docs/invoice-sample.txt`) → watch every field highlight its source.

### Or with Docker

```bash
cd groundtruth
docker compose up --build
# -> http://localhost:8000
```

---

## Enable real AI extraction (production)

Demo mode is great for trying the product; for production accuracy, switch on LangExtract:

```bash
pip install -r requirements-llm.txt          # installs langextract
```

Then set **one** key in `.env`:

```
GEMINI_API_KEY=your_google_ai_studio_key     # get one at https://aistudio.google.com/apikey
# or
OPENAI_API_KEY=your_openai_key
DEFAULT_MODEL_ID=gemini-3.5-flash            # or gpt-4o-mini, etc.
```

Restart. Extractions now run through the real LLM with schema-constrained, grounded output. If the LLM call ever fails, the app automatically falls back to demo mode so a request never errors out.

> In the Docker image, uncomment the two `requirements-llm.txt` lines in the `Dockerfile` and pass the key via `docker compose` env / `.env`.

---

## Enable billing (Stripe)

Billing is optional. Without Stripe keys, everyone stays on Free and upgrade buttons explain that billing isn't configured.

1. Create a [Stripe](https://dashboard.stripe.com) account.
2. Create three recurring **Products/Prices** (Starter €29, Pro €99, Business €299). Optionally create a **metered** price for €0.05/page overage.
3. Put the keys and price IDs in `.env`:

   ```
   STRIPE_SECRET_KEY=sk_live_...            # or sk_test_...
   STRIPE_PUBLISHABLE_KEY=pk_live_...
   STRIPE_PRICE_STARTER=price_...
   STRIPE_PRICE_PRO=price_...
   STRIPE_PRICE_BUSINESS=price_...
   STRIPE_PRICE_OVERAGE_METERED=price_...   # optional
   ```

4. Add a webhook endpoint in Stripe pointing to `https://YOUR_DOMAIN/api/billing/webhook`, subscribe to `checkout.session.completed` and `customer.subscription.*`, and paste the signing secret:

   ```
   STRIPE_WEBHOOK_SECRET=whsec_...
   ```

Test locally with the Stripe CLI:

```bash
stripe listen --forward-to localhost:8000/api/billing/webhook
```

The full checkout → webhook → plan-upgrade → metered-overage loop is implemented in `backend/app/billing.py`.

---

## Project structure

```
groundtruth/
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI app: API routes + serves the frontend
│   │   ├── config.py         # env-driven settings
│   │   ├── db.py             # SQLAlchemy models (User, Job, UsageRecord)
│   │   ├── security.py       # password hashing, JWT, API-key auth
│   │   ├── plans.py          # pricing plans = source of truth for quotas
│   │   ├── templates_lib.py  # extraction templates (prompt + examples + demo patterns)
│   │   ├── extraction.py     # LangExtract wrapper + grounded demo engine
│   │   ├── usage.py          # quota enforcement + metering
│   │   ├── billing.py        # Stripe checkout / portal / webhook / overage
│   │   ├── exports.py        # JSON / CSV / table serialization
│   │   └── schemas.py        # Pydantic request/response models
│   ├── requirements.txt      # light core deps (always)
│   ├── requirements-llm.txt  # optional: langextract
│   └── .env.example
├── frontend/
│   ├── index.html            # landing page
│   ├── pricing.html          # pricing + checkout
│   ├── login.html            # signup / login
│   ├── app.html              # the product (upload, extract, grounded viewer)
│   ├── css/styles.css
│   └── js/{api,landing,auth,app}.js
├── marketing/
│   ├── marketing-copy.md     # final landing/pricing/email/social copy
│   └── growth-plan.md        # 30-day acquisition plan + ready-to-post assets
├── sample_docs/
├── Dockerfile
└── docker-compose.yml
```

## REST API

Included on Pro/Business. Authenticate with the `X-API-Key` header (find your key in the app under **API & keys**).

```bash
curl -X POST http://localhost:8000/api/extract \
  -H "X-API-Key: gt_xxx" \
  -H "Content-Type: application/json" \
  -d '{"template":"invoice","text":"Invoice #INV-2045 ... Total Due: $1,815.00"}'
```

Returns grounded extractions with character offsets (`source_span`) for every field. Endpoints: `POST /api/extract`, `POST /api/extract/file`, `GET /api/jobs`, `GET /api/jobs/{id}`, `GET /api/jobs/{id}/export.{json|csv}`, `GET /api/usage`. Interactive docs at `/docs`.

## Deploy

Any container host works (Render, Fly.io, Railway, a VPS). Ship the `Dockerfile`, set env vars, point a domain at it, and add the Stripe webhook. Use a Postgres `DATABASE_URL` and a persistent volume for production.

## License / attribution

Groundtruth is a product built **on top of** the open-source LangExtract library (Apache-2.0, © Google). Groundtruth is an independent product and is **not affiliated with or endorsed by Google**.
