# Aspira TAT System v2 - Complete Setup Guide

This guide provides step-by-step instructions for setting up the Aspira TAT System from scratch on a fresh machine.

## Table of Contents

1. [System Requirements](#system-requirements)
2. [Prerequisites](#prerequisites)
3. [Project Overview](#project-overview)
4. [Installation Steps](#installation-steps)
5. [Environment Configuration](#environment-configuration)
6. [Database Setup](#database-setup)
7. [Running the Application](#running-the-application)
8. [Docker Setup (Alternative)](#docker-setup-alternative)
---

## System Requirements

### Minimum Requirements
- **Operating System**: Windows 10+, macOS 10.15+, or Linux (Ubuntu 20.04+ recommended)
- **RAM**: 8 GB minimum, 16 GB recommended
- **Disk Space**: 5 GB free space
- **Network**: Stable internet connection for external services

### Software Requirements

#### Python Backend
- **Python**: 3.10 or higher (3.11 recommended)
- **pip**: Latest version (comes with Python)
- **Virtual Environment**: venv (built into Python)

#### Node.js Frontend
- **Node.js**: 20.x (exact version: 20-alpine in Docker)
- **npm**: 9.x or higher (comes with Node.js)

#### External Services (Required)
- **PostgreSQL**: Neon cloud database (recommended) or local PostgreSQL 14+
- **Redis**: Local Redis 7+ or Upstash managed Redis

#### Optional Services
- **SMTP Server**: For email alerts (e.g., Gmail, SendGrid, AWS SES)
- **Webhook Endpoint**: For outbound result notifications

---

## Prerequisites

### 1. Install Python 3.10+

**Windows:**
```powershell
# Download from https://www.python.org/downloads/
# During installation, check "Add Python to PATH"
python --version
```

**macOS (using Homebrew):**
```bash
brew install python@3.11
python3 --version
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt update
sudo apt install python3.11 python3.11-venv python3-pip
python3 --version
```

### 2. Install Node.js 20.x

**Windows:**
```powershell
# Download from https://nodejs.org/
# Or using nvm-windows:
nvm install 20
nvm use 20
node --version
npm --version
```

**macOS/Linux (using nvm):**
```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash
source ~/.bashrc
nvm install 20
nvm use 20
node --version
npm --version
```

### 3. Install Git (for cloning repository)

**Windows:** Download from https://git-scm.com/download/win

**macOS:**
```bash
brew install git
```

**Linux:**
```bash
sudo apt install git
```

### 4. Install Redis (for local development)

**Windows:** Use Docker or WSL2
```powershell
# Using Docker:
docker run -d -p 6379:6379 redis:7-alpine
```

**macOS:**
```bash
brew install redis
brew services start redis
```

**Linux:**
```bash
sudo apt install redis-server
sudo systemctl start redis
sudo systemctl enable redis
```

**Alternative:** Use Upstash managed Redis (recommended for production)

---

## Project Overview

The Aspira TAT System is a production-grade Turnaround Time engine with the following architecture:

### Architecture Components
- **Backend**: FastAPI (Python 3.11) with async PostgreSQL support
- **Frontend**: Next.js 15 (React 18, TypeScript, Tailwind CSS v4)
- **Database**: PostgreSQL on Neon (cloud) or local PostgreSQL
- **Cache/Queue**: Redis for hot cache and Celery broker
- **Task Processing**: Celery + Celery Beat for async webhook processing
- **Authentication**: Cookie-based session auth with RBAC

### Project Structure
```
new test/
├── app/                    # Python backend (FastAPI)
│   ├── main.py            # FastAPI application entry point
│   ├── models.py          # Pydantic models
│   ├── pg_database.py     # Database layer
│   ├── routers/           # API route handlers
│   ├── workers/           # Celery tasks
│   ├── services/          # Business logic
│   └── core/              # Core utilities (auth, cache, etc.)
├── components/            # Next.js React components
├── config/                # Configuration files
├── database/              # Database schema and migrations
├── deploy/                # Docker files
├── edos.csv               # Test catalog (required)
├── requirements.txt       # Python dependencies
├── package.json           # Node.js dependencies
└── docker-compose.yml     # Docker orchestration
```

---

## Installation Steps

### Step 1: Clone the Repository

```bash
git clone <repository-url>
cd new test
```

**Note:** The repository directory is named "new test" (with a space). Ensure you navigate to it correctly.

### Step 2: Create Python Virtual Environment

**Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**macOS/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

**Verification:**
```bash
python --version
# Should show Python 3.10+
```

### Step 3: Install Python Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

**Key dependencies installed:**
- fastapi>=0.111.0 (Web framework)
- uvicorn[standard]>=0.29.0 (ASGI server)
- asyncpg>=0.29.0 (Async PostgreSQL driver)
- psycopg2-binary>=2.9.9 (Sync PostgreSQL driver for Celery)
- redis>=5.0.0 (Redis client)
- celery>=5.4.0 (Task queue)
- pydantic>=2.7.0 (Data validation)
- pandas>=2.2.0 (EDOS catalog parsing)

### Step 4: Install Node.js Dependencies

```bash
npm install
```

**Key dependencies installed:**
- next@15.0.0 (React framework)
- react@18.2.0 (UI library)
- tailwindcss@4.2.4 (CSS framework)
- @radix-ui/* (UI component library)
- lucide-react (Icons)

---

## Environment Configuration

### Step 1: Create .env File

Copy the template and configure it:

**Windows:**
```powershell
copy .env.neon-template .env
```

**macOS/Linux:**
```bash
cp .env.neon-template .env
```

### Step 2: Configure Required Environment Variables

Edit the `.env` file with your configuration:

#### Required Variables

```env
# PostgreSQL Database (Neon or local)
DATABASE_URL=postgresql://<user>:<password>@<host>/<db>?sslmode=require&channel_binding=require

# Leave these empty - they auto-derive from DATABASE_URL
PG_DSN=
PG_POOL_MIN=20
PG_POOL_MAX=100

# Redis Configuration
REDIS_URL=redis://localhost:6379/0
# Or for Upstash (managed Redis):
# REDIS_URL=rediss://default:<password>@<host>:6379

REDIS_TTL=172800
CELERY_CONCURRENCY=8
TZ=Asia/Kolkata
```

#### Authentication Variables

```env
# Demo Mode - Set to true for local development (bypasses auth)
DEMO_MODE=true

# Webhook Security (Required in production)
WEBHOOK_SHARED_SECRET=your-secret-key-here
WEBHOOK_SIGNATURE_HEADER=X-Aspira-Signature
WEBHOOK_TIMESTAMP_HEADER=X-Aspira-Timestamp
WEBHOOK_MAX_CLOCK_SKEW_SECONDS=300
```

#### Optional Variables (Email Alerts)

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASS=your-app-password
ALERT_EMAIL_FROM=noreply@aspira.com
ALERT_EMAIL_TO=alerts@aspira.com
```

#### Optional Variables (Webhook Results)

```env
WEBHOOK_RESULTS_URL=https://your-lis-system.com/api/results
```

#### Migration Feature Flags (Advanced)

```env
# Enable/disable migration features
MIGRATION_RECONCILIATION_ENABLED=false
MIGRATION_RECONCILIATION_SWEEP_ENABLED=false
MIGRATION_DUAL_WRITE_SLA_ETA=false
MIGRATION_DUAL_WRITE_QUEUE_ROUTING=false
MIGRATION_READ_NEW_DASHBOARD_MODEL=false
MIGRATION_READ_NEW_API_MODEL=false
MIGRATION_DISABLE_LEGACY_WRITES=false
MIGRATION_ENABLE_CYCLE_LINEAGE=false
```

### Step 3: Verify .env Configuration

Ensure the `.env` file is in the project root (same level as `package.json` and `requirements.txt`).

---

## Database Setup

### Option A: Neon Cloud Database (Recommended)

1. **Create a Neon Account**
   - Go to https://neon.tech
   - Sign up and create a new project
   - Copy the connection string

2. **Configure DATABASE_URL**
   ```env
   DATABASE_URL=postgresql://neondb_owner:npg_xxx@ep-xxx.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require
   ```

3. **Run Database Migration**
   ```bash
   python database/migrate.py
   ```

   This will:
   - Connect to Neon database
   - Drop and recreate the public schema
   - Execute `database/schema.sql`
   - Create all tables, indexes, and triggers

### Option B: Local PostgreSQL

1. **Install PostgreSQL**
   - Windows: Download from https://www.postgresql.org/download/windows/
   - macOS: `brew install postgresql@14`
   - Linux: `sudo apt install postgresql postgresql-contrib`

2. **Create Database**
   ```bash
   # Start PostgreSQL service
   # Windows: Start PostgreSQL service from Services
   # macOS: brew services start postgresql@14
   # Linux: sudo systemctl start postgresql

   # Create database
   createdb tat_db
   ```

3. **Configure DATABASE_URL**
   ```env
   DATABASE_URL=postgresql://postgres:your-password@localhost:5432/tat_db
   ```

4. **Run Database Migration**
   ```bash
   python database/migrate.py
   ```

### Step 4: Initialize Demo Data (Optional but Recommended)

To populate the database with realistic test data:

```bash
python database/init_demo.py
```

This will:
- Create 9 realistic labs (GHK, NM, Shobha, Kharghar, Chembur, HOC, Truecare, SSO, OS)
- Create admin and lab manager user accounts
- Initialize master EDOS test catalog (15 test types)
- Configure lab capabilities and EDOS distribution
- Set up batch schedules
- Configure routing rules
---
## Running the Application

### Manual Setup (Development)

You need to run 4 separate processes:

#### Terminal 1: Backend API
```bash
# Activate virtual environment first
.\venv\Scripts\Activate.ps1  # Windows
source venv/bin/activate      # macOS/Linux

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

#### Terminal 2: Celery Worker
```bash
# Activate virtual environment first
.\venv\Scripts\Activate.ps1  # Windows
source venv/bin/activate      # macOS/Linux

celery -A app.workers.celery_app worker --loglevel=info -P solo --queues=queue:webhook-processing,queue:alert-processing,projection
```

#### Terminal 3: Celery Beat (Scheduler)
```bash
# Activate virtual environment first
.\venv\Scripts\Activate.ps1  # Windows
source venv/bin/activate      # macOS/Linux

celery -A app.workers.celery_app beat --loglevel=info
```

#### Terminal 4: Frontend
```bash
npm run dev
```

### Service URLs

| Service | URL | Description |
|---------|-----|-------------|
| Frontend Dashboard | http://localhost:3000 | Next.js application |
| Backend API | http://localhost:8000 | FastAPI backend |
| API Documentation | http://localhost:8000/docs | Swagger UI |
| Health Check | http://localhost:8000/health | Health endpoint |

---

## Docker Setup (Alternative)

### Prerequisites

- Docker Desktop installed and running
- Docker Compose installed (comes with Docker Desktop)

### Step 1: Configure .env for Docker

The `.env` file should be configured as described in [Environment Configuration](#environment-configuration).

**Note for Docker:**
- PostgreSQL runs on Neon (cloud) - no local container needed
- Redis can be local or Upstash (managed)
- The docker-compose.yml does NOT include a Redis container

### Step 2: Build and Start Services

```bash
# Build and start all services
docker compose up --build

# Or run in detached mode
docker compose up --build -d

# View logs
docker compose logs -f backend
docker compose logs -f worker
docker compose logs -f frontend
```

### Step 3: Stop Services

```bash
# Stop services
docker compose down

# Stop and remove volumes
docker compose down -v
```

### Docker Services

The docker-compose.yml includes:
- **backend**: FastAPI (uvicorn) on port 8000
- **worker**: Celery worker for webhook processing
- **beat**: Celery beat for scheduled tasks
- **frontend**: Next.js on port 3000

---
### 5. Verify Redis Connection

```bash
# Using Python
python -c "import redis; r = redis.from_url(os.getenv('REDIS_URL')); r.ping()"
```

### 6. Verify Celery Worker

Check Celery worker terminal for:
```
[tasks]
. webhook.process
. sweep.delayed
. projection.refresh
. reconciliation.sweep
. sla.at_risk
. redraw.overdue
. lab.downtime_sync
. alert.process

[queues]
. queue:webhook-processing
. queue:alert-processing
. projection
```

### 7. Test Webhook Ingestion

Send a test webhook:

```bash
curl -X POST http://localhost:8000/api/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "webhook_type": "BILL_GENERATE",
    "bill_id": 12345,
    "lab_id": 1,
    "payload": {}
  }'
```

**Expected response:**
```json
{
  "status": "accepted",
  "event_id": 1,
  "message": "Webhook received and queued for processing"
}
```

---

## Complete Postman Guide for Webhook Testing

This guide walks you through sending all webhook types one by one using Postman.

### Prerequisites

1. Download and install Postman: https://www.postman.com/downloads/
2. Backend API running on `http://localhost:8000`
3. Database initialized with demo data (`python database/init_demo.py`)

---

### Step 1: Create a New Collection

1. Open Postman
2. Click **"+ Create"** → **Collection**
3. Name it **"Aspira TAT Webhooks"**
4. Click **Create**

---

### Step 2: Create Environment Variables (Optional but Recommended)

1. Click **Environments** in the left sidebar
2. Click **"+ Create New"**
3. Name it **"Local Development"**
4. Add these variables:

| Variable | Initial Value | Current Value |
|----------|---|---|
| base_url | http://localhost:8000 | http://localhost:8000 |
| bill_id | 12345 | 12345 |
| lab_id | 1 | 1 |
| patient_id | 101 | 101 |
| sample_accession | ACC-2024-001 | ACC-2024-001 |
| lab_report_id | 1001 | 1001 |

5. Click **Save**
6. Select this environment from the top-right dropdown

---

### Step 3: Create Webhook Requests

#### 1️⃣ **BILL_GENERATE** (Start Here)

This webhook initiates a new bill and starts the TAT pipeline.

1. Click **"+"** to create a new request in your collection
2. Name it **"1. BILL_GENERATE"**
3. Set **Method** to **POST**
4. Set **URL** to:
   ```
   {{base_url}}/api/webhook
   ```

5. Go to **Headers** tab and add:
   ```
   Content-Type: application/json
   ```

6. Go to **Body** tab, select **raw** and **JSON**, then paste:

```json
{
  "webhook_type": "BILL_GENERATE",
  "bill_id": {{bill_id}},
  "lab_id": {{lab_id}},
  "payload": {
    "webhookId": 1001,
    "billId": {{bill_id}},
    "labId": {{lab_id}},
    "billTime": "2024-06-10T10:00:00Z",
    "totalAmount": 5000,
    "dueAmount": 5000,
    "billAdvance": 0,
    "patientId": {{patient_id}},
    "patientName": "John Doe",
    "patientGender": "M",
    "patientAge": "35",
    "collectedSampleId": {
      "id": 2001,
      "accessionNo": "{{sample_accession}}",
      "collectionTime": "2024-06-10T09:30:00Z",
      "type": "BLOOD",
      "name": "Blood Sample"
    },
    "labReportDetails": [
      {
        "labReportId": {{lab_report_id}},
        "testID": 101,
        "testCode": "CBC",
        "testName": "Complete Blood Count",
        "testCategory": "Hematology",
        "testAmount": 500
      }
    ],
    "sampleDate": "2024-06-10T09:30:00Z",
    "reportDate": "2024-06-10T10:00:00Z"
  }
}
```

7. Click **Send**
8. Check response (should be 202 Accepted)

---

#### 2️⃣ **BILL_UPDATE**

Updates bill information.

1. Create a new request: **"2. BILL_UPDATE"**
2. Set **Method** to **POST**
3. Set **URL** to: `{{base_url}}/api/webhook`
4. **Body** (raw JSON):

```json
{
  "webhook_type": "BILL_UPDATE",
  "bill_id": {{bill_id}},
  "lab_id": {{lab_id}},
  "payload": {
    "webhookId": 1002,
    "billId": {{bill_id}},
    "labId": {{lab_id}},
    "billTime": "2024-06-10T10:15:00Z",
    "totalAmount": 5500,
    "dueAmount": 5500,
    "billAdvance": 0,
    "patientId": {{patient_id}},
    "patientName": "John Doe"
  }
}
```

5. Click **Send**

---

#### 3️⃣ **SAMPLE_COLLECTED**

Marks sample as collected at the collection center.

1. Create request: **"3. SAMPLE_COLLECTED"**
2. **URL**: `{{base_url}}/api/webhook`
3. **Body**:

```json
{
  "webhook_type": "SAMPLE_COLLECTED",
  "bill_id": {{bill_id}},
  "lab_id": {{lab_id}},
  "payload": {
    "webhookId": 1003,
    "bill_id": {{bill_id}},
    "lab_id": {{lab_id}},
    "sampleId": {
      "id": 2001,
      "accessionNo": "{{sample_accession}}",
      "collectionTime": "2024-06-10T09:30:00Z",
      "type": "BLOOD",
      "name": "Blood Sample"
    },
    "timestamp": "2024-06-10T09:30:00Z"
  }
}
```

4. Click **Send**

---

#### 4️⃣ **SAMPLE_RECEIVED**

Marks sample as received at the processing lab (triggers scheduling).

1. Create request: **"4. SAMPLE_RECEIVED"**
2. **URL**: `{{base_url}}/api/webhook`
3. **Body**:

```json
{
  "webhook_type": "SAMPLE_RECEIVED",
  "bill_id": {{bill_id}},
  "lab_id": {{lab_id}},
  "payload": {
    "webhookId": 1004,
    "bill_id": {{bill_id}},
    "lab_id": {{lab_id}},
    "sampleId": {
      "id": 2001,
      "accessionNo": "{{sample_accession}}"
    },
    "receivedTime": "2024-06-10T10:30:00Z",
    "receivedBy": "Lab Tech"
  }
}
```

4. Click **Send**

---

#### 5️⃣ **REPORT_SAVE**

Saves result values (not final submission).

1. Create request: **"5. REPORT_SAVE"**
2. **URL**: `{{base_url}}/api/webhook`
3. **Body**:

```json
{
  "webhook_type": "REPORT_SAVE",
  "bill_id": {{bill_id}},
  "lab_id": {{lab_id}},
  "payload": {
    "webhookId": 1005,
    "bill_id": {{bill_id}},
    "lab_id": {{lab_id}},
    "labReportDetails": [
      {
        "labReportId": {{lab_report_id}},
        "testID": 101,
        "testCode": "CBC",
        "testName": "Complete Blood Count",
        "testAmount": 500,
        "reportDate": "2024-06-10T11:00:00Z"
      }
    ],
    "timestamp": "2024-06-10T11:00:00Z",
    "savedBy": "Lab Analyst"
  }
}
```

4. Click **Send**

---

#### 6️⃣ **REPORT_SUBMIT**

Submits report for final review (main TAT completion trigger).

1. Create request: **"6. REPORT_SUBMIT"**
2. **URL**: `{{base_url}}/api/webhook`
3. **Body**:

```json
{
  "webhook_type": "REPORT_SUBMIT",
  "bill_id": {{bill_id}},
  "lab_id": {{lab_id}},
  "payload": {
    "webhookId": 1006,
    "bill_id": {{bill_id}},
    "lab_id": {{lab_id}},
    "labReportDetails": [
      {
        "labReportId": {{lab_report_id}},
        "testID": 101,
        "testCode": "CBC",
        "testName": "Complete Blood Count",
        "reportDate": "2024-06-10T11:15:00Z"
      }
    ],
    "submittedTime": "2024-06-10T11:15:00Z",
    "submittedBy": "Lab Manager"
  }
}
```

4. Click **Send**

---

#### 7️⃣ **REPORT_SIGNED**

Report signed by authorized personnel (final state).

1. Create request: **"7. REPORT_SIGNED"**
2. **URL**: `{{base_url}}/api/webhook`
3. **Body**:

```json
{
  "webhook_type": "REPORT_SIGNED",
  "bill_id": {{bill_id}},
  "lab_id": {{lab_id}},
  "payload": {
    "webhookId": 1007,
    "bill_id": {{bill_id}},
    "lab_id": {{lab_id}},
    "labReportDetails": [
      {
        "labReportId": {{lab_report_id}},
        "testID": 101,
        "testCode": "CBC"
      }
    ],
    "signedTime": "2024-06-10T11:30:00Z",
    "signedBy": "Dr. Smith"
  }
}
```

4. Click **Send**

---

#### 8️⃣ **SAMPLE_REJECTED**

Sample rejected at lab (requires redraw).

1. Create request: **"8. SAMPLE_REJECTED"**
2. **URL**: `{{base_url}}/api/webhook`
3. **Body**:

```json
{
  "webhook_type": "SAMPLE_REJECTED",
  "bill_id": {{bill_id}},
  "lab_id": {{lab_id}},
  "payload": {
    "webhookId": 1008,
    "bill_id": {{bill_id}},
    "lab_id": {{lab_id}},
    "sampleId": {
      "id": 2001,
      "accessionNo": "{{sample_accession}}"
    },
    "rejectionReason": "Hemolyzed sample",
    "rejectionTime": "2024-06-10T10:45:00Z",
    "rejectedBy": "Lab Tech"
  }
}
```

4. Click **Send**

---

#### 9️⃣ **SAMPLE_REDRAWN**

Sample redrawn (creates new cycle).

1. Create request: **"9. SAMPLE_REDRAWN"**
2. **URL**: `{{base_url}}/api/webhook`
3. **Body**:

```json
{
  "webhook_type": "SAMPLE_REDRAWN",
  "bill_id": {{bill_id}},
  "lab_id": {{lab_id}},
  "payload": {
    "webhookId": 1009,
    "bill_id": {{bill_id}},
    "lab_id": {{lab_id}},
    "sampleId": {
      "id": 2001,
      "accessionNo": "{{sample_accession}}"
    },
    "newSampleId": {
      "id": 2002,
      "accessionNo": "ACC-2024-001-RD1",
      "collectionTime": "2024-06-10T11:00:00Z"
    },
    "redrawReason": "Hemolyzed sample",
    "redrawTime": "2024-06-10T11:00:00Z"
  }
}
```

4. Click **Send**

---

#### 🔟 **SAMPLE_DISMISSED**

Sample/bill completely dismissed.

1. Create request: **"10. SAMPLE_DISMISSED"**
2. **URL**: `{{base_url}}/api/webhook`
3. **Body**:

```json
{
  "webhook_type": "SAMPLE_DISMISSED",
  "bill_id": {{bill_id}},
  "lab_id": {{lab_id}},
  "payload": {
    "webhookId": 1010,
    "bill_id": {{bill_id}},
    "lab_id": {{lab_id}},
    "sampleId": {
      "id": 2001,
      "accessionNo": "{{sample_accession}}"
    },
    "dismissalReason": "Patient cancelled",
    "dismissalTime": "2024-06-10T12:00:00Z"
  }
}
```

4. Click **Send**

---

#### 1️⃣1️⃣ **TEST_DISMISSED**

Individual test dismissed/cancelled.

1. Create request: **"11. TEST_DISMISSED"**
2. **URL**: `{{base_url}}/api/webhook`
3. **Body**:

```json
{
  "webhook_type": "TEST_DISMISSED",
  "bill_id": {{bill_id}},
  "lab_id": {{lab_id}},
  "payload": {
    "webhookId": 1011,
    "bill_id": {{bill_id}},
    "lab_id": {{lab_id}},
    "testID": 101,
    "testCode": "CBC",
    "testName": "Complete Blood Count",
    "dismissalReason": "Patient refused",
    "dismissalTime": "2024-06-10T12:15:00Z"
  }
}
```

4. Click **Send**

---

### Running Webhooks in Sequence

#### Option 1: Manual Execution

1. Click each request in order (1-7 for happy path)
2. Wait for response (should be **202 Accepted**)
3. Proceed to next request

#### Option 2: Run Collection Automatically

1. Click the **▶ Play** button next to your collection name
2. Select **"Local Development"** environment
3. Set delay to **2 seconds** between requests
4. Click **Run Aspira TAT Webhooks**

Postman will execute all requests with 2-second delays between them.

---

### Response Interpretation

**Success Response (202 Accepted):**
```json
{
  "status": "accepted",
  "event_id": 1,
  "message": "Webhook received and queued for processing"
}
```

**Error Responses:**

| Status | Meaning |
|--------|---------|
| 202 | ✅ Webhook accepted, queued for processing |
| 400 | ❌ Invalid payload (check JSON syntax) |
| 422 | ❌ Validation failed (missing required fields) |
| 500 | ❌ Server error (check backend logs) |

---

### Common Payload Fields Reference

| Field | Type | Required | Example |
|-------|------|----------|---------|
| webhook_type | string | Yes | "BILL_GENERATE" |
| bill_id | integer | Yes | 12345 |
| lab_id | integer | Yes | 1 |
| payload | object | Yes | { ... } |
| webhookId | integer | No | 1001 |
| timestamp | string | No | "2024-06-10T10:00:00Z" |

---

### Recommended Testing Sequence

**Happy Path (Normal Case):**
1. BILL_GENERATE
2. SAMPLE_COLLECTED
3. SAMPLE_RECEIVED
4. REPORT_SAVE
5. REPORT_SUBMIT
6. REPORT_SIGNED

**Error Scenario (Sample Rejection):**
1. BILL_GENERATE
2. SAMPLE_COLLECTED
3. SAMPLE_RECEIVED
4. SAMPLE_REJECTED
5. SAMPLE_REDRAWN
6. (Repeat from SAMPLE_COLLECTED with new accession number)

**Cancellation Scenario:**
1. BILL_GENERATE
2. SAMPLE_COLLECTED
3. SAMPLE_DISMISSED

---

### Debugging Tips

1. **Check Backend Logs:**
   ```bash
   # Terminal running uvicorn
   # Look for webhook processing messages
   ```

2. **Check Celery Worker:**
   ```bash
   # Terminal running celery worker
   # Verify webhook.process task is received
   ```

3. **View Database Events:**
   ```sql
   -- Connect to PostgreSQL
   SELECT * FROM tat_webhook_event ORDER BY created_at DESC LIMIT 10;
   ```

4. **Enable Postman Console:**
   - Press **Ctrl+Alt+C** (or Cmd+Option+C on Mac)
   - View request/response details
   - Check headers and body

---

### Next Steps

- Once webhooks are successfully processed, check the dashboard at `http://localhost:3000`
- Verify bill status, sample journey, and TAT metrics are updated
- Monitor alerts if SLA thresholds are breached

---
### Performance Tuning

1. **PostgreSQL**
   ```env
   PG_POOL_MIN=20
   PG_POOL_MAX=100
   ```

2. **Celery**
   ```env
   CELERY_CONCURRENCY=8  # Adjust based on CPU cores
   ```

3. **Redis**
   ```env
   REDIS_TTL=172800  # 48 hours
   ```

### Monitoring

- Enable logging for all services
- Set up health checks
- Monitor Celery queue lengths
- Track webhook processing times
- Monitor database connection pool usage
---
## Checklist

Before starting development, ensure you have:

- [ ] Python 3.10+ installed
- [ ] Node.js 20.x installed
- [ ] Virtual environment created and activated
- [ ] Python dependencies installed (`pip install -r requirements.txt`)
- [ ] Node dependencies installed (`npm install`)
- [ ] .env file configured with DATABASE_URL
- [ ] Redis running (local or Upstash)
- [ ] Database migrated (`python database/migrate.py`)
- [ ] Demo data initialized (`python database/init_demo.py`)
- [ ] edos.csv file present in project root
- [ ] Backend starts successfully (`uvicorn app.main:app`)
- [ ] Celery worker starts successfully
- [ ] Celery beat starts successfully
- [ ] Frontend starts successfully (`npm run dev`)
- [ ] Can access http://localhost:3000
- [ ] Can access http://localhost:8000/docs
- [ ] Health check passes (`curl http://localhost:8000/health`)

---

**Last Updated:** 2026-05-31
**Version:** 2.0.0
