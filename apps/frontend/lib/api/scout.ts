import { apiDelete, apiFetch, apiPatch, apiPost } from './client';

export interface SearchProfileConfig {
  desired_titles?: string[];
  adjacent_titles?: string[];
  locations?: string[];
  workplace_types?: Array<'remote' | 'hybrid' | 'onsite'>;
  seniority?: string[];
  minimum_years_experience?: number | null;
  maximum_years_experience?: number | null;
  required_skills?: string[];
  preferred_skills?: string[];
  excluded_terms?: string[];
  preferred_companies?: string[];
  industries?: string[];
  employment_types?: string[];
  daily_pack_limit: number;
  reserve_limit?: number;
  minimum_match_score: number;
  max_per_company?: number;
  timezone?: string;
  [key: string]: unknown;
}

export interface SearchProfile {
  profile_id: string;
  name: string;
  config: SearchProfileConfig;
  is_active: boolean;
}

export interface JobPosting {
  posting_id: string;
  title: string;
  company: string;
  location: string | null;
  workplace_type: string | null;
  description: string;
  source_url: string | null;
  source_type: string;
  published_at: string | null;
}

export interface Opportunity {
  match_id: string;
  profile_id: string;
  posting: JobPosting;
  eligible: boolean;
  score: number;
  score_components: Record<string, number>;
  gaps: string[];
  explanation: string;
  state: string;
  selected_date: string | null;
  daily_rank: number | null;
  pack_status: string | null;
  referral_count: number;
}

export interface ArtifactPack {
  pack_id: string;
  match_id: string;
  resume_id: string | null;
  cover_letter: string | null;
  outreach_message: string | null;
  referral_subject: string | null;
  referral_email: string | null;
  linkedin_message: string | null;
  interview_prep: Record<string, unknown> | null;
  application_answers: Record<string, string>;
  provenance: Record<string, unknown>;
  llm_usage: {
    calls?: number;
    prompt_tokens?: number;
    completion_tokens?: number;
    cost_usd?: number;
  };
  status: string;
  error: string | null;
}

export interface JobSource {
  source_id: string;
  name: string;
  source_type: string;
  config: Record<string, unknown>;
  enabled: boolean;
  status: string;
  last_scan_at: string | null;
  last_error: string | null;
}

export interface ScoutRun {
  run_id: string;
  source_id: string;
  status: string;
  discovered_count: number;
  created_count: number;
  error: string | null;
  started_at: string;
  finished_at: string | null;
}

export interface CandidateFact {
  fact_id: string;
  fact_key: string;
  label: string;
  value: string;
  category: string;
  sensitive: boolean;
}

export interface Contact {
  contact_id: string;
  first_name: string;
  last_name: string;
  company: string | null;
  position: string | null;
  profile_url: string | null;
  email: string | null;
}

export interface ReferralMatch {
  referral_match_id: string;
  contact: Contact;
  score: number;
  explanation: string;
  contacted_at: string | null;
  response_notes: string | null;
}

async function json<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(
      typeof payload.detail === 'string' ? payload.detail : `Request failed (${response.status})`
    );
  }
  return response.json() as Promise<T>;
}

export const listProfiles = () => apiFetch('/search-profiles').then(json<SearchProfile[]>);
export const createProfile = (payload: Record<string, unknown>) =>
  apiPost('/search-profiles', payload).then(json<SearchProfile>);
export const updateProfile = (id: string, payload: Record<string, unknown>) =>
  apiPatch(`/search-profiles/${id}`, payload).then(json<SearchProfile>);
export const listOpportunities = () => apiFetch('/opportunities').then(json<Opportunity[]>);
export const listToday = () => apiFetch('/opportunities/today').then(json<Opportunity[]>);
export const getPack = (id: string) =>
  apiFetch(`/opportunities/${id}/pack`).then(json<ArtifactPack>);
export const updatePack = (id: string, payload: Record<string, string>) =>
  apiPatch(`/opportunities/${id}/pack`, payload).then(json<ArtifactPack>);
export const preparePack = (id: string, regenerate = false) =>
  apiPost(`/opportunities/${id}/prepare`, {
    force: regenerate,
    regeneration_key: regenerate ? crypto.randomUUID() : null,
  }).then(json<ArtifactPack>);
export const updateOpportunity = (id: string, state: string) =>
  apiPatch(`/opportunities/${id}`, { state }).then(json<Record<string, unknown>>);
export const replaceOpportunity = (id: string) =>
  apiPost(`/opportunities/${id}/replace`, {}).then(json<Record<string, unknown>>);
export const selectToday = (profileId: string) =>
  apiPost(`/opportunities/today/select?profile_id=${encodeURIComponent(profileId)}`, {}).then(
    json<Opportunity[]>
  );
export const addManualJob = (payload: Record<string, unknown>) =>
  apiPost('/opportunities/manual', payload).then(json<{ posting_id: string }>);
export const listSources = () => apiFetch('/sources').then(json<JobSource[]>);
export const listScoutRuns = () => apiFetch('/scout-runs').then(json<ScoutRun[]>);
export const createSource = (payload: Record<string, unknown>) =>
  apiPost('/sources', payload).then(json<JobSource>);
export const scanSource = (id: string) =>
  apiPost(`/sources/${id}/scan`, {}).then(json<Record<string, unknown>>);
export const listContacts = () => apiFetch('/contacts').then(json<Contact[]>);
export const listCandidateFacts = () => apiFetch('/candidate-facts').then(json<CandidateFact[]>);
export const saveCandidateFact = (payload: Record<string, unknown>) =>
  apiPost('/candidate-facts', payload).then(json<CandidateFact>);
export const importMasterResumeFacts = () =>
  apiPost('/candidate-facts/import-master', {}).then(
    json<{ imported: number; facts: CandidateFact[] }>
  );
export const deleteCandidateFact = (id: string) =>
  apiDelete(`/candidate-facts/${id}`).then(json<{ message: string }>);
export const listReferrals = (id: string, refresh = false) =>
  apiFetch(`/opportunities/${id}/referrals?refresh=${refresh}`).then(json<ReferralMatch[]>);
export const updateReferral = (
  matchId: string,
  referralId: string,
  payload: { contacted?: boolean; response_notes?: string }
) =>
  apiPatch(`/opportunities/${matchId}/referrals/${referralId}`, payload).then(json<ReferralMatch>);
export async function importConnections(
  file: File
): Promise<{ imported: number; updated: number }> {
  const form = new FormData();
  form.append('file', file);
  return apiFetch('/contacts/import/linkedin', { method: 'POST', body: form }).then(
    json<{ imported: number; updated: number }>
  );
}

export async function streamScoutEvents(onEvent: () => void, signal: AbortSignal): Promise<void> {
  const response = await apiFetch('/events', { signal }, 1_800_000);
  if (!response.ok || !response.body) throw new Error('Live progress is unavailable.');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (!signal.aborted) {
    const { done, value } = await reader.read();
    if (done) return;
    buffer += decoder.decode(value, { stream: true });
    const messages = buffer.split('\n\n');
    buffer = messages.pop() || '';
    for (const message of messages) {
      if (message.includes('event: scout')) onEvent();
    }
  }
}
