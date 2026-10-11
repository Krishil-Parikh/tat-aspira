# Deployment Guide: Railway (Backend + Celery) & Vercel (Frontend)

This guide walks you through deploying your Aspira TAT System:
- **Backend + Celery Workers → Railway**
- **Frontend (Next.js) → Vercel**

---

## **PART 1: PRE-DEPLOYMENT SETUP**

### Step 1.1: Create Accounts
- [ ] Create [Railway.app](https://railway.app) account
- [ ] Create [Vercel](https://vercel.com) account
- [ ] Ensure your GitHub repo is connected to both

### Step 1.2: Generate Secrets
Run this in your project root to generate secure keys:
```bash
# Generate SECRET_KEY and WEBHOOK_SHARED_SECRET
python -c "import secrets; print('SECRET_KEY:', secrets.token_urlsafe(32)); print('WEBHOOK_SHARED_SECRET:', secrets.token_urlsafe(32))"
```
Save these values—you'll need them in Railway's environment variables.

### Step 1.3: External Services Required
You'll need to set up these **before** deploying:

#### A. PostgreSQL Database
Choose **one**:
- **Neon.tech** (recommended): https://neon.tech
  - Signup → Create project → Get `DATABASE_URL` (format: `postgresql://user:pass@host/db`)
  - Copy the full connection string
  
- **Railway** (setup in Railway later—see Part 2.1)

#### B. Redis (for Celery broker & cache)
Choose **one**:
- **Upstash** (recommended): https://upstash.com
  - Signup → Create Redis database → Get `REDIS_URL` (format: `rediss://default:password@host:port`)
  - Use the "CLI Connection URL"
  
- **Railway** (setup in Railway later—see Part 2.2)

---

## **PART 2: RAILWAY DEPLOYMENT (Backend + Celery)**

### Step 2.1: Create Railway Project & Database

1. **Go to Railway.app → New Project**
2. **Add PostgreSQL Service**:
   - Click "+ Add" → Select "PostgreSQL"
   - Railway creates it automatically
   - Go to the PostgreSQL service → Variables tab
   - Copy `DATABASE_URL` (you'll need this)

3. **Add Redis Service** (for Celery):
   - Click "+ Add" → Select "Redis"
   - Go to Redis service → Variables tab
   - Copy `REDIS_URL` (starts with `redis://` or `rediss://`)

> **Note**: If you already have Neon/Upstash accounts with credentials, you can skip the Railway-hosted versions and use those external URLs instead.

### Step 2.2: Add Backend Service (FastAPI)

1. **Click "+ Add" → "GitHub Repo"**
   - Select your GitHub repository
   - Railway auto-detects the Python backend

2. **Configure Service Name**:
   - Name it: `backend`

3. **Set Environment Variables**:
   - Go to the backend service → **Variables** tab
   - Add all these variables:

```env
# Database
DATABASE_URL=<paste from PostgreSQL or Neon>

# Redis / Celery
REDIS_URL=<paste from Redis or Upstash>

# App Config
APP_ENV=production
ENVIRONMENT=production
NODE_ENV=production

# Authentication & Security
SECRET_KEY=<from Step 1.2>
WEBHOOK_SHARED_SECRET=<from Step 1.2>

# SMTP (email notifications) - configure if you have email setup
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASS=your-app-password
ALERT_EMAIL_FROM=your-email@gmail.com
ALERT_EMAIL_TO=alerts@yourdomain.com

# Webhook (for result callbacks - update FRONTEND_URL later)
WEBHOOK_RESULTS_URL=https://your-frontend.vercel.app/api/webhooks/results

# Database Pool Sizing
PG_POOL_MIN=5
PG_POOL_MAX=20

# Celery Concurrency
CELERY_CONCURRENCY=4
TZ=Asia/Kolkata

# Migration Flags (enable gradually)
MIGRATION_RECONCILIATION_ENABLED=false
MIGRATION_RECONCILIATION_SWEEP_ENABLED=false
```

**Important**: Save `BACKEND_URL` (Railway gives you something like `https://backend-prod-xxx.railway.app`) for the frontend deployment.

### Step 2.3: Create Procfile for Railway

In your project **root**, create `Procfile`:

```procfile
# Procfile
web: gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w 4 --bind 0.0.0.0:$PORT --timeout 120
worker: celery -A app.workers.celery_app worker -Q queue:webhook-processing,queue:sample-processing,queue:result-processing,queue:alert-processing,queue:projection -c 4 -n worker@%h --loglevel=info
beat: celery -A app.workers.celery_app beat --loglevel=info
```

**Push to GitHub**:
```bash
git add Procfile
git commit -m "Add Procfile for Railway deployment"
git push origin main
```

### Step 2.4: Deploy Backend on Railway

1. **In Railway**, go to your backend service
2. **Settings** tab → Scroll to "Deploy" section
3. **Choose the `web` process**:
   - Deployment command: `web`
   - This runs the FastAPI server

4. **Click Deploy**
   - Railway pulls from GitHub
   - Installs `requirements.txt`
   - Runs the Procfile `web` process
   - Wait for "Deployment Successful" ✓

5. **Check Logs**:
   - Go to **Deployments** → Click the latest → **View Logs**
   - Should see: `"Uvicorn running on 0.0.0.0:PORT"`

### Step 2.5: Add Celery Worker Service

1. **In Railway, click "+ Add"** in the same project
2. **Select "GitHub Repo"** (same repo)
3. **Name it**: `celery-worker`
4. **Copy all environment variables** from the backend service:
   - Go to backend → Variables → Select all → Copy
   - Go to celery-worker → Variables → Paste
5. **Deploy**:
   - Settings → Deployment command: `worker` (from Procfile)
   - Click Deploy

### Step 2.6: Add Celery Beat Service (Optional but Recommended)

1. **Click "+ Add"** → **"GitHub Repo"**
2. **Name it**: `celery-beat`
3. **Copy environment variables** from backend
4. **Deploy**:
   - Settings → Deployment command: `beat`
   - Click Deploy

This handles periodic tasks like:
- Sweep delayed queue (5 min)
- Refresh projections (10 min)
- Reconciliation sweep (1 min)
- SLA at-risk checks (5 min)

### Step 2.7: Test Backend

```bash
# Get your backend URL from Railway
# Click the backend service → go to "Connect" tab
# Copy the public URL (e.g., https://backend-prod-xxx.railway.app)

# Test health endpoint
curl https://YOUR-BACKEND-URL/health

# Should return: {"status": "ok"}
```

---

## **PART 3: VERCEL DEPLOYMENT (Frontend)**

### Step 3.1: Connect Frontend to Vercel

1. **Go to Vercel.com → New Project**
2. **Import from Git** → Select your GitHub repo
3. **Vercel auto-detects** Next.js setup

### Step 3.2: Set Environment Variables (Frontend)

In Vercel dashboard:
1. **Settings** → **Environment Variables**
2. **Add variable**: `NEXT_PUBLIC_BACKEND_URL`
   - Value: `https://YOUR-BACKEND-URL` (from Railway Step 2.7)
   - Scope: Production, Preview, Development
3. **Click Save**

Example:
```
NEXT_PUBLIC_BACKEND_URL=https://backend-prod-xxx.railway.app
```

> **Why `NEXT_PUBLIC_`?** This prefix makes it available in the browser. Update any API calls in your `lib/api.ts` to use this:
>
> ```typescript
> const API_BASE = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';
> ```

### Step 3.3: Deploy Frontend

1. **In Vercel**, click **Deploy**
2. Wait for build to complete
3. Get your **Vercel URL** (e.g., `https://aspira-prod.vercel.app`)
4. **Copy this URL**—you'll need it for Step 3.4

### Step 3.4: Update Railway Webhook URL

Back in Railway:
1. Go to **backend service** → **Variables**
2. Update `WEBHOOK_RESULTS_URL`:
   ```
   WEBHOOK_RESULTS_URL=https://YOUR-VERCEL-URL/api/webhooks/results
   ```
   Example: `WEBHOOK_RESULTS_URL=https://aspira-prod.vercel.app/api/webhooks/results`

3. **Redeploy backend** (click Redeploy button)

---

## **PART 4: INTEGRATION & TESTING**

### Step 4.1: Test API Connectivity

From your frontend app (browser console or via API test):

```javascript
// Test backend connectivity
fetch(process.env.NEXT_PUBLIC_BACKEND_URL + '/health')
  .then(r => r.json())
  .then(d => console.log('Backend status:', d));
```

### Step 4.2: Test Celery Queue

If you have a route that triggers a Celery task:
```bash
curl -X POST https://YOUR-BACKEND-URL/api/webhook/process \
  -H "Content-Type: application/json" \
  -d '{"event_id": 1}'
```

Check Celery logs in Railway (celery-worker service → Logs)

### Step 4.3: Check Database Connection

```bash
# SSH into Railway backend pod (if needed)
# Or check logs for PostgreSQL connection errors
```

---

## **PART 5: MONITORING & TROUBLESHOOTING**

### Monitor Backend Logs
- **Railway** → Backend service → **Deployments** → **View Logs**
- Look for errors or health check failures

### Monitor Celery Workers
- **Railway** → celery-worker service → **Logs**
- Should see task processing logs

### Monitor Database Connections
- **Neon or Railway PostgreSQL** → Check connection count
- If hitting max connections, increase `PG_POOL_MAX` in environment

### Common Issues

| Issue | Fix |
|-------|-----|
| 502 Bad Gateway | Backend crashed—check logs for import/syntax errors |
| Celery tasks not running | Check `REDIS_URL` is accessible; verify Redis service is running |
| Webhook delivery fails | Verify `WEBHOOK_RESULTS_URL` is correct; check frontend logs |
| Database connection timeout | Increase `PG_POOL_MAX`; verify `DATABASE_URL` is correct |
| CORS errors | Add frontend domain to FastAPI CORS middleware in `app/main.py` |

### Fix CORS (if needed)
In `app/main.py`, update the CORS middleware:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://YOUR-VERCEL-URL",
        "http://localhost:3000",  # local dev
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## **PART 6: SCALING & OPTIMIZATION**

### Auto-scaling on Railway
1. Go to **backend service** → **Settings**
2. **Scaling** tab → Enable auto-scaling
3. Set max replicas (e.g., 3)

### Increase Celery Concurrency
- Update `CELERY_CONCURRENCY` env var (e.g., 8 for high load)
- Redeploy worker service

### Database Connection Pooling
- Increase `PG_POOL_MAX` if you see "too many connections" errors
- Start with 20, increase to 50+ for production

### Cache Strategy
- Enable Redis caching for frequent queries
- Use Celery task result caching (configured in `celery_app.py`)

---

## **PART 7: CI/CD IMPROVEMENTS**

### Add Health Check to Railway
Your backend already has `/health` endpoint. Railway will auto-detect it.

### Auto-redeploy on Push
1. Both Railway and Vercel auto-redeploy on `git push`
2. Make sure `.env` is in `.gitignore` (secrets not in git)

### Staging Environment
1. Create `staging` branch
2. Set up Railway/Vercel to deploy from `staging` branch separately
3. Test before merging to `main` (production)

---

## **FINAL CHECKLIST**

- [ ] PostgreSQL database created (Neon or Railway)
- [ ] Redis instance created (Upstash or Railway)
- [ ] Procfile created and pushed to GitHub
- [ ] Backend deployed on Railway with all env vars
- [ ] Celery worker deployed on Railway
- [ ] Celery beat deployed on Railway
- [ ] Frontend deployed on Vercel
- [ ] `NEXT_PUBLIC_BACKEND_URL` set in Vercel
- [ ] `WEBHOOK_RESULTS_URL` updated in Railway
- [ ] Backend health check responds ✓
- [ ] Frontend loads and connects to backend ✓
- [ ] Test a sample API call from frontend ✓

---

## **Quick Reference: Important URLs**

```
Backend:  https://YOUR-BACKEND.railway.app
Frontend: https://YOUR-FRONTEND.vercel.app
Database: postgresql://neon-host/db-name
Redis:    rediss://default:pass@host:port
```

---

## **Need Help?**

- **Railway Docs**: https://docs.railway.app
- **Vercel Docs**: https://vercel.com/docs
- **FastAPI Deployment**: https://fastapi.tiangolo.com/deployment/
- **Celery on Production**: https://docs.celeryproject.io/en/stable/deployment/

Good luck! 🚀
