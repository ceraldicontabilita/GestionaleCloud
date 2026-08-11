import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

const source = readFileSync(resolve(process.cwd(), 'src/pages/Fornitori.jsx'), 'utf8');

describe('schede Fornitori compatte', () => {
  it('espone direttamente tutte le azioni senza menu puntini', () => {
    expect(source).toContain('data-testid={`azioni-visibili-${idFornitore(supplier)}`}');
    for (const label of ['Fatture', 'Modifica', 'Cessa', 'Elimina']) {
      expect(source).toContain(label);
    }
    expect(source).not.toContain('title="Altre azioni"');
  });

  it('mantiene una griglia mobile corta e filtri compatti', () => {
    expect(source).toContain("? 'repeat(2, minmax(0, 1fr))'");
    expect(source).toContain('Senza metodo');
    expect(source).toContain("padding: isMobile ? '7px 8px' : '8px 10px'");
  });
});
