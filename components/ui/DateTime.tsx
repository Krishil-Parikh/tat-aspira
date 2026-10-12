"use client";
import React, { useState, useEffect } from 'react';

interface DateTimeProps {
  date: string | Date;
  format?: 'time' | 'dateTime' | 'date';
  className?: string;
  options?: Intl.DateTimeFormatOptions;
}

export function DateTime({ date, format = 'dateTime', className, options }: DateTimeProps) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) return <span className={className} suppressHydrationWarning>...</span>;

  const d = new Date(date);
  
  if (format === 'time') {
    return <span className={className}>{d.toLocaleTimeString([], options || { hour: '2-digit', minute: '2-digit' })}</span>;
  }
  
  if (format === 'date') {
    return <span className={className}>{d.toLocaleDateString([], options)}</span>;
  }

  return <span className={className}>{d.toLocaleString([], options)}</span>;
}
