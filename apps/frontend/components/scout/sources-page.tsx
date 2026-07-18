'use client';

import { useCallback, useEffect, useState } from 'react';
import { Activity, Plus, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { createSource, listSources, scanSource, type JobSource } from '@/lib/api/scout';

export function SourcesPage() {
  const [sources, setSources] = useState<JobSource[]>([]);
  const [form, setForm] = useState({
    name: '',
    company: '',
    source_type: 'greenhouse',
    endpoint: '',
    render_javascript: false,
  });
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(
    () =>
      listSources()
        .then(setSources)
        .catch((reason: Error) => setError(reason.message)),
    []
  );
  useEffect(() => {
    void load();
  }, [load]);
  async function add(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const adapterKeys: Record<string, string> = {
        greenhouse: 'board_token',
        lever: 'site',
        ashby: 'board_name',
        smartrecruiters: 'company_id',
      };
      const config =
        form.source_type === 'careers_page'
          ? {
              url: form.endpoint,
              company: form.company,
              render_javascript: form.render_javascript,
              max_pages: 40,
              browser_max_pages: 5,
            }
          : {
              [adapterKeys[form.source_type]]: form.endpoint,
              company: form.company,
            };
      await createSource({
        name: form.name,
        source_type: form.source_type,
        config,
        enabled: true,
      });
      setForm({ ...form, name: '', company: '', endpoint: '' });
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not add source.');
    }
  }
  async function scan(id: string) {
    try {
      await scanSource(id);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Scan failed.');
    }
  }
  return (
    <main className="p-5 lg:p-8">
      <p className="font-mono text-xs font-bold uppercase tracking-widest text-blue-700">
        Discovery control
      </p>
      <h1 className="mt-2 font-serif text-5xl font-black uppercase">Job sources</h1>
      <p className="mt-3 max-w-2xl text-sm">
        Public ATS feeds and company career pages only. Crawls respect robots.txt, never
        authenticate, and expose failures here.
      </p>
      {error && (
        <div className="mt-5 border border-black bg-orange-100 p-3 font-mono text-xs">{error}</div>
      )}
      <div className="mt-8 grid gap-6 xl:grid-cols-[420px_1fr]">
        <form onSubmit={add} className="h-fit border border-black bg-white shadow-sw-md">
          <div className="border-b border-black bg-black p-4 text-white">
            <h2 className="font-serif text-2xl font-black uppercase">Add source</h2>
          </div>
          <div className="grid gap-4 p-5">
            <Field
              label="Source name"
              value={form.name}
              onChange={(name) => setForm({ ...form, name })}
            />
            <Field
              label="Company name"
              value={form.company}
              onChange={(company) => setForm({ ...form, company })}
            />
            <label className="font-mono text-[10px] font-bold uppercase">
              Adapter
              <select
                value={form.source_type}
                onChange={(e) => setForm({ ...form, source_type: e.target.value })}
                className="mt-1 h-10 w-full border border-black bg-white px-3 text-sm normal-case"
              >
                <option value="greenhouse">Greenhouse</option>
                <option value="lever">Lever</option>
                <option value="ashby">Ashby</option>
                <option value="smartrecruiters">SmartRecruiters</option>
                <option value="careers_page">Career website</option>
              </select>
            </label>
            <Field
              label={form.source_type === 'careers_page' ? 'Public URL' : 'Board / company token'}
              value={form.endpoint}
              onChange={(endpoint) => setForm({ ...form, endpoint })}
            />
            {form.source_type === 'careers_page' && (
              <label className="flex items-start gap-3 border border-black bg-blue-50 p-3 text-xs">
                <input
                  type="checkbox"
                  checked={form.render_javascript}
                  onChange={(event) =>
                    setForm({ ...form, render_javascript: event.target.checked })
                  }
                  className="mt-0.5 accent-blue-700"
                />
                <span>
                  <b className="block font-mono text-[10px] uppercase">JavaScript fallback</b>
                  Use headless Chromium only if sitemap and static JSON-LD discovery find no jobs.
                </span>
              </label>
            )}
            <Button type="submit">
              <Plus /> Add source
            </Button>
          </div>
        </form>
        <section className="border border-black bg-white">
          <div className="flex justify-between border-b border-black p-4">
            <h2 className="font-mono text-xs font-black uppercase">Connected / {sources.length}</h2>
            <Activity className="size-4" />
          </div>
          {sources.length === 0 ? (
            <p className="p-8 text-center text-sm text-neutral-600">No sources configured yet.</p>
          ) : (
            sources.map((source) => (
              <article
                key={source.source_id}
                className="grid gap-3 border-b border-black p-4 md:grid-cols-[1fr_auto_auto] md:items-center"
              >
                <div>
                  <h3 className="font-serif text-xl font-black uppercase">{source.name}</h3>
                  <p className="font-mono text-[10px] uppercase">
                    {source.source_type} · Last scan{' '}
                    {source.last_scan_at ? new Date(source.last_scan_at).toLocaleString() : 'never'}
                  </p>
                  {source.last_error && (
                    <p className="mt-2 text-xs text-red-700">{source.last_error}</p>
                  )}
                </div>
                <span
                  className={`border border-black px-2 py-1 font-mono text-[10px] font-bold uppercase ${source.status === 'healthy' ? 'bg-green-700 text-white' : 'bg-neutral-200'}`}
                >
                  {source.status}
                </span>
                <Button size="sm" variant="outline" onClick={() => void scan(source.source_id)}>
                  <RefreshCw /> Scan
                </Button>
              </article>
            ))
          )}
        </section>
      </div>
    </main>
  );
}

function Field({
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
