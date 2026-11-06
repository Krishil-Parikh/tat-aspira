"use client";
import React from 'react';
import useSWR from 'swr';
import { Server, Database, Zap, Webhook, RefreshCw, CheckCircle2, AlertTriangle } from 'lucide-react';
import { cn } from '@/components/ui/utils';
import { fetchSystemStatus } from '@/app/lib/api';
import { formatDateTime } from '@/app/lib/timeFormat';

function StatusPill({ ok, okText = 'Healthy', badText = 'Down' }: { ok: boolean; okText?: string; badText?: string }) {
  return (
    <span className={cn(
      "px-2.5 py-1 rounded-full text-[9px] font-black uppercase tracking-widest flex items-center gap-1",
      ok ? "bg-success/10 text-success-text" : "bg-red-500/10 text-red-500"
    )}>
      {ok ? <CheckCircle2 size={10} /> : <AlertTriangle size={10} />}{ok ? okText : badText}
    </span>
  );
}

export default function SettingsPage() {
  const { data, error, isLoading, mutate } = useSWR('systemStatus', fetchSystemStatus, { refreshInterval: 15000 });
  const wh = data?.webhooks ?? {};

  const services = data ? [
    { icon: Server,   label: 'API server',  ok: data.api?.ok,
      detail: `v${data.api?.version} · ${data.api?.environment}${data.api?.demo_mode ? ' · demo mode' : ''}` },
    { icon: Database, label: 'Database (PostgreSQL)', ok: data.database?.ok,
      detail: data.database?.ok ? `${data.database.latency_ms} ms` : data.database?.error },
    { icon: Zap,      label: 'Cache & task queue (Redis)', ok: data.redis?.ok,
      detail: data.redis?.ok ? `${data.redis.latency_ms} ms` : data.redis?.error },
  ] : [];

  return (
    <div className="max-w-4xl mx-auto space-y-8 pb-20">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-4xl font-black text-foreground tracking-tight">SYSTEM STATUS</h1>
          <p className="text-muted font-medium">Live health of the services behind the dashboard. Refreshes every 15 seconds.</p>
        </div>
        <button onClick={() => mutate()}
          className="px-4 py-2 rounded-xl bg-surface-low text-[10px] font-black uppercase tracking-widest flex items-center gap-2">
          <RefreshCw size={12} className={isLoading ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>

      {error && (
        <div className="p-4 bg-red-400/10 border border-red-400/30 rounded-xl text-[11px] font-black text-red-400">
          ⚠ Could not load system status: {error.message}
        </div>
      )}

      <section className="bg-surface-lowest p-7 rounded-3xl border border-border-ghost shadow-sm">
        <h3 className="text-[10px] font-black text-muted uppercase tracking-widest mb-6 flex items-center gap-2">
          <Server size={14} /> Services
        </h3>
        <div className="space-y-3">
          {services.map(s => (
            <div key={s.label} className="flex items-center justify-between p-4 rounded-2xl bg-surface-low">
              <div className="flex items-center gap-3">
                <s.icon size={16} className="text-primary" />
                <div>
                  <p className="text-sm font-black text-foreground">{s.label}</p>
                  <p className="text-[10px] text-muted font-bold">{s.detail}</p>
                </div>
              </div>
              <StatusPill ok={!!s.ok} />
            </div>
          ))}
          {!data && !error && <p className="text-xs text-muted">Loading…</p>}
        </div>
      </section>

      <section className="bg-surface-lowest p-7 rounded-3xl border border-border-ghost shadow-sm">
        <h3 className="text-[10px] font-black text-muted uppercase tracking-widest mb-6 flex items-center gap-2">
          <Webhook size={14} /> CrelioHealth event pipeline
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { label: 'Processed (24 h)', value: wh.processed_24h ?? '—' },
            { label: 'Waiting',          value: wh.waiting ?? '—', warn: (wh.waiting ?? 0) > 20 },
            { label: 'Failed',           value: wh.failed ?? '—', warn: (wh.failed ?? 0) > 0 },
            { label: 'Waiting for data', value: wh.awaiting_reconciliation ?? '—' },
          ].map(k => (
            <div key={k.label} className="p-4 rounded-2xl bg-surface-low">
              <p className="text-[9px] font-black uppercase tracking-widest text-muted mb-1">{k.label}</p>
              <p className={cn("text-2xl font-black", k.warn ? 'text-red-500' : 'text-foreground')}>{k.value}</p>
            </div>
          ))}
        </div>
        <p className="text-[10px] text-muted font-bold mt-4">
          Last event processed: {wh.last_processed_at ? formatDateTime(`${wh.last_processed_at}Z`) : '—'}
        </p>
        {(wh.recent_failures ?? []).length > 0 && (
          <div className="mt-6 space-y-2">
            <p className="text-[10px] font-black uppercase tracking-widest text-muted">Recent failures</p>
            {wh.recent_failures.map((f: any) => (
              <div key={f.id} className="p-3 rounded-xl bg-red-500/5 border border-red-500/20 text-[11px]">
                <span className="font-black">#{f.id} {f.webhook_type}</span> · bill {f.bill_id} — {f.error_message || 'no message'}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
