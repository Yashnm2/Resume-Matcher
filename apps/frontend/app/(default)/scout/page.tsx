import { ScoutShell } from '@/components/scout/scout-shell';
import { ScoutWorkspace } from '@/components/scout/scout-workspace';
import { listOpportunities, listProfiles, listToday } from '@/lib/api/scout';

export const dynamic = 'force-dynamic';

export default async function ScoutPage() {
  const [todayResult, opportunitiesResult, profilesResult] = await Promise.allSettled([
    listToday(),
    listOpportunities(),
    listProfiles(),
  ]);
  const today = todayResult.status === 'fulfilled' ? todayResult.value : [];
  const opportunities = opportunitiesResult.status === 'fulfilled' ? opportunitiesResult.value : [];
  const profiles = profilesResult.status === 'fulfilled' ? profilesResult.value : [];
  return (
    <ScoutShell active="/scout">
      <ScoutWorkspace
        initialJobs={today.length ? today : opportunities}
        initialProfiles={profiles}
      />
    </ScoutShell>
  );
}
