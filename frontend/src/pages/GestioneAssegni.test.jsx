import { describe, expect, it } from 'vitest';

import {
  assegnoInteramenteAssociato,
  filtraAssegni,
  normalizzaBeneficiarioAssegno,
  totaleQuoteFatture,
} from './GestioneAssegni';

const ASSEGNI = [
  { id: 'a1', numero: '208769333', importo: 1097.47, beneficiario: '-' },
  { id: 'a2', numero: '208770635', importo: 644.21, beneficiario: 'FORNITORE TEST' },
  { id: 'a3', numero: '0208771000-01', importo: null, beneficiario: null, stato: 'vuoto' },
];

describe('Filtri pagina assegni', () => {
  it('non tratta i segnaposto come un vero beneficiario', () => {
    expect(normalizzaBeneficiarioAssegno('-')).toBe('');
    expect(normalizzaBeneficiarioAssegno('N/A')).toBe('');
    expect(normalizzaBeneficiarioAssegno('FORNITORE TEST')).toBe('FORNITORE TEST');
  });

  it('filtra per importo esatto accettando il formato italiano', () => {
    expect(filtraAssegni(ASSEGNI, { importoEsatto: '1.097,47' }).map(a => a.id)).toEqual(['a1']);
  });

  it('mostra i fogli del carnet anche prima di inserire importo e beneficiario', () => {
    expect(filtraAssegni(ASSEGNI).map(a => a.id)).toContain('a3');
    expect(filtraAssegni(ASSEGNI, { importoMin: '1' }).map(a => a.id)).not.toContain('a3');
  });

  it('inizia a filtrare il numero solo dopo tre cifre', () => {
    expect(filtraAssegni(ASSEGNI, { numeroAssegno: '20' })).toHaveLength(3);
    expect(filtraAssegni(ASSEGNI, { numeroAssegno: '933' }).map(a => a.id)).toEqual(['a1']);
  });
});

describe('Copertura assegno con fatture collegate', () => {
  it('considera completo l’assegno da 652,74 associato alla fattura da 652,74', () => {
    const collegate = [{ id: 'fattura-1', quota: 652.74 }];

    expect(totaleQuoteFatture(collegate)).toBeCloseTo(652.74, 2);
    expect(assegnoInteramenteAssociato(652.74, collegate)).toBe(true);
  });

  it('consente altre fatture soltanto finché resta un importo da coprire', () => {
    expect(assegnoInteramenteAssociato(652.74, [{ quota: 331.04 }])).toBe(false);
    expect(
      assegnoInteramenteAssociato(652.74, [{ quota: 331.04 }, { quota: 321.70 }])
    ).toBe(true);
  });
});
