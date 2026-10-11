# Aspira TAT System v2

**Production-grade Turnaround Time (TAT) engine for Aspira Diagnostics.**

Event-driven webhook ingestion → PostgreSQL batch scheduling → Redis real-time cache → Celery async processing → Next.js 15 dashboard.

---

## Stack

| Layer | Technology |
|---|---|
| API server | FastAPI + Uvicorn/Gunicorn |
| Frontend | Next.js 15 (React 18, TypeScript, Tailwind CSS v4) |
| Database | PostgreSQL on Neon (asyncpg + psycopg2) |
| Cache & broker | Redis (hot cache + Celery broker) |
| Task processing | Celery + Celery Beat |
| Data validation | Pydantic v2 |
| Auth | Cookie-based session (verified against `tat_user` table) |
| Config | python-dotenv + `config/settings.py` |

---

## Quick Start (Manual)

```powershell
# 1. Create and activate Python virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Install frontend dependencies
npm install

# 4. Configure environment
copy .env.neon-template .env
# Edit .env — set DATABASE_URL to your Neon connection string

# 5. Apply database schema (first time only — run from project root)
python database/migrate.py

# 6. Start all services in separate terminals
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
celery -A app.workers.celery_app worker --loglevel=info -P solo --queues=queue:webhook-processing,projection
celery -A app.workers.celery_app beat --loglevel=info
npm run dev
```

| Service | URL |
|---|---|
| Frontend Dashboard | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| Health Check | http://localhost:8000/health |

---

## Quick Start (Docker)

```powershell
# Start everything (Redis + backend + worker + beat + frontend)
docker compose up --build

# Detached mode
docker compose up --build -d

# Tail logs
docker compose logs -f backend

# Stop and remove volumes
docker compose down -v
```

> PostgreSQL runs on Neon (cloud). No local PostgreSQL container is needed.

---

## Webhook Events

The system processes 9 event types via `POST /api/webhook`:

| Event | Trigger | Key Action |
|---|---|---|
| `BILL_GENERATE` | New bill created | Creates bill → sample → test instances (draft) |
| `BILL_UPDATE` | Bill activated | Activates records to `pending` |
| `SAMPLE_COLLECTED` | Sample drawn | Records `collected_at` |
| `SAMPLE_RECEIVED` | **Sample arrives at lab** | **Scheduling trigger** — routing + batch + ETA |
| `SAMPLE_REJECTED` | Sample quality rejected | Cancels sample + all tests |
| `REPORT_SUBMIT` | Result entered | Marks test completed, checks sample completion |
| `REPORT_SIGNED` | Doctor approves | Marks signed, checks sample completion |
| `REPORT_PDF` | PDF generated | Stores PDF artifact only |
| `SAMPLE_SENT_TO_EXTERNAL` | Sample routed to external lab | Marks sample in transit for outsourcing |
| `TEST_DISMISSED` | Test cancelled | Cancels individual test |

All events return **HTTP 202** in under 5 ms. Processing is fully asynchronous via Celery.

---

## Key Features

### Batch-Based Scheduling
Samples are assigned to **pre-defined batch time slots** per lab (e.g., 08:00, 14:00, 20:00). Scheduling triggers on `SAMPLE_RECEIVED`. Batch slots are configured in `tat_lab_batch_schedule`.

### Per-Test Lab Routing
Each test on a sample gets its own `processing_lab_id`, resolved by:
1. Lab capability match (`tat_lab_capability`)
2. Admin override (`tat_test_routing` table — test-code or department-level)
3. Fallback to the designated MAIN/fallback lab (fires a routing alert)

### ETA Versioning
`tat_eta` holds the current ETA. Every recalculation snapshots the previous ETA to `tat_eta_history` with a reason and version number — full immutable audit trail.

### Redis Hot Cache
After every key event, the sample record is pushed to a Redis sorted-set (`hot:pipeline`). The Operations Dashboard reads from this at sub-millisecond speed via `GET /api/pipeline/hot`.

### Missed Batch Detection
Celery Beat runs `do_sweep_delayed()` every 5 minutes. If a batch time has passed without the sample being processed, it is reassigned to the next available slot, the ETA is recalculated, and an alert is fired.

### Role-Based Access Control (RBAC)
Routes are protected via cookie-based session auth (`app/core/auth.py`). Roles: `admin`, `lab`, `doctor`, `logistics`. Role and `lab_id` are read from the `tat_user` database table — never trusted from the client.

---

## Project Structure

```
new test/
├── app/                           Python backend (FastAPI)
│   ├── main.py                    FastAPI app + lifespan (DB pool, EDOS, Redis)
│   ├── models.py                  Pydantic v2 models + WebhookType enum
│   ├── pg_database.py             Async DB layer (asyncpg pool + all queries)
│   ├── edos_loader.py             EDOS CSV catalog (in-memory at startup)
│   ├── schedule_parser.py         Schedule parsing utilities
│   ├── tat_parser.py              TAT calculation utilities
│   ├── routers/
│   │   ├── webhook.py             POST /api/webhook — ingest + idempotency
│   │   ├── api.py                 Core read API (samples, bills, labs, stats)
│   │   ├── actions.py             Role-specific actions (logistics, lab, admin)
│   │   ├── dashboard.py           Dashboard, KPI, and timeline endpoints
│   │   ├── admin.py               Admin management endpoints
│   │   ├── logistics.py           Logistics-specific endpoints
│   │   └── sample_create.py       Direct sample creation endpoint
│   ├── workers/
│   │   ├── celery_app.py          Celery config + task registration + Beat schedule
│   │   └── webhook_processor.py   9 event handlers + sweep task
│   ├── services/
│   │   ├── scheduler.py           Batch slot + routing + TAT logic
│   │   ├── alert_service.py       Email + webhook alert dispatch
│   │   ├── queue_service.py       Redis priority queue push/pop
│   │   ├── kpi_service.py         KPI calculation and metrics
│   │   ├── queue_prioritizer.py   Queue prioritization logic
│   │   ├── reconciliation.py      Data reconciliation utilities
│   │   └── state_machine.py       Sample state machine management
│   ├── core/
│   │   ├── engine.py              Cache push helper + manual accession
│   │   ├── hot_cache.py           Redis sorted-set pipeline cache
│   │   ├── idempotency.py         Redis TTL deduplication guard
│   │   ├── auth.py                Cookie-based RBAC session auth
│   │   ├── circuit_breaker.py     Circuit breaker for external calls
│   │   └── pg_pool.py             PostgreSQL connection pool management
│   ├── dashboard/                 Dashboard pages and components
│   ├── login/                     Login/authentication pages
│   ├── lib/                       Frontend utility libraries
│   ├── data/                      Static data files
│   ├── utils/                     Utility functions
│   └── tests/                     Backend tests
├── components/                    Next.js React components
│   ├── dashboard/                 Dashboard-specific components
│   ├── figma/                     Figma-related components
│   └── ui/                        UI component library (shadcn/ui)
├── config/
│   ├── settings.py                All environment-overridable config (cfg object)
│   └── constants.py               Named constants (TAT defaults, pool sizes)
├── database/
│   ├── schema.sql                 Full PostgreSQL schema + seed data
│   ├── migrate.py                 Schema migration runner (Neon + local PG)
│   └── init_demo.py               Demo data initialization
├── deploy/
│   ├── Dockerfile.backend         Python 3.11-slim image (FastAPI + Celery)
│   └── Dockerfile.frontend        Node 20-alpine multi-stage Next.js image
├── tests/                        Test directory
├── scratch/                       Scratch/working directory
├── docker-compose.yml             Full stack: backend + worker + beat + frontend
├── .env                           Local environment (gitignored)
├── .env.neon-template             .env template to copy
├── edos.csv                       EDOS test catalog (loaded at startup)
├── requirements.txt               Python dependencies
├── package.json                   Node.js dependencies (Next.js 15)
├── next.config.js                 Next.js configuration
├── tailwind.config.js             Tailwind CSS configuration
├── tsconfig.json                  TypeScript configuration
└── middleware.ts                  Next.js middleware
```

---

## Environment Variables

Copy `.env.neon-template` to `.env` and configure:

```env
# Required — Neon PostgreSQL connection string
DATABASE_URL=postgresql://<user>:<password>@<neon-host>/<db>?sslmode=require&channel_binding=require

# Auto-derived from DATABASE_URL — leave empty
PG_DSN=

# Connection pool sizes
PG_POOL_MIN=20
PG_POOL_MAX=100

# Redis (localhost for manual; overridden to redis://redis:6379/0 in Docker)
REDIS_URL=redis://localhost:6379/0
REDIS_TTL=172800
CELERY_CONCURRENCY=8

# Timezone for IST alert formatting
TZ=Asia/Kolkata

# SMTP (optional — for email alerts)
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASS=
ALERT_EMAIL_FROM=
ALERT_EMAIL_TO=

# Outbound webhook (optional — notifies LIS on sample completion)
WEBHOOK_RESULTS_URL=
```

---

## API Reference (Summary)

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/webhook` | None | Ingest LIS webhook event |
| `GET` | `/api/samples` | Required | List samples (filter by status) |
| `GET` | `/api/samples/{id}` | Required | Sample detail + tests + ETA + logs |
| `GET` | `/api/bills/{id}` | Required | Bill by internal ID |
| `GET` | `/api/bills/external/{id}` | Required | Bill by LIS bill ID |
| `GET` | `/api/labs` | Required | All active labs |
| `GET` | `/api/labs/{id}/queue` | Required | Lab work queue |
| `GET` | `/api/labs/{id}/batches` | Required | Batch schedule + assignments |
| `GET` | `/api/labs/{id}/kpi` | admin/lab | Per-lab KPI metrics |
| `GET` | `/api/stats` | Required | System-wide dashboard counts |
| `GET` | `/api/stats/labs` | Required | Per-lab queue + batch stats |
| `GET` | `/api/stats/sla` | Required | SLA breach rate by client type |
| `GET` | `/api/pipeline/hot` | Required | Redis hot cache (sub-ms) |
| `GET` | `/api/notifications` | Required | Alert events from audit log |
| `GET` | `/api/dashboard/admin` | admin | Full admin dashboard |
| `GET` | `/api/dashboard/lab` | lab | Lab-scoped dashboard |
| `GET` | `/api/dashboard/admin/lab-metrics` | admin | Lab management KPIs |
| `GET` | `/api/dashboard/admin/labs` | admin | Labs with performance metrics |
| `GET` | `/api/samples/{id}/timeline` | Required | Chronological event timeline |
| `GET` | `/api/samples/{id}/eta-history` | admin/doctor | ETA version audit trail |
| `GET` | `/api/analytics/tests` | admin/lab | Per-test-type SLA analytics |
| `POST` | `/api/logistics/confirm-pickup` | logistics/admin | Mark sample picked up |
| `POST` | `/api/logistics/confirm-delivery` | logistics/admin | Confirm lab delivery |
| `POST` | `/api/lab/confirm-receipt` | lab/admin | Lab confirms sample receipt |
| `POST` | `/api/lab/submit-result` | lab/admin | Submit test result |
| `POST` | `/api/override/priority` | admin | Change sample priority |
| `POST` | `/api/override/routing` | admin | Re-route sample to different lab |
| `POST` | `/api/override/retry` | admin | Re-queue failed sample |
| `GET` | `/health` | None | Health check |
| `GET` | `/docs` | None | Swagger UI |

Full interactive documentation: **http://localhost:8000/docs**
