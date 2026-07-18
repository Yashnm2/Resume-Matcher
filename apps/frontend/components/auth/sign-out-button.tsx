'use client';

import { useRouter } from 'next/navigation';
import { getSupabaseBrowserClient } from '@/lib/supabase/client';

export function SignOutButton() {
  const router = useRouter();
  const supabase = getSupabaseBrowserClient();
  if (!supabase) return null;
  return (
    <button
      onClick={async () => {
        await supabase.auth.signOut();
        router.replace('/login');
        router.refresh();
      }}
      className="hidden items-center border-l border-black px-4 font-mono text-[10px] font-bold uppercase hover:bg-black hover:text-white lg:flex"
    >
      Sign out
    </button>
  );
}
