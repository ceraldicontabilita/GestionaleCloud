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
    expect(frontendSource).toContain('RipartizioneSalari');
    expect(frontendSource).toContain('/api/archivio-bonifici/ripartizione-salari/');
    expect(frontendSource).not.toContain('op.compatibilita_score');
    expect(backendSource).toContain('_salario_appartiene_al_dipendente');
    expect(backendSource).toContain('risolvi_dipendente(await _indici_dipendenti(hr)');
    expect(backendSource).toContain('Identifica il dipendente nella pagina HR Bonifici da associare');
    expect(backendSource).toContain('from app.services.associazione_salari import anteprima, pubblica, conferma');
  });

  it('non espone piu esportazioni xlsx o csv nella pagina', () => {
    expect(frontendSource).not.toContain('Export XLSX');
    expect(frontendSource).not.toContain('Export CSV');
    expect(frontendSource).not.toContain('handleExport');
    expect(frontendSource).not.toContain('📥 Importa');
    expect(frontendSource).not.toContain('handleDownloadZip');
    expect(frontendSource).not.toContain('clicca per scaricare ZIP');
  });

  it('un bonifico con la fattura collegata mostra la fattura e non propone il periodo', () => {
    expect(frontendSource).toContain('Pagamento fattura: nessun periodo');
    expect(frontendSource).toContain("t.fattura_esito === 'acconto'");
    // la colonna del salario non ripete «Scegli periodo» su ogni riga: solo per i dipendenti
    expect(frontendSource).toContain('!t.destinazione_dipendente');
    expect(frontendSource).toContain('t.destinazione_automatica');
  });
});
