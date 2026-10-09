import { describe, expect, it } from 'vitest';
import { descriviScontrino, statoCorrispettivo } from './FattureEmesse';

describe('FattureEmesse', () => {
  it('lo stato del corrispettivo ha sempre un testo, non solo un colore', () => {
    expect(statoCorrispettivo({ corrispettivo: { stato: 'SODDISFATTO' } }).testo).toBe('Collegata');
    expect(statoCorrispettivo({ corrispettivo: { stato: 'DA_VERIFICARE' } }).testo).toBe('Da scegliere');
    expect(statoCorrispettivo({}).testo).toBe('Corrispettivo non arrivato');
  });

  it('dice da dove viene il giorno dello scontrino', () => {
    expect(descriviScontrino({ scontrino: { data: '2026-07-10', numero: '2586-0352', fonte: 'causale' } }))
      .toBe('Scontrino del 10/07/2026 n. 2586-0352');
    expect(descriviScontrino({ scontrino: { data: '2026-07-20', fonte: 'data_fattura' } }))
      .toBe('Scontrino del 20/07/2026 (data della fattura)');
    expect(descriviScontrino({})).toBe('Scontrino non indicato');
  });
});
