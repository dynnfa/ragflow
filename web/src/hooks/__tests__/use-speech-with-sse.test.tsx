let mockTenantId = 'team-one';
let mockReady = true;

jest.mock('../route-hook', () => ({}));
jest.mock('../use-user-setting-request', () => ({}));
jest.mock('eventsource-parser/stream', () => ({}));
jest.mock('../use-model-tenant', () => ({
  useModelTenant: () => ({ tenantId: mockTenantId, ready: mockReady }),
}));

import { renderHook } from '@testing-library/react';
import { useSpeechWithSse } from '../logic-hooks';

it('uses the selected team for speech, including after switching teams', async () => {
  const originalFetch = global.fetch;
  const fetchMock = jest.fn().mockResolvedValue({
    clone: () => ({ json: async () => ({ code: 0 }) }),
  } as Response);
  global.fetch = fetchMock;
  try {
    const { result, rerender } = renderHook(() => useSpeechWithSse());
    await result.current.read({ text: 'hello' });
    expect(fetchMock.mock.calls[0][1]?.headers).toEqual(
      expect.objectContaining({ 'X-Model-Tenant': 'team-one' }),
    );
    mockTenantId = 'team-two';
    rerender();
    await result.current.read({ text: 'hello' });
    expect(fetchMock.mock.calls[1][1]?.headers).toEqual(
      expect.objectContaining({ 'X-Model-Tenant': 'team-two' }),
    );
    mockReady = false;
    rerender();
    await expect(result.current.read({ text: 'hello' })).rejects.toThrow();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  } finally {
    global.fetch = originalFetch;
  }
});
