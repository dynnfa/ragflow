import { act, render, screen, waitFor } from '@testing-library/react';
import { FormProvider, useForm } from 'react-hook-form';
import { ChatTtsModel } from './chat-tts-model';

let mockDefaultModel = 'team-tts';
jest.mock('@/hooks/use-llm-request', () => ({
  useFetchDefaultModelDictionary: () => ({ tts_id: mockDefaultModel }),
}));
jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
jest.mock('@/components/model-tree-select', () => ({
  ModelTypeMap: { tts_id: ['tts'] },
  ModelTreeSelectFormField: () => <div data-testid="tts-picker" />,
}));

it('persists the team default without replacing an existing model after a team switch', async () => {
  let form: {
    getValues: (name: string) => unknown;
    setValue: (name: string, value: unknown) => void;
  };
  function Harness() {
    const methods = useForm<Record<string, any>>({
      defaultValues: { prompt_config: { tts: true } },
    });
    form = methods;
    return (
      <FormProvider {...methods}>
        <ChatTtsModel />
      </FormProvider>
    );
  }
  const { rerender } = render(<Harness />);
  await waitFor(() =>
    expect(form.getValues('prompt_config.tts_model_id')).toBe('team-tts'),
  );
  expect(screen.getByTestId('tts-picker')).toBeInTheDocument();
  mockDefaultModel = 'other-team-tts';
  rerender(<Harness />);
  expect(form!.getValues('prompt_config.tts_model_id')).toBe('team-tts');
  act(() => form!.setValue('prompt_config.tts', false));
  expect(screen.queryByTestId('tts-picker')).not.toBeInTheDocument();
  expect(form!.getValues('prompt_config.tts_model_id')).toBe('team-tts');
});
