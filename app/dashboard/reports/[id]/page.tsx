"use client";
import React, { use } from 'react';
import useSWR from 'swr';
import { motion } from 'motion/react';
import Link from 'next/link';
import { fetchSampleDetail, fetchSampleTimeline } from '@/app/lib/api';
import {
  CheckCircle2, ArrowLeft, Activity, Clock, ShieldCheck, MapPin, Beaker,
  AlertTriangle, FlaskConical, User, Database, Zap, TrendingUp, Layers
} from 'lucide-react';
import { cn } from '@/components/ui/utils';

const STATUS_CONFIG: Record<string, { bg: string, border: string, text: string }> = {
  completed:  { bg: 'bg-emerald-500/10', border: 'border-emerald-500/30', text: 'text-emerald-500' },
  processing: { bg: 'bg-primary/10',     border: 'border-primary/30',     text: 'text-primary' },
  in_queue:   { bg: 'bg-amber-500/10',   border: 'border-amber-500/30',   text: 'text-amber-500' },
  arrived:    { bg: 'bg-blue-500/10',    border: 'border-blue-500/30',    text: 'text-blue-500' },
  pending:    { bg: 'bg-surface-high',   border: 'border-border-ghost',   text: 'text-muted' },
  cancelled:  { bg: 'bg-red-500/10',     border: 'border-red-500/30',     text: 'text-red-400' },
  unassigned: { bg: 'bg-orange-500/10',  border: 'border-orange-500/30',  text: 'text-orange-500' },
};

const TIMELINE_ICON_MAP: Record<string, any> = {
  sample_activated:      MapPin,
  sample_created:        Beaker,
  sample_received:       FlaskConical,
  sample_collected:      FlaskConical,
  routing_assigned:      MapPin,
  routing_failed:        AlertTriangle,
  batch_assigned:        Clock,
  batch_missed:          AlertTriangle,
  test_completed:        CheckCircle2,
  test_started:          Activity,
  sample_completed:      CheckCircle2,
  tat_breach_alert:      AlertTriangle,
  sample_delayed:        AlertTriangle,
};

const TIMELINE_COLORS: Record<string, string> = {
  tat_breach_alert:  'border-red-500 bg-red-500/10 text-red-500',
  sample_delayed:    'border-orange-500 bg-orange-500/10 text-orange-500',
  routing_failed:    'border-orange-500 bg-orange-500/10 text-orange-500',
  batch_missed:      'border-amber-500 bg-amber-500/10 text-amber-500',
  test_completed:    'border-emerald-500 bg-emerald-500/10 text-emerald-500',
  sample_completed:  'border-emerald-500 bg-emerald-500/10 text-emerald-500',
  routing_assigned:  'border-primary bg-primary/10 text-primary',
  batch_assigned:    'border-primary bg-primary/10 text-primary',
};

function formatMins(totalMins: number | string | null | undefined): string {
  if (totalMins == null || totalMins === '') return '—';
  const minsNum = typeof totalMins === 'string' ? parseFloat(totalMins) : totalMins;
  if (isNaN(minsNum)) return '—';
  const h = Math.floor(minsNum / 60);
  const m = Math.round(minsNum % 60);
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function fmt(dateStr: string | undefined | null): string {
  if (!dateStr) return '—';
  let dStr = dateStr;
  // Ensure UTC parsing if the database omitted the timezone
  if (!dStr.endsWith('Z') && !dStr.includes('+')) {
    dStr += 'Z';
  }
  return new Date(dStr).toLocaleString('en-IN', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
  });
}

function StatCard({ label, value, sub, colorClass }: { label: string; value: string; sub?: string; colorClass?: string }) {
  return (
    <motion.div 
      whileHover={{ y: -2 }}
      className="bg-surface-lowest/60 backdrop-blur-md rounded-2xl p-5 border border-white/40 shadow-[0_4px_16px_-4px_rgba(0,0,0,0.02)] transition-all"
    >
      <p className="text-[10px] font-black text-muted uppercase tracking-widest mb-1">{label}</p>
      <p className={cn("text-xl font-technical font-black tracking-tight", colorClass || "text-foreground")}>{value}</p>
      {sub && <p className="text-[10px] text-muted/80 mt-1 font-medium">{sub}</p>}
    </motion.div>
  );
}

export default function SampleReportPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);

  const { data: detailData, isLoading: detailLoading } = useSWR(
    `report-${id}`, () => fetchSampleDetail(Number(id)), { refreshInterval: 15000 }
  );
  const { data: timelineData, isLoading: timelineLoading } = useSWR(
    `timeline-${id}`, () => fetchSampleTimeline(Number(id)), { refreshInterval: 15000 }
  );

  if (detailLoading || timelineLoading) return (
    <div className="flex flex-col items-center justify-center min-h-[500px] gap-6">
      <div className="relative w-16 h-16">
        <div className="absolute inset-0 border-4 border-primary/20 rounded-full"></div>
        <div className="absolute inset-0 border-4 border-primary border-t-transparent rounded-full animate-spin"></div>
      </div>
      <p className="text-[10px] font-black text-primary uppercase tracking-[0.3em] animate-pulse">Loading Operations...</p>
    </div>
  );

  const { sample, tests, eta } = detailData || {};
  const timelineEvents = timelineData?.timeline || [];

  if (!sample) return (
    <div className="flex flex-col items-center justify-center min-h-[500px]">
      <Database size={48} className="text-muted/20 mb-4" />
      <p className="text-[10px] font-black text-muted uppercase tracking-widest">Sample not found in database</p>
    </div>
  );

  const isComplete = sample.status === 'completed';
  const completedTests = (tests || []).filter((t: any) => t.status === 'completed').length;
  const totalTests = (tests || []).length;
  
  const sampleStatusConfig = STATUS_CONFIG[sample.status?.toLowerCase()] || STATUS_CONFIG.pending;

  return (
    <div className="relative min-h-screen -mx-8 -mt-8 px-8 pt-8 pb-24 overflow-hidden">
      {/* ── BACKGROUND EFFECTS ── */}
      <div className="absolute top-0 left-0 w-full h-[600px] bg-gradient-to-br from-[#E6F0F9] via-[#F6FAFF] to-transparent -z-10" />
      <div className="absolute top-[-20%] right-[-10%] w-[800px] h-[800px] bg-primary/5 rounded-full blur-[120px] -z-10" />
      <div className="absolute bottom-0 left-[-10%] w-[600px] h-[600px] bg-emerald-500/5 rounded-full blur-[100px] -z-10" />

      <div className="max-w-5xl mx-auto space-y-10">
        <Link href="/dashboard" className="inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-muted hover:text-primary transition-colors">
          <ArrowLeft size={14} /> Back to Dashboard
        </Link>

        {/* ── PAGE HEADER ── */}
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 relative z-10">
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
            <div className="flex items-center gap-2 mb-2">
              <div className="w-8 h-8 rounded-xl bg-primary/10 flex items-center justify-center">
                <Beaker size={14} className="text-primary" />
              </div>
              <span className="text-[10px] font-black text-primary uppercase tracking-[0.2em]">
                ASPIRA SAMPLE RECORD
              </span>
            </div>
            <h1 className="text-5xl md:text-6xl font-headline font-black tracking-tighter text-foreground drop-shadow-sm">
              {sample.accession_no || `Sample #${sample.id}`}
            </h1>
          </motion.div>
          
          <motion.div 
            initial={{ opacity: 0, scale: 0.95 }} 
            animate={{ opacity: 1, scale: 1 }}
            className="flex items-center gap-3 bg-white/60 backdrop-blur-xl p-2 pr-6 rounded-full border border-white/50 shadow-sm"
          >
            <div className={cn("w-10 h-10 rounded-full flex items-center justify-center", sampleStatusConfig.bg, sampleStatusConfig.text)}>
              {isComplete ? <CheckCircle2 size={18} /> : <Activity size={18} />}
            </div>
            <div>
              <p className="text-[9px] font-black uppercase tracking-widest text-muted mb-0.5">Status</p>
              <p className={cn("text-xs font-black uppercase tracking-widest", sampleStatusConfig.text)}>
                {isComplete ? 'Processing Complete' : `${completedTests}/${totalTests} Tests Done`}
              </p>
            </div>
          </motion.div>
        </div>

        {/* ── 1. SAMPLE INFORMATION ── */}
        <motion.div 
          initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
          className="bg-white/40 backdrop-blur-2xl rounded-[2rem] border border-white/60 shadow-[0_8px_32px_-8px_rgba(0,0,0,0.04)] overflow-hidden"
        >
          <div className="px-8 py-6 border-b border-white/40 flex items-center gap-3 bg-white/20">
            <User size={18} className="text-primary" />
            <h2 className="text-sm font-headline font-black uppercase tracking-widest text-foreground">Sample Information</h2>
          </div>
          <div className="p-8 grid grid-cols-2 md:grid-cols-4 gap-5">
            <StatCard label="Patient" value={sample.patient_name || '—'} />
            <StatCard label="Bill ID" value={`#${sample.external_bill_id || sample.bill_id}`} />
            <StatCard
              label="Sample Status"
              value={sample.status?.toUpperCase() || '—'}
              colorClass={sampleStatusConfig.text}
            />
            <StatCard label="Priority" value={sample.priority || 'NORMAL'} />
            <StatCard label="Collected At" value={fmt(sample.collected_at)} />
            <StatCard label="Received At Lab" value={sample.received_at || sample.arrived_at_lab ? fmt(sample.received_at || sample.arrived_at_lab) : 'Awaiting Arrival'} />
            <StatCard label="Total Tests" value={String(totalTests)} sub={`${completedTests} completed successfully`} />
            <StatCard
              label="Assigned Lab"
              value={sample.lab_name ? sample.lab_name : (sample.assigned_lab_id ? `Lab #${sample.assigned_lab_id}` : (totalTests > 1 ? 'Multiple Labs (Split Order)' : 'Routing...'))}
              colorClass={sample.lab_name || totalTests > 1 ? "text-foreground" : "text-amber-500"}
            />
          </div>

          {/* TAT Banner */}
          {eta && (
            <div className="px-8 pb-8">
              <div className="bg-gradient-to-r from-surface-lowest to-surface-low rounded-3xl p-6 grid grid-cols-2 md:grid-cols-4 gap-6 border border-border-ghost shadow-inner">
                <div>
                  <p className="flex items-center gap-1.5 text-[9px] font-black text-muted uppercase tracking-widest mb-1.5">
                    <Clock size={12} /> Total ETA
                  </p>
                  <p className="text-3xl font-technical font-black text-foreground">
                    {eta.total_eta_mins != null ? formatMins(eta.total_eta_mins) : '—'}
                  </p>
                </div>
                <div>
                  <p className="flex items-center gap-1.5 text-[9px] font-black text-muted uppercase tracking-widest mb-1.5">
                    <Layers size={12} /> Queue Wait
                  </p>
                  <p className="text-3xl font-technical font-black text-foreground">
                    {eta.queue_wait_mins != null ? formatMins(eta.queue_wait_mins) : '—'}
                  </p>
                </div>
                <div>
                  <p className="flex items-center gap-1.5 text-[9px] font-black text-muted uppercase tracking-widest mb-1.5">
                    <Activity size={12} /> Lab Processing
                  </p>
                  <p className="text-3xl font-technical font-black text-foreground">
                    {eta.lab_processing_mins != null ? formatMins(eta.lab_processing_mins) : '—'}
                  </p>
                </div>
                <div className="relative">
                  <div className="absolute -left-6 top-0 bottom-0 w-px bg-border-ghost hidden md:block"></div>
                  <p className="flex items-center gap-1.5 text-[9px] font-black text-muted uppercase tracking-widest mb-1.5 pl-0 md:pl-2">
                    <ShieldCheck size={12} /> SLA Status
                  </p>
                  <p className={cn("text-3xl font-technical font-black pl-0 md:pl-2", eta.is_tat_breached ? "text-red-500" : "text-emerald-500")}>
                    {eta.is_tat_breached
                      ? `BREACHED`
                      : 'WITHIN SLA'}
                  </p>
                  {eta.is_tat_breached && (
                    <p className="text-[10px] font-bold text-red-500/70 mt-1 pl-0 md:pl-2">+{formatMins(eta.breach_by_mins)} over target</p>
                  )}
                </div>
              </div>
            </div>
          )}
        </motion.div>

        {/* ── 2. TESTS & RESULTS ── */}
        <motion.div 
          initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}
          className="bg-white/60 backdrop-blur-2xl rounded-[2rem] border border-white/60 shadow-[0_8px_32px_-8px_rgba(0,0,0,0.04)] overflow-hidden"
        >
          <div className="px-8 py-6 border-b border-white/60 flex items-center justify-between bg-white/30">
            <div className="flex items-center gap-3">
              <FlaskConical size={18} className="text-primary" />
              <h2 className="text-sm font-headline font-black uppercase tracking-widest text-foreground">Tests & Results</h2>
            </div>
            <span className="px-3 py-1 bg-white rounded-full text-[9px] font-black text-primary uppercase shadow-sm border border-primary/10">
              {totalTests} Tracked
            </span>
          </div>
          <div className="divide-y divide-border-ghost/50">
            {(tests || []).map((test: any, idx: number) => {
              const labTat = test.lab_tat_mins;
              const slaTat = test.sla_tat_mins;
              const breached = test.is_original_breached;
              const hasLab = !!test.lab_name;
              const testConfig = STATUS_CONFIG[test.status?.toLowerCase()] || STATUS_CONFIG.pending;

              return (
                <div key={test.id} className="p-8 hover:bg-white/40 transition-colors">
                  <div className="flex flex-col lg:flex-row items-start justify-between gap-8">
                    
                    {/* Left: Test Info */}
                    <div className="flex items-start gap-5 flex-1 w-full lg:w-auto">
                      <div className={cn("w-14 h-14 rounded-2xl flex items-center justify-center shrink-0 border shadow-inner", testConfig.bg, testConfig.border, testConfig.text)}>
                        <Activity size={24} />
                      </div>
                      <div>
                        <div className="flex items-center gap-3 mb-1.5">
                          <h3 className="font-headline font-black text-xl tracking-tight text-foreground">{test.test_code}</h3>
                          <span className={cn("px-2.5 py-1 rounded-full border text-[9px] font-black uppercase tracking-widest", testConfig.bg, testConfig.border, testConfig.text)}>
                            {test.status?.replace('_', ' ')}
                          </span>
                        </div>
                        <p className="text-sm text-muted font-medium">{test.test_name || 'Standard Diagnostics'}</p>
                      </div>
                    </div>

                    {/* Right: Metrics Grid */}
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-8 w-full lg:w-1/2 bg-surface-lowest/50 p-5 rounded-2xl border border-white/50">
                      <div>
                        <p className="text-[9px] font-black text-muted/70 uppercase tracking-widest mb-1.5">Assigned Lab</p>
                        <p className={cn("font-bold text-sm tracking-tight", hasLab ? "text-foreground" : "text-amber-500")}>
                          {test.lab_name || 'Unassigned'}
                        </p>
                      </div>
                      <div>
                        <p className="text-[9px] font-black text-muted/70 uppercase tracking-widest mb-1.5">Actual TAT</p>
                        <p className={cn("font-technical font-black text-base", breached === 1 ? "text-red-500" : labTat ? "text-emerald-500" : "text-muted")}>
                          {labTat != null ? formatMins(labTat) : 'Pending'}
                        </p>
                      </div>
                      <div className="hidden md:block">
                        <p className="text-[9px] font-black text-muted/70 uppercase tracking-widest mb-1.5">SLA Target</p>
                        <p className="font-technical font-black text-base text-muted">
                          {slaTat != null ? formatMins(slaTat) : '—'}
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* ETA Indicator */}
                  {test.estimated_end_time && test.status !== 'completed' && (
                    <div className="mt-4 ml-[76px] flex items-center gap-3">
                      <div className="flex items-center gap-2 bg-surface-low px-3 py-1.5 rounded-lg border border-border-ghost">
                        <Clock size={12} className="text-muted" />
                        <p className="text-[10px] font-black text-muted uppercase">
                          Est. End: <span className="text-foreground">{fmt(test.estimated_end_time)}</span>
                        </p>
                      </div>
                      {test.is_tat_breached && (
                        <span className="px-3 py-1.5 rounded-lg bg-red-500/10 border border-red-500/20 text-red-500 text-[10px] font-black flex items-center gap-1.5 shadow-sm">
                          <AlertTriangle size={12} /> TAT BREACHED
                        </span>
                      )}
                    </div>
                  )}

                  {/* Final Result Block */}
                  <div className="mt-6 ml-[76px]">
                    {test.result ? (
                      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="bg-gradient-to-br from-emerald-500/10 to-emerald-500/5 border border-emerald-500/20 rounded-2xl p-6 shadow-sm relative overflow-hidden">
                        <div className="absolute top-0 right-0 p-6 opacity-10">
                          <ShieldCheck size={64} className="text-emerald-500" />
                        </div>
                        <div className="flex items-center gap-2 mb-3 relative z-10">
                          <ShieldCheck size={16} className="text-emerald-600" />
                          <p className="text-[10px] font-black text-emerald-700 uppercase tracking-[0.2em]">Final Report Generated</p>
                        </div>
                        <p className="font-technical font-black text-foreground text-xl relative z-10">{test.result}</p>
                        {test.actual_completion_time && (
                          <p className="text-[10px] font-bold text-emerald-700/60 mt-3 relative z-10">Completed: {fmt(test.actual_completion_time)}</p>
                        )}
                      </motion.div>
                    ) : (
                      <div className="bg-surface-low/30 rounded-2xl p-6 border border-dashed border-border-ghost flex flex-col items-center justify-center text-center">
                        <Zap size={24} className="text-muted/30 mb-2" />
                        <p className="text-[10px] font-black text-muted uppercase tracking-[0.2em]">Awaiting Lab Submission</p>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </motion.div>

        {/* ── 3. OPERATIONAL TIMELINE ── */}
        <motion.div 
          initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}
          className="bg-white/60 backdrop-blur-2xl rounded-[2rem] border border-white/60 shadow-[0_8px_32px_-8px_rgba(0,0,0,0.04)] overflow-hidden"
        >
          <div className="px-8 py-6 border-b border-white/60 flex items-center justify-between bg-white/30">
            <div className="flex items-center gap-3">
              <TrendingUp size={18} className="text-primary" />
              <h2 className="text-sm font-headline font-black uppercase tracking-widest text-foreground">Operational Timeline</h2>
            </div>
            <span className="text-[10px] font-black text-muted uppercase tracking-widest">
              {timelineEvents.length} Events Logged
            </span>
          </div>
          
          <div className="p-8 md:p-10">
            {timelineEvents.length === 0 ? (
              <div className="flex flex-col items-center py-10">
                <Clock size={32} className="text-muted/30 mb-4" />
                <p className="text-[10px] font-black text-muted uppercase tracking-[0.3em] text-center">No timeline events recorded</p>
              </div>
            ) : (
              <div className="relative border-l-[3px] border-border-ghost/50 ml-6 md:ml-8 space-y-10">
                {timelineEvents.map((event: any, idx: number) => {
                  const Icon = TIMELINE_ICON_MAP[event.event_type] || Activity;
                  const colorClass = TIMELINE_COLORS[event.event_type] || 'border-white bg-surface-low text-muted shadow-sm';
                  const isFirst = idx === 0;

                  return (
                    <motion.div
                      key={event.id}
                      initial={{ opacity: 0, x: -20 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: idx * 0.08, type: "spring", stiffness: 100 }}
                      className="relative pl-10"
                    >
                      {/* Timeline dot & glow */}
                      {isFirst && <div className="absolute -left-[27px] top-0 w-12 h-12 rounded-full bg-primary/20 blur-md animate-pulse"></div>}
                      <div className={cn(
                        "absolute -left-[22px] top-1 w-10 h-10 rounded-full border-[3px] flex items-center justify-center z-10 transition-transform hover:scale-110",
                        isFirst ? "bg-primary border-primary/20 text-white shadow-lg shadow-primary/30" : colorClass
                      )}>
                        <Icon size={16} />
                      </div>

                      <div className="bg-white/80 border border-white shadow-sm p-5 rounded-2xl group hover:shadow-md hover:bg-white transition-all">
                        <div className="flex items-center gap-3 mb-2 flex-wrap">
                          {isFirst && (
                            <span className="px-2.5 py-1 rounded bg-primary text-[9px] font-black uppercase tracking-widest text-white shadow-sm">
                              Latest Event
                            </span>
                          )}
                          <span className={cn(
                            "text-[11px] font-black uppercase tracking-widest",
                            isFirst ? "text-primary" : "text-foreground/80"
                          )}>
                            {event.event_type.replace(/_/g, ' ')}
                          </span>
                          <span className="text-[10px] font-black font-technical text-muted ml-auto bg-surface-lowest px-2 py-0.5 rounded-full border border-border-ghost">
                            {fmt(event.event_timestamp)}
                          </span>
                        </div>

                        <p className="text-[15px] font-medium text-foreground/80 leading-relaxed">{event.notes || '—'}</p>

                        {(event.lab_name || event.test_code) && (
                          <div className="flex items-center gap-4 mt-4 pt-3 border-t border-border-ghost/50 text-[10px] font-black text-muted uppercase tracking-widest">
                            {event.lab_name && (
                              <span className="flex items-center gap-1.5">
                                <MapPin size={12} /> <span className="text-primary">{event.lab_name}</span>
                              </span>
                            )}
                            {event.test_code && (
                              <span className="flex items-center gap-1.5">
                                <Activity size={12} /> <span className="text-foreground">{event.test_code}</span>
                              </span>
                            )}
                          </div>
                        )}
                      </div>
                    </motion.div>
                  );
                })}
              </div>
            )}
          </div>
        </motion.div>
      </div>
    </div>
  );
}
