import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

const frontendSource = readFileSync(
  resolve(process.cwd(), 'src/pages/ArchivioBonifici.jsx'),
  'utf8'
);
const backendSource = readFileSync(
  resolve(process.cwd(), '../app/routers/bonifici_module/associazioni.py'),
  'utf8'
);

describe('Archivio bonifici: scelta salario sicura', () => {
  it('mostra periodi dello stesso dipendente e non percentuali basate sull importo', () => {
    expect(frontendSource).toContain('Scegli periodo');
    expect(frontendSource).toContain('Identita verificata');
    expect(frontendSource).not.toContain('op.compatibilita_score');
    expect(backendSource).toContain('_salario_appartiene_al_dipendente');
    expect(backendSource).toContain('Il periodo selezionato appartiene a un altro dipendente');
  });

  it('non espone piu esportazioni xlsx o csv nella pagina', () => {
    expect(frontendSource).not.toContain('Export XLSX');
    expect(frontendSource).not.toContain('Export CSV');
    expect(frontendSource).not.toContain('handleExport');
    expect(frontendSource).not.toContain('📥 Importa');
    expect(frontendSource).not.toContain('handleDownloadZip');
    expect(frontendSource).not.toContain('clicca per scaricare ZIP');
  });
});
