import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

describe('Confine operativo della pagina Admin', () => {
  it('non contiene import Drive o tabelle contabili SumUp', () => {
    const source = readFileSync(join(process.cwd(), 'src', 'pages', 'Admin.jsx'), 'utf8');

    expect(source).not.toContain('/api/fatture/drive/sync');
    expect(source).not.toContain('/api/config-import/importa-anno');
    expect(source).not.toContain('Incassi SumUp');
    expect(source).not.toContain('Accrediti SumUp');
    expect(source).not.toContain('Fatture importate (totale)');
  });
});
