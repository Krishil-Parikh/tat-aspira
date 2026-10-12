# 🔧 Deployment Troubleshooting Guide

All deployment issues organized by component. Check the relevant section based on where you're seeing problems.

---

## **FRONTEND (VERCEL) ISSUES**

### ❌ "Build failed"

**Symptoms:**
- Vercel shows "Build failed" in dashboard
- Site doesn't deploy

**Solutions:**
1. **Check build logs**:
   - Vercel → Deployments → Click failed deployment → Logs
   - Look for TypeScript or syntax errors

2. **Verify Node version**:
   - Go to Settings → Node.js Version
   - Make sure it's 18+ (your package.json uses Next.js 15)

3. **Check dependencies**:
   - Make sure `package.json` has all required packages
   - Try locally: `npm install && npm run build`

4. **Environment variables**:
   - Vercel → Settings → Environment Variables
   - Make sure `NEXT_PUBLIC_BACKEND_URL` is set

---

### ❌ "Cannot reach backend" / API 404 errors

**Symptoms:**
- Frontend loads but API calls fail
- Browser console shows CORS errors
- Fetch returns 404 from backend URL

**Solutions:**
1. **Verify backend URL**:
   ```javascript
   console.log(process.env.NEXT_PUBLIC_BACKEND_URL)
   // Should print: https://backend-prod-xxx.railway.app
   ```

2. **Test backend directly**:
   ```bash
   curl https://YOUR-BACKEND.railway.app/health
   # Should return: {"status": "ok"}
   ```

3. **Check Vercel env var**:
   - Go to Settings → Environment Variables
   - Find `NEXT_PUBLIC_BACKEND_URL`
   - Make sure it's set for Production
   - Verify it doesn't have trailing slash

4. **Redeploy after env var change**:
   - Click "Redeploy" button in Vercel
   - (Simply setting env var doesn't redeploy automatically)

5. **Check CORS in backend**:
   - Update `app/main.py` CORS middleware:
   ```python
   app.add_middleware(
       CORSMiddleware,
       allow_origins=[
           "https://YOUR-VERCEL-URL.vercel.app",
           "http://localhost:3000",
       ],
       allow_credentials=True,
       allow_methods=["*"],
       allow_headers=["*"],
   )
   ```
   - Push to GitHub and redeploy backend

---

### ❌ "Blank page" / "White screen"

**Symptoms:**
- Site loads but shows nothing
- No errors in console

**Solutions:**
1. **Check browser console** (F12 → Console tab):
   - Look for any error messages
   - Look for 404s or network errors

2. **Verify environment**:
   - Make sure env vars are set before build
   - If you added env vars, click "Redeploy"

3. **Check Next.js version**:
   - Your package.json has `next@15`
   - Make sure Vercel isn't forcing an older version

---

## **BACKEND (RAILWAY) ISSUES**

### ❌ "502 Bad Gateway"

**Symptoms:**
- Backend URL returns 502 error
- Deployment shows successful but won't respond

**Solutions:**
1. **Check deployment logs**:
   - Railway → backend service → Deployments → View Logs
   - Look for Python import errors or syntax errors

2. **Verify Procfile**:
   - Make sure `Procfile` exists in project root
   - Check `web` process command is correct:
   ```
   web: gunicorn app.main:app -k uvicorn.workers.UvicornWorker ...
   ```

3. **Check environment variables**:
   - Go to backend service → Variables
   - Make sure `DATABASE_URL` is set
   - Make sure `REDIS_URL` is set
   - If you added/changed vars, redeploy

4. **Test locally**:
   ```bash
   # Make sure it runs locally first
   python -m pip install -r requirements.txt
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

5. **Check Python version**:
   - Railway should auto-detect Python 3.10+
   - If not, add `runtime.txt`:
   ```
   python-3.11.5
   ```
   - Push and redeploy

6. **Check health endpoint**:
   ```bash
   curl https://YOUR-BACKEND.railway.app/health
   # If 502, backend isn't running
   ```

---

### ❌ "502" with deployment successful but won't start

**Symptoms:**
- Procfile exists
- Env vars are set
- Still getting 502

**Solutions:**
1. **Memory/resource issues**:
   - Check Railway dashboard for resource usage
   - Try increasing memory allocation (Settings → Resource)

2. **Gunicorn workers**:
   - Reduce workers in Procfile if memory is low:
   ```
   web: gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w 2 ...
   ```

3. **Port binding**:
   - Make sure `$PORT` is used correctly:
   ```
   web: gunicorn app.main:app ... --bind 0.0.0.0:$PORT ...
   ```

4. **Timeout issue**:
   - If app takes long to start, increase timeout:
   ```
   web: gunicorn app.main:app ... --timeout 120 ...
   ```

---

### ❌ "Cannot connect to database"

**Symptoms:**
- Backend logs show "unable to connect to PostgreSQL"
- Queries timeout
- "too many connections" errors

**Solutions:**
1. **Verify DATABASE_URL**:
   ```bash
   # Check it's set in Railway
   # Go to backend service → Variables
   # DATABASE_URL should be: postgresql://user:pass@host/db
   ```

2. **Check database is running**:
   - If using Railway PostgreSQL:
     - Go to PostgreSQL service
     - Should show "running" status
   - If using Neon.tech:
     - Log in to Neon console
     - Check project status

3. **Test connection locally**:
   ```bash
   # Install psycopg2 locally
   pip install psycopg2-binary
   
   # Test connection
   python -c "
   import asyncpg
   import asyncio
   async def test():
       conn = await asyncpg.connect('YOUR-DATABASE-URL')
       print('Connected!')
   asyncio.run(test())
   "
   ```

4. **Connection pool exhaustion**:
   - Check if `PG_POOL_MAX` is too low
   - Increase it in Railway Variables:
   ```
   PG_POOL_MIN=5
   PG_POOL_MAX=30  # Increase this
   ```

5. **Check firewall/IP whitelist**:
   - Neon.tech: Check Connection Pooler settings
   - Railway: Should auto-allow internally

---

### ❌ "redis.exceptions.ConnectionError"

**Symptoms:**
- Celery worker won't start
- Backend logs show "ConnectionError" for Redis
- "Cannot connect to Redis" errors

**Solutions:**
1. **Verify REDIS_URL**:
   - Go to Railway backend service → Variables
   - Check `REDIS_URL` is set
   - Format should be: `redis://...` or `rediss://...`

2. **Check Redis is running**:
   - If using Railway Redis:
     - Go to Redis service → Should show "running"
   - If using Upstash:
     - Log in to Upstash console
     - Check database status

3. **Test Redis connection**:
   ```bash
   # Install redis locally
   pip install redis
   
   # Test connection
   python -c "
   import redis
   r = redis.from_url('YOUR-REDIS-URL')
   print(r.ping())  # Should print: True
   "
   ```

4. **Upstash-specific issues**:
   - Make sure using "CLI Connection URL" not "REST API URL"
   - Verify it starts with `rediss://` (note: double 's')
   - Check Upstash connection limit (typically 30)

5. **SSL issues**:
   - If URL is `rediss://` (double s), it needs SSL
   - Your `celery_app.py` already handles this, but verify:
   ```python
   broker_use_ssl={"ssl_cert_reqs": "none"} if cfg.REDIS_URL.startswith("rediss://") else False
   ```

---

## **CELERY WORKER ISSUES**

### ❌ "Worker won't start / tasks not processing"

**Symptoms:**
- Celery worker deployment shows successful
- But logs show no "ready to accept tasks"
- Tasks queue up but don't execute

**Solutions:**
1. **Check Celery logs**:
   - Railway → celery-worker service → Deployments → View Logs
   - Look for connection errors or startup failures

2. **Verify environment variables**:
   - Make sure all vars copied from backend
   - Especially `REDIS_URL` and `DATABASE_URL`
   - Click "Redeploy" after adding vars

3. **Check Procfile worker command**:
   ```
   worker: celery -A app.workers.celery_app worker -Q queue:webhook-processing,... -c 4 ...
   ```

4. **Memory issues**:
   - Celery worker is memory-intensive
   - Check Railway resource allocation
   - Reduce concurrency if needed:
   ```
   worker: celery -A app.workers.celery_app worker ... -c 2 ...
   ```

5. **Redis broker issue**:
   - Same as backend Redis issues above
   - Make sure `REDIS_URL` is correct

---

### ❌ "Tasks stuck in queue"

**Symptoms:**
- Tasks appear in queue but never complete
- Logs show "task started" but no result

**Solutions:**
1. **Check worker is running**:
   - Go to celery-worker service → Logs
   - Should see periodic: `celery worker ready to accept tasks`

2. **Verify Redis**:
   - Connect to Redis and check queue:
   ```bash
   redis-cli -u YOUR-REDIS-URL
   > KEYS queue:*
   > LLEN queue:webhook-processing  # Should show queue length
   ```

3. **Check task code**:
   - Look in `app/workers/webhook_processor.py`
   - Make sure task logic doesn't crash
   - Add logging to see where it's stuck

4. **Increase worker concurrency**:
   - Change in Procfile or Railway Variables:
   ```
   CELERY_CONCURRENCY=8
   ```
   - Then redeploy worker

---

## **CELERY BEAT (SCHEDULER) ISSUES**

### ❌ "Scheduled tasks not running"

**Symptoms:**
- Celery beat deployment shows running
- But scheduled tasks (sweep, reconciliation, etc.) don't execute

**Solutions:**
1. **Check beat logs**:
   - Railway → celery-beat service → Logs
   - Should show periodic schedule messages

2. **Verify schedule**:
   - Check `app/workers/celery_app.py`:
   ```python
   celery_app.conf.beat_schedule = {
       "sweep-delayed": {"task": "sweep.delayed", "schedule": 300.0},
       ...
   }
   ```

3. **Clock skew**:
   - If beat can't connect to Redis, it can't schedule
   - Make sure `REDIS_URL` is correct

4. **Redis blocking**:
   - Check Redis isn't full or slow
   - Run in Railway shell: `redis-cli -u YOUR-REDIS-URL`

---

## **DATABASE ISSUES**

### ❌ "Migrations haven't run"

**Symptoms:**
- Backend starts but queries fail with "table doesn't exist"
- 500 errors on API calls

**Solutions:**
1. **Check if database is initialized**:
   - Look at `database/schema.sql`
   - Has it been run?

2. **Run migrations**:
   - Connect to database and run schema:
   ```bash
   # Using psql
   psql "YOUR-DATABASE-URL" < database/schema.sql
   ```

3. **Or use Railway shell**:
   - Railway → PostgreSQL service → Shell
   - Paste schema.sql commands

4. **Verify tables exist**:
   ```sql
   SELECT table_name FROM information_schema.tables 
   WHERE table_schema = 'public';
   ```

---

### ❌ "Database connection timeout on large queries"

**Symptoms:**
- API works for small queries
- Large queries timeout (>30 sec)
- 504 Timeout errors

**Solutions:**
1. **Increase timeout**:
   ```
   web: gunicorn app.main:app ... --timeout 120 ...
   ```

2. **Add indexes**:
   - Check `database/schema.sql` for missing indexes
   - Add indexes for frequently queried columns

3. **Optimize queries**:
   - Check `app/routers/` for N+1 queries
   - Use connection pooling efficiently

4. **Increase pool size**:
   ```
   PG_POOL_MAX=50
   ```

---

## **MONITORING & DEBUGGING**

### How to Check Logs

**Vercel:**
```
Dashboard → Deployments → Click deployment → Function Logs
```

**Railway:**
```
Project → Service → Deployments → View Logs
```

### Real-time Log Viewing

**Railway CLI** (if installed):
```bash
railway logs
# or specific service:
railway logs -s backend
```

### Common Log Patterns

| Pattern | Meaning | Action |
|---------|---------|--------|
| `Uvicorn running on` | Backend started ✓ | App is running |
| `ready to accept tasks` | Celery worker running ✓ | Worker is active |
| `ConnectionError` | DB/Redis unreachable | Check URLs |
| `ImportError` | Missing Python package | Check requirements.txt |
| `SyntaxError` | Bad Python code | Check git diff |

---

## **TESTING CHECKLIST**

After deployment, test these:

```bash
# 1. Backend health
curl https://YOUR-BACKEND/health

# 2. Database connection
curl https://YOUR-BACKEND/api/stats

# 3. Celery worker
curl -X POST https://YOUR-BACKEND/api/webhook/process \
  -H "Content-Type: application/json" \
  -d '{"event_id": 1}'

# 4. Frontend loads
open https://YOUR-FRONTEND.vercel.app

# 5. Frontend → Backend
# In browser console:
fetch(process.env.NEXT_PUBLIC_BACKEND_URL + '/health').then(r => r.json()).then(console.log)
```

---

## **QUICK REFERENCE**

### Most Common Issues

1. **502 Bad Gateway** → Check backend logs, Procfile, env vars
2. **Cannot reach backend** → Check NEXT_PUBLIC_BACKEND_URL, CORS
3. **Database connection fail** → Check DATABASE_URL, database is running
4. **Celery won't start** → Check REDIS_URL, env vars copied
5. **Tasks not executing** → Check worker is running, Redis accessible

### Fastest Solutions

| Issue | Fix |
|-------|-----|
| 502 on backend | `railway redeploy` (in backend service) |
| Can't reach backend from frontend | Check and `redeploy` Vercel after setting env var |
| Celery stuck | Check Redis with `redis-cli` |
| DB timeout | Increase `--timeout` in Procfile |

---

## **Need More Help?**

1. Check full guides:
   - `DEPLOYMENT_GUIDE.md`
   - `DEPLOYMENT_ARCHITECTURE.md`

2. Check logs:
   - Railway Deployments tab
   - Vercel Function Logs

3. External resources:
   - Railway docs: https://docs.railway.app
   - FastAPI: https://fastapi.tiangolo.com/deployment/
   - Celery: https://docs.celeryproject.io/

---

🚀 Most issues are resolved by checking logs and environment variables!
