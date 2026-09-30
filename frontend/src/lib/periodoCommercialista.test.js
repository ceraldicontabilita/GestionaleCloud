import { describe, expect, it } from 'vitest';

import {
  calcolaPeriodo, isoDaIT, itDaISO, mascheraDataIT, queryPeriodo, statoMese,
} from './periodoCommercialista';

describe('periodo dell\'Area Commercialista', () => {
  it('mese: primo e ultimo giorno, anche bisestile', () => {
    const p = calcolaPeriodo({ ...statoMese(2026, 9), anno: 2026 });
    expect(p).toMatchObject({ valido: true, dal: '2026-09-01', al: '2026-09-30', etichetta: 'Settembre 2026', meseRotta: 9 });
    expect(calcolaPeriodo({ ...statoMese(2028, 2), anno: 2028 }).al).toBe('2028-02-29');
  });

  it('trimestre: tre mesi interi e nessun mese per le rotte', () => {
    const p = calcolaPeriodo({ modo: 'trimestre', trimestre: 3, anno: 2026 });
    expect(p).toMatchObject({ dal: '2026-07-01', al: '2026-09-30', etichetta: '3° trimestre 2026', meseRotta: 0 });
    expect(calcolaPeriodo({ modo: 'trimestre', trimestre: 1, anno: 2026 }).al).toBe('2026-03-31');
  });

  it('anno: dal 1 gennaio al 31 dicembre', () => {
    expect(calcolaPeriodo({ modo: 'anno', anno: 2026 })).toMatchObject({
      dal: '2026-01-01', al: '2026-12-31', etichetta: 'Intero anno 2026', meseRotta: 0,
    });
  });

  it('personalizzato: legge gg/mm/aaaa e produce ISO', () => {
    const p = calcolaPeriodo({ modo: 'personalizzato', anno: 2026, dalIT: '15/08/2026', alIT: '05/09/2026' });
    expect(p).toMatchObject({ valido: true, dal: '2026-08-15', al: '2026-09-05', etichetta: 'dal 15/08/2026 al 05/09/2026' });
  });

  it('personalizzato: date incomplete, invertite o troppo lunghe non sono valide', () => {
    expect(calcolaPeriodo({ modo: 'personalizzato', anno: 2026, dalIT: '15/08', alIT: '' }).valido).toBe(false);
    const rovesciato = calcolaPeriodo({ modo: 'personalizzato', anno: 2026, dalIT: '05/09/2026', alIT: '15/08/2026' });
    expect(rovesciato.valido).toBe(false);
    expect(rovesciato.errore).toMatch(/dopo/);
    expect(calcolaPeriodo({ modo: 'personalizzato', anno: 2026, dalIT: '01/01/2020', alIT: '01/01/2026' }).errore).toMatch(/troppo lungo/);
  });

  it('isoDaIT rifiuta i giorni che non esistono', () => {
    expect(isoDaIT('31/02/2026')).toBeNull();
    expect(isoDaIT('29/02/2028')).toBe('2028-02-29');
    expect(itDaISO('2026-09-30T10:00:00Z')).toBe('30/09/2026');
  });

  it('la maschera mette da sola le barre', () => {
    expect(mascheraDataIT('3009')).toBe('30/09');
    expect(mascheraDataIT('30092026')).toBe('30/09/2026');
    expect(mascheraDataIT('30/09/20269')).toBe('30/09/2026');
  });

  it('queryPeriodo porta dal, al e i parametri non vuoti', () => {
    const q = queryPeriodo({ dal: '2026-09-01', al: '2026-09-30' }, { carnet_ids: '1234,5678', vuoto: '' });
    expect(q).toBe('?dal=2026-09-01&al=2026-09-30&carnet_ids=1234%2C5678');
  });
});
