import { SelectWithSearch } from '@/components/originui/select-with-search';
import { RAGFlowFormItem } from '@/components/ragflow-form';
import { Checkbox } from '@/components/ui/checkbox';
import { PermissionRole } from '@/constants/permission';
import { useListTenant } from '@/hooks/use-user-setting-request';
import { useMemo } from 'react';
import { useFormContext, useWatch } from 'react-hook-form';
import { useTranslation } from 'react-i18next';

function TeamOption({
  label,
  teamId,
  selectedIds,
  onChange,
}: {
  label: string;
  teamId: string;
  selectedIds: string[];
  onChange: (ids: string[]) => void;
}) {
  const handleCheckedChange = (checked: boolean | 'indeterminate') => {
    onChange(
      checked === true
        ? [...selectedIds, teamId]
        : selectedIds.filter((id) => id !== teamId),
    );
  };
  return (
    <label className="flex items-center gap-2 py-1 text-text-primary">
      <Checkbox
        checked={selectedIds.includes(teamId)}
        onCheckedChange={handleCheckedChange}
        aria-label={label}
      />
      {label}
    </label>
  );
}

export function PermissionFormField() {
  const { t } = useTranslation();
  const form = useFormContext();
  const permission = useWatch({ control: form.control, name: 'permission' });
  const sharedTeamIds: string[] =
    useWatch({
      control: form.control,
      name: 'shared_team_ids',
      defaultValue: [],
    }) ?? [];
  const { data: teams, loading } = useListTenant();
  const scopeOptions = useMemo(
    () => [
      { label: t('knowledgeConfiguration.onlyMe'), value: PermissionRole.Me },
      {
        label: t('knowledgeConfiguration.selectedTeams'),
        value: PermissionRole.Team,
      },
    ],
    [t],
  );
  const teamOptions = useMemo(
    () =>
      teams
        .filter((team) => team.role === 'owner' || team.role === 'normal')
        .map((team) => ({
          label: team.nickname || team.email,
          value: team.tenant_id,
        })),
    [teams],
  );

  const handlePermissionChange = (value: string) => {
    form.setValue('permission', value, { shouldDirty: true });
    if (value === PermissionRole.Me) {
      form.setValue('shared_team_ids', [], {
        shouldDirty: true,
        shouldValidate: true,
      });
    }
  };
  const handleTeamsChange = (value: string[]) => {
    form.setValue('shared_team_ids', value, {
      shouldDirty: true,
      shouldValidate: true,
    });
  };

  return (
    <>
      <RAGFlowFormItem
        name="permission"
        label={t('knowledgeConfiguration.permissions')}
        description={t('knowledgeConfiguration.teamSharingTip')}
        horizontal
      >
        {() => (
          <SelectWithSearch
            options={scopeOptions}
            value={permission}
            onChange={handlePermissionChange}
            triggerClassName="w-full"
            testId="ds-settings-basic-permissions-select"
          />
        )}
      </RAGFlowFormItem>
      {permission === PermissionRole.Team && (
        <RAGFlowFormItem
          name="shared_team_ids"
          label={t('knowledgeConfiguration.sharedTeams')}
          horizontal
          required
        >
          {() => (
            <div
              className="max-h-56 overflow-y-auto"
              data-testid="ds-settings-shared-teams-select"
            >
              {teamOptions.map((team) => (
                <TeamOption
                  key={team.value}
                  label={team.label}
                  teamId={team.value}
                  selectedIds={sharedTeamIds}
                  onChange={handleTeamsChange}
                />
              ))}
              {!loading && teamOptions.length === 0 && (
                <p className="text-text-secondary">
                  {t('knowledgeConfiguration.noTeams')}
                </p>
              )}
            </div>
          )}
        </RAGFlowFormItem>
      )}
    </>
  );
}
