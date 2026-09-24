import { describe, expect, it } from 'vitest';
import { tabUnificataDaPath } from './tabUnificataDaPath';

describe('tabUnificataDaPath', () => {
  it('ignora il prefisso morto e non spezza gli hyphen', () => {
    expect(tabUnificataDaPath('/riconciliazione')).toBe('dashboard');
    expect(tabUnificataDaPath('/riconciliazione/banca')).toBe('banca');
    expect(tabUnificataDaPath('/riconciliazione/f24')).toBe('f24');
    expect(tabUnificataDaPath('/riconciliazione/banca?movimento=1')).toBe('banca');
    expect(tabUnificataDaPath('/riconciliazione/movimenti-banca')).toBe('dashboard');
    expect(tabUnificataDaPath('/riconciliazione-unificata/banca')).toBe('dashboard');
  });
});
