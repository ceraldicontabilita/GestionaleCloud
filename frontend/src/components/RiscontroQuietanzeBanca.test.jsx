import React from 'react';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../api', () => ({ default: { get: vi.fn() } }));

import api from '../api';
import RiscontroQuietanzeBanca from './RiscontroQuietanzeBanca';

const source = readFileSync(resolve(process.cwd(), 'src/components/RiscontroQuietanzeBanca.jsx'), 'utf8');
const riconciliazione = readFileSync(resolve(process.cwd(), 'src/pages/RiconciliazioneUnificata.jsx'), 'utf8');

const RISPOSTA = {
  copertura_banca: { dal: '2026-01-16', al: '2026-09-17' },
  conteggi: { fuori_periodo_estratto: 234 },
  riscontrati: [{
    chiave: 'p1', data: '2026-08-20', importo: 654.33, protocollo: '26082011065626134/000001',
    quietanze: [{ id: 'q1', pdf_url: '/api/originale/f24/q1', filename: 'q1.pdf' }],
    addebito: { movimento_id: 'm1', data: '2026-08-20', importo: 654.33 },
    motivazione: 'importo 654.33 EUR uguale al centesimo; DATA INCASSO nella causale: 20/08/2026',
    ravvedimento_di: [{ f24_id: 'orig', pdf_url: '/api/originale/f24/orig' }],
    inviato_il_it: '20/08/2026', programmato: false, tipo_versamento: 'ravvedimento', senza_modello: false,
  }],
  tributi_ripetuti: [{
    chiave: 'a||b', data: '2026-06-16', righe: '3918 2026 3574.00',
    motivazione: 'stesse righe (3918 2026 3574.00) in 2 deleghe versate il 16/06/2026',
    pagamenti: [
      { chiave: 'a', protocollo: '26060212304532735/000001', importo: 1969.1, inviato_il_it: '02/06/2026',
        programmato: true, tipo_versamento: 'ordinario', senza_modello: true,
        quietanze: [{ id: 'qa', pdf_url: '/api/originale/f24/qa' }],
        addebito: { movimento_id: 'ma', data: '2026-06-17', importo: 1969.1 } },
      { chiave: 'b', protocollo: '26061631545528157/000001', importo: 2179.1, inviato_il_it: '16/06/2026',
        programmato: false, tipo_versamento: 'ordinario', senza_modello: true,
        quietanze: [{ id: 'qb', pdf_url: '/api/originale/f24/qb' }],
        addebito: { movimento_id: 'mb', data: '2026-06-17', importo: 2179.1 } },
    ],
  }],
  da_verificare: [],
  addebiti_senza_quietanza: [{
    movimento_id: 'm9', data: '2026-09-17', importo: 9421.15,
    motivazione: 'quietanza da riscaricare dal Cassetto Fiscale',
  }],
  quietanze_senza_addebito: [],
  quietanze_incomplete: [],
};

describe('Quietanze F24 e addebiti in banca', () => {
  it('è montato nella scheda F24 e non usa colori vietati né emoji', () => {
    expect(riconciliazione.match(/<RiscontroQuietanzeBanca anno=\{anno\} \/>/g)).toHaveLength(2);
    expect(source).toContain('/api/f24-riconciliazione/quietanze-banca');
    expect(source).not.toMatch(/#(0f2744|2563eb|1e40af|dbeafe|4f46e5|7c3aed|64748b)/i);
    expect(source).not.toMatch(/[\u{1F300}-\u{1FAFF}]/u);
  });

  it("mostra esito a parole, motivazione e i link ai due documenti", async () => {
    api.get.mockResolvedValueOnce({ data: RISPOSTA });
    render(<MemoryRouter><RiscontroQuietanzeBanca anno={2026} /></MemoryRouter>);

    await waitFor(() => expect(screen.getByText('Riscontrato')).toBeTruthy());
    expect(api.get).toHaveBeenCalledWith('/api/f24-riconciliazione/quietanze-banca?anno=2026');
    expect(screen.getByText('Quietanza mancante')).toBeTruthy();
    expect(screen.getByText(/DATA INCASSO nella causale/)).toBeTruthy();
    expect(screen.getByTestId('apri-addebito-m1').getAttribute('href'))
      .toBe('/riconciliazione/banca?movimento=m1');
    expect(screen.getByTestId('apri-quietanza-riscontrati:p1')).toBeTruthy();
    expect(screen.getByText(/234 quietanze/)).toBeTruthy();
  });

  it("un pagamento di ravvedimento porta l'etichetta e apre l'F24 del commercialista", async () => {
    api.get.mockResolvedValueOnce({ data: RISPOSTA });
    render(<MemoryRouter><RiscontroQuietanzeBanca anno={2026} /></MemoryRouter>);

    await waitFor(() => expect(screen.getByTestId('ravvedimento-riscontrati:p1')).toBeTruthy());
    expect(screen.getByTestId('ravvedimento-riscontrati:p1').textContent).toBe('Ravvedimento');
    expect(screen.getByTestId('apri-originale-orig')).toBeTruthy();
    expect(screen.getAllByTestId('invio-delega')[0].textContent)
      .toContain('inviata il 20/08/2026 · non programmata · Ravvedimento');
  });

  it('una rata della dilazione INPS dice quale rata del piano paga', async () => {
    const rata = {
      ...RISPOSTA.riscontrati[0], chiave: 'r2', ravvedimento_di: [], tipo_versamento: 'regolarizzazione',
      inviato_il_it: '06/03/2026', programmato: true, senza_modello: true,
      dilazione_inps: { dilazione_id: 'dilazione_inps:INPS.5100.24/02/2026.0175250', rata: 2, di: 4 },
    };
    api.get.mockResolvedValueOnce({ data: { ...RISPOSTA, riscontrati: [rata] } });
    render(<MemoryRouter><RiscontroQuietanzeBanca anno={2026} /></MemoryRouter>);

    await waitFor(() => expect(screen.getAllByTestId('invio-delega').length).toBeGreaterThan(0));
    expect(screen.getAllByTestId('invio-delega')[0].textContent)
      .toBe('inviata il 06/03/2026 · programmata · Rata 2/4 dilazione INPS');
  });

  it('lo stesso tributo in due deleghe mostra entrambe, con invio e addebito', async () => {
    api.get.mockResolvedValueOnce({ data: RISPOSTA });
    render(<MemoryRouter><RiscontroQuietanzeBanca anno={2026} /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText('Versato due volte')).toBeTruthy());

    fireEvent.click(screen.getByTestId('filtro-tributi_ripetuti'));
    const invii = screen.getAllByTestId('invio-delega').map(e => e.textContent);
    expect(invii).toEqual([
      'inviata il 02/06/2026 · programmata · Ordinario · senza modello del commercialista',
      'inviata il 16/06/2026 · non programmata · Ordinario · senza modello del commercialista',
    ]);
    expect(screen.getByTestId('apri-addebito-ma')).toBeTruthy();
    expect(screen.getByTestId('apri-addebito-mb')).toBeTruthy();
  });

  it('il filtro mostra un gruppo solo, il più recente per primo', async () => {
    api.get.mockResolvedValueOnce({ data: RISPOSTA });
    render(<MemoryRouter><RiscontroQuietanzeBanca anno={2026} /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText('Riscontrato')).toBeTruthy());

    const esiti = screen.getAllByTestId(/^esito-/).map(e => e.textContent);
    expect(esiti).toEqual(['Quietanza mancante', 'Riscontrato', 'Versato due volte']);

    fireEvent.click(screen.getByTestId('filtro-riscontrati'));
    expect(screen.queryByText('Quietanza mancante')).toBeNull();
    expect(screen.getByText('Riscontrato')).toBeTruthy();
  });

  it('mostra il livello di ogni esito, la differenza e i periodi senza estratto', async () => {
    api.get.mockResolvedValueOnce({ data: {
      ...RISPOSTA,
      riscontrati: [],
      tributi_ripetuti: [],
      addebiti_senza_quietanza: [],
      da_verificare: [{
        chiave: 'p2', data: '2026-06-16', importo: 1000, livello: 'PARZIALE', differenza: 3,
        quietanze: [{ id: 'q2', filename: 'q2.pdf' }],
        addebito: { movimento_id: 'm2', data: '2026-06-16', importo: 1003 },
        motivazione: 'differenza +3.00 EUR: da verificare con il commercialista',
      }],
      quietanze_senza_estratto: [{
        chiave: 'p3', data: '2025-05-16', importo: 777, livello: 'NESSUN_MATCH',
        estratto_periodo_presente: false, quietanze: [{ id: 'q3', filename: 'q3.pdf' }],
        motivazione: 'estratto conto del periodo assente: non si puo\' dire se il pagamento manchi',
      }],
    } });
    render(<MemoryRouter><RiscontroQuietanzeBanca anno={2026} /></MemoryRouter>);

    await waitFor(() => expect(screen.getByText('Estratto assente')).toBeTruthy());
    expect(screen.getByTestId('livello-da_verificare:p2').textContent).toContain('Livello: Parziale');
    expect(screen.getByTestId('livello-da_verificare:p2').textContent).toContain('differenza');
    expect(screen.getByTestId('livello-quietanze_senza_estratto:p3').textContent)
      .toContain('Livello: Pagato, senza addebito in banca');
    expect(screen.getByTestId('filtro-quietanze_senza_estratto').textContent).toContain('(1)');
  });
});
