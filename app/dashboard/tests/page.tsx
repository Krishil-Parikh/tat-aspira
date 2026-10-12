"use client";

import React, { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import useSWR from 'swr';
import { motion } from 'motion/react';
import {
  AlertCircle, ChevronLeft, ChevronRight, Clock, Eye, RefreshCw, Search
} from 'lucide-react';
import { fetchTrackedTests } from '@/app/lib/api';
import { cn } from '@/components/ui/utils';

const PAGE_SIZE = 20;

const STATUS_OPTIONS = ['', 'draft', 'pending', 'processing', 'completed', 'cancelled'];

const STATUS_COLORS: Record<string, string> = {
  draft:      'bg-surface-high border-border-ghost text-muted',
  pending:    'bg-amber-500/10 border-amber-500/30 text-amber-500',
  processing: 'bg-primary/10 border-primary/30 text-primary',
  completed:  'bg-success/10 border-success/30 text-success-text',
  cancelled:  'bg-red-500/10 border-red-500/30 text-red-400',
};

function timeAgo(value?: string) {
  if (!value) return 'Unknown';
  const diff = Date.now() - new Date(value).getTime();
  if (Number.isNaN(diff)) return 'Unknown';

  const minutes = Math.max(0, Math.floor(diff / 60000));
  if (minutes < 1) return 'Just now';
  if (minutes < 60) return `${minutes}m ago`;

  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;

  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;

  const months = Math.floor(days / 30);
  if (months < 12) return `${months}mo ago`;

  return `${Math.floor(months / 12)}y ago`;
}

function formatEta(value?: string) {
  if (!value) return 'Pending ETA';
  return new Date(value).toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export default function TestTrackingPage() {
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(1);
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    setPage(1);
  }, [search, status]);

  const offset = (page - 1) * PAGE_SIZE;
  const { data, isLoading, error, mutate } = useSWR(
    ['tracked-tests', search, status, offset],
    () => fetchTrackedTests({
      q: search.trim() || undefined,
      status: status || undefined,
      limit: PAGE_SIZE,
      offset,
    }),
    { refreshInterval: 10000 }
  );

  const tests = data?.tests || [];
  const total = data?.total || 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const summary = useMemo(() => ({
    visible: tests.length,
    overdue: tests.filter((test: any) => (
      test.eta &&
      !['completed', 'cancelled'].includes(test.status) &&
      new Date(test.eta).getTime() < Date.now()
    )).length,
  }), [tests]);

  return (
    <div className="space-y-8 pb-20">
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-6">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <div className="w-2 h-2 rounded-full bg-primary animate-pulse" />
            <span className="text-[10px] font-black text-muted uppercase tracking-widest">Test Tracking</span>
          </div>
          <h1 className="text-5xl font-black text-foreground tracking-tighter leading-none mb-2">TESTS</h1>
          <p className="text-muted font-medium max-w-xl">
            Live test instances joined to patient, bill, sample, and ETA records.
          </p>
        </div>

        <button
          suppressHydrationWarning
          onClick={() => mutate()}
          className="flex items-center gap-2 px-4 py-2.5 bg-surface-low border border-border-ghost rounded-xl text-[10px] font-black uppercase tracking-widest text-muted hover:text-foreground transition-all"
        >
          <RefreshCw size={14} className={cn(isLoading && "animate-spin")} />
          Refresh
        </button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Total Tests', value: total },
          { label: 'This Page', value: summary.visible },
          { label: 'Overdue', value: summary.overdue, color: 'text-red-500' },
          { label: 'Rows / Page', value: PAGE_SIZE },
        ].map(stat => (
          <div key={stat.label} className="bg-surface-lowest rounded-2xl border border-border-ghost p-5">
            <p className="text-[9px] font-black text-muted uppercase tracking-widest mb-1">{stat.label}</p>
            <p className={cn("text-3xl font-black font-technical text-foreground", stat.color)}>{mounted ? stat.value : '...'}</p>
          </div>
        ))}
      </div>

      <div className="bg-surface-lowest rounded-[2rem] border border-border-ghost overflow-hidden shadow-sm">
        <div className="p-5 border-b border-border-ghost/30 flex flex-col lg:flex-row gap-3 lg:items-center">
          <div className="flex-1 bg-surface-low rounded-2xl border border-border-ghost flex items-center px-4 group focus-within:border-primary/30 transition-all">
            <Search size={18} className="text-muted group-focus-within:text-primary transition-colors" />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search patient name, bill ID, patient ID..."
              className="flex-1 bg-transparent py-3 px-3 text-xs font-black outline-none text-foreground placeholder:text-muted/50"
            />
          </div>

          <select
            value={status}
            onChange={e => setStatus(e.target.value)}
            className="h-12 bg-surface-low border border-border-ghost rounded-2xl px-4 text-[10px] font-black uppercase tracking-widest text-foreground outline-none focus:border-primary/30"
          >
            {STATUS_OPTIONS.map(option => (
              <option key={option || 'all'} value={option}>
                {option ? option.replace(/_/g, ' ') : 'All statuses'}
              </option>
            ))}
          </select>
        </div>

        {isLoading && !data ? (
          <div className="flex flex-col items-center justify-center py-24 space-y-4">
            <div className="w-10 h-10 border-4 border-primary border-t-transparent rounded-full animate-spin" />
            <p className="text-[10px] font-black text-muted uppercase tracking-widest">Loading Tests...</p>
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center py-24 gap-3 text-red-500">
            <AlertCircle size={36} />
            <p className="text-[10px] font-black uppercase tracking-widest">{error.message || 'Unable to load tests'}</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-surface-low/50 border-b border-border-ghost/30">
                  {['Test Name', 'Status', 'Patient Name', 'Bill ID', 'Patient ID', 'ETA', 'Created', 'Action'].map(label => (
                    <th key={label} className="px-6 py-5 text-[10px] font-black text-muted uppercase tracking-[0.2em] whitespace-nowrap">
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border-ghost/10">
                {tests.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="px-8 py-24 text-center">
                      <div className="text-[10px] font-black text-muted uppercase tracking-widest">No tests found</div>
                    </td>
                  </tr>
                ) : tests.map((test: any, idx: number) => {
                  const overdue = test.eta &&
                    !['completed', 'cancelled'].includes(test.status) &&
                    new Date(test.eta).getTime() < Date.now();

                  return (
                    <motion.tr
                      key={test.test_instance_id}
                      initial={{ opacity: 0, y: 6 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: idx * 0.02 }}
                      className="hover:bg-surface-low/30 transition-colors"
                    >
                      <td className="px-6 py-5 min-w-64">
                        <p className="text-sm font-technical font-black text-foreground">
                          {test.test_name || `Test #${test.test_instance_id}`}
                        </p>
                        <p className="text-[9px] font-black text-muted uppercase tracking-widest mt-1">
                          {test.accession_no || `Sample #${test.sample_id || '-'}`}
                        </p>
                      </td>
                      <td className="px-6 py-5">
                        <span className={cn(
                          "inline-flex px-3 py-1 rounded-full text-[9px] font-black uppercase tracking-widest border",
                          STATUS_COLORS[test.status] || 'bg-surface-high border-border-ghost text-muted'
                        )}>
                          {(test.status || 'unknown').replace(/_/g, ' ')}
                        </span>
                      </td>
                      <td className="px-6 py-5 text-xs font-black text-foreground/80 uppercase tracking-widest whitespace-nowrap">
                        {test.patient_name || '-'}
                      </td>
                      <td className="px-6 py-5 text-xs font-technical font-black text-foreground whitespace-nowrap">
                        {test.bill_id || '-'}
                      </td>
                      <td className="px-6 py-5 text-xs font-technical font-black text-muted whitespace-nowrap">
                        {test.patient_id || '-'}
                      </td>
                      <td className="px-6 py-5 whitespace-nowrap">
                        <div className={cn(
                          "flex items-center gap-2 text-xs font-technical font-black",
                          overdue ? "text-red-500" : "text-foreground"
                        )}>
                          <Clock size={14} className={cn(overdue ? "text-red-500 animate-pulse" : "text-muted/40")} />
                          {mounted ? formatEta(test.eta) : '...'}
                        </div>
                      </td>
                      <td className="px-6 py-5 text-[10px] font-black text-muted uppercase tracking-widest whitespace-nowrap">
                        {mounted ? timeAgo(test.created_at) : '...'}
                      </td>
                      <td className="px-6 py-5">
                        {test.test_instance_id ? (
                          <Link
                            href={`/tests/${test.test_instance_id}`}
                            className="inline-flex items-center gap-2 px-3 py-2 bg-surface-low border border-border-ghost text-foreground rounded-xl text-[9px] font-black uppercase tracking-widest hover:bg-surface-high transition-all"
                          >
                            <Eye size={13} /> View
                          </Link>
                        ) : (
                          <span className="text-[9px] font-black text-muted uppercase tracking-widest">Unavailable</span>
                        )}
                      </td>
                    </motion.tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        <div className="px-5 py-4 border-t border-border-ghost/30 flex items-center justify-between gap-4">
          <p className="text-[10px] font-black text-muted uppercase tracking-widest">
            Page {page} of {totalPages} &middot; {total} tests
          </p>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page <= 1}
              className="p-2.5 bg-surface-low border border-border-ghost rounded-xl text-muted hover:text-foreground disabled:opacity-40 disabled:hover:text-muted transition-all"
              aria-label="Previous page"
            >
              <ChevronLeft size={16} />
            </button>
            <button
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
              className="p-2.5 bg-surface-low border border-border-ghost rounded-xl text-muted hover:text-foreground disabled:opacity-40 disabled:hover:text-muted transition-all"
              aria-label="Next page"
            >
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
