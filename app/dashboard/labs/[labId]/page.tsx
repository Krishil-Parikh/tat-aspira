"use client";
import React from 'react';
import useSWR from 'swr';
import { useParams, useRouter } from 'next/navigation';
import { motion } from 'motion/react';
import Link from 'next/link';
import {
  ArrowLeft, FlaskConical, Clock, ShieldCheck, Layers, Activity,
  RefreshCw, AlertCircle, CheckCircle2, BarChart3, ChevronRight
} from 'lucide-react';
import { fetchLabKpi, fetchLabWorkQueue } from '@/app/lib/api';
import { cn } from '@/components/ui/utils';

// ── Metric row ────────────────────────────────────────────────────────────────
function MetricRow({ label, value, icon: Icon, color }: { label: string; value: string | number; icon?: any; color?: string }) {
  return (
    <div className="flex items-center justify-between py-4 border-b border-border-ghost/50 last:border-0">
      <div className="flex items-center gap-3">
        {Icon && <Icon size={14} className="text-muted" />}
        <span className="text-[10px] font-black uppercase tracking-widest text-muted">{label}</span>
      </div>
      <span className={cn("text-sm font-black font-technical", color || "text-foreground")}>{value}</span>
    </div>
  );
}

export default function LabDetailPage() {
  const params = useParams();
  const labId = Number(params?.labId);
  const router = useRouter();

  const { data: kpi, isLoading: kpiLoading, error, mutate } = useSWR(
    labId ? `kpi-detail-${labId}` : null,
    () => fetchLabKpi(labId),
    { refreshInterval: 15000 }
  );

  const { data: queueData, isLoading: queueLoading } = useSWR(
    labId ? `work-queue-detail-${labId}` : null,
    () => fetchLabWorkQueue(labId),
    { refreshInterval: 10000 }
  );

  const workItems: any[] = queueData?.work_items || [];

  const sla = kpi?.sla_percent ?? 100;
  const slaColor = sla >= 90 ? 'text-emerald-400' : sla >= 70 ? 'text-amber-400' : 'text-red-400';
  const barColor = sla >= 90 ? 'bg-emerald-400' : sla >= 70 ? 'bg-amber-400' : 'bg-red-400';

  if (kpiLoading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] space-y-6">
        <div className="w-12 h-12 border-4 border-primary border-t-transparent rounded-full animate-spin" />
        <p className="text-[10px] font-black text-muted uppercase tracking-[0.3em]">Loading Lab Detail...</p>
      </div>
    );
  }

  if (error || !kpi) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] space-y-4">
        <AlertCircle size={36} className="text-red-400 opacity-60" />
        <p className="text-[10px] font-black text-muted uppercase tracking-[0.3em]">Lab {labId} not found</p>
        <Link href="/dashboard/labs">
          <button className="px-4 py-2 bg-surface-low border border-border-ghost rounded-xl text-[10px] font-black uppercase tracking-widest text-muted hover:text-foreground transition-all flex items-center gap-2">
            <ArrowLeft size={12} /> Back to Labs
          </button>
        </Link>
      </div>
    );
  }

  // Derived: delayed = TAT breaches (samples where actual > expected)
  const delayed = kpi.tat_breaches ?? 0;
  const successRate = kpi.total_tests > 0
    ? Math.round(((kpi.completed_tests - delayed) / kpi.total_tests) * 100)
    : 100;

  return (
    <div className="space-y-8 pb-20">
      {/* Back nav */}
      <Link href="/dashboard/labs" className="inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-muted hover:text-primary transition-all">
        <ArrowLeft size={12} /> All Labs
      </Link>

      {/* Header */}
      <div className="flex items-end justify-between flex-wrap gap-4">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <div className={cn("w-2 h-2 rounded-full", kpi.is_available ? "bg-success animate-pulse" : "bg-red-400")} />
            <span className="text-[10px] font-black text-muted uppercase tracking-widest">
              {kpi.lab_code} · {kpi.is_available ? 'ONLINE' : 'OFFLINE'}
            </span>
          </div>
          <h1 className="text-4xl font-black text-foreground tracking-tighter leading-none">{kpi.lab_name}</h1>
        </div>
        <button onClick={() => mutate()} className="flex items-center gap-2 px-4 py-2.5 bg-surface-low border border-border-ghost rounded-xl text-[10px] font-black uppercase tracking-widest text-muted hover:text-foreground transition-all">
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      {/* KPI overview grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Total Tests',  value: kpi.total_tests,     color: '',                icon: Layers },
          { label: 'Completed',    value: kpi.completed_tests,  color: 'text-success-text', icon: CheckCircle2 },
          { label: 'Delayed',      value: delayed,              color: delayed > 0 ? 'text-red-400' : '', icon: AlertCircle },
          { label: 'Success Rate', value: `${successRate}%`,   color: successRate >= 90 ? 'text-success-text' : 'text-amber-500', icon: ShieldCheck },
        ].map((m, i) => (
          <motion.div
            key={m.label}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.07 }}
            className="bg-surface-lowest rounded-2xl border border-border-ghost p-6"
          >
            <div className="flex items-center gap-2 mb-3">
              <m.icon size={14} className="text-muted" />
              <p className="text-[9px] font-black uppercase tracking-widest text-muted">{m.label}</p>
            </div>
            <p className={cn("text-3xl font-black font-technical", m.color || "text-foreground")}>{m.value}</p>
          </motion.div>
        ))}
      </div>

      {/* Detailed metrics + SLA */}
      <div className="grid md:grid-cols-2 gap-6">
        {/* Metrics */}
        <div className="bg-surface-lowest rounded-3xl border border-border-ghost p-8">
          <div className="flex items-center gap-3 mb-6">
            <BarChart3 size={18} className="text-primary" />
            <h2 className="text-sm font-headline font-black uppercase tracking-widest">Lab Metrics</h2>
          </div>
          <MetricRow label="Queue Depth"          value={`${kpi.queue_depth ?? 0} samples`}  icon={Layers} />
          <MetricRow label="Pending Batches"      value={kpi.pending_batches ?? 0}            icon={Clock} />
          <MetricRow label="Missed Batches"       value={kpi.missed_batches ?? 0} color={kpi.missed_batches > 0 ? 'text-amber-500' : ''} icon={AlertCircle} />
          <MetricRow label="Avg Expected TAT"     value={kpi.avg_expected_tat_mins ? `${Math.round(kpi.avg_expected_tat_mins)} min` : '—'} icon={Clock} />
          <MetricRow label="Avg Actual TAT"       value={kpi.avg_actual_tat_mins  ? `${Math.round(kpi.avg_actual_tat_mins)} min`  : '—'} icon={Clock} />
          <MetricRow label="Samples with ETA"    value={kpi.samples_with_eta ?? 0}           icon={Activity} />
        </div>

        {/* SLA panel */}
        <div className="bg-foreground rounded-3xl p-8 text-white relative overflow-hidden">
          <h2 className="text-[10px] font-black text-white/40 uppercase tracking-[0.3em] mb-6">SLA Compliance</h2>
          <motion.div
            initial={{ scale: 0.7, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ type: 'spring', bounce: 0.4 }}
            className={cn("text-7xl font-headline font-black mb-2 leading-none", slaColor)}
          >
            {sla}%
          </motion.div>
          <p className="text-sm text-white/50 mb-6">
            {kpi.tat_breaches ?? 0} breaches out of {kpi.samples_with_eta ?? 0} samples with ETA
          </p>
          {/* Progress bar */}
          <div className="w-full bg-white/10 h-3 rounded-full overflow-hidden">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${sla}%` }}
              transition={{ delay: 0.4, duration: 1, ease: 'easeOut' }}
              className={cn("h-full rounded-full", barColor)}
            />
          </div>
          <Activity className="absolute bottom-[-10px] left-[-20px] text-white/5 w-40 h-40" />
        </div>
      </div>

      {/* Active Work Queue */}
      <div className="bg-surface-lowest rounded-3xl border border-border-ghost overflow-hidden">
        <div className="px-8 py-5 border-b border-border-ghost flex items-center justify-between">
          <div className="flex items-center gap-3">
            <FlaskConical size={16} className="text-primary" />
            <h2 className="text-sm font-headline font-black uppercase tracking-widest">Active Work Queue</h2>
          </div>
          <span className="px-3 py-1 rounded-full bg-primary/10 text-primary text-[9px] font-black">
            {queueLoading ? '...' : workItems.length} items
          </span>
        </div>
        {queueLoading ? (
          <div className="flex items-center justify-center py-12">
            <RefreshCw size={20} className="animate-spin text-muted" />
          </div>
        ) : workItems.length === 0 ? (
          <div className="text-center py-16">
            <CheckCircle2 size={36} className="text-success-text mx-auto mb-3 opacity-40" />
            <p className="text-[10px] font-black text-muted uppercase tracking-widest">Queue clear</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="bg-surface-low/40 border-b border-border-ghost/30">
                  {['Accession', 'Patient', 'Test', 'Status', 'ETA'].map(h => (
                    <th key={h} className="px-6 py-4 text-[9px] font-black text-muted uppercase tracking-[0.2em]">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border-ghost/10">
                {workItems.slice(0, 20).map((item: any, i: number) => (
                  <tr key={`${item.sample_id}-${item.test_instance_id}-${i}`} className="hover:bg-surface-low/20 transition-colors">
                    <td className="px-6 py-4 font-technical text-sm font-black text-foreground uppercase">
                      {item.accession_no || `#${item.sample_id}`}
                    </td>
                    <td className="px-6 py-4 text-xs text-muted font-medium">{item.patient_name || '—'}</td>
                    <td className="px-6 py-4 text-xs font-black text-foreground">{item.test_code || item.test_name || '—'}</td>
                    <td className="px-6 py-4">
                      <span className={cn(
                        "px-2.5 py-1 rounded-full text-[9px] font-black uppercase tracking-widest border",
                        item.test_status === 'completed'  ? "bg-success/10 border-success/30 text-success-text" :
                        item.test_status === 'processing' ? "bg-primary/10 border-primary/30 text-primary" :
                        "bg-surface-low border-border-ghost text-muted"
                      )}>
                        {(item.test_status || 'pending').replace(/_/g, ' ')}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-[10px] font-black text-muted">
                      {item.estimated_end_time
                        ? new Date(item.estimated_end_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                        : '—'}
                      {item.is_tat_breached ? <span className="ml-2 text-red-400">⚠</span> : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
