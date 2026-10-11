"use client";

import React from 'react';
import { motion } from 'motion/react';
import { Activity, AlertTriangle, CheckCircle2, TrendingDown, Zap } from 'lucide-react';
import { cn } from '@/components/ui/utils';
import { formatMinutesToHrMin } from '@/app/lib/timeFormat';

interface LabMetric {
  id: number;
  lab_name: string;
  lab_code: string;
  is_available: boolean;
  max_concurrent_samples: number;
  queue_size: number;
  avg_tat_mins: number;
  sla_percent: number;
  delayed_tests: number;
  active_batches: number;
  utilization_percent: number;
  status: 'healthy' | 'overloaded' | 'delayed' | 'at_risk';
  total_tests_processed: number;
}

interface LabMetricsTableProps {
  labs: LabMetric[];
  loading?: boolean;
  onLabClick?: (labId: number) => void;
}

export default function LabMetricsTable({
  labs,
  loading = false,
  onLabClick,
}: LabMetricsTableProps) {
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'healthy':
        return 'bg-success/10 border-success/30 text-success-text';
      case 'delayed':
        return 'bg-red-400/10 border-red-400/30 text-red-400';
      case 'overloaded':
        return 'bg-amber-500/10 border-amber-500/30 text-amber-500';
      case 'at_risk':
        return 'bg-blue-500/10 border-blue-500/30 text-blue-500';
      default:
        return 'bg-surface-low border-border-ghost text-muted';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'healthy':
        return <CheckCircle2 size={14} />;
      case 'delayed':
        return <AlertTriangle size={14} />;
      case 'overloaded':
        return <Zap size={14} />;
      case 'at_risk':
        return <TrendingDown size={14} />;
      default:
        return <Activity size={14} />;
    }
  };

  const getStatusLabel = (status: string) => {
    return status.charAt(0).toUpperCase() + status.slice(1);
  };

  if (loading) {
    return (
      <div className="bg-surface-lowest rounded-3xl border border-border-ghost p-8">
        <div className="space-y-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-16 bg-surface-low rounded-xl animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  if (labs.length === 0) {
    return (
      <div className="bg-surface-lowest rounded-3xl border border-border-ghost p-8 text-center">
        <p className="text-muted font-bold text-[10px] uppercase tracking-widest">
          No labs found
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {labs.map((lab, idx) => (
        <motion.div
          key={lab.id}
          initial={{ opacity: 0, x: -10 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: idx * 0.05 }}
          onClick={() => onLabClick?.(lab.id)}
          className={cn(
            "bg-surface-lowest rounded-2xl border border-border-ghost p-5 transition-all",
            onLabClick && "cursor-pointer hover:border-primary/50 hover:shadow-md"
          )}
        >
          {/* Header Row: Name + Status */}
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="font-headline font-black text-foreground">{lab.lab_name}</h3>
              <p className="text-[9px] text-muted font-bold uppercase tracking-widest mt-1">
                {lab.lab_code}
              </p>
            </div>
            <div className={cn(
              "px-3 py-1.5 rounded-full border flex items-center gap-1.5 text-[9px] font-black uppercase",
              getStatusColor(lab.status)
            )}>
              {getStatusIcon(lab.status)}
              {getStatusLabel(lab.status)}
            </div>
          </div>

          {/* Metrics Grid */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-[9px]">
            {/* Queue Size */}
            <div className="bg-surface-low rounded-lg p-3">
              <p className="text-muted font-bold uppercase tracking-widest mb-1">Queue</p>
              <p className="font-technical font-black text-lg text-foreground">
                {lab.queue_size}
              </p>
              <p className="text-[8px] text-muted mt-1">
                active entries
              </p>
            </div>

            {/* Avg TAT */}
            <div className="bg-surface-low rounded-lg p-3">
              <p className="text-muted font-bold uppercase tracking-widest mb-1">Avg TAT</p>
              <p className="font-technical font-black text-lg text-primary">
                {formatMinutesToHrMin(lab.avg_tat_mins)}
              </p>
              <p className="text-[8px] text-muted mt-1">
                elapsed
              </p>
            </div>

            {/* SLA % */}
            <div className="bg-surface-low rounded-lg p-3">
              <p className="text-muted font-bold uppercase tracking-widest mb-1">SLA</p>
              <p className={cn(
                "font-technical font-black text-lg",
                (lab.sla_percent || 0) > 90 ? 'text-success-text' : 'text-amber-500'
              )}>
                {lab.sla_percent || 0}%
              </p>
              <p className="text-[8px] text-muted mt-1">
                compliance
              </p>
            </div>

            {/* Delayed Tests */}
            <div className="bg-surface-low rounded-lg p-3">
              <p className="text-muted font-bold uppercase tracking-widest mb-1">Delayed</p>
              <p className={cn(
                "font-technical font-black text-lg",
                lab.delayed_tests > 0 ? 'text-red-400' : 'text-success-text'
              )}>
                {lab.delayed_tests}
              </p>
              <p className="text-[8px] text-muted mt-1">
                tests
              </p>
            </div>

            {/* Utilization */}
            <div className="bg-surface-low rounded-lg p-3">
              <p className="text-muted font-bold uppercase tracking-widest mb-1">Util.</p>
              <p className={cn(
                "font-technical font-black text-lg",
                lab.utilization_percent > 80 ? 'text-amber-500' : 'text-foreground'
              )}>
                {lab.utilization_percent}%
              </p>
              <p className="text-[8px] text-muted mt-1">
                capacity
              </p>
            </div>
          </div>

          {/* Bottom Row: Active Batches + Tests */}
          <div className="mt-4 pt-3 border-t border-border-ghost flex items-center justify-between text-[9px]">
            <div>
              <span className="text-muted font-bold uppercase tracking-widest">
                Active Batches:
              </span>
              <span className="font-technical font-black text-foreground ml-2">
                {lab.active_batches}
              </span>
            </div>
            <div>
              <span className="text-muted font-bold uppercase tracking-widest">
                Total Processed:
              </span>
              <span className="font-technical font-black text-foreground ml-2">
                {lab.total_tests_processed}
              </span>
            </div>
            {!lab.is_available && (
              <div className="px-2 py-1 rounded bg-red-400/10 border border-red-400/30 text-red-400 font-bold">
                UNAVAILABLE
              </div>
            )}
          </div>
        </motion.div>
      ))}
    </div>
  );
}
