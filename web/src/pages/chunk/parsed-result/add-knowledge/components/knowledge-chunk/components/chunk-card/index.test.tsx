import { fireEvent, render, screen } from '@testing-library/react';
import { ChunkTextMode } from '../../constant';
import ChunkCard from './index';

jest.mock('@/components/image', () => ({
  __esModule: true,
  default: () => null,
}));
jest.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const Chunk = {
  chunk_id: 'chunk',
  available_int: 1,
  content_with_weight: 'Shared content',
  doc_id: 'doc',
  doc_name: 'Document',
  image_id: '',
  positions: [],
};

test('shared readers can inspect content but cannot edit or switch a chunk', () => {
  const editChunk = jest.fn();
  const switchChunk = jest.fn();
  const clickChunkCard = jest.fn();
  render(
    <ChunkCard
      item={Chunk}
      canWrite={false}
      checked={false}
      selected={false}
      textMode={ChunkTextMode.Full}
      editChunk={editChunk}
      switchChunk={switchChunk}
      clickChunkCard={clickChunkCard}
      handleCheckboxClick={jest.fn()}
    />,
  );
  expect(screen.getByRole('checkbox')).toBeDisabled();
  expect(screen.getByRole('switch')).toBeDisabled();
  fireEvent.doubleClick(screen.getByText('Shared content'));
  fireEvent.click(screen.getByText('Shared content'));
  expect(editChunk).not.toHaveBeenCalled();
  expect(switchChunk).not.toHaveBeenCalled();
  expect(clickChunkCard).toHaveBeenCalledWith('chunk');
});

test('creators retain chunk editing and switching', () => {
  const editChunk = jest.fn();
  const switchChunk = jest.fn();
  render(
    <ChunkCard
      item={Chunk}
      canWrite
      checked={false}
      selected={false}
      textMode={ChunkTextMode.Full}
      editChunk={editChunk}
      switchChunk={switchChunk}
      clickChunkCard={jest.fn()}
      handleCheckboxClick={jest.fn()}
    />,
  );
  fireEvent.doubleClick(screen.getByText('Shared content'));
  fireEvent.click(screen.getByRole('switch'));
  expect(editChunk).toHaveBeenCalledWith('chunk');
  expect(switchChunk).toHaveBeenCalledWith(0, ['chunk']);
});
