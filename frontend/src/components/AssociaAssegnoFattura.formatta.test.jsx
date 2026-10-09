import { describe, expect, it } from 'vitest';
import { formattaFinaleAssegno } from './AssociaAssegnoFattura';

describe('formattaFinaleAssegno', () => {
  it('conserva il trattino dove lo scrive il titolare', () => {
    expect(formattaFinaleAssegno('694-90')).toBe('694-90');
    expect(formattaFinaleAssegno('9490-07')).toBe('9490-07');
    expect(formattaFinaleAssegno('694-')).toBe('694-');
  });

  it('senza trattino mostra la guida storica 328-01 fino a cinque cifre', () => {
    expect(formattaFinaleAssegno('00001')).toBe('000-01');
    expect(formattaFinaleAssegno('328')).toBe('328');
    expect(formattaFinaleAssegno('769490')).toBe('769490');
  });

  it('tiene solo cifre, al massimo dieci', () => {
    expect(formattaFinaleAssegno('69-4/90a')).toBe('69-490');
    expect(formattaFinaleAssegno('020876949012')).toBe('0876949012');
  });
});
