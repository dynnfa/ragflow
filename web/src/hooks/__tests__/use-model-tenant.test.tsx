import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { selectModelTenant, useModelTenant } from '../use-model-tenant';

const mockListTenant = jest.fn();
jest.mock('@/services/user-service', () => ({
  listTenant: () => mockListTenant(),
}));
jest.mock('@/utils/authorization-util', () => ({
  __esModule: true,
  default: { getUserInfoObject: () => ({ id: 'member' }) },
}));

const OwnTeam = {
  tenant_id: 'member',
  role: 'owner',
  nickname: 'My team',
  avatar: '',
  delta_seconds: 0,
  email: '',
  update_date: '',
};
const SharedTeam = {
  ...OwnTeam,
  tenant_id: 'owner',
  role: 'normal',
  nickname: 'Shared team',
};
const PendingTeam = { ...OwnTeam, tenant_id: 'pending', role: 'invite' };

beforeEach(() => localStorage.clear());

it('selects the sole joined team without including pending invitations', () => {
  expect(selectModelTenant([OwnTeam, SharedTeam, PendingTeam])).toEqual(
    SharedTeam,
  );
  expect(selectModelTenant([OwnTeam, PendingTeam], 'pending')).toEqual(OwnTeam);
});

it('respects explicit selection and avoids arbitrarily choosing between teams', () => {
  const secondTeam = { ...SharedTeam, tenant_id: 'other' };
  expect(selectModelTenant([OwnTeam, SharedTeam], 'member')).toEqual(OwnTeam);
  expect(selectModelTenant([OwnTeam, SharedTeam, secondTeam])).toEqual(OwnTeam);
  expect(selectModelTenant([OwnTeam], 'removed-team')).toEqual(OwnTeam);
});

it('switches between owner and member permissions and persists the selected team', async () => {
  mockListTenant.mockResolvedValue({
    data: { code: 0, data: [OwnTeam, SharedTeam, PendingTeam] },
  });
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const { result } = renderHook(() => useModelTenant(), { wrapper });
  await waitFor(() => expect(result.current.ready).toBe(true));
  expect(result.current.tenantId).toBe('owner');
  expect(result.current.canManage).toBe(false);
  expect(result.current.teams).toHaveLength(2);
  act(() => result.current.selectTenant('member'));
  expect(result.current.tenantId).toBe('member');
  expect(result.current.canManage).toBe(true);
  expect(localStorage.getItem('model-team:member')).toBe('member');
});
