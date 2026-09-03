import React from 'react';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import api from '../api';
import {
  CartaNexi,
  CartaSumUp,
  BadgeCategoria,
  FattureAtteseNelRegistroBanca,
  MovimentoModal,
  Provvisori,
  etichettaTabProvvisori,
  filtraFattureProvvisorie,
  filtraMovimentiPrimaNota,
  eCategoriaStorica,
  nomeFornitoreMovimento,
  normalizzaDescrizioneMovimento,
} from './PrimaNota';

vi.mock('../api', () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn() },
}));

const rispostaVuota = {
  data: { verifica: { addebiti_trovati: 0, dettagli: [] } },
};

describe('Conto SumUp separato dalla Banca', () => {
  it('mostra tutti gli accrediti ricevuti raggruppati per giornata', () => {
    render(<CartaSumUp
      anno={2026}
      dati={{
        totale_ricevuto: 934.20,
        totale_netto_vendite: 116.90,
        credito_sumup_aperto: 116.90,
        saldo_mastercard: 934.20,
        numero_payout: 3,
        giornate_vendite: [
          { data: '2026-08-11', vendite: 116.90, rimborsi: 0, netto: 116.90, transazioni: 2 },
        ],
        giorni: [
          { data: '2026-08-10', importo: 834.20, numero_payout: 2, payout_ids: ['PID1', 'PID2'] },
          { data: '2026-08-09', importo: 100, numero_payout: 1, payout_ids: ['PID3'] },
        ],
      }}
    />);

    expect(screen.getByRole('heading', { name: 'Accrediti giornalieri Mastercard SumUp' })).toBeInTheDocument();
    expect(screen.getByText('PID1, PID2')).toBeInTheDocument();
    expect(screen.getByText('PID3')).toBeInTheDocument();
    expect(screen.getByText('€ 834,20')).toBeInTheDocument();
    expect(screen.getByText('€ 100,00')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Vendite SumUp acquisite' })).toBeInTheDocument();
    expect(screen.getByText('11-08-2026')).toBeInTheDocument();
    expect(screen.getAllByText('€ 116,90').length).toBeGreaterThan(0);
  });

  it('non contiene piu il pannello di dettaglio entrate e la differenza POS fuorviante', () => {
    const source = readFileSync(resolve(process.cwd(), 'src/pages/PrimaNota.jsx'), 'utf8');
    expect(source).not.toContain('Dettaglio entrate');
    expect(source).not.toContain('Credito POS ancora da incassare / differenza temporale');
  });

  it('non offre creazione o spostamento diretto di righe nel registro Banca', () => {
    const source = readFileSync(resolve(process.cwd(), 'src/pages/PrimaNota.jsx'), 'utf8');
    expect(source).not.toContain('/api/prima-nota/sposta-movimento');
    expect(source).toContain("{tipo === 'cassa' && (");
  });

  it('rende non modificabile la proiezione live SumUp', () => {
    const source = readFileSync(resolve(process.cwd(), 'src/pages/PrimaNota.jsx'), 'utf8');
    expect(source).toContain('mov.non_modificabile');
    expect(source).toContain('Dato live');
  });
});

describe('Icone categorie Prima Nota', () => {
  it('rende le categorie Banca e Cassa senza errori runtime', () => {
    render(<>
      <BadgeCategoria categoria="Versamento Banca" />
      <BadgeCategoria categoria="Pagamento in Cassa" />
    </>);
    expect(screen.getByText('Versamento Banca')).toBeInTheDocument();
    expect(screen.getByText('Pagamento in Cassa')).toBeInTheDocument();
  });

  it('non presenta il credito SumUp come un versamento in banca', () => {
    render(<BadgeCategoria categoria="POS SUMUP Verso Banca" />);
    expect(screen.getByText('POS SUMUP → credito gestore')).toBeInTheDocument();
  });

  it('segnala un credito SumUp negativo senza compensarlo', () => {
    render(<CartaSumUp anno={2026} dati={{ credito_sumup_aperto: -12.34 }} />);
    expect(screen.getByRole('alert')).toHaveTextContent('12,34');
    expect(screen.getByRole('alert')).toHaveTextContent('non compensa automaticamente');
  });
});

describe('Carta Nexi e anno globale', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockResolvedValue(rispostaVuota);
  });

  it('passa sempre l’anno globale al backend e ricarica quando cambia', async () => {
    const { rerender } = render(<CartaNexi anno={2025} />);
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/nexi/stato?anno=2025'));

    rerender(<CartaNexi anno={2026} />);
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/nexi/stato?anno=2026'));
    expect(api.get).toHaveBeenCalledTimes(2);
  });

  it('ignora la risposta lenta dell’anno precedente', async () => {
    let completa2025;
    let completa2026;
    api.get.mockImplementation(url => new Promise(resolve => {
      if (url.endsWith('2025')) completa2025 = resolve;
      else completa2026 = resolve;
    }));

    const { rerender } = render(<CartaNexi anno={2025} />);
    await waitFor(() => expect(completa2025).toBeTypeOf('function'));
    rerender(<CartaNexi anno={2026} />);
    await waitFor(() => expect(completa2026).toBeTypeOf('function'));

    completa2026({ data: { verifica: {
      addebiti_trovati: 1,
      dettagli: [{ periodo: '2026-01', data_addebito: '2026-02-16', importo: 10, stato: 'estratto_mancante' }],
    } } });
    expect(await screen.findByText(/periodo 2026-01/)).toBeInTheDocument();

    completa2025({ data: { verifica: {
      addebiti_trovati: 1,
      dettagli: [{ periodo: '2025-01', data_addebito: '2025-02-16', importo: 20, stato: 'estratto_mancante' }],
    } } });
    await waitFor(() => expect(screen.queryByText(/periodo 2025-01/)).not.toBeInTheDocument());
    expect(screen.getByText(/periodo 2026-01/)).toBeInTheDocument();
  });
});

describe('Numero assegno in Prima Nota Banca', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.put.mockResolvedValue({ data: { message: 'salvato' } });
  });

  it('mostra, modifica e salva il numero assegno sulla riga banca', async () => {
    const onSaved = vi.fn();
    render(<MovimentoModal
      tipo="banca"
      movimento={{
        id: 'mov-1', data: '2026-05-31', tipo: 'uscita', importo: 1098.28,
        descrizione: 'Fattura fornitore', categoria: 'Fatture', assegno_numero: '208769300',
      }}
      onClose={vi.fn()}
      onSaved={onSaved}
    />);

    const numero = screen.getByLabelText('Numero assegno');
    expect(numero).toHaveValue('208769300');
    fireEvent.change(numero, { target: { value: '208769333' } });
    fireEvent.click(screen.getByRole('button', { name: '💾 Salva' }));

    await waitFor(() => expect(api.put).toHaveBeenCalledWith(
      '/api/prima-nota/banca/mov-1',
      expect.objectContaining({ numero_assegno: '208769333', importo: 1098.28 }),
    ));
    expect(onSaved).toHaveBeenCalledTimes(1);
  });
});

describe('Filtri distinti della Prima Nota', () => {
  const movimenti = [
    {
      id: 'm1', data: '2026-03-31', categoria: 'Fatture',
      numero_fattura: 'V1-8016',
      descrizione: 'Pagamento fattura V1-8016 - G.I.A.L. Generale Ingrosso Alimentare S.R.L.',
      importo: 1053.88,
    },
    {
      id: 'm2', data: '2026-03-27', categoria: 'Fatture',
      numero_fattura: '217AX8F01404', fornitore: 'San Carlo Gruppo Alimentare S.P.A',
      descrizione: 'Pagamento fattura 217AX8F01404 - San Carlo Gruppo Alimentare S.P.A',
      importo: 33.79,
    },
  ];

  it('ricava il fornitore anche dalle descrizioni storiche', () => {
    expect(nomeFornitoreMovimento(movimenti[0])).toBe('G.I.A.L. Generale Ingrosso Alimentare S.R.L.');
  });

  it('combina numero fattura, data e fornitore senza confonderli', () => {
    expect(filtraMovimentiPrimaNota(movimenti, {
      numeroFattura: '01404', data: '2026-03-27', fornitore: 'san carlo',
    })).toEqual([movimenti[1]]);
    expect(filtraMovimentiPrimaNota(movimenti, {
      numeroFattura: '01404', data: '2026-03-31', fornitore: 'san carlo',
    })).toEqual([]);
  });

  it('applica gli stessi filtri alle fatture provvisorie', () => {
    const provvisori = movimenti.map(m => ({
      fattura_id: m.id,
      fattura_numero: m.numero_fattura,
      fattura_data: m.data,
      fornitore: nomeFornitoreMovimento(m),
    }));
    expect(filtraFattureProvvisorie(provvisori, {
      numeroFattura: 'V1', data: '2026-03-31', fornitore: 'g.i.a.l',
    })).toEqual([provvisori[0]]);
  });
});

describe('Fatture provvisorie in attesa banca', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('sposta in attesa banca senza chiamare la conferma di pagamento', async () => {
    api.post.mockResolvedValue({
      data: {
        message: 'Fattura spostata tra i pagamenti attesi in banca.',
      },
    });
    const onRicarica = vi.fn().mockResolvedValue(undefined);
    render(<Provvisori
      provvisori={[{
        fattura_id: 'fatt-1', fattura_numero: '120', fattura_data: '2026-07-28',
        fornitore: 'Fornitore Test', importo: 306.15, suggerimento: 'sospesa',
      }]}
      attesaBanca={[]}
      onRicarica={onRicarica}
    />);

    fireEvent.click(screen.getByRole('button', { name: '🏦 Attendi banca' }));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/prima-nota/provvisori/attendi-banca',
      { fattura_id: 'fatt-1' },
    ));
    expect(api.post).not.toHaveBeenCalledWith(
      '/api/prima-nota/provvisori/conferma',
      expect.objectContaining({ metodo: 'banca' }),
    );
    expect(await screen.findByRole('status')).toHaveTextContent('pagamenti attesi in banca');
    expect(onRicarica).toHaveBeenCalledTimes(1);
  });

  it('separa nel contatore le decisioni dai pagamenti gia in attesa banca', () => {
    expect(etichettaTabProvvisori([{}, {}], [{}, {}, {}])).toBe(
      '⚠️ Da decidere (2) · 🏦 Attesa banca (3)',
    );
  });

  it('compatta soltanto descrizioni duplicate parola per parola', () => {
    const descrizione = 'BONIF. VS. FAVORE - BON.DA CERALDI BONIF. VS. FAVORE - BON.DA CERALDI';
    expect(normalizzaDescrizioneMovimento(descrizione)).toBe(
      'BONIF. VS. FAVORE - BON.DA CERALDI',
    );
    expect(normalizzaDescrizioneMovimento('Bonifico fornitore non duplicato'))
      .toBe('Bonifico fornitore non duplicato');
  });

  it('riconosce le categorie numeriche legacy senza confonderle con quelle operative', () => {
    expect(eCategoriaStorica('5331')).toBe(true);
    expect(eCategoriaStorica('5814')).toBe(true);
    expect(eCategoriaStorica('F24')).toBe(false);
  });

  it('pagina la coda da decidere quando contiene centinaia di documenti', () => {
    const provvisori = Array.from({ length: 51 }, (_, indice) => ({
      fattura_id: `fatt-${indice}`,
      fattura_numero: `F-${indice}`,
      fattura_data: '2026-06-01',
      fornitore: 'Fornitore Test',
      importo: 10,
      suggerimento: 'sospesa',
    }));
    render(<Provvisori
      provvisori={provvisori}
      attesaBanca={[]}
      onRicarica={vi.fn().mockResolvedValue(undefined)}
    />);

    expect(screen.getByTestId('paginazione-da-decidere')).toHaveTextContent('Documenti da associare: 51');
    expect(screen.getByText('Pagina 1/2')).toBeInTheDocument();
    expect(screen.queryByText(/Fatt. F-50 del/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Pagina da decidere successiva' }));

    expect(screen.getByText('Pagina 2/2')).toBeInTheDocument();
    expect(screen.getByText(/Fatt. F-50 del/)).toBeInTheDocument();
  }, 15000);

  it('mostra nel registro Banca le fatture attese del mese selezionato', () => {
    render(<FattureAtteseNelRegistroBanca
      fatture={[
        { fattura_id: 'gen', fattura_numero: 'G-1', fattura_data: '2026-01-10', fornitore: 'Gennaio SRL', importo: 100 },
        { fattura_id: 'mag', fattura_numero: 'M-1', fattura_data: '2026-05-12', fornitore: 'Maggio SRL', importo: 200 },
      ]}
      mese={4}
      onGestisci={vi.fn()}
    />);

    expect(screen.getByText(/Fatture attese in banca: 1/)).toBeInTheDocument();
    expect(screen.getByText(/Maggio SRL/)).toBeInTheDocument();
    expect(screen.queryByText(/Gennaio SRL/)).not.toBeInTheDocument();
  });

  it('permette di correggere una fattura in attesa banca riportandola da decidere', async () => {
    api.post.mockResolvedValue({
      data: {
        fattura: {
          id: 'fatt-attesa', numero: '55', data: '2026-06-19',
          fornitore: 'Fornitore Test', importo: 334.16,
        },
        message: 'Fattura 55 di Fornitore Test, del 2026-06-19, EUR 334,16, riportata in Da decidere.',
      },
    });
    const onRicarica = vi.fn().mockResolvedValue(undefined);
    render(<Provvisori
      provvisori={[]}
      attesaBanca={[{
        fattura_id: 'fatt-attesa', fattura_numero: '55', fattura_data: '2026-06-19',
        fornitore: 'Fornitore Test', importo: 334.16, suggerimento: 'banca',
      }]}
      onRicarica={onRicarica}
    />);

    fireEvent.click(screen.getByRole('button', { name: /Da decidere/i }));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/prima-nota/provvisori/da-decidere',
      { fattura_id: 'fatt-attesa' },
    ));
    const esito = await screen.findByRole('status');
    expect(esito).toHaveTextContent('Fattura 55');
    expect(esito).toHaveTextContent('Fornitore Test');
    expect(esito).toHaveTextContent('2026-06-19');
    expect(esito).toHaveTextContent('EUR 334,16');
    expect(onRicarica).toHaveBeenCalledTimes(1);
  });

  it('mostra la quadratura completa delle fatture senza duplicare quelle gia registrate', () => {
    render(<Provvisori
      provvisori={[]}
      attesaBanca={[]}
      completezza={{
        anno: 2026,
        fatture_attive_positive: 745,
        gia_registrate_pagamento_completo: 451,
        aperte_prima_delle_esclusioni: 294,
        escluse_cassa_banca: 2,
        aperte_mostrate: 292,
      }}
      onRicarica={vi.fn()}
    />);

    const riepilogo = screen.getByTestId('completezza-fatture-provvisorie');
    expect(riepilogo).toHaveTextContent("745 fatture dell'anno con importo positivo");
    expect(riepilogo).toHaveTextContent('451 gia registrate/pagate');
    expect(riepilogo).toHaveTextContent('292 aperte mostrate qui');
    expect(riepilogo).toHaveTextContent('2 escluse dal flusso Cassa/Banca');
  });

  it('registra in Cassa la conferma esplicita della singola fattura', async () => {
    api.post.mockResolvedValue({ data: { success: true } });
    const onRicarica = vi.fn().mockResolvedValue(undefined);
    render(<Provvisori
      provvisori={[{
        fattura_id: 'fatt-cassa', fattura_numero: '120', fattura_data: '2026-07-28',
        fornitore: 'Fornitore Test', importo: 306.15, suggerimento: 'sospesa',
      }]}
      attesaBanca={[]}
      onRicarica={onRicarica}
    />);

    fireEvent.click(screen.getByRole('button', { name: /Cassa$/i }));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/prima-nota/provvisori/conferma',
      {
        fattura_id: 'fatt-cassa',
        metodo: 'cassa',
        approva_metodo_fattura: true,
      },
    ));
    expect(onRicarica).toHaveBeenCalledTimes(1);
    expect(onRicarica).toHaveBeenCalledWith({ silent: true });
  });

  it('in selezione veloce assegna metodi diversi senza smontare filtri e lista', async () => {
    api.post.mockResolvedValue({ data: { success: true, message: 'Aggiornata' } });
    const onRicarica = vi.fn().mockResolvedValue(undefined);
    render(<Provvisori
      provvisori={[
        { fattura_id: 'cassa-1', fattura_numero: 'C1', fattura_data: '2026-08-01', fornitore: 'Carta Party', importo: 100 },
        { fattura_id: 'banca-1', fattura_numero: 'B1', fattura_data: '2026-08-02', fornitore: 'Europa', importo: 200 },
      ]}
      attesaBanca={[]}
      onRicarica={onRicarica}
    />);

    fireEvent.click(screen.getByLabelText('Attiva selezione veloce'));
    fireEvent.change(screen.getByPlaceholderText('Es. San Carlo'), {
      target: { value: 'Carta' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Cassa$/i }));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/prima-nota/provvisori/conferma',
      { fattura_id: 'cassa-1', metodo: 'cassa', approva_metodo_fattura: true },
    ));
    expect(onRicarica).toHaveBeenCalledWith({ silent: true });
    expect(screen.getByPlaceholderText('Es. San Carlo')).toHaveValue('Carta');
  });

  it('registra la quota Cassa e lascia il residuo alla riconciliazione bancaria', async () => {
    api.post.mockResolvedValue({
      data: { message: 'Quota Cassa registrata; residuo in attesa della banca.' },
    });
    const onRicarica = vi.fn().mockResolvedValue(undefined);
    render(<Provvisori
      provvisori={[{
        fattura_id: 'fatt-parziale', fattura_numero: '122', fattura_data: '2026-07-30',
        fornitore: 'Fornitore Parziale', importo: 100, suggerimento: 'sospesa',
      }]}
      attesaBanca={[]}
      onRicarica={onRicarica}
    />);

    fireEvent.click(screen.getByRole('button', { name: /Parziale/i }));
    fireEvent.change(screen.getByLabelText('Quota pagata in contanti'), {
      target: { value: '40,00' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Conferma' }));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/prima-nota/provvisori/conferma-divisione',
      {
        fattura_id: 'fatt-parziale',
        importo_cassa: 40,
        importo_banca: 60,
      },
    ));
    expect(api.post).not.toHaveBeenCalledWith(
      '/api/pagamenti/registra',
      expect.anything(),
    );
    expect(await screen.findByRole('status')).toHaveTextContent('residuo in attesa');
    expect(onRicarica).toHaveBeenCalledTimes(1);
  });

  it('mostra sulla fattura l errore restituito dal backend', async () => {
    api.post.mockRejectedValue({ response: { data: { detail: 'Pagamento non registrato' } } });
    render(<Provvisori
      provvisori={[{
        fattura_id: 'fatt-errore', fattura_numero: '121', fattura_data: '2026-07-29',
        fornitore: 'Fornitore Errore', importo: 100, suggerimento: 'sospesa',
      }]}
      attesaBanca={[]}
      onRicarica={vi.fn()}
    />);

    fireEvent.click(screen.getByRole('button', { name: /Cassa$/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Pagamento non registrato');
  });

  it('permette di associare a mano ma mai di forzare un pagamento inventato', async () => {
    // La riga era di sola lettura: si poteva solo guardare la fattura, che si
    // vede gia' nella pagina Fatture. Ora si puo' scegliere il movimento vero.
    // Resta vietato quello che era vietato prima: registrare un pagamento
    // senza un addebito reale in estratto conto.
    api.get.mockResolvedValue({ data: { fattura: {}, candidati: [], totale: 0 } });
    render(<Provvisori
      provvisori={[]}
      attesaBanca={[{
        fattura_id: 'fatt-2', fattura_numero: '121', fattura_data: '2026-07-29',
        fornitore: 'Fornitore Banca', importo: 100, fonte_metodo: 'operatore_prima_nota',
      }]}
      onRicarica={vi.fn()}
    />);

    expect(screen.queryByRole('button', { name: /Forza banca/i })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Associa a mano' }));

    // I candidati arrivano dall'estratto conto: nessuna riga inventata.
    await waitFor(() => expect(api.get).toHaveBeenCalledWith(
      '/api/prima-nota/banca/candidati-per-fattura?fattura_id=fatt-2'));
    expect(await screen.findByText(/Nessun movimento compatibile/)).toBeInTheDocument();
  });

  it('non espone un riprocessamento storico mutativo diretto', async () => {
    const onRicarica = vi.fn().mockResolvedValue(undefined);
    render(<Provvisori provvisori={[]} attesaBanca={[]} onRicarica={onRicarica} />);

    expect(screen.queryByRole('button', { name: 'Riprocessa estratto conto' })).not.toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('evidenzia un dubbio sul metodo senza creare un pagamento', async () => {
    api.post.mockResolvedValue({ data: {
      message: 'Anomalia aperta sulla fattura 2/761 di CERAMICHE MARA S.R.L.',
    } });
    const onRicarica = vi.fn().mockResolvedValue(undefined);
    render(<Provvisori
      provvisori={[{
        fattura_id: 'fatt-dubbia', fattura_numero: '2/761', fattura_data: '2026-03-02',
        fornitore: 'CERAMICHE MARA S.R.L.', importo: 464.23, suggerimento: 'sospesa',
      }]}
      attesaBanca={[]}
      onRicarica={onRicarica}
    />);

    fireEvent.click(screen.getByRole('button', { name: /Dubbio sul pagamento/i }));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/prima-nota/provvisori/segnala-dubbio',
      { fattura_id: 'fatt-dubbia' },
    ));
    expect(api.post).not.toHaveBeenCalledWith(
      '/api/prima-nota/provvisori/conferma', expect.anything(),
    );
    expect(await screen.findByRole('status')).toHaveTextContent('Anomalia aperta');
    expect(onRicarica).toHaveBeenCalledWith({ silent: true });
  });

  it('mostra e filtra il DDT collegato alla fattura', () => {
    render(<Provvisori
      provvisori={[{
        fattura_id: 'fatt-ddt', fattura_numero: 'FVL824', fattura_data: '2026-04-30',
        fornitore: '2M ITALIA S.R.L.', importo: 190,
        dati_ddt: [{ numero: 'DDT862', data: '2026-04-17', giorni_prima_fattura: 13 }],
      }]}
      attesaBanca={[]}
      onRicarica={vi.fn()}
    />);

    expect(screen.getByText(/DDT DDT862 del 17-04-2026 · 13 gg prima/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Filtra per numero DDT'), { target: { value: '999' } });
    expect(screen.getByText('Nessuna fattura provvisoria corrisponde ai filtri.')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Filtra per numero DDT'), { target: { value: '862' } });
    expect(screen.getByText(/FVL824/)).toBeInTheDocument();
  });

  it('ricostruisce il numero completo dell assegno dal finale 123-01', async () => {
    api.get.mockResolvedValue({ data: {
      candidati: [{
        assegno_id: 'ass-7', numero_completo: '0208770000-01', importo: 448.35,
        data: '2026-05-15', fonte_estratto_conto: true,
        movimento_estratto_conto_id: 'ec-7',
      }],
      message: 'Numero assegno completo trovato. Verifica e conferma il collegamento.',
    } });
    api.post.mockResolvedValue({ data: { message: 'Assegno 0208770000-01 collegato.' } });
    const onRicarica = vi.fn().mockResolvedValue(undefined);
    render(<Provvisori
      provvisori={[]}
      attesaBanca={[{
        fattura_id: 'fatt-ass', fattura_numero: '2600735/V', fattura_data: '2026-05-15',
        fornitore: 'GRUPPO MARTELLOZZO S.R.L.', importo: 448.35,
        fonte_metodo: 'assegno_compilato',
      }]}
      onRicarica={onRicarica}
    />);

    fireEvent.click(screen.getByRole('button', { name: /Associa assegno alla fattura 2600735\/V/ }));
    const frammento = await screen.findByLabelText('Finale assegno nel formato 123-01');
    fireEvent.change(frammento, { target: { value: '00001' } });
    expect(frammento).toHaveValue('000-01');
    fireEvent.click(screen.getByRole('button', { name: 'Cerca assegno' }));

    await waitFor(() => expect(api.get).toHaveBeenLastCalledWith(
      '/api/prima-nota/provvisori/assegni-proposti',
      { params: { fattura_id: 'fatt-ass', frammento: '000-01' } },
    ));
    expect(await screen.findByText(/Assegno 0208770000-01/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Collega 0208770000-01' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/prima-nota/provvisori/associa-assegno',
      expect.objectContaining({
        fattura_id: 'fatt-ass', assegno_id: 'ass-7',
        movimento_estratto_conto_id: 'ec-7', numero_completo: '0208770000-01',
      }),
    ));
  });

  it('propone il collegamento assegno anche per una fattura generica in attesa banca', async () => {
    api.get.mockResolvedValue({ data: { candidati: [], message: 'Inserisci il numero assegno.' } });
    render(<Provvisori
      provvisori={[]}
      attesaBanca={[{
        fattura_id: 'fatt-generica', fattura_numero: '88', fattura_data: '2026-08-08',
        fornitore: 'KIMBO S.P.A.', importo: 1498.96,
        fonte_metodo: 'operatore_prima_nota',
      }]}
      onRicarica={vi.fn()}
    />);

    fireEvent.click(screen.getByRole('button', { name: 'Associa assegno alla fattura 88' }));

    await waitFor(() => expect(api.get).toHaveBeenCalledWith(
      '/api/prima-nota/provvisori/assegni-proposti',
      { params: { fattura_id: 'fatt-generica', frammento: '' } },
    ));
    expect(await screen.findByLabelText('Ultime 5 cifre e suffisso assegno')).toBeInTheDocument();
  });

  it('riconosce la RiBa bancaria e non propone un assegno', () => {
    render(<Provvisori
      provvisori={[]}
      attesaBanca={[{
        fattura_id: 'fatt-riba', fattura_numero: '0000202611306589',
        fattura_data: '2026-08-07', fornitore: 'Leasys Italia S.p.A.',
        importo: 1119.48,
        evidenza_banca: 'strumento_fornitore_importo_data',
        strumento_bancario: { codice: 'riba', label: 'RiBa' },
        motivo_sospensione: 'Importo al centesimo, ma due documenti sono candidati',
        movimento_banca: {
          id: 'ec-riba', data: '2026-08-08',
          descrizione: 'RIB LEASYS ITALIA SPA FATTURA 0000202611306589',
        },
      }]}
      onRicarica={vi.fn()}
    />);

    expect(screen.getByText(/RiBa identificata nell'estratto conto/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Associa assegno/ })).not.toBeInTheDocument();
    expect(screen.getByText(/Importo al centesimo, ma due documenti/)).toBeInTheDocument();
  });

  it('per una fattura banca senza strumento identificato espone Abbina assegno', () => {
    render(<Provvisori
      provvisori={[]}
      attesaBanca={[{
        fattura_id: 'fatt-generica', fattura_numero: '0070021988',
        fattura_data: '2026-06-29', fornitore: 'KIMBO S.P.A.',
        importo: 1498.96,
      }]}
      onRicarica={vi.fn()}
    />);

    expect(screen.getByRole('button', {
      name: /Associa assegno alla fattura 0070021988/,
    })).toHaveTextContent('Abbina assegno');
  });
});

describe('Conferma multipla delle provvisorie', () => {
  beforeEach(() => vi.clearAllMocks());

  const due = [
    { fattura_id: 'f1', fattura_numero: '10', fattura_data: '2026-08-01',
      fornitore: 'Kimbo', importo: 100 },
    { fattura_id: 'f2', fattura_numero: '11', fattura_data: '2026-08-02',
      fornitore: 'Saima', importo: 50 },
  ];

  it('spunta piu fatture e le registra in Cassa con UNA chiamata', async () => {
    api.post.mockResolvedValue({ data: {
      success: true, riuscite: 2, scartate: 0, esiti: [],
      message: '2 fatture registrate',
    } });
    const onRicarica = vi.fn().mockResolvedValue(undefined);
    render(<Provvisori provvisori={due} attesaBanca={[]} onRicarica={onRicarica} />);

    fireEvent.click(screen.getByLabelText('Seleziona fattura 10'));
    fireEvent.click(screen.getByLabelText('Seleziona fattura 11'));
    fireEvent.click(screen.getByRole('button', { name: /Registra in Cassa \(2\)/ }));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/prima-nota/provvisori/conferma-multipla',
      { fattura_ids: ['f1', 'f2'], metodo: 'cassa' },
    ));
    expect(api.post).toHaveBeenCalledTimes(1);   // UNA chiamata, non una per fattura
    expect(onRicarica).toHaveBeenCalledTimes(1); // UNA ricarica: era la lentezza
    expect(await screen.findByRole('status')).toHaveTextContent('2 fatture registrate');
  });

  it('seleziona tutte e le sposta in attesa banca', async () => {
    api.post.mockResolvedValue({ data: {
      success: true, riuscite: 2, scartate: 0, esiti: [], message: '2 fatture registrate',
    } });
    render(<Provvisori provvisori={due} attesaBanca={[]}
      onRicarica={vi.fn().mockResolvedValue(undefined)} />);

    fireEvent.click(screen.getByLabelText('Seleziona tutte le fatture visibili'));
    fireEvent.click(screen.getByRole('button', { name: /Attendi banca \(2\)/ }));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/prima-nota/provvisori/conferma-multipla',
      { fattura_ids: ['f1', 'f2'], metodo: 'attendi_banca' },
    ));
  });

  it('una fattura scartata resta selezionata e il motivo si legge', async () => {
    api.post.mockResolvedValue({ data: {
      success: false, riuscite: 1, scartate: 1,
      esiti: [
        { fattura_id: 'f1', success: true },
        { fattura_id: 'f2', success: false, detail: 'La fattura ha gia un pagamento contabile completo.' },
      ],
      message: '1 fatture registrate, 1 scartate (vedi dettaglio)',
    } });
    render(<Provvisori provvisori={due} attesaBanca={[]}
      onRicarica={vi.fn().mockResolvedValue(undefined)} />);

    fireEvent.click(screen.getByLabelText('Seleziona tutte le fatture visibili'));
    fireEvent.click(screen.getByRole('button', { name: /Registra in Cassa \(2\)/ }));

    expect(await screen.findByRole('status')).toHaveTextContent('1 scartate');
    expect(screen.getByText(/pagamento contabile completo/)).toBeInTheDocument();
  });

  it('cambiando filtro non invia fatture diventate invisibili', async () => {
    api.post.mockResolvedValue({ data: {
      success: true, riuscite: 1, scartate: 0, esiti: [], message: '1 fattura registrata',
    } });
    render(<Provvisori provvisori={due} attesaBanca={[]}
      onRicarica={vi.fn().mockResolvedValue(undefined)} />);

    fireEvent.click(screen.getByLabelText('Seleziona tutte le fatture visibili'));
    fireEvent.change(screen.getByLabelText('Filtra per nome fornitore'), {
      target: { value: 'Kimbo' },
    });
    await waitFor(() => expect(screen.getByText(/1 selezionate/)).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /Registra in Cassa \(1\)/ }));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/prima-nota/provvisori/conferma-multipla',
      { fattura_ids: ['f1'], metodo: 'cassa' },
    ));
  });
});

describe('Registro completo fatture in Prima Nota', () => {
  it('mantiene visibili pagate e aperte, espone DDT e pagina oltre cento righe', () => {
    const tutteFatture = Array.from({ length: 101 }, (_, indice) => ({
      fattura_id: `fatt-${indice + 1}`,
      fattura_numero: `N-${indice + 1}`,
      fattura_data: '2026-06-29',
      fornitore: indice === 0 ? 'KIMBO S.P.A.' : `FORNITORE ${indice + 1}`,
      totale_fattura: 10 + indice,
      importo_residuo: indice === 0 ? 0 : 10 + indice,
      stato: indice === 0 ? 'registrata_banca' : 'da_decidere',
      stato_label: indice === 0 ? 'Registrata in Banca' : 'Da decidere',
      stato_ddt: indice === 0 ? 'presente' : 'non_indicato_nell_xml',
      dati_ddt: indice === 0
        ? [{ numero: '5010118184', data: '2026-06-29', giorni_prima_fattura: 0 }]
        : [],
      richiede_azione: indice !== 0,
      movimenti_prima_nota: indice === 0
        ? [{ id: 'pn-1', posizione: 'banca', data: '2026-06-30', importo: 10 }]
        : [],
    }));

    render(<Provvisori
      provvisori={tutteFatture.slice(1)}
      attesaBanca={[]}
      tutteFatture={tutteFatture}
      completezza={{
        anno: 2026, fatture_attive_positive: 101,
        gia_registrate_pagamento_completo: 1, aperte_mostrate: 100,
        escluse_cassa_banca: 0,
      }}
      onRicarica={vi.fn().mockResolvedValue(undefined)}
    />);

    fireEvent.click(screen.getByRole('tab', { name: 'Tutte le fatture (101)' }));
    expect(screen.getByText('Registrata in Banca')).toBeInTheDocument();
    expect(screen.getByText(/DDT 5010118184 del/)).toBeInTheDocument();
    expect(screen.getByText('Pagina 1/2')).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('Pagina fatture successiva'));
    expect(screen.getByText('Pagina 2/2')).toBeInTheDocument();
    expect(screen.getByText(/Fatt. N-101 del/)).toBeInTheDocument();
  });
});

describe('Deep link tra sezioni contabili', () => {
  it('trova il movimento anche tramite id della prova bancaria', () => {
    const movimenti = [{
      id: 'PN-BARBETTA',
      movimento_estratto_conto_id: 'EC-2026-08-07-23.10-d2ef4678',
      descrizione: 'Pagamento fattura Barbetta',
      importo: 23.10,
    }];

    expect(filtraMovimentiPrimaNota(movimenti, {
      testo: 'EC-2026-08-07-23.10-d2ef4678',
    })).toHaveLength(1);
  });
});
