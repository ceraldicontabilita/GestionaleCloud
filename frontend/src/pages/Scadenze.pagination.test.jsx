import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

const source = readFileSync(resolve(process.cwd(), 'src/pages/Scadenze.jsx'), 'utf8');

describe('Paginazione Scadenze', () => {
  it('usa il totale server e rende raggiungibili le righe oltre le prime cinquanta', () => {
    expect(source).toContain("params.append('offset', append ? String(scadenze.length) : '0')");
    expect(source).toContain('setTotaleScadenze(Number(scadenzeRes.data.totale || 0))');
    expect(source).toContain('📋 Tutte le Scadenze ({totaleScadenze})');
    expect(source).toContain('onClick={() => loadData(true)}');
    expect(source).toContain('Mostra altre ${Math.min(50, totaleScadenze - scadenze.length)} scadenze');
  });

  it('non conserva scadenze del periodo precedente quando il caricamento fallisce', () => {
    expect(source).toContain("const [loadError, setLoadError] = useState('')");
    expect(source).toContain('setScadenze([])');
    expect(source).toContain('setTotaleScadenze(0)');
    expect(source).toContain("Scadenze non disponibili per l'anno e i filtri selezionati.");
    expect(source).toContain('role="alert"');
    expect(source).toContain('Riprova');
  });
});
