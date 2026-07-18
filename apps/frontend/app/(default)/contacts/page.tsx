import { ScoutShell } from '@/components/scout/scout-shell';
import { ContactsPage } from '@/components/scout/contacts-page';
export default function Page() {
  return (
    <ScoutShell active="/contacts">
      <ContactsPage />
    </ScoutShell>
  );
}
