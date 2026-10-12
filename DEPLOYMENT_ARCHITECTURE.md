# 🏗️ Deployment Architecture

## **Complete System Architecture**

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         END USERS / BROWSERS                             │
└────────────────┬────────────────────────────────────────────────────────┘
                 │
                 │ HTTPS
                 ↓
    ┌────────────────────────────────┐
    │  VERCEL (Frontend)             │
    │  ├─ Next.js 15 Server          │
    │  ├─ React Components           │
    │  └─ TypeScript + Tailwind      │
    │                                 │
    │  URL:                           │
    │  https://aspira.vercel.app     │
    └────────────┬────────────────────┘
                 │
                 │ HTTP/HTTPS
                 │ NEXT_PUBLIC_BACKEND_URL
                 ↓
    ┌──────────────────────────────────────────────────────────────────┐
    │  RAILWAY (Backend Infrastructure)                               │
    │  ├─────────────────────────────────────────────────────────────┤
    │  │  FastAPI Web Server (Port 8000)                             │
    │  │  ├─ FastAPI app (Python)                                   │
    │  │  ├─ Gunicorn + Uvicorn workers (4)                         │
    │  │  ├─ Health check endpoint                                   │
    │  │  └─ All API routes                                          │
    │  │                                                              │
    │  │  URL: https://backend-prod-xxx.railway.app                 │
    │  │─────────────────────────────────────────────────────────────│
    │  │  Celery Worker (Background Tasks)                          │
    │  │  ├─ Processes webhook events                                │
    │  │  ├─ Handles sample/result processing                       │
    │  │  ├─ Manages queue: webhook-processing                      │
    │  │  ├─ Manages queue: sample-processing                       │
    │  │  ├─ Manages queue: result-processing                       │
    │  │  ├─ Manages queue: alert-processing                        │
    │  │  ├─ Manages queue: projection                              │
    │  │  └─ Concurrency: 4-8 workers                               │
    │  │─────────────────────────────────────────────────────────────│
    │  │  Celery Beat (Scheduled Tasks)                             │
    │  │  ├─ Sweep delayed queue (every 5 min)                      │
    │  │  ├─ Refresh projections (every 10 min)                     │
    │  │  ├─ Reconciliation sweep (every 1 min)                     │
    │  │  ├─ SLA at-risk checks (every 5 min)                       │
    │  │  ├─ Redraw overdue checks (every 30 min)                   │
    │  │  └─ Lab downtime sync (every 1 hour)                       │
    │  └─────────────────────────────────────────────────────────────┘
    │         ↓                ↓                    ↓
    │    HTTP/S(async)   HTTP/S(async)         HTTP/S
    └──────────┼──────────────┼────────────────────┼────────────┘
               │              │                    │
               ↓              ↓                    ↓
    ┌──────────────────┐ ┌──────────────┐  ┌─────────────────┐
    │ PostgreSQL       │ │ Redis        │  │ External APIs   │
    │ (Database)       │ │ (Broker +    │  │ (Webhooks,      │
    │                  │ │  Cache)      │  │  Notifications) │
    │ Tables:          │ │              │  │                 │
    │ ├─ samples       │ │ Channels:    │  │ ├─ Email SMTP   │
    │ ├─ results       │ │ ├─ queue:... │  │ └─ External     │
    │ ├─ queue         │ │ └─ hot:...   │  │    Systems      │
    │ ├─ alerts        │ │              │  └─────────────────┘
    │ ├─ sla_eta       │ │ Connection:  │
    │ └─ ...           │ │ rediss://... │
    │                  │ │ or redis://  │
    │ Connection:      │ │ Upstash or   │
    │ postgresql://    │ │ Railway      │
    │ Neon or Railway  │ └──────────────┘
    │ Max connections: │
    │ 20-50            │
    └──────────────────┘
```

---

## **Data Flow**

### 1. **User interacts with Frontend (Vercel)**
```
Browser → Vercel (Next.js) → render UI
```

### 2. **Frontend calls Backend API**
```
Browser → Vercel Frontend
         → rewrites /api/* to NEXT_PUBLIC_BACKEND_URL
         → Railway Backend (FastAPI)
         → Response back to browser
```

### 3. **Backend processes request**
```
FastAPI receives request
├─ Query PostgreSQL
├─ Update cache in Redis
├─ Return response
└─ Optionally queue Celery task
```

### 4. **Background Tasks (Celery)**
```
FastAPI queues task to Redis
         ↓
Celery Worker picks up from queue
         ↓
Celery Worker processes (connects to PostgreSQL, calls APIs)
         ↓
Result stored in Redis
         ↓
Frontend polls or receives webhook for completion
```

### 5. **Scheduled Tasks (Celery Beat)**
```
Every N minutes:
├─ Sweep delayed queue
├─ Refresh projections
├─ Check SLA at-risk
├─ Reconciliation
└─ Lab downtime sync
```

---

## **Environment Variables Flow**

```
┌─ Vercel Environment ─────────────────────────┐
│                                              │
│  NEXT_PUBLIC_BACKEND_URL                    │
│  = "https://backend-prod-xxx.railway.app"   │
│                                              │
│  Used in:                                    │
│  ├─ next.config.js rewrites                 │
│  ├─ app/lib/api.ts BASE_URL                 │
│  └─ All fetch() calls from components       │
└──────────────────────────────────────────────┘

┌─ Railway Environment ────────────────────────────────────────┐
│                                                              │
│  DATABASE_URL = "postgresql://user:pass@host/db"            │
│                Used by: FastAPI, Celery Worker             │
│                                                              │
│  REDIS_URL = "rediss://default:pass@host:port"             │
│                Used by: Celery (broker), FastAPI (cache)   │
│                                                              │
│  SECRET_KEY, WEBHOOK_SHARED_SECRET, SMTP_* ...             │
│                Used by: All backend processes               │
│                                                              │
│  Shared by: Backend, Celery Worker, Celery Beat            │
└──────────────────────────────────────────────────────────────┘
```

---

## **Request Lifecycle Example**

### Scenario: User views Dashboard

```
1. USER CLICKS DASHBOARD
   │
   ├─ Browser requests: https://aspira.vercel.app/dashboard
   │
   ├─ Vercel (Next.js) renders page
   │
   └─ Next.js client component runs:
      fetch(NEXT_PUBLIC_BACKEND_URL + '/api/stats')
                          ↓
   
2. API REQUEST TO BACKEND
   │
   ├─ Fetch goes to: https://backend-prod-xxx.railway.app/api/stats
   │
   ├─ Railway FastAPI receives request
   │
   └─ FastAPI executes:
      ├─ Connect to PostgreSQL
      ├─ Query tables (samples, results, sla_eta)
      ├─ Calculate stats
      ├─ Cache result in Redis (1 hour TTL)
      └─ Return JSON response
                        ↓
   
3. RESPONSE BACK TO FRONTEND
   │
   ├─ Browser receives: {"samples": 1200, "avg_tat": 4.5, ...}
   │
   └─ React component updates UI
```

---

## **Background Task Example**

### Scenario: Webhook received from lab system

```
1. WEBHOOK RECEIVED
   │
   ├─ Lab system POSTs to: https://backend-prod-xxx.railway.app/webhook/result
   │
   ├─ FastAPI validates signature using WEBHOOK_SHARED_SECRET
   │
   └─ FastAPI queues Celery task:
      celery_app.send_task('webhook.process', args=[event_id])
                        ↓
   
2. TASK QUEUED IN REDIS
   │
   ├─ Message goes to: redis://broker/queue:webhook-processing
   │
   └─ Celery Worker continuously polls this queue
                        ↓
   
3. CELERY WORKER PICKS UP TASK
   │
   ├─ Worker reads task from Redis queue
   │
   ├─ Worker executes: webhook_processor.handle_webhook(event_id)
   │
   ├─ During execution:
   │  ├─ Connect to PostgreSQL
   │  ├─ Parse lab result data
   │  ├─ Update sample status
   │  ├─ Calculate TAT
   │  ├─ Update caches
   │  └─ May trigger more tasks
   │
   └─ Result stored in Redis (TTL: 48 hours)
                        ↓
   
4. FRONT-END NOTIFIED (polling or websocket)
   │
   ├─ Frontend receives task completion
   │
   └─ UI updates with new data
```

---

## **Scaling Layers**

```
┌─────────────────────────────────────────────────────┐
│ Layer 1: Frontend (Vercel)                          │
│ - Auto-scaled globally (CDN edge nodes)             │
│ - Automatic failover & redundancy                   │
│ - Cache static assets worldwide                     │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ Layer 2: FastAPI Backend (Railway)                  │
│ - Multiple Gunicorn workers (4 default, scale up)   │
│ - Connection pooling to PostgreSQL (20-50)          │
│ - Redis hot cache (prevents DB query spike)         │
│ - Auto-scaling: Enable in Railway Settings         │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ Layer 3: Celery Workers (Railway)                   │
│ - Can add multiple worker replicas                  │
│ - Each runs in separate container                   │
│ - Tasks distributed across workers                  │
│ - Concurrency per worker: 4-8                       │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ Layer 4: Database (PostgreSQL / Neon)               │
│ - Managed service (auto-backups, replicas)          │
│ - Connection pooling (PgBouncer recommended)        │
│ - Read replicas for analytics (optional)            │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ Layer 5: Cache & Broker (Redis / Upstash)          │
│ - Managed Redis with automatic failover             │
│ - Cluster support for high throughput               │
│ - Connection limit awareness (Railway: pool_limit)  │
└─────────────────────────────────────────────────────┘
```

---

## **Deployment Summary**

| Component | Platform | Scaling | Monitoring |
|-----------|----------|---------|-----------|
| Frontend | Vercel | Auto (edge CDN) | Vercel Dashboard |
| Backend API | Railway | Manual replicas | Railway Logs |
| Celery Worker | Railway | Manual replicas | Railway Logs |
| Celery Beat | Railway | Single instance | Railway Logs |
| PostgreSQL | Neon/Railway | Managed | Native tools |
| Redis | Upstash/Railway | Managed | Native tools |

---

## **Production Readiness Checklist**

```
Deployment:
✓ Procfile configured
✓ Requirements.txt pinned to versions
✓ Environment variables secure
✓ Secrets in Railway (not in git)

Database:
□ Connection pooling enabled
□ Read replicas (optional)
□ Automated backups verified
□ Point-in-time recovery available

Monitoring:
□ Error tracking (Sentry/DataDog)
□ Performance monitoring
□ Uptime/health checks
□ Log aggregation

Performance:
□ Database indexes optimized
□ Redis cache strategy verified
□ CDN cache headers set
□ Celery concurrency tuned

Security:
□ HTTPS everywhere
□ CORS properly configured
□ API authentication working
□ Secrets not in logs
```

---

## **Questions?**

Refer back to:
- `DEPLOYMENT_GUIDE.md` - Full detailed steps
- `DEPLOYMENT_QUICK_START.md` - Quick checklist
- This file - Architecture & data flow

🚀 Ready to deploy!
