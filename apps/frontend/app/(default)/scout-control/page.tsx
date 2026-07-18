import { ScoutControlPage } from '@/components/scout/scout-control-page';
import { ScoutShell } from '@/components/scout/scout-shell';

export default function ScoutControlRoute() {
  return (
    <ScoutShell active="/scout-control">
      <ScoutControlPage />
    </ScoutShell>
  );
}
