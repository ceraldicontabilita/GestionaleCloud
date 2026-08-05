import { describe, expect, it } from 'vitest';
import { buildBalanceSummary } from './PianoDeiConti';


describe('buildBalanceSummary', () => {
  it('somma una sola volta i saldi gia calcolati per conto', () => {
    const summary = buildBalanceSummary({
      attivo: [{ saldo: 100 }, { saldo: -20 }],
      passivo: [{ saldo: 45 }],
      patrimonio_netto: [{ saldo: 10 }],
      ricavi: [{ saldo: 500 }, { saldo: 25 }],
      costi: [{ saldo: 300 }, { saldo: 75 }],
    });

    expect(summary.stato_patrimoniale.attivo.totale).toBe(80);
    expect(summary.stato_patrimoniale.passivo.totale).toBe(45);
    expect(summary.stato_patrimoniale.patrimonio_netto.totale).toBe(10);
    expect(summary.conto_economico.ricavi.totale).toBe(525);
    expect(summary.conto_economico.costi.totale).toBe(375);
    expect(summary.conto_economico.risultato).toBe(150);
  });
});
