"use client";
import React, { useState } from 'react';
import useSWR from 'swr';
import { motion, AnimatePresence } from 'motion/react';
import { Truck, Package, CheckCircle2, Clock, AlertCircle, Navigation, ChevronRight, RefreshCw, FlaskConical, MapPin } from 'lucide-react';
import { fetchPickupQueue, confirmPickup, confirmDelivery, fetchAllLabs } from '@/app/lib/api';
import { cn } from '@/components/ui/utils';

const PRIORITY_COLORS: Record<string, string> = {
  URGENT: 'bg-red-500/10 border-red-500/30 text-red-500',
  HIGH: 'bg-amber-500/10 border-amber-500/30 text-amber-500',
  NORMAL: 'bg-success/10 border-success/30 text-success-text',
  LOW: 'bg-surface-high border-border-ghost text-muted',
};

export default function LogisticsPage() {
  const [actionLoading, setActionLoading] = useState<number | null>(null);
  const [selectedLab, setSelectedLab] = useState<Record<number, number>>({});
  const [feedback, setFeedback] = useState<{ id: number; type: 'success' | 'error'; msg: string } | null>(null);

  const { data: queueData, isLoading, mutate } = useSWR('pickupQueue', fetchPickupQueue, { refreshInterval: 10000 });
  const { data: labsData } = useSWR('allLabs', fetchAllLabs, { refreshInterval: 30000 });

  const queue = queueData?.queue || [];
  const labs = labsData?.labs || [];

  const handlePickup = async (sampleId: number) => {
    setActionLoading(sampleId);
    try {
      await confirmPickup(sampleId);
      setFeedback({ id: sampleId, type: 'success', msg: 'Pickup confirmed! Sample in transit.' });
      mutate();
    } catch (e: any) {
      setFeedback({ id: sampleId, type: 'error', msg: e.message });
    } finally {
      setActionLoading(null);
    }
  };

  const handleDelivery = async (sampleId: number) => {
    const labId = selectedLab[sampleId];
    if (!labId) {
      setFeedback({ id: sampleId, type: 'error', msg: 'Please select destination lab first.' });
      return;
    }
    setActionLoading(sampleId);
    try {
      await confirmDelivery(sampleId, labId);
      setFeedback({ id: sampleId, type: 'success', msg: 'Delivered! SAMPLE_RECEIVED event fired.' });
      mutate();
    } catch (e: any) {
      setFeedback({ id: sampleId, type: 'error', msg: e.message });
    } finally {
      setActionLoading(null);
    }
  };

  const [refreshing, setRefreshing] = useState(false);
  const handleRefresh = async () => {
    setRefreshing(true);
    await mutate();
    // Small delay for visual feedback
    setTimeout(() => setRefreshing(false), 600);
  };

  return (
    <div className="space-y-8 pb-20">
      {/* Header */}
      <div className="flex items-end justify-between">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <div className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
            <span className="text-[10px] font-black text-muted uppercase tracking-widest">Logistics Command</span>
          </div>
          <h1 className="text-5xl font-black text-foreground tracking-tighter leading-none mb-2">LOGISTICS</h1>
          <p className="text-muted font-medium max-w-lg">
            Manage sample pickups, deliveries, and lab handovers. Confirming delivery fires the SAMPLE_RECEIVED event.
          </p>
        </div>
        <button 
          suppressHydrationWarning 
          onClick={handleRefresh} 
          disabled={refreshing || isLoading}
          className="flex items-center gap-2 px-4 py-2.5 bg-surface-low border border-border-ghost rounded-xl text-[10px] font-black uppercase tracking-widest text-muted hover:text-foreground transition-all disabled:opacity-50"
        >
          <RefreshCw size={14} className={cn(refreshing || isLoading ? "animate-spin" : "")} />
          {refreshing || isLoading ? "Syncing..." : "Refresh"}
        </button>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: 'Awaiting Pickup', value: queue.filter((s: any) => s.status === 'routed' || s.status === 'pending').length, icon: Package, color: 'text-amber-500' },
          { label: 'In Transit', value: queue.filter((s: any) => s.status === 'in_transit').length, icon: Truck, color: 'text-primary' },
          { label: 'Delivered Today', value: queue.filter((s: any) => s.status === 'arrived').length, icon: CheckCircle2, color: 'text-success-text' },
        ].map((stat) => (
          <div key={stat.label} className="bg-surface-lowest rounded-2xl border border-border-ghost p-5 flex items-center gap-4">
            <div className="w-10 h-10 rounded-xl bg-surface-low flex items-center justify-center">
              <stat.icon size={20} className={stat.color} />
            </div>
            <div>
              <p className="text-[9px] font-black text-muted uppercase tracking-widest">{stat.label}</p>
              <p className="text-2xl font-black font-technical text-foreground">{stat.value}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Pickup Queue */}
      <div className="bg-surface-lowest rounded-3xl border border-border-ghost overflow-hidden">
        <div className="px-8 py-6 border-b border-border-ghost flex items-center gap-3">
          <Package className="text-primary" size={20} />
          <h2 className="text-lg font-headline font-black uppercase tracking-widest">Pickup & Delivery Queue</h2>
          <span className="ml-auto px-3 py-1 rounded-full bg-primary/10 text-primary text-[10px] font-black">{queue.length} samples</span>
        </div>

        {isLoading ? (
          <div className="flex flex-col items-center justify-center py-20 space-y-4">
            <div className="w-10 h-10 border-4 border-primary border-t-transparent rounded-full animate-spin" />
            <p className="text-[10px] font-black text-muted uppercase tracking-widest">Loading Queue...</p>
          </div>
        ) : queue.length === 0 ? (
          <div className="text-center py-20">
            <CheckCircle2 size={40} className="text-success-text mx-auto mb-4 opacity-40" />
            <p className="text-[10px] font-black text-muted uppercase tracking-[0.3em]">All clear — no pending pickups</p>
          </div>
        ) : (
          <div className="divide-y divide-border-ghost">
            {queue.map((sample: any) => {
              const isLoading_ = actionLoading === sample.id;
              const fb = feedback?.id === sample.id ? feedback : null;
              return (
                <motion.div
                  key={sample.id}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  className="px-8 py-5 flex flex-col md:flex-row md:items-center gap-4"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3 mb-1">
                      <span className="font-technical font-black text-foreground text-sm">{sample.accession_no || `#${sample.id}`}</span>
                      <span className={cn("px-2 py-0.5 rounded-full border text-[9px] font-black uppercase", PRIORITY_COLORS[sample.priority] || PRIORITY_COLORS.NORMAL)}>
                        {sample.priority}
                      </span>
                      <span className="px-2 py-0.5 rounded-full bg-surface-high text-[9px] font-black uppercase text-muted">{sample.status}</span>
                    </div>
                    <p className="text-sm font-medium text-muted truncate">{sample.patient_name} · Bill #{sample.external_bill_id}</p>
                    
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-2">
                      <div className="flex items-center gap-1.5">
                        <MapPin size={12} className="text-amber-500" />
                        <span className="text-[8px] font-bold text-muted uppercase tracking-widest">Pickup:</span>
                        <p className="text-[10px] font-black uppercase tracking-widest text-foreground">{sample.pickup_location || 'Collection Center'}</p>
                      </div>
                      
                      <div className="flex items-center gap-1.5">
                        <Navigation size={12} className="text-primary" />
                        <span className="text-[8px] font-bold text-muted uppercase tracking-widest">Drop:</span>
                        <p className="text-[10px] font-black uppercase tracking-widest text-primary">{sample.drop_location || 'Pending Lab'}</p>
                      </div>
                    </div>
                  </div>

                  {fb && (
                    <div className={cn("text-[10px] font-black uppercase tracking-wide px-3 py-2 rounded-xl border", fb.type === 'success' ? 'bg-success/10 border-success/30 text-success-text' : 'bg-red-400/10 border-red-400/30 text-red-400')}>
                      {fb.msg}
                    </div>
                  )}

                  <div className="flex items-center gap-3">
                    {/* Delivery lab selector */}
                    {sample.status !== 'in_transit' ? (
                      <button
                        suppressHydrationWarning
                        disabled={isLoading_}
                        onClick={() => handlePickup(sample.id)}
                        className="px-5 py-2.5 bg-amber-500/10 border border-amber-500/30 text-amber-500 rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-amber-500/20 transition-all disabled:opacity-50 flex items-center gap-2"
                      >
                        {isLoading_ ? <RefreshCw size={12} className="animate-spin" /> : <Package size={14} />}
                        Confirm Pickup
                      </button>
                    ) : (
                      <div className="flex items-center gap-2">
                        <select
                          value={selectedLab[sample.id] || ''}
                          onChange={(e) => setSelectedLab(prev => ({ ...prev, [sample.id]: Number(e.target.value) }))}
                          className="bg-surface-low border-none rounded-xl py-2.5 px-3 text-[10px] font-black uppercase text-foreground outline-none focus:ring-2 focus:ring-primary"
                        >
                          <option value="">Select Lab</option>
                          {labs.map((lab: any) => (
                            <option key={lab.id} value={lab.id}>{lab.lab_name}</option>
                          ))}
                        </select>
                        <button
                          suppressHydrationWarning
                          disabled={isLoading_}
                          onClick={() => handleDelivery(sample.id)}
                          className="px-5 py-2.5 bg-primary text-white rounded-xl text-[10px] font-black uppercase tracking-widest hover:opacity-90 transition-all disabled:opacity-50 flex items-center gap-2 shadow-lg shadow-primary/20"
                        >
                          {isLoading_ ? <RefreshCw size={12} className="animate-spin" /> : <CheckCircle2 size={14} />}
                          Confirm Delivery
                        </button>
                      </div>
                    )}
                  </div>
                </motion.div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
