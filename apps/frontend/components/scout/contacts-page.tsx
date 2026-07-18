'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Upload, UserRound } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { importConnections, listContacts, type Contact } from '@/lib/api/scout';

export function ContactsPage() {
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const load = useCallback(() => listContacts().then(setContacts), []);
  useEffect(() => {
    void load();
  }, [load]);
  async function upload(file?: File) {
    if (!file) return;
    try {
      const result = await importConnections(file);
      setMessage(`Imported ${result.imported}; updated ${result.updated}.`);
      await load();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : 'Import failed.');
    }
  }
  return (
    <main className="p-5 lg:p-8">
      <div className="flex flex-wrap items-end justify-between gap-5">
        <div>
          <p className="font-mono text-xs font-bold uppercase tracking-widest text-blue-700">
            Referral network
          </p>
          <h1 className="mt-2 font-serif text-5xl font-black uppercase">Contacts</h1>
          <p className="mt-3 max-w-2xl text-sm">
            Import LinkedIn’s official Connections.csv. Resume Matcher never logs in, scrapes
            profiles, guesses email addresses, or sends messages.
          </p>
        </div>
        <input
          ref={input}
          type="file"
          accept=".csv,text/csv"
          className="hidden"
          onChange={(event) => void upload(event.target.files?.[0])}
        />
        <Button onClick={() => input.current?.click()}>
          <Upload /> Import Connections.csv
        </Button>
      </div>
      {message && (
        <div className="mt-5 border border-black bg-blue-50 p-3 font-mono text-xs">{message}</div>
      )}
      <section className="mt-8 border border-black bg-white shadow-sw-md">
        <div className="grid grid-cols-[1fr_auto] border-b border-black bg-black p-4 text-white">
          <h2 className="font-mono text-xs font-black uppercase">First-degree directory</h2>
          <span className="font-mono text-xs">{contacts.length}</span>
        </div>
        {contacts.length === 0 ? (
          <div className="grid min-h-72 place-items-center p-8 text-center">
            <div>
              <UserRound className="mx-auto mb-4 size-10 text-blue-700" />
              <h3 className="font-serif text-2xl font-black uppercase">No connections imported</h3>
              <p className="mt-2 text-sm text-neutral-600">
                Your notes and referral history are preserved across repeated exports.
              </p>
            </div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left">
              <thead className="font-mono text-[10px] uppercase">
                <tr>
                  <th className="border-b border-r border-black p-3">Name</th>
                  <th className="border-b border-r border-black p-3">Company</th>
                  <th className="border-b border-r border-black p-3">Title</th>
                  <th className="border-b border-black p-3">Reach</th>
                </tr>
              </thead>
              <tbody>
                {contacts.map((contact) => (
                  <tr key={contact.contact_id}>
                    <td className="border-b border-r border-black p-3 font-bold">
                      {contact.first_name} {contact.last_name}
                    </td>
                    <td className="border-b border-r border-black p-3 text-sm">
                      {contact.company || '—'}
                    </td>
                    <td className="border-b border-r border-black p-3 text-sm">
                      {contact.position || '—'}
                    </td>
                    <td className="border-b border-black p-3 font-mono text-[10px] uppercase">
                      {contact.email
                        ? 'Email available'
                        : contact.profile_url
                          ? 'LinkedIn message'
                          : 'No route'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
