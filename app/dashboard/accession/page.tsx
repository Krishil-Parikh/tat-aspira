"use client";
import React, { useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { motion, AnimatePresence } from 'motion/react';
import {
  Plus, CheckCircle2, AlertTriangle, ClipboardCheck, History, Clock,
  FlaskConical, ChevronRight, MapPin, Timer, Activity,
} from 'lucide-react';
import { cn } from '@/components/ui/utils';
import { admitSample, fetchAdmitOptions, fetchBillJourney, AdmitOptions } from '@/app/lib/api';
import { formatDateTime } from '@/app/lib/timeFormat';

type Priority = 'NORMAL' | 'HIGH' | 'URGENT';

interface AdmittedSample {
  bill_id: number;
  accession_no: string;
  patient: string;
  tests: string[];
  collection_lab: string;
  // filled in once the pipeline has processed the bill
  sample_id?: number;
  status?: string;
  labs?: string[];
  eta_end?: string | null;
  tat_breached?: boolean | null;
}

type Phase = 'idle' | 'submitting' | 'processing' | 'done' | 'error';

const PRIORITY_HINT: Record<Priority, string> = {
  NORMAL: 'Standard queue',
  HIGH:   'Ahead of normal samples',
  URGENT: 'Top of every queue',
};

function sleep(ms: number) {
  return new Promise<void>(res => setTimeout(res, ms));
}

export default function AccessionPage() {
  const [options, setOptions]   = useState<AdmitOptions | null>(null);
  const [loadError, setLoadError] = useState('');
  const [patientName, setPatientName] = useState('');
  const [selected, setSelected] = useState<string[]>([]);
  const [labId, setLabId]       = useState<number | ''>('');
  const [priority, setPriority] = useState<Priority>('NORMAL');

  const [phase, setPhase]       = useState<Phase>('idle');
  const [errorMsg, setErrorMsg] = useState('');
  const [result, setResult]     = useState<AdmittedSample | null>(null);
  const [recent, setRecent]     = useState<AdmittedSample[]>([]);
  const resultRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let alive = true;
    fetchAdmitOptions()
      .then(data => {
        if (!alive) return;
        setOptions(data);
        // Default collection point: a collection centre if there is one, else the first lab.
        const hoc = data.labs.find(l => l.lab_code === 'HOC');
        setLabId((hoc ?? data.labs[0])?.id ?? '');
      })
      .catch(err => alive && setLoadError(err.message || 'Could not load tests and labs'));
    return () => { alive = false; };
  }, []);

  const testsByDept = useMemo(() => {
    const groups: Record<string, AdmitOptions['tests']> = {};
    for (const t of options?.tests ?? []) {
      (groups[t.department_name || 'General'] ??= []).push(t);
    }
    return groups;
  }, [options]);

  const toggleTest = (code: string) =>
    setSelected(prev => prev.includes(code) ? prev.filter(c => c !== code) : [...prev, code]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!patientName.trim()) { setPhase('error'); setErrorMsg('Enter the patient name.'); return; }
    if (!selected.length)    { setPhase('error'); setErrorMsg('Select at least one test.'); return; }
    if (!labId)              { setPhase('error'); setErrorMsg('Select the collection centre.'); return; }

    setPhase('submitting');
    setErrorMsg('');
    setResult(null);
    let admitted: AdmittedSample;
    try {
      const res = await admitSample({
        patient_name: patientName.trim(),
        test_codes: selected,
        collection_lab_id: Number(labId),
        priority,
      });
      admitted = {
        bill_id: res.bill_id, accession_no: res.accession_no, patient: patientName.trim(),
        tests: res.tests, collection_lab: res.collection_lab,
      };
    } catch (err: any) {
      setPhase('error');
      setErrorMsg(err.message || 'Could not admit the sample');
      return;
    }

    // The bill is processed by the webhook pipeline; wait until the sample exists so the
    // success message is about something real (routing lab + ETA), not just a queued event.
    setResult(admitted);
    setPhase('processing');
    for (let attempt = 0; attempt < 15; attempt++) {
      await sleep(attempt === 0 ? 800 : 1500);
      try {
        const journey = await fetchBillJourney(admitted.bill_id);
        const sample = journey?.samples?.[0];
        if (sample) {
          admitted = {
            ...admitted,
            sample_id: sample.sample_id,
            status: sample.status,
            labs: Array.from(new Set((sample.tests ?? [])
              .map((t: any) => t.processing_lab).filter(Boolean))) as string[],
            eta_end: sample.sample_eta_end,
            tat_breached: sample.sample_tat_breached,
          };
          setResult(admitted);
          setPhase('done');
          setRecent(prev => [admitted, ...prev].slice(0, 6));
          setPatientName('');
          setSelected([]);
          setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 100);
          return;
        }
      } catch { /* not processed yet */ }
    }
    setPhase('error');
    setErrorMsg(`Bill ${admitted.bill_id} was submitted but has not been processed yet. ` +
                'Check the Audit Log in a minute; if it does not appear, the background worker may be down.');
  };

  const handleReset = () => { setPhase('idle'); setResult(null); setErrorMsg(''); };
  const busy = phase === 'submitting' || phase === 'processing';

  return (
    <div className="max-w-[1100px] mx-auto px-4 py-8 space-y-16">
      <div className="flex flex-col lg:flex-row gap-8 items-start">
        {/* LEFT: Admission form */}
        <section className="w-full lg:flex-1">
          <div className="bg-surface-lowest rounded-3xl overflow-hidden border border-border-ghost shadow-sm">
            <div className="bg-primary h-1.5 w-full" />
            <div className="p-8">
              <header className="mb-8">
                <h1 className="font-headline text-3xl font-black text-foreground tracking-tight">Admit New Sample</h1>
                <p className="text-muted font-medium text-sm mt-1">
                  Register a walk-in sample. It is routed to a lab, given a batch slot and an ETA,
                  exactly like a bill coming from CrelioHealth.
                </p>
              </header>

              {loadError && (
                <div className="p-4 mb-6 bg-red-400/10 border border-red-400/30 rounded-xl text-[11px] font-black text-red-400">
                  ⚠ {loadError}
                </div>
              )}

              <form onSubmit={handleSubmit} className="space-y-6">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <label className="block text-[10px] font-black uppercase tracking-widest text-muted">Patient Name</label>
                    <input
                      className="w-full bg-surface-low border-none rounded-xl py-4 px-5 font-technical text-foreground font-black focus:ring-4 focus:ring-primary/10 transition-all outline-none"
                      type="text" placeholder="e.g. Priya Sharma" maxLength={120}
                      value={patientName}
                      onChange={e => setPatientName(e.target.value)}
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="block text-[10px] font-black uppercase tracking-widest text-muted">Collected At</label>
                    <select
                      className="w-full bg-surface-low border-none rounded-xl py-4 px-5 text-sm font-black text-foreground focus:ring-4 focus:ring-primary/10 transition-all outline-none"
                      value={labId}
                      onChange={e => setLabId(e.target.value ? Number(e.target.value) : '')}>
                      <option value="">Select collection centre…</option>
                      {(options?.labs ?? []).map(l => (
                        <option key={l.id} value={l.id}>{l.lab_name}</option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="space-y-3">
                  <div className="flex justify-between items-baseline">
                    <label className="block text-[10px] font-black uppercase tracking-widest text-muted">Tests</label>
                    <span className="text-[10px] font-black text-primary uppercase tracking-widest">{selected.length} selected</span>
                  </div>
                  <div className="max-h-72 overflow-y-auto rounded-xl bg-surface-low p-3 space-y-4">
                    {!options && !loadError && <p className="text-xs text-muted p-2">Loading tests…</p>}
                    {Object.entries(testsByDept).map(([dept, tests]) => (
                      <div key={dept}>
                        <p className="text-[9px] font-black uppercase tracking-[0.2em] text-muted/70 px-2 mb-1">{dept}</p>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
                          {tests.map(t => {
                            const on = selected.includes(t.test_code);
                            return (
                              <button type="button" key={t.test_code} onClick={() => toggleTest(t.test_code)}
                                className={cn("text-left px-3 py-2 rounded-lg border transition-all",
                                  on ? "bg-primary/10 border-primary text-primary" : "bg-surface-lowest border-transparent hover:border-primary/30")}>
                                <span className="block text-xs font-black">{t.test_name}</span>
                                <span className="block text-[9px] font-bold text-muted mt-0.5">
                                  {t.test_code}{t.tat_hours ? ` · TAT ${t.tat_hours}h` : ''}
                                </span>
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="space-y-3">
                  <label className="block text-[10px] font-black uppercase tracking-widest text-muted">Priority</label>
                  <div className="grid grid-cols-3 gap-3">
                    {(['NORMAL', 'HIGH', 'URGENT'] as Priority[]).map(p => (
                      <label key={p} className={cn(
                        "relative flex flex-col items-center justify-center py-3 px-2 rounded-xl cursor-pointer transition-all border-2 text-center",
                        priority === p ? "bg-primary/5 border-primary text-primary" : "bg-surface-low border-transparent text-muted hover:bg-surface-high"
                      )}>
                        <input className="sr-only" name="priority" type="radio" value={p}
                          checked={priority === p} onChange={() => setPriority(p)} />
                        <span className="text-xs font-black uppercase tracking-widest">{p}</span>
                        <span className="text-[9px] font-bold mt-1 opacity-70">{PRIORITY_HINT[p]}</span>
                      </label>
                    ))}
                  </div>
                </div>

                {phase === 'error' && (
                  <div className="p-4 bg-red-400/10 border border-red-400/30 rounded-xl text-[11px] font-black text-red-400">
                    ⚠ {errorMsg}
                  </div>
                )}

                {phase === 'done' ? (
                  <motion.button type="button" onClick={handleReset} whileHover={{ scale: 1.01 }} whileTap={{ scale: 0.98 }}
                    className="w-full bg-surface-low text-foreground py-5 rounded-2xl font-headline font-black text-lg border-2 border-border-ghost hover:bg-surface-high transition-all mt-4 flex items-center justify-center gap-3">
                    <Plus size={24} />Admit Another Sample
                  </motion.button>
                ) : (
                  <motion.button whileHover={{ scale: 1.01 }} whileTap={{ scale: 0.98 }}
                    disabled={busy || !options}
                    className="w-full bg-primary text-white py-5 rounded-2xl font-headline font-black text-lg shadow-xl shadow-primary/20 hover:opacity-90 transition-all mt-4 flex items-center justify-center gap-3 disabled:opacity-60">
                    {busy ? (
                      <><span className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                        {phase === 'submitting' ? 'Submitting…' : 'Routing to a lab…'}</>
                    ) : (
                      <><ClipboardCheck size={24} />Admit Sample</>
                    )}
                  </motion.button>
                )}
              </form>
            </div>
          </div>
        </section>

        {/* RIGHT: what happens next */}
        <aside className="w-full lg:w-[340px] flex-shrink-0">
          <div className="bg-surface-lowest rounded-3xl border border-border-ghost overflow-hidden sticky top-8">
            <div className="p-6 border-b border-surface-low flex items-center gap-2">
              <Activity size={14} className="text-primary" />
              <h2 className="font-headline font-black text-foreground uppercase tracking-widest text-xs">What happens next</h2>
            </div>
            <ol className="p-6 space-y-4 text-xs text-muted font-medium">
              {[
                ['Bill created', 'A bill and a sample (accession number) are created for the patient.'],
                ['Routed to a lab', 'Each test goes to a lab that can run it, based on the lab network setup.'],
                ['Batch slot & ETA', 'The lab’s next batch run is booked and an expected finish time is set.'],
                ['TAT tracking', 'The committed turnaround time starts; breaches raise alerts.'],
              ].map(([title, text], i) => {
                const reached = phase === 'done' || (phase === 'processing' && i === 0);
                return (
                  <li key={title} className="flex gap-3">
                    {reached
                      ? <CheckCircle2 size={16} className="text-success-text shrink-0 mt-0.5" />
                      : <span className="w-4 h-4 rounded-full border-2 border-surface-high shrink-0 mt-0.5" />}
                    <div>
                      <p className="text-[10px] font-black uppercase tracking-widest text-foreground">{title}</p>
                      <p className="mt-0.5">{text}</p>
                    </div>
                  </li>
                );
              })}
            </ol>
          </div>
        </aside>
      </div>

      {/* Result card */}
      <AnimatePresence>
        {result && phase === 'done' && (
          <motion.div ref={resultRef} initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }} transition={{ type: 'spring', bounce: 0.3 }}
            className="rounded-3xl overflow-hidden border border-success/30 shadow-2xl shadow-success/10">
            <div className="h-1.5 w-full bg-success" />
            <div className="p-8 bg-surface-lowest">
              <div className="flex flex-col md:flex-row md:items-center gap-6 mb-8">
                <div className="w-16 h-16 rounded-2xl bg-success/10 flex items-center justify-center shadow-lg shrink-0">
                  <CheckCircle2 size={32} className="text-success-text" />
                </div>
                <div className="flex-1">
                  <p className="text-[10px] font-black uppercase tracking-widest mb-1 text-success-text">Sample admitted</p>
                  <h2 className="font-technical text-2xl font-black text-foreground uppercase">{result.accession_no}</h2>
                  <p className="text-sm text-muted font-medium">{result.patient} · Bill #{result.bill_id}</p>
                </div>
                {result.sample_id && (
                  <Link href={`/dashboard/reports/${result.sample_id}`}
                    className="px-5 py-3 rounded-xl bg-primary text-white text-[10px] font-black uppercase tracking-widest flex items-center gap-2">
                    Open sample record <ChevronRight size={14} />
                  </Link>
                )}
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {[
                  { icon: FlaskConical, label: 'Tests',        value: result.tests.join(', ') },
                  { icon: MapPin,       label: 'Collected at', value: result.collection_lab },
                  { icon: MapPin,       label: 'Processing lab', value: result.labs?.length ? result.labs.join(', ') : 'Not assigned yet' },
                  { icon: Timer,        label: 'Expected finish',
                    // journey times are UTC without an offset
                    value: result.eta_end
                      ? formatDateTime(/[zZ]|[+-]\d\d:\d\d$/.test(result.eta_end) ? result.eta_end : `${result.eta_end}Z`)
                      : 'Set when the lab receives the sample' },
                ].map(item => (
                  <div key={item.label} className="p-4 rounded-2xl bg-surface-low">
                    <p className="text-[9px] font-black uppercase tracking-widest text-muted mb-1 flex items-center gap-1">
                      <item.icon size={10} />{item.label}
                    </p>
                    <p className="font-technical text-sm font-black text-foreground">{item.value}</p>
                  </div>
                ))}
              </div>
              {result.status === 'unassigned' && (
                <p className="mt-4 text-[11px] font-black text-amber-500 flex items-center gap-2">
                  <AlertTriangle size={14} /> No lab can run one of these tests — an admin can route it from Admin Controls → Unassigned.
                </p>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Recently admitted (this session) */}
      {recent.length > 0 && (
        <section>
          <header className="mb-8 flex items-center gap-3">
            <History size={20} className="text-muted" />
            <h2 className="font-headline font-black text-xl text-foreground uppercase tracking-tight">Recently Admitted</h2>
          </header>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
            {recent.map(s => (
              <Link key={s.bill_id} href={s.sample_id ? `/dashboard/reports/${s.sample_id}` : '#'}
                className="bg-surface-lowest p-5 rounded-2xl border border-border-ghost flex items-center gap-4 hover:bg-surface-low transition-all group">
                <div className="w-12 h-12 rounded-xl flex items-center justify-center shadow-sm shrink-0 bg-primary/10 text-primary">
                  <Clock size={22} />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-technical text-sm font-black text-foreground uppercase truncate">{s.accession_no}</p>
                  <p className="text-[10px] text-muted uppercase font-black tracking-widest truncate mt-1">
                    {s.patient} · {s.tests.join(', ')}
                  </p>
                </div>
                <ChevronRight size={16} className="text-muted/20 group-hover:text-primary transition-all shrink-0" />
              </Link>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
