import { describe, expect, it } from 'vitest';

import { imponibileItem, ivaItem } from './Corrispettivi';

describe('Compatibilita IVA corrispettivi storici', () => {
  it('riconosce il vecchio totale_iva che conteneva in realta imponibile', () => {
    const storico = { totale: 1851.71, totale_iva: 1683.37 };

    expect(imponibileItem(storico)).toBe(1683.37);
    expect(ivaItem(storico)).toBeCloseTo(168.34, 2);
  });

  it('mantiene separati imponibile e IVA nei record canonici', () => {
    const canonico = {
      totale: 110,
      totale_imponibile: 100,
      totale_iva: 10,
    };

    expect(imponibileItem(canonico)).toBe(100);
    expect(ivaItem(canonico)).toBe(10);
  });

  it('non riclassifica una vera IVA priva di imponibile', () => {
    const parziale = { totale: 110, totale_iva: 10 };

    expect(imponibileItem(parziale)).toBe(0);
    expect(ivaItem(parziale)).toBe(10);
  });
});
