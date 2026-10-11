"use client";
import React, { useState } from 'react';
import useSWR from 'swr';
import { motion } from 'motion/react';
import Link from 'next/link';
import { fetchSamples } from '@/app/lib/api';
import {
  ClipboardList, CheckCircle2, Clock, AlertCircle, RefreshCw, FileText
} from 'lucide-react';
import { cn } from '@/components/ui/utils';

const STATUS_CONFIG: Record<string, { label: string; color: string; icon: any }> = {
  completed:    { label: 'Completed',     color: 'bg-success/10 border-success/30 text-success-text', icon: CheckCircle2 },
  processing:   { label: 'Processing',    color: 'bg-primary/10 border-primary/30 text-primary', icon: Clock },
  in_transit:   { label: 'In Transit',    color: 'bg-amber-500/10 border-amber-500/30 text-amber-500', icon: Clock },
  arrived:      { label: 'At Lab',        color: 'bg-primary/10 border-primary/30 text-primary', icon: Clock },
  routed:       { label: 'Routed',        color: 'bg-surface-high border-border-ghost text-muted', icon: Clock },
  pending:      { label: 'Pending',       color: 'bg-surface-high border-border-ghost text-muted', icon: Clock },
  unassigned:   { label: 'Unassigned',    color: 'bg-red-500/10 border-red-500/30 text-red-400', icon: AlertCircle },
  cancelled:    { label: 'Cancelled',     color: 'bg-red-500/10 border-red-500/30 text-red-400', icon: AlertCircle },
};

const PRIORITY_COLORS: Record<string, string> = {
  URGENT: 'text-red-500',
  HIGH:   'text-amber-500',
  NORMAL: 'text-muted',
  LOW:    'text-muted/60',
};

export default function MySamplesPage() {
  const [statusFilter, setStatusFilter] = useState<string>('');

  const { data, isLoading, mutate } = useSWR(
    `my-samples-${statusFilter}`,
    () => fetchSamples({ status: statusFilter || undefined, limit: 100 }),
    { refreshInterval: 15000 }
  );

  const samples = data?.samples || [];

  const statusTabs = [
    { key: '',           label: 'All' },
    { key: 'pending',    label: 'Pending' },
    { key: 'processing', label: 'Processing' },
    { key: 'completed',  label: 'Completed' },
  ];

  return (
    <div className="space-y-8 pb-20">
      {/* Header */}
      <div className="flex items-end justify-between">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <div className="w-2 h-2 rounded-full bg-success-bg animate-pulse" />
            <span className="text-[10px] font-black text-muted uppercase tracking-widest">Doctor Portal</span>
          </div>
          <h1 className="text-5xl font-black text-foreground tracking-tighter leading-none mb-2">MY SAMPLES</h1>
          <p className="text-muted font-medium max-w-lg">
            Track your submitted samples, estimated TAT, and access completed reports.
          </p>
        </div>
        <button
          onClick={() => mutate()}
          className="flex items-center gap-2 px-4 py-2.5 bg-surface-low border border-border-ghost rounded-xl text-[10px] font-black uppercase tracking-widest text-muted hover:text-foreground transition-all"
        >
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      {/* Status filter tabs */}
      <div className="flex gap-2 flex-wrap">
        {statusTabs.map(tab => (
          <button
            key={tab.key}
            onClick={() => setStatusFilter(tab.key)}
            className={cn(
              "px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all border",
              statusFilter === tab.key
                ? "bg-primary text-white border-primary"
                : "bg-surface-low text-muted border-border-ghost hover:text-foreground"
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Summary row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Total Submitted', value: samples.length },
          { label: 'In Progress',     value: samples.filter((s: any) => !['completed', 'cancelled'].includes(s.status)).length },
          { label: 'Reports Ready',   value: samples.filter((s: any) => s.status === 'completed').length },
          { label: 'SLA Breached',    value: samples.filter((s: any) => s.is_tat_breached).length },
        ].map(stat => (
          <div key={stat.label} className="bg-surface-lowest rounded-2xl border border-border-ghost p-5">
            <p className="text-[9px] font-black text-muted uppercase tracking-widest mb-1">{stat.label}</p>
            <p className="text-3xl font-black font-technical text-foreground">{stat.value}</p>
          </div>
        ))}
      </div>

      {/* Sample list */}
      {isLoading ? (
        <div className="flex flex-col items-center justify-center py-24 gap-4">
          <div className="w-10 h-10 border-4 border-primary border-t-transparent rounded-full animate-spin" />
          <p className="text-[10px] font-black text-muted uppercase tracking-widest">Loading Samples...</p>
        </div>
      ) : samples.length === 0 ? (
        <div className="text-center py-24 bg-surface-lowest rounded-3xl border border-border-ghost">
          <ClipboardList size={48} className="mx-auto mb-4 text-muted opacity-30" />
          <p className="text-[10px] font-black text-muted uppercase tracking-[0.3em]">No samples found</p>
          <Link
            href="/dashboard/accession"
            className="inline-flex items-center gap-2 mt-6 px-6 py-3 bg-primary text-white rounded-xl text-[10px] font-black uppercase tracking-widest hover:opacity-90 transition-all"
          >
            <ClipboardList size={14} /> Admit New Sample
          </Link>
        </div>
      ) : (
        <div className="space-y-3">
          {samples.map((sample: any) => {
            const cfg = STATUS_CONFIG[sample.status] || STATUS_CONFIG.pending;
            const StatusIcon = cfg.icon;
            const isComplete = sample.status === 'completed';
            return (
              <motion.div
                key={sample.id}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                className="bg-surface-lowest rounded-2xl border border-border-ghost hover:border-primary/30 transition-all overflow-hidden group"
              >
                <div className="px-6 py-5 flex items-center gap-4">
                  {/* Status indicator */}
                  <div className={cn("w-10 h-10 rounded-xl flex items-center justify-center shrink-0", cfg.color.split(' ').slice(0, 2).join(' '))}>
                    <StatusIcon size={18} />
                  </div>

                  {/* Main info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3 flex-wrap mb-1">
                      <span className="font-technical font-black text-foreground text-sm">
                        {sample.accession_no || `Sample #${sample.id}`}
                      </span>
                      <span className={cn("px-2.5 py-0.5 rounded-full border text-[9px] font-black uppercase", cfg.color)}>
                        {cfg.label}
                      </span>
                      <span className={cn("text-[10px] font-black uppercase", PRIORITY_COLORS[sample.priority] || PRIORITY_COLORS.NORMAL)}>
                        {sample.priority}
                      </span>
                    </div>
                    <p className="text-sm text-muted">
                      {sample.patient_name} &middot; Bill #{sample.external_bill_id || sample.bill_id}
                    </p>
                    <div className="flex items-center gap-4 mt-1.5">
                      {sample.collected_at && (
                        <span className="text-[9px] font-bold text-muted flex items-center gap-1">
                          <Clock size={10} />
                          {new Date(sample.collected_at).toLocaleDateString()}
                        </span>
                      )}
                      {sample.total_tests && (
                        <span className="text-[9px] font-bold text-muted">
                          {sample.completed_tests || 0}/{sample.total_tests} tests complete
                        </span>
                      )}
                      {sample.total_eta_mins && !isComplete && (
                        <span className="text-[9px] font-bold text-primary">
                          ~{sample.total_eta_mins}m remaining
                        </span>
                      )}
                      {sample.system_tat_mins && isComplete && (
                        <span className="text-[9px] font-bold text-success-text">
                          TAT: {sample.system_tat_mins}m
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Progress bar */}
                  {sample.total_tests > 0 && (
                    <div className="hidden md:block w-24">
                      <div className="h-1.5 bg-surface-high rounded-full overflow-hidden">
                        <div
                          className={cn("h-full rounded-full transition-all", isComplete ? "bg-success-bg" : "bg-primary")}
                          style={{ width: `${Math.round(((sample.completed_tests || 0) / sample.total_tests) * 100)}%` }}
                        />
                      </div>
                      <p className="text-[8px] font-black text-muted mt-1 text-center">
                        {Math.round(((sample.completed_tests || 0) / sample.total_tests) * 100)}%
                      </p>
                    </div>
                  )}

                  {/* Action buttons */}
                  <div className="flex items-center gap-2 shrink-0">
                    {isComplete ? (
                      <Link
                        href={`/dashboard/reports/${sample.id}`}
                        className="flex items-center gap-2 px-4 py-2.5 bg-primary text-white rounded-xl text-[9px] font-black uppercase tracking-widest hover:opacity-90 transition-all shadow-lg shadow-primary/20"
                      >
                        <FileText size={13} /> View Report
                      </Link>
                    ) : (
                      <span className="flex items-center gap-2 px-4 py-2.5 bg-surface-low border border-border-ghost text-muted rounded-xl text-[9px] font-black uppercase tracking-widest">
                        In Progress
                      </span>
                    )}
                  </div>
                </div>
              </motion.div>
            );
          })}
        </div>
      )}

      {/* Quick action */}
      <div className="pt-4">
        <Link
          href="/dashboard/accession"
          className="inline-flex items-center gap-2 px-6 py-3 bg-surface-low border border-border-ghost rounded-xl text-[10px] font-black uppercase tracking-widest text-muted hover:text-foreground hover:border-primary/30 transition-all"
        >
          <ClipboardList size={14} /> Admit Another Sample
        </Link>
      </div>
    </div>
  );
}
