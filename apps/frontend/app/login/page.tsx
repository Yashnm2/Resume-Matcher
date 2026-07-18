'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { getSupabaseBrowserClient } from '@/lib/supabase/client';

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const supabase = getSupabaseBrowserClient();
    if (!supabase) {
      setError('Supabase is not configured for this deployment.');
      return;
    }
    setBusy(true);
    setError(null);
    const result = await supabase.auth.signInWithPassword({ email, password });
    setBusy(false);
    if (result.error) {
      setError(result.error.message);
      return;
    }
    router.replace('/scout');
    router.refresh();
  }

  return (
    <main className="grid min-h-screen place-items-center bg-[#f3f0e8] bg-[linear-gradient(to_right,rgba(0,0,0,.08)_1px,transparent_1px),linear-gradient(to_bottom,rgba(0,0,0,.08)_1px,transparent_1px)] bg-[size:24px_24px] p-5">
      <form
        onSubmit={submit}
        className="w-full max-w-md border border-black bg-[#f3f0e8] shadow-[8px_8px_0_#000]"
      >
        <div className="border-b border-black bg-blue-700 p-6 text-white">
          <p className="font-mono text-[10px] font-bold uppercase tracking-widest">
            Private workspace
          </p>
          <h1 className="mt-2 font-serif text-4xl font-black uppercase">Resume Matcher</h1>
        </div>
        <div className="grid gap-4 p-6">
          <label className="font-mono text-[10px] font-bold uppercase">
            Email
            <input
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="mt-1 h-11 w-full border border-black bg-white px-3 font-sans text-sm normal-case"
            />
          </label>
          <label className="font-mono text-[10px] font-bold uppercase">
            Password
            <input
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="mt-1 h-11 w-full border border-black bg-white px-3 font-sans text-sm normal-case"
            />
          </label>
          {error && (
            <p role="alert" className="border border-black bg-orange-100 p-3 text-sm">
              {error}
            </p>
          )}
          <Button type="submit" disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in'}
          </Button>
        </div>
      </form>
    </main>
  );
}
