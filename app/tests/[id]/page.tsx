"use client";

import React, { use, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import useSWR from 'swr';
import {
  AlertCircle, ArrowLeft, CheckCircle2, Clock, FileText, User
} from 'lucide-react';
import { fetchTrackedTestDetail } from '@/app/lib/api';
import { cn } from '@/components/ui/utils';

const STATUS_COLORS: Record<string, string> = {
  draft:      'bg-surface-high border-border-ghost text-muted',
  pending:    'bg-amber-500/10 border-amber-500/30 text-amber-500',
  processing: 'bg-primary/10 border-primary/30 text-primary',
  completed:  'bg-success/10 border-success/30 text-success-text',
  delivered:  'bg-success/10 border-success/30 text-success-text',
  cancelled:  'bg-red-500/10 border-red-500/30 text-red-400',
};

function readableDate(value?: string) {
  if (!value) return 'Not available';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Not available';
  return date.toLocaleString([], {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function statusLabel(value?: string) {
  if (!value) return 'Unknown';
  return value.replace(/_/g, ' ');
}

function Field({ label, value }: { label: string; value?: React.ReactNode }) {
  return (
    <div>
      <p className="text-[9px] font-black text-muted uppercase tracking-widest mb-1">{label}</p>
      <p className="text-sm font-black text-foreground">{value || '-'}</p>
    </div>
  );
}

export default function TestDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const resolvedParams = use(params);
  const testId = resolvedParams.id;
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  const { data, isLoading, error } = useSWR(
    `tracked-test-${testId}`,
    () => fetchTrackedTestDetail(testId),
    { refreshInterval: 10000 }
  );

  const isOverdue = useMemo(() => (
    data?.eta &&
    !['completed', 'cancelled', 'delivered'].includes((data.status || '').toLowerCase()) &&
    new Date(data.eta).getTime() < Date.now()
  ), [data]);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-background flex flex-col items-center justify-center gap-4 p-6">
        <div className="w-10 h-10 border-4 border-primary border-t-transparent rounded-full animate-spin" />
        <p className="text-[10px] font-black text-muted uppercase tracking-widest">Loading Test Detail...</p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-6">
        <div className="bg-surface-lowest border border-border-ghost rounded-3xl p-8 text-center max-w-md">
          <AlertCircle size={40} className="mx-auto mb-4 text-red-500" />
          <h1 className="text-2xl font-black text-foreground tracking-tight mb-2">Test unavailable</h1>
          <p className="text-sm text-muted mb-6">{error?.message || 'Unable to load this test.'}</p>
          <Link
            href="/dashboard/tests"
            className="inline-flex items-center gap-2 px-4 py-2.5 bg-primary text-white rounded-xl text-[10px] font-black uppercase tracking-widest"
          >
            <ArrowLeft size={14} /> Back to tests
          </Link>
        </div>
      </div>
    );
  }

  const status = (data.status || '').toLowerCase();
  const timeline = data.timeline || [];

  return (
    <div className="min-h-screen bg-background p-6 lg:p-10">
      <div className="max-w-7xl mx-auto space-y-8">
        <header className="flex flex-col md:flex-row md:items-end justify-between gap-5">
          <div>
            <Link
              href="/dashboard/tests"
              className="inline-flex items-center gap-2 text-[10px] font-black text-muted uppercase tracking-widest hover:text-foreground transition-colors mb-4"
            >
              <ArrowLeft size={14} /> Test Tracking
            </Link>
            <h1 className="text-5xl font-black text-foreground tracking-tighter leading-none mb-2">
              {data.test_name || `Test #${data.test_id}`}
            </h1>
            <p className="text-muted font-medium">
              Test #{data.test_id} &middot; {data.accession_no || `Sample #${data.sample_id || '-'}`}
            </p>
          </div>

          <span className={cn(
            "inline-flex w-fit px-4 py-2 rounded-full border text-[10px] font-black uppercase tracking-widest",
            STATUS_COLORS[status] || 'bg-surface-high border-border-ghost text-muted'
          )}>
            {statusLabel(data.status)}
          </span>
        </header>

        <div className="grid grid-cols-1 xl:grid-cols-[1fr_360px] gap-8 items-start">
          <main className="space-y-8">
            <section className="bg-surface-lowest border border-border-ghost rounded-3xl overflow-hidden shadow-sm">
              <div className="px-6 py-5 border-b border-border-ghost/30 flex items-center gap-3">
                <div className="w-10 h-10 rounded-2xl bg-primary/10 flex items-center justify-center">
                  <FileText size={18} className="text-primary" />
                </div>
                <div>
                  <h2 className="text-xl font-black text-foreground tracking-tight">Test Info</h2>
                  <p className="text-[10px] font-black text-muted uppercase tracking-widest">Patient, bill, and lab context</p>
                </div>
              </div>

              <div className="p-6 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                <Field label="Test ID" value={data.test_id} />
                <Field label="Test Name" value={data.test_name} />
                <Field label="Patient Name" value={data.patient_name} />
                <Field label="Bill ID" value={data.bill_id} />
                <Field label="Patient ID" value={data.patient_id} />
                <Field label="Created" value={mounted ? readableDate(data.created_at) : '...'} />
                <Field label="Source Lab" value={data.source_lab || 'Unknown'} />
                <Field label="Processing Lab" value={data.processing_lab || 'Unassigned'} />
                <div>
                  <p className="text-[9px] font-black text-muted uppercase tracking-widest mb-1">Status</p>
                  <span className={cn(
                    "inline-flex px-3 py-1 rounded-full border text-[9px] font-black uppercase tracking-widest",
                    STATUS_COLORS[status] || 'bg-surface-high border-border-ghost text-muted'
                  )}>
                    {statusLabel(data.status)}
                  </span>
                </div>
              </div>
            </section>

            <section className="bg-surface-lowest border border-border-ghost rounded-3xl p-6 shadow-sm">
              <div className="flex items-center gap-3 mb-7">
                <div className="w-10 h-10 rounded-2xl bg-success/10 flex items-center justify-center">
                  <CheckCircle2 size={18} className="text-success-text" />
                </div>
                <div>
                  <h2 className="text-xl font-black text-foreground tracking-tight">Status Timeline</h2>
                  <p className="text-[10px] font-black text-muted uppercase tracking-widest">Chronological audit trail</p>
                </div>
              </div>

              <div className="relative pl-7">
                <div className="absolute left-[10px] top-1 bottom-1 w-px bg-border-ghost" />
                {timeline.length === 0 ? (
                  <p className="text-[10px] font-black text-muted uppercase tracking-widest py-10">No timeline events yet</p>
                ) : timeline.map((event: any, index: number) => {
                  const complete = index < timeline.length - 1 || ['completed', 'delivered', 'cancelled'].includes(status);
                  return (
                    <div key={`${event.status}-${event.timestamp}-${index}`} className="relative pb-8 last:pb-0">
                      <div className={cn(
                        "absolute -left-[22px] top-0 w-5 h-5 rounded-full border-4 border-surface-lowest",
                        complete ? "bg-success-bg" : "bg-surface-high"
                      )} />
                      <div className="bg-surface-low rounded-2xl border border-border-ghost p-4">
                        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2 mb-2">
                          <h3 className="text-sm font-black text-foreground">{event.status}</h3>
                          <time className="text-[9px] font-black text-muted uppercase tracking-widest whitespace-nowrap">
                            {mounted ? readableDate(event.timestamp) : '...'}
                          </time>
                        </div>
                        <p className="text-sm text-muted font-medium">{event.description || 'Event recorded'}</p>
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>
          </main>

          <aside className="space-y-6 xl:sticky xl:top-8">
            <section className={cn(
              "bg-surface-lowest border rounded-3xl p-6 shadow-sm",
              isOverdue ? "border-red-500/30" : "border-border-ghost"
            )}>
              <div className="flex items-center justify-between gap-3 mb-6">
                <div className="flex items-center gap-3">
                  <div className={cn(
                    "w-10 h-10 rounded-2xl flex items-center justify-center",
                    isOverdue ? "bg-red-500/10" : "bg-primary/10"
                  )}>
                    <Clock size={18} className={isOverdue ? "text-red-500" : "text-primary"} />
                  </div>
                  <div>
                    <h2 className="text-xl font-black text-foreground tracking-tight">ETA</h2>
                    <p className="text-[10px] font-black text-muted uppercase tracking-widest">Expected completion</p>
                  </div>
                </div>

                {isOverdue && (
                  <span className="px-3 py-1 rounded-full bg-red-500/10 border border-red-500/30 text-red-500 text-[9px] font-black uppercase tracking-widest">
                    Overdue
                  </span>
                )}
              </div>

              <p className={cn(
                "text-3xl font-black font-technical tracking-tight",
                isOverdue ? "text-red-500" : "text-foreground"
              )}>
                {mounted ? readableDate(data.eta) : '...'}
              </p>
              <p className="text-xs text-muted font-medium mt-3">
                {data.eta
                  ? isOverdue
                    ? 'This test has crossed its backend ETA.'
                    : 'ETA is calculated by the backend TAT engine.'
                  : 'No ETA has been assigned yet.'}
              </p>
            </section>

            <section className="bg-surface-lowest border border-border-ghost rounded-3xl p-6 shadow-sm">
              <div className="flex items-center gap-3 mb-5">
                <div className="w-10 h-10 rounded-2xl bg-surface-low flex items-center justify-center">
                  <User size={18} className="text-muted" />
                </div>
                <div>
                  <h2 className="text-xl font-black text-foreground tracking-tight">Context</h2>
                  <p className="text-[10px] font-black text-muted uppercase tracking-widest">Operational links</p>
                </div>
              </div>
              <div className="space-y-3">
                <div className="px-4 py-3 bg-surface-low border border-border-ghost rounded-2xl">
                  <p className="text-[9px] font-black text-muted uppercase tracking-widest mb-1">Sample</p>
                  <p className="text-xs font-black text-foreground">
                    {data.accession_no || `Sample #${data.sample_id || '-'}`}
                  </p>
                </div>
              </div>
            </section>
          </aside>
        </div>
      </div>
    </div>
  );
}
