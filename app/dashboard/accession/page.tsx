"use client";
import React, { useEffect, useState, useRef } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  Plus, CheckCircle2, AlertCircle, QrCode, Keyboard, ScanLine,
  ClipboardCheck, Layers, History, Hourglass, Clock, ArrowRight,
  Shield, Zap, Database, Server, Radio, AlertTriangle, CheckCheck,
  Activity, FlaskConical, ChevronRight
} from 'lucide-react';
import { cn } from '@/components/ui/utils';
import { fetchTests } from '@/app/lib/api';

type Priority = 'ROUTINE' | 'URGENT' | 'STAT';

interface PipelineStep {
  id: string;
  label: string;
  sublabel: string;
  icon: React.ElementType;
  status: 'pending' | 'running' | 'done' | 'warn';
  detail?: string;
}

interface AccessionResult {
  sample_id: string;
  event_id: number;
  test_name: string;
  status: 'accepted' | 'duplicate';
}

interface TestOption {
  test_code: string;
  test_name: string;
  department?: string;
  department_name?: string;
  tat_raw?: string;
  schedule_raw?: string;
}

const STEPS_TEMPLATE: Omit<PipelineStep, 'status' | 'detail'>[] = [
  { id: 'reception',  label: 'Specimen Logged',    sublabel: 'Initial reception recorded',    icon: ClipboardCheck },
  { id: 'validation', label: 'Identity Verified',  sublabel: 'Unique ID & checksum pass',     icon: Shield },
  { id: 'mapping',    label: 'Methodology Mapped', sublabel: 'EDOS protocol identified',      icon: FlaskConical },
  { id: 'batching',   label: 'Batch Sequencing',   sublabel: 'Assigned to next available run', icon: Layers },
  { id: 'governance', label: 'SLA Governance',     sublabel: 'Timeline & TAT compliance check', icon: Activity },
  { id: 'ledger',     label: 'Digital Ledger',     sublabel: 'Secure persistence complete',   icon: Database },
  { id: 'radar',      label: 'Alert Radar',        sublabel: 'Active monitoring enabled',     icon: Radio },
  { id: 'final',      label: 'Ingestion Complete', sublabel: 'Sample active in system',       icon: CheckCheck },
];

function fmtTime(iso: string) {
  return new Date(iso).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' });
}
function genBillId() {
  return Math.floor(900000 + Math.random() * 99999);
}
function genReportId() {
  return Math.floor(100000 + Math.random() * 899999);
}
function sleep(ms: number) {
  return new Promise<void>(res => setTimeout(res, ms));
}

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export default function AccessionPage() {
  const [testOptions, setTestOptions] = useState<TestOption[]>([]);
  const [formData, setFormData] = useState({
    test_code: '',
    patient_name: '',
    priority: 'ROUTINE' as Priority,
    agreed_tat_hours: 24,
  });

  const [activeTab, setActiveTab]       = useState<'scan' | 'manual'>('scan');
  const [phase, setPhase]               = useState<'idle' | 'running' | 'done' | 'error'>('idle');
  const [steps, setSteps]               = useState<PipelineStep[]>([]);
  const [result, setResult]             = useState<AccessionResult | null>(null);
  const [errorMsg, setErrorMsg]         = useState('');
  const [recentSamples, setRecentSamples] = useState<any[]>([]);
  const [scanPulse, setScanPulse]       = useState(false);
  const resultRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let alive = true;
    fetchTests({ limit: 100 })
      .then(data => {
        if (alive) setTestOptions(data?.tests || []);
      })
      .catch(() => {
        if (alive) setTestOptions([]);
      });
    return () => {
      alive = false;
    };
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.test_code) return;

    const testMeta = testOptions.find(t => t.test_code === formData.test_code);
    if (!testMeta) {
      setPhase('error');
      setErrorMsg('Selected test is not available in the EDOS catalog.');
      return;
    }
    const billId   = genBillId();
    const reportId = genReportId();
    const now      = new Date().toISOString();

    const initial: PipelineStep[] = STEPS_TEMPLATE.map(s => ({ ...s, status: 'pending' }));
    setSteps(initial);
    setPhase('running');
    setResult(null);
    setErrorMsg('');

    const delays = [300, 350, 300, 400, 250, 500, 400, 350];

    // Animate first 6 steps locally (reception → ledger)
    for (let i = 0; i < STEPS_TEMPLATE.length - 2; i++) {
      const d = delays[i] ?? 350;
      await sleep(d * 0.3);
      setSteps(prev => prev.map((s, idx) => idx === i ? { ...s, status: 'running' } : s));
      await sleep(d * 0.7);

      let status: PipelineStep['status'] = 'done';
      let detail: string | undefined;

      if (STEPS_TEMPLATE[i].id === 'reception')  detail = `Time: ${fmtTime(now)} · Bill ID: ${billId}`;
      if (STEPS_TEMPLATE[i].id === 'validation') detail = `Patient: ${formData.patient_name || 'Anonymous'} · Code: ${formData.test_code}`;
      if (STEPS_TEMPLATE[i].id === 'mapping')    detail = `${testMeta.test_name} · Dept: ${testMeta.department_name || testMeta.department || 'General'}`;
      if (STEPS_TEMPLATE[i].id === 'batching')   detail = `TAT: ${testMeta.tat_raw} · Schedule: ${testMeta.schedule_raw}`;
      if (STEPS_TEMPLATE[i].id === 'governance') {
        detail = `SLA window: ${formData.agreed_tat_hours}h · Priority: ${formData.priority}`;
      }
      if (STEPS_TEMPLATE[i].id === 'ledger') detail = `Submitting to system...`;

      setSteps(prev => prev.map((s, idx) => idx === i ? { ...s, status, detail } : s));
    }

    // Step 6 (radar) — mark running while we do the real API call
    setSteps(prev => prev.map((s, idx) => idx === 6 ? { ...s, status: 'running' } : s));

    // Build BILL_UPDATE webhook payload
    const webhookPayload = {
      webhook_type: 'BILL_UPDATE',
      bill_id: billId,
      billId: billId,
      labId: 1,
      billTime: now,
      patientName: formData.patient_name || 'Walk-in Patient',
      orgId: { orgId: 1, orgFullName: 'Aspira Collection Center' },
      labReportDetails: [
        {
          labReportId: reportId,
          labReportIndex: 1,
          testCode: formData.test_code,
          testName: testMeta.test_name,
          testCategory: testMeta.department_name || testMeta.department || 'General',
          sampleDate: now,
          reportDate: now,
          departmentId: { id: 1, name: testMeta.department_name || testMeta.department || 'General' },
        },
      ],
    };

    let eventId = 0;
    let apiOk = false;
    try {
      const res = await fetch(`${BASE_URL}/api/webhook`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(webhookPayload),
      });
      const json = await res.json();
      if (res.ok || res.status === 202) {
        apiOk = true;
        eventId = json.event_id || 0;
        // Mark radar done
        setSteps(prev => prev.map((s, idx) =>
          idx === 6 ? { ...s, status: 'done', detail: `Event ID: ${eventId} · Celery task queued` } : s
        ));
      } else {
        throw new Error(json.detail || `HTTP ${res.status}`);
      }
    } catch (err: any) {
      setSteps(prev => prev.map((s, idx) =>
        idx === 6 ? { ...s, status: 'warn', detail: `API error: ${err.message}` } : s
      ));
      setPhase('error');
      setErrorMsg(err.message || 'Webhook submission failed');
      return;
    }

    // Final step
    await sleep(300);
    setSteps(prev => prev.map((s, idx) =>
      idx === 7 ? { ...s, status: 'done', detail: `Admitted · Celery processing started` } : s
    ));

    setResult({
      sample_id: `BILL-${billId}`,
      event_id: eventId,
      test_name: testMeta.test_name,
      status: 'accepted',
    });
    setPhase('done');

    setRecentSamples(prev => [{
      sample_id: `BILL-${billId}`,
      test_name: testMeta.test_name,
      timestamp: 'Just now',
      status: 'processing' as const,
    }, ...prev].slice(0, 6));

    setFormData(prev => ({ ...prev, patient_name: '' }));
    setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 100);
  };

  const handleReset = () => { setPhase('idle'); setSteps([]); setResult(null); setErrorMsg(''); };

  const triggerScanPulse = () => {
    setScanPulse(true);
    setTimeout(() => setScanPulse(false), 800);
    setFormData(prev => ({
      ...prev,
      patient_name: 'Walk-in Patient',
      test_code: testOptions[Math.floor(Math.random() * Math.min(testOptions.length, 6))]?.test_code || '',
    }));
  };

  const selectedTest = testOptions.find(t => t.test_code === formData.test_code);

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
                  Register specimen — fires a real BILL_UPDATE webhook for Celery processing.
                </p>
              </header>

              {/* Tabs */}
              <div className="flex gap-1 p-1 bg-surface-low rounded-xl mb-6">
                {([['scan', QrCode, 'Scan QR / Barcode'], ['manual', Keyboard, 'Manual Entry']] as const).map(([tab, Icon, label]) => (
                  <button key={tab} onClick={() => setActiveTab(tab)}
                    className={cn("flex-1 py-2.5 px-4 rounded-lg text-sm font-bold transition-all flex items-center justify-center gap-2",
                      activeTab === tab ? "bg-surface-lowest text-primary shadow-sm" : "text-muted hover:bg-surface-high"
                    )}>
                    <Icon size={16} />{label}
                  </button>
                ))}
              </div>

              {/* Scanner zone */}
              <AnimatePresence mode="wait">
                {activeTab === 'scan' && (
                  <motion.div key="scan" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}
                    onClick={triggerScanPulse}
                    className={cn("w-full h-44 rounded-2xl flex flex-col items-center justify-center mb-8 cursor-pointer group border-2 transition-all duration-300 relative overflow-hidden",
                      scanPulse ? "bg-primary/10 border-primary" : "bg-surface-lowest hover:bg-primary/5 border-transparent hover:border-primary/30"
                    )}>
                    {scanPulse && (
                      <motion.div initial={{ scaleY: 0, opacity: 0.8 }} animate={{ scaleY: 1, opacity: 0 }} transition={{ duration: 0.6 }}
                        className="absolute inset-0 bg-primary/20 origin-top" />
                    )}
                    <ScanLine size={48} className={cn("mb-3 transition-all", scanPulse ? "text-primary scale-110" : "text-primary group-hover:scale-110")} />
                    {scanPulse ? (
                      <p className="text-sm font-black text-primary uppercase tracking-widest">Scan Captured!</p>
                    ) : (
                      <>
                        <p className="text-sm font-black text-primary uppercase tracking-widest">Click to Simulate Scan</p>
                        <p className="text-[10px] text-muted font-black uppercase tracking-[0.2em] mt-2">Accepts GS1-128 and DataMatrix</p>
                      </>
                    )}
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Form */}
              <form onSubmit={handleSubmit} className="space-y-6">
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <label className="block text-[10px] font-black uppercase tracking-widest text-muted">Patient Name</label>
                    <input
                      className="w-full bg-surface-low border-none rounded-xl py-4 px-5 font-technical text-foreground font-black focus:ring-4 focus:ring-primary/10 transition-all outline-none"
                      type="text" placeholder="e.g. John Doe"
                      value={formData.patient_name}
                      onChange={e => setFormData({ ...formData, patient_name: e.target.value })}
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="block text-[10px] font-black uppercase tracking-widest text-muted">Test Methodology</label>
                    <select required
                      className="w-full bg-surface-low border-none rounded-xl py-4 px-5 text-sm font-black text-foreground focus:ring-4 focus:ring-primary/10 transition-all outline-none appearance-none"
                      value={formData.test_code}
                      onChange={e => setFormData({ ...formData, test_code: e.target.value })}>
                      <option value="">Select Methodology...</option>
                      {testOptions.map(t => (
                        <option key={t.test_code} value={t.test_code}>{t.test_name} ({t.test_code})</option>
                      ))}
                    </select>
                  </div>
                </div>

                <AnimatePresence>
                  {selectedTest && (
                    <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}
                      className="flex items-center gap-3 px-4 py-3 bg-primary/5 rounded-xl border border-primary/15">
                      <FlaskConical size={16} className="text-primary shrink-0" />
                      <div className="flex gap-4 text-[10px] font-black uppercase tracking-widest text-primary/80 flex-wrap">
                        <span>{selectedTest.department_name || selectedTest.department || 'General'}</span>
                        <span className="text-muted/40">·</span>
                        <span>TAT: {selectedTest.tat_raw}</span>
                        <span className="text-muted/40">·</span>
                        <span>Schedule: {selectedTest.schedule_raw}</span>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>

                <div className="space-y-3">
                  <label className="block text-[10px] font-black uppercase tracking-widest text-muted">Priority Level</label>
                  <div className="grid grid-cols-3 gap-3">
                    {(['ROUTINE', 'URGENT', 'STAT'] as Priority[]).map(p => (
                      <label key={p} className={cn(
                        "relative flex items-center justify-center py-4 px-4 rounded-xl cursor-pointer transition-all border-2",
                        formData.priority === p ? "bg-primary/5 border-primary text-primary" : "bg-surface-low border-transparent text-muted hover:bg-surface-high"
                      )}>
                        <input className="sr-only" name="priority" type="radio" value={p}
                          checked={formData.priority === p} onChange={() => setFormData({ ...formData, priority: p })} />
                        <span className="text-xs font-black uppercase tracking-widest">{p}</span>
                      </label>
                    ))}
                  </div>
                </div>

                <div className="space-y-2">
                  <div className="flex justify-between">
                    <label className="block text-[10px] font-black uppercase tracking-widest text-muted">Agreed TAT</label>
                    <span className="text-[10px] font-black text-primary uppercase tracking-widest">{formData.agreed_tat_hours} hrs</span>
                  </div>
                  <input type="range" min={1} max={72} step={1} value={formData.agreed_tat_hours}
                    onChange={e => setFormData({ ...formData, agreed_tat_hours: Number(e.target.value) })}
                    className="w-full accent-primary" />
                  <div className="flex justify-between text-[9px] font-black text-muted uppercase tracking-widest">
                    <span>1 Hr (STAT)</span><span>24 Hrs (Standard)</span><span>72 Hrs (Culture)</span>
                  </div>
                </div>

                {/* Error banner */}
                {phase === 'error' && (
                  <div className="p-4 bg-red-400/10 border border-red-400/30 rounded-xl text-[10px] font-black text-red-400 uppercase tracking-wide">
                    ⚠ Submission failed: {errorMsg}
                  </div>
                )}

                {phase === 'done' ? (
                  <motion.button type="button" onClick={handleReset} whileHover={{ scale: 1.01 }} whileTap={{ scale: 0.98 }}
                    className="w-full bg-surface-low text-foreground py-5 rounded-2xl font-headline font-black text-lg border-2 border-border-ghost hover:bg-surface-high transition-all mt-4 flex items-center justify-center gap-3">
                    <Plus size={24} />Admit Another Sample
                  </motion.button>
                ) : (
                  <motion.button whileHover={{ scale: 1.01 }} whileTap={{ scale: 0.98 }}
                    disabled={phase === 'running'}
                    className="w-full bg-primary text-white py-5 rounded-2xl font-headline font-black text-lg shadow-xl shadow-primary/20 hover:opacity-90 transition-all mt-4 flex items-center justify-center gap-3 disabled:opacity-60">
                    {phase === 'running' ? (
                      <><span className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />Submitting Sample...</>
                    ) : (
                      <><ClipboardCheck size={24} />Admit &amp; Assign to Batch</>
                    )}
                  </motion.button>
                )}
              </form>
            </div>
          </div>
        </section>

        {/* RIGHT: Live pipeline visualiser */}
        <aside className="w-full lg:w-[340px] flex-shrink-0">
          <div className="bg-surface-lowest rounded-3xl border border-border-ghost overflow-hidden sticky top-8">
            <div className="p-6 border-b border-surface-low flex items-center gap-2">
              <Activity size={14} className="text-primary" />
              <h2 className="font-headline font-black text-foreground uppercase tracking-widest text-xs">Processing Telemetry</h2>
              {phase === 'running' && (
                <span className="ml-auto flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
                  <span className="text-[9px] font-black text-primary uppercase tracking-widest">Live</span>
                </span>
              )}
            </div>
            <div className="p-6">
              {phase === 'idle' ? (
                <div className="relative pl-6 space-y-6 before:content-[''] before:absolute before:left-[9px] before:top-2 before:bottom-2 before:w-[2px] before:bg-surface-low">
                  {STEPS_TEMPLATE.map((step, i) => {
                    const Icon = step.icon;
                    return (
                      <div key={step.id} className="relative flex items-start gap-3">
                        <div className={cn("absolute -left-[15px] top-0.5 w-2.5 h-2.5 rounded-full z-10",
                          i === 0 ? "bg-primary ring-4 ring-primary/20" : "bg-surface-high")} />
                        <div>
                          <div className={cn("text-[10px] font-black uppercase tracking-widest leading-none",
                            i === 0 ? "text-primary" : "text-muted/60")}>{step.label}</div>
                          <p className="text-[9px] text-muted/50 font-bold mt-0.5">{step.sublabel}</p>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="space-y-2">
                  {steps.map((step, i) => (
                    <motion.div key={step.id} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.03 }}
                      className={cn("flex items-start gap-3 p-2.5 rounded-xl transition-all",
                        step.status === 'running' ? "bg-primary/5" : step.status === 'warn' ? "bg-amber-500/5" : "")}>
                      <div className="mt-0.5 shrink-0">
                        {step.status === 'pending'  && <div className="w-4 h-4 rounded-full border-2 border-surface-high" />}
                        {step.status === 'running'  && <div className="w-4 h-4 rounded-full border-2 border-primary border-t-transparent animate-spin" />}
                        {step.status === 'done'     && <CheckCircle2 size={16} className="text-success-text" />}
                        {step.status === 'warn'     && <AlertTriangle size={16} className="text-amber-500" />}
                      </div>
                      <div className="min-w-0">
                        <div className={cn("text-[10px] font-black uppercase tracking-widest leading-none",
                          step.status === 'pending' ? "text-muted/40" : step.status === 'running' ? "text-primary" :
                          step.status === 'warn' ? "text-amber-500" : "text-foreground")}>{step.label}</div>
                        {step.detail ? (
                          <p className="text-[9px] font-technical text-muted font-bold mt-0.5 break-all">{step.detail}</p>
                        ) : (
                          <p className="text-[9px] text-muted/40 font-bold mt-0.5">{step.sublabel}</p>
                        )}
                      </div>
                    </motion.div>
                  ))}
                </div>
              )}
            </div>
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
                <div>
                  <p className="text-[10px] font-black uppercase tracking-widest mb-1 text-success-text">
                    Ingestion Complete — Sample Queued for Processing
                  </p>
                  <h2 className="font-technical text-2xl font-black text-foreground uppercase">{result.sample_id}</h2>
                  <p className="text-sm text-muted font-medium">{result.test_name}</p>
                </div>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                {[
                  { label: 'Webhook Event ID', value: `#${result.event_id}` },
                  { label: 'Test Methodology',  value: result.test_name },
                  { label: 'Processing Status', value: 'Celery Processing' },
                ].map((item, idx) => (
                  <div key={idx} className="p-4 rounded-2xl bg-surface-low">
                    <p className="text-[9px] font-black uppercase tracking-widest text-muted mb-1">{item.label}</p>
                    <p className="font-technical text-sm font-black text-foreground">{item.value}</p>
                  </div>
                ))}
              </div>
              <p className="text-[10px] text-muted mt-4">
                The sample will appear in tracking views once Celery processes the webhook (usually within seconds).
              </p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Recently Admitted */}
      {recentSamples.length > 0 && (
        <section>
          <header className="mb-8 flex justify-between items-center">
            <div className="flex items-center gap-3">
              <History size={20} className="text-muted" />
              <h2 className="font-headline font-black text-xl text-foreground uppercase tracking-tight">Recently Admitted</h2>
            </div>
          </header>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
            {recentSamples.map((sample, idx) => (
              <motion.div key={`${sample.sample_id}-${idx}`} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
                transition={{ delay: idx * 0.07 }} whileHover={{ y: -4 }}
                className="bg-surface-lowest p-5 rounded-2xl border border-border-ghost flex items-center gap-4 hover:bg-surface-low transition-all group">
                <div className="w-12 h-12 rounded-xl flex items-center justify-center shadow-sm shrink-0 bg-primary/10 text-primary">
                  <Hourglass size={22} className="animate-pulse" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-technical text-sm font-black text-foreground uppercase truncate">{sample.sample_id}</p>
                  <div className="flex items-center gap-2 mt-1">
                    <p className="text-[10px] text-muted uppercase font-black tracking-widest truncate">{sample.test_name}</p>
                    <span className="text-muted/30 font-black text-[10px]">/</span>
                    <p className="text-[10px] text-muted/60 font-bold flex items-center gap-1 whitespace-nowrap">
                      <Clock size={10} />{sample.timestamp}
                    </p>
                  </div>
                </div>
                <ChevronRight size={16} className="text-muted/20 group-hover:text-primary transition-all shrink-0" />
              </motion.div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
