import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

const hub = readFileSync(resolve(process.cwd(), 'src/pages/hub/RiconciliazioneHub.jsx'), 'utf8');
const tabs = readFileSync(resolve(process.cwd(), 'src/components/ds/HubTabs.jsx'), 'utf8');

describe('navigazione visibile della riconciliazione', () => {
  it('espone le sei destinazioni principali senza select', () => {
    for (const label of ['Bancaria', 'F24', 'Archivio bonifici', 'Assegni', 'PayPal', 'Coerenza POS']) {
      expect(hub).toContain(`label: '${label}'`);
    }
    expect(hub).toContain('mode="visible"');
    expect(tabs).toContain('role="tablist"');
    expect(tabs).toContain("scrollSnapType: 'x mandatory'");
  });
});
