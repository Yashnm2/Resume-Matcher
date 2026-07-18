import Link from 'next/link';
import type { ReactNode } from 'react';
import { SignOutButton } from '@/components/auth/sign-out-button';

const links = [
  ['Dashboard', '/dashboard'],
  ["Today's 20", '/scout'],
  ['Scout', '/scout-control'],
  ['Application Tracker', '/tracker'],
  ['Contacts', '/contacts'],
  ['Sources', '/sources'],
  ['Candidate facts', '/candidate-facts'],
  ['Settings', '/settings'],
] as const;

export function ScoutShell({ children, active }: { children: ReactNode; active: string }) {
  return (
    <div className="min-h-screen bg-[#f3f0e8] text-black">
      <header className="sticky top-0 z-40 border-b border-black bg-[#f3f0e8]">
        <div className="flex min-h-16 items-stretch">
          <Link
            href="/"
            className="flex items-center border-r border-black px-5 font-serif text-xl font-black uppercase tracking-tight"
          >
            RM<span className="text-blue-700">/Scout</span>
          </Link>
          <nav aria-label="Primary" className="flex min-w-0 flex-1 overflow-x-auto">
            {links.map(([label, href]) => (
              <Link
                key={href}
                href={href}
                className={`flex shrink-0 items-center border-r border-black px-4 font-mono text-[11px] font-bold uppercase tracking-[0.12em] hover:bg-blue-700 hover:text-white ${active === href ? 'bg-black text-white' : ''}`}
              >
                {label}
              </Link>
            ))}
          </nav>
          <div className="hidden items-center px-4 font-mono text-[10px] uppercase tracking-widest lg:flex">
            Remote / Asia–Singapore
          </div>
          <SignOutButton />
        </div>
      </header>
      {children}
    </div>
  );
}
