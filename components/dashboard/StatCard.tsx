"use client";
import React from 'react';
import { motion } from 'motion/react';
import { LucideIcon, TrendingUp, TrendingDown } from 'lucide-react';
import { cn } from '@/components/ui/utils';

interface StatCardProps {
  label: string;
  value: string | number;
  icon: LucideIcon;
  trend?: {
    value: number;
    isUp: boolean;
  };
}

export function StatCard({ label, value, icon: Icon, trend }: StatCardProps) {
  return (
    <motion.div
      whileHover={{ y: -4, backgroundColor: 'var(--surface-container-low)' }}
      className="bg-surface-lowest p-8 rounded-[2rem] border border-border-ghost transition-all flex flex-col justify-between"
    >
      <div className="flex items-start justify-between mb-8">
        <div className="p-3 bg-primary/5 text-primary rounded-xl">
          <Icon size={20} />
        </div>
        
        {trend && (
          <div className={cn(
            "flex items-center space-x-1 text-[9px] font-black uppercase tracking-widest px-2.5 py-1 rounded-full",
            trend.isUp ? "bg-success/10 text-success-text" : "bg-error/10 text-error-text"
          )}>
            {trend.isUp ? <TrendingUp size={10} /> : <TrendingDown size={10} />}
            <span>{trend.value}%</span>
          </div>
        )}
      </div>

      <div>
        <div className="text-4xl font-headline font-black text-foreground tracking-tighter leading-none mb-1">
          {typeof value === 'number' ? value.toLocaleString() : value}
        </div>
        <p className="text-[10px] font-black text-muted uppercase tracking-[0.2em]">
          {label}
        </p>
      </div>
    </motion.div>
  );
}
