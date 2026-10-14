# Aspira TAT — Live Demo Runbook (multi-lab sample journeys)

Every step is a `curl` call against the deployed backend. Each call sends exactly what
CrelioHealth would send (Bill Generation, Sample Received, Report Submit…), so the demo
runs the real routing, batch-slot and ETA logic, just triggered by hand.

After each step, `GET /api/demo/journey/<billId>` shows the whole picture for that bill:
which lab each test went to, when it arrived there, and its ETA.

---

## 0. One-time setup on the server (`51.20.173.132`)

`.env` on the server must contain:

```ini
DEMO_MODE=true            # unsigned webhooks, processed inline, Redis optional
APP_ENV=development       # DEMO_MODE is refused when APP_ENV=production
PUBLIC_API_URL=http://51.20.173.132:8000
DATABASE_URL=...          # the demo database
REDIS_URL=...             # optional in demo mode
WEBHOOK_SHARED_SECRET=... # any value; signed requests are still verified
```

Start and load the demo lab network (**this wipes the database `DATABASE_URL` points to**):

```bash
docker compose up -d --build
docker compose exec backend python database/migrate.py      # recreate schema
docker compose exec backend python database/init_demo.py    # 9-lab demo network
```

Existing database that must not be wiped? Apply the two files in `database/migrations/`
instead of `migrate.py`, then run `init_demo.py` only on a database with no bills yet.

Dashboard: `http://51.20.173.132:3000` · API docs: `http://51.20.173.132:8000/docs`

## 1. Before you start (on the laptop you demo from)

Works in Git Bash, macOS and Linux terminals.

```bash
export API=http://51.20.173.132:8000
export B=101    # run number: use a new value for every fresh run (bill ids must be new)
at() { date -u -d "+${1:-0} minutes" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -v+${1:-0}M +%Y-%m-%dT%H:%M:%SZ; }
T0=$(at 0)

curl -s $API/health; echo
```

`at 90` = the time 90 minutes from now (used to stage receipts at different labs).

### Demo lab network (from `init_demo.py`)

| Lab | CrelioHealth `labId` | Processes |
|---|---|---|
| GHK (fallback) | 1001 | Haematology, Biochemistry, Clin. Pathology, Thyroid, Lipid |
| NM | 1002 | Thyroid, Hormonal, Specialized Biochem |
| SHOBHA | 1003 | Haematology, Clinical Pathology |
| KHARGHAR | 1004 | Haematology, Biochemistry |
| CHEMBUR | 1005 | Haematology |
| HOC | 1006 | — (collection centre) |
| TRUECARE | 1007 | — (collection centre) |
| SSO | 1008 | Haematology |
| OS | 1009 | Specialized Biochem, Molecular |

Tests used below: CBC (Haematology, testID 230964), URINE (Clinical Pathology, 231287),
LFT (Biochemistry, 234978), THYROID (Thyroid, 237001), MOLECULAR (Molecular, 238003).

---

## Case 1 — Collected and processed in the same lab (Shobha)

**1a. Bill generated at Shobha** (CBC + Urine, one tube)

```bash
curl -s -X POST $API/api/webhook -H 'Content-Type: application/json' -d @- <<EOF; echo
{"webhook_type":"BILL_GENERATE","billId":${B}01,
 "labId":{"labId":1003,"labName":"SHOBHA"},"orgId":{"orgId":7001,"orgFullName":"Demo Clinic"},
 "patientId":${B}01,"patientName":"Case 1 Patient","collectionTime":"$T0",
 "labReportDetails":[
  {"labReportId":${B}0101,"collectedSampleId":{"accessionNo":"SHB-${B}01","collectionTime":"$T0"},
   "reportID":{"testID":230964,"testCode":"CBC","testName":"Complete Blood Count","departmentId":906}},
  {"labReportId":${B}0102,"collectedSampleId":{"accessionNo":"SHB-${B}01","collectionTime":"$T0"},
   "reportID":{"testID":231287,"testCode":"URINE","testName":"Routine Examination Urine","departmentId":915}}]}
EOF
```

**1b. Shobha receives the sample** (both tests)

```bash
curl -s -X POST $API/api/webhook -H 'Content-Type: application/json' -d @- <<EOF; echo
{"webhook_type":"SAMPLE_RECEIVED","billId":${B}01,"sampleId":"SHB-${B}01",
 "labId":1003,"accessionDate":"$(at 15)","CentreReportId":[${B}0101,${B}0102]}
EOF
```

**1c. Show it** — collected at SHOBHA, both tests processed at SHOBHA, one slot, one ETA.

```bash
curl -s $API/api/demo/journey/${B}01; echo
```

---

## Case 2 — Collected in Lab 1, processed in Lab 2 (Truecare → Shobha)

**2a. Bill generated at Truecare** (collection centre, processes nothing itself)

```bash
curl -s -X POST $API/api/webhook -H 'Content-Type: application/json' -d @- <<EOF; echo
{"webhook_type":"BILL_GENERATE","billId":${B}02,
 "labId":{"labId":1007,"labName":"TRUECARE"},"orgId":{"orgId":7001,"orgFullName":"Demo Clinic"},
 "patientId":${B}02,"patientName":"Case 2 Patient","collectionTime":"$T0",
 "labReportDetails":[
  {"labReportId":${B}0201,"collectedSampleId":{"accessionNo":"TRU-${B}02","collectionTime":"$T0"},
   "reportID":{"testID":230964,"testCode":"CBC","testName":"Complete Blood Count","departmentId":906}},
  {"labReportId":${B}0202,"collectedSampleId":{"accessionNo":"TRU-${B}02","collectionTime":"$T0"},
   "reportID":{"testID":231287,"testCode":"URINE","testName":"Routine Examination Urine","departmentId":915}}]}
EOF
```

**2b. Shobha receives it 45 minutes later** (after transport)

```bash
R2=$(at 45)     # receipt time, kept so E3 can resend this exact event
curl -s -X POST $API/api/webhook -H 'Content-Type: application/json' -d @- <<EOF; echo
{"webhook_type":"SAMPLE_RECEIVED","billId":${B}02,"sampleId":"TRU-${B}02",
 "labId":1003,"accessionDate":"$R2","CentreReportId":[${B}0201,${B}0202]}
EOF
```

**2c. Show it** — collected at TRUECARE, processed at SHOBHA, arrival 45 min after collection.

```bash
curl -s $API/api/demo/journey/${B}02; echo
```

---

## Case 3 — Collected in Lab 1, reports split across Labs 2/3/4/5 (HOC → Shobha, Kharghar, NM, OS)

**3a. Bill generated at HOC** — four tests, one tube

```bash
curl -s -X POST $API/api/webhook -H 'Content-Type: application/json' -d @- <<EOF; echo
{"webhook_type":"BILL_GENERATE","billId":${B}03,
 "labId":{"labId":1006,"labName":"HOC"},"orgId":{"orgId":7001,"orgFullName":"Demo Clinic"},
 "patientId":${B}03,"patientName":"Case 3 Patient","collectionTime":"$T0",
 "labReportDetails":[
  {"labReportId":${B}0301,"collectedSampleId":{"accessionNo":"HOC-${B}03","collectionTime":"$T0"},
   "reportID":{"testID":230964,"testCode":"CBC","testName":"Complete Blood Count","departmentId":906}},
  {"labReportId":${B}0302,"collectedSampleId":{"accessionNo":"HOC-${B}03","collectionTime":"$T0"},
   "reportID":{"testID":234978,"testCode":"LFT","testName":"Liver Function Test","departmentId":913}},
  {"labReportId":${B}0303,"collectedSampleId":{"accessionNo":"HOC-${B}03","collectionTime":"$T0"},
   "reportID":{"testID":237001,"testCode":"THYROID","testName":"Thyroid Profile","departmentId":917}},
  {"labReportId":${B}0304,"collectedSampleId":{"accessionNo":"HOC-${B}03","collectionTime":"$T0"},
   "reportID":{"testID":238003,"testCode":"MOLECULAR","testName":"Molecular Testing","departmentId":921}}]}
EOF
```

**3b. Shobha receives the CBC (+1 h)** — the other three get a provisional lab and ETA

```bash
curl -s -X POST $API/api/webhook -H 'Content-Type: application/json' -d @- <<EOF; echo
{"webhook_type":"SAMPLE_RECEIVED","billId":${B}03,"sampleId":"HOC-${B}03",
 "labId":1003,"accessionDate":"$(at 60)","CentreReportId":[${B}0301]}
EOF
curl -s $API/api/demo/journey/${B}03; echo
```

**3c. Kharghar receives the LFT (+2 h), NM the Thyroid (+3 h), OS the Molecular (+4 h)**

```bash
curl -s -X POST $API/api/webhook -H 'Content-Type: application/json' -d @- <<EOF; echo
{"webhook_type":"SAMPLE_RECEIVED","billId":${B}03,"sampleId":"HOC-${B}03",
 "labId":1004,"accessionDate":"$(at 120)","CentreReportId":[${B}0302]}
EOF
curl -s -X POST $API/api/webhook -H 'Content-Type: application/json' -d @- <<EOF; echo
{"webhook_type":"SAMPLE_RECEIVED","billId":${B}03,"sampleId":"HOC-${B}03",
 "labId":1002,"accessionDate":"$(at 180)","CentreReportId":[${B}0303]}
EOF
curl -s -X POST $API/api/webhook -H 'Content-Type: application/json' -d @- <<EOF; echo
{"webhook_type":"SAMPLE_RECEIVED","billId":${B}03,"sampleId":"HOC-${B}03",
 "labId":1009,"accessionDate":"$(at 240)","CentreReportId":[${B}0304]}
EOF
```

**3d. Show it** — four labs, each with its own arrival time, batch slot and ETA;
`sample_eta_end` is the slowest lab.

```bash
curl -s $API/api/demo/journey/${B}03; echo
```

**3e. Labs report results one by one** — the sample completes only after the last lab reports

```bash
for R in ${B}0301 ${B}0302 ${B}0303; do
curl -s -X POST $API/api/webhook -H 'Content-Type: application/json' -d @- <<EOF; echo
{"webhook_type":"REPORT_SUBMIT","billId":${B}03,"labReportId":$R,"reportDate":"$(at 300)","isSigned":1}
EOF
done
curl -s $API/api/demo/journey/${B}03; echo      # sample: partially_complete
curl -s -X POST $API/api/webhook -H 'Content-Type: application/json' -d @- <<EOF; echo
{"webhook_type":"REPORT_SUBMIT","billId":${B}03,"labReportId":${B}0304,"reportDate":"$(at 360)","isSigned":1}
EOF
curl -s $API/api/demo/journey/${B}03; echo      # sample + bill: completed
```

---

## Extra cases (if there is time)

### E1 — Same tube travels Shobha → Kharghar (sequential labs)

Shobha receives the tube with CBC + LFT; later the tube reaches Kharghar, which takes the LFT.
The LFT moves to Kharghar with Kharghar's own arrival time.

```bash
curl -s -X POST $API/api/webhook -H 'Content-Type: application/json' -d @- <<EOF; echo
{"webhook_type":"BILL_GENERATE","billId":${B}04,
 "labId":{"labId":1006,"labName":"HOC"},"orgId":{"orgId":7001,"orgFullName":"Demo Clinic"},
 "patientId":${B}04,"patientName":"Chain Patient","collectionTime":"$T0",
 "labReportDetails":[
  {"labReportId":${B}0401,"collectedSampleId":{"accessionNo":"HOC-${B}04","collectionTime":"$T0"},
   "reportID":{"testID":230964,"testCode":"CBC","testName":"Complete Blood Count","departmentId":906}},
  {"labReportId":${B}0402,"collectedSampleId":{"accessionNo":"HOC-${B}04","collectionTime":"$T0"},
   "reportID":{"testID":234978,"testCode":"LFT","testName":"Liver Function Test","departmentId":913}}]}
EOF
curl -s -X POST $API/api/webhook -H 'Content-Type: application/json' -d @- <<EOF; echo
{"webhook_type":"SAMPLE_RECEIVED","billId":${B}04,"sampleId":"HOC-${B}04",
 "labId":1003,"accessionDate":"$(at 60)","CentreReportId":[${B}0401,${B}0402]}
EOF
curl -s $API/api/demo/journey/${B}04; echo      # both at SHOBHA
curl -s -X POST $API/api/webhook -H 'Content-Type: application/json' -d @- <<EOF; echo
{"webhook_type":"SAMPLE_RECEIVED","billId":${B}04,"sampleId":"HOC-${B}04",
 "labId":1004,"accessionDate":"$(at 150)","CentreReportId":[${B}0402]}
EOF
curl -s $API/api/demo/journey/${B}04; echo      # LFT now at KHARGHAR
```

### E2 — Two tubes on one bill, received at different labs

```bash
curl -s -X POST $API/api/webhook -H 'Content-Type: application/json' -d @- <<EOF; echo
{"webhook_type":"BILL_GENERATE","billId":${B}05,
 "labId":{"labId":1007,"labName":"TRUECARE"},"orgId":{"orgId":7001,"orgFullName":"Demo Clinic"},
 "patientId":${B}05,"patientName":"Two Tube Patient","collectionTime":"$T0",
 "labReportDetails":[
  {"labReportId":${B}0501,"collectedSampleId":{"accessionNo":"EDTA-${B}05","collectionTime":"$T0"},
   "reportID":{"testID":230964,"testCode":"CBC","testName":"Complete Blood Count","departmentId":906}},
  {"labReportId":${B}0502,"collectedSampleId":{"accessionNo":"SST-${B}05","collectionTime":"$T0"},
   "reportID":{"testID":237001,"testCode":"THYROID","testName":"Thyroid Profile","departmentId":917}}]}
EOF
curl -s -X POST $API/api/webhook -H 'Content-Type: application/json' -d @- <<EOF; echo
{"webhook_type":"SAMPLE_RECEIVED","billId":${B}05,"sampleId":"EDTA-${B}05",
 "labId":1003,"accessionDate":"$(at 40)","CentreReportId":[${B}0501]}
EOF
curl -s -X POST $API/api/webhook -H 'Content-Type: application/json' -d @- <<EOF; echo
{"webhook_type":"SAMPLE_RECEIVED","billId":${B}05,"sampleId":"SST-${B}05",
 "labId":1002,"accessionDate":"$(at 70)","CentreReportId":[${B}0502]}
EOF
curl -s $API/api/demo/journey/${B}05; echo      # two samples, two labs
```

### E3 — Duplicate delivery is ignored

Re-send the exact receipt from 2b (same lab, same time `$R2`), as CrelioHealth does when
it retries a delivery. The response says `"duplicate":true` and nothing changes.

```bash
curl -s -X POST $API/api/webhook -H 'Content-Type: application/json' -d @- <<EOF; echo
{"webhook_type":"SAMPLE_RECEIVED","billId":${B}02,"sampleId":"TRU-${B}02",
 "labId":1003,"accessionDate":"$R2","CentreReportId":[${B}0201,${B}0202]}
EOF
```

### E4 — Redraw: sample rejected quality-wise, new draw, new cycle

```bash
curl -s -X POST $API/api/webhook -H 'Content-Type: application/json' -d @- <<EOF; echo
{"webhook_type":"SAMPLE_REDRAWN","billId":${B}01,"sampleId":"SHB-${B}01",
 "redrawReason":"Haemolysed","newCollectionTime":"$(at 90)"}
EOF
curl -s $API/api/demo/journey/${B}01; echo      # cycle 1 invalidated, cycle 2 pending
curl -s -X POST $API/api/webhook -H 'Content-Type: application/json' -d @- <<EOF; echo
{"webhook_type":"SAMPLE_RECEIVED","billId":${B}01,"sampleId":"SHB-${B}01",
 "labId":1003,"accessionDate":"$(at 100)","CentreReportId":[${B}0101,${B}0102]}
EOF
curl -s $API/api/demo/journey/${B}01; echo      # cycle 2 routed and slotted
```

### E5 — Sample sent to an external lab

```bash
curl -s -X POST $API/api/webhook -H 'Content-Type: application/json' -d @- <<EOF; echo
{"webhook_type":"SAMPLE_SENT_TO_EXTERNAL","billId":${B}02,"sampleId":"TRU-${B}02",
 "externalLabName":"Metropolis Reference Lab","sentTime":"$(at 60)"}
EOF
curl -s $API/api/demo/journey/${B}02; echo      # assignment=outsourced, vendor ETA kept
```

---

## What to point at in the journey output

| Field | Meaning |
|---|---|
| `collected_at_lab` | Lab where the bill / collection happened |
| `samples[].labs` | Labs processing this tube |
| `tests[].processing_lab` / `routing_reason` | Where the test runs and why (`webhook_received_at` = that lab confirmed receipt; `capability_match` = provisional, not yet received) |
| `tests[].arrived_at_lab` | When the sample reached that lab |
| `tests[].eta_start` / `eta_end` | Batch slot and expected finish at that lab |
| `samples[].sample_eta_end` | Expected finish of the whole sample (slowest lab) |
| `tests[].tat_breached` | Whether the ETA misses the TAT commitment |

Times are UTC.

## Other useful reads

```bash
curl -s "$API/api/samples?limit=20"; echo        # recent samples
curl -s $API/api/labs; echo                       # labs with internal ids
curl -s $API/api/dashboard/admin; echo            # admin dashboard numbers
```
