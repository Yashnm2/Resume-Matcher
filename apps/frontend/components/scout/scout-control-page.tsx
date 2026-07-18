'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { listScoutRuns, listSources, type JobSource, type ScoutRun } from '@/lib/api/scout';

export function ScoutControlPage() {
  const [runs, setRuns] = useState<ScoutRun[]>([]);
  const [sources, setSources] = useState<JobSource[]>([]);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    try {
      const [nextRuns, nextSources] = await Promise.all([listScoutRuns(), listSources()]);
      setRuns(nextRuns);
      setSources(nextSources);
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Scout history is unavailable.');
    }
  }, []);
  useEffect(() => void load(), [load]);
  const healthy = sources.filter((source) => source.status === 'healthy').length;
  const discovered = runs.reduce((sum, run) => sum + run.discovered_count, 0);

  return (
    <main className="p-5 lg:p-8">
      <div className="flex flex-wrap items-end justify-between gap-5">
        <div>
          <p className="font-mono text-xs font-bold uppercase tracking-widest text-blue-700">
            Scheduled discovery
          </p>
          <h1 className="mt-2 font-serif text-5xl font-black uppercase">Scout</h1>
          <p className="mt-3 max-w-2xl text-sm">
            Runs every four hours. Each source fails independently and keeps a visible history.
          </p>
        </div>
        <div className="flex gap-3">
          <Link href="/sources">
            <Button variant="outline">Manage sources</Button>
          </Link>
          <Button onClick={() => void load()}>
            <RefreshCw /> Refresh
          </Button>
        </div>
      </div>
      {error && (
        <p role="alert" className="mt-5 border border-black bg-orange-100 p-3 text-sm">
          {error}
        </p>
      )}
      <section className="mt-8 grid border border-black bg-white shadow-sw-md sm:grid-cols-3">
        <Metric label="Configured sources" value={sources.length} />
        <Metric label="Healthy sources" value={healthy} />
        <Metric label="Postings observed" value={discovered} />
      </section>
      <section className="mt-6 border border-black bg-white">
        <div className="border-b border-black bg-black p-4 text-white">
          <h2 className="font-mono text-xs font-black uppercase">Run history</h2>
        </div>
        {runs.length === 0 ? (
          <p className="p-8 text-center text-sm text-neutral-600">No scans have run yet.</p>
        ) : (
          runs.map((run) => (
            <article
              key={run.run_id}
              className="grid gap-2 border-b border-black p-4 md:grid-cols-[1fr_auto_auto_auto] md:items-center"
            >
              <div>
                <b className="font-serif uppercase">{run.source_id}</b>
                <p className="font-mono text-[9px] uppercase">
                  {new Date(run.started_at).toLocaleString()}
                </p>
              </div>
              <span className="font-mono text-[10px] uppercase">{run.discovered_count} found</span>
              <span className="font-mono text-[10px] uppercase">{run.created_count} new</span>
              <span
                className={`border border-black px-2 py-1 font-mono text-[10px] font-bold uppercase ${run.status === 'completed' ? 'bg-green-700 text-white' : run.status === 'failed' ? 'bg-orange-100' : ''}`}
              >
                {run.status}
              </span>
              {run.error && <p className="text-xs text-red-700 md:col-span-4">{run.error}</p>}
            </article>
          ))
        )}
      </section>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="border-b border-r border-black p-5 sm:border-b-0">
      <span className="font-mono text-[10px] uppercase">{label}</span>
      <b className="mt-1 block font-serif text-4xl">{value}</b>
    </div>
  );
}
