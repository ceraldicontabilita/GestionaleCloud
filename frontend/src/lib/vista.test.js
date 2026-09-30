import { describe, expect, it } from 'vitest';
import {
  NON_DISPONIBILE, annoDelFiltro, codiceTributo, dataOppure, euroCentesimiOTrattino, euroCentesimiOppure,
  euroOppure, idF24DaUrl, percorsoCedolino, percorsoF24, percorsoProtocollo, percorsoTributo, testoOppure, urlOriginale,
} from './vista';

describe('vista: valori mancanti e formati', () => {
  it('un valore che manca non e mai zero', () => {
    for (const v of [null, undefined, '', Number.NaN]) {
      expect(euroOppure(v)).toBe(NON_DISPONIBILE);
      expect(euroCentesimiOppure(v)).toBe(NON_DISPONIBILE);
      expect(euroCentesimiOTrattino(v)).toBe(NON_DISPONIBILE);
      expect(dataOppure(v)).toBe(NON_DISPONIBILE);
      expect(testoOppure(v)).toBe(NON_DISPONIBILE);
    }
  });

  it('lo zero vero resta zero, lo zero del server sulle colonne di importo e un trattino', () => {
    expect(euroOppure(0)).toContain('0,00');
    expect(euroCentesimiOTrattino(0)).toBe('—');
    expect(euroCentesimiOTrattino(123456)).toContain('1.234,56');
  });

  it('date gg/mm/aaaa e importi in euro', () => {
    expect(dataOppure('2026-04-16')).toBe('16/04/2026');
    expect(dataOppure('2026-04-16T10:00:00+02:00')).toBe('16/04/2026');
    expect(euroOppure(1037.12)).toMatch(/1\.037,12/);
  });

  it('il codice tributo resta testo', () => {
    expect(codiceTributo('1040 ')).toBe('1040');
    expect(codiceTributo(1040)).toBe('1040');
    expect(codiceTributo(null)).toBe('');
  });
});

describe('vista: originali e percorsi', () => {
  it('un solo modo di comporre l indirizzo dell originale', () => {
    expect(urlOriginale({ tipo: 'quietanza', id: 'q 1' })).toBe('/api/f24-public/pdf/q%201');
    expect(urlOriginale({ tipo: 'f24', id: 'm1' })).toBe('/api/f24-public/pdf/m1');
    expect(urlOriginale({ tipo: 'cedolino', id: 'c1' })).toBe('/api/cedolini/c1/pdf');
    expect(urlOriginale({ url: '/api/x/pdf' })).toBe('/api/x/pdf');
    expect(urlOriginale({ tipo: 'sconosciuto', id: '1' })).toBeNull();
    expect(urlOriginale({ tipo: 'f24' })).toBeNull();
  });

  it('riconosce l id F24 dall indirizzo del PDF', () => {
    expect(idF24DaUrl('/api/f24-public/pdf/abc-1')).toBe('abc-1');
    expect(idF24DaUrl('/api/altro/abc')).toBeNull();
    expect(idF24DaUrl(null)).toBeNull();
  });

  it('i percorsi canonici delle viste', () => {
    expect(percorsoF24('a/b')).toBe('/fiscale/f24/a%2Fb');
    expect(percorsoTributo(' 6099 ')).toBe('/fiscale/tributi/6099');
    expect(percorsoCedolino('c1')).toBe('/personale/cedolini/c1');
    expect(percorsoProtocollo('P-7')).toBe('/protocollo/P-7');
    expect(percorsoProtocollo('2023/000123')).toBe('/protocollo/2023/000123');
  });

  it('il filtro anno: globale, fisso o tutti', () => {
    expect(annoDelFiltro(2026, null)).toBe(2026);
    expect(annoDelFiltro(2026, '2024')).toBe(2024);
    expect(annoDelFiltro(2026, 'tutti')).toBeNull();
    expect(annoDelFiltro(2026, 'boh')).toBe(2026);
  });
});
