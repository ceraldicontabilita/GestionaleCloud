/**
 * Mappa di navigazione unica: ogni sezione in vista, una volta sola, e con
 * un indirizzo che il router conosce davvero.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import { gruppiVisibili, NAV_COLONNA, NAV_GRUPPI, NAV_TUTTE, schedeDi, voceDi } from './navigation.config';

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

  it('in colonna stanno solo i hub: poche voci, tutte le pagine come schede', () => {
    // Decisione del titolare (07/10/2026): prima erano 54 voci in piano.
    expect(NAV_COLONNA.length).toBeLessThanOrEqual(20);
    expect(NAV_TUTTE.length).toBeGreaterThan(50);
    for (const hub of NAV_COLONNA.filter(v => v.schede?.length)) {
      expect(hub.to, hub.label).toBe(hub.schede[0].to);
      expect(hub.schede.length, hub.label).toBeGreaterThanOrEqual(2);
      for (const scheda of hub.schede) expect(scheda.perche, scheda.to).toBeTruthy();
    }
  });

  it('le sezioni di Contabilità stanno tutte fra le schede del suo hub', () => {
    const contabilita = NAV_COLONNA.find(v => v.label === 'Contabilità');
    expect(contabilita.schede).toHaveLength(11);
    expect(contabilita.schede.every(s => s.to.startsWith('/contabilita'))).toBe(true);
  });

  it('il libro giornale non sta in colonna finché resta spento', () => {
    expect(NAV_TUTTE.some(v => v.to === '/contabilita/giornale')).toBe(false);
  });

  it('la voce attiva è quella col prefisso più lungo, e porta con sé il suo hub', () => {
    expect(voceDi('/riconciliazione/f24').voce.label).toBe('F24');
    expect(voceDi('/riconciliazione/f24').hub.label).toBe('Fisco e scadenze');
    expect(voceDi('/riconciliazione').voce.label).toBe('Riepilogo');
    expect(voceDi('/riconciliazione').hub.label).toBe('Riconciliazione');
    expect(voceDi('/fatture/abc123').voce.label).toBe('Ricevute');
    expect(voceDi('/fatture/abc123').hub.label).toBe('Fatture');
    expect(voceDi('/fatture/corrispettivi').voce.label).toBe('Corrispettivi');
    expect(voceDi('/contabilita/controllo').gruppo.id).toBe('controlli');
    expect(voceDi('/').voce.label).toBe('Dashboard');
    expect(voceDi('/fornitori').hub.label).toBe('Fornitori');
    expect(voceDi('/pagina-inesistente')).toBeNull();
  });

  it('le schede del hub seguono il ruolo e spariscono se resta una scheda sola', () => {
    const riconciliazione = schedeDi('/riconciliazione/banca', false);
    expect(riconciliazione.hub.label).toBe('Riconciliazione');
    expect(riconciliazione.attiva.to).toBe('/riconciliazione/banca');
    expect(riconciliazione.schede.map(s => s.label)).toContain('Assegni');
    expect(schedeDi('/scadenze', true).schede.some(s => s.to === '/situazione-fiscale')).toBe(true);
    expect(schedeDi('/scadenze', false).schede.some(s => s.to === '/situazione-fiscale')).toBe(false);
    expect(schedeDi('/fornitori', true)).toBeNull();
    expect(schedeDi('/admin', false)).toBeNull();
    expect(schedeDi('/pagina-inesistente', true)).toBeNull();
  });

  it('le viste per id (MINI-08) stanno sotto Situazione fiscale, senza rubare gli altri prefissi', () => {
    expect(voceDi('/fiscale/tributi/1040').voce.label).toBe('Situazione fiscale');
    expect(voceDi('/fiscale/f24/abc').voce.label).toBe('Situazione fiscale');
    expect(voceDi('/tributi').voce.label).toBe('Situazione fiscale');
    expect(voceDi('/situazione-fiscale/ritenute').voce.label).toBe('Situazione fiscale');
    expect(voceDi('/fiscale/altro')).toBeNull();
  });

  it('le voci riservate non compaiono a chi non è amministratore', () => {
    const voci = gruppiVisibili(false).flatMap(g => g.voci);
    expect(voci.some(v => v.adminOnly)).toBe(false);
    expect(voci.some(v => v.label === 'Impostazioni')).toBe(false);
    const schede = voci.flatMap(v => v.schede || []);
    expect(schede.some(s => s.adminOnly)).toBe(false);
    expect(schede.some(s => s.to === '/situazione-fiscale')).toBe(false);
    expect(gruppiVisibili(true).flatMap(g => g.voci)).toHaveLength(NAV_COLONNA.length);
  });
});
