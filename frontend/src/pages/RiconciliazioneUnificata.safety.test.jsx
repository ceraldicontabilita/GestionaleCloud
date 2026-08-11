import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

const source = readFileSync(resolve(process.cwd(), 'src/pages/RiconciliazioneUnificata.jsx'), 'utf8');

describe('sicurezza della pagina Riconciliazione', () => {
  it('non espone né richiama riparazioni o riconciliazioni automatiche', () => {
    expect(source).not.toContain('Auto-Ripara');
    expect(source).not.toContain('Auto-Riconcilia');
    expect(source).not.toContain('/api/fatture-ricevute/auto-ricostruisci-dati');
    expect(source).not.toContain('/smart/riconcilia-auto');
  });

  it('mantiene il riepilogo come informazione in sola lettura', () => {
    expect(source).toContain('collegamenti già registrati');
  });
  it('non conferma mai automaticamente il primo candidato ambiguo', () => {
    expect(source).not.toContain('suggerimenti?.slice(0, 1)');
    expect(source).toContain('Seleziona il candidato digitando il numero');
  });

  it('richiede motivo per ignorare e modalita per gli stipendi non quadrati', () => {
    expect(source).toContain('codice_motivo');
    expect(source).toContain('acconto, saldo, multiplo oppure errore');
  });

  it('conserva la fonte bancaria e sostituisce le azioni di massa con analisi read-only', () => {
    expect(source).toContain('Analizza anomalie');
    expect(source).toContain('bank-anomaly-report');
    expect(source).toContain('Segnato come riconciliato, ma senza una fattura');
    expect(source).not.toContain('`Analisi in sola lettura: ${report.totale_anomalie');
    expect(source).toContain('Escludi dalla coda');
    expect(source).not.toContain('btn-elimina-movimento');
    expect(source).not.toContain('/api/estratto-conto-movimenti/${movId}');
  });

  it('supporta prospetti uno-a-molti e mostra caricati di totale', () => {
    expect(source).toContain("['fattura', 'fattura_sdd', 'fattura_bonifico']");
    expect(source).toContain('quota_cents');
    expect(source).toContain('stats.banca || movimentiBanca.length');
  });
});
