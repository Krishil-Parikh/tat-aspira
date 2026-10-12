"use client";
import React, { useEffect, useState } from 'react';
import useSWR from 'swr';
import { motion } from 'motion/react';
import Link from 'next/link';
import {
  Zap, Activity, Clock, AlertCircle, ShieldCheck, 
  Layers, CheckCircle2, FlaskConical, Database, FileText
} from 'lucide-react';
import { StatCard } from '@/components/dashboard/StatCard';
import { cn } from '@/components/ui/utils';
import { fetchAdminDashboard, fetchLabDashboard, fetchTestAnalytics, confirmLabReceipt } from '@/app/lib/api';

function formatMins(totalMins: number | string | null | undefined): string {
  if (totalMins == null || totalMins === '') return '—';
  const minsNum = typeof totalMins === 'string' ? parseFloat(totalMins) : totalMins;
  if (isNaN(minsNum)) return '—';
  
  const h = Math.floor(minsNum / 60);
  const m = Math.round(minsNum % 60);
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

// Reusable pipeline progress bar component
const PipelineStatus = ({ stats }: { stats: any }) => {
  const stages = [
    { label: "Bill", count: stats?.total_samples || 0 },
    { label: "Split/Dispatch", count: stats?.active_samples || 0 },
    { label: "Received/Processing", count: (stats?.active_samples || 0) - (stats?.tat_breaches || 0) }, // proxy metric for processing
    { label: "Completed", count: stats?.completed_samples || 0 },
  ];
  return (
    <div className="bg-surface-lowest p-6 rounded-3xl border border-border-ghost">
      <h2 className="text-xs font-black text-muted uppercase tracking-widest mb-6">Global Pipeline Status</h2>
      <div className="flex items-center justify-between relative">
        <div className="absolute left-0 right-0 top-1/2 h-1 bg-border-ghost -z-10 -translate-y-1/2"></div>
        {stages.map((stage, idx) => (
          <div key={stage.label} className="flex flex-col items-center bg-surface-lowest px-2">
            <div className="w-8 h-8 rounded-full bg-primary/20 border-2 border-primary flex items-center justify-center text-primary font-black text-xs">
              {idx + 1}
            </div>
            <span className="text-[10px] font-black uppercase mt-2">{stage.label}</span>
            <span className="text-lg font-technical font-black text-primary">{stage.count}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

export default function DashboardPage() {
  const [mounted, setMounted] = useState(false);
  const [userRole, setUserRole] = useState<string | null>(null);
  const [processingId, setProcessingId] = useState<number | null>(null);

  useEffect(() => {
    setMounted(true);
    const cookies = document.cookie.split('; ');
    const role = cookies.find(c => c.startsWith('aspira_role='))?.split('=')[1] || 'admin';
    setUserRole(role.toLowerCase());
  }, []);

  // Admin Data
  const { data: adminData } = useSWR((mounted && userRole === 'admin') ? 'adminDash' : null, fetchAdminDashboard, { refreshInterval: 60000 });
  const { data: analyticsData } = useSWR((mounted && userRole === 'admin') ? 'testAnalytics' : null, fetchTestAnalytics, { refreshInterval: 120000 });

  // Lab Data
  const { data: labData, mutate: mutateLab } = useSWR((mounted && userRole === 'lab') ? 'labDash' : null, fetchLabDashboard, { refreshInterval: 30000 });

  const handleQuickReceipt = async (sampleId: number, labId: number) => {
    setProcessingId(sampleId);
    try {
      await confirmLabReceipt(sampleId, labId);
      mutateLab();
    } catch (e) {
      console.error(e);
    } finally {
      setProcessingId(null);
    }
  };

  if (!mounted) return null;

  // ─── ADMIN VIEW ─────────────────────────────────────────────────────────────
  if (userRole === 'admin') {
    const stats = adminData?.stats || { active_samples: 0, tat_breaches: 0, total_samples: 0, total_tests_in_catalog: 0, completed_samples: 0 };
    const labs = adminData?.labs || [];
    const testAnalytics = analyticsData?.tests || [];

    const complianceRate = Math.round(((stats.total_samples - (stats.tat_breaches || 0)) / (stats.total_samples || 1)) * 100);

    return (
      <div className="space-y-10 pb-20">
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-8">
          <div>
            <h1 className="text-5xl font-black text-foreground tracking-tighter leading-none mb-3">FRONTIER <span className="text-primary text-2xl">ADMIN</span></h1>
            <p className="text-muted font-medium max-w-lg">Global Operations Control Tower & System Analytics.</p>
          </div>
          <Link href="/dashboard/accession">
            <motion.button whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }} className="px-8 py-4 bg-primary text-white font-black text-xs uppercase tracking-widest rounded-2xl">
              Admit Sample
            </motion.button>
          </Link>
        </div>

        {/* Global KPIs */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <StatCard label="Active Tests" value={stats.active_samples} icon={Activity} />
          <StatCard label="Completed" value={stats.completed_samples} icon={CheckCircle2} />
          <StatCard label="SLA Compliance" value={`${complianceRate}%`} icon={ShieldCheck} />
          <StatCard label="Process Breaches" value={stats.tat_breaches || 0} icon={AlertCircle} />
        </div>

        {/* Pipeline Status */}
        <PipelineStatus stats={stats} />

        {/* Lab-wise KPIs & Analytics Grid */}
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-8">
          
          {/* Lab-wise KPIs */}
          <div className="bg-surface-lowest p-6 rounded-3xl border border-border-ghost">
            <h2 className="text-xs font-black text-muted uppercase tracking-widest mb-6 flex items-center gap-2"><Database size={14} /> Laboratory Analytics</h2>
            <div className="space-y-4">
              {labs.map((lab: any) => (
                <Link
                  href={`/dashboard/labs/${lab.id}`}
                  key={lab.id}
                  className="block hover:border-primary transition-colors bg-surface-low border border-border-ghost rounded-2xl p-5"
                >
                  <div className="flex justify-between items-center">
                    <div>
                      <h3 className="font-bold text-foreground">{lab.lab_name}</h3>
                      {/* BUG-C7 FIX: get_lab_stats() returns queue_depth/pending_batches, not sla_percent */}
                      <p className="text-[10px] text-muted font-black uppercase tracking-widest mt-1">
                        Queue: {lab.queue_depth ?? 0} · Missed Batches: {lab.missed_batches ?? 0}
                      </p>
                    </div>
                    <div className="text-right">
                      <span className="text-2xl font-black font-technical text-primary">
                        {lab.pending_batches ?? 0}
                      </span>
                      <p className="text-[9px] text-muted uppercase tracking-widest">Pending Batches</p>
                    </div>
                  </div>
                </Link>
              ))}
              {labs.length === 0 && (
                <p className="text-xs text-muted font-medium italic text-center py-6">No lab data available.</p>
              )}
            </div>
          </div>

          {/* Test-wise SLA Analytics */}
          <div className="bg-surface-lowest p-6 rounded-3xl border border-border-ghost">
            <h2 className="text-xs font-black text-muted uppercase tracking-widest mb-6 flex items-center gap-2"><FileText size={14} /> Test SLA Breakdown</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-border-ghost">
                    <th className="pb-3 text-[10px] font-black text-muted uppercase tracking-widest">Test</th>
                    <th className="pb-3 text-[10px] font-black text-muted uppercase tracking-widest">Avg TAT</th>
                    <th className="pb-3 text-[10px] font-black text-muted uppercase tracking-widest">Volume</th>
                    <th className="pb-3 text-[10px] font-black text-muted uppercase tracking-widest text-right">SLA %</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-ghost">
                  {testAnalytics.slice(0, 10).map((test: any) => (
                    <tr key={test.test_code}>
                      <td className="py-4">
                        <p className="font-bold">{test.test_code}</p>
                        <p className="text-[9px] text-muted uppercase">{test.test_name}</p>
                      </td>
                      <td className="py-4 font-technical">{formatMins(test.avg_actual_tat_mins)}</td>
                      <td className="py-4 font-technical">{test.total}</td>
                      <td className="py-4 text-right font-black font-technical text-primary">{test.sla_percent}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* System Alerts & Notifications (Admin) */}
          <div className="bg-surface-lowest p-6 rounded-3xl border border-border-ghost xl:col-span-2">
            <h2 className="text-xs font-black text-muted uppercase tracking-widest mb-6 flex items-center gap-2"><AlertCircle size={14} className="text-red-500" /> System Alerts Log</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              
              {/* Unassigned Samples */}
              <div className="space-y-3">
                <h3 className="text-[10px] font-black text-foreground uppercase tracking-widest">Unassigned & Routing Failures</h3>
                {adminData?.unassigned_samples?.length === 0 ? (
                  <p className="text-xs text-muted font-medium italic">No unassigned samples.</p>
                ) : (
                  <div className="space-y-2">
                    {adminData?.unassigned_samples?.slice(0, 5).map((u: any) => (
                      <div key={u.id} className="p-3 bg-red-500/5 border border-red-500/20 rounded-xl flex items-center justify-between">
                        <div>
                          <p className="text-xs font-bold text-red-500">{u.accession_no || `Sample #${u.id}`}</p>
                          <p className="text-[9px] text-muted uppercase tracking-widest">{u.patient_name || 'Unknown Patient'}</p>
                        </div>
                        <Link href={`/dashboard/reports/${u.id}`} className="text-[9px] font-black text-red-500 hover:underline uppercase">Resolve</Link>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Recent TAT Breaches */}
              <div className="space-y-3">
                <h3 className="text-[10px] font-black text-foreground uppercase tracking-widest">Recent SLA Breaches</h3>
                {adminData?.recent_breaches?.length === 0 ? (
                  <p className="text-xs text-muted font-medium italic">No recent breaches.</p>
                ) : (
                  <div className="space-y-2">
                    {adminData?.recent_breaches?.slice(0, 5).map((b: any) => (
                      <div key={b.sample_id} className="p-3 bg-amber-500/5 border border-amber-500/20 rounded-xl flex items-center justify-between">
                        <div>
                          <p className="text-xs font-bold text-amber-600">{b.notes || 'TAT Breach Alert'}</p>
                          <p className="text-[9px] text-muted uppercase tracking-widest">Lab: {b.lab_name || 'Unknown'} · Bill: {b.external_bill_id}</p>
                        </div>
                        <Link href={`/dashboard/reports/${b.sample_id}`} className="text-[9px] font-black text-amber-600 hover:underline uppercase">View</Link>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>

        </div>
      </div>
    );
  }

  // ─── LAB USER VIEW ──────────────────────────────────────────────────────────
  if (userRole === 'lab') {
    const kpi = labData?.kpi || {};
    const queue = labData?.work_queue || [];

    return (
      <div className="space-y-10 pb-20">
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-8">
          <div>
            <h1 className="text-5xl font-black text-foreground tracking-tighter leading-none mb-3">LABORATORY <span className="text-primary text-2xl">OPS</span></h1>
            <p className="text-muted font-medium max-w-lg">Workstation for {kpi.lab_name || 'your assigned lab'}.</p>
          </div>
          <Link href="/dashboard/lab-queue">
            <motion.button whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }} className="px-8 py-4 bg-primary text-white font-black text-xs uppercase tracking-widest rounded-2xl">
              Open Work Queue
            </motion.button>
          </Link>
        </div>

        {/* Lab KPIs */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          <StatCard label="Pending Tests" value={kpi.pending_tests || 0} icon={Activity} />
          <StatCard label="SLA Compliance" value={`${kpi.sla_percent || 100}%`} icon={ShieldCheck} />
          <StatCard label="Avg TAT" value={formatMins(kpi.avg_actual_tat_mins)} icon={Clock} />
          <StatCard label="TAT Breaches" value={kpi.tat_breaches || 0} icon={AlertCircle} />
        </div>

        {/* Quick Work Queue */}
        <div className="bg-surface-lowest rounded-3xl border border-border-ghost overflow-hidden">
          <div className="px-8 py-6 border-b border-border-ghost flex justify-between items-center">
            <h2 className="text-lg font-headline font-black uppercase tracking-widest">Incoming Samples</h2>
            <Link href="/dashboard/lab-queue" className="text-[10px] font-black text-primary uppercase tracking-widest hover:underline">View Full Queue →</Link>
          </div>
          <div className="divide-y divide-border-ghost">
            {queue.slice(0, 5).map((item: any) => (
              <div key={item.sample_id} className="p-6 flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 rounded-xl bg-surface-low flex items-center justify-center"><FlaskConical size={18} className="text-primary" /></div>
                  <div>
                    <p className="font-bold">{item.accession_no || `Sample #${item.sample_id}`}</p>
                    <p className="text-[10px] text-muted font-black uppercase tracking-widest">{item.test_name}</p>
                  </div>
                </div>
                {item.sample_status === 'routed' && (
                  <button 
                    disabled={processingId === item.sample_id}
                    onClick={() => handleQuickReceipt(item.sample_id, item.assigned_lab_id)}
                    className="px-4 py-2 bg-success text-success-text font-black text-[10px] uppercase tracking-widest rounded-xl disabled:opacity-50"
                  >
                    {processingId === item.sample_id ? 'Confirming...' : 'Mark Received'}
                  </button>
                )}
                {item.sample_status !== 'routed' && (
                  <span className="text-[10px] font-black uppercase px-3 py-1 bg-surface-high rounded-full">{item.sample_status}</span>
                )}
              </div>
            ))}
            {queue.length === 0 && (
              <div className="p-12 text-center text-muted text-[10px] font-black uppercase tracking-widest">Queue is empty</div>
            )}
          </div>
        </div>

        {/* Lab Activity Log */}
        <div className="bg-surface-lowest rounded-3xl border border-border-ghost overflow-hidden">
          <div className="px-8 py-6 border-b border-border-ghost flex justify-between items-center">
            <h2 className="text-lg font-headline font-black uppercase tracking-widest flex items-center gap-2"><CheckCircle2 size={18} className="text-success-text" /> Recent Completions</h2>
          </div>
          <div className="p-6">
            {labData?.recent_completions?.length === 0 ? (
              <p className="text-xs text-muted font-medium italic text-center py-4">No recent test completions.</p>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {labData?.recent_completions?.slice(0, 6).map((comp: any) => (
                  <div key={comp.test_code + comp.sample_id} className="p-4 bg-success/5 border border-success/20 rounded-2xl flex items-start gap-4">
                    <div className="w-8 h-8 rounded-full bg-success/10 flex items-center justify-center shrink-0">
                      <ShieldCheck size={14} className="text-success-text" />
                    </div>
                    <div>
                      <p className="text-sm font-bold text-foreground">{comp.test_code}</p>
                      <p className="text-[10px] text-muted font-black uppercase tracking-widest mb-1">{comp.patient_name}</p>
                      <p className="text-[9px] text-success-text font-black uppercase tracking-widest">
                        {formatMins(comp.actual_total_eta_mins)} TAT
                        {comp.actual_tat_breached ? ' (BREACHED)' : ' (ON TIME)'}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  return null;
}
