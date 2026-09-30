import { render, screen } from '@testing-library/react';
import Compilation from './index';

jest.mock('@/components/back-button', () => ({
  __esModule: true,
  default: ({ children }: { children: React.ReactNode }) => (
    <button>{children}</button>
  ),
}));
jest.mock('@/components/originui/select-with-search', () => ({
  SelectWithSearch: () => null,
}));
jest.mock('@/components/ragflow-avatar', () => ({ RAGFlowAvatar: () => null }));
jest.mock('@/hooks/logic-hooks/navigate-hooks', () => ({
  useNavigatePage: () => ({ navigateToDataFile: () => jest.fn() }),
}));
jest.mock('@/hooks/use-knowledge-request', () => ({
  useFetchKnowledgeBaseConfiguration: () => ({
    data: { id: 'kb', name: 'Shared dataset', can_write: false },
    loading: false,
  }),
}));
jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
jest.mock('react-router', () => ({ useParams: () => ({ id: 'kb' }) }));
jest.mock('./constants', () => ({
  ViewMode: { LlmWiki: 'wiki' },
  StructureKinds: [],
  VisibleViewModes: [],
  ViewModeLabelKeyMap: {},
}));
jest.mock('./dataset-structure-view', () => ({
  DatasetStructureView: () => null,
}));
jest.mock('./skills-view', () => ({ SkillsView: () => null }));
jest.mock('./nav-tree-view', () => ({ NavTreeView: () => null }));
jest.mock('./llm-wiki-view', () => ({
  LlmWikiView: () => {
    const {
      useKnowledgeBaseContext,
    } = require('../contexts/knowledge-base-context');
    const { knowledgeBase } = useKnowledgeBaseContext();
    return (
      <output data-testid="access">{JSON.stringify(knowledgeBase)}</output>
    );
  },
}));

test('the standalone compilation route provides dataset permissions to its views', () => {
  render(<Compilation />);
  expect(JSON.parse(screen.getByTestId('access').textContent!)).toEqual({
    id: 'kb',
    name: 'Shared dataset',
    can_write: false,
  });
});
