/**
 * app/lib/api.ts
 * ─────────────────────────────────────────────────────────────────────────────
 * Centralised fetch helpers for the Aspira TAT frontend.
 * All calls go to NEXT_PUBLIC_API_URL (default: http://localhost:8000).
 *
 * Naming convention:  fetch*   → GET
 *                     confirm* → POST side-effect (logistics)
 *                     admin*   → POST admin override
 *                     update*  → POST status advance
 *                     submit*  → POST result upload
 */

const BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

// ─── Generic helper ───────────────────────────────────────────────────────────

async function api<T = any>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    credentials: 'include',                        // ← send auth cookies cross-origin
    headers: { 'Content-Type': 'application/json', ...(options?.headers ?? {}) },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text().catch(() => res.statusText);
    throw new Error(body || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

// ─── Stats ────────────────────────────────────────────────────────────────────

/** GET /api/stats — dashboard aggregate metrics */
export const fetchStats = () => api('/api/stats');

/** GET /api/stats/labs — per-lab queue depth + batch counts */
export const fetchLabStats = () => api('/api/stats/labs');

/** GET /api/stats/sla — SLA breach rate by client type */
export const fetchSlaStats = () => api('/api/stats/sla');

// ─── Samples ──────────────────────────────────────────────────────────────────

export interface SamplesParams {
  status?: string;
  limit?: number;
  offset?: number;
}

/** GET /api/samples — paginated sample list */
export const fetchSamples = ({ status, limit = 50, offset = 0 }: SamplesParams = {}) => {
  const params = new URLSearchParams();
  if (status) params.set('status', status);
  params.set('limit', String(limit));
  params.set('offset', String(offset));
  return api(`/api/samples?${params.toString()}`);
};

/** GET /api/samples/:id — full sample detail with tests, ETA, logs */
export const fetchSampleDetail = (id: number | string) =>
  api(`/api/samples/${id}`);

/** GET /api/samples/:id/timeline — full event timeline from tat_log */
export const fetchSampleTimeline = (id: number | string) =>
  api(`/api/samples/${id}/timeline`);

// ─── Labs ─────────────────────────────────────────────────────────────────────

/** GET /api/labs — list all labs */
export const fetchAllLabs = () => api('/api/labs');

/** GET /api/labs/:id — single lab detail + queue depth */
export const fetchLab = (labId: number) => api(`/api/labs/${labId}`);

/**
 * GET /api/labs/:id/kpi — per-lab KPI metrics
 * Returns: total_tests, completed_tests, pending_tests, cancelled_tests,
 *          tat_breaches, avg_actual_tat_mins, avg_expected_tat_mins,
 *          sla_percent, pending_batches, missed_batches, queue_depth
 */
export const fetchLabKpi = (labId: number) => api(`/api/labs/${labId}/kpi`);

/** GET /api/labs/:id/queue — queue entries for a lab */
export const fetchLabQueue = (labId: number, limit = 50) =>
  api(`/api/labs/${labId}/queue?limit=${limit}`);

/** GET /api/labs/:id/batches — batch schedule + assignments for a lab */
export const fetchLabBatches = (labId: number, limit = 50) =>
  api(`/api/labs/${labId}/batches?limit=${limit}`);

// ─── Notifications / Audit log ────────────────────────────────────────────────

export interface AuditLogParams {
  sampleId?: number;
  limit?: number;
}

/** GET /api/notifications — global alert events or per-sample audit log */
export const fetchAuditLog = ({ sampleId, limit = 50 }: AuditLogParams = {}) => {
  const params = new URLSearchParams();
  if (sampleId) params.set('sample_id', String(sampleId));
  params.set('limit', String(limit));
  return api(`/api/notifications?${params.toString()}`);
};

/** GET /api/notifications/all — full system-wide audit log */
export const fetchAllAuditLogs = (limit = 50, offset = 0) =>
  api(`/api/notifications/all?limit=${limit}&offset=${offset}`);

// ─── Tests catalog ────────────────────────────────────────────────────────────

export interface TestsParams {
  q?: string;
  page?: number;
  limit?: number;
}

/** GET /api/tests — paginated EDOS test catalog */
export const fetchTests = ({ q, page = 1, limit = 25 }: TestsParams = {}) => {
  const params = new URLSearchParams();
  if (q) params.set('q', q);
  params.set('page', String(page));
  params.set('limit', String(limit));
  return api(`/api/tests?${params.toString()}`);
};

/** GET /api/catalog/master — full test definitions catalog */
export const fetchAllTests = () => api('/api/catalog/master');

/** GET /api/tests/:code — single test by code */
export const fetchTest = (testCode: string) =>
  api(`/api/tests/${testCode.toUpperCase()}`);

export interface TrackedTestsParams {
  q?: string;
  status?: string;
  limit?: number;
  offset?: number;
}

/** GET /api/v1/tests - joined test tracking feed */
export const fetchTrackedTests = ({
  q,
  status,
  limit = 20,
  offset = 0,
}: TrackedTestsParams = {}) => {
  const params = new URLSearchParams();
  if (q) params.set('q', q);
  if (status) params.set('status', status);
  params.set('limit', String(limit));
  params.set('offset', String(offset));
  return api(`/api/v1/tests?${params.toString()}`);
};

/** GET /api/v1/tests/:id - test detail with dynamic timeline */
export const fetchTrackedTestDetail = (testId: number | string) =>
  api(`/api/v1/tests/${testId}`);

// ─── Hot pipeline cache ───────────────────────────────────────────────────────

/** GET /api/pipeline/hot — Redis hot cache snapshot (newest samples first) */
export const fetchHotPipeline = (offset = 0, limit = 50) =>
  api(`/api/pipeline/hot?offset=${offset}&limit=${limit}`);

// ─── Logistics actions ────────────────────────────────────────────────────────

/** GET /api/logistics/pickup-queue — samples awaiting / in transit */
export const fetchPickupQueue = () => api('/api/logistics/pickup-queue');

/** POST /api/logistics/confirm-pickup — mark sample as in-transit */
export const confirmPickup = (sampleId: number) =>
  api('/api/logistics/confirm-pickup', {
    method: 'POST',
    body: JSON.stringify({ sample_id: sampleId }),
  });

/** POST /api/logistics/confirm-delivery — deliver to lab, fire SAMPLE_RECEIVED */
export const confirmDelivery = (sampleId: number, labId: number) =>
  api('/api/logistics/confirm-delivery', {
    method: 'POST',
    body: JSON.stringify({ sample_id: sampleId, lab_id: labId }),
  });

// ─── Lab workstation actions ──────────────────────────────────────────────────

/** GET /api/lab/:labId/work-queue — all pending tests assigned to a lab */
export const fetchLabWorkQueue = (labId: number) =>
  api(`/api/lab/${labId}/work-queue`);

/** POST /api/lab/confirm-receipt — lab confirms physical receipt, starts TAT */
export const confirmLabReceipt = (sampleId: number, labId: number) =>
  api('/api/lab/confirm-receipt', {
    method: 'POST',
    body: JSON.stringify({ sample_id: sampleId, lab_id: labId }),
  });

/** POST /api/lab/test-status — advance test to next status step */
export const updateTestStatus = (testInstanceId: number, status: string) =>
  api('/api/lab/test-status', {
    method: 'POST',
    body: JSON.stringify({ test_instance_id: testInstanceId, status }),
  });

/** POST /api/lab/submit-result — submit test result, fires REPORT_SUBMIT */
export const submitTestResult = (
  testInstanceId: number,
  sampleId: number,
  result: string,
) =>
  api('/api/lab/submit-result', {
    method: 'POST',
    body: JSON.stringify({ test_instance_id: testInstanceId, sample_id: sampleId, result }),
  });

/** Alias for submitTestResult used in legacy components */
export const submitResult = submitTestResult;

/** Alias for confirmLabReceipt used in legacy components */
export const markSampleReceived = confirmLabReceipt;

// ─── Admin actions ────────────────────────────────────────────────────────────

/**
 * POST /api/override/priority — override sample priority with audit reason
 */
export const adminChangePriority = (
  sampleId: number,
  priority: string,
  reason: string,
) =>
  api('/api/override/priority', {
    method: 'POST',
    body: JSON.stringify({ sample_id: sampleId, priority, reason }),
  });

/**
 * POST /api/admin/labs/:labId/availability — toggle lab ACTIVE / DOWN
 */
export const adminToggleLab = (
  labId: number,
  isActive: boolean,
  reason: string,
) =>
  api(`/api/admin/labs/${labId}/availability`, {
    method: 'POST',
    body: JSON.stringify({ is_active: isActive, reason }),
  });

/** GET /api/admin/unassigned — samples with no lab assigned */
export const fetchUnassignedSamples = () => api('/api/admin/unassigned');

/**
 * Admin routing override — re-routes a sample to a different lab.
 * Uses PATCH on /api/samples/:sampleId (or falls back to priority override API).
 * Adjust the endpoint below if a dedicated route is added later.
 */
export const adminOverrideRouting = (
  sampleId: number,
  newLabId: number,
  reason: string,
  testCode?: string,
) =>
  api('/api/override/routing', {
    method: 'POST',
    body: JSON.stringify({
      sample_id: sampleId,
      new_lab_id: newLabId,
      reason,
      ...(testCode ? { test_code: testCode } : {}),
    }),
  });

/**
 * POST /api/override/retry — enqueue a failed sample for re-processing
 */
export const adminRetry = (sampleId: number, reason: string) =>
  api('/api/override/retry', {
    method: 'POST',
    body: JSON.stringify({ sample_id: sampleId, reason }),
  });

// ─── Sample report (Doctor portal) ───────────────────────────────────────────

/** GET /api/samples/:id/report — consolidated lab report for a sample */
export const fetchSampleReport = (sampleId: number) =>
  api(`/api/samples/${sampleId}/report`);

/** GET /api/samples/:id/eta-history — ETA change audit trail */
export const fetchEtaHistory = (sampleId: number) =>
  api(`/api/samples/${sampleId}/eta-history`);

// ─── Dashboard aggregates ─────────────────────────────────────────────────────

/** GET /api/dashboard/admin — system-wide KPIs, labs, breaches, unassigned */
export const fetchAdminDashboard = () => api('/api/dashboard/admin');

/** GET /api/dashboard/admin/lab-metrics — overall system KPIs for ops center */
export const fetchLabManagementMetrics = () => api('/api/dashboard/admin/lab-metrics');

/** GET /api/dashboard/admin/labs — enhanced lab list with metrics and status */
export const fetchLabsWithMetrics = () => api('/api/dashboard/admin/labs');

/** GET /api/dashboard/lab — lab-scoped KPI + work queue for authenticated lab user */
export const fetchLabDashboard = () => api('/api/dashboard/lab');

/** GET /api/analytics/tests — per-test-type SLA analytics */
export const fetchTestAnalytics = () => api('/api/analytics/tests');

// ─── Lab EDOS management ──────────────────────────────────────────────────────

/**
 * GET /api/lab/edos — returns the lab's full EDOS catalog with processing times.
 * Response shape: { lab_id, lab_name, edos: EdosEntry[] }
 */
export const fetchLabEdos = () => api('/api/lab/edos');

export interface UpdateLabEdosPayload {
  test_code: string;
  processing_time_mins: number;
  committed_tat_hours?: number;
  is_active?: number; // 1 | 0
}

/**
 * POST /api/lab/edos/update — update processing time / TAT commitment for a test.
 */
export const updateLabEdos = (payload: UpdateLabEdosPayload) =>
  api('/api/lab/edos/update', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
