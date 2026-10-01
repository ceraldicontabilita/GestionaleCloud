import { describe, expect, it } from 'vitest';
import { buildBalanceSummary, lato_saldo } from './PianoDeiConti';


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

describe('lato_saldo', () => {
  it('un saldo negativo su Erario c/IVA e un credito, non un debito', () => {
    expect(lato_saldo({ codice: '35.01', categoria: 'passivo', saldo: -76201.59 }))
      .toEqual({ testo: 'credito verso Erario', favorevole: true });
  });

  it('un saldo negativo su un altro conto del passivo e solo un saldo in dare', () => {
    expect(lato_saldo({ codice: '33.03.01', categoria: 'passivo', saldo: -10 }))
      .toEqual({ testo: 'saldo in dare', favorevole: false });
  });

  it('un saldo positivo non porta etichetta', () => {
    expect(lato_saldo({ codice: '35.01.11', categoria: 'passivo', saldo: 47890.44 })).toBeNull();
  });
});
