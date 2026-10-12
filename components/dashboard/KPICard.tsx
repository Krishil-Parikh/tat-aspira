"use client";

import React from 'react';
import { motion } from 'motion/react';
import { LucideIcon } from 'lucide-react';
import { cn } from '@/components/ui/utils';
import { formatMinutesToHrMin } from '@/app/lib/timeFormat';

interface KPICardProps {
  title: string;
  value: string | number;
  unit?: string;
  icon: LucideIcon;
  trend?: 'up' | 'down' | 'neutral';
  trendPercent?: number;
  description?: string;
  color?: 'primary' | 'success' | 'warning' | 'danger' | 'info';
  onClick?: () => void;
  loading?: boolean;
  mini?: boolean;
  isTimeFormat?: boolean; // If true, format value as hr:mm
}

export default function KPICard({
  title,
  value,
  unit,
  icon: Icon,
  trend,
  trendPercent,
  description,
  color = 'primary',
  onClick,
  loading = false,
  mini = false,
  isTimeFormat = false,
}: KPICardProps) {
  const colorClasses = {
    primary: 'bg-primary/10 border-primary/30 text-primary',
    success: 'bg-success/10 border-success/30 text-success-text',
    warning: 'bg-amber-500/10 border-amber-500/30 text-amber-500',
    danger: 'bg-red-400/10 border-red-400/30 text-red-400',
    info: 'bg-blue-500/10 border-blue-500/30 text-blue-500',
  };

  // Format value for display
  const displayValue = isTimeFormat && typeof value === 'number' 
    ? formatMinutesToHrMin(value) 
    : value;

  const textColorClasses = {
    primary: 'text-primary',
    success: 'text-success-text',
    warning: 'text-amber-500',
    danger: 'text-red-400',
    info: 'text-blue-500',
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      onClick={onClick}
      className={cn(
        "rounded-xl border transition-all cursor-pointer",
        mini 
          ? "p-4 bg-surface-low border-border-ghost hover:border-primary/50 hover:shadow-md"
          : "p-6 bg-surface-lowest border-border-ghost hover:border-primary/50 hover:shadow-lg",
        onClick && "hover:shadow-lg"
      )}
    >
      <div className={cn("flex items-start justify-between", mini && "flex-col")}>
        <div className={cn("flex-1", mini && "w-full")}>
          <div className="flex items-center gap-2 mb-2">
            <div className={cn(
              "p-2 rounded-lg border",
              colorClasses[color]
            )}>
              <Icon size={mini ? 16 : 20} />
            </div>
            <p className={cn(
              "text-[9px] font-black uppercase tracking-widest text-muted",
              mini && "text-[8px]"
            )}>
              {title}
            </p>
          </div>

          {/* Value Section */}
          <div className={mini ? "mt-2" : "mt-4"}>
            <div className="flex items-baseline gap-1">
              {loading ? (
                <div className="h-8 w-16 bg-surface-high animate-pulse rounded" />
              ) : (
                <>
                  <span className={cn(
                    "font-black font-technical",
                    mini ? "text-2xl" : "text-4xl",
                    textColorClasses[color]
                  )}>
                    {displayValue}
                  </span>
                  {unit && (
                    <span className="text-[10px] font-bold text-muted ml-1">
                      {unit}
                    </span>
                  )}
                </>
              )}
            </div>

            {/* Trend */}
            {trend && trendPercent !== undefined && (
              <div className={cn(
                "flex items-center gap-1 mt-2 text-[10px] font-bold",
                trend === 'up' ? 'text-success-text' :
                trend === 'down' ? 'text-red-400' :
                'text-muted'
              )}>
                <span>
                  {trend === 'up' ? '↑' : trend === 'down' ? '↓' : '→'}
                </span>
                <span>{Math.abs(trendPercent)}%</span>
              </div>
            )}

            {/* Description */}
            {description && (
              <p className="text-[8px] text-muted font-medium mt-1">
                {description}
              </p>
            )}
          </div>
        </div>

        {/* Icon (right side for non-mini) */}
        {!mini && (
          <div className={cn(
            "opacity-20 ml-4 shrink-0",
            textColorClasses[color]
          )}>
            <Icon size={40} />
          </div>
        )}
      </div>
    </motion.div>
  );
}
