import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

import { NAV_COLONNA } from '../../navigation.config';

const hub = readFileSync(resolve(process.cwd(), 'src/pages/hub/RiconciliazioneHub.jsx'), 'utf8');
const tabs = readFileSync(resolve(process.cwd(), 'src/components/ds/HubTabs.jsx'), 'utf8');

describe('navigazione visibile della riconciliazione', () => {
  it('espone le destinazioni principali come schede della mappa unica, senza select', () => {
    const schede = NAV_COLONNA.find(v => v.label === 'Riconciliazione').schede.map(s => s.label);
    for (const label of [
      'Riepilogo',
      'Banca',
      'Stipendi',
      'Documenti',
      'PagoPA',
      'Bonifici',
      'Assegni',
      'PayPal',
      'Coerenza POS',
    ]) {
      expect(schede).toContain(label);
    }
    // L'hub non disegna piu' una propria riga di schede: la disegna SchedeHub.
    expect(hub).not.toContain('HubTabs');
    expect(tabs).toContain('role="tablist"');
    expect(tabs).toContain("flexWrap: 'wrap'");
    expect(tabs).not.toContain('<option');
  });

  it('non usa includes sul pezzo banca', () => {
    expect(hub).not.toContain("includes('/banca')");
    expect(hub).toContain('sezioneRiconciliazione');
  });

  it('sincronizza PayPal automaticamente quando si apre il tab', () => {
    expect(hub).toContain("api.get('/api/paypal-api/status')");
    expect(hub).toContain("api.post('/api/paypal-api/sync'");
    expect(hub).toContain("activeTab !== 'paypal'");
    expect(hub).toContain('paypalRefreshKey');
  });

  it('nasconde il vecchio comando manuale di sincronizzazione PayPal', () => {
    expect(hub).toContain('[data-testid="sync-paypal-api-btn"]');
    expect(hub).toContain('select:has(+ [data-testid="sync-paypal-api-btn"])');
  });
});
