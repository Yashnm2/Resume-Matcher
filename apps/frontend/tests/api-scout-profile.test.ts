import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { deleteCandidateFact, importMasterResumeFacts } from '@/lib/api/scout';

describe('career profile API client', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('imports source-backed facts from the master resume', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ imported: 3, facts: [] }), { status: 200 })
    );

    await expect(importMasterResumeFacts()).resolves.toMatchObject({ imported: 3 });
    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toContain('/candidate-facts/import-master');
    expect((options as RequestInit).method).toBe('POST');
  });

  it('deletes one fact by its stable id', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ message: 'Candidate fact deleted successfully' }), {
        status: 200,
      })
    );

    await deleteCandidateFact('fact-1');
    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toContain('/candidate-facts/fact-1');
    expect((options as RequestInit).method).toBe('DELETE');
  });
});
