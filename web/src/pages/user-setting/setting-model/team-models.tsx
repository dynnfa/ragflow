import {
  useFetchAllAddedModels,
  useFetchDefaultModels,
} from '@/hooks/use-llm-request';
import { useTranslation } from 'react-i18next';

export function TeamModels() {
  const { t } = useTranslation();
  const { data: models, loading } = useFetchAllAddedModels();
  const { data: defaults } = useFetchDefaultModels();

  return (
    <section className="flex-1 overflow-auto rounded-lg border border-border-button p-6">
      <p className="mb-6 text-sm text-text-secondary">
        {t('setting.teamModelsReadOnly')}
      </p>
      <h2 className="mb-3 text-lg text-text-primary">
        {t('setting.systemModelSettings')}
      </h2>
      <ul className="mb-6 space-y-2 text-sm text-text-secondary">
        {defaults.map((model) => (
          <li key={model.model_type}>
            {model.model_type}: {model.model_name || '—'}
          </li>
        ))}
      </ul>
      <h2 className="mb-3 text-lg text-text-primary">
        {t('setting.availableModels')}
      </h2>
      {loading ? (
        <p className="text-text-secondary">…</p>
      ) : (
        <ul className="space-y-2 text-sm text-text-primary">
          {models.map((model) => (
            <li key={model.model_id} className="rounded-md bg-bg-card p-3">
              {model.name}
              <span className="ml-3 text-text-secondary">
                {model.provider_name} / {model.instance_name} ·{' '}
                {model.model_type.join(', ')}
              </span>
            </li>
          ))}
          {models.length === 0 && (
            <li className="text-text-secondary">
              {t('setting.noInstancesConfigured')}
            </li>
          )}
        </ul>
      )}
    </section>
  );
}
