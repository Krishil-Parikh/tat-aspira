"use client";
import React, { useEffect, useState } from 'react';
import useSWR from 'swr';
import { ShieldAlert, Terminal, ArrowRight, Loader2, Search } from 'lucide-react';
import { fetchAllAuditLogs } from '@/app/lib/api';
import Link from 'next/link';

export default function AuditLogPage() {
  const [mounted, setMounted] = useState(false);
  const [limit, setLimit] = useState(100);
  
  useEffect(() => {
    setMounted(true);
  }, []);

  const { data, error, isLoading } = useSWR(mounted ? ['auditLog', limit] : null, () => fetchAllAuditLogs(limit, 0), {
    refreshInterval: 15000
  });

  if (!mounted) return null;

  return (
    <div className="space-y-8 pb-20">
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-8">
        <div>
          <h1 className="text-5xl font-black text-foreground tracking-tighter leading-none mb-3">
            SYSTEM <span className="text-primary text-2xl">AUDIT LOG</span>
          </h1>
          <p className="text-muted font-medium max-w-lg">Immutable event trail for all webhook actions, routing decisions, and SLA alerts.</p>
        </div>
        <div className="flex items-center gap-3 bg-surface-lowest p-2 rounded-2xl border border-border-ghost">
          <Terminal size={18} className="text-muted ml-2" />
          <div className="px-4 py-2 bg-surface-high rounded-xl text-[10px] font-black uppercase tracking-widest text-foreground">
            {data?.total || 0} Events Recorded
          </div>
        </div>
      </div>

      <div className="bg-surface-lowest rounded-3xl border border-border-ghost overflow-hidden">
        <div className="px-8 py-6 border-b border-border-ghost flex items-center justify-between">
          <h2 className="text-lg font-headline font-black uppercase tracking-widest flex items-center gap-2">
            <ShieldAlert size={18} className="text-primary" /> Event Stream
          </h2>
          <div className="relative group">
            <div className="absolute inset-y-0 left-4 flex items-center pointer-events-none">
              <Search size={14} className="text-muted group-focus-within:text-primary transition-colors" />
            </div>
            <input
              type="text"
              placeholder="SEARCH LOGS..."
              className="w-full md:w-64 pl-10 pr-4 py-2.5 bg-surface-high border-none rounded-xl text-[10px] font-black uppercase tracking-widest text-foreground placeholder:text-muted focus:ring-2 focus:ring-primary/20 outline-none transition-all"
            />
          </div>
        </div>

        {isLoading ? (
          <div className="p-20 flex flex-col items-center justify-center text-muted">
            <Loader2 className="animate-spin mb-4 text-primary" size={32} />
            <p className="text-[10px] font-black uppercase tracking-widest">Decrytping Audit Trail...</p>
          </div>
        ) : error ? (
          <div className="p-20 text-center text-red-500 font-bold">Failed to load audit logs.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left whitespace-nowrap">
              <thead className="bg-surface-high/50 border-b border-border-ghost">
                <tr>
                  <th className="px-8 py-4 text-[10px] font-black text-muted uppercase tracking-widest">Timestamp</th>
                  <th className="px-8 py-4 text-[10px] font-black text-muted uppercase tracking-widest">Event Type</th>
                  <th className="px-8 py-4 text-[10px] font-black text-muted uppercase tracking-widest">Details</th>
                  <th className="px-8 py-4 text-[10px] font-black text-muted uppercase tracking-widest">Sample / Bill</th>
                  <th className="px-8 py-4 text-[10px] font-black text-muted uppercase tracking-widest text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-ghost">
                {data?.logs?.map((log: any) => (
                  <tr key={log.id} className="hover:bg-surface-high/20 transition-colors">
                    <td className="px-8 py-4">
                      <p className="font-bold text-xs">{new Date(log.event_timestamp).toLocaleDateString()}</p>
                      <p className="text-[10px] font-technical text-muted">{new Date(log.event_timestamp).toLocaleTimeString()}</p>
                    </td>
                    <td className="px-8 py-4">
                      <span className="px-3 py-1 bg-surface-high text-[9px] font-black uppercase tracking-widest rounded-full">
                        {log.event_type.replace(/_/g, ' ')}
                      </span>
                    </td>
                    <td className="px-8 py-4">
                      <p className="text-xs font-medium text-foreground max-w-sm truncate" title={log.notes}>
                        {log.notes || 'System action recorded.'}
                      </p>
                    </td>
                    <td className="px-8 py-4">
                      <div className="flex flex-col">
                        <span className="text-[10px] font-black text-primary uppercase tracking-widest">{log.external_bill_id || 'N/A'}</span>
                        <span className="text-[9px] text-muted font-bold uppercase">{log.patient_name || '-'}</span>
                      </div>
                    </td>
                    <td className="px-8 py-4 text-right">
                      {log.sample_id && (
                        <Link href={`/dashboard/reports/${log.sample_id}`} className="inline-flex items-center gap-1 text-[10px] font-black uppercase tracking-widest text-primary hover:underline">
                          View <ArrowRight size={12} />
                        </Link>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        
        {data?.logs?.length === limit && (
          <div className="p-6 border-t border-border-ghost flex justify-center">
            <button 
              onClick={() => setLimit(l => l + 100)}
              className="px-6 py-2 bg-surface-high hover:bg-surface-high/80 text-[10px] font-black uppercase tracking-widest rounded-xl transition-colors"
            >
              Load More Events
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
