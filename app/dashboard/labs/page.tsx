"use client";
import React, { useEffect, useState } from 'react';
import useSWR from 'swr';
import { motion } from 'motion/react';
import Link from 'next/link';
import {
  Activity, Clock, ShieldCheck, AlertCircle, ChevronRight,
  FlaskConical, RefreshCw, TrendingUp, Layers, CheckCircle2,
  BarChart3
} from 'lucide-react';
import { fetchAllLabs, fetchLabKpi } from '@/app/lib/api';
import { cn } from '@/components/ui/utils';

// ── Root-cause fixed: was using hardcoded http://127.0.0.1:8000 with no auth cookies.
// Now uses fetchAllLabs() + fetchLabKpi() from api.ts which:
//  1. Routes through Next.js proxy (/api/...) so cookies are same-origin
//  2. Includes credentials: 'include' for session auth
// ──────────────────────────────────────────────────────────────────────────────

function getRole(): string {
  if (typeof document === 'undefined') return 'admin';
  const cookies = document.cookie.split('; ');
  return cookies.find(c => c.startsWith('aspira_role='))?.split('=')[1]?.toLowerCase() || 'admin';
}
function getLabId(): number | null {
  if (typeof document === 'undefined') return null;
  const cookies = document.cookie.split('; ');
  const v = cookies.find(c => c.startsWith('aspira_lab_id='))?.split('=')[1];
  return v ? parseInt(v) : null;
}

// ── KPI card component ────────────────────────────────────────────────────────
function KpiCard({ label, value, sub, color }: { label: string; value: string | number; sub?: string; color?: string }) {
  return (
    <div>
      <p className="text-[9px] font-black uppercase tracking-widest text-muted mb-1">{label}</p>
      <p className={cn("text-2xl font-technical font-black", color || "text-foreground")}>
        {value}
        {sub && <span className="text-sm font-bold ml-0.5">{sub}</span>}
      </p>
    </div>
  );
}

// ── Per-lab card (fetches its own KPI) ───────────────────────────────────────
function LabCard({ lab, index }: { lab: any; index: number }) {
  const { data: kpi, isLoading: kpiLoading } = useSWR(
    `kpi-${lab.id}`,
    () => fetchLabKpi(lab.id),
    { refreshInterval: 20000 }
  );

  const sla = kpi?.sla_percent ?? 100;
  const slaColor = sla >= 90 ? 'text-success-text' : sla >= 70 ? 'text-amber-500' : 'text-red-400';
  const barColor = sla >= 90 ? 'bg-success' : sla >= 70 ? 'bg-amber-500' : 'bg-red-400';

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.07 }}
      className="bg-surface-lowest rounded-[2rem] border border-border-ghost overflow-hidden group hover:border-primary/40 hover:shadow-lg hover:shadow-primary/5 transition-all flex flex-col"
    >
      {/* Header */}
      <div className="p-6 border-b border-surface-low">
        <div className="flex items-center justify-between mb-4">
          <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center text-primary">
            <FlaskConical size={20} />
          </div>
          <div className="flex items-center gap-2">
            <span className={cn(
              "px-2.5 py-1 rounded-full text-[9px] font-black uppercase tracking-widest border",
              lab.is_available
                ? "bg-success/10 border-success/30 text-success-text"
                : "bg-red-400/10 border-red-400/30 text-red-400"
            )}>
              {lab.is_available ? 'ONLINE' : 'OFFLINE'}
            </span>
            {lab.is_fallback ? (
              <span className="px-2.5 py-1 rounded-full text-[9px] font-black uppercase tracking-widest border bg-amber-500/10 border-amber-500/30 text-amber-500">
                FALLBACK
              </span>
            ) : null}
          </div>
        </div>
        <h2 className="text-lg font-headline font-black text-foreground uppercase leading-tight">{lab.lab_name}</h2>
        <p className="text-[10px] font-black uppercase tracking-widest text-muted mt-1">{lab.lab_code} · {lab.processing_mode === 'max' ? 'Parallel' : 'Sequential'} Mode</p>
      </div>

      {/* KPI Grid */}
      <div className="p-6 grid grid-cols-2 gap-5 flex-1">
        {kpiLoading ? (
          <div className="col-span-2 flex items-center justify-center py-4">
            <RefreshCw size={16} className="animate-spin text-muted" />
          </div>
        ) : (
          <>
            <KpiCard label="Total Tests"  value={kpi?.total_tests ?? lab.queue_depth ?? 0} />
            <KpiCard label="Completed"    value={kpi?.completed_tests ?? 0} color="text-success-text" />
            <KpiCard label="Pending"      value={kpi?.pending_tests ?? 0} color="text-amber-500" />
            <KpiCard label="TAT Breaches" value={kpi?.tat_breaches ?? 0}  color={kpi?.tat_breaches > 0 ? 'text-red-400' : 'text-foreground'} />

            {/* SLA Bar */}
            <div className="col-span-2">
              <div className="flex items-center justify-between mb-2">
                <p className="text-[9px] font-black uppercase tracking-widest text-muted">SLA Compliance</p>
                <p className={cn("text-sm font-black font-technical", slaColor)}>{sla}%</p>
              </div>
              <div className="w-full bg-surface-low h-2 rounded-full overflow-hidden">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${sla}%` }}
                  transition={{ delay: index * 0.07 + 0.4, duration: 0.8, ease: 'easeOut' }}
                  className={cn("h-full rounded-full", barColor)}
                />
              </div>
            </div>

            {/* Avg TAT */}
            <div className="col-span-2 flex items-center justify-between pt-1 border-t border-border-ghost/50">
              <div className="flex items-center gap-2 text-muted">
                <Clock size={12} />
                <span className="text-[9px] font-black uppercase tracking-widest">Avg TAT</span>
              </div>
              <span className="text-[10px] font-black font-technical text-foreground">
                {kpi?.avg_actual_tat_mins ? `${Math.round(kpi.avg_actual_tat_mins)} min` : '—'}
              </span>
            </div>

            {/* Queue depth */}
            <div className="col-span-2 flex items-center justify-between">
              <div className="flex items-center gap-2 text-muted">
                <Layers size={12} />
                <span className="text-[9px] font-black uppercase tracking-widest">Queue / Batches</span>
              </div>
              <span className="text-[10px] font-black font-technical text-foreground">
                {kpi?.queue_depth ?? lab.queue_depth ?? 0} / {kpi?.pending_batches ?? lab.pending_batches ?? 0}
              </span>
            </div>
          </>
        )}
      </div>

      {/* Footer link → lab detail */}
      <Link href={`/dashboard/labs/${lab.id}`} className="block">
        <div className="px-6 py-4 border-t border-border-ghost flex items-center justify-between text-muted hover:text-primary hover:bg-primary/5 transition-all">
          <span className="text-[9px] font-black uppercase tracking-widest">View Detail</span>
          <ChevronRight size={14} className="group-hover:translate-x-1 transition-transform" />
        </div>
      </Link>
    </motion.div>
  );
}

// ── Main Labs page ────────────────────────────────────────────────────────────
export default function LabsPage() {
  const [mounted, setMounted] = useState(false);
  const [role, setRole] = useState<string>('admin');
  const [sessionLabId, setSessionLabId] = useState<number | null>(null);

  useEffect(() => {
    setMounted(true);
    setRole(getRole());
    setSessionLabId(getLabId());
  }, []);

  const { data: labsData, isLoading, error, mutate } = useSWR(
    'allLabs',
    fetchAllLabs,
    { refreshInterval: 15000 }
  );

  const allLabs: any[] = labsData?.labs || [];

  // RBAC: lab role sees only their own lab; admin sees all
  const visibleLabs = (mounted && role === 'lab' && sessionLabId)
    ? allLabs.filter(l => l.id === sessionLabId)
    : allLabs;

  if (!mounted || isLoading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] space-y-6">
        <div className="w-12 h-12 border-4 border-primary border-t-transparent rounded-full animate-spin" />
        <p className="text-[10px] font-black text-muted uppercase tracking-[0.3em]">Loading Lab Telemetry...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] space-y-4">
        <AlertCircle size={36} className="text-red-400 opacity-60" />
        <p className="text-[10px] font-black text-muted uppercase tracking-[0.3em]">Failed to load lab data</p>
        <button onClick={() => mutate()} className="px-4 py-2 bg-surface-low border border-border-ghost rounded-xl text-[10px] font-black uppercase tracking-widest text-muted hover:text-foreground transition-all flex items-center gap-2">
          <RefreshCw size={12} /> Retry
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-10 pb-20">
      {/* Header */}
      <div className="flex items-end justify-between">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <div className="w-2 h-2 rounded-full bg-primary animate-pulse" />
            <span className="text-[10px] font-black text-muted uppercase tracking-widest">
              Lab Network · {visibleLabs.length} {visibleLabs.length === 1 ? 'Node' : 'Nodes'}
            </span>
          </div>
          <h1 className="text-5xl font-black text-foreground tracking-tighter leading-none mb-3">LABORATORIES</h1>
          <p className="text-muted font-medium max-w-lg">
            {role === 'lab'
              ? 'Your lab metrics, queue depth, and SLA compliance.'
              : 'Live capacity, queue depths, KPIs, and SLA compliance across all testing facilities.'}
          </p>
        </div>
        <button onClick={() => mutate()} className="flex items-center gap-2 px-4 py-2.5 bg-surface-low border border-border-ghost rounded-xl text-[10px] font-black uppercase tracking-widest text-muted hover:text-foreground transition-all">
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      {/* Lab Cards */}
      {visibleLabs.length === 0 ? (
        <div className="col-span-3 text-center py-20 bg-surface-lowest rounded-[2rem] border border-border-ghost">
          <FlaskConical size={36} className="text-muted/20 mx-auto mb-4" />
          <p className="text-[10px] font-black text-muted uppercase tracking-[0.3em]">No labs configured in the system</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {visibleLabs.map((lab, i) => (
            <LabCard key={lab.id} lab={lab} index={i} />
          ))}
        </div>
      )}
    </div>
  );
}
