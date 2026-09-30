import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../../api';
import PacchettoDaInviare from './PacchettoDaInviare';

vi.mock('../../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock('../../lib/scaricaOriginale', () => ({ scaricaOriginale: vi.fn().mockResolvedValue('x.pdf') }));

const periodo = { valido: true, dal: '2026-09-01', al: '2026-09-30', etichetta: 'Settembre 2026', anno: 2026, meseRotta: 9 };
const config = { email: 'commercialista@esempio.it', smtp_configured: true };

const voce = (id, titolo, stato, extra = {}) => ({
  voce: id, titolo, stato, motivo: null, conteggio: 3, totale: '120,00', avvisi: [], ultimo_invio: null, ...extra,
});

const pacchetto = () => ({
  periodo: { dal: '2026-09-01', al: '2026-09-30', etichetta: 'Settembre 2026' },
  destinatario: 'commercialista@esempio.it',
  smtp_configurato: true,
  voci: [
    voce('prima_nota_cassa', 'Prima Nota Cassa', 'pronto'),
    voce('banca', 'Banca (conto BPM)', 'incompleto', { motivo: '2 movimenti su 9 non sono ancora nell\'estratto conto ufficiale' }),
    voce('paypal', 'PayPal', 'vuoto', { conteggio: 0, totale: null, motivo: 'Nessun dato nel periodo' }),
    voce('sumup', 'SumUp', 'non_disponibile', { conteggio: 0, totale: null, motivo: 'Fonte non leggibile (RuntimeError)' }),
    voce('presenze', 'Presenze (HR)', 'da_inviare', { conteggio: 1, motivo: 'Presenze registrate in HR, invio al consulente non ancora fatto' }),
    voce('bonifici', 'Bonifici effettuati', 'pronto', {
      ultimo_invio: { data: '2026-09-20T10:00:00+00:00', dal: '2026-09-01', al: '2026-09-30', destinatario: 'commercialista@esempio.it' },
    }),
  ],
});

async function apri(dati = pacchetto()) {
  api.get.mockResolvedValue({ data: dati });
  const avviso = vi.fn();
  const onInviato = vi.fn();
  render(<PacchettoDaInviare periodo={periodo} carnetIds={[]} config={config} avviso={avviso} onInviato={onInviato} />);
  await screen.findByTestId('voce-prima_nota_cassa');
  return { avviso, onInviato };
}

describe('Pacchetto da inviare', () => {
  beforeEach(() => vi.clearAllMocks());

  it('legge il pacchetto del periodo con dal e al', async () => {
    await apri();
    expect(api.get).toHaveBeenCalledWith('/api/commercialista/pacchetto?dal=2026-09-01&al=2026-09-30');
  });

  it('ogni scheda dice stato, righe, totale e motivo con le parole', async () => {
    await apri();
    expect(screen.getByTestId('stato-prima_nota_cassa')).toHaveTextContent('Pronto');
    expect(screen.getByTestId('conteggio-prima_nota_cassa')).toHaveTextContent('3 righe · € 120,00');
    expect(screen.getByTestId('stato-banca')).toHaveTextContent('Incompleto');
    expect(screen.getByTestId('motivo-banca')).toHaveTextContent('2 movimenti su 9');
    expect(screen.getByTestId('stato-paypal')).toHaveTextContent('Vuoto');
    expect(screen.getByTestId('stato-sumup')).toHaveTextContent('Non disponibile');
    expect(screen.getByTestId('motivo-sumup')).toHaveTextContent('RuntimeError');
    expect(screen.getByTestId('stato-presenze')).toHaveTextContent('Da inviare');
    expect(screen.getByTestId('conteggio-presenze')).toHaveTextContent('1 mese con presenze');
  });

  it('«Ultimo invio» per scheda, oppure mai inviato', async () => {
    await apri();
    expect(screen.getByTestId('ultimo-bonifici')).toHaveTextContent('Ultimo invio 20/09/2026');
    expect(screen.getByTestId('ultimo-prima_nota_cassa')).toHaveTextContent('Mai inviato per questo periodo');
  });

  it('spunta da sola i documenti pronti; vuoto e non disponibile non si includono', async () => {
    await apri();
    expect(screen.getByTestId('includi-prima_nota_cassa')).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByTestId('includi-banca')).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByTestId('includi-paypal')).toBeDisabled();
    expect(screen.getByTestId('includi-sumup')).toBeDisabled();
    expect(screen.getByTestId('invia-selezionati')).toHaveTextContent('Invia selezionati (4)');
    fireEvent.click(screen.getByTestId('includi-banca'));
    expect(screen.getByTestId('invia-selezionati')).toHaveTextContent('Invia selezionati (3)');
  });

  it('il modale elenca cosa parte, a chi e per quale periodo; l\'invio e\' un\'unica chiamata', async () => {
    const { avviso, onInviato } = await apri();
    api.post.mockResolvedValue({
      data: {
        success: true, message: '4 allegati inviati a commercialista@esempio.it',
        esiti: [
          { voce: 'prima_nota_cassa', titolo: 'Prima Nota Cassa', esito: 'allegata', file: ['a.pdf'] },
          { voce: 'banca', titolo: 'Banca (conto BPM)', esito: 'allegata', file: ['b.pdf'] },
          { voce: 'presenze', titolo: 'Presenze (HR)', esito: 'allegata', file: ['p.pdf', 'p.csv'] },
          { voce: 'bonifici', titolo: 'Bonifici effettuati', esito: 'saltata', motivo: 'Nessun dato nel periodo' },
        ],
      },
    });
    fireEvent.click(screen.getByTestId('invia-selezionati'));
    const modale = await screen.findByRole('dialog');
    expect(within(modale).getByTestId('destinatario-invio')).toHaveTextContent('commercialista@esempio.it');
    expect(modale).toHaveTextContent('Settembre 2026 (01/09/2026 - 30/09/2026)');
    expect(within(modale).getByTestId('conferma-banca')).toHaveTextContent('Incompleto: 2 movimenti su 9');
    expect(within(modale).getByTestId('conferma-prima_nota_cassa')).toBeInTheDocument();
    expect(within(modale).queryByTestId('conferma-paypal')).toBeNull();

    fireEvent.click(within(modale).getByTestId('conferma-invio-pacchetto'));
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    expect(api.post).toHaveBeenCalledWith('/api/commercialista/invia-pacchetto', expect.objectContaining({
      dal: '2026-09-01', al: '2026-09-30', presenze_rinvia: false,
      voci: ['prima_nota_cassa', 'banca', 'presenze', 'bonifici'],
    }));
    // esito per ogni allegato, scritto a parole
    const esiti = await screen.findByTestId('esiti-invio');
    expect(within(esiti).getByTestId('esito-prima_nota_cassa')).toHaveTextContent('inviato');
    expect(within(esiti).getByTestId('esito-presenze')).toHaveTextContent('inviato (2 file)');
    expect(within(esiti).getByTestId('esito-bonifici')).toHaveTextContent('saltato, Nessun dato nel periodo');
    expect(avviso).toHaveBeenCalledWith('4 allegati inviati a commercialista@esempio.it', 'success');
    expect(onInviato).toHaveBeenCalled();
  });

  it('un errore del server resta nel modale e non chiude niente', async () => {
    await apri();
    api.post.mockRejectedValue({ response: { data: { detail: 'Invio email non riuscito (SMTPAuthenticationError)' } } });
    fireEvent.click(screen.getByTestId('invia-selezionati'));
    fireEvent.click(await screen.findByTestId('conferma-invio-pacchetto'));
    expect(await screen.findByRole('alert')).toHaveTextContent('SMTPAuthenticationError');
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('presenze gia inviate: «Già inviato», mai rimandate in silenzio, «Rinvia» chiede conferma', async () => {
    const dati = pacchetto();
    dati.voci[4] = voce('presenze', 'Presenze (HR)', 'gia_inviato', {
      conteggio: 1, motivo: 'Già inviato il 25/09/2026',
      ultimo_invio: { data: '2026-09-25T10:00:00+00:00', destinatario: 'commercialista@esempio.it' },
    });
    await apri(dati);
    expect(screen.getByTestId('stato-presenze')).toHaveTextContent('Già inviato');
    // non e' spuntata e non c'e' il chip: c'e' solo «Rinvia»
    expect(screen.queryByTestId('includi-presenze')).toBeNull();
    expect(screen.getByTestId('invia-selezionati')).toHaveTextContent('Invia selezionati (3)');

    fireEvent.click(screen.getByTestId('rinvia-presenze'));
    expect(screen.getByRole('alert')).toHaveTextContent('Le presenze risultano già inviate');
    expect(screen.getByTestId('invia-selezionati')).toHaveTextContent('Invia selezionati (3)');
    fireEvent.click(screen.getByRole('button', { name: 'Sì, rinvia' }));
    expect(screen.getByTestId('includi-presenze')).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByTestId('invia-selezionati')).toHaveTextContent('Invia selezionati (4)');

    api.post.mockResolvedValue({ data: { success: true, esiti: [] } });
    fireEvent.click(screen.getByTestId('invia-selezionati'));
    fireEvent.click(await screen.findByTestId('conferma-invio-pacchetto'));
    await waitFor(() => expect(api.post).toHaveBeenCalled());
    expect(api.post.mock.calls[0][1].presenze_rinvia).toBe(true);
  });

  it('anteprima: le prime righe del documento, prima di inviare', async () => {
    await apri();
    api.get.mockResolvedValueOnce({
      data: {
        sezioni: [{ titolo: '', colonne: ['Data', 'Causale', 'Entrate'],
          righe: Array.from({ length: 10 }, (_, i) => [`0${i}/09/2026`, `Incasso ${i}`, '', '10,00']) }],
      },
    });
    fireEvent.click(screen.getByTestId('anteprima-prima_nota_cassa'));
    const dettaglio = await screen.findByTestId('dettaglio-prima_nota_cassa');
    expect(api.get).toHaveBeenLastCalledWith('/api/commercialista/voce/prima_nota_cassa?dal=2026-09-01&al=2026-09-30');
    expect(dettaglio).toHaveTextContent('00/09/2026 · Incasso 0 · 10,00');
    expect(dettaglio).toHaveTextContent('e altre 2 righe nel PDF');
    fireEvent.click(screen.getByTestId('anteprima-prima_nota_cassa'));
    expect(screen.queryByTestId('dettaglio-prima_nota_cassa')).toBeNull();
  });

  it('senza email configurata l\'invio e\' spento e lo dice', async () => {
    api.get.mockResolvedValue({ data: pacchetto() });
    render(<PacchettoDaInviare periodo={periodo} carnetIds={[]} config={{ email: 'a@b.it', smtp_configured: false }} />);
    await screen.findByTestId('voce-prima_nota_cassa');
    expect(screen.getByTestId('invia-selezionati')).toBeDisabled();
    expect(screen.getByRole('alert')).toHaveTextContent('Email non configurata');
  });
});
