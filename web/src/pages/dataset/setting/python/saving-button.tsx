import { ButtonLoading } from '@/components/ui/button';
import { ParseType } from '@/constants/knowledge';
import { useUpdateKnowledge } from '@/hooks/use-knowledge-request';
import { useMemo } from 'react';
import { useKnowledgeBaseContext } from '../../contexts/knowledge-base-context';
import { useFormContext } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router';

export function GeneralSavingButton() {
  const form = useFormContext();
  const { knowledgeBase } = useKnowledgeBaseContext();
  const { saveKnowledgeConfiguration, loading: submitLoading } =
    useUpdateKnowledge();
  const { id: kb_id } = useParams();
  const { t } = useTranslation();

  const defaultValues = useMemo(
    () => form.formState.defaultValues ?? {},
    [form.formState.defaultValues],
  );
  const chunk_method = defaultValues['chunk_method'];

  const handleSave = async () => {
    const valid = await form.trigger(['name', 'permission', 'shared_team_ids']);
    const { name, description, permission, shared_team_ids, avatar } =
      form.getValues();
    if (valid) {
      await saveKnowledgeConfiguration({
        kb_id,
        chunk_method,
        name,
        description,
        avatar,
        permission,
        shared_team_ids,
      });
    }
  };

  return (
    <ButtonLoading
      type="button"
      disabled={knowledgeBase?.can_write === false}
      loading={submitLoading}
      data-testid="ds-settings-basic-save-btn"
      onClick={handleSave}
    >
      {t('knowledgeConfiguration.save')}
    </ButtonLoading>
  );
}

export function SavingButton() {
  const { saveKnowledgeConfiguration, loading: submitLoading } =
    useUpdateKnowledge();
  const form = useFormContext();
  const { knowledgeBase } = useKnowledgeBaseContext();
  const { id: kb_id } = useParams();
  const { t } = useTranslation();

  return (
    <ButtonLoading
      disabled={knowledgeBase?.can_write === false}
      loading={submitLoading}
      data-testid="ds-settings-page-save-btn"
      onClick={() => {
        (async () => {
          try {
            const beValid = await form.trigger();
            if (!beValid) {
              const errors = form.formState.errors;
              console.error('Validation errors:', errors);
            }
            if (beValid) {
              form.handleSubmit(async (originalValues) => {
                const values = originalValues;
                if (originalValues.parse_type === ParseType.BuiltIn) {
                  values.pipeline_id = null;
                } else {
                  values.chunk_method = null;
                }

                await saveKnowledgeConfiguration({
                  kb_id,
                  ...values,
                  parser_config: {
                    ...values.parser_config,
                    image_table_context_window:
                      values.parser_config.image_table_context_window,
                    image_context_size:
                      values.parser_config.image_table_context_window,
                    table_context_size:
                      values.parser_config.image_table_context_window,
                    // Unset children delimiter if this option is not enabled
                    children_delimiter: values.parser_config.enable_children
                      ? values.parser_config.children_delimiter
                      : '',
                  },
                });
              })();
            }
          } catch (e) {
            console.log(e);
          }
        })();
      }}
    >
      {t('knowledgeConfiguration.save')}
    </ButtonLoading>
  );
}
