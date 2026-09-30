import React from 'react';
import { MemoryRouter } from 'react-router-dom';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import Commercialista from './Commercialista.jsx';

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }));
vi.mock('../contexts/AnnoContext', () => ({ useAnnoGlobale: () => ({ anno: 2026, setAnno: vi.fn() }) }));
vi.mock('../contexts/GuscioContext', () => ({
  useGuscio: () => ({ alertCommercialista: null, ricaricaAlertCommercialista: vi.fn() }),
}));
vi.mock('jspdf', () => ({ jsPDF: vi.fn() }));
vi.mock('jspdf-autotable', () => ({ default: vi.fn() }));

const risposta = url => {
  if (url.includes('/config')) return { data: { email: 'c@esempio.it', nome: 'Dott.', smtp_configured: true } };
  if (url.includes('/log')) return { data: { log: [] } };
  if (url.includes('/invii')) return { data: { invii: [] } };
  if (url.includes('/pacchetto')) return { data: { periodo: {}, destinatario: 'c@esempio.it', voci: [] } };
  if (url.includes('/prima-nota-cassa')) return { data: { movimenti: [], totale_entrate: 0, totale_uscite: 0, saldo: 0 } };
  if (url.includes('/fatture-cassa')) return { data: { fatture: [], totale_fatture: 0, totale_importo: 0 } };
  if (url.includes('/api/assegni')) return { data: [] };
  return { data: {} };
};

describe('Area Commercialista: il periodo alimenta ogni chiamata', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockImplementation(async url => risposta(url));
  });

  it('mese di default e poi trimestre: dal/al su cassa, fatture e pacchetto', async () => {
    render(<MemoryRouter initialEntries={['/commercialista?mese=9']}><Commercialista /></MemoryRouter>);
    await waitFor(() => expect(api.get).toHaveBeenCalledWith(
      '/api/commercialista/prima-nota-cassa/2026/9?dal=2026-09-01&al=2026-09-30'));
    expect(api.get).toHaveBeenCalledWith('/api/commercialista/fatture-cassa/2026/9?dal=2026-09-01&al=2026-09-30');
    expect(api.get).toHaveBeenCalledWith('/api/commercialista/pacchetto?dal=2026-09-01&al=2026-09-30');

    fireEvent.click(screen.getByRole('radio', { name: 'Trimestre' }));
    fireEvent.change(screen.getByLabelText('Trimestre'), { target: { value: '2' } });
    await waitFor(() => expect(api.get).toHaveBeenCalledWith(
      '/api/commercialista/prima-nota-cassa/2026/0?dal=2026-04-01&al=2026-06-30'));
    expect(api.get).toHaveBeenCalledWith('/api/commercialista/pacchetto?dal=2026-04-01&al=2026-06-30');
    // l'invio singolo di un mese non vale per un trimestre: il bottone e' spento e dice dove andare
    expect(screen.getByTestId('send-prima-nota-email')).toBeDisabled();
  });
});
