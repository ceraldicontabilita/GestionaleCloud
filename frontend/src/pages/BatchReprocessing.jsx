import React, { useCallback, useEffect, useMemo, useState } from 'react';
import api from '../api';
import { toast } from 'sonner';
import { useConfirm } from '../components/ui/ConfirmDialog';
import { PageLayout } from '../components/PageLayout';
import { AlertTriangle, CheckCircle, FileText, Loader2, Play, RefreshCw } from 'lucide-react';

const etichetta = valore => String(valore || 'non_classificato')
  .replaceAll('_', ' ')
  .replaceAll('-', ' ')
  .replace(/\b\w/g, c => c.toUpperCase());

export default function BatchReprocessing() {
  const confirm = useConfirm();
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

  return (
    <PageLayout
      title="Rielaborazione documenti"
      subtitle="Rilegge gli originali con i parser correnti, per tutte le categorie presenti in archivio"
      icon={<RefreshCw size={24} />}
    >
      <div className="max-w-5xl mx-auto space-y-6">
        <section className="bg-white rounded-xl shadow-sm border p-6">
          <div className="flex items-center justify-between gap-4 flex-wrap mb-4">
            <div>
              <h3 className="text-lg font-semibold flex items-center gap-2">
                <FileText size={20} /> Documenti disponibili
              </h3>
              <p className="text-sm text-gray-500 mt-1">
                Le categorie vengono lette dall'archivio: non esiste più una lista fissa limitata a F24 e cedolini.
              </p>
            </div>
            <div className="text-right">
              <div className="text-3xl font-bold text-slate-800">{anteprima?.totale || 0}</div>
              <div className="text-xs text-gray-500">documenti rielaborabili</div>
            </div>
          </div>

          <label className="block text-sm font-medium text-gray-700 mb-2" htmlFor="categoria-rielaborazione">
            Ambito
          </label>
          <select
            id="categoria-rielaborazione"
            value={categoria}
            onChange={e => setCategoria(e.target.value)}
            className="w-full min-h-11 border rounded-lg px-3 bg-white"
          >
            <option value="">Tutte le categorie ({anteprima?.totale || 0})</option>
            {categorie.map(([nome, totale]) => (
              <option key={nome} value={nome}>{etichetta(nome)} ({totale})</option>
            ))}
          </select>

          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2 mt-4">
            {categorie.map(([nome, totale]) => (
              <button
                type="button"
                key={nome}
                onClick={() => setCategoria(nome)}
                className={`text-left rounded-lg border px-3 py-2 ${categoria === nome ? 'border-slate-700 bg-slate-50' : 'border-slate-200 bg-white'}`}
              >
                <span className="font-medium">{etichetta(nome)}</span>
                <span className="float-right font-mono text-gray-500">{totale}</span>
              </button>
            ))}
          </div>
        </section>

        {stato && (
          <section className={`rounded-xl border p-6 ${stato.running ? 'bg-yellow-50 border-yellow-200' : stato.error ? 'bg-red-50 border-red-200' : risultato ? 'bg-green-50 border-green-200' : 'bg-white'}`}>
            <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
              {stato.running ? <Loader2 size={20} className="animate-spin" /> : stato.error ? <AlertTriangle size={20} /> : risultato ? <CheckCircle size={20} /> : <RefreshCw size={20} />}
              Stato rielaborazione
            </h3>
            <div className="text-sm font-medium">{stato.progress || 'Inattiva'}</div>
            {stato.error && <div className="mt-2 text-red-700">{stato.error}</div>}

            {risultato && (
              <div className="mt-4 space-y-3">
                {risultato.dry_run && (
                  <span className="inline-block px-2 py-1 rounded bg-orange-100 text-orange-800 text-xs font-semibold">
                    SIMULAZIONE: nessun dato salvato
                  </span>
                )}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-center">
                  <div className="bg-white rounded p-3"><b className="text-xl block">{risultato.totale_documenti || 0}</b><span className="text-xs text-gray-500">Trovati</span></div>
                  <div className="bg-white rounded p-3"><b className="text-xl block">{risultato.totale_processati || 0}</b><span className="text-xs text-gray-500">Processati</span></div>
                  <div className="bg-white rounded p-3"><b className="text-xl block text-green-700">{risultato.totale_successi || 0}</b><span className="text-xs text-gray-500">Riletti</span></div>
                  <div className="bg-white rounded p-3"><b className="text-xl block text-red-700">{risultato.totale_errori || 0}</b><span className="text-xs text-gray-500">Da verificare</span></div>
                </div>
                {Object.keys(risultato.categorie || {}).length > 0 && (
                  <details>
                    <summary className="cursor-pointer font-medium">Risultati per categoria</summary>
                    <div className="mt-2 grid gap-1 text-sm">
                      {Object.entries(risultato.categorie).map(([nome, dati]) => (
                        <div key={nome} className="flex justify-between bg-white rounded px-3 py-2">
                          <span>{etichetta(nome)}</span>
                          <span>{dati.successi || 0} riusciti · {dati.errori || 0} da verificare</span>
                        </div>
                      ))}
                    </div>
                  </details>
                )}
              </div>
            )}
          </section>
        )}

        <section className="bg-white rounded-xl shadow-sm border p-6">
          <h3 className="text-lg font-semibold mb-4">Azioni</h3>
          <div className="grid md:grid-cols-2 gap-4">
            <div className="rounded-lg bg-blue-50 p-4">
              <h4 className="font-semibold text-blue-900">Simulazione</h4>
              <p className="text-sm text-blue-700 mt-1 mb-3">Rilegge i documenti e mostra l'esito senza salvare modifiche.</p>
              <button onClick={() => avvia(true)} disabled={caricamento || stato?.running} className="flex items-center gap-2 px-4 py-2 bg-blue-700 text-white rounded-lg disabled:opacity-50">
                <Play size={16} /> Simula rielaborazione
              </button>
            </div>
            <div className="rounded-lg bg-orange-50 border border-orange-200 p-4">
              <h4 className="font-semibold text-orange-900 flex items-center gap-2"><AlertTriangle size={17} /> Esecuzione</h4>
              <p className="text-sm text-orange-700 mt-1 mb-3">Salva il nuovo esito accanto all'originale. Non crea un nuovo documento né un nuovo pagamento.</p>
              <button onClick={avviaReale} disabled={caricamento || stato?.running} className="flex items-center gap-2 px-4 py-2 bg-orange-700 text-white rounded-lg disabled:opacity-50">
                <Play size={16} /> Rielabora documenti
              </button>
            </div>
          </div>
        </section>

        <section className="text-sm text-gray-600 bg-gray-50 rounded-lg p-4">
          <b>Regola:</b> la rielaborazione non sostituisce l'originale e non prova un pagamento. Serve a rieseguire classificazione ed estrazione con i parser correnti e a conservare il nuovo risultato per confronto e verifica.
        </section>
      </div>
    </PageLayout>
  );
}
