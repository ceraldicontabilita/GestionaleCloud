import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import api from '../api';
import ApriOriginale, { VisoreOriginale } from './ApriOriginale';

vi.mock('../api', () => ({
  default: { get: vi.fn() },
  messaggioErrore: e => {
    const d = e?.response?.data;
    return `${d?.message || e?.message}${d?.correlation_id ? ` (rif. ${d.correlation_id})` : ''}`;
  },
}));
vi.mock('sonner', () => ({ toast: { error: vi.fn() } }));

const rispostaPdf = () => ({
  data: new Blob(['%PDF'], { type: 'application/pdf' }),
  headers: { 'content-type': 'application/pdf' },
});

describe('ApriOriginale: un solo componente per ogni originale', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.URL.createObjectURL = vi.fn(() => 'blob:originale');
    window.URL.revokeObjectURL = vi.fn();
  });

  it('apre l originale dall endpoint unico per tipo e id', async () => {
    api.get.mockResolvedValue(rispostaPdf());
    render(<ApriOriginale tipo="cedolino" id="c1" titolo="Busta paga" testId="apri" />);
    fireEvent.click(screen.getByTestId('apri'));
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/originale/cedolino/c1', { responseType: 'blob' }));
    expect(await screen.findByTestId('document-viewer-download')).toBeInTheDocument();
  });

  it.each([
    [{ driveId: 'D1' }, '/api/originale?drive_id=D1'],
    [{ sha256: 'ab' }, '/api/originale?sha256=ab'],
    [{ tipo: 'verbale', id: 'A/1', indice: 2 }, '/api/originale/verbale/A/1?indice=2'],
    [{ tipo: 'protocollo', id: '2023/000123' }, '/api/originale/protocollo/2023/000123'],
    [{ url: '/api/originale/f24/m1' }, '/api/originale/f24/m1'],
  ])('indirizzo per %j', async (props, atteso) => {
    api.get.mockResolvedValue(rispostaPdf());
    render(<ApriOriginale {...props} testId="apri" />);
    fireEvent.click(screen.getByTestId('apri'));
    await waitFor(() => expect(api.get).toHaveBeenCalledWith(atteso, { responseType: 'blob' }));
  });

  it('senza chiave non mostra un bottone che non apre niente', () => {
    render(<ApriOriginale tipo="cedolino" id={null} testId="apri" />);
    expect(screen.queryByTestId('apri')).toBeNull();
    expect(screen.getByTestId('apri-assente')).toHaveTextContent('Originale non disponibile');
  });

  it('il tocco e di almeno 44px e il testo del bottone e quello passato', () => {
    render(<ApriOriginale tipo="f24" id="m1" testId="apri">Importo versato 1.000,00</ApriOriginale>);
    const bottone = screen.getByTestId('apri');
    expect(bottone).toHaveTextContent('Importo versato 1.000,00');
    expect(bottone.style.minHeight).toBe('44px');
  });

  it('l originale che il server non trova si dice con le parole del server e il riferimento', async () => {
    const corpo = new Blob([JSON.stringify({
      code: 'ORIGINALE_NON_DISPONIBILE', message: 'Originale non disponibile', correlation_id: 'abc123def456',
    })], { type: 'application/json' });
    api.get.mockRejectedValue({ message: 'Request failed with status code 404', response: { status: 404, data: corpo } });
    render(<VisoreOriginale url="/api/originale/quietanza/q1" titolo="Quietanza" onClose={() => {}} />);
    expect(await screen.findByText(/Originale non disponibile \(rif\. abc123def456\)/)).toBeInTheDocument();
  });

  it('un XML resta XML: il tipo lo dice il server, non il visualizzatore', async () => {
    api.get.mockResolvedValue({
      data: new Blob(['<x/>'], { type: 'application/xml' }), headers: { 'content-type': 'application/xml; charset=utf-8' },
    });
    render(<VisoreOriginale url="/api/originale/fattura/f1" titolo="Fattura" onClose={() => {}} />);
    await waitFor(() => expect(window.URL.createObjectURL).toHaveBeenCalled());
    expect(window.URL.createObjectURL.mock.calls[0][0].type).toBe('application/xml');
  });
});
