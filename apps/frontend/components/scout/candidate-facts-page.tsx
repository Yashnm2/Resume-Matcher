'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import Check from 'lucide-react/dist/esm/icons/check';
import FileUp from 'lucide-react/dist/esm/icons/file-up';
import Pencil from 'lucide-react/dist/esm/icons/pencil';
import Plus from 'lucide-react/dist/esm/icons/plus';
import Save from 'lucide-react/dist/esm/icons/save';
import Trash2 from 'lucide-react/dist/esm/icons/trash-2';
import X from 'lucide-react/dist/esm/icons/x';
import { Button } from '@/components/ui/button';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import {
  createProfile,
  deleteCandidateFact,
  importMasterResumeFacts,
  listCandidateFacts,
  listProfiles,
  saveCandidateFact,
  updateProfile,
  type CandidateFact,
  type SearchProfile,
  type SearchProfileConfig,
} from '@/lib/api/scout';

const categories = [
  'career_goals',
  'writing_preferences',
  'education',
  'experience',
  'projects',
  'leadership',
  'achievements',
  'skills',
  'availability',
  'location',
  'links',
  'work_authorization',
  'application_preferences',
];

const internshipWritingDefaults = {
  fact_key: 'internship_writing_preferences',
  label: 'Internship writing style',
  category: 'writing_preferences',
  value:
    'Lead with technical work, projects, and individual ownership. Use concise evidence and truthful STAR framing. Keep social-media duties out unless the role explicitly values them. Avoid repetition, inflated claims, and invented metrics.',
};

type ProfileForm = {
  name: string;
  desiredTitles: string;
  adjacentTitles: string;
  locations: string;
  industries: string;
  requiredSkills: string;
  preferredSkills: string;
  maximumYearsExperience: number;
  minimumScore: number;
  workplaceTypes: Array<'remote' | 'hybrid' | 'onsite'>;
};

const defaultProfile: ProfileForm = {
  name: 'Primary internship search',
  desiredTitles: 'Software Engineering Intern, Data Science Intern, Investment Analyst Intern',
  adjacentTitles: 'AI Intern, Product Intern, Business Analyst Intern',
  locations: 'Singapore, Remote',
  industries: 'Technology, Financial Services, Venture Capital',
  requiredSkills: 'Python, Data Analysis, Excel',
  preferredSkills: 'Machine Learning, SQL, AI Automation',
  maximumYearsExperience: 1,
  minimumScore: 65,
  workplaceTypes: ['remote', 'hybrid', 'onsite'],
};

const emptyFact = {
  fact_key: '',
  label: '',
  value: '',
  category: 'projects',
};

const join = (value: unknown) => (Array.isArray(value) ? value.join(', ') : '');
const split = (value: string) =>
  value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);

function profileToForm(profile?: SearchProfile): ProfileForm {
  if (!profile) return defaultProfile;
  const config = profile.config;
  const workplaceTypes = config.workplace_types;
  return {
    name: profile.name,
    desiredTitles: join(config.desired_titles),
    adjacentTitles: join(config.adjacent_titles),
    locations: join(config.locations),
    industries: join(config.industries),
    requiredSkills: join(config.required_skills),
    preferredSkills: join(config.preferred_skills),
    maximumYearsExperience: Number(config.maximum_years_experience ?? 1),
    minimumScore: Number(config.minimum_match_score ?? 65),
    workplaceTypes:
      workplaceTypes && workplaceTypes.length > 0 ? workplaceTypes : ['remote', 'hybrid', 'onsite'],
  };
}

export function CandidateFactsPage() {
  const [facts, setFacts] = useState<CandidateFact[]>([]);
  const [profile, setProfile] = useState<SearchProfile | undefined>();
  const [profileForm, setProfileForm] = useState<ProfileForm>(defaultProfile);
  const [factForm, setFactForm] = useState(emptyFact);
  const [editingFactId, setEditingFactId] = useState<string | null>(null);
  const [deletingFact, setDeletingFact] = useState<CandidateFact | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [savingProfile, setSavingProfile] = useState(false);
  const [savingFact, setSavingFact] = useState(false);
  const [importing, setImporting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [nextFacts, profiles] = await Promise.all([listCandidateFacts(), listProfiles()]);
      const primaryProfile = profiles.find((item) => item.is_active) ?? profiles[0];
      setFacts(nextFacts);
      setProfile(primaryProfile);
      setProfileForm(profileToForm(primaryProfile));
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not load your career profile.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => void load(), [load]);

  const readiness = useMemo(() => {
    const safeFacts = facts.filter((fact) => !fact.sensitive);
    return [
      { label: 'Target roles', complete: split(profileForm.desiredTitles).length > 0 },
      {
        label: 'Resume evidence',
        complete: safeFacts.some((fact) =>
          ['education', 'experience', 'projects', 'skills'].includes(fact.category)
        ),
      },
      {
        label: 'Writing direction',
        complete: safeFacts.some((fact) => fact.category === 'writing_preferences'),
      },
      {
        label: 'Application logistics',
        complete: safeFacts.some((fact) =>
          ['availability', 'work_authorization', 'location'].includes(fact.category)
        ),
      },
    ];
  }, [facts, profileForm.desiredTitles]);
  const readinessCount = readiness.filter((item) => item.complete).length;

  async function saveProfile(event: React.FormEvent) {
    event.preventDefault();
    setSavingProfile(true);
    setError(null);
    try {
      const currentConfig = profile?.config ?? ({} as SearchProfileConfig);
      const payload = {
        name: profileForm.name,
        is_active: true,
        config: {
          ...currentConfig,
          desired_titles: split(profileForm.desiredTitles),
          adjacent_titles: split(profileForm.adjacentTitles),
          locations: split(profileForm.locations),
          industries: split(profileForm.industries),
          required_skills: split(profileForm.requiredSkills),
          preferred_skills: split(profileForm.preferredSkills),
          workplace_types: profileForm.workplaceTypes,
          employment_types: ['internship'],
          seniority: ['intern', 'entry level'],
          minimum_years_experience: 0,
          maximum_years_experience: profileForm.maximumYearsExperience,
          daily_pack_limit: currentConfig.daily_pack_limit ?? 10,
          reserve_limit: currentConfig.reserve_limit ?? 10,
          minimum_match_score: profileForm.minimumScore,
          max_per_company: currentConfig.max_per_company ?? 2,
          timezone: currentConfig.timezone ?? 'Asia/Singapore',
        },
      };
      const saved = profile
        ? await updateProfile(profile.profile_id, payload)
        : await createProfile(payload);
      setProfile(saved);
      setProfileForm(profileToForm(saved));
      setNotice('Internship targeting saved. New opportunities will use these preferences.');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not save search preferences.');
    } finally {
      setSavingProfile(false);
    }
  }

  async function submitFact(event: React.FormEvent) {
    event.preventDefault();
    setSavingFact(true);
    setError(null);
    try {
      await saveCandidateFact({ ...factForm, sensitive: false });
      setFactForm(emptyFact);
      setEditingFactId(null);
      setNotice(editingFactId ? 'Evidence updated.' : 'Evidence added to your approved library.');
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not save this evidence.');
    } finally {
      setSavingFact(false);
    }
  }

  async function importEvidence() {
    setImporting(true);
    setError(null);
    try {
      const result = await importMasterResumeFacts();
      setNotice(
        result.imported === 0
          ? 'Your master resume did not contain importable evidence.'
          : `Imported ${result.imported} source-backed facts from your master resume.`
      );
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not import resume evidence.');
    } finally {
      setImporting(false);
    }
  }

  async function addWritingDefaults() {
    setSavingFact(true);
    try {
      await saveCandidateFact({ ...internshipWritingDefaults, sensitive: false });
      setNotice('Your internship writing preferences are now active.');
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not save writing preferences.');
    } finally {
      setSavingFact(false);
    }
  }

  function editFact(fact: CandidateFact) {
    setEditingFactId(fact.fact_id);
    setFactForm({
      fact_key: fact.fact_key,
      label: fact.label,
      value: fact.value,
      category: fact.category,
    });
    document.getElementById('evidence-editor')?.scrollIntoView({ behavior: 'smooth' });
  }

  async function confirmDelete() {
    if (!deletingFact) return;
    try {
      await deleteCandidateFact(deletingFact.fact_id);
      setNotice('Evidence removed. It will no longer be reused.');
      setDeletingFact(null);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not delete this evidence.');
    }
  }

  return (
    <main className="p-5 lg:p-8">
      <div className="flex flex-col justify-between gap-5 border-b-2 border-black pb-7 lg:flex-row lg:items-end">
        <div>
          <p className="font-mono text-xs font-bold uppercase tracking-widest text-blue-700">
            Your source of truth
          </p>
          <h1 className="mt-2 font-serif text-4xl font-black uppercase sm:text-6xl">
            My internship profile
          </h1>
          <p className="mt-3 max-w-3xl text-sm leading-6">
            Set the roles you want, import only supported resume evidence, and tell every writing
            tool how to represent you. Facts stay editable and sensitive screening answers are
            withheld automatically.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link
            href="/dashboard"
            className="inline-flex h-10 items-center justify-center border border-black bg-white px-4 font-mono text-sm font-medium uppercase tracking-wide shadow-sw-sm hover:translate-x-px hover:translate-y-px hover:shadow-none"
          >
            Edit master resume
          </Link>
          <Link
            href="/tailor"
            className="inline-flex h-10 items-center justify-center border border-black bg-blue-700 px-4 font-mono text-sm font-medium uppercase tracking-wide text-white shadow-sw-sm hover:translate-x-px hover:translate-y-px hover:bg-blue-800 hover:shadow-none"
          >
            Tailor to a role
          </Link>
        </div>
      </div>

      {(error || notice) && (
        <div
          role={error ? 'alert' : 'status'}
          className={`mt-5 border border-black p-3 text-sm ${error ? 'bg-orange-100' : 'bg-green-100'}`}
        >
          {error ?? notice}
        </div>
      )}

      <section className="mt-6 grid border border-black bg-black sm:grid-cols-2 xl:grid-cols-4">
        {readiness.map((item) => (
          <div
            key={item.label}
            className="flex items-center gap-3 border border-black bg-white p-4"
          >
            <span
              className={`grid h-7 w-7 place-items-center border border-black ${item.complete ? 'bg-green-700 text-white' : 'bg-[#f3f0e8]'}`}
            >
              {item.complete ? <Check className="h-4 w-4" /> : '-'}
            </span>
            <div>
              <p className="font-mono text-[9px] font-bold uppercase tracking-widest">
                {item.complete ? 'Ready' : 'Needs input'}
              </p>
              <p className="font-serif font-bold uppercase">{item.label}</p>
            </div>
          </div>
        ))}
      </section>
      <p className="mt-2 text-right font-mono text-[10px] uppercase text-neutral-600">
        Profile readiness {readinessCount} / {readiness.length}
      </p>

      <div className="mt-8 grid gap-7 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <form onSubmit={saveProfile} className="h-fit border border-black bg-white shadow-sw-md">
          <div className="border-b border-black bg-blue-700 p-5 text-white">
            <p className="font-mono text-[9px] uppercase tracking-widest">Internship targeting</p>
            <h2 className="font-serif text-2xl font-black uppercase">What should we look for?</h2>
          </div>
          <div className="grid gap-4 p-5 sm:grid-cols-2">
            <ProfileField
              label="Profile name"
              value={profileForm.name}
              onChange={(name) => setProfileForm({ ...profileForm, name })}
              className="sm:col-span-2"
            />
            <ProfileField
              label="Target internship titles"
              hint="Comma separated"
              value={profileForm.desiredTitles}
              onChange={(desiredTitles) => setProfileForm({ ...profileForm, desiredTitles })}
              className="sm:col-span-2"
            />
            <ProfileField
              label="Adjacent titles"
              hint="Useful alternatives"
              value={profileForm.adjacentTitles}
              onChange={(adjacentTitles) => setProfileForm({ ...profileForm, adjacentTitles })}
              className="sm:col-span-2"
            />
            <ProfileField
              label="Locations"
              value={profileForm.locations}
              onChange={(locations) => setProfileForm({ ...profileForm, locations })}
            />
            <ProfileField
              label="Industries"
              value={profileForm.industries}
              onChange={(industries) => setProfileForm({ ...profileForm, industries })}
            />
            <ProfileField
              label="Core target skills"
              value={profileForm.requiredSkills}
              onChange={(requiredSkills) => setProfileForm({ ...profileForm, requiredSkills })}
            />
            <ProfileField
              label="Preferred target skills"
              value={profileForm.preferredSkills}
              onChange={(preferredSkills) => setProfileForm({ ...profileForm, preferredSkills })}
            />
            <label className="font-mono text-[10px] font-bold uppercase">
              Maximum experience requested / {profileForm.maximumYearsExperience} year
              <input
                type="range"
                min="0"
                max="3"
                value={profileForm.maximumYearsExperience}
                onChange={(event) =>
                  setProfileForm({
                    ...profileForm,
                    maximumYearsExperience: Number(event.target.value),
                  })
                }
                className="mt-3 w-full accent-blue-700"
              />
            </label>
            <label className="font-mono text-[10px] font-bold uppercase">
              Minimum match score / {profileForm.minimumScore}
              <input
                type="range"
                min="50"
                max="90"
                value={profileForm.minimumScore}
                onChange={(event) =>
                  setProfileForm({ ...profileForm, minimumScore: Number(event.target.value) })
                }
                className="mt-3 w-full accent-blue-700"
              />
            </label>
            <fieldset className="sm:col-span-2">
              <legend className="font-mono text-[10px] font-bold uppercase">Workplace types</legend>
              <div className="mt-2 flex flex-wrap gap-2">
                {(['remote', 'hybrid', 'onsite'] as const).map((type) => {
                  const selected = profileForm.workplaceTypes.includes(type);
                  return (
                    <button
                      key={type}
                      type="button"
                      aria-pressed={selected}
                      onClick={() =>
                        setProfileForm({
                          ...profileForm,
                          workplaceTypes: selected
                            ? profileForm.workplaceTypes.filter((item) => item !== type)
                            : [...profileForm.workplaceTypes, type],
                        })
                      }
                      className={`border border-black px-3 py-2 font-mono text-[10px] font-bold uppercase ${selected ? 'bg-black text-white' : 'bg-white'}`}
                    >
                      {type}
                    </button>
                  );
                })}
              </div>
            </fieldset>
          </div>
          <div className="flex justify-end border-t border-black p-4">
            <Button type="submit" disabled={savingProfile}>
              <Save className="h-4 w-4" /> {savingProfile ? 'Saving...' : 'Save targeting'}
            </Button>
          </div>
        </form>

        <section className="min-w-0 space-y-5">
          <div className="border border-black bg-[#f3f0e8] p-5 shadow-sw-md">
            <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
              <div>
                <p className="font-mono text-[9px] font-bold uppercase tracking-widest text-blue-700">
                  Fast setup
                </p>
                <h2 className="font-serif text-2xl font-black uppercase">
                  Build my evidence library
                </h2>
                <p className="mt-1 max-w-xl text-sm">
                  Import education, experience, projects, skills, awards, and credentials from the
                  processed master resume. Contact details are never imported here.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" onClick={addWritingDefaults} disabled={savingFact}>
                  <Check className="h-4 w-4" /> Use my writing defaults
                </Button>
                <Button onClick={importEvidence} disabled={importing}>
                  <FileUp className="h-4 w-4" /> {importing ? 'Importing...' : 'Import master'}
                </Button>
              </div>
            </div>
          </div>

          <form
            id="evidence-editor"
            onSubmit={submitFact}
            className="border border-black bg-white shadow-sw-md"
          >
            <div className="flex items-center justify-between border-b border-black bg-black p-4 text-white">
              <h2 className="font-serif text-xl font-black uppercase">
                {editingFactId ? 'Edit approved evidence' : 'Add approved evidence'}
              </h2>
              {editingFactId && (
                <button
                  type="button"
                  aria-label="Cancel editing"
                  onClick={() => {
                    setEditingFactId(null);
                    setFactForm(emptyFact);
                  }}
                >
                  <X className="h-5 w-5" />
                </button>
              )}
            </div>
            <div className="grid gap-4 p-5 sm:grid-cols-2">
              <FactField
                label="Stable key"
                value={factForm.fact_key}
                disabled={Boolean(editingFactId)}
                onChange={(fact_key) =>
                  setFactForm({
                    ...factForm,
                    fact_key: fact_key.toLowerCase().replace(/[^a-z0-9_]/g, '_'),
                  })
                }
              />
              <FactField
                label="Evidence label"
                value={factForm.label}
                onChange={(label) => setFactForm({ ...factForm, label })}
              />
              <label className="font-mono text-[10px] font-bold uppercase">
                Category
                <select
                  value={factForm.category}
                  onChange={(event) => setFactForm({ ...factForm, category: event.target.value })}
                  className="mt-1 h-11 w-full border border-black bg-white px-3 text-sm normal-case"
                >
                  {categories.map((category) => (
                    <option key={category}>{category}</option>
                  ))}
                </select>
              </label>
              <label className="font-mono text-[10px] font-bold uppercase sm:col-span-2">
                Exact supported fact or preference
                <textarea
                  required
                  value={factForm.value}
                  onChange={(event) => setFactForm({ ...factForm, value: event.target.value })}
                  className="mt-1 min-h-28 w-full border border-black bg-white p-3 font-sans text-sm normal-case"
                  placeholder="Write only what you can support. Include scope, ownership, tools, and results when known."
                />
              </label>
            </div>
            <div className="flex justify-end border-t border-black p-4">
              <Button type="submit" disabled={savingFact}>
                {editingFactId ? <Save className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
                {savingFact ? 'Saving...' : editingFactId ? 'Update evidence' : 'Add evidence'}
              </Button>
            </div>
          </form>

          <div className="border border-black bg-white">
            <div className="flex items-center justify-between border-b border-black p-4">
              <span className="font-mono text-xs font-black uppercase">
                Approved evidence / {facts.filter((fact) => !fact.sensitive).length}
              </span>
              <span className="font-mono text-[9px] uppercase text-neutral-500">
                {loading ? 'Loading...' : `${facts.length} total`}
              </span>
            </div>
            {!loading && facts.length === 0 ? (
              <div className="p-8 text-center">
                <p className="font-serif text-xl font-bold uppercase">No evidence yet</p>
                <p className="mt-2 text-sm text-neutral-600">
                  Import your master resume or add your first supported project, leadership, or
                  application fact above.
                </p>
              </div>
            ) : (
              facts.map((fact) => (
                <article key={fact.fact_id} className="border-b border-black p-4 last:border-b-0">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <b className="font-serif uppercase">{fact.label}</b>
                      <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-6">
                        {fact.value}
                      </p>
                    </div>
                    <div className="flex shrink-0 gap-1">
                      <button
                        type="button"
                        aria-label={`Edit ${fact.label}`}
                        onClick={() => editFact(fact)}
                        className="grid h-9 w-9 place-items-center border border-black hover:bg-blue-700 hover:text-white"
                      >
                        <Pencil className="h-4 w-4" />
                      </button>
                      <button
                        type="button"
                        aria-label={`Delete ${fact.label}`}
                        onClick={() => setDeletingFact(fact)}
                        className="grid h-9 w-9 place-items-center border border-black hover:bg-red-700 hover:text-white"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <span
                      className={`border border-black px-2 py-1 font-mono text-[9px] uppercase ${fact.sensitive ? 'bg-orange-100' : 'bg-green-700 text-white'}`}
                    >
                      {fact.sensitive ? 'Withheld' : fact.category.replaceAll('_', ' ')}
                    </span>
                    <span className="font-mono text-[9px] text-neutral-500">{fact.fact_key}</span>
                  </div>
                </article>
              ))
            )}
          </div>
        </section>
      </div>

      <ConfirmDialog
        open={Boolean(deletingFact)}
        onOpenChange={(open) => !open && setDeletingFact(null)}
        title="Remove approved evidence?"
        description="This fact will stop appearing in future application packs. Existing resumes and letters are not changed."
        confirmLabel="Remove evidence"
        cancelLabel="Keep it"
        variant="danger"
        onConfirm={confirmDelete}
      />
    </main>
  );
}

function ProfileField({
  label,
  hint,
  value,
  onChange,
  className = '',
}: {
  label: string;
  hint?: string;
  value: string;
  onChange: (value: string) => void;
  className?: string;
}) {
  return (
    <label className={`font-mono text-[10px] font-bold uppercase ${className}`}>
      {label} {hint && <span className="font-normal text-neutral-500">/ {hint}</span>}
      <input
        required
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1 h-11 w-full border border-black bg-white px-3 font-sans text-sm normal-case"
      />
    </label>
  );
}

function FactField({
  label,
  value,
  onChange,
  disabled = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  return (
    <label className="font-mono text-[10px] font-bold uppercase">
      {label}
      <input
        required
        disabled={disabled}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1 h-11 w-full border border-black bg-white px-3 font-sans text-sm normal-case disabled:bg-neutral-100 disabled:text-neutral-500"
      />
    </label>
  );
}
