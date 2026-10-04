import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import RigheAcquisti from './RigheAcquisti';

vi.mock('../api', () => ({ default: { get: vi.fn() } }));
vi.mock('../contexts/AnnoContext', () => ({ useAnnoGlobale: () => ({ anno: 2026 }) }));
vi.mock('../lib/utils', async importOriginal => {
  const actual = await importOriginal();
  return { ...actual, useIsMobile: () => false };
});

const riga = {
  id: 'f-1:1', fattura_id: 'f-1', documento_id: 'doc-1', hash_originale: 'a'.repeat(64),
  url_originale: '/api/fatture-ricevute/fattura/f-1/view-assoinvoice', numero_linea: '1',
  descrizione_originale: 'Pentola a pressione Lagostina', codici_articolo: [{ tipo: 'ASIN', valore: 'B00TEST' }],
  fornitore: 'Amazon Business EU', partita_iva: '13397910962', numero_fattura: 'IT63F2ABEC',
  data_fattura: '2026-01-10', tipo_documento: 'TD04', imponibile: 67.71, aliquota_iva: 22,
  ordini: ['407-4144790-3445105'], contratti: [], ddt: [],
  pagamenti_dichiarati: [{ codice: 'MP08', descrizione: 'Carta di pagamento', importo: 82.61 }],
  metodo_previsto: 'banca', metodo_effettivo: null,
  classificazione: { stato: 'DA_VERIFICARE' },
  nota_credito: { stato: 'da_recuperare', messaggio: 'Carica o recupera la fattura IT53HH03ABEI del 2025-12-16.' },
  anomalie: ['nota_credito_da_recuperare'],
};

describe('Righe acquisti', () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => cleanup());

  it('carica 200 righe canoniche e mantiene distinta la prova di pagamento', async () => {
    api.get.mockResolvedValue({ data: { righe: [riga], totale: 1, da_verificare: 1, anomalie: 1, has_more: false } });
    render(<RigheAcquisti />);

    expect(await screen.findByText('Pentola a pressione Lagostina')).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith('/api/righe-acquisti', { params: expect.objectContaining({ anno: '2026', limit: 200, skip: 0 }) });
    fireEvent.click(screen.getByRole('button', { name: 'Dettagli' }));
    expect(screen.getByText(/Pagamenti: dichiarato, previsto ed effettivo restano distinti/i)).toBeInTheDocument();
    expect(screen.getByText(/MP08 - Carta di pagamento/)).toBeInTheDocument();
    expect(screen.getByText(/Metodo previsto dal fornitore: banca/)).toBeInTheDocument();
    expect(screen.getByText(/Metodo effettivo provato: non documentato/)).toBeInTheDocument();
    expect(screen.getByText(/Carica o recupera la fattura IT53HH03ABEI/)).toBeInTheDocument();
  });

  it('mostra un errore recuperabile senza presentare un elenco vuoto come valido', async () => {
    api.get.mockRejectedValue({ response: { data: { detail: 'Servizio temporaneamente non disponibile' } } });
    render(<RigheAcquisti />);

    expect(await screen.findByRole('alert')).toHaveTextContent('Servizio temporaneamente non disponibile');
    await waitFor(() => expect(screen.queryByText('Nessuna riga trovata con questi filtri.')).not.toBeInTheDocument());
  });
});
