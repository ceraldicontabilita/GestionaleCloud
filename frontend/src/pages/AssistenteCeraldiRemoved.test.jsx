import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import { NAV_TUTTE } from '../navigation.config';

describe('Rimozione Assistente Ceraldi', () => {
  it('non espone piu la pagina riepilogativa nella rotta o nella navigazione', () => {
    const mainSource = readFileSync(join(process.cwd(), 'src', 'main.jsx'), 'utf8');

    expect(NAV_TUTTE.some(item => item.to === '/assistente')).toBe(false);
    expect(mainSource).not.toContain('AssistenteCeraldi');
    expect(mainSource).not.toContain('path: "assistente"');
  });
});
