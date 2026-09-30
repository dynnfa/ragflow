import { llmServiceForTenant } from './llm-service';
import request from '@/utils/next-request';

jest.mock('@/utils/next-request', () => ({
  __esModule: true,
  default: jest.fn(),
}));

it('scopes model queries to the selected team and retains model type filters', () => {
  const service = llmServiceForTenant('team-1');
  service.listAllAddedModels({ params: { type: 'chat' } }, true);
  expect(request).toHaveBeenCalledWith(
    expect.objectContaining({
      method: 'get',
      headers: { 'X-Model-Tenant': 'team-1' },
      params: { type: 'chat' },
    }),
  );
});

it('retains URL parameters and request bodies for both mutation calling styles', () => {
  const service = llmServiceForTenant('team-2');
  const body = {
    provider_name: 'OpenAI',
    instance_name: 'default',
    model_name: 'test-model',
  };
  service.addInstanceModel(body);
  expect(request).toHaveBeenLastCalledWith(
    expect.objectContaining({
      url: expect.stringContaining(
        '/providers/OpenAI/instances/default/models',
      ),
      headers: { 'X-Model-Tenant': 'team-2' },
      data: body,
    }),
  );
  service.addProviderInstance(
    { llm_factory: 'OpenAI', data: { instance_name: 'default' } },
    true,
  );
  expect(request).toHaveBeenLastCalledWith(
    expect.objectContaining({
      url: expect.stringContaining('/providers/OpenAI/instances'),
      headers: { 'X-Model-Tenant': 'team-2' },
      data: { instance_name: 'default' },
    }),
  );
});
