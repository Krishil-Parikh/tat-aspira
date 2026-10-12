"use client";
import React, { useState } from 'react';
import useSWR from 'swr';
import { motion } from 'motion/react';
import Link from 'next/link';
import {
  Settings, RefreshCw, Route, ShieldAlert, CheckCircle2, AlertTriangle,
  Activity, Power, ScrollText, History, List, TrendingUp, Clock,
  Gauge, Zap, Target, TrendingDown, BarChart3, Users, Timer, AlertCircle
} from 'lucide-react';
import {
  adminOverrideRouting, adminRetry, adminChangePriority, adminToggleLab,
  fetchAllLabs, fetchUnassignedSamples, fetchAuditLog, fetchSlaStats,
  fetchLabManagementMetrics, fetchLabsWithMetrics
} from '@/app/lib/api';
import { cn } from '@/components/ui/utils';
import KPICard from '@/components/dashboard/KPICard';
import LabMetricsTable from '@/components/dashboard/LabMetricsTable';

type Section = 'override' | 'labs' | 'unassigned' | 'audit' | 'sla';

export default function AdminPage() {
  const [activeSection, setActiveSection] = useState<Section>('override');
  const [loading, setLoading] = useState(false);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // Override form state
  const [sampleId, setSampleId]   = useState('');
  const [labId, setLabId]         = useState('');
  const [reason, setReason]       = useState('');
  const [testCode, setTestCode]   = useState('');
  const [priority, setPriority]   = useState('HIGH');

  // Lab toggle state
  const [labToggleId, setLabToggleId]       = useState('');
  const [labToggleReason, setLabToggleReason] = useState('');

  // SWR data
  const { data: labsData, mutate: mutateLabs } = useSWR('allLabs', fetchAllLabs, { refreshInterval: 15000 });
  const { data: unassignedData, mutate: mutateUnassigned } = useSWR('unassigned', fetchUnassignedSamples, { refreshInterval: 10000 });
  const { data: auditData } = useSWR('auditLog', () => fetchAuditLog({ limit: 50 }), { refreshInterval: 15000 });
  const { data: slaData } = useSWR('slaStats', fetchSlaStats, { refreshInterval: 20000 });
  
  // NEW: Lab metrics for dashboard
  const { data: metricsData, mutate: mutateMetrics } = useSWR(
    'labMetrics', 
    fetchLabManagementMetrics, 
    { refreshInterval: 30000 }
  );
  const { data: labsMetricsData, mutate: mutateLaborMetrics } = useSWR(
    'labsWithMetrics',
    fetchLabsWithMetrics,
    { refreshInterval: 30000 }
  );

  const labs      = labsData?.labs || [];
  const unassigned = unassignedData?.unassigned || [];
  const auditLogs  = auditData?.notifications || [];
  const slaStats   = slaData?.sla_by_client_type || [];
  
  // NEW: Extract metrics and labs with enhanced data
  const metrics = metricsData?.metrics || null;
  const labsWithMetrics = labsMetricsData?.labs || [];


  const doAction = async (fn: () => Promise<any>, successMsg: string) => {
    setLoading(true);
    setFeedback(null);
    try {
      await fn();
      setFeedback({ type: 'success', message: successMsg });
    } catch (e: any) {
      setFeedback({ type: 'error', message: e.message || 'Action failed' });
    } finally {
      setLoading(false);
    }
  };

  const handleOverride = (e: React.FormEvent) => {
    e.preventDefault();
    doAction(
      () => adminOverrideRouting(+sampleId, +labId, reason, testCode || undefined),
      'Routing override applied. ETA recalculation pending.'
    );
  };

  const handlePriority = (e: React.FormEvent) => {
    e.preventDefault();
    doAction(
      () => adminChangePriority(+sampleId, priority, reason),
      `Priority changed to ${priority}.`
    );
  };

  const handleRetry = () => {
    if (!sampleId || !reason) {
      setFeedback({ type: 'error', message: 'Sample ID and Reason required for retry.' });
      return;
    }
    doAction(() => adminRetry(+sampleId, reason), 'Retry enqueued.');
  };

  const handleLabToggle = (active: boolean) => {
    if (!labToggleId || !labToggleReason) {
      setFeedback({ type: 'error', message: 'Lab ID and reason are required.' });
      return;
    }
    doAction(async () => {
      await adminToggleLab(+labToggleId, active, labToggleReason);
      mutateLabs();
    }, `Lab ${labToggleId} set to ${active ? 'ACTIVE' : 'DOWN'}.`);
  };

  const sectionNav: { key: Section; label: string; icon: any }[] = [
    { key: 'override',    label: 'Routing & Priority',  icon: Route },
    { key: 'labs',        label: 'Lab Management',      icon: Power },
    { key: 'unassigned',  label: 'Unassigned Queue',    icon: AlertTriangle },
    { key: 'audit',       label: 'Audit Log',           icon: ScrollText },
    { key: 'sla',         label: 'SLA Report',          icon: TrendingUp },
  ];

  return (
    <div className="space-y-6 pb-20">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2 mb-2">
          <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
          <span className="text-[10px] font-black text-muted uppercase tracking-widest">System Control</span>
        </div>
        <h1 className="text-5xl font-black text-foreground tracking-tighter leading-none mb-2">ADMIN CONTROLS</h1>
        <p className="text-muted font-medium max-w-lg">Full operational control. All actions are audited.</p>
      </div>

      {/* Feedback */}
      {feedback && (
        <motion.div
          initial={{ opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
          className={cn("p-4 rounded-xl border flex items-center gap-3",
            feedback.type === 'success'
              ? 'bg-success/10 border-success/30 text-success-text'
              : 'bg-red-400/10 border-red-400/30 text-red-400'
          )}
        >
          {feedback.type === 'success' ? <CheckCircle2 size={18} /> : <AlertTriangle size={18} />}
          <span className="font-bold text-sm uppercase tracking-widest">{feedback.message}</span>
        </motion.div>
      )}

      {/* Section nav tabs */}
      <div className="flex gap-2 flex-wrap">
        {sectionNav.map(s => (
          <button
            key={s.key}
            onClick={() => setActiveSection(s.key)}
            className={cn(
              "flex items-center gap-2 px-4 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all border",
              activeSection === s.key
                ? "bg-primary text-white border-primary shadow-lg shadow-primary/20"
                : "bg-surface-low text-muted border-border-ghost hover:text-foreground"
            )}
          >
            <s.icon size={14} />
            {s.label}
          </button>
        ))}
      </div>

      {/* ── Section: Routing Override + Priority + Retry ── */}
      {activeSection === 'override' && (
        <div className="grid md:grid-cols-2 gap-6">
          {/* Routing Override */}
          <div className="bg-surface-lowest rounded-3xl border border-border-ghost p-8">
            <div className="flex items-center gap-3 mb-6">
              <Route className="text-primary" size={20} />
              <h2 className="text-lg font-headline font-black uppercase tracking-widest">Force Routing</h2>
            </div>
            <form onSubmit={handleOverride} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-[9px] font-black uppercase tracking-widest text-muted mb-1">Sample ID</label>
                  <input required type="number" value={sampleId} onChange={e => setSampleId(e.target.value)}
                    className="w-full bg-surface-low border-none rounded-xl py-3 px-4 font-technical font-black text-foreground focus:ring-2 focus:ring-primary outline-none" placeholder="e.g. 1045" />
                </div>
                <div>
                  <label className="block text-[9px] font-black uppercase tracking-widest text-muted mb-1">New Lab ID</label>
                  <input required type="number" value={labId} onChange={e => setLabId(e.target.value)}
                    className="w-full bg-surface-low border-none rounded-xl py-3 px-4 font-technical font-black text-foreground focus:ring-2 focus:ring-primary outline-none" placeholder="e.g. 3" />
                </div>
              </div>
              <div>
                <label className="block text-[9px] font-black uppercase tracking-widest text-muted mb-1">Test Code (optional)</label>
                <input type="text" value={testCode} onChange={e => setTestCode(e.target.value)}
                  className="w-full bg-surface-low border-none rounded-xl py-3 px-4 font-technical font-black text-foreground focus:ring-2 focus:ring-primary outline-none" placeholder="CBC001 (leave blank for all tests)" />
              </div>
              <div>
                <label className="block text-[9px] font-black uppercase tracking-widest text-muted mb-1">Audit Reason *</label>
                <input required type="text" value={reason} onChange={e => setReason(e.target.value)}
                  className="w-full bg-surface-low border-none rounded-xl py-3 px-4 font-technical font-black text-foreground focus:ring-2 focus:ring-primary outline-none" placeholder="Why are you overriding?" />
              </div>
              <div className="flex gap-3 pt-2">
                <button type="submit" disabled={loading}
                  className="flex-1 bg-primary text-white py-3.5 rounded-xl font-black text-[10px] uppercase tracking-widest hover:opacity-90 disabled:opacity-50 flex items-center justify-center gap-2">
                  <ShieldAlert size={16} /> Force Route
                </button>
                <button type="button" onClick={handleRetry} disabled={loading}
                  className="flex-1 bg-surface-low text-foreground py-3.5 rounded-xl font-black text-[10px] uppercase tracking-widest border hover:bg-surface-high disabled:opacity-50 flex items-center justify-center gap-2">
                  <RefreshCw size={16} /> Retry Processing
                </button>
              </div>
            </form>
          </div>

          {/* Priority Override */}
          <div className="bg-surface-lowest rounded-3xl border border-border-ghost p-8">
            <div className="flex items-center gap-3 mb-6">
              <Activity className="text-amber-500" size={20} />
              <h2 className="text-lg font-headline font-black uppercase tracking-widest">Change Priority</h2>
            </div>
            <form onSubmit={handlePriority} className="space-y-4">
              <div>
                <label className="block text-[9px] font-black uppercase tracking-widest text-muted mb-1">Sample ID</label>
                <input required type="number" value={sampleId} onChange={e => setSampleId(e.target.value)}
                  className="w-full bg-surface-low border-none rounded-xl py-3 px-4 font-technical font-black text-foreground focus:ring-2 focus:ring-primary outline-none" placeholder="e.g. 1045" />
              </div>
              <div>
                <label className="block text-[9px] font-black uppercase tracking-widest text-muted mb-1">New Priority</label>
                <select value={priority} onChange={e => setPriority(e.target.value)}
                  className="w-full bg-surface-low border-none rounded-xl py-3 px-4 font-technical font-black text-foreground focus:ring-2 focus:ring-primary outline-none">
                  <option value="URGENT">URGENT</option>
                  <option value="HIGH">HIGH</option>
                  <option value="NORMAL">NORMAL</option>
                  <option value="LOW">LOW</option>
                </select>
              </div>
              <div>
                <label className="block text-[9px] font-black uppercase tracking-widest text-muted mb-1">Audit Reason *</label>
                <input required type="text" value={reason} onChange={e => setReason(e.target.value)}
                  className="w-full bg-surface-low border-none rounded-xl py-3 px-4 font-technical font-black text-foreground focus:ring-2 focus:ring-primary outline-none" placeholder="Why are you changing priority?" />
              </div>
              <button type="submit" disabled={loading}
                className="w-full bg-amber-500 text-white py-3.5 rounded-xl font-black text-[10px] uppercase tracking-widest hover:opacity-90 disabled:opacity-50 flex items-center justify-center gap-2">
                <ShieldAlert size={16} /> Apply Priority Override
              </button>
            </form>
          </div>
        </div>
      )}

      {/* ── Section: Lab Management ── */}
      {activeSection === 'labs' && (
        <div className="space-y-8">
          {/* KPI Metrics Section */}
          <div className="space-y-4">
            {!metricsData ? (
              <div className="bg-surface-lowest rounded-3xl border border-border-ghost p-8">
                <div className="flex items-center gap-3 mb-4">
                  <Gauge className="text-primary animate-spin" size={20} />
                  <h2 className="text-lg font-headline font-black uppercase tracking-widest">Overall System KPIs</h2>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {Array.from({ length: 9 }).map((_, i) => (
                    <div key={i} className="h-32 bg-surface-low rounded-2xl animate-pulse" />
                  ))}
                </div>
              </div>
            ) : metrics ? (
              <>
                <div>
                  <div className="flex items-center gap-2 mb-4">
                    <Gauge className="text-primary" size={20} />
                    <h2 className="text-lg font-headline font-black uppercase tracking-widest">Overall System KPIs</h2>
                  </div>
                  <p className="text-[10px] text-muted font-bold mb-4">Real-time operations control metrics</p>
                </div>

                {/* First Row: 3 KPIs */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <KPICard
                    title="Total Active Labs"
                    value={metrics.total_active_labs}
                    unit="labs"
                    icon={Users}
                    color="success"
                    description="Labs currently available"
                  />
                  <KPICard
                    title="Total Tests Today"
                    value={metrics.total_tests_today}
                    unit="tests"
                    icon={BarChart3}
                    color="primary"
                    description="Tests created today"
                  />
                  <KPICard
                    title="Total In Progress"
                    value={metrics.total_in_progress}
                    unit="tests"
                    icon={Activity}
                    color="info"
                    description="Pending/Processing status"
                  />
                </div>

                {/* Second Row: 3 KPIs */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <KPICard
                    title="Completed Today"
                    value={metrics.total_completed_today}
                    unit="tests"
                    icon={CheckCircle2}
                    color="success"
                    description="Successfully completed"
                  />
                  <KPICard
                    title="Delayed Tests"
                    value={metrics.delayed_tests}
                    unit="tests"
                    icon={AlertCircle}
                    color={metrics.delayed_tests > 0 ? 'danger' : 'success'}
                    description="TAT breached"
                  />
                  <KPICard
                    title="SLA Compliance"
                    value={metrics.sla_compliance_percent}
                    unit="%"
                    icon={Target}
                    color={metrics.sla_compliance_percent > 90 ? 'success' : 'warning'}
                    description="On-time completion rate"
                  />
                </div>

                {/* Third Row: 3 KPIs */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <KPICard
                    title="Avg Processing TAT"
                    value={metrics.avg_processing_tat_mins}
                    unit="mins"
                    icon={Timer}
                    color="primary"
                    description="Average actual TAT"
                    isTimeFormat={true}
                  />
                  <KPICard
                    title="Queue Load"
                    value={metrics.queue_load}
                    unit="entries"
                    icon={Zap}
                    color={metrics.queue_load > 20 ? 'warning' : 'primary'}
                    description="Active queue entries"
                  />
                  <KPICard
                    title="Avg Queue Wait"
                    value={metrics.avg_queue_wait_mins}
                    unit="mins"
                    icon={Clock}
                    color="primary"
                    description="Average wait time"
                    isTimeFormat={true}
                  />
                </div>
              </>
            ) : null}
          </div>

          {/* Enhanced Lab Metrics Table */}
          <div className="pt-4">
            <div className="flex items-center gap-2 mb-4">
              <Power className="text-primary" size={20} />
              <h2 className="text-lg font-headline font-black uppercase tracking-widest">Lab Performance Metrics</h2>
              <span className="ml-auto px-3 py-1 rounded-full bg-primary/10 text-primary text-[10px] font-black">
                {labsWithMetrics.length} labs
              </span>
            </div>
          </div>

          <LabMetricsTable
            labs={labsWithMetrics}
            loading={!labsMetricsData}
            onLabClick={(labId) => {
              // Could open a modal or navigate to lab details
            }}
          />

          {/* Lab Availability Toggle */}
          <div className="bg-surface-lowest rounded-3xl border border-border-ghost p-8">
            <div className="flex items-center gap-3 mb-6">
              <Power className="text-red-500" size={20} />
              <h2 className="text-lg font-headline font-black uppercase tracking-widest">Toggle Lab Availability</h2>
            </div>
            <div className="grid grid-cols-2 gap-4 mb-4">
              <div>
                <label className="block text-[9px] font-black uppercase tracking-widest text-muted mb-1">Lab ID</label>
                <input type="number" value={labToggleId} onChange={e => setLabToggleId(e.target.value)}
                  className="w-full bg-surface-low border-none rounded-xl py-3 px-4 font-technical font-black text-foreground focus:ring-2 focus:ring-primary outline-none" placeholder="e.g. 2" />
              </div>
              <div>
                <label className="block text-[9px] font-black uppercase tracking-widest text-muted mb-1">Audit Reason *</label>
                <input type="text" value={labToggleReason} onChange={e => setLabToggleReason(e.target.value)}
                  className="w-full bg-surface-low border-none rounded-xl py-3 px-4 font-technical font-black text-foreground focus:ring-2 focus:ring-primary outline-none" placeholder="Reason for status change" />
              </div>
            </div>
            <div className="flex gap-3">
              <button onClick={() => handleLabToggle(true)} disabled={loading}
                className="flex-1 bg-success/10 border border-success/30 text-success-text py-3.5 rounded-xl font-black text-[10px] uppercase tracking-widest hover:bg-success/20 disabled:opacity-50 flex items-center justify-center gap-2">
                <CheckCircle2 size={14} /> Set ACTIVE
              </button>
              <button onClick={() => handleLabToggle(false)} disabled={loading}
                className="flex-1 bg-red-400/10 border border-red-400/30 text-red-400 py-3.5 rounded-xl font-black text-[10px] uppercase tracking-widest hover:bg-red-400/20 disabled:opacity-50 flex items-center justify-center gap-2">
                <Power size={14} /> Set DOWN
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Section: Unassigned Queue ── */}
      {activeSection === 'unassigned' && (
        <div className="bg-surface-lowest rounded-3xl border border-border-ghost overflow-hidden">
          <div className="px-8 py-6 border-b border-border-ghost flex items-center gap-3">
            <AlertTriangle className="text-amber-500" size={20} />
            <h2 className="text-lg font-headline font-black uppercase tracking-widest">Unassigned Samples</h2>
            <span className="ml-auto px-3 py-1 rounded-full bg-amber-500/10 text-amber-500 text-[10px] font-black">{unassigned.length} items</span>
          </div>
          {unassigned.length === 0 ? (
            <div className="text-center py-16">
              <CheckCircle2 size={36} className="text-success-text mx-auto mb-3 opacity-40" />
              <p className="text-[10px] font-black text-muted uppercase tracking-widest">No unassigned samples</p>
            </div>
          ) : (
            <div className="divide-y divide-border-ghost">
              {unassigned.map((s: any) => (
                <div key={s.id} className="px-8 py-5 flex items-center justify-between gap-4">
                  <div>
                    <p className="font-technical font-black text-foreground">{s.accession_no || `#${s.id}`}</p>
                    <p className="text-[10px] text-muted">{s.patient_name} · Bill #{s.external_bill_id}</p>
                    <p className="text-[9px] text-amber-500 font-black mt-1">
                      Unassigned tests: {(s.unassigned_tests || []).join(', ')}
                    </p>
                  </div>
                  <span className="px-4 py-2 bg-surface-low border border-border-ghost text-muted rounded-xl text-[9px] font-black uppercase">
                    Needs Routing
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Section: Audit Log ── */}
      {activeSection === 'audit' && (
        <div className="bg-surface-lowest rounded-3xl border border-border-ghost overflow-hidden">
          <div className="px-8 py-6 border-b border-border-ghost flex items-center gap-3">
            <ScrollText className="text-primary" size={20} />
            <h2 className="text-lg font-headline font-black uppercase tracking-widest">Audit Log</h2>
          </div>
          <div className="divide-y divide-border-ghost max-h-150 overflow-y-auto">
            {auditLogs.length === 0 ? (
              <div className="text-center py-16">
                <p className="text-[10px] font-black text-muted uppercase tracking-widest">No audit events</p>
              </div>
            ) : auditLogs.map((log: any, i: number) => (
              <div key={i} className="px-8 py-4 flex items-start gap-4">
                <div className="w-2 h-2 rounded-full bg-primary mt-2 shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-3 flex-wrap mb-0.5">
                    <span className="px-2 py-0.5 rounded bg-surface-high text-[9px] font-black uppercase text-muted">{log.event_type}</span>
                    {log.sample_id && <span className="text-[9px] text-muted">Sample #{log.sample_id}</span>}
                  </div>
                  <p className="text-sm font-medium text-foreground">{log.notes || log.message || '—'}</p>
                </div>
                <p className="text-[9px] text-muted font-bold shrink-0">
                  {log.event_timestamp ? new Date(log.event_timestamp).toLocaleString() : '—'}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Section: SLA Report ── */}
      {activeSection === 'sla' && (
        <div className="bg-surface-lowest rounded-3xl border border-border-ghost overflow-hidden">
          <div className="px-8 py-6 border-b border-border-ghost flex items-center gap-3">
            <TrendingUp className="text-primary" size={20} />
            <h2 className="text-lg font-headline font-black uppercase tracking-widest">SLA Compliance Report</h2>
          </div>
          {slaStats.length === 0 ? (
            <div className="text-center py-16">
              <p className="text-[10px] font-black text-muted uppercase tracking-widest">No SLA data yet</p>
            </div>
          ) : (
            <div className="p-8 grid md:grid-cols-3 gap-6">
              {slaStats.map((row: any) => {
                const compliance = row.total > 0 ? Math.round(((row.total - row.breached) / row.total) * 100) : 100;
                return (
                  <div key={row.client_type} className="bg-surface-low rounded-2xl p-6">
                    <p className="text-[9px] font-black text-muted uppercase tracking-widest mb-2">{row.client_type}</p>
                    <p className={cn("text-4xl font-black font-technical", compliance >= 90 ? 'text-success-text' : compliance >= 70 ? 'text-amber-500' : 'text-red-500')}>
                      {compliance}%
                    </p>
                    <p className="text-[10px] text-muted mt-2">{row.total} samples · {row.breached} breached</p>
                    <div className="w-full bg-surface-high rounded-full h-2 mt-3 overflow-hidden">
                      <div className={cn("h-full rounded-full", compliance >= 90 ? 'bg-success-bg' : compliance >= 70 ? 'bg-amber-500' : 'bg-red-500')} style={{ width: `${compliance}%` }} />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
