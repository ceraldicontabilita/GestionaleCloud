import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import RigheAcquisti from './RigheAcquisti';

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
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

  it('conferma soltanto la proposta della singola riga con motivazione', async () => {
    const proposta = {
      ...riga,
      classificazione: {
        stato: 'PROPOSTA', natura: 'utensile', categoria: 'utensili cucina', conto: '05.01.06',
        confidenza: 0.91, spiegazione: 'Descrizione inequivocabile', regola: 'SKU esatto', versione: 1,
      },
    };
    api.get.mockImplementation(url => Promise.resolve({ data: url.endsWith('/stato')
      ? { abilitato: false, proposte_aperte: 1 }
      : { righe: [proposta], totale: 1, da_verificare: 0, anomalie: 1, has_more: false } }));
    api.post.mockResolvedValue({ data: { classificazione: { stato: 'confermata' } } });
    render(<RigheAcquisti />);

    fireEvent.click(await screen.findByRole('button', { name: 'Dettagli' }));
    const conferma = screen.getByRole('button', { name: /Conferma/ });
    expect(conferma).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Motivazione decisione'), { target: { value: 'Verificata sul documento' } });
    fireEvent.click(conferma);

    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/righe-acquisti/classificazione/f-1%3A1/decisione',
      { azione: 'conferma', motivazione: 'Verificata sul documento', regola_fiscale: '' },
    ));
  });

  it('propone categoria e natura dal nome, si corregge da qui e salva con il flag non cespite', async () => {
    api.get.mockImplementation(url => Promise.resolve({ data: url.includes('/proposta-lotti')
      ? {
        nome_canc: 'Bacon a fette', categoria: 'Salumi', natura: 'ingrediente', alimentare: true,
        non_cespite: false, fonte: 'dal_nome', spiegazione: 'Il nome dice «Salumi».', conto: '55.01.01', centro_costo: 'CDC-04',
      }
      : url.includes('/proposta-categoria')
        ? { conto: '55.01.07', centro_costo: 'CDC-01', fonte: 'regole_in_uso', spiegazione: 'Proposta dalle scelte già in uso per «Bevande»: conto 55.01.07 Acquisti merci e centro CDC-01 BAR / CAFFETTERIA.' }
        : url.includes('/prodotti-lotti')
          ? {
            prodotti: [{ nome_canc: 'Bacon a fette', categoria: 'Salumi' }], categorie: ['Salumi', 'Bevande', 'Pasta'],
            centri_costo: [{ codice: 'CDC-01', nome: 'Bar' }, { codice: 'CDC-04', nome: 'Rosticceria' }],
            conti: [{ codice: '55.01.01', descrizione: 'Acquisti di materie prime' }, { codice: '55.01.07', descrizione: 'Acquisti merci' }],
          }
        : url.endsWith('/stato') ? { abilitato: false, proposte_aperte: 0 }
          : { righe: [riga], totale: 1, da_verificare: 1, anomalie: 0, has_more: false } }));
    api.post.mockResolvedValue({ data: { righe_estese: 2, cespiti_gia_creati: 1 } });
    render(<RigheAcquisti />);

    fireEvent.click(await screen.findByRole('button', { name: 'Dettagli' }));
    // La proposta riempie il form: categoria e natura arrivano dal nome.
    expect(await screen.findByText(/Il nome dice «Salumi»/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText('Categoria Lotti')).toHaveValue('Salumi'));
    expect(screen.getByLabelText('Natura')).toHaveValue('ingrediente');
    expect(screen.getByLabelText('Articolo di Lotti')).toHaveValue('Bacon a fette');
    // L'articolo che sto classificando resta in evidenza in cima al riquadro.
    expect(screen.getByTestId('articolo-in-classificazione')).toHaveTextContent('Pentola a pressione Lagostina');
    // La proposta porta anche conto e centro di costo.
    await waitFor(() => expect(screen.getByLabelText('Conto')).toHaveValue('55.01.01'));
    expect(screen.getByLabelText('Centro di costo')).toHaveValue('CDC-04');
    // Cambiando categoria, conto e centro si riproporranno dalle scelte in uso.
    fireEvent.change(screen.getByLabelText('Categoria Lotti'), { target: { value: 'Bevande' } });
    await waitFor(() => expect(screen.getByLabelText('Conto')).toHaveValue('55.01.07'));
    expect(screen.getByLabelText('Centro di costo')).toHaveValue('CDC-01');
    expect(await screen.findByText(/Acquisti merci e centro CDC-01/)).toBeInTheDocument();
    // Il titolare spunta «non cespite».
    fireEvent.click(screen.getByLabelText('Non è un cespite'));
    fireEvent.click(screen.getByRole('button', { name: /Salva e aggiorna le righe uguali/ }));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/righe-acquisti/f-1%3A1/prodotto-lotti',
      expect.objectContaining({
        nome_canc: 'Bacon a fette', categoria: 'Bevande', alimentare: true, natura: 'ingrediente',
        conto: '55.01.07', centro_costo: 'CDC-01', non_cespite: true,
      }),
    ));
    // L'esito dice quante righe uguali sono state aggiornate e avvisa dei cespiti già nati.
    expect(await screen.findByText(/aggiornate anche 2 righe uguali/)).toBeInTheDocument();
    expect(screen.getByText(/già 1 cespiti creati/)).toBeInTheDocument();
  });

  it('non permette «non cespite» insieme alla natura cespite', async () => {
    api.get.mockImplementation(url => Promise.resolve({ data: url.includes('/proposta-lotti')
      ? { nome_canc: null, categoria: null, natura: null, alimentare: true, non_cespite: false, fonte: null, spiegazione: 'Nessuna proposta' }
      : url.includes('/prodotti-lotti') ? { prodotti: [], categorie: ['Pasta'], centri_costo: [] }
        : url.endsWith('/stato') ? { abilitato: false, proposte_aperte: 0 }
          : { righe: [riga], totale: 1, da_verificare: 1, anomalie: 0, has_more: false } }));
    render(<RigheAcquisti />);

    fireEvent.click(await screen.findByRole('button', { name: 'Dettagli' }));
    fireEvent.click(screen.getByLabelText('Non è merce alimentare'));
    fireEvent.change(screen.getByLabelText('Natura'), { target: { value: 'cespite' } });
    fireEvent.click(screen.getByLabelText('Non è un cespite'));
    expect(await screen.findByRole('alert')).toHaveTextContent(/non possono stare insieme/);
    expect(screen.getByRole('button', { name: /Salva e aggiorna le righe uguali/ })).toBeDisabled();
  });

  it('mostra dentro il riquadro l\'errore del salvataggio, senza chiudere la finestra', async () => {
    api.get.mockImplementation(url => Promise.resolve({ data: url.includes('/proposta-lotti')
      ? { nome_canc: 'Bacon a fette', categoria: 'Salumi', natura: 'ingrediente', alimentare: true, non_cespite: false, fonte: 'dal_nome', spiegazione: 'Il nome dice «Salumi».', conto: null, centro_costo: null }
      : url.includes('/prodotti-lotti') ? { prodotti: [{ nome_canc: 'Bacon a fette' }], categorie: ['Salumi'], centri_costo: [], conti: [] }
        : url.endsWith('/stato') ? { abilitato: false, proposte_aperte: 0 }
          : { righe: [riga], totale: 1, da_verificare: 1, anomalie: 0, has_more: false } }));
    api.post.mockRejectedValue({ response: { data: { detail: 'conto fuori dal piano dei conti ufficiale' } } });
    render(<RigheAcquisti />);

    fireEvent.click(await screen.findByRole('button', { name: 'Dettagli' }));
    await waitFor(() => expect(screen.getByLabelText('Categoria Lotti')).toHaveValue('Salumi'));
    fireEvent.click(screen.getByRole('button', { name: /Salva e aggiorna le righe uguali/ }));
    expect(await screen.findByText('conto fuori dal piano dei conti ufficiale')).toBeInTheDocument();
    expect(screen.getByTestId('articolo-in-classificazione')).toBeInTheDocument();
  });
});
