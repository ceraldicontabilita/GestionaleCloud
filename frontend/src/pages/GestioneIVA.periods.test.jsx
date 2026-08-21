import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

const source = readFileSync(resolve(process.cwd(), 'src/pages/GestioneIVA.jsx'), 'utf8');
const styles = readFileSync(resolve(process.cwd(), 'src/pages/GestioneIVA.css'), 'utf8');

describe('Gestione IVA per periodo', () => {
  it('espone Annuale e i dodici mesi come tab visibili', () => {
    expect(source).toContain('data-testid="iva-tab-annuale"');
    expect(source).toContain('MESI_FULL.slice(1).map');
    expect(source).toContain('data-testid={`iva-tab-mese-${numeroMese}`}');
    expect(styles).toContain('scroll-snap-type: x proximity');
  });

  it('carica fatture e corrispettivi del periodo selezionato', () => {
    expect(source).toContain('/api/iva/fatture?periodo=${periodo}');
    expect(source).toContain('/api/corrispettivi?data_da=${start}&data_a=${end}');
    expect(source).toContain('iva-corrispettivi-tabella');
    expect(source).toContain('corrispettiviUnici');
    expect(source).toContain('copie escluse');
    expect(source).toContain('La matricola RT identifica il registratore');
  });

  it('mostra IVA esposta, percentuale detraibile e stato non classificato', () => {
    expect(source).toContain('percentuale_detraibilita_iva');
    expect(source).toContain('Da classificare');
    expect(source).toContain('IVA esposta');
    expect(source).toContain('IVA detraibile');
  });

  it('non mostra più il vecchio contatore del pregresso', () => {
    expect(source).not.toContain('data-testid="calcola-pregresso"');
    expect(source).not.toContain('ultimoRic');
    expect(source).not.toContain('Fatture lette');
  });
});

