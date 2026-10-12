"use client";
import React, { useState, useEffect } from 'react';
import { motion } from 'motion/react';
import { Shield, Server, Cpu, CheckCircle2 } from 'lucide-react';
import { cn } from '@/components/ui/utils';

// ─── Mock infra status (all green for the demo) ───────────────────────────────

const SERVICES = [
  { label: 'Edge Gateway',          status: 'healthy',   detail: 'FastAPI 0.110 · 0.0.0.0:8000' },
  { label: 'Hot Storage (Redis)',   status: 'active',    detail: 'Redis 7.2 · :6379 · 2.1 ms RTT' },
  { label: 'Cold Storage (MongoDB)',status: 'connected', detail: 'MongoDB 6.0 · lab_tat · 4 collections' },
  { label: 'Sample Worker Pool',    status: 'healthy',   detail: 'Celery · 8 threads · sample-processing' },
  { label: 'Result Worker Pool',    status: 'healthy',   detail: 'Celery · 4 threads · result-processing' },
  { label: 'Alert Worker Pool',     status: 'active',    detail: 'Celery · 2 threads · alert-processing' },
  { label: 'Projection Cache',      status: 'healthy',   detail: 'Celery · 2 threads · projection' },
];

function useUptime() {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    // Start at a realistic-looking uptime offset (4h 12m 33s)
    const base = 4 * 3600 + 12 * 60 + 33;
    setElapsed(base);
    const t = setInterval(() => setElapsed(e => e + 1), 1000);
    return () => clearInterval(t);
  }, []);

  const h  = String(Math.floor(elapsed / 3600)).padStart(2, '0');
  const m  = String(Math.floor((elapsed % 3600) / 60)).padStart(2, '0');
  const s  = String(elapsed % 60).padStart(2, '0');
  return `${h}:${m}:${s}`;
}

export default function SettingsPage() {
  const uptime = useUptime();
  const [heartbeat, setHeartbeat] = useState('');

  useEffect(() => {
    const tick = () => setHeartbeat(new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }));
    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="max-w-4xl mx-auto space-y-8 pb-20">
      <div>
        <h1 className="text-4xl font-black text-foreground tracking-tight">SYSTEM CONFIG</h1>
        <p className="text-muted font-medium">Infrastructure health and core parameter management</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Left: Node status */}
        <div className="space-y-6">
          <section className="bg-surface-lowest p-7 rounded-3xl border border-border-ghost shadow-sm">
            <h3 className="text-[10px] font-black text-muted uppercase tracking-widest mb-6 flex items-center gap-2">
              <Server size={14} />
              Node Infrastructure
            </h3>

            <div className="space-y-4">
              {SERVICES.map(svc => (
                <motion.div
                  key={svc.label}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  className="flex items-center justify-between border-b border-border-ghost/10 pb-4 last:border-0 last:pb-0 group"
                >
                  <div>
                    <span className="text-sm font-bold text-foreground/80">{svc.label}</span>
                    <p className="text-[9px] font-technical font-black text-muted uppercase tracking-widest mt-0.5">
                      {svc.detail}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="text-[9px] font-black uppercase tracking-widest text-success-text">
                      {svc.status}
                    </span>
                    <CheckCircle2 size={14} className="text-success-text" />
                  </div>
                </motion.div>
              ))}
            </div>
          </section>

          {/* Security toggles */}
          <section className="bg-surface-lowest p-7 rounded-3xl border border-border-ghost shadow-sm">
            <h3 className="text-[10px] font-black text-muted uppercase tracking-widest mb-6 flex items-center gap-2">
              <Shield size={14} />
              Security &amp; Policy
            </h3>
            <div className="space-y-5">
              {[
                ['Auto-purge expired cache',  true],
                ['SLA Breach Alerts',         true],
                ['Idempotency TTL (48 h)',     true],
                ['Email Alert Dispatch',      false],
              ].map(([label, on]) => (
                <div key={String(label)} className="flex items-center justify-between">
                  <span className="text-sm font-bold text-muted">{String(label)}</span>
                  <div className={cn(
                    "w-10 h-5 rounded-full relative transition-colors",
                    on ? "bg-primary" : "bg-surface-high"
                  )}>
                    <div className={cn(
                      "absolute top-1 w-3 h-3 bg-white rounded-full transition-all",
                      on ? "right-1" : "left-1"
                    )} />
                  </div>
                </div>
              ))}
            </div>
          </section>
        </div>

        {/* Right: Instance card + identity */}
        <div className="space-y-6">
          <div className="bg-primary p-8 rounded-3xl text-white shadow-2xl shadow-primary/30 relative overflow-hidden">
            <Cpu className="absolute top-[-20px] right-[-20px] w-32 h-32 text-white/10" />
            <div className="relative z-10">
              <h3 className="text-xl font-black mb-1">Instance Frontier-01</h3>
              <p className="text-sm text-white/60 mb-6">Next.js 15 + FastAPI 0.110 · Synchronized</p>

              <div className="p-4 bg-white/10 rounded-2xl backdrop-blur-sm border border-white/10 mb-4">
                <div className="text-[10px] font-black uppercase tracking-widest text-white/50 mb-1">Process Uptime</div>
                <div className="text-2xl font-mono font-bold tracking-tighter">{uptime}</div>
              </div>

              <div className="grid grid-cols-3 gap-3">
                {[
                  { label: 'Workers', value: '7' },
                  { label: 'Threads', value: '16' },
                  { label: 'Queue Depth', value: '0' },
                ].map(item => (
                  <div key={item.label} className="p-3 bg-white/10 rounded-xl text-center">
                    <div className="text-lg font-black font-mono">{item.value}</div>
                    <div className="text-[8px] font-black text-white/50 uppercase tracking-widest">{item.label}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <section className="bg-surface-lowest p-7 rounded-3xl border border-border-ghost shadow-sm">
            <h3 className="text-[10px] font-black text-muted uppercase tracking-widest mb-5">Instance Identity</h3>
            <div className="space-y-3">
              {[
                ['UUID',          'aspira_prod_3391'],
                ['Region',        'ap-south-1 (Mumbai)'],
                ['Environment',   'Production Demo'],
                ['Last Heartbeat', heartbeat],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between items-center border-b border-border-ghost/10 pb-2 last:border-0">
                  <span className="text-[10px] font-black text-muted uppercase tracking-widest">{k}</span>
                  <span className="text-[10px] font-technical font-black text-foreground/70">{v}</span>
                </div>
              ))}
            </div>
            <button className="w-full mt-6 py-3 bg-surface-low text-muted font-black text-[10px] uppercase tracking-widest rounded-xl hover:bg-surface-high transition-all">
              Rotate Access Tokens
            </button>
          </section>
        </div>
      </div>
    </div>
  );
}
