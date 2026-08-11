import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';


describe('Dashboard con fonti atomiche', () => {
  it('espone la copertura dei corrispettivi e la proiezione SumUp live', () => {
    const source = readFileSync(resolve(process.cwd(), 'src/pages/Dashboard.jsx'), 'utf8');
    expect(source).toContain('copertura_corrispettivi');
    expect(source).toContain('sumup_cassa_live');
    expect(source).toContain('senza riscrivere la prova sorgente');
  });
});
