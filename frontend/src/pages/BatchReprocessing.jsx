import React, { useCallback, useEffect, useMemo, useState } from 'react';
import api from '../api';
import { toast } from 'sonner';
import { useConfirm } from '../components/ui/ConfirmDialog';
import { PageLayout } from '../components/PageLayout';
import { AlertTriangle, CheckCircle, FileText, Loader2, Play, RefreshCw } from 'lucide-react';
import { Button, Card, Select } from '../components/ds';
import { COLORS, BORDER_RADIUS, useIsMobile } from '../lib/utils';

const etichetta = valore => String(valore || 'non_classificato')
  .replaceAll('_', ' ')
  .replaceAll('-', ' ')
  .replace(/\b\w/g, c => c.toUpperCase());

export default function BatchReprocessing() {
  const confirm = useConfirm();
  const isMobile = useIsMobile();
  const [anteprima, setAnteprima] = useState(null);
  const [stato, setStato] = useState(null);
  const [categoria, setCategoria] = useState('');
  const [caricamento, setCaricamento] = useState(false);
  const [controlloStato, setControlloStato] = useState(false);

  const caricaAnteprima = useCallback(async () => {
    try {
      const res = await api.get('/api/batch-reprocess/preview');
      setAnteprima(res.data);
    } catch (err) {
      console.error('Errore caricamento anteprima rielaborazione:', err);
      toast.error('Impossibile leggere i documenti disponibili per la rielaborazione');
    }
  }, []);

  const caricaStato = useCallback(async () => {
    try {
      const res = await api.get('/api/batch-reprocess/status');
      setStato(res.data);
      return res.data;
    } catch (err) {
      console.error('Errore caricamento stato rielaborazione:', err);
      return null;
    }
  }, []);

  useEffect(() => {
    caricaAnteprima();
    caricaStato();
  }, [caricaAnteprima, caricaStato]);

  useEffect(() => {
    if (!controlloStato) return undefined;
    const timer = setInterval(async () => {
      const s = await caricaStato();
      if (s && !s.running) {
        setControlloStato(false);
        caricaAnteprima();
      }
    }, 3000);
    return () => clearInterval(timer);
  }, [controlloStato, caricaStato, caricaAnteprima]);

  const categorie = useMemo(
    () => Object.entries(anteprima?.categorie || {}).sort((a, b) => b[1] - a[1]),
    [anteprima],
  );

  const avvia = async (simulazione) => {
    setCaricamento(true);
    try {
      const params = new URLSearchParams({ dry_run: String(simulazione) });
      if (categoria) params.set('categoria', categoria);
      await api.post(`/api/batch-reprocess/start?${params.toString()}`);
      toast.success(simulazione ? 'Simulazione avviata' : 'Rielaborazione avviata');
      setControlloStato(true);
      await caricaStato();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Errore avvio rielaborazione documenti');
    } finally {
      setCaricamento(false);
    }
  };

  const avviaReale = async () => {
    const nome = categoria ? etichetta(categoria) : 'tutti i documenti';
    const ok = await confirm({
      title: 'Rielabora documenti',
      message: `Rielaborare ${nome}? Il documento originale non viene sostituito; il nuovo esito viene salvato accanto all'originale.`,
      variant: 'warning',
    });
    if (ok) avvia(false);
  };

  const risultato = stato?.result || null;
  const colonne = n => (isMobile ? '1fr' : `repeat(${n}, minmax(0, 1fr))`);
  const sfondoStato = stato?.running ? COLORS.warningLight : stato?.error ? COLORS.dangerLight : risultato ? COLORS.successLight : COLORS.card;
  const tessera = { background: COLORS.card, borderRadius: BORDER_RADIUS.md, padding: 12 };

  return (
    <PageLayout
      title="Rielaborazione documenti"
      subtitle="Rilegge gli originali con i parser correnti, per tutte le categorie presenti in archivio"
    >
      <div style={{ maxWidth: 1024, margin: '0 auto', display: 'grid', gap: 24 }}>
        <Card
          title="Documenti disponibili"
          icon={<FileText size={18} aria-hidden style={{ marginRight: 6, verticalAlign: '-3px' }} />}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap', marginBottom: 16 }}>
            <p style={{ margin: 0, fontSize: 13, color: COLORS.textMuted, flex: '1 1 260px' }}>
              Le categorie vengono lette dall'archivio: non esiste più una lista fissa limitata a F24 e cedolini.
            </p>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: 28, fontWeight: 800, color: COLORS.text }}>{anteprima?.totale ?? 0}</div>
              <div style={{ fontSize: 12, color: COLORS.textMuted }}>documenti rielaborabili</div>
            </div>
          </div>

          <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 8 }} htmlFor="categoria-rielaborazione">
            Ambito
          </label>
          <Select
            id="categoria-rielaborazione"
            value={categoria}
            onChange={e => setCategoria(e.target.value)}
            style={{ width: '100%', minHeight: 44 }}
          >
            <option value="">Tutte le categorie ({anteprima?.totale ?? 0})</option>
            {categorie.map(([nome, totale]) => (
              <option key={nome} value={nome}>{etichetta(nome)} ({totale})</option>
            ))}
          </Select>

          <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, minmax(0, 1fr))', gap: 8, marginTop: 16 }}>
            {categorie.map(([nome, totale]) => (
              <button
                type="button"
                key={nome}
                onClick={() => setCategoria(nome)}
                aria-pressed={categoria === nome}
                style={{
                  textAlign: 'left', minHeight: 44, cursor: 'pointer', font: 'inherit', color: COLORS.text,
                  borderRadius: BORDER_RADIUS.md, padding: '8px 12px',
                  border: `1px solid ${categoria === nome ? COLORS.primary : COLORS.border}`,
                  background: categoria === nome ? COLORS.primarySoft : COLORS.card,
                  display: 'flex', justifyContent: 'space-between', gap: 8,
                }}
              >
                <span style={{ fontWeight: 600 }}>{etichetta(nome)}</span>
                <span style={{ color: COLORS.textMuted, fontVariantNumeric: 'tabular-nums' }}>{totale}</span>
              </button>
            ))}
          </div>
        </Card>

        {stato && (
          <section style={{ borderRadius: BORDER_RADIUS.lg, border: `1px solid ${COLORS.border}`, padding: 24, background: sfondoStato }}>
            <h3 style={{ margin: '0 0 12px', fontSize: 17, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 8 }}>
              {stato.running ? <Loader2 size={20} aria-hidden style={{ animation: 'rielab-spin 1s linear infinite' }} /> : stato.error ? <AlertTriangle size={20} aria-hidden /> : risultato ? <CheckCircle size={20} aria-hidden /> : <RefreshCw size={20} aria-hidden />}
              Stato rielaborazione
            </h3>
            <style>{'@keyframes rielab-spin { to { transform: rotate(360deg); } }'}</style>
            <div style={{ fontSize: 13, fontWeight: 600 }}>{stato.progress || 'Inattiva'}</div>
            {stato.error && <div style={{ marginTop: 8, color: COLORS.danger }}>{stato.error}</div>}

            {risultato && (
              <div style={{ marginTop: 16, display: 'grid', gap: 12 }}>
                {risultato.dry_run && (
                  <span style={{ justifySelf: 'start', padding: '4px 8px', borderRadius: BORDER_RADIUS.sm, background: COLORS.warningLight, color: COLORS.warning, fontSize: 12, fontWeight: 700 }}>
                    SIMULAZIONE: nessun dato salvato
                  </span>
                )}
                <div style={{ display: 'grid', gridTemplateColumns: isMobile ? 'repeat(2, minmax(0, 1fr))' : 'repeat(4, minmax(0, 1fr))', gap: 12, textAlign: 'center' }}>
                  <div style={tessera}><b style={{ fontSize: 20, display: 'block' }}>{risultato.totale_documenti ?? 0}</b><span style={{ fontSize: 12, color: COLORS.textMuted }}>Trovati</span></div>
                  <div style={tessera}><b style={{ fontSize: 20, display: 'block' }}>{risultato.totale_processati ?? 0}</b><span style={{ fontSize: 12, color: COLORS.textMuted }}>Processati</span></div>
                  <div style={tessera}><b style={{ fontSize: 20, display: 'block', color: COLORS.success }}>{risultato.totale_successi ?? 0}</b><span style={{ fontSize: 12, color: COLORS.textMuted }}>Riletti</span></div>
                  <div style={tessera}><b style={{ fontSize: 20, display: 'block', color: COLORS.danger }}>{risultato.totale_errori ?? 0}</b><span style={{ fontSize: 12, color: COLORS.textMuted }}>Da verificare</span></div>
                </div>
                {Object.keys(risultato.categorie || {}).length > 0 && (
                  <details>
                    <summary style={{ cursor: 'pointer', fontWeight: 600, minHeight: 44, display: 'flex', alignItems: 'center' }}>Risultati per categoria</summary>
                    <div style={{ marginTop: 8, display: 'grid', gap: 4, fontSize: 13 }}>
                      {Object.entries(risultato.categorie).map(([nome, dati]) => (
                        <div key={nome} style={{ ...tessera, padding: '8px 12px', display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
                          <span>{etichetta(nome)}</span>
                          <span>{dati.successi ?? 0} riusciti · {dati.errori ?? 0} da verificare</span>
                        </div>
                      ))}
                    </div>
                  </details>
                )}
              </div>
            )}
          </section>
        )}

        <Card title="Azioni">
          <div style={{ display: 'grid', gridTemplateColumns: colonne(2), gap: 16 }}>
            <div style={{ borderRadius: BORDER_RADIUS.md, background: COLORS.bgAlt, border: `1px solid ${COLORS.border}`, padding: 16 }}>
              <h4 style={{ margin: 0, fontWeight: 700 }}>Simulazione</h4>
              <p style={{ fontSize: 13, color: COLORS.textMuted, margin: '4px 0 12px' }}>Rilegge i documenti e mostra l'esito senza salvare modifiche.</p>
              <Button variant="primary" onClick={() => avvia(true)} disabled={caricamento || stato?.running} iconLeft={<Play size={16} aria-hidden />} style={{ minHeight: 44 }}>
                Simula rielaborazione
              </Button>
            </div>
            <div style={{ borderRadius: BORDER_RADIUS.md, background: COLORS.warningLight, border: `1px solid ${COLORS.border}`, padding: 16 }}>
              <h4 style={{ margin: 0, fontWeight: 700, color: COLORS.warning, display: 'flex', alignItems: 'center', gap: 8 }}><AlertTriangle size={17} aria-hidden /> Esecuzione</h4>
              <p style={{ fontSize: 13, color: COLORS.warning, margin: '4px 0 12px' }}>Salva il nuovo esito accanto all'originale. Non crea un nuovo documento né un nuovo pagamento.</p>
              <Button variant="danger" onClick={avviaReale} disabled={caricamento || stato?.running} iconLeft={<Play size={16} aria-hidden />} style={{ minHeight: 44 }}>
                Rielabora documenti
              </Button>
            </div>
          </div>
        </Card>

        <section style={{ fontSize: 13, color: COLORS.textMuted, background: COLORS.bgAlt, borderRadius: BORDER_RADIUS.md, padding: 16 }}>
          <b>Regola:</b> la rielaborazione non sostituisce l'originale e non prova un pagamento. Serve a rieseguire classificazione ed estrazione con i parser correnti e a conservare il nuovo risultato per confronto e verifica.
        </section>
      </div>
    </PageLayout>
  );
}
