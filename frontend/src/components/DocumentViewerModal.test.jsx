import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import api from '../api';
import DocumentViewerModal from './DocumentViewerModal';

vi.mock('../api', () => ({ default: { get: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { error: vi.fn() } }));

describe('Vedi documento: il file si puo sempre scaricare', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.URL.createObjectURL = vi.fn(() => 'blob:x');
    window.URL.revokeObjectURL = vi.fn();
  });

  it('mostra «Scarica» anche senza onDownload quando il documento e del gestionale', async () => {
    api.get.mockResolvedValue({
      data: new Blob(['%PDF'], { type: 'application/pdf' }),
      headers: { 'content-type': 'application/pdf', 'content-disposition': 'inline; filename="Quietanza.pdf"' },
    });
    render(<DocumentViewerModal title="Quietanza F24 04/2026" src="/api/originale/quietanza/q1" onClose={() => {}} />);
    fireEvent.click(screen.getByTestId('document-viewer-download'));
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/api/originale/quietanza/q1', { responseType: 'blob' })
    );
  });

  it('senza un indirizzo del gestionale non mostra un «Scarica» che non funzionerebbe', () => {
    render(<DocumentViewerModal title="Esterno" src="https://example.org/x.pdf" onClose={() => {}} />);
    expect(screen.queryByTestId('document-viewer-download')).toBeNull();
  });
});
