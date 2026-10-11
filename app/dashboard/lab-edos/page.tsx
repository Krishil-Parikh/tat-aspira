"use client";
import React, { useState, useMemo } from 'react';
import useSWR from 'swr';
import { motion, AnimatePresence } from 'motion/react';
import {
  BookOpen, Search, Filter, Edit3, Save, X, 
  Clock, Layers, CheckCircle2, AlertCircle, RefreshCw
} from 'lucide-react';
import { fetchLabEdos, updateLabEdos } from '@/app/lib/api';
import { cn } from '@/components/ui/utils';

export default function LabEdosPage() {
  const [search, setSearch] = useState('');
  const [editing, setEditing] = useState<any>(null);
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; msg: string } | null>(null);

  const { data, isLoading, mutate } = useSWR('lab-edos', fetchLabEdos);
  const edos = data?.edos || [];

  const filtered = useMemo(() => {
    return edos.filter((item: any) => 
      item.test_code.toLowerCase().includes(search.toLowerCase()) ||
      (item.test_name || item.global_name || '').toLowerCase().includes(search.toLowerCase())
    );
  }, [edos, search]);

  const handleUpdate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editing) return;
    setSubmitting(true);
    try {
      await updateLabEdos({
        test_code: editing.test_code,
        processing_time_mins: parseInt(editing.processing_time_mins),
        committed_tat_hours: parseFloat(editing.committed_tat_hours || 0),
        is_active: editing.is_active ? 1 : 0
      });
      setFeedback({ type: 'success', msg: `Successfully updated ${editing.test_code}` });
      setEditing(null);
      mutate();
      setTimeout(() => setFeedback(null), 3000);
    } catch (err: any) {
      setFeedback({ type: 'error', msg: err.message });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-8 pb-20">
      {/* Header */}
      <div className="flex items-end justify-between">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <BookOpen size={16} className="text-primary" />
            <span className="text-[10px] font-black text-muted uppercase tracking-widest">Lab Specific Catalog</span>
          </div>
          <h1 className="text-5xl font-black text-foreground tracking-tighter leading-none mb-3">EDOS MANAGEMENT</h1>
          <p className="text-muted font-medium max-w-lg">
            Manage your lab's TAT commitments, batching frequency, and test availability.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="relative group">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-muted group-focus-within:text-primary transition-colors" size={16} />
            <input 
              type="text" 
              placeholder="Filter by code or name..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="pl-12 pr-6 py-3 bg-surface-low border border-border-ghost rounded-2xl text-sm font-medium focus:ring-2 focus:ring-primary/20 outline-none w-64 transition-all"
            />
          </div>
          <button onClick={() => mutate()} className="p-3 bg-surface-low border border-border-ghost rounded-2xl text-muted hover:text-foreground transition-all">
            <RefreshCw size={18} className={isLoading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {feedback && (
        <motion.div 
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className={cn(
            "p-4 rounded-2xl border flex items-center gap-3",
            feedback.type === 'success' ? "bg-success/10 border-success/30 text-success-text" : "bg-red-500/10 border-red-500/30 text-red-500"
          )}
        >
          {feedback.type === 'success' ? <CheckCircle2 size={18} /> : <AlertCircle size={18} />}
          <p className="text-xs font-black uppercase tracking-wider">{feedback.msg}</p>
        </motion.div>
      )}

      {/* Grid */}
      {isLoading ? (
        <div className="flex flex-col items-center justify-center py-24 space-y-4">
          <div className="w-10 h-10 border-4 border-primary border-t-transparent rounded-full animate-spin" />
          <p className="text-[10px] font-black text-muted uppercase tracking-widest">Synchronizing Catalog...</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filtered.map((item: any) => (
            <motion.div
              key={item.test_code}
              layoutId={item.test_code}
              className="bg-surface-lowest rounded-[2rem] border border-border-ghost p-6 group hover:border-primary/40 transition-all"
            >
              <div className="flex items-start justify-between mb-4">
                <div>
                  <p className="text-[10px] font-black text-primary uppercase tracking-[0.2em] mb-1">{item.test_code}</p>
                  <h3 className="text-lg font-headline font-black text-foreground uppercase truncate w-48">{item.test_name || item.global_name}</h3>
                  <p className="text-[9px] font-bold text-muted uppercase tracking-wider">{item.department_name || 'General'}</p>
                </div>
                <button 
                  onClick={() => setEditing({ ...item })}
                  className="w-10 h-10 rounded-xl bg-surface-low flex items-center justify-center text-muted group-hover:text-primary group-hover:bg-primary/5 transition-all"
                >
                  <Edit3 size={18} />
                </button>
              </div>

              <div className="grid grid-cols-2 gap-4 mt-6">
                <div className="bg-surface-low rounded-2xl p-4">
                  <div className="flex items-center gap-2 mb-1 text-muted">
                    <Clock size={12} />
                    <span className="text-[9px] font-black uppercase tracking-widest">Process (Mins)</span>
                  </div>
                  <p className="text-2xl font-technical font-black text-foreground">{item.processing_time_mins}</p>
                </div>
                <div className="bg-surface-low rounded-2xl p-4">
                  <div className="flex items-center gap-2 mb-1 text-muted">
                    <Layers size={12} />
                    <span className="text-[9px] font-black uppercase tracking-widest">SLA (Hours)</span>
                  </div>
                  <p className="text-2xl font-technical font-black text-foreground">{item.committed_tat_hours || 0}</p>
                </div>
              </div>

              <div className="mt-6 flex items-center justify-between">
                <span className={cn(
                  "px-3 py-1 rounded-full text-[9px] font-black uppercase tracking-[0.15em] border",
                  item.is_active ? "bg-success/10 border-success/30 text-success-text" : "bg-red-400/10 border-red-400/30 text-red-400"
                )}>
                  {item.is_active ? 'Offering' : 'Disabled'}
                </span>
                {item.is_outsourced === 1 && (
                  <span className="text-[9px] font-black text-amber-500 uppercase">Outsourced</span>
                )}
              </div>
            </motion.div>
          ))}
        </div>
      )}

      {/* Edit Modal */}
      <AnimatePresence>
        {editing && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-background/80 backdrop-blur-md z-50 flex items-center justify-center p-6"
          >
            <motion.div
              initial={{ scale: 0.95, y: 20 }}
              animate={{ scale: 1, y: 0 }}
              exit={{ scale: 0.95, y: 20 }}
              className="bg-surface-lowest rounded-[2.5rem] border border-border-ghost shadow-2xl w-full max-w-lg overflow-hidden"
            >
              <form onSubmit={handleUpdate}>
                <div className="p-8 bg-surface-low/30">
                  <div className="flex items-center justify-between mb-6">
                    <div>
                      <p className="text-[10px] font-black text-primary uppercase tracking-[0.3em] mb-1">Configuration Editor</p>
                      <h2 className="text-2xl font-headline font-black text-foreground uppercase tracking-tight">{editing.test_code}</h2>
                    </div>
                    <button type="button" onClick={() => setEditing(null)} className="p-2 text-muted hover:text-foreground">
                      <X size={24} />
                    </button>
                  </div>

                  <div className="space-y-6">
                    <div>
                      <label className="block text-[10px] font-black text-muted uppercase tracking-widest mb-2">Internal Processing Time (Mins)</label>
                      <input 
                        type="number"
                        value={editing.processing_time_mins}
                        onChange={e => setEditing({ ...editing, processing_time_mins: e.target.value })}
                        className="w-full bg-surface-low border border-border-ghost rounded-2xl px-6 py-4 font-technical text-xl font-black text-foreground focus:ring-2 focus:ring-primary outline-none transition-all"
                      />
                      <p className="text-[9px] text-muted mt-2">Time taken by the lab internally to process this test.</p>
                    </div>

                    <div>
                      <label className="block text-[10px] font-black text-muted uppercase tracking-widest mb-2">Committed TAT (Hours)</label>
                      <input 
                        type="number"
                        step="0.5"
                        value={editing.committed_tat_hours}
                        onChange={e => setEditing({ ...editing, committed_tat_hours: e.target.value })}
                        className="w-full bg-surface-low border border-border-ghost rounded-2xl px-6 py-4 font-technical text-xl font-black text-foreground focus:ring-2 focus:ring-primary outline-none transition-all"
                      />
                      <p className="text-[9px] text-muted mt-2">Overall commitment provided to the client for this test.</p>
                    </div>

                    <div className="flex items-center justify-between p-4 bg-surface-low rounded-2xl">
                      <div className="flex items-center gap-3">
                        <div className={cn("w-3 h-3 rounded-full", editing.is_active ? "bg-success" : "bg-red-400")} />
                        <span className="text-xs font-black uppercase tracking-widest">Active Status</span>
                      </div>
                      <button 
                        type="button"
                        onClick={() => setEditing({ ...editing, is_active: !editing.is_active })}
                        className={cn(
                          "px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all",
                          editing.is_active ? "bg-success/10 text-success-text" : "bg-red-400/10 text-red-400"
                        )}
                      >
                        {editing.is_active ? 'ENABLED' : 'DISABLED'}
                      </button>
                    </div>
                  </div>
                </div>

                <div className="p-8 flex gap-4">
                  <button
                    type="submit"
                    disabled={submitting}
                    className="flex-1 bg-primary text-white py-4 rounded-2xl font-black text-sm uppercase tracking-widest hover:shadow-lg hover:shadow-primary/20 transition-all flex items-center justify-center gap-2"
                  >
                    {submitting ? <RefreshCw size={18} className="animate-spin" /> : <Save size={18} />}
                    Apply Configuration
                  </button>
                  <button
                    type="button"
                    onClick={() => setEditing(null)}
                    className="px-8 py-4 bg-surface-high text-foreground rounded-2xl font-black text-sm uppercase tracking-widest hover:bg-surface-low transition-all"
                  >
                    Discard
                  </button>
                </div>
              </form>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
