import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

const hub = readFileSync(resolve(process.cwd(), 'src/pages/hub/RiconciliazioneHub.jsx'), 'utf8');
const tabs = readFileSync(resolve(process.cwd(), 'src/components/ds/HubTabs.jsx'), 'utf8');

describe('navigazione visibile della riconciliazione', () => {
  it('espone le destinazioni principali senza select di navigazione', () => {
    for (const label of ['Riconciliazione', 'Indice operazioni', 'F24', 'PagoPA', 'Bonifici', 'Assegni', 'PayPal', 'Coerenza POS']) {
      expect(hub).toContain(`label: '${label}'`);
    }
    expect(hub).toContain('mode="visible"');
    expect(tabs).toContain('role="tablist"');
    expect(tabs).toContain("scrollSnapType: 'x mandatory'");
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
