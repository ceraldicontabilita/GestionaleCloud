import { describe, expect, it } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const source = fs.readFileSync(path.join(here, 'VerbaliRiconciliazione.jsx'), 'utf8');

describe('verbali: dati probatori e conferma esplicita', () => {
  it('non mostra come certo un importo OCR e non riconcilia al primo click', () => {
    expect(source).toContain('OCR da verificare');
    expect(source).toContain('Data da verificare');
    expect(source).toContain('?dry_run=true');
    expect(source).toContain('?dry_run=false');
    expect(source).toContain('await confirm({');
    expect(source).toContain('Cerca prove');
    expect(source).not.toContain('{v.importo ? formatEuro(v.importo)');
    expect(source).not.toContain('Riconcilia Automatico');
  });
});
