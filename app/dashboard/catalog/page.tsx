"use client";
import React, { useState, useMemo } from 'react';
import useSWR from 'swr';
import { motion, AnimatePresence } from 'motion/react';
import { Search, Info, Clock, Calendar, ChevronDown, FlaskConical, RefreshCw } from 'lucide-react';
import { fetchAllTests } from '@/app/lib/api';
import { cn } from '@/components/ui/utils';

const DEPT_COLORS: Record<string, string> = {
  Hematology:    'bg-red-400/10 text-red-400',
  Biochemistry:  'bg-amber-400/10 text-amber-500',
  Immunology:    'bg-violet-400/10 text-violet-500',
  Microbiology:  'bg-emerald-400/10 text-emerald-500',
  Pathology:     'bg-sky-400/10 text-sky-500',
  Endocrinology: 'bg-pink-400/10 text-pink-500',
  Molecular:     'bg-indigo-400/10 text-indigo-500',
  Cardiology:    'bg-rose-400/10 text-rose-500',
  Oncology:      'bg-orange-400/10 text-orange-500',
};

export default function CatalogPage() {
  const [search, setSearch] = useState('');
  const [expanded, setExpanded] = useState<string | null>(null);

  const { data, isLoading, mutate, error } = useSWR('master-catalog', fetchAllTests);
  const tests = data?.tests || [];

  const filtered = useMemo(() => {
    return tests.filter((t: any) =>
      (t.test_name || '').toLowerCase().includes(search.toLowerCase()) ||
      (t.test_code || '').toLowerCase().includes(search.toLowerCase()) ||
      (t.department_name || '').toLowerCase().includes(search.toLowerCase())
    );
  }, [tests, search]);

  return (
    <div className="space-y-8 pb-20">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div>
          <h1 className="text-4xl font-black text-foreground tracking-tight">EDOS CATALOG</h1>
          <p className="text-muted font-medium">
            Directory of active laboratory methodologies and TAT commitments
            <span className="ml-2 text-[10px] font-black text-primary/60 uppercase tracking-widest">
              [{tests.length} methodologies indexed]
            </span>
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="bg-surface-lowest p-2 rounded-2xl border border-border-ghost flex items-center px-4 w-72 group focus-within:w-80 transition-all duration-300">
            <Search size={18} className="text-muted group-focus-within:text-primary" />
            <input
              type="text"
              placeholder="Search test name or code..."
              className="flex-1 bg-transparent py-2 px-3 text-sm font-bold outline-none text-foreground"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>
          <button onClick={() => mutate()} className="p-3 bg-surface-lowest border border-border-ghost rounded-2xl text-muted hover:text-foreground transition-all">
            <RefreshCw size={18} className={isLoading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="flex flex-col items-center justify-center py-24 space-y-4">
          <div className="w-10 h-10 border-4 border-primary border-t-transparent rounded-full animate-spin" />
          <p className="text-[10px] font-black text-muted uppercase tracking-widest">Syncing Master Index...</p>
        </div>
      ) : error ? (
        <div className="text-center py-20 bg-surface-lowest rounded-3xl border border-red-500/20">
          <AlertCircle size={40} className="mx-auto text-red-400 mb-4" />
          <h3 className="text-lg font-black text-foreground">Catalog Unavailable</h3>
          <p className="text-muted mt-1">Ensure the database initialization script has been run.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filtered.map((test: any, index: number) => {
            const deptClass = DEPT_COLORS[test.department_name] || 'bg-surface-high text-muted';
            const isExpanded = expanded === test.test_code;

            return (
              <motion.div
                key={test.test_code}
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: Math.min(index * 0.04, 0.5) }}
                whileHover={{ y: -4 }}
                className="bg-surface-lowest p-6 rounded-[2rem] border border-border-ghost hover:border-primary/30 transition-all group"
              >
                <div className="flex items-start justify-between mb-4">
                  <div className={`p-3 rounded-2xl group-hover:scale-110 transition-transform ${deptClass.split(' ')[0]}`}>
                    <FlaskConical size={20} className={deptClass.split(' ')[1]} />
                  </div>
                  <div className={`text-[10px] font-black uppercase tracking-widest px-2 py-1 rounded-lg border border-current/20 ${deptClass}`}>
                    {test.department_name || 'General'}
                  </div>
                </div>

                <div className="space-y-1 mb-6">
                  <div className="text-xs font-black text-primary uppercase tracking-tighter">{test.test_code}</div>
                  <h3 className="text-lg font-black text-foreground leading-tight line-clamp-1 uppercase font-headline">{test.test_name}</h3>
                </div>

                <div className="grid grid-cols-2 gap-4 border-t border-border-ghost pt-6">
                  <div className="space-y-1">
                    <div className="flex items-center space-x-1 text-muted">
                      <Clock size={12} />
                      <span className="text-[9px] font-black uppercase tracking-widest">PROCESS (MIN)</span>
                    </div>
                    <div className="text-xs font-bold text-foreground font-technical">{test.processing_time_mins || 'VARIES'}</div>
                  </div>
                  <div className="space-y-1">
                    <div className="flex items-center space-x-1 text-muted">
                      <Calendar size={12} />
                      <span className="text-[9px] font-black uppercase tracking-widest">TAT (HOURS)</span>
                    </div>
                    <div className="text-xs font-bold text-foreground font-technical">
                      {test.predefined_tat_hours || 0}H
                    </div>
                  </div>
                </div>

                <button
                  onClick={() => setExpanded(isExpanded ? null : test.test_code)}
                  className="w-full mt-6 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest text-muted hover:text-foreground hover:bg-surface-low transition-all flex items-center justify-center space-x-1"
                >
                  <span>Protocol Details</span>
                  <motion.span animate={{ rotate: isExpanded ? 180 : 0 }} transition={{ duration: 0.2 }}>
                    <ChevronDown size={14} />
                  </motion.span>
                </button>

                {isExpanded && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    className="mt-4 pt-4 border-t border-border-ghost space-y-2"
                  >
                    {[
                      ['Internal Code', test.test_code],
                      ['Category',      test.test_category || 'Diagnostic'],
                      ['Global TAT',    `${test.predefined_tat_hours || 0} Hours`],
                      ['Critical',      test.is_critical ? 'YES' : 'NO'],
                      ['Parallel',      test.is_parallel_capable ? 'YES' : 'NO'],
                    ].map(([label, val]) => (
                      <div key={label} className="flex justify-between items-center">
                        <span className="text-[9px] font-black uppercase tracking-widest text-muted">{label}</span>
                        <span className="text-[9px] font-bold text-foreground text-right">{val}</span>
                      </div>
                    ))}
                  </motion.div>
                )}
              </motion.div>
            );
          })}
        </div>
      )}

      {!isLoading && filtered.length === 0 && (
        <div className="text-center py-20 bg-surface-lowest rounded-3xl border border-dashed border-border-ghost">
          <Info size={40} className="mx-auto text-muted mb-4" />
          <h3 className="text-lg font-black text-foreground">No Matching Methodologies</h3>
          <p className="text-muted mt-1">Zero results for "{search}" in the active EDOS index.</p>
        </div>
      )}
    </div>
  );
}

function AlertCircle(props: any) {
  return (
    <svg
      {...props}
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="8" x2="12" y2="12" />
      <line x1="12" y1="16" x2="12.01" y2="16" />
    </svg>
  );
}
