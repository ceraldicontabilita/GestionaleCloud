import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const hub = readFileSync(resolve(process.cwd(), 'src/pages/hub/ContabilitaHub.jsx'), 'utf8');

describe('parser hub contabilità', () => {
  it('non usa includes sulle sottostringhe', () => {
    expect(hub).not.toContain("includes('/bilancio')");
    expect(hub).not.toContain('getTabFromPath');
    expect(hub).toContain('sezioneContabilita');
    expect(hub).not.toContain('⚠️');
  });
});
