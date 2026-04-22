import React, { useState, useEffect, useCallback } from 'react';
import api from '../api';
import { PageLayout } from '../components/PageLayout';
import {
  RefreshCw,
  Play,
  AlertTriangle,
  CheckCircle,
  Loader2,
  FileText,
  Users,
} from 'lucide-react';

export default function BatchReprocessing() {
  const [preview, setPreview] = useState(null);
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [polling, setPolling] = useState(false);

  const loadPreview = useCallback(async () => {
    try {
      const res = await api.get('/api/batch-reprocess/preview');
      setPreview(res.data);
    } catch (err) {
      console.error('Errore caricamento preview:', err);
    }
  }, []);

  const loadStatus = useCallback(async () => {
    try {
      const res = await api.get('/api/batch-reprocess/status');
      setStatus(res.data);
      return res.data;
    } catch (err) {
      console.error('Errore caricamento status:', err);
      return null;
    }
  }, []);

  useEffect(() => {
    loadPreview();
    loadStatus();
  }, [loadPreview, loadStatus]);

  // Polling quando il job è in corso
  useEffect(() => {
    let interval;
    if (polling) {
      interval = setInterval(async () => {
        const s = await loadStatus();
        if (s && !s.running) {
          setPolling(false);
        }
      }, 3000);
    }
    return () => clearInterval(interval);
  }, [polling, loadStatus]);

  const startReprocessing = async (dryRun = true, type = 'all') => {
    setLoading(true);
    try {
      let endpoint = '/api/batch-reprocess/start';
      if (type === 'f24') endpoint = '/api/batch-reprocess/f24-only';
      if (type === 'cedolini') endpoint = '/api/batch-reprocess/cedolini-only';

      await api.post(`${endpoint}?dry_run=${dryRun}`);
      setPolling(true);
      await loadStatus();
    } catch (err) {
      console.error('Errore avvio:', err);
      alert(err.response?.data?.detail || 'Errore avvio riprocessamento');
    } finally {
      setLoading(false);
    }
  };

  return (
    <PageLayout
      title="Riprocessamento Batch"
      subtitle="Riprocessa F24 e Cedolini con il parser migliorato"
      icon={<RefreshCw size={24} />}
    >
      <div className="max-w-4xl mx-auto space-y-6">
        {/* Preview */}
        {preview && (
          <div className="bg-white rounded-xl shadow-sm border p-6">
            <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
              <FileText size={20} />
              Documenti da Riprocessare
            </h3>
            <div className="grid grid-cols-3 gap-4">
              <div className="bg-blue-50 rounded-lg p-4 text-center">
                <div className="text-3xl font-bold text-blue-700">{preview.f24_totale || 0}</div>
                <div className="text-gray-600">F24</div>
              </div>
              <div className="bg-green-50 rounded-lg p-4 text-center">
                <div className="text-3xl font-bold text-green-700">
                  {preview.cedolini_totale || 0}
                </div>
                <div className="text-gray-600">Cedolini</div>
              </div>
              <div className="bg-purple-50 rounded-lg p-4 text-center">
                <div className="text-3xl font-bold text-purple-700">{preview.totale || 0}</div>
                <div className="text-gray-600">Totale</div>
              </div>
            </div>

            {/* Dettaglio collezioni */}
            <div className="mt-4 grid grid-cols-2 gap-4 text-sm">
              <div>
                <h4 className="font-semibold text-gray-700 mb-1">F24 per collezione:</h4>
                {Object.entries(preview.f24 || {}).map(([coll, count]) => (
                  <div key={coll} className="flex justify-between text-gray-600">
                    <span>{coll}</span>
                    <span className="font-mono">{count}</span>
                  </div>
                ))}
              </div>
              <div>
                <h4 className="font-semibold text-gray-700 mb-1">Cedolini per collezione:</h4>
                {Object.entries(preview.cedolini || {}).map(([coll, count]) => (
                  <div key={coll} className="flex justify-between text-gray-600">
                    <span>{coll}</span>
                    <span className="font-mono">{count}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Status */}
        {status && (
          <div
            className={`rounded-xl border p-6 ${
              status.running
                ? 'bg-yellow-50 border-yellow-200'
                : status.error
                  ? 'bg-red-50 border-red-200'
                  : status.result
                    ? 'bg-green-50 border-green-200'
                    : 'bg-white'
            }`}
          >
            <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
              {status.running ? (
                <Loader2 size={20} className="animate-spin" />
              ) : status.error ? (
                <AlertTriangle size={20} className="text-red-500" />
              ) : status.result ? (
                <CheckCircle size={20} className="text-green-500" />
              ) : (
                <RefreshCw size={20} />
              )}
              Stato Job
            </h3>

            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <span className="font-medium">Stato:</span>
                <span
                  className={`px-2 py-1 rounded text-sm ${
                    status.running
                      ? 'bg-yellow-200 text-yellow-800'
                      : status.error
                        ? 'bg-red-200 text-red-800'
                        : status.result
                          ? 'bg-green-200 text-green-800'
                          : 'bg-gray-200 text-gray-800'
                  }`}
                >
                  {status.progress || 'Inattivo'}
                </span>
              </div>

              {status.error && <div className="text-red-600 mt-2">Errore: {status.error}</div>}

              {status.result && (
                <div className="mt-4 space-y-3">
                  <div className="text-sm text-gray-600">
                    {status.result.dry_run && (
                      <span className="bg-orange-100 text-orange-700 px-2 py-1 rounded mr-2">
                        DRY RUN - Nessuna modifica salvata
                      </span>
                    )}
                  </div>

                  <div className="grid grid-cols-4 gap-4 text-center">
                    <div className="bg-white rounded p-3 shadow-sm">
                      <div className="text-xl font-bold text-blue-600">
                        {status.result.f24_success || 0}
                      </div>
                      <div className="text-xs text-gray-500">F24 OK</div>
                    </div>
                    <div className="bg-white rounded p-3 shadow-sm">
                      <div className="text-xl font-bold text-red-600">
                        {status.result.f24_errors || 0}
                      </div>
                      <div className="text-xs text-gray-500">F24 Errori</div>
                    </div>
                    <div className="bg-white rounded p-3 shadow-sm">
                      <div className="text-xl font-bold text-green-600">
                        {status.result.cedolini_success || 0}
                      </div>
                      <div className="text-xs text-gray-500">Cedolini OK</div>
                    </div>
                    <div className="bg-white rounded p-3 shadow-sm">
                      <div className="text-xl font-bold text-red-600">
                        {status.result.cedolini_errors || 0}
                      </div>
                      <div className="text-xs text-gray-500">Cedolini Errori</div>
                    </div>
                  </div>

                  <div className="text-center text-lg font-semibold mt-4">
                    Totale: {status.result.totale_successi || 0} /{' '}
                    {status.result.totale_processati || 0} processati con successo
                  </div>

                  {status.result.errors?.length > 0 && (
                    <details className="mt-4">
                      <summary className="cursor-pointer text-red-600 font-medium">
                        Mostra {status.result.errors?.length || 0} errori
                      </summary>
                      <div className="mt-2 max-h-40 overflow-y-auto text-sm bg-red-50 p-3 rounded">
                        {(status.result.errors || []).map((err, i) => (
                          <div key={i} className="mb-1 pb-1 border-b border-red-100">
                            [{err.type}] {err.collection}: {err.error}
                          </div>
                        ))}
                      </div>
                    </details>
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Azioni */}
        <div className="bg-white rounded-xl shadow-sm border p-6">
          <h3 className="text-lg font-semibold mb-4">Avvia Riprocessamento</h3>

          <div className="space-y-4">
            {/* Test Mode */}
            <div className="p-4 bg-blue-50 rounded-lg">
              <h4 className="font-medium text-blue-800 mb-2">Modalità Test (DRY RUN)</h4>
              <p className="text-sm text-blue-600 mb-3">
                Esegue il riprocessamento senza salvare le modifiche. Usa per verificare quanti
                documenti verrebbero aggiornati.
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => startReprocessing(true, 'all')}
                  disabled={loading || status?.running}
                  className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
                >
                  <Play size={16} />
                  Test Tutti
                </button>
                <button
                  onClick={() => startReprocessing(true, 'f24')}
                  disabled={loading || status?.running}
                  className="flex items-center gap-2 px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:opacity-50"
                >
                  <FileText size={16} />
                  Test F24
                </button>
                <button
                  onClick={() => startReprocessing(true, 'cedolini')}
                  disabled={loading || status?.running}
                  className="flex items-center gap-2 px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:opacity-50"
                >
                  <Users size={16} />
                  Test Cedolini
                </button>
              </div>
            </div>

            {/* Production Mode */}
            <div className="p-4 bg-orange-50 rounded-lg border border-orange-200">
              <h4 className="font-medium text-orange-800 mb-2 flex items-center gap-2">
                <AlertTriangle size={18} />
                Modalità Produzione (MODIFICA DATI)
              </h4>
              <p className="text-sm text-orange-600 mb-3">
                ⚠️ Attenzione: questa operazione modificherà permanentemente i dati nel database. I
                nuovi dati estratti verranno salvati nei campi *_enhanced.
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => {
                    if (
                      window.confirm(
                        'Sei sicuro? Questa operazione modificherà i dati nel database.'
                      )
                    ) {
                      startReprocessing(false, 'all');
                    }
                  }}
                  disabled={loading || status?.running}
                  className="flex items-center gap-2 px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 disabled:opacity-50"
                >
                  <Play size={16} />
                  Riprocessa Tutti
                </button>
                <button
                  onClick={() => {
                    if (window.confirm('Riprocessare tutti gli F24?')) {
                      startReprocessing(false, 'f24');
                    }
                  }}
                  disabled={loading || status?.running}
                  className="flex items-center gap-2 px-4 py-2 bg-orange-500 text-white rounded-lg hover:bg-orange-600 disabled:opacity-50"
                >
                  <FileText size={16} />
                  Riprocessa F24
                </button>
                <button
                  onClick={() => {
                    if (window.confirm('Riprocessare tutti i Cedolini?')) {
                      startReprocessing(false, 'cedolini');
                    }
                  }}
                  disabled={loading || status?.running}
                  className="flex items-center gap-2 px-4 py-2 bg-orange-500 text-white rounded-lg hover:bg-orange-600 disabled:opacity-50"
                >
                  <Users size={16} />
                  Riprocessa Cedolini
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Info */}
        <div className="text-sm text-gray-500 bg-gray-50 rounded-lg p-4">
          <h4 className="font-medium text-gray-700 mb-2">Come funziona:</h4>
          <ul className="list-disc list-inside space-y-1">
            <li>Il sistema legge i PDF originali memorizzati nel database</li>
            <li>Ogni documento viene riprocessato con il nuovo parser AI migliorato</li>
            <li>
              I nuovi dati vengono salvati in campi separati (*_enhanced) per non sovrascrivere i
              dati originali
            </li>
            <li>Puoi confrontare i dati originali con quelli migliorati</li>
          </ul>
        </div>
      </div>
    </PageLayout>
  );
}
