"use client";
import React, { useState } from 'react';
import useSWR from 'swr';
import { motion, AnimatePresence } from 'motion/react';
import {
  FlaskConical, CheckCircle2, Clock, Loader, ChevronRight,
  RefreshCw, Play, Upload, AlertCircle, Activity
} from 'lucide-react';
import {
  fetchLabWorkQueue, markSampleReceived, updateTestStatus, submitResult
} from '@/app/lib/api';
import { cn } from '@/components/ui/utils';

// Get lab_id from cookie set at login.
// NOTE: This is UI-only. Backend always derives lab_id from session cookie,
// never trusts this value for authorization.
function getLabId(): number {
  if (typeof document === 'undefined') return 0;
  const cookies = document.cookie.split('; ');
  const v = cookies.find(c => c.startsWith('aspira_lab_id='))?.split('=')[1];
  return v ? parseInt(v) : 0; // 0 = unknown; backend session is authoritative
}

const TEST_STATUS_FLOW: Record<string, { next: string; label: string; color: string }> = {
  pending:    { next: 'in_queue',    label: 'Accept to Queue',  color: 'bg-surface-low text-muted' },
  in_queue:   { next: 'processing',  label: 'Start Processing', color: 'bg-amber-500/10 text-amber-500' },
  processing: { next: 'completed',   label: 'Mark Complete',    color: 'bg-primary/10 text-primary' },
};

export default function LabQueuePage() {
  const labId = getLabId();
  const [submitting, setSubmitting] = useState<number | null>(null);
  const [resultModal, setResultModal] = useState<{ testId: number; sampleId: number; code: string } | null>(null);
  const [resultText, setResultText] = useState('');
  const [feedback, setFeedback] = useState<{ id: number; type: 'success' | 'error'; msg: string } | null>(null);

  const { data, isLoading, mutate } = useSWR(
    `lab-queue-${labId}`,
    () => fetchLabWorkQueue(labId),
    { refreshInterval: 8000 }
  );

  const workItems = data?.work_items || [];

  // Group by sample
  const grouped = workItems.reduce((acc: any, item: any) => {
    if (!acc[item.sample_id]) {
      acc[item.sample_id] = {
        sample_id: item.sample_id,
        accession_no: item.accession_no,
        patient_name: item.patient_name,
        priority: item.priority,
        sample_status: item.sample_status,
        arrived_at_lab: item.arrived_at_lab,
        estimated_end_time: item.estimated_end_time,
        is_tat_breached: item.is_tat_breached,
        tests: []
      };
    }
    acc[item.sample_id].tests.push(item);
    return acc;
  }, {});
  const samples = Object.values(grouped);

  const handleAdvanceStatus = async (testInstanceId: number, currentStatus: string) => {
    const next = TEST_STATUS_FLOW[currentStatus]?.next;
    if (!next) return;
    if (next === 'completed') {
      setResultModal({ testId: testInstanceId, sampleId: 0, code: '' });
      return;
    }
    setSubmitting(testInstanceId);
    try {
      await updateTestStatus(testInstanceId, next);
      setFeedback({ id: testInstanceId, type: 'success', msg: `Status → ${next.toUpperCase()}` });
      mutate();
    } catch (e: any) {
      setFeedback({ id: testInstanceId, type: 'error', msg: e.message });
    } finally {
      setSubmitting(null);
    }
  };

  const handleOpenResult = (test: any) => {
    setResultModal({ testId: test.test_instance_id, sampleId: test.sample_id, code: test.test_code });
    setResultText('');
  };

  const handleSubmitResult = async () => {
    if (!resultModal || !resultText.trim()) return;
    setSubmitting(resultModal.testId);
    try {
      await submitResult(resultModal.testId, resultModal.sampleId, resultText);
      setFeedback({ id: resultModal.testId, type: 'success', msg: 'Result submitted! Completion engine processing.' });
      setResultModal(null);
      setResultText('');
      mutate();
    } catch (e: any) {
      setFeedback({ id: resultModal.testId, type: 'error', msg: e.message });
    } finally {
      setSubmitting(null);
    }
  };

  const handleConfirmReceipt = async (sampleId: number) => {
    setSubmitting(sampleId * -1);
    try {
      // Backend ignores cookie lab_id and uses the session-derived lab_id for RBAC
      await markSampleReceived(sampleId, labId);
      setFeedback({ id: sampleId, type: 'success', msg: 'Lab receipt confirmed. TAT clock started.' });
      mutate();
    } catch (e: any) {
      setFeedback({ id: sampleId, type: 'error', msg: e.message });
    } finally {
      setSubmitting(null);
    }
  };

  const [mounted, setMounted] = React.useState(false);
  React.useEffect(() => {
    setMounted(true);
  }, []);

  return (
    <div className="space-y-8 pb-20">
      {/* Header */}
      <div className="flex items-end justify-between">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <div className="w-2 h-2 rounded-full bg-primary animate-pulse" />
            <span className="text-[10px] font-black text-muted uppercase tracking-widest">Lab Work Station · Lab {mounted ? labId : '...'}</span>
          </div>
          <h1 className="text-5xl font-black text-foreground tracking-tighter leading-none mb-2">LAB QUEUE</h1>
          <p className="text-muted font-medium max-w-lg">
            Manage your assigned samples and tests. Confirm receipt, process tests, and submit results.
          </p>
        </div>
        <button suppressHydrationWarning onClick={() => mutate()} className="flex items-center gap-2 px-4 py-2.5 bg-surface-low border border-border-ghost rounded-xl text-[10px] font-black uppercase tracking-widest text-muted hover:text-foreground transition-all">
          <RefreshCw size={14} />
          Refresh
        </button>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: 'Total Assigned', value: mounted ? workItems.length : '...', color: 'text-foreground' },
          { label: 'In Queue', value: mounted ? workItems.filter((t: any) => t.test_status === 'in_queue').length : '...', color: 'text-amber-500' },
          { label: 'Processing', value: mounted ? workItems.filter((t: any) => t.test_status === 'processing').length : '...', color: 'text-primary' },
          { label: 'TAT Breaches', value: mounted ? workItems.filter((t: any) => t.is_tat_breached).length : '...', color: 'text-red-500' },
        ].map(s => (
          <div key={s.label} className="bg-surface-lowest rounded-2xl border border-border-ghost p-5">
            <p className="text-[9px] font-black text-muted uppercase tracking-widest mb-1">{s.label}</p>
            <p className={cn("text-3xl font-black font-technical", s.color)}>{s.value}</p>
          </div>
        ))}
      </div>

      {/* Work queue */}
      {isLoading ? (
        <div className="flex flex-col items-center justify-center py-24 space-y-4">
          <div className="w-10 h-10 border-4 border-primary border-t-transparent rounded-full animate-spin" />
          <p className="text-[10px] font-black text-muted uppercase tracking-widest">Loading Work Queue...</p>
        </div>
      ) : samples.length === 0 ? (
        <div className="text-center py-24 bg-surface-lowest rounded-3xl border border-border-ghost">
          <CheckCircle2 size={48} className="text-success-text mx-auto mb-4 opacity-30" />
          <p className="text-[10px] font-black text-muted uppercase tracking-[0.3em]">Queue is clear — no pending tests</p>
        </div>
      ) : (
        <div className="space-y-4">
          {(samples as any[]).map((sample: any) => (
            <motion.div
              key={sample.sample_id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className={cn(
                "bg-surface-lowest rounded-3xl border overflow-hidden",
                sample.is_tat_breached ? "border-red-500/30" : "border-border-ghost"
              )}
            >
              {/* Sample header */}
              <div className="px-6 py-4 border-b border-border-ghost flex items-center justify-between bg-surface-low/50">
                <div className="flex items-center gap-4">
                  <div>
                    <p className="font-technical font-black text-foreground">{sample.accession_no || `Sample #${sample.sample_id}`}</p>
                    <p className="text-[10px] text-muted font-medium">{sample.patient_name}</p>
                  </div>
                  <span className={cn(
                    "px-2.5 py-1 rounded-full border text-[9px] font-black uppercase",
                    sample.priority === 'URGENT' ? 'bg-red-500/10 border-red-500/30 text-red-500' :
                    sample.priority === 'HIGH' ? 'bg-amber-500/10 border-amber-500/30 text-amber-500' :
                    'bg-success/10 border-success/30 text-success-text'
                  )}>{sample.priority}</span>
                  {sample.is_tat_breached === 1 && (
                    <span className="px-2.5 py-1 rounded-full bg-red-500/10 border border-red-500/30 text-red-500 text-[9px] font-black uppercase flex items-center gap-1">
                      <AlertCircle size={10} /> TAT Breached
                    </span>
                  )}
                </div>
                {!sample.arrived_at_lab && (
                  <button
                    disabled={submitting === sample.sample_id * -1}
                    onClick={() => handleConfirmReceipt(sample.sample_id)}
                    className="px-4 py-2 bg-primary text-white rounded-xl text-[10px] font-black uppercase tracking-widest hover:opacity-90 disabled:opacity-50 flex items-center gap-2 shadow-lg shadow-primary/20"
                  >
                    {submitting === sample.sample_id * -1 ? <RefreshCw size={12} className="animate-spin" /> : <FlaskConical size={12} />}
                    Confirm Receipt
                  </button>
                )}
                {sample.arrived_at_lab && (
                  <span className="text-[9px] font-black uppercase tracking-widest text-success-text flex items-center gap-1">
                    <CheckCircle2 size={12} /> Received · TAT Running
                  </span>
                )}
              </div>

              {/* Tests */}
              <div className="divide-y divide-border-ghost">
                {sample.tests.map((test: any) => {
                  const nextAction = TEST_STATUS_FLOW[test.test_status];
                  const isSubmitting = submitting === test.test_instance_id;
                  const fb = feedback?.id === test.test_instance_id ? feedback : null;
                  return (
                    <div key={test.test_instance_id} className="px-6 py-4 flex items-center gap-4">
                      <div className="w-8 h-8 rounded-xl bg-surface-low flex items-center justify-center shrink-0">
                        <Activity size={14} className="text-primary" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="font-technical font-black text-sm text-foreground">{test.test_code}</p>
                        <p className="text-[10px] text-muted">{test.test_name || 'Unknown Test'}</p>
                      </div>
                      <span className={cn(
                        "px-2.5 py-1 rounded-full text-[9px] font-black uppercase border",
                        test.test_status === 'processing' ? 'bg-primary/10 border-primary/30 text-primary' :
                        test.test_status === 'in_queue' ? 'bg-amber-500/10 border-amber-500/30 text-amber-500' :
                        test.test_status === 'completed' ? 'bg-success/10 border-success/30 text-success-text' :
                        'bg-surface-high border-border-ghost text-muted'
                      )}>{test.test_status?.replace('_', ' ')}</span>
                      {fb && (
                        <span className={cn("text-[9px] font-black uppercase", fb.type === 'success' ? 'text-success-text' : 'text-red-400')}>{fb.msg}</span>
                      )}
                      {nextAction && test.test_status !== 'completed' && (
                        <div className="flex items-center gap-2">
                          {test.test_status === 'processing' ? (
                            <button
                              onClick={() => handleOpenResult(test)}
                              className="px-4 py-2 bg-success/10 border border-success/30 text-success-text rounded-xl text-[9px] font-black uppercase flex items-center gap-1.5 hover:bg-success/20 transition-all"
                            >
                              <Upload size={12} /> Submit Result
                            </button>
                          ) : (
                            <button
                              disabled={isSubmitting}
                              onClick={() => handleAdvanceStatus(test.test_instance_id, test.test_status)}
                              className={cn("px-4 py-2 rounded-xl text-[9px] font-black uppercase border flex items-center gap-1.5 hover:opacity-80 transition-all disabled:opacity-50", nextAction.color, "border-current/30")}
                            >
                              {isSubmitting ? <RefreshCw size={12} className="animate-spin" /> : <Play size={12} />}
                              {nextAction.label}
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </motion.div>
          ))}
        </div>
      )}

      {/* Result Submission Modal */}
      <AnimatePresence>
        {resultModal && (
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
              className="bg-surface-lowest rounded-3xl border border-border-ghost shadow-2xl w-full max-w-lg p-8"
            >
              <h2 className="text-2xl font-headline font-black uppercase tracking-tight mb-2">Submit Result</h2>
              <p className="text-[10px] text-muted font-black uppercase tracking-widest mb-6">Test · {resultModal.code}</p>
              <textarea
                value={resultText}
                onChange={e => setResultText(e.target.value)}
                rows={5}
                placeholder="Enter test result value, interpretation, or report text..."
                className="w-full bg-surface-low border-none rounded-2xl p-4 font-technical text-foreground outline-none focus:ring-2 focus:ring-primary resize-none mb-6"
              />
              <div className="flex gap-3">
                <button
                  onClick={handleSubmitResult}
                  disabled={!resultText.trim() || !!submitting}
                  className="flex-1 bg-primary text-white py-3.5 rounded-xl font-black text-sm uppercase tracking-widest hover:opacity-90 disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  {submitting ? <RefreshCw size={16} className="animate-spin" /> : <Upload size={16} />}
                  Submit to Completion Engine
                </button>
                <button
                  onClick={() => setResultModal(null)}
                  className="px-6 py-3.5 bg-surface-low text-foreground rounded-xl font-black text-sm uppercase tracking-widest hover:bg-surface-high transition-all"
                >
                  Cancel
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
