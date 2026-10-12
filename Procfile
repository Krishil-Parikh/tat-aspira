# Procfile - Railway deployment configuration
# Railway will use this to run different processes

# Web server (FastAPI with Uvicorn + Gunicorn)
web: gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w 4 --bind 0.0.0.0:$PORT --timeout 120

# Celery Worker (processes background tasks)
worker: celery -A app.workers.celery_app worker -Q queue:webhook-processing,queue:sample-processing,queue:result-processing,queue:alert-processing,queue:projection -c 4 -n worker@%h --loglevel=info

# Celery Beat (periodic/scheduled tasks)
beat: celery -A app.workers.celery_app beat --loglevel=info
