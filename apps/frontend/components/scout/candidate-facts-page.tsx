'use client';

import { useCallback, useEffect, useState } from 'react';
import { Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { listCandidateFacts, saveCandidateFact, type CandidateFact } from '@/lib/api/scout';

const categories = [
  'work_authorization',
  'availability',
  'location',
  'links',
  'compensation',
  'screening',
];

export function CandidateFactsPage() {
  const [facts, setFacts] = useState<CandidateFact[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    fact_key: 'work_authorization',
    label: 'Work authorization',
    value: '',
    category: 'work_authorization',
  });
  const load = useCallback(
    () =>
      listCandidateFacts()
        .then(setFacts)
        .catch((reason: Error) => setError(reason.message)),
    []
  );
  useEffect(() => void load(), [load]);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    try {
      await saveCandidateFact({ ...form, sensitive: false });
      setForm({ ...form, value: '' });
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not save this fact.');
    }
  }
  return (
    <main className="p-5 lg:p-8">
      <p className="font-mono text-xs font-bold uppercase tracking-widest text-blue-700">
        Approved answer library
      </p>
      <h1 className="mt-2 font-serif text-5xl font-black uppercase">Candidate facts</h1>
      <p className="mt-3 max-w-3xl text-sm">
        Only explicit facts here can be reused in application answers. Demographic, disability,
        veteran, criminal-history, and legal-attestation questions are always withheld.
      </p>
      {error && (
        <p role="alert" className="mt-5 border border-black bg-orange-100 p-3 text-sm">
          {error}
        </p>
      )}
      <div className="mt-8 grid gap-6 xl:grid-cols-[420px_1fr]">
        <form onSubmit={submit} className="h-fit border border-black bg-white shadow-sw-md">
          <div className="border-b border-black bg-black p-4 text-white">
            <h2 className="font-serif text-2xl font-black uppercase">Add factual answer</h2>
          </div>
          <div className="grid gap-4 p-5">
            <FactField
              label="Key"
              value={form.fact_key}
              onChange={(fact_key) =>
                setForm({ ...form, fact_key: fact_key.toLowerCase().replace(/[^a-z0-9_]/g, '_') })
              }
            />
            <FactField
              label="Question label"
              value={form.label}
              onChange={(label) => setForm({ ...form, label })}
            />
            <label className="font-mono text-[10px] font-bold uppercase">
              Category
              <select
                value={form.category}
                onChange={(event) => setForm({ ...form, category: event.target.value })}
                className="mt-1 h-10 w-full border border-black bg-white px-3 text-sm normal-case"
              >
                {categories.map((category) => (
                  <option key={category}>{category}</option>
                ))}
              </select>
            </label>
            <label className="font-mono text-[10px] font-bold uppercase">
              Answer
              <textarea
                required
                value={form.value}
                onChange={(event) => setForm({ ...form, value: event.target.value })}
                className="mt-1 min-h-28 w-full border border-black bg-white p-3 font-sans text-sm normal-case"
              />
            </label>
            <Button type="submit">
              <Plus /> Save fact
            </Button>
          </div>
        </form>
        <section className="border border-black bg-white">
          <div className="border-b border-black p-4 font-mono text-xs font-black uppercase">
            Reusable answers / {facts.filter((fact) => !fact.sensitive).length}
          </div>
          {facts.length === 0 ? (
            <p className="p-8 text-center text-sm text-neutral-600">No approved facts yet.</p>
          ) : (
            facts.map((fact) => (
              <article key={fact.fact_id} className="border-b border-black p-4">
                <div className="flex justify-between gap-3">
                  <b className="font-serif uppercase">{fact.label}</b>
                  <span
                    className={`border border-black px-2 py-1 font-mono text-[9px] uppercase ${fact.sensitive ? 'bg-orange-100' : 'bg-green-700 text-white'}`}
                  >
                    {fact.sensitive ? 'Withheld' : fact.category}
                  </span>
                </div>
                <p className="mt-2 whitespace-pre-wrap text-sm">{fact.value}</p>
              </article>
            ))
          )}
        </section>
      </div>
    </main>
  );
}

function FactField({
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
