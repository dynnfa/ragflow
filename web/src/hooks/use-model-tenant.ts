import { ITenant } from '@/interfaces/database/user-setting';
import { listTenant } from '@/services/user-service';
import authorization from '@/utils/authorization-util';
import { useQuery } from '@tanstack/react-query';
import { create } from 'zustand';

const ModelTenantKeys = {
  teams: (userId: string) => ['modelTeams', userId] as const,
};

const useModelTenantSelection = create<{
  selections: Record<string, string>;
  select: (userId: string, tenantId: string) => void;
}>((set) => ({
  selections: {},
  select: (userId, tenantId) => {
    localStorage.setItem(`model-team:${userId}`, tenantId);
    set((state) => ({
      selections: { ...state.selections, [userId]: tenantId },
    }));
  },
}));

export function selectModelTenant(teams: ITenant[], selectedId?: string) {
  const accepted = teams.filter((team) =>
    ['owner', 'normal'].includes(team.role),
  );
  const selected = accepted.find((team) => team.tenant_id === selectedId);
  if (selected) return selected;
  const joined = accepted.filter((team) => team.role === 'normal');
  return joined.length === 1
    ? joined[0]
    : accepted.find((team) => team.role === 'owner');
}

export function useModelTenant() {
  const userId: string = authorization.getUserInfoObject()?.id ?? '';
  const { data: teams = [], isSuccess } = useQuery<ITenant[]>({
    queryKey: ModelTenantKeys.teams(userId),
    queryFn: async () => {
      const { data } = await listTenant();
      if (data.code !== 0) throw new Error(data.message);
      return data.data.filter((team: ITenant) =>
        ['owner', 'normal'].includes(team.role),
      );
    },
    staleTime: 0,
  });
  const { selections, select } = useModelTenantSelection();
  const selectedId =
    selections[userId] ??
    localStorage.getItem(`model-team:${userId}`) ??
    undefined;
  const team = selectModelTenant(teams, selectedId);
  return {
    teams,
    team,
    tenantId: team?.tenant_id,
    ready: isSuccess && !!team,
    canManage: team?.role === 'owner',
    selectTenant: (tenantId: string) => select(userId, tenantId),
  };
}
