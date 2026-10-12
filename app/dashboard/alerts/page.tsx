"use client";
import React, { useState } from 'react';
import useSWR from 'swr';
import { motion, AnimatePresence } from 'motion/react';
import {
  Bell,
  CheckCircle2,
  AlertTriangle,
  ShieldAlert,
  Info,
  RefreshCw,
} from 'lucide-react';
import { cn } from '@/components/ui/utils';
import { DateTime } from '@/components/ui/DateTime';
import { fetchAuditLog } from '@/app/lib/api';

// Map backend event_type → display level
function getLevel(event_type: string): 'high' | 'warning' | 'info' {
  const t = (event_type || '').toLowerCase();
  if (t.includes('breach') || t.includes('escalation') || t.includes('error')) return 'high';
  if (t.includes('delay') || t.includes('missed') || t.includes('downtime')) return 'warning';
  return 'info';
}

function humanEvent(event_type: string): string {
  return (event_type || '').replace(/_/g, ' ').toUpperCase();
}

function formatMessage(log: any): string {
  return log.notes || log.message || humanEvent(log.event_type);
}

function ShieldCheckIcon({ className, size }: { className?: string; size?: number }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      <path d="m9 12 2 2 4-4" />
    </svg>
  );
}

export default function AlertsPage() {
  const [dismissed, setDismissed] = useState<Set<number>>(new Set());
  const [readSet, setReadSet]     = useState<Set<number>>(new Set());

  const { data, isLoading, mutate } = useSWR(
    'alerts',
    () => fetchAuditLog({ limit: 50 }),
    { refreshInterval: 12000 }
  );

  const [refreshing, setRefreshing] = useState(false);
  const handleRefresh = async () => {
    setRefreshing(true);
    await mutate();
    setTimeout(() => setRefreshing(false), 600);
  };

  const rawLogs: any[] = data?.notifications || [];

  // Filter dismissed
  const alerts = rawLogs.filter(a => !dismissed.has(a.id));
  const unreadCount = alerts.filter(a => !readSet.has(a.id)).length;

  const acknowledgeAll = () => {
    setReadSet(new Set(alerts.map((a: any) => a.id)));
  };

  const markRead = (id: number) => {
    setReadSet(prev => new Set([...prev, id]));
  };

  const dismissAlert = (id: number) => {
    setDismissed(prev => new Set([...prev, id]));
  };

  return (
    <div className="max-w-[1000px] mx-auto space-y-10 pb-20">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-8">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Bell size={16} className="text-primary" />
            <span className="text-[10px] font-black text-muted uppercase tracking-widest">Protocol Intelligence</span>
          </div>
          <h1 className="text-5xl font-black text-foreground tracking-tighter leading-none mb-3">ALERTS</h1>
          <p className="text-muted font-medium max-w-lg">
            Operational exceptions and protocol breaches detected by the governance engine.
          </p>
        </div>

        <div className="flex items-center gap-3">
          {unreadCount > 0 && (
            <div className="px-4 py-2 bg-error/10 rounded-xl border border-error/20 text-[10px] font-black text-error-text uppercase tracking-widest">
              {unreadCount} Unread
            </div>
          )}
          <button
            onClick={handleRefresh}
            className="flex items-center gap-2 px-5 py-3 bg-surface-lowest border border-border-ghost rounded-2xl text-[10px] font-black text-muted uppercase tracking-widest hover:bg-surface-low transition-all"
          >
            <RefreshCw size={14} className={cn((refreshing || isLoading) && 'animate-spin')} />
            Sync
          </button>
          {alerts.length > 0 && (
            <button
              onClick={acknowledgeAll}
              className="flex items-center gap-2 px-6 py-3 bg-surface-lowest border border-border-ghost rounded-2xl text-[10px] font-black text-muted uppercase tracking-widest hover:bg-surface-low transition-all"
            >
              <CheckCircle2 size={14} />
              Acknowledge All
            </button>
          )}
        </div>
      </div>

      {/* Loading state */}
      {isLoading && !data && (
        <div className="flex flex-col items-center justify-center py-20 gap-4">
          <div className="w-10 h-10 border-4 border-primary border-t-transparent rounded-full animate-spin" />
          <p className="text-[10px] font-black text-muted uppercase tracking-widest">Loading Alerts...</p>
        </div>
      )}

      {/* Alert list */}
      {!isLoading || data ? (
        <div className="space-y-4">
          {alerts.length === 0 ? (
            <div className="bg-surface-lowest border border-border-ghost border-dashed rounded-[2rem] py-20 text-center">
              <ShieldCheckIcon size={48} className="mx-auto text-muted/20 mb-4" />
              <p className="text-[10px] font-black text-muted uppercase tracking-[0.3em]">Operational Horizon Clear</p>
              {rawLogs.length > 0 && dismissed.size > 0 && (
                <p className="text-[9px] text-muted/50 mt-2">{dismissed.size} dismissed events hidden</p>
              )}
            </div>
          ) : (
            <AnimatePresence mode="popLayout">
              {alerts.map((log: any) => {
                const level = getLevel(log.event_type);
                const isRead = readSet.has(log.id);
                return (
                  <motion.div
                    key={log.id}
                    layout
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, scale: 0.95, height: 0 }}
                    transition={{ duration: 0.2 }}
                    onClick={() => markRead(log.id)}
                    className={cn(
                      "p-8 rounded-[2rem] border transition-all flex items-start gap-6 group cursor-pointer",
                      isRead
                        ? "bg-surface-low/50 border-border-ghost grayscale opacity-50"
                        : level === 'high'
                          ? "bg-surface-lowest border-red-400/20 shadow-sm shadow-red-400/5 hover:border-red-400/40"
                          : level === 'warning'
                            ? "bg-surface-lowest border-amber-400/20 shadow-sm hover:border-amber-400/40"
                            : "bg-surface-lowest border-border-ghost shadow-sm hover:border-primary/20"
                    )}
                  >
                    {/* Icon */}
                    <div className={cn(
                      "shrink-0 mt-1.5 p-2.5 rounded-xl",
                      level === 'high'    ? "bg-red-400/10 text-red-400" :
                      level === 'warning' ? "bg-amber-400/10 text-amber-500" :
                      "bg-primary/10 text-primary"
                    )}>
                      {level === 'high'    ? <ShieldAlert size={20} /> :
                       level === 'warning' ? <AlertTriangle size={20} /> :
                       <Info size={20} />}
                    </div>

                    {/* Content */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between mb-2">
                        <span className={cn(
                          "text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-md border",
                          level === 'high'    ? "border-red-400/30 text-red-400" :
                          level === 'warning' ? "border-amber-400/30 text-amber-500" :
                          "border-primary/20 text-primary"
                        )}>
                          {humanEvent(log.event_type)}
                        </span>
                        <div className="flex items-center gap-2">
                          <p className="text-[10px] font-black text-muted uppercase tracking-widest">
                            <DateTime date={log.event_timestamp || log.created_at} />
                          </p>
                          {!isRead && (
                            <span className="w-1.5 h-1.5 rounded-full bg-primary ring-4 ring-primary/10" />
                          )}
                        </div>
                      </div>
                      <h3 className="text-base font-headline font-black text-foreground leading-tight mb-3 uppercase tracking-tight">
                        {formatMessage(log)}
                      </h3>
                      {log.sample_id && (
                        <div className="inline-flex items-center gap-2 px-3 py-1 bg-surface-low rounded-lg text-[10px] font-technical font-black text-primary uppercase">
                          Sample #{log.sample_id}
                        </div>
                      )}
                    </div>

                    {/* Actions */}
                    <div className="flex flex-col gap-2 shrink-0">
                      <button
                        onClick={e => { e.stopPropagation(); dismissAlert(log.id); }}
                        className="p-3 bg-surface-low rounded-xl text-muted hover:text-error-text transition-all opacity-0 group-hover:opacity-100 text-[9px] font-black uppercase"
                      >
                        ✕
                      </button>
                    </div>
                  </motion.div>
                );
              })}
            </AnimatePresence>
          )}
        </div>
      ) : null}
    </div>
  );
}
