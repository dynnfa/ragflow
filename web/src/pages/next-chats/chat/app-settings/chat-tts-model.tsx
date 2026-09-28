import {
  ModelTreeSelectFormField,
  ModelTypeMap,
} from '@/components/model-tree-select';
import { useFetchDefaultModelDictionary } from '@/hooks/use-llm-request';
import { prefixName } from '@/utils/form';
import { useEffect } from 'react';
import { useFormContext, useWatch } from 'react-hook-form';
import { useTranslation } from 'react-i18next';

export function ChatTtsModel({ prefix = '' }: { prefix?: string }) {
  const { t } = useTranslation();
  const { control, setValue } = useFormContext();
  const name = prefixName(prefix, 'prompt_config.tts_model_id');
  const enabled = useWatch({
    control,
    name: prefixName(prefix, 'prompt_config.tts'),
  });
  const modelId = useWatch({ control, name });
  const { tts_id: defaultModelId } = useFetchDefaultModelDictionary();

  useEffect(() => {
    if (enabled && !modelId && defaultModelId) {
      setValue(name, defaultModelId, { shouldValidate: true });
    }
  }, [enabled, modelId, defaultModelId, name, setValue]);

  if (!enabled) return null;
  return (
    <ModelTreeSelectFormField
      name={name}
      modelTypes={ModelTypeMap.tts_id}
      label={t('chat.tts')}
      required
    />
  );
}
