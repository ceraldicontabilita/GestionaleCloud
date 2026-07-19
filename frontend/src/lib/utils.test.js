// Primo test frontend del progetto (0 test automatici prima di questo
// file, nessun tool configurato). Copre le funzioni di formattazione
// importi/date di lib/utils.js: sono usate in praticamente ogni pagina
// dell'app per mostrare cifre contabili — un bug qui si vede ovunque.
// Vedi anche il commento nel file sorgente sul bug reale del 14/07/2026
// ("1119 €" invece di "€ 1.119,00").
import { describe, it, expect } from 'vitest';
import {
  formatEuro,
  formatEuroD,
  formatEuroShort,
  formatEuroStr,
  formatDateIT,
  formatDateGGMM,
  parseDateIT,
  formatDateTimeIT,
  formatDateShort,
} from './utils';

describe('formatEuro', () => {
  it('formatta un importo normale con simbolo prima, punto delle migliaia, virgola decimale', () => {
    expect(formatEuro(1119)).toBe('€ 1.119,00');
  });

  it('formatta zero come "€ 0,00", mai "€ 0"', () => {
    expect(formatEuro(0)).toBe('€ 0,00');
  });

  it('gestisce null/undefined senza sollevare', () => {
    expect(formatEuro(null)).toBe('€ 0,00');
    expect(formatEuro(undefined)).toBe('€ 0,00');
  });

  it('gestisce input non numerico senza sollevare', () => {
    expect(formatEuro('non-un-numero')).toBe('€ 0,00');
  });

  it('formatta correttamente i decimali (arrotondamento a 2 cifre)', () => {
    expect(formatEuro(1234.5)).toBe('€ 1.234,50');
    expect(formatEuro(1234.567)).toBe('€ 1.234,57');
  });

  it('formatta importi negativi (es. storni/note di credito)', () => {
    expect(formatEuro(-500)).toBe('€ -500,00');
  });

  it('accetta stringhe numeriche (dati che arrivano spesso come stringa dal backend)', () => {
    expect(formatEuro('1234.56')).toBe('€ 1.234,56');
  });

  it('formatta importi grandi con più separatori di migliaia', () => {
    expect(formatEuro(1234567.89)).toBe('€ 1.234.567,89');
  });
});

describe('formatEuroD', () => {
  it('si comporta come formatEuro per un input valido', () => {
    expect(formatEuroD(1119)).toBe('€ 1.119,00');
  });

  it('gestisce null/undefined senza sollevare', () => {
    expect(formatEuroD(null)).toBe('€ 0,00');
  });
});

describe('formatEuroShort', () => {
  it('formatta senza simbolo euro', () => {
    expect(formatEuroShort(1119)).toBe('1.119,00');
  });

  it('gestisce null/undefined senza sollevare', () => {
    expect(formatEuroShort(null)).toBe('0,00');
  });
});

describe('formatEuroStr', () => {
  it('è equivalente a formatEuro', () => {
    expect(formatEuroStr(1119)).toBe(formatEuro(1119));
    expect(formatEuroStr(null)).toBe('€ 0,00');
  });
});

describe('formatDateIT', () => {
  it('converte una data ISO (aaaa-mm-gg) in gg-mm-aaaa', () => {
    expect(formatDateIT('2026-07-19')).toBe('19-07-2026');
  });

  it('gestisce un datetime ISO completo (con T) prendendo solo la data', () => {
    expect(formatDateIT('2026-07-19T14:30:00Z')).toBe('19-07-2026');
  });

  it('converte un formato legacy gg/mm/aaaa in gg-mm-aaaa', () => {
    expect(formatDateIT('19/07/2026')).toBe('19-07-2026');
  });

  it('ritorna "-" per input assente', () => {
    expect(formatDateIT(null)).toBe('-');
    expect(formatDateIT('')).toBe('-');
  });

  it('non solleva su input malformato, ritorna l\'originale', () => {
    expect(formatDateIT('testo-non-una-data')).toBe('testo-non-una-data');
  });
});

describe('formatDateGGMM', () => {
  it('estrae solo giorno/mese da una data ISO', () => {
    expect(formatDateGGMM('2026-07-06')).toBe('06/07');
  });

  it('ritorna "-" per input assente', () => {
    expect(formatDateGGMM(null)).toBe('-');
  });
});

describe('parseDateIT', () => {
  it('converte gg/mm/aaaa in aaaa/mm/gg', () => {
    expect(parseDateIT('19/07/2026')).toBe('2026/07/19');
  });

  it('ritorna null per input assente', () => {
    expect(parseDateIT(null)).toBe(null);
    expect(parseDateIT('')).toBe(null);
  });
});

describe('formatDateTimeIT', () => {
  it('formatta data e ora nel formato gg-mm-aaaa hh:mm', () => {
    // Costruita in UTC così il test è deterministico a prescindere dal
    // fuso orario della macchina che esegue il test.
    const iso = new Date(Date.UTC(2026, 6, 19, 14, 30)).toISOString();
    const risultato = formatDateTimeIT(iso);
    expect(risultato).toMatch(/^19-07-2026 \d{2}:\d{2}$/);
  });

  it('ritorna "-" per input assente', () => {
    expect(formatDateTimeIT(null)).toBe('-');
  });

  it('non solleva su input malformato', () => {
    expect(formatDateTimeIT('testo-non-una-data')).toBe('testo-non-una-data');
  });
});

describe('formatDateShort', () => {
  it('formatta come gg-mm da una data ISO', () => {
    expect(formatDateShort('2026-07-19')).toBe('19-07');
  });

  it('ritorna "-" per input assente', () => {
    expect(formatDateShort(null)).toBe('-');
  });
});
