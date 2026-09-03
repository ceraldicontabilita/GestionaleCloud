import React from 'react';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ScadenzeIvaMensili, giornoIT } from './IvaAuditSections';

const gestioneIva = readFileSync(resolve(process.cwd(), 'src/pages/GestioneIVA.jsx'), 'utf8');

describe('IVA: mesi con dati mancanti (PR 9)', () => {
  it('formatta le date in gg/mm/aaaa', () => {
    expect(giornoIT('2026-02-03')).toBe('03/02/2026');
    expect(giornoIT('')).toBe('');
  });

  it('un mese senza corrispettivi mostra "Dati mancanti" e i giorni senza chiusura RT, mai 0 €', () => {
    render(
      <ScadenzeIvaMensili
        anno={2026}
        loading={false}
        error={null}
        dati={{
          scadenze: [{
            mese: 2, mese_nome: 'Febbraio', stato: 'DATI_MANCANTI', attendibile: false,
            motivi: ['archivio_fatture_vuoto', 'nessun_corrispettivo_nel_mese', 'giorni_senza_corrispettivo'],
            giorni_senza_corrispettivo: ['2026-02-01', '2026-02-02'], giorni_mese: 28,
            data_scadenza: '2026-03-16', iva_debito: null, iva_credito: null, saldo: null, saldo_cents: null,
            fonte: 'stima',
          }],
          totale_a_credito: 0, totale_da_versare: 0, saldo_progressivo: 0,
        }}
      />,
    );
    const card = screen.getByTestId('iva-scadenza-mese-2');
    expect(card.textContent).toContain('Dati mancanti');
    expect(card.textContent).toContain('Archivio fatture vuoto');
    expect(card.textContent).toContain('Nessun corrispettivo del mese');
    expect(card.textContent).toContain('Giorni senza chiusura RT: 2 su 28 — 01/02/2026, 02/02/2026');
    expect(card.textContent).not.toContain('Stima');
    expect(card.textContent).not.toContain('€ 0,00');
  });

  it('la pagina IVA mostra l\'avviso con i giorni mancanti nel cruscotto mensile', () => {
    expect(gestioneIva).toContain("dashboard?.stato_liquidazione === 'DATI_MANCANTI'");
    expect(gestioneIva).toContain('data-testid="iva-dati-mancanti"');
    expect(gestioneIva).toContain('Giorni senza chiusura RT');
    expect(gestioneIva).toContain('dashboard.giorni_senza_corrispettivo.map(giornoIT)');
    expect(gestioneIva).toContain('Archivio fatture vuoto');
  });
});
