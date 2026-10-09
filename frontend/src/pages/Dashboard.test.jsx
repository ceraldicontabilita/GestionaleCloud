import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

import { DATO_NON_DISPONIBILE, statoIva } from './Dashboard';


describe('Dashboard con fonti atomiche', () => {
  it('espone la copertura dei corrispettivi e la proiezione SumUp live', () => {
    const source = readFileSync(resolve(process.cwd(), 'src/pages/Dashboard.jsx'), 'utf8');
    expect(source).toContain('copertura_corrispettivi');
    expect(source).toContain('sumup_cassa_live');
    expect(source).toContain('senza riscrivere la prova sorgente');
  });

  it('IVA senza saldo calcolabile e «Dato non disponibile», non 0,00', () => {
    expect(statoIva(null, null)).toEqual({ tipo: 'non_disponibile', valore: null });
    expect(statoIva(0, 0)).toEqual({ tipo: 'zero', valore: 0 });
    expect(statoIva(120, 0)).toEqual({ tipo: 'da_versare', valore: 120 });
    expect(statoIva(0, 45)).toEqual({ tipo: 'a_credito', valore: 45 });
    const source = readFileSync(resolve(process.cwd(), 'src/pages/Dashboard.jsx'), 'utf8');
    expect(source).toContain("cardIva.tipo === 'non_disponibile'");
    expect(source).not.toContain("valore == null ? '—'");
  });

  it('dichiara personale e contributi mancanti invece di mostrare zero', () => {
    const source = readFileSync(resolve(process.cwd(), 'src/pages/Dashboard.jsx'), 'utf8');
    expect(source).toContain('costi.personale == null');
    expect(source).toContain('Contributi a carico dell');
    expect(DATO_NON_DISPONIBILE).toBe('Dato non disponibile');
  });

  it('filtra sempre le scadenze con l anno globale selezionato', () => {
    const source = readFileSync(resolve(process.cwd(), 'src/pages/Dashboard.jsx'), 'utf8');
    expect(source).toContain('/api/scadenze?anno=${anno}');
    expect(source).not.toContain('/api/scadenze/prossime?');
  });
});
