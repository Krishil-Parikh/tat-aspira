# 🚀 QUICK DEPLOYMENT CHECKLIST

Complete these steps in order. Estimated time: **30-45 minutes**

---

## **PHASE 1: SETUP EXTERNAL SERVICES (10 min)**

### Step 1: Generate Security Keys
```bash
python -c "import secrets; print('SECRET_KEY:', secrets.token_urlsafe(32)); print('WEBHOOK_SECRET:', secrets.token_urlsafe(32))"
```
👉 **Save these** - you'll paste them into Railway

### Step 2: PostgreSQL Database
Choose **one**:

- **Neon.tech** (easier):
  1. Go to https://neon.tech → Sign up
  2. Create project → Get `DATABASE_URL`
  3. Copy full connection string (starts with `postgresql://`)

- **Railway** (Part 2.1):
  1. Create project → Add PostgreSQL service
  2. Copy `DATABASE_URL` from Variables tab

👉 **Save** `DATABASE_URL`

### Step 3: Redis
Choose **one**:

- **Upstash** (easier):
  1. Go to https://upstash.com → Sign up
  2. Create Redis → Get "CLI Connection URL"
  3. Copy the URL (starts with `rediss://` or `redis://`)

- **Railway** (Part 2.2):
  1. Same project → Add Redis service
  2. Copy `REDIS_URL` from Variables tab

👉 **Save** `REDIS_URL`

---

## **PHASE 2: DEPLOY BACKEND ON RAILWAY (15 min)**

### Step 4: Create Railway Project
1. Go to https://railway.app → New Project
2. Click "+ Add" → "GitHub Repo" → Select your repo
3. Name it: **`backend`**

### Step 5: Add Environment Variables to Backend
Go to **backend service** → **Variables** tab → Add these:

```
DATABASE_URL=<paste from Step 2>
REDIS_URL=<paste from Step 3>
APP_ENV=production
ENVIRONMENT=production
NODE_ENV=production
SECRET_KEY=<paste from Step 1>
WEBHOOK_SHARED_SECRET=<paste from Step 1>
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASS=your-app-password
ALERT_EMAIL_FROM=your-email@gmail.com
ALERT_EMAIL_TO=alerts@yourdomain.com
PG_POOL_MIN=5
PG_POOL_MAX=20
CELERY_CONCURRENCY=4
TZ=Asia/Kolkata
MIGRATION_RECONCILIATION_ENABLED=false
MIGRATION_RECONCILIATION_SWEEP_ENABLED=false
```

### Step 6: Deploy Backend Service
1. Make sure `Procfile` exists in your repo root (we created it)
2. Go to **Settings** → Scroll to "Deploy"
3. **Deployment command**: `web`
4. Click **Deploy**
5. ⏳ Wait for "Deployment Successful" message
6. ✅ Check logs: Go to **Deployments** → Click latest → **View Logs**
7. Should see: `Uvicorn running on 0.0.0.0:...`

### Step 7: Get Backend URL
- Click **backend service** → **Settings** → **Public URL**
- It looks like: `https://backend-prod-xxx.railway.app`
- 👉 **Copy this** (you'll need it for Vercel)

### Step 8: Test Backend Health
```bash
# Open in browser or terminal
curl https://YOUR-BACKEND-URL/health
# Should return: {"status": "ok"}
```

### Step 9: Add Celery Worker Service
1. In Railway, click "+ Add" → "GitHub Repo" (same repo)
2. Name it: **`celery-worker`**
3. Go to **backend service** → **Variables** → Select all → Copy
4. Go to **celery-worker service** → **Variables** → Paste
5. Go to **Settings** → Deployment command: `worker`
6. Click **Deploy**
7. ⏳ Wait for success
8. ✅ Check logs for: `celery ... ready to accept tasks`

### Step 10: Add Celery Beat (Optional but Recommended)
1. Click "+ Add" → "GitHub Repo"
2. Name it: **`celery-beat`**
3. Copy variables from backend
4. Deployment command: `beat`
5. Deploy

---

## **PHASE 3: DEPLOY FRONTEND ON VERCEL (10 min)**

### Step 11: Create Vercel Project
1. Go to https://vercel.com → New Project
2. **Import from Git** → Select your repo
3. Vercel auto-detects Next.js
4. Click **Deploy**

### Step 12: Add Environment Variable to Vercel
While deploying OR in **Settings** → **Environment Variables**:

Add variable:
```
Name: NEXT_PUBLIC_BACKEND_URL
Value: https://YOUR-BACKEND-URL (from Step 7)
Scope: Production, Preview, Development
```

Example:
```
NEXT_PUBLIC_BACKEND_URL=https://backend-prod-xxx.railway.app
```

### Step 13: Deploy Frontend
1. Click **Deploy** (if not already deployed)
2. ⏳ Wait for build to complete
3. ✅ Get your Vercel URL: `https://YOUR-FRONTEND.vercel.app`

---

## **PHASE 4: FINAL INTEGRATION (5 min)**

### Step 14: Update Railway Webhook URL
1. Go back to **Railway** → **backend service** → **Variables**
2. Find `WEBHOOK_RESULTS_URL`
3. Update to: `https://YOUR-FRONTEND.vercel.app/api/webhooks/results`
4. Example: `https://aspira-prod.vercel.app/api/webhooks/results`
5. **Redeploy backend**: Click Redeploy button

### Step 15: Test Everything Works
```bash
# In your browser console:
fetch(process.env.NEXT_PUBLIC_BACKEND_URL + '/health')
  .then(r => r.json())
  .then(d => console.log('✓ Backend connected:', d))
  .catch(e => console.error('✗ Backend error:', e))
```

Should see: `✓ Backend connected: {status: "ok"}`

---

## **VERIFICATION CHECKLIST**

- [ ] Backend responds to `/health` endpoint
- [ ] Celery worker logs show "ready to accept tasks"
- [ ] Frontend deploys on Vercel without build errors
- [ ] Frontend loads and can fetch from backend
- [ ] Test a sample API call (e.g., GET /api/stats)
- [ ] Check Railway logs for any errors
- [ ] Verify database is being queried (check PostgreSQL connection count)

---

## **📊 FINAL URLs**

Save these:
- **Frontend**: `https://YOUR-FRONTEND.vercel.app`
- **Backend API**: `https://YOUR-BACKEND.railway.app`
- **Database**: (PostgreSQL connection string - keep private)
- **Redis**: (Redis URL - keep private)

---

## **❌ COMMON ISSUES**

| Problem | Solution |
|---------|----------|
| Backend won't deploy | Check logs; verify Python 3.10+ |
| 502 Bad Gateway | Backend crashed—check Procfile & import errors |
| Celery tasks failing | Verify REDIS_URL is correct & accessible |
| Frontend 404 errors | Verify `NEXT_PUBLIC_BACKEND_URL` is set in Vercel |
| Database connection timeout | Increase `PG_POOL_MAX` to 30 |
| CORS errors on frontend | Update CORS in `app/main.py` with Vercel domain |

---

## **NEXT STEPS**

After deployment:
1. ✅ Test all features end-to-end
2. ✅ Monitor Railway & Vercel logs for errors
3. ✅ Set up email notifications (configure SMTP)
4. ✅ Enable auto-scaling on Railway (Settings → Scaling)
5. ✅ Create staging environment for testing
6. ✅ Set up GitHub branch protection rules

---

## **HELP**

- 📖 Full guide: See `DEPLOYMENT_GUIDE.md`
- 🚀 Railway docs: https://docs.railway.app
- 🎨 Vercel docs: https://vercel.com/docs
- 🔧 FastAPI deployment: https://fastapi.tiangolo.com/deployment/
