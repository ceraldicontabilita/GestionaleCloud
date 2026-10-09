import { describe, expect, it } from 'vitest';
import { totaleAltriCosti } from './VeicoliHub.jsx';

describe('Riepilogo costi noleggio', () => {
  it('include pedaggi, costi extra e riparazioni nel totale Altro', () => {
    expect(
      totaleAltriCosti({
        totale_pedaggio: 30,
        totale_costi_extra: 40,
        totale_riparazioni: 60,
      })
    ).toBe(130);
  });

  it('tratta i valori mancanti come zero', () => {
    expect(totaleAltriCosti({ totale_riparazioni: 25 })).toBe(25);
    expect(totaleAltriCosti(null)).toBe(0);
  });
});
