import { CandidateFactsPage } from '@/components/scout/candidate-facts-page';
import { ScoutShell } from '@/components/scout/scout-shell';

export default function CandidateFactsRoute() {
  return (
    <ScoutShell active="/candidate-facts">
      <CandidateFactsPage />
    </ScoutShell>
  );
}
