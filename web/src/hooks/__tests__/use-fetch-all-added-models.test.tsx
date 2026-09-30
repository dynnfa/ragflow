import { ModelTypeMap } from '@/components/model-tree-select';
import request from '@/utils/next-request';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { useFetchAllAddedModels, useModelValidIds } from '../use-llm-request';

let mockTenantId = 'team-1';

jest.mock('@/utils/next-request', () => ({
  __esModule: true,
  default: jest.fn(),
}));

jest.mock('../use-model-tenant', () => ({
  useModelTenant: () => ({ tenantId: mockTenantId, ready: true }),
}));

jest.mock('../use-warn-empty-model', () => ({
  useWarnEmptyModel: jest.fn(),
}));

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

function model(modelId: string) {
  return {
    model_id: modelId,
    name: modelId,
    model_type: ['chat'],
    provider_id: 'openai',
    provider_name: 'OpenAI',
    instance_name: 'default',
    instance_id: 'default',
  };
}

beforeEach(() => {
  mockTenantId = 'team-1';
  jest.mocked(request).mockReset();
});

it('fetches the selected team model list without an owner or type query', async () => {
  jest.mocked(request).mockResolvedValue({
    data: { code: 0, data: [model('model-1')] },
  });
  const { result } = renderHook(() => useFetchAllAddedModels(), {
    wrapper: createWrapper(),
  });

  await waitFor(() => expect(result.current.isFetched).toBe(true));

  expect(result.current.data[0].model_id).toBe('model-1');
  expect(request).toHaveBeenCalledWith(
    expect.objectContaining({
      url: expect.stringMatching(/\/models$/),
      method: 'get',
      headers: { 'X-Model-Tenant': 'team-1' },
      params: {},
    }),
  );
});

it('preserves an explicitly requested model type', async () => {
  jest.mocked(request).mockResolvedValue({ data: { code: 0, data: [] } });
  const { result } = renderHook(() => useFetchAllAddedModels('chat'), {
    wrapper: createWrapper(),
  });

  await waitFor(() => expect(result.current.isFetched).toBe(true));

  expect(request).toHaveBeenCalledWith(
    expect.objectContaining({
      headers: { 'X-Model-Tenant': 'team-1' },
      params: { type: 'chat' },
    }),
  );
});

it('refreshes model validation when the selected model team changes', async () => {
  jest.mocked(request).mockResolvedValueOnce({
    data: { code: 0, data: [model('team-one-model')] },
  });
  const { result, rerender } = renderHook(
    () => useModelValidIds(ModelTypeMap.llm_id),
    { wrapper: createWrapper() },
  );
  await waitFor(() =>
    expect(result.current.validIds.has('team-one-model')).toBe(true),
  );

  mockTenantId = 'team-2';
  jest.mocked(request).mockResolvedValueOnce({
    data: { code: 0, data: [model('team-two-model')] },
  });
  rerender();
  expect(result.current.isFetched).toBe(false);
  expect(result.current.validIds.has('team-one-model')).toBe(false);

  await waitFor(() =>
    expect(result.current.validIds.has('team-two-model')).toBe(true),
  );
  expect(request).toHaveBeenLastCalledWith(
    expect.objectContaining({
      headers: { 'X-Model-Tenant': 'team-2' },
      params: {},
    }),
  );
});
