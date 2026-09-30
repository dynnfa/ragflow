import { act, fireEvent, render, screen } from '@testing-library/react';
import { useEffect } from 'react';
import { FormProvider, useForm, useWatch } from 'react-hook-form';
import { ParseType } from '@/constants/knowledge';
import { formSchema } from './form-schema';
import { PermissionFormField } from './permission-form-field';

jest.mock('@/hooks/use-user-setting-request', () => ({
  useListTenant: () => ({
    loading: false,
    data: [
      { tenant_id: 'owned', nickname: 'Own team', role: 'owner' },
      { tenant_id: 'joined', nickname: 'Joined team', role: 'normal' },
      { tenant_id: 'invited', nickname: 'Invited team', role: 'invite' },
    ],
  }),
}));
jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
jest.mock('@/components/originui/select-with-search', () => ({
  SelectWithSearch: ({
    options,
    value,
    onChange,
  }: {
    options: { label: string; value: string }[];
    value: string;
    onChange: (value: string) => void;
  }) => {
    const handleChange = (event: React.ChangeEvent<HTMLSelectElement>) =>
      onChange(event.target.value);
    return (
      <select aria-label="Sharing scope" value={value} onChange={handleChange}>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    );
  },
}));

const PrivateScope = { permission: 'me', shared_team_ids: [] as string[] };
function SharingForm({
  values = PrivateScope,
}: {
  values?: typeof PrivateScope;
}) {
  const form = useForm({ defaultValues: values });
  const current = useWatch({ control: form.control });
  useEffect(() => {
    form.reset(values);
  }, [form, values]);
  return (
    <FormProvider {...form}>
      <PermissionFormField />
      <output data-testid="sharing-values">{JSON.stringify(current)}</output>
    </FormProvider>
  );
}
const readValues = () =>
  JSON.parse(screen.getByTestId('sharing-values').textContent!);

test('only owned and accepted teams can be selected, with no implicit selection', async () => {
  render(<SharingForm />);
  await act(async () => {
    fireEvent.change(screen.getByLabelText('Sharing scope'), {
      target: { value: 'team' },
    });
  });
  expect(screen.getByRole('checkbox', { name: 'Own team' })).not.toBeChecked();
  expect(
    screen.getByRole('checkbox', { name: 'Joined team' }),
  ).not.toBeChecked();
  expect(
    screen.queryByRole('checkbox', { name: 'Invited team' }),
  ).not.toBeInTheDocument();
  await act(async () => {
    fireEvent.click(screen.getByRole('checkbox', { name: 'Own team' }));
  });
  await act(async () => {
    fireEvent.click(screen.getByRole('checkbox', { name: 'Joined team' }));
  });
  expect(readValues().shared_team_ids).toEqual(['owned', 'joined']);
  await act(async () => {
    fireEvent.click(screen.getByRole('checkbox', { name: 'Own team' }));
  });
  expect(readValues().shared_team_ids).toEqual(['joined']);
});

test('private scope clears grants and switching back does not select every team', async () => {
  render(
    <SharingForm
      values={{ permission: 'team', shared_team_ids: ['joined'] }}
    />,
  );
  await act(async () => {
    fireEvent.change(screen.getByLabelText('Sharing scope'), {
      target: { value: 'me' },
    });
  });
  expect(readValues()).toEqual(PrivateScope);
  await act(async () => {
    fireEvent.change(screen.getByLabelText('Sharing scope'), {
      target: { value: 'team' },
    });
  });
  expect(readValues().shared_team_ids).toEqual([]);
});

test('loading or resetting dataset settings restores the exact selected teams', async () => {
  const { rerender } = render(<SharingForm />);
  rerender(
    <SharingForm
      values={{ permission: 'team', shared_team_ids: ['joined'] }}
    />,
  );
  expect(screen.getByRole('checkbox', { name: 'Joined team' })).toBeChecked();
  expect(screen.getByRole('checkbox', { name: 'Own team' })).not.toBeChecked();
  rerender(
    <SharingForm values={{ permission: 'team', shared_team_ids: ['owned'] }} />,
  );
  expect(
    screen.getByRole('checkbox', { name: 'Joined team' }),
  ).not.toBeChecked();
  expect(screen.getByRole('checkbox', { name: 'Own team' })).toBeChecked();
});

test('team scope requires a target while private scope accepts none', () => {
  const settings = {
    parse_type: ParseType.BuiltIn,
    name: 'Dataset',
    chunk_method: 'naive',
    embedding_model: 'embedding',
    pagerank: 0,
  };
  const result = formSchema.safeParse({
    ...settings,
    permission: 'team',
    shared_team_ids: [],
  });
  expect(result.success).toBe(false);
  if (!result.success)
    expect(
      result.error.issues.some((issue) => issue.path[0] === 'shared_team_ids'),
    ).toBe(true);
  expect(
    formSchema.safeParse({
      ...settings,
      permission: 'team',
      shared_team_ids: ['joined'],
    }).success,
  ).toBe(true);
  expect(formSchema.safeParse({ ...settings, ...PrivateScope }).success).toBe(
    true,
  );
});
