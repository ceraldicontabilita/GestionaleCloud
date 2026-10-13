import { describe, expect, it } from 'vitest';
import { righeGriglia } from './GrigliaPaghe';

describe('griglia contabile paghe', () => {
  it('usa i mensili canonici e mostra anche pagamenti anteriori senza cedolino', () => {
    const archivio = [{
      dipendente_id: 'pocci', dipendente: 'Pocci Salvatore', anno: 2020, mese: 1,
      busta: 875, erogato: 875, saldo: 0,
    }];
    const contabili = [
      { dipendente_id: 'pocci', dipendente: 'Pocci Salvatore', anno: 2018, mese: 8,
        cedolini: 0, dovuto: 0, bonifico: 375, acconti: 0, erogato: 375, saldo_progressivo: -375 },
      { dipendente_id: 'pocci', dipendente: 'Pocci Salvatore', anno: 2020, mese: 1,
        cedolini: 875, dovuto: 875, bonifico: 0, acconti: 0, erogato: 0, saldo_progressivo: 500 },
    ];

    const gruppi = righeGriglia(archivio, [], contabili);
    expect(gruppi.map(g => g.anno)).toEqual([2020, 2018]);
    expect(gruppi[0].mesi[1]).toMatchObject({ busta: 875, erogato: 0, saldo: 875 });
    expect(gruppi[1].mesi[8]).toMatchObject({ pagamento_senza_cedolino: true, erogato: 375, saldo: -375 });
  });

  it('non somma una seconda volta i record di competenza quando usa la contabilità', () => {
    const archivio = [
      { dipendente_id: 'd', dipendente: 'Dipendente', anno: 2026, mese: 7, busta: 1000, erogato: 1000 },
      { dipendente_id: 'd', dipendente: 'Dipendente', anno: 2026, mese: 14, busta: 500, erogato: 500 },
    ];
    const contabili = [{
      dipendente_id: 'd', dipendente: 'Dipendente', anno: 2026, mese: 7,
      cedolini: 1500, dovuto: 1500, bonifico: 1500, acconti: 0, erogato: 1500, saldo_progressivo: 0,
    }];

    const [gruppo] = righeGriglia(archivio, [], contabili);
    expect(Object.keys(gruppo.mesi)).toEqual(['7']);
    expect(gruppo.mesi[7]).toMatchObject({ busta: 1500, erogato: 1500, saldo: 0 });
  });
});
