/**
 * Mappa di navigazione unica: ogni sezione in vista, una volta sola, e con
 * un indirizzo che il router conosce davvero.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import { gruppiVisibili, NAV_GRUPPI, NAV_TUTTE, voceDi } from './navigation.config';

const main = readFileSync(join(process.cwd(), 'src', 'main.jsx'), 'utf8');
const rotteDiPrimoLivello = [...main.matchAll(/path: "([\w-]+)(?:\/\*)?"/g)].map(m => m[1]);

describe('navigation.config', () => {
  it('nessun indirizzo compare due volte', () => {
    const indirizzi = NAV_TUTTE.map(v => v.to || v.href);
    expect(new Set(indirizzi).size).toBe(indirizzi.length);
  });

  it('ogni voce interna porta a una rotta montata dal router', () => {
    for (const voce of NAV_TUTTE.filter(v => v.to && v.to !== '/')) {
      const primo = voce.to.split('/')[1];
      expect(rotteDiPrimoLivello, voce.to).toContain(primo);
    }
  });

  it('ogni gruppo ha titolo, colore e almeno una voce', () => {
    for (const gruppo of NAV_GRUPPI) {
      expect(gruppo.titolo).toBeTruthy();
      expect(gruppo.colore).toMatch(/^#[0-9a-f]{6}$/i);
      expect(gruppo.voci.length).toBeGreaterThan(0);
    }
  });

  it('le quindici sezioni di Contabilità stanno tutte nella colonna', () => {
    const contabilita = NAV_TUTTE.filter(v => v.to?.startsWith('/contabilita'));
    expect(contabilita).toHaveLength(15);
  });

  it('la voce attiva è quella col prefisso più lungo', () => {
    expect(voceDi('/riconciliazione/f24').voce.label).toBe('F24');
    expect(voceDi('/riconciliazione').voce.label).toBe('Riconciliazione');
    expect(voceDi('/fatture/abc123').voce.label).toBe('Fatture');
    expect(voceDi('/fatture/corrispettivi').voce.label).toBe('Corrispettivi');
    expect(voceDi('/contabilita/controllo').gruppo.id).toBe('controlli');
    expect(voceDi('/').voce.label).toBe('Dashboard');
    expect(voceDi('/pagina-inesistente')).toBeNull();
  });

  it('le voci riservate non compaiono a chi non è amministratore', () => {
    const voci = gruppiVisibili(false).flatMap(g => g.voci);
    expect(voci.some(v => v.adminOnly)).toBe(false);
    expect(voci.some(v => v.to === '/utenti')).toBe(false);
    expect(gruppiVisibili(true).flatMap(g => g.voci)).toHaveLength(NAV_TUTTE.length);
  });
});
