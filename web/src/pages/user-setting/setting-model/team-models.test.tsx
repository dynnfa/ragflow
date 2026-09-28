import { render, screen } from '@testing-library/react';
import { TeamModels } from './team-models';

jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
jest.mock('@/hooks/use-llm-request', () => ({
  useFetchAllAddedModels: () => ({
    data: [
      {
        model_id: 'shared-model',
        name: 'Team chat model',
        provider_name: 'OpenAI',
        instance_name: 'team',
        model_type: ['chat'],
      },
    ],
    loading: false,
  }),
  useFetchDefaultModels: () => ({
    data: [{ model_type: 'chat', model_name: 'Team chat model' }],
  }),
}));

it('lets members inspect shared models without credential forms or management controls', () => {
  render(<TeamModels />);
  expect(screen.getAllByText(/Team chat model/)).toHaveLength(2);
  expect(screen.getByText('setting.teamModelsReadOnly')).toBeInTheDocument();
  expect(screen.queryByRole('button')).not.toBeInTheDocument();
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
});
