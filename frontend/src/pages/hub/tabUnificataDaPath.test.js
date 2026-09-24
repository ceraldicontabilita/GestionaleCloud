import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { tabUnificataDaPath } from './tabUnificataDaPath';

describe('tabUnificataDaPath', () => {
  it('non usa il prefisso morto e tiene il segmento intero', () => {
    expect(tabUnificataDaPath('/riconciliazione')).toBe('dashboard');
    expect(tabUnificataDaPath('/riconciliazione/banca')).toBe('banca');
    expect(tabUnificataDaPath('/riconciliazione/f24')).toBe('f24');
    expect(tabUnificataDaPath('/riconciliazione/banca?movimento=1')).toBe('banca');
    expect(tabUnificataDaPath('/riconciliazione/movimenti-banca')).toBe('dashboard');
    expect(tabUnificataDaPath('/riconciliazione-unificata/banca')).toBe('dashboard');
  });

  it('il sorgente Unificata non deve più contenere la regex morta', () => {
    const src = readFileSync(
      resolve(process.cwd(), 'src/pages/RiconciliazioneUnificata.jsx'),
      'utf8',
    );
    expect(src).not.toContain('(?:-unificata)');
    expect(src).not.toContain('riconciliazione-unificata');
  });
});
