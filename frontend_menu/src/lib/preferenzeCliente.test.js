import {
  leggiLingua, salvaLingua, leggiConsenso, salvaConsenso,
  CONSENSO_ACCETTATO, CONSENSO_RIFIUTATO,
} from './preferenzeCliente';
import { urlConfigurato } from './collegamentiPubblici';

describe('lingua del menu clienti', () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => jest.restoreAllMocks());

  test('senza preferenza parte in italiano', () => {
    expect(leggiLingua()).toBe('it');
  });

  test('una preferenza salvata si rispetta', () => {
    salvaLingua('en');
    expect(leggiLingua()).toBe('en');
  });

  test('un valore sconosciuto torna all\'italiano', () => {
    localStorage.setItem('menu_lingua', 'fr');
    expect(leggiLingua()).toBe('it');
  });

  test('storage che lancia: italiano, nessun errore', () => {
    jest.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('bloccato'); });
    jest.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('bloccato'); });
    expect(leggiLingua()).toBe('it');
    expect(salvaLingua('en')).toBe(false);
    expect(leggiConsenso()).toBeNull();
  });
});

describe('consenso cookie', () => {
  beforeEach(() => localStorage.clear());

  test('senza scelta non c\'e\' consenso', () => {
    expect(leggiConsenso()).toBeNull();
  });

  test('il «No» resta registrato con la data', () => {
    const adesso = new Date('2026-09-26T10:00:00Z');
    salvaConsenso(CONSENSO_RIFIUTATO, adesso);
    expect(leggiConsenso()).toEqual({ scelta: 'rifiutato', data: '2026-09-26T10:00:00.000Z' });
  });

  test('il «Sì» resta registrato con la data', () => {
    salvaConsenso(CONSENSO_ACCETTATO, new Date('2026-09-26T11:00:00Z'));
    expect(leggiConsenso().scelta).toBe('accettato');
  });

  test('la vecchia chiave vale come accettato, senza data inventata', () => {
    localStorage.setItem('cookieAccepted', 'true');
    expect(leggiConsenso()).toEqual({ scelta: 'accettato', data: null });
  });

  test('una scelta sconosciuta non si salva', () => {
    expect(() => salvaConsenso('forse')).toThrow();
  });
});

describe('collegamenti esterni', () => {
  test.each([null, '', '#', 'http://esempio.it', 'javascript:alert(1)', 'non un url'])(
    '%p non conta come configurato', (url) => {
      expect(urlConfigurato(url)).toBe(false);
    }
  );

  test('un https completo e\' configurato', () => {
    expect(urlConfigurato('https://www.esempio.it/pagina')).toBe(true);
  });
});
