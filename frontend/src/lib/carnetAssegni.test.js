import { describe, expect, it } from 'vitest';

import { DA_COLLEGARE, avvisoSenzaFattura, datiRigaAssegno } from './carnetAssegni';

describe('righe del carnet assegni', () => {
  it('il beneficiario e\' il ripiego del fornitore, non una colonna', () => {
    const d = datiRigaAssegno({ beneficiario: 'ROSSI SRL', numero_fattura: '12/A', data_fattura: '2026-09-03' });
    expect(d).toEqual({ fornitore: 'ROSSI SRL', numeroFattura: '12/A', dataFattura: '03/09/2026' });
  });

  it('il fornitore della fattura vince sul beneficiario', () => {
    expect(datiRigaAssegno({ fornitore_fattura: 'ALFA', beneficiario: 'BETA', numero_fattura: '1' }).fornitore).toBe('ALFA');
  });

  it('cio\' che manca resta «Da collegare», mai un trattino', () => {
    expect(datiRigaAssegno({ numero: '0001' })).toEqual({
      fornitore: DA_COLLEGARE, numeroFattura: DA_COLLEGARE, dataFattura: DA_COLLEGARE,
    });
  });

  it('con piu fatture le date arrivano dal dettaglio', () => {
    const d = datiRigaAssegno({
      numero_fattura: '1, 2',
      fatture_dettaglio: [{ data_fattura: '2026-09-03' }, { data_fattura: '2026-09-10' }],
    });
    expect(d.dataFattura).toBe('03/09/2026, 10/09/2026');
  });

  it('l\'avviso conta gli assegni senza fattura', () => {
    expect(avvisoSenzaFattura([{ numero_fattura: '1' }, {}, {}])).toBe('2 assegni senza fattura collegata');
    expect(avvisoSenzaFattura([{}])).toBe('1 assegno senza fattura collegata');
    expect(avvisoSenzaFattura([{ numero_fattura: '1' }])).toBe('');
  });
});
