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

  it('nel magazzino / fuori: un controllo solo, filtro in lista, niente badge con emoji', () => {
    expect(source).toContain('<MagazzinoFornitore');
    expect(source).toContain('data-testid="filtro-magazzino"');
    expect(source).toContain("etichetta: 'Fuori dal magazzino'");
    expect(source).not.toContain('Escluso magazzino');
    expect(source).not.toContain('handleToggleEsclude');
    // il salvataggio generico non porta il flag: si cambia solo dal controllo con anteprima
    expect(source).toContain('datiScheda(formData)');
  });

  it('il metodo ha una data «valido dal» e si applica alle fatture dalla scheda', () => {
    expect(source).toContain('data-testid="metodo-valido-dal"');
    expect(source).toContain('<MetodoDalFornitore');
    expect(source).not.toContain('giorni_pagamento || 30} giorni');
  });

  it('mantiene una griglia mobile corta e filtri compatti', () => {
    expect(source).toContain("? 'repeat(2, minmax(0, 1fr))'");
    expect(source).toContain('Senza metodo');
    expect(source).toContain("padding: isMobile ? '7px 8px' : '8px 10px'");
  });
});
