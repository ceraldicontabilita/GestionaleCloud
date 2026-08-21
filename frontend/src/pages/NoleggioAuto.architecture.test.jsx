import { describe, expect, it } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const source = fs.readFileSync(path.join(here, 'NoleggioAuto.jsx'), 'utf8');

describe('confini operativi della pagina Noleggio', () => {
  it('separa pagamenti bancari e associazione fattura-veicolo', () => {
    expect(source).toContain('AssociaMovimentoBanca');
    expect(source).toContain('Verifica pagamento');
    expect(source).not.toContain('/riconciliazione/banca?ambito=noleggio');
    expect(source).toContain('/associa-veicolo');
    expect(source).toContain('questa relazione non modifica lo stato del pagamento');
    expect(source).not.toContain('🔗 Associa');
  });
});
