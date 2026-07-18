'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Check,
  ChevronRight,
  Clipboard,
  Download,
  ExternalLink,
  RefreshCw,
  Sparkles,
  UserRound,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  addManualJob,
  createProfile,
  getPack,
  listOpportunities,
  listProfiles,
  listReferrals,
  listToday,
  preparePack,
  replaceOpportunity,
  selectToday,
  streamScoutEvents,
  updateOpportunity,
  updatePack,
  updateProfile,
  updateReferral,
  type ArtifactPack,
  type Opportunity,
  type SearchProfile,
  type ReferralMatch,
} from '@/lib/api/scout';

const tabs = [
  'Résumé',
  'Cover letter',
  'Referral',
  'Outreach',
  'Interview prep',
  'Answers',
] as const;
type Tab = (typeof tabs)[number];

const isInboxJob = (job: Opportunity) =>
  ['selected', 'reserve', 'preparing', 'ready', 'applied'].includes(job.state);

function scoreTone(score: number) {
  if (score >= 85) return 'bg-green-700 text-white';
  if (score >= 70) return 'bg-blue-700 text-white';
  return 'bg-orange-500 text-black';
}

export function ScoutWorkspace({
  initialJobs = [],
  initialProfiles = [],
}: {
  initialJobs?: Opportunity[];
  initialProfiles?: SearchProfile[];
}) {
  const initialInboxJobs = initialJobs.filter(isInboxJob);
  const [jobs, setJobs] = useState<Opportunity[]>(initialInboxJobs);
  const [profiles, setProfiles] = useState<SearchProfile[]>(initialProfiles);
  const [selectedId, setSelectedId] = useState<string | null>(
    initialInboxJobs[0]?.match_id ?? null
  );
  const [tab, setTab] = useState<Tab>('Résumé');
  const [pack, setPack] = useState<ArtifactPack | null>(null);
  const [referrals, setReferrals] = useState<ReferralMatch[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [manualOpen, setManualOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [live, setLive] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [today, availableProfiles] = await Promise.all([listToday(), listProfiles()]);
      const queue = (today.length ? today : await listOpportunities()).filter(isInboxJob);
      setJobs(queue);
      setProfiles(availableProfiles);
      setSelectedId((current) =>
        current && queue.some((job) => job.match_id === current)
          ? current
          : (queue[0]?.match_id ?? null)
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not load the scout queue.');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    async function connect() {
      while (active) {
        try {
          setLive(true);
          await streamScoutEvents(() => void load(), controller.signal);
        } catch {
          if (!controller.signal.aborted) setLive(false);
        }
        if (active) await new Promise((resolve) => setTimeout(resolve, 3000));
      }
    }
    void connect();
    return () => {
      active = false;
      controller.abort();
    };
  }, [load]);
  const selected = useMemo(
    () => jobs.find((job) => job.match_id === selectedId) ?? null,
    [jobs, selectedId]
  );
  const primary = jobs.filter((job) => job.state !== 'reserve');
  const reserves = jobs.filter((job) => job.state === 'reserve');

  useEffect(() => {
    setPack(null);
    setReferrals([]);
    if (!selected) return;
    void listReferrals(selected.match_id)
      .then(setReferrals)
      .catch(() => undefined);
    if (selected.pack_status === 'ready') {
      void getPack(selected.match_id)
        .then(setPack)
        .catch(() => undefined);
    }
  }, [selected]);

  async function buildToday() {
    if (!profiles[0]) {
      setError('Create a search profile before building today’s queue.');
      return;
    }
    setBusy(true);
    try {
      setJobs(await selectToday(profiles[0].profile_id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Selection failed.');
    } finally {
      setBusy(false);
    }
  }

  async function generate() {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      setPack(await preparePack(selected.match_id, Boolean(pack)));
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Pack generation failed.');
    } finally {
      setBusy(false);
    }
  }

  async function move(state: string) {
    if (!selected) return;
    await updateOpportunity(selected.match_id, state);
    await load();
  }

  async function replace() {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      await replaceOpportunity(selected.match_id);
      setSelectedId(null);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'No reserve opportunity is available.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <section className="grid border-b border-black bg-[linear-gradient(to_right,rgba(0,0,0,.07)_1px,transparent_1px),linear-gradient(to_bottom,rgba(0,0,0,.07)_1px,transparent_1px)] bg-[size:24px_24px] px-5 py-7 lg:grid-cols-[1fr_auto] lg:px-8">
        <div>
          <p className="mb-2 font-mono text-[11px] font-bold uppercase tracking-[0.18em] text-blue-700">
            Daily application production desk · {live ? 'Live' : 'Connecting'}
          </p>
          <h1 className="font-serif text-4xl font-black uppercase leading-none tracking-tight md:text-6xl">
            Today’s <span className="text-blue-700">20</span>
          </h1>
          <p className="mt-3 max-w-2xl text-sm">
            A ranked, evidence-backed queue. Nothing is submitted or sent until you decide.
          </p>
        </div>
        <div className="mt-5 flex items-end gap-3 lg:mt-0">
          <Button variant="outline" onClick={() => setManualOpen(true)}>
            + Add job
          </Button>
          <Button variant="outline" onClick={() => setProfileOpen(true)}>
            {profiles.length === 0 ? 'Set preferences' : 'Edit preferences'}
          </Button>
          <Button onClick={buildToday} disabled={busy}>
            <Sparkles /> Build today
          </Button>
        </div>
      </section>

      {error && (
        <div
          role="alert"
          className="border-b border-black bg-orange-100 px-5 py-3 font-mono text-xs"
        >
          <b>Action needed:</b> {error}
        </div>
      )}
      {manualOpen && (
        <ManualJob
          profileId={profiles[0]?.profile_id}
          onClose={() => setManualOpen(false)}
          onSaved={load}
        />
      )}
      {profileOpen && (
        <ProfileSetup
          profile={profiles[0]}
          onClose={() => setProfileOpen(false)}
          onSaved={async () => {
            await load();
            setProfileOpen(false);
          }}
        />
      )}
      {profiles.length === 0 && (
        <button
          onClick={() => setProfileOpen(true)}
          className="grid w-full grid-cols-[auto_1fr_auto] items-center gap-4 border-b border-black bg-blue-50 px-5 py-4 text-left hover:bg-blue-100"
        >
          <span className="grid size-8 place-items-center border border-black bg-blue-700 font-mono text-white">
            01
          </span>
          <span>
            <b className="block font-serif text-lg uppercase">Create your search profile</b>
            <span className="text-sm">
              Set target roles, locations, skills, and the 70-point quality threshold.
            </span>
          </span>
          <ChevronRight />
        </button>
      )}

      <section className="grid min-h-[calc(100vh-190px)] min-w-0 xl:grid-cols-[330px_minmax(360px,1fr)_minmax(400px,1.08fr)]">
        <aside className="min-w-0 border-b border-black xl:border-b-0 xl:border-r">
          <PanelLabel label="Queue" meta={`${primary.length}/20 ready`} />
          <div className="max-h-[36rem] overflow-auto xl:max-h-[calc(100vh-235px)]">
            {jobs.length === 0 ? (
              <EmptyQueue />
            ) : (
              primary.map((job, index) => (
                <JobRow
                  key={job.match_id}
                  job={job}
                  index={index + 1}
                  active={job.match_id === selectedId}
                  onClick={() => setSelectedId(job.match_id)}
                />
              ))
            )}
          </div>
          {reserves.length > 0 && (
            <details className="border-t border-black">
              <summary className="cursor-pointer px-4 py-3 font-mono text-xs font-bold uppercase">
                Reserve list / {reserves.length}
              </summary>
              {reserves.map((job, index) => (
                <JobRow
                  key={job.match_id}
                  job={job}
                  index={index + 1}
                  active={job.match_id === selectedId}
                  onClick={() => setSelectedId(job.match_id)}
                />
              ))}
            </details>
          )}
        </aside>

        <article className="min-w-0 border-b border-black xl:border-b-0 xl:border-r">
          <PanelLabel
            label="Role intelligence"
            meta={selected ? `${selected.score.toFixed(0)} / 100` : 'No selection'}
          />
          {selected ? (
            <JobDetail job={selected} />
          ) : (
            <BlankPanel
              title="Select an opportunity"
              body="Choose a ranked job to inspect its source, fit evidence, and qualification gaps."
            />
          )}
        </article>

        <aside className="min-w-0">
          <PanelLabel
            label="Application pack"
            meta={
              pack
                ? `${pack.status} · ${pack.llm_usage.cost_usd ? `$${pack.llm_usage.cost_usd.toFixed(4)}` : `${pack.llm_usage.calls || 0} calls`}`
                : selected?.pack_status || 'Not started'
            }
          />
          {selected ? (
            <>
              <div className="flex overflow-x-auto border-b border-black" role="tablist">
                {tabs.map((item) => (
                  <button
                    key={item}
                    role="tab"
                    aria-selected={tab === item}
                    onClick={() => setTab(item)}
                    className={`shrink-0 border-r border-black px-3 py-3 font-mono text-[10px] font-bold uppercase ${tab === item ? 'bg-blue-700 text-white' : 'hover:bg-black hover:text-white'}`}
                  >
                    {item}
                  </button>
                ))}
              </div>
              <PackContent
                tab={tab}
                pack={pack}
                selected={selected}
                referrals={referrals}
                onReferralUpdate={(updated) =>
                  setReferrals((current) =>
                    current.map((item) =>
                      item.referral_match_id === updated.referral_match_id ? updated : item
                    )
                  )
                }
                onPackUpdate={setPack}
              />
              <div className="sticky bottom-0 flex flex-wrap gap-2 border-t border-black bg-[#f3f0e8] p-3">
                <Button size="sm" onClick={generate} disabled={busy}>
                  <RefreshCw className={busy ? 'animate-spin' : ''} />
                  {pack ? 'Regenerate' : 'Prepare pack'}
                </Button>
                <Button size="sm" variant="outline" onClick={() => void copyPack(tab, pack)}>
                  <Clipboard /> Copy
                </Button>
                {pack?.resume_id && (
                  <a
                    href={
                      tab === 'Cover letter'
                        ? `/api/v1/resumes/${pack.resume_id}/cover-letter/pdf`
                        : `/api/v1/resumes/${pack.resume_id}/pdf`
                    }
                  >
                    <Button size="sm" variant="success">
                      <Download /> {tab === 'Cover letter' ? 'Letter PDF' : 'Résumé PDF'}
                    </Button>
                  </a>
                )}
                {pack?.resume_id && tab === 'Résumé' && (
                  <a href={`/builder?id=${pack.resume_id}`}>
                    <Button size="sm" variant="outline">
                      Edit résumé
                    </Button>
                  </a>
                )}
                <Button size="sm" variant="outline" onClick={() => void move('ignored')}>
                  Ignore
                </Button>
                <Button size="sm" variant="outline" onClick={() => void replace()} disabled={busy}>
                  Replace
                </Button>
                <Button size="sm" variant="outline" onClick={() => void move('applied')}>
                  <Check /> Mark applied
                </Button>
              </div>
            </>
          ) : (
            <BlankPanel
              title="No pack selected"
              body="Application materials appear here after you select a job."
            />
          )}
        </aside>
      </section>
    </main>
  );
}

function PanelLabel({ label, meta }: { label: string; meta: string }) {
  return (
    <div className="flex h-11 items-center justify-between border-b border-black bg-black px-4 text-white">
      <span className="font-mono text-[11px] font-bold uppercase tracking-widest">{label}</span>
      <span className="font-mono text-[10px] uppercase text-blue-200">{meta}</span>
    </div>
  );
}

function JobRow({
  job,
  index,
  active,
  onClick,
}: {
  job: Opportunity;
  index: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`grid w-full grid-cols-[34px_1fr_auto] border-b border-black text-left ${active ? 'bg-blue-50' : 'hover:bg-white'}`}
    >
      <span className="border-r border-black py-4 text-center font-mono text-xs font-bold">
        {String(index).padStart(2, '0')}
      </span>
      <span className="min-w-0 p-3">
        <span className="block truncate font-serif text-lg font-black uppercase leading-tight">
          {job.posting.title}
        </span>
        <span className="mt-1 block truncate font-mono text-[10px] uppercase tracking-wider">
          {job.posting.company} · {job.posting.location || 'Location open'}
        </span>
        <span className="mt-2 flex gap-2 font-mono text-[9px] uppercase">
          <b>{job.posting.source_type}</b>
          <span>{job.referral_count ? `${job.referral_count} contacts` : 'No referral yet'}</span>
        </span>
      </span>
      <span
        className={`m-3 self-start border border-black px-2 py-1 font-mono text-xs font-black ${scoreTone(job.score)}`}
      >
        {job.score.toFixed(0)}
      </span>
    </button>
  );
}

function JobDetail({ job }: { job: Opportunity }) {
  return (
    <div className="max-h-[calc(100vh-235px)] overflow-auto p-5 lg:p-7">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="font-mono text-[10px] font-bold uppercase text-blue-700">
            {job.posting.company}
          </p>
          <h2 className="mt-1 font-serif text-3xl font-black uppercase leading-none">
            {job.posting.title}
          </h2>
          <p className="mt-2 font-mono text-xs uppercase">
            {job.posting.location || 'Location not listed'} ·{' '}
            {job.posting.workplace_type || 'Workplace not listed'}
          </p>
        </div>
        {job.posting.source_url && (
          <a
            aria-label="Open original posting"
            href={job.posting.source_url}
            target="_blank"
            rel="noreferrer"
            className="border border-black p-2 shadow-sw-sm hover:bg-blue-700 hover:text-white"
          >
            <ExternalLink className="size-4" />
          </a>
        )}
      </div>
      <div className="my-6 grid grid-cols-3 border border-black">
        {Object.entries(job.score_components)
          .slice(0, 6)
          .map(([name, value]) => (
            <div key={name} className="border-b border-r border-black p-3">
              <span className="block font-mono text-[9px] uppercase">
                {name.replaceAll('_', ' ')}
              </span>
              <b className="font-serif text-2xl">{Math.round(value)}</b>
            </div>
          ))}
      </div>
      <h3 className="font-mono text-[11px] font-bold uppercase tracking-widest">Why it fits</h3>
      <p className="mt-2 text-sm leading-6">{job.explanation}</p>
      {job.gaps.length > 0 && (
        <>
          <h3 className="mt-6 font-mono text-[11px] font-bold uppercase tracking-widest">
            Qualification gaps
          </h3>
          <ul className="mt-2 border border-black bg-orange-50 p-4 text-sm">
            {job.gaps.map((gap) => (
              <li key={gap}>— {gap}</li>
            ))}
          </ul>
        </>
      )}
      <h3 className="mt-6 font-mono text-[11px] font-bold uppercase tracking-widest">
        Original job description
      </h3>
      <p className="mt-2 whitespace-pre-wrap text-sm leading-6">{job.posting.description}</p>
    </div>
  );
}

function PackContent({
  tab,
  pack,
  selected,
  referrals,
  onReferralUpdate,
  onPackUpdate,
}: {
  tab: Tab;
  pack: ArtifactPack | null;
  selected: Opportunity;
  referrals: ReferralMatch[];
  onReferralUpdate: (referral: ReferralMatch) => void;
  onPackUpdate: (pack: ArtifactPack) => void;
}) {
  let content = '';
  if (pack) {
    if (tab === 'Cover letter') content = pack.cover_letter || '';
    if (tab === 'Referral')
      content = [
        pack.referral_subject && `Subject: ${pack.referral_subject}`,
        pack.referral_email,
        pack.linkedin_message && `LinkedIn variant:\n${pack.linkedin_message}`,
      ]
        .filter(Boolean)
        .join('\n\n');
    if (tab === 'Outreach') content = pack.outreach_message || '';
    if (tab === 'Interview prep') content = JSON.stringify(pack.interview_prep, null, 2);
    if (tab === 'Answers') content = JSON.stringify(pack.application_answers, null, 2);
    if (tab === 'Résumé')
      content = pack.resume_id
        ? `Immutable tailored résumé ${pack.resume_id}\n\nVerified field changes\n${JSON.stringify(pack.provenance.fields || {}, null, 2)}`
        : '';
  }
  if (!pack)
    return (
      <BlankPanel
        title="Pack not prepared"
        body={`Prepare evidence-backed materials for ${selected.posting.title}. The master résumé remains untouched.`}
        icon
      />
    );
  return (
    <div className="min-h-[28rem] max-h-[calc(100vh-300px)] overflow-auto bg-white p-6">
      {tab === 'Referral' && referrals.length > 0 && (
        <div className="mb-6 grid gap-3">
          <p className="font-mono text-[10px] font-bold uppercase tracking-widest">
            Best first-degree contacts
          </p>
          {referrals.map((referral, index) => (
            <ReferralCard
              key={referral.referral_match_id}
              matchId={selected.match_id}
              referral={referral}
              rank={index + 1}
              onUpdate={onReferralUpdate}
            />
          ))}
        </div>
      )}
      {['Cover letter', 'Referral', 'Outreach'].includes(tab) ? (
        <>
          {tab === 'Referral' && (
            <div className="mb-4 border-y border-black py-3 text-sm">
              <b>Subject: {pack.referral_subject}</b>
            </div>
          )}
          <EditablePackCopy
            tab={tab}
            pack={pack}
            content={tab === 'Referral' ? pack.referral_email || '' : content}
            onSaved={onPackUpdate}
          />
          {tab === 'Referral' && pack.linkedin_message && (
            <div className="mt-5 border-t border-black pt-4">
              <p className="font-mono text-[10px] font-bold uppercase">LinkedIn variant</p>
              <p className="mt-2 text-sm leading-6">{pack.linkedin_message}</p>
            </div>
          )}
        </>
      ) : (
        <pre className="whitespace-pre-wrap font-sans text-sm leading-6">
          {content || 'This artifact is not available yet.'}
        </pre>
      )}
    </div>
  );
}

function EditablePackCopy({
  tab,
  pack,
  content,
  onSaved,
}: {
  tab: Tab;
  pack: ArtifactPack;
  content: string;
  onSaved: (pack: ArtifactPack) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(content);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    setDraft(content);
    setEditing(false);
  }, [content, tab]);

  async function save() {
    setSaving(true);
    try {
      const key =
        tab === 'Cover letter'
          ? 'cover_letter'
          : tab === 'Outreach'
            ? 'outreach_message'
            : 'referral_email';
      onSaved(await updatePack(pack.match_id, { [key]: draft }));
      setEditing(false);
    } finally {
      setSaving(false);
    }
  }
  return (
    <div>
      {editing ? (
        <textarea
          aria-label={`Edit ${tab}`}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          className="min-h-80 w-full border border-black p-4 text-sm leading-6"
        />
      ) : (
        <pre className="whitespace-pre-wrap font-sans text-sm leading-6">{content}</pre>
      )}
      <div className="mt-4 flex gap-2">
        {editing ? (
          <>
            <Button size="sm" onClick={() => void save()} disabled={saving}>
              {saving ? 'Saving…' : 'Save edits'}
            </Button>
            <Button size="sm" variant="outline" onClick={() => setEditing(false)}>
              Cancel
            </Button>
          </>
        ) : (
          <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
            Edit copy
          </Button>
        )}
      </div>
    </div>
  );
}

function ReferralCard({
  matchId,
  referral,
  rank,
  onUpdate,
}: {
  matchId: string;
  referral: ReferralMatch;
  rank: number;
  onUpdate: (referral: ReferralMatch) => void;
}) {
  const [notes, setNotes] = useState(referral.response_notes || '');
  const contact = referral.contact;
  async function save(payload: { contacted?: boolean; response_notes?: string }) {
    onUpdate(await updateReferral(matchId, referral.referral_match_id, payload));
  }
  return (
    <div className="border border-black bg-blue-50 p-3 shadow-sw-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <b className="font-serif uppercase">
            {rank}. {contact.first_name} {contact.last_name}
          </b>
          <p className="font-mono text-[9px] uppercase">
            {contact.position || 'Role not listed'} · {referral.score.toFixed(0)} match
          </p>
        </div>
        {contact.profile_url && (
          <a
            href={contact.profile_url}
            target="_blank"
            rel="noreferrer"
            className="font-mono text-[9px] font-bold uppercase underline"
          >
            Profile
          </a>
        )}
      </div>
      <p className="mt-2 text-xs leading-5">{referral.explanation}</p>
      <textarea
        aria-label={`Response notes for ${contact.first_name}`}
        value={notes}
        onChange={(event) => setNotes(event.target.value)}
        placeholder="Response notes"
        className="mt-3 min-h-16 w-full border border-black bg-white p-2 text-xs"
      />
      <div className="mt-2 flex gap-2">
        <Button
          size="sm"
          variant="outline"
          onClick={() => void save({ contacted: !referral.contacted_at })}
        >
          {referral.contacted_at ? 'Undo contacted' : 'Mark contacted'}
        </Button>
        <Button size="sm" variant="outline" onClick={() => void save({ response_notes: notes })}>
          Save note
        </Button>
      </div>
    </div>
  );
}

function BlankPanel({
  title,
  body,
  icon = false,
}: {
  title: string;
  body: string;
  icon?: boolean;
}) {
  return (
    <div className="flex min-h-[28rem] flex-col items-center justify-center p-10 text-center">
      {icon && (
        <div className="mb-5 border border-black bg-blue-700 p-4 text-white shadow-sw-md">
          <UserRound />
        </div>
      )}
      <h2 className="font-serif text-2xl font-black uppercase">{title}</h2>
      <p className="mt-3 max-w-sm text-sm leading-6 text-neutral-600">{body}</p>
    </div>
  );
}
function EmptyQueue() {
  return (
    <BlankPanel
      title="Your queue is clear"
      body="Add a job manually or configure public ATS and career-site sources, then build today’s ranked list."
      icon
    />
  );
}

async function copyPack(tab: Tab, pack: ArtifactPack | null) {
  if (!pack) return;
  const values: Record<Tab, string> = {
    Résumé: pack.resume_id || '',
    'Cover letter': pack.cover_letter || '',
    Referral: [pack.referral_subject, pack.referral_email].filter(Boolean).join('\n\n'),
    Outreach: pack.outreach_message || '',
    'Interview prep': JSON.stringify(pack.interview_prep, null, 2),
    Answers: JSON.stringify(pack.application_answers, null, 2),
  };
  await navigator.clipboard.writeText(values[tab]);
}

function ManualJob({
  profileId,
  onClose,
  onSaved,
}: {
  profileId?: string;
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const [form, setForm] = useState({
    title: '',
    company: '',
    location: '',
    source_url: '',
    description: '',
  });
  const [saving, setSaving] = useState(false);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    try {
      await addManualJob({ ...form, profile_id: profileId || null });
      await onSaved();
      onClose();
    } finally {
      setSaving(false);
    }
  }
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4">
      <form
        onSubmit={submit}
        className="w-full max-w-2xl border border-black bg-[#f3f0e8] shadow-[8px_8px_0_#000]"
      >
        <div className="flex items-center justify-between border-b border-black bg-blue-700 p-4 text-white">
          <h2 className="font-serif text-2xl font-black uppercase">Add an opportunity</h2>
          <button type="button" onClick={onClose} className="font-mono text-xs uppercase">
            Close ×
          </button>
        </div>
        <div className="grid gap-3 p-5 sm:grid-cols-2">
          {(['title', 'company', 'location', 'source_url'] as const).map((field) => (
            <label key={field} className="font-mono text-[10px] font-bold uppercase">
              {field.replace('_', ' ')}
              <input
                required={field === 'title' || field === 'company'}
                value={form[field]}
                onChange={(e) => setForm({ ...form, [field]: e.target.value })}
                className="mt-1 h-10 w-full border border-black bg-white px-3 font-sans text-sm normal-case"
              />
            </label>
          ))}
          <label className="font-mono text-[10px] font-bold uppercase sm:col-span-2">
            Job description
            <textarea
              required
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              className="mt-1 min-h-48 w-full border border-black bg-white p-3 font-sans text-sm normal-case"
            />
          </label>
        </div>
        <div className="flex justify-end gap-3 border-t border-black p-4">
          <Button type="button" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={saving}>
            {saving ? 'Scoring…' : 'Add and score'}
            <ChevronRight />
          </Button>
        </div>
      </form>
    </div>
  );
}

function ProfileSetup({
  profile,
  onClose,
  onSaved,
}: {
  profile?: SearchProfile;
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const config = profile?.config;
  const join = (value: unknown) => (Array.isArray(value) ? value.join(', ') : '');
  const [name, setName] = useState(profile?.name ?? 'Primary search');
  const [titles, setTitles] = useState(join(config?.desired_titles) || 'Software Engineer');
  const [locations, setLocations] = useState(join(config?.locations) || 'Singapore, Remote');
  const [skills, setSkills] = useState(join(config?.required_skills));
  const [minimumScore, setMinimumScore] = useState(config?.minimum_match_score ?? 70);
  const [saving, setSaving] = useState(false);
  const split = (value: string) =>
    value
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    try {
      const payload = {
        name,
        is_active: true,
        config: {
          ...(config ?? {}),
          desired_titles: split(titles),
          locations: split(locations),
          required_skills: split(skills),
          workplace_types: config?.workplace_types ?? ['remote', 'hybrid', 'onsite'],
          daily_pack_limit: config?.daily_pack_limit ?? 20,
          reserve_limit: config?.reserve_limit ?? 10,
          minimum_match_score: minimumScore,
          max_per_company: config?.max_per_company ?? 2,
          timezone: config?.timezone ?? 'Asia/Singapore',
        },
      };
      if (profile) await updateProfile(profile.profile_id, payload);
      else await createProfile(payload);
      await onSaved();
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4">
      <form
        onSubmit={submit}
        className="w-full max-w-xl border border-black bg-[#f3f0e8] shadow-[8px_8px_0_#000]"
      >
        <div className="flex items-center justify-between border-b border-black bg-blue-700 p-4 text-white">
          <div>
            <p className="font-mono text-[9px] uppercase tracking-widest">Step 1 / Search rules</p>
            <h2 className="font-serif text-2xl font-black uppercase">Set preferences</h2>
          </div>
          <button type="button" onClick={onClose} className="font-mono text-xs uppercase">
            Close ×
          </button>
        </div>
        <div className="grid gap-4 p-5">
          <ProfileField label="Profile name" value={name} onChange={setName} />
          <ProfileField
            label="Target titles — comma separated"
            value={titles}
            onChange={setTitles}
          />
          <ProfileField
            label="Locations — comma separated"
            value={locations}
            onChange={setLocations}
          />
          <ProfileField
            label="Required skills — comma separated"
            value={skills}
            onChange={setSkills}
          />
          <label className="font-mono text-[10px] font-bold uppercase">
            Minimum fit score / {minimumScore}
            <input
              type="range"
              min="50"
              max="95"
              value={minimumScore}
              onChange={(event) => setMinimumScore(Number(event.target.value))}
              className="mt-2 w-full accent-blue-700"
            />
          </label>
          <p className="border border-black bg-white p-3 text-xs leading-5">
            The system will prepare at most 20 packs, keep 10 qualified reserves, and limit each
            company to two roles per day.
          </p>
        </div>
        <div className="flex justify-end gap-3 border-t border-black p-4">
          <Button type="button" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={saving}>
            {saving ? 'Saving…' : 'Save search profile'}
          </Button>
        </div>
      </form>
    </div>
  );
}

function ProfileField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="font-mono text-[10px] font-bold uppercase">
      {label}
      <input
        required
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1 h-10 w-full border border-black bg-white px-3 font-sans text-sm normal-case"
      />
    </label>
  );
}
