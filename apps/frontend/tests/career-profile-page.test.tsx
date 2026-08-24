import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CandidateFactsPage } from '@/components/scout/candidate-facts-page';
import {
  importMasterResumeFacts,
  listCandidateFacts,
  listProfiles,
  saveCandidateFact,
} from '@/lib/api/scout';

vi.mock('@/lib/api/scout', () => ({
  createProfile: vi.fn(),
  deleteCandidateFact: vi.fn(),
  importMasterResumeFacts: vi.fn(),
  listCandidateFacts: vi.fn(),
  listProfiles: vi.fn(),
  saveCandidateFact: vi.fn(),
  updateProfile: vi.fn(),
}));

vi.mock('@/components/ui/confirm-dialog', () => ({ ConfirmDialog: () => null }));

describe('internship profile workspace', () => {
  beforeEach(() => {
    vi.mocked(listCandidateFacts).mockResolvedValue([]);
    vi.mocked(listProfiles).mockResolvedValue([]);
    vi.mocked(saveCandidateFact).mockResolvedValue({
      fact_id: 'fact-1',
      fact_key: 'internship_writing_preferences',
      label: 'Internship writing style',
      value: 'Concise and technical',
      category: 'writing_preferences',
      sensitive: false,
    });
    vi.mocked(importMasterResumeFacts).mockResolvedValue({ imported: 4, facts: [] });
  });

  it('starts with internship-specific targets and a clear evidence empty state', async () => {
    render(<CandidateFactsPage />);

    expect(await screen.findByRole('heading', { name: 'My internship profile' })).toBeVisible();
    expect(screen.getByDisplayValue(/Software Engineering Intern/)).toBeVisible();
    expect(screen.getByText('No evidence yet')).toBeVisible();
    expect(screen.getByText('Profile readiness 1 / 4')).toBeVisible();
  });

  it('can install the evidence-first internship writing preference', async () => {
    render(<CandidateFactsPage />);
    await screen.findByRole('heading', { name: 'My internship profile' });

    fireEvent.click(screen.getByRole('button', { name: /Use my writing defaults/i }));

    await waitFor(() => expect(saveCandidateFact).toHaveBeenCalledOnce());
    expect(saveCandidateFact).toHaveBeenCalledWith(
      expect.objectContaining({
        fact_key: 'internship_writing_preferences',
        category: 'writing_preferences',
        sensitive: false,
      })
    );
  });
});
