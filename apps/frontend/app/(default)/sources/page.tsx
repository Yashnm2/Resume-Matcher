import { ScoutShell } from '@/components/scout/scout-shell';
import { SourcesPage } from '@/components/scout/sources-page';
export default function Page() {
  return (
    <ScoutShell active="/sources">
      <SourcesPage />
    </ScoutShell>
  );
}
