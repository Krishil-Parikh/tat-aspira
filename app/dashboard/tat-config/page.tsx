"use client";
import React, { useEffect, useMemo, useState } from 'react';
import useSWR from 'swr';
import { motion, AnimatePresence } from 'motion/react';
import {
  Timer, Search, Edit3, Save, X, Plus, Trash2, RefreshCw,
  CheckCircle2, AlertCircle, ChevronLeft, ChevronRight, Building2,
} from 'lucide-react';
import {
  fetchTatConfig, createTatEntry, updateTatEntry, deleteTatEntry,
  fetchTatOrgs, setOrgTatCategory,
  type TatCategory, type TatEntry, type TatEntryInput,
} from '@/app/lib/api';
import { cn } from '@/components/ui/utils';

const CATEGORIES: { id: TatCategory; label: string }[] = [
  { id: 'B2B', label: 'B2B' },
  { id: 'PRIORITY', label: 'Priority' },
  { id: 'HLM', label: 'HLM' },
  { id: 'CAMP', label: 'Camp' },
];
const PAGE_SIZE = 50;
const STAGES = [
  { key: 'accession_mins', label: 'Accession' },
  { key: 'validation_mins', label: 'Report Validation' },
  { key: 'approval_mins', label: 'Report Approval' },
  { key: 'submission_mins', label: 'Report Submission' },
] as const;
type StageKey = typeof STAGES[number]['key'];

/** 2880 → "2d", 1530 → "1d 1h 30m", null → "—" */
function formatMins(mins: number | null | undefined): string {
  if (mins === null || mins === undefined) return '—';
  const d = Math.floor(mins / 1440);
  const h = Math.floor((mins % 1440) / 60);
  const m = mins % 60;
  const parts = [d && `${d}d`, h && `${h}h`, m && `${m}m`].filter(Boolean);
  return parts.length ? parts.join(' ') : '0m';
}

/** Days / hours / minutes entry for one duration (stored as minutes). */
function DurationInput({ value, onChange, required }: {
  value: number | null; onChange: (v: number | null) => void; required?: boolean;
}) {
  const d = value === null ? '' : Math.floor(value / 1440);
  const h = value === null ? '' : Math.floor((value % 1440) / 60);
  const m = value === null ? '' : value % 60;
  const set = (part: 'd' | 'h' | 'm', raw: string) => {
    const cur = { d: Number(d || 0), h: Number(h || 0), m: Number(m || 0) };
    cur[part] = Math.max(0, Number(raw || 0));
    const total = cur.d * 1440 + cur.h * 60 + cur.m;
    onChange(total === 0 && !required && raw === '' && value === null ? null : total);
  };
  return (
    <div className="flex items-center gap-2">
      {([['d', d, 'days'], ['h', h, 'hrs'], ['m', m, 'min']] as const).map(([part, v, unit]) => (
        <label key={part} className="flex items-center gap-1.5 bg-surface-low border border-border-ghost rounded-xl px-3 py-2 focus-within:ring-2 focus-within:ring-primary/30">
          <input
            type="number"
            min={0}
            value={v}
            onChange={e => set(part, e.target.value)}
            className="w-12 bg-transparent font-technical font-black text-foreground outline-none"
          />
          <span className="text-[9px] font-black text-muted uppercase tracking-widest">{unit}</span>
        </label>
      ))}
      {!required && value !== null && (
        <button type="button" onClick={() => onChange(null)} className="text-[9px] font-black text-muted uppercase tracking-widest hover:text-foreground">
          Clear
        </button>
      )}
    </div>
  );
}

type Draft = TatEntryInput & { id?: number };

const emptyDraft = (category: TatCategory): Draft => ({
  test_code: '', client_category: category, test_name: '',
  accession_mins: null, validation_mins: null, approval_mins: null, submission_mins: null,
  overall_tat_mins: 0, is_active: 1,
});

const stageSum = (d: Draft): number | null =>
  STAGES.every(s => d[s.key] !== null) ? STAGES.reduce((t, s) => t + (d[s.key] as number), 0) : null;

export default function TatConfigPage() {
  const [view, setView] = useState<'tests' | 'orgs'>('tests');
  const [category, setCategory] = useState<TatCategory>('B2B');
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(0);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [autoSum, setAutoSum] = useState(true);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; msg: string } | null>(null);

  // Debounce the search box into the server query.
  useEffect(() => {
    const t = setTimeout(() => { setQuery(search.trim()); setPage(0); }, 300);
    return () => clearTimeout(t);
  }, [search]);

  const listKey = ['tat-config', category, query, page] as const;
  const { data, error, isLoading, mutate } = useSWR(listKey, () =>
    fetchTatConfig({ category, q: query || undefined, limit: PAGE_SIZE, offset: page * PAGE_SIZE }));
  const { data: orgData, mutate: mutateOrgs } = useSWR(view === 'orgs' ? 'tat-orgs' : null, fetchTatOrgs);

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const flash = (type: 'success' | 'error', msg: string) => {
    setFeedback({ type, msg });
    if (type === 'success') setTimeout(() => setFeedback(null), 3000);
  };

  const openEdit = (entry: TatEntry) => {
    const d: Draft = {
      id: entry.id, test_code: entry.test_code, client_category: entry.client_category,
      test_name: entry.test_name ?? '', accession_mins: entry.accession_mins,
      validation_mins: entry.validation_mins, approval_mins: entry.approval_mins,
      submission_mins: entry.submission_mins, overall_tat_mins: entry.overall_tat_mins,
      is_active: entry.is_active,
    };
    setAutoSum(stageSum(d) === entry.overall_tat_mins);
    setConfirmDelete(false);
    setDraft(d);
  };

  const openNew = () => { setAutoSum(true); setConfirmDelete(false); setDraft(emptyDraft(category)); };

  const setStage = (key: StageKey, v: number | null) => {
    if (!draft) return;
    const next = { ...draft, [key]: v };
    const sum = stageSum(next);
    if (autoSum && sum !== null) next.overall_tat_mins = sum;
    setDraft(next);
  };

  const sum = draft ? stageSum(draft) : null;

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!draft) return;
    if (!draft.id && !draft.test_code?.trim()) { flash('error', 'Test code is required'); return; }
    if (!draft.overall_tat_mins || draft.overall_tat_mins <= 0) { flash('error', 'Overall TAT must be greater than zero'); return; }
    setSubmitting(true);
    try {
      const body: TatEntryInput = {
        test_name: draft.test_name?.trim() || null,
        accession_mins: draft.accession_mins, validation_mins: draft.validation_mins,
        approval_mins: draft.approval_mins, submission_mins: draft.submission_mins,
        overall_tat_mins: draft.overall_tat_mins, is_active: draft.is_active,
      };
      if (draft.id) {
        await updateTatEntry(draft.id, body);
        flash('success', `Saved ${draft.test_code} (${draft.client_category}) — applies to new samples immediately`);
      } else {
        await createTatEntry({ ...body, test_code: draft.test_code!.trim().toUpperCase(), client_category: draft.client_category });
        flash('success', `Added ${draft.test_code!.toUpperCase()} (${draft.client_category})`);
      }
      setDraft(null);
      mutate();
    } catch (err: any) {
      flash('error', err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async () => {
    if (!draft?.id) return;
    setSubmitting(true);
    try {
      await deleteTatEntry(draft.id);
      flash('success', `Removed ${draft.test_code} (${draft.client_category})`);
      setDraft(null);
      mutate();
    } catch (err: any) {
      flash('error', err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleOrgCategory = async (orgId: number, cat: TatCategory, name: string) => {
    try {
      await setOrgTatCategory(orgId, cat);
      flash('success', `${name} now uses ${cat} TAT`);
      mutateOrgs();
    } catch (err: any) {
      flash('error', err.message);
    }
  };

  const counts = data?.counts;
  const tabs = useMemo(() => CATEGORIES.map(c => ({ ...c, n: counts?.[c.id] ?? 0 })), [counts]);

  return (
    <div className="space-y-8 pb-20">
      {/* Header */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Timer size={16} className="text-primary" />
            <span className="text-[10px] font-black text-muted uppercase tracking-widest">Committed Turnaround</span>
          </div>
          <h1 className="text-5xl font-black text-foreground tracking-tighter leading-none mb-3">TAT CONFIGURATION</h1>
          <p className="text-muted font-medium max-w-xl">
            Predefined TAT per test for each client category. SLA deadlines and breach alerts use these values as soon as you save.
          </p>
        </div>
        <div className="flex items-center gap-2 bg-surface-low border border-border-ghost rounded-2xl p-1">
          {([['tests', 'Tests', Timer], ['orgs', 'Client Categories', Building2]] as const).map(([id, label, Icon]) => (
            <button
              key={id}
              onClick={() => setView(id)}
              className={cn(
                "flex items-center gap-2 px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all",
                view === id ? "bg-primary text-white shadow-lg shadow-primary/20" : "text-muted hover:text-foreground"
              )}
            >
              <Icon size={14} /> {label}
            </button>
          ))}
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
          <p className="text-xs font-black uppercase tracking-wider flex-1">{feedback.msg}</p>
          <button onClick={() => setFeedback(null)} className="opacity-60 hover:opacity-100"><X size={16} /></button>
        </motion.div>
      )}

      {error && (
        <div className="p-6 rounded-[2rem] border border-red-500/30 bg-red-500/10 text-red-500 flex items-center gap-3">
          <AlertCircle size={20} />
          <p className="text-xs font-black uppercase tracking-wider">
            {String(error.message).includes('403') || String(error.message).toLowerCase().includes('forbidden')
              ? 'TAT configuration is restricted to admins.'
              : `Could not load TAT configuration: ${error.message}`}
          </p>
        </div>
      )}

      {error ? null : view === 'tests' ? (
        <>
          {/* Toolbar */}
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex flex-wrap gap-2">
              {tabs.map(t => (
                <button
                  key={t.id}
                  onClick={() => { setCategory(t.id); setPage(0); }}
                  className={cn(
                    "px-4 py-2.5 rounded-2xl border text-[10px] font-black uppercase tracking-widest transition-all",
                    category === t.id
                      ? "bg-primary/10 border-primary/40 text-primary"
                      : "bg-surface-low border-border-ghost text-muted hover:text-foreground"
                  )}
                >
                  {t.label} <span className="font-technical ml-1 opacity-70">{t.n}</span>
                </button>
              ))}
            </div>
            <div className="flex items-center gap-3">
              <div className="relative group">
                <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-muted group-focus-within:text-primary transition-colors" size={16} />
                <input
                  type="text"
                  placeholder="Search code or test name..."
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  className="pl-12 pr-6 py-3 bg-surface-low border border-border-ghost rounded-2xl text-sm font-medium focus:ring-2 focus:ring-primary/20 outline-none w-72 transition-all"
                />
              </div>
              <button onClick={() => mutate()} className="p-3 bg-surface-low border border-border-ghost rounded-2xl text-muted hover:text-foreground transition-all" title="Refresh">
                <RefreshCw size={18} className={isLoading ? 'animate-spin' : ''} />
              </button>
              <button onClick={openNew} className="flex items-center gap-2 px-5 py-3 bg-primary text-white rounded-2xl text-[10px] font-black uppercase tracking-widest hover:shadow-lg hover:shadow-primary/20 transition-all">
                <Plus size={16} /> Add Test
              </button>
            </div>
          </div>

          {/* Table */}
          <div className="bg-surface-lowest rounded-[2rem] border border-border-ghost overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-border-ghost">
                    {['Code', 'Test Name', ...STAGES.map(s => s.label), 'Overall TAT', 'Status', 'Last Edited', ''].map(h => (
                      <th key={h} className="px-5 py-4 text-[9px] font-black text-muted uppercase tracking-widest whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {isLoading && (
                    <tr><td colSpan={10} className="px-5 py-16 text-center text-[10px] font-black text-muted uppercase tracking-widest">Loading TAT master...</td></tr>
                  )}
                  {!isLoading && items.length === 0 && (
                    <tr><td colSpan={10} className="px-5 py-16 text-center text-[10px] font-black text-muted uppercase tracking-widest">No tests match</td></tr>
                  )}
                  {items.map(entry => (
                    <tr key={entry.id} className="border-b border-border-ghost/60 hover:bg-surface-low/50 transition-colors group">
                      <td className="px-5 py-3 font-technical text-xs font-black text-primary whitespace-nowrap">{entry.test_code}</td>
                      <td className="px-5 py-3 text-sm font-bold text-foreground max-w-xs truncate" title={entry.test_name ?? ''}>{entry.test_name || '—'}</td>
                      {STAGES.map(s => (
                        <td key={s.key} className="px-5 py-3 font-technical text-xs text-muted whitespace-nowrap">{formatMins(entry[s.key])}</td>
                      ))}
                      <td className="px-5 py-3 font-technical text-sm font-black text-foreground whitespace-nowrap">{formatMins(entry.overall_tat_mins)}</td>
                      <td className="px-5 py-3">
                        <span className={cn(
                          "px-2.5 py-1 rounded-full text-[8px] font-black uppercase tracking-[0.15em] border whitespace-nowrap",
                          entry.is_active ? "bg-success/10 border-success/30 text-success-text" : "bg-red-400/10 border-red-400/30 text-red-400"
                        )}>
                          {entry.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                      <td className="px-5 py-3 text-[10px] text-muted whitespace-nowrap">
                        <div className="font-bold">{entry.updated_by || '—'}</div>
                        <div>{new Date(entry.updated_at).toLocaleString()}</div>
                      </td>
                      <td className="px-5 py-3">
                        <button onClick={() => openEdit(entry)} className="w-9 h-9 rounded-xl bg-surface-low flex items-center justify-center text-muted group-hover:text-primary transition-all" title="Edit">
                          <Edit3 size={16} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex items-center justify-between px-5 py-4 border-t border-border-ghost">
              <p className="text-[10px] font-black text-muted uppercase tracking-widest">
                {total ? `${page * PAGE_SIZE + 1}–${Math.min(total, (page + 1) * PAGE_SIZE)} of ${total}` : '0 tests'}
              </p>
              <div className="flex items-center gap-2">
                <button disabled={page === 0} onClick={() => setPage(p => p - 1)} className="p-2 rounded-xl bg-surface-low text-muted hover:text-foreground disabled:opacity-30"><ChevronLeft size={16} /></button>
                <span className="font-technical text-xs font-black text-muted">{page + 1} / {pages}</span>
                <button disabled={page + 1 >= pages} onClick={() => setPage(p => p + 1)} className="p-2 rounded-xl bg-surface-low text-muted hover:text-foreground disabled:opacity-30"><ChevronRight size={16} /></button>
              </div>
            </div>
          </div>
        </>
      ) : (
        /* Client categories */
        <div className="bg-surface-lowest rounded-[2rem] border border-border-ghost overflow-hidden">
          <div className="p-6 border-b border-border-ghost">
            <p className="text-sm text-muted font-medium">
              Each client organisation uses one TAT category. Walk-in patients and organisations without a category use <span className="font-black text-foreground">B2B</span>; a test missing from the chosen category falls back to its B2B value.
            </p>
          </div>
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-border-ghost">
                {['Organisation', 'LIS Org ID', 'TAT Category'].map(h => (
                  <th key={h} className="px-5 py-4 text-[9px] font-black text-muted uppercase tracking-widest">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {!orgData && (
                <tr><td colSpan={3} className="px-5 py-16 text-center text-[10px] font-black text-muted uppercase tracking-widest">Loading organisations...</td></tr>
              )}
              {orgData?.orgs.length === 0 && (
                <tr><td colSpan={3} className="px-5 py-16 text-center text-[10px] font-black text-muted uppercase tracking-widest">No organisations yet — they appear after their first bill arrives</td></tr>
              )}
              {orgData?.orgs.map(org => (
                <tr key={org.id} className="border-b border-border-ghost/60">
                  <td className="px-5 py-3 text-sm font-bold text-foreground">{org.org_name}</td>
                  <td className="px-5 py-3 font-technical text-xs text-muted">{org.external_org_id}</td>
                  <td className="px-5 py-3">
                    <select
                      value={CATEGORIES.some(c => c.id === org.sla_tier) ? org.sla_tier : 'B2B'}
                      onChange={e => handleOrgCategory(org.id, e.target.value as TatCategory, org.org_name)}
                      className="bg-surface-low border border-border-ghost rounded-xl px-3 py-2 text-xs font-black uppercase tracking-widest text-foreground outline-none focus:ring-2 focus:ring-primary/30"
                    >
                      {CATEGORIES.map(c => <option key={c.id} value={c.id}>{c.label}</option>)}
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Edit / add modal */}
      <AnimatePresence>
        {draft && (
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
              className="bg-surface-lowest rounded-[2.5rem] border border-border-ghost shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto"
            >
              <form onSubmit={handleSave}>
                <div className="p-8 bg-surface-low/30 space-y-6">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-[10px] font-black text-primary uppercase tracking-[0.3em] mb-1">
                        {draft.id ? 'Edit Predefined TAT' : 'Add Predefined TAT'} · {draft.client_category}
                      </p>
                      <h2 className="text-2xl font-headline font-black text-foreground uppercase tracking-tight">
                        {draft.id ? draft.test_code : 'New Test'}
                      </h2>
                    </div>
                    <button type="button" onClick={() => setDraft(null)} className="p-2 text-muted hover:text-foreground"><X size={24} /></button>
                  </div>

                  {!draft.id && (
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="block text-[10px] font-black text-muted uppercase tracking-widest mb-2">Test Code (as in LIS)</label>
                        <input
                          value={draft.test_code}
                          onChange={e => setDraft({ ...draft, test_code: e.target.value })}
                          className="w-full bg-surface-low border border-border-ghost rounded-2xl px-5 py-3 font-technical font-black uppercase text-foreground focus:ring-2 focus:ring-primary outline-none"
                          placeholder="e.g. BIOC074"
                        />
                      </div>
                      <div>
                        <label className="block text-[10px] font-black text-muted uppercase tracking-widest mb-2">Category</label>
                        <select
                          value={draft.client_category}
                          onChange={e => setDraft({ ...draft, client_category: e.target.value as TatCategory })}
                          className="w-full bg-surface-low border border-border-ghost rounded-2xl px-5 py-3 font-black uppercase text-foreground focus:ring-2 focus:ring-primary outline-none"
                        >
                          {CATEGORIES.map(c => <option key={c.id} value={c.id}>{c.label}</option>)}
                        </select>
                      </div>
                    </div>
                  )}

                  <div>
                    <label className="block text-[10px] font-black text-muted uppercase tracking-widest mb-2">Test Name</label>
                    <input
                      value={draft.test_name ?? ''}
                      onChange={e => setDraft({ ...draft, test_name: e.target.value })}
                      className="w-full bg-surface-low border border-border-ghost rounded-2xl px-5 py-3 font-bold text-foreground focus:ring-2 focus:ring-primary outline-none"
                    />
                  </div>

                  <div className="space-y-3">
                    <p className="text-[10px] font-black text-muted uppercase tracking-widest">Stage Breakdown <span className="normal-case font-bold tracking-normal">(optional)</span></p>
                    {STAGES.map(s => (
                      <div key={s.key} className="flex flex-wrap items-center justify-between gap-3">
                        <span className="text-xs font-black text-foreground uppercase tracking-wider w-40">{s.label}</span>
                        <DurationInput value={draft[s.key]} onChange={v => setStage(s.key, v)} />
                      </div>
                    ))}
                  </div>

                  <div className="p-5 bg-primary/5 border border-primary/20 rounded-2xl space-y-3">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <span className="text-xs font-black text-primary uppercase tracking-wider w-40">Overall TAT</span>
                      <DurationInput
                        required
                        value={draft.overall_tat_mins || null}
                        onChange={v => { setAutoSum(false); setDraft({ ...draft, overall_tat_mins: v ?? 0 }); }}
                      />
                    </div>
                    <div className="flex items-center justify-between text-[10px] text-muted">
                      <span>
                        {sum !== null
                          ? <>Sum of stages: <span className="font-technical font-black text-foreground">{formatMins(sum)}</span></>
                          : 'Fill all four stages to compute the overall TAT automatically'}
                      </span>
                      {sum !== null && sum !== draft.overall_tat_mins && (
                        <button type="button" onClick={() => { setAutoSum(true); setDraft({ ...draft, overall_tat_mins: sum }); }} className="font-black text-primary uppercase tracking-widest">
                          Use sum
                        </button>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center justify-between p-4 bg-surface-low rounded-2xl">
                    <div className="flex items-center gap-3">
                      <div className={cn("w-3 h-3 rounded-full", draft.is_active ? "bg-success" : "bg-red-400")} />
                      <span className="text-xs font-black uppercase tracking-widest">Used for SLA</span>
                    </div>
                    <button
                      type="button"
                      onClick={() => setDraft({ ...draft, is_active: draft.is_active ? 0 : 1 })}
                      className={cn(
                        "px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all",
                        draft.is_active ? "bg-success/10 text-success-text" : "bg-red-400/10 text-red-400"
                      )}
                    >
                      {draft.is_active ? 'ACTIVE' : 'INACTIVE'}
                    </button>
                  </div>
                </div>

                <div className="p-8 flex flex-wrap gap-4">
                  <button
                    type="submit"
                    disabled={submitting}
                    className="flex-1 bg-primary text-white py-4 rounded-2xl font-black text-sm uppercase tracking-widest hover:shadow-lg hover:shadow-primary/20 transition-all flex items-center justify-center gap-2 disabled:opacity-60"
                  >
                    {submitting ? <RefreshCw size={18} className="animate-spin" /> : <Save size={18} />}
                    {draft.id ? 'Save Changes' : 'Add Test'}
                  </button>
                  {draft.id && (
                    confirmDelete ? (
                      <button type="button" onClick={handleDelete} disabled={submitting} className="px-6 py-4 bg-red-500 text-white rounded-2xl font-black text-sm uppercase tracking-widest">
                        Confirm Delete
                      </button>
                    ) : (
                      <button type="button" onClick={() => setConfirmDelete(true)} className="px-6 py-4 bg-red-500/10 text-red-500 rounded-2xl font-black text-sm uppercase tracking-widest flex items-center gap-2">
                        <Trash2 size={16} /> Delete
                      </button>
                    )
                  )}
                  <button
                    type="button"
                    onClick={() => setDraft(null)}
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
