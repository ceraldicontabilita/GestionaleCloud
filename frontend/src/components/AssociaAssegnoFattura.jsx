import React, { useState } from 'react';

import api from '../api';
import { formatDateIT, formatEuroD } from '../lib/utils';
import { useConfirm } from './ui/ConfirmDialog';


export function formattaFinaleAssegno(input) {
  const cifre = String(input ?? '').replace(/\D/g, '').slice(-5);
  if (cifre.length <= 3) return cifre;
  return `${cifre.slice(0, 3)}-${cifre.slice(3)}`;
}


function datiFattura(fattura = {}) {
  return {
    id: fattura.fattura_id || fattura.id,
    numero: fattura.fattura_numero || fattura.invoice_number
      || fattura.numero_documento || fattura.numero_fattura || '',
    importo: fattura.importo ?? fattura.total_amount ?? fattura.importo_totale ?? 0,
    fornitore: fattura.fornitore || fattura.supplier_name
      || fattura.fornitore_ragione_sociale || '',
  };
}


/**
 * Unica interfaccia di associazione assegno -> fattura.
 *
 * Prima Nota e Archivio Fatture usano questo stesso componente e gli stessi
 * endpoint. La decisione resta al backend canonico: registro assegni + numero
 * nella causale BPM + importo al centesimo + movimento ufficiale. Il client
 * non crea mai un collegamento sulla sola uguaglianza dell'importo.
 */
export default function AssociaAssegnoFattura({
  fattura,
  onSuccess,
  buttonLabel = 'Abbina assegno',
  buttonStyle = {},
}) {
  const confirm = useConfirm();
  const dati = datiFattura(fattura);
  const [aperto, setAperto] = useState(false);
  const [frammento, setFrammento] = useState('');
  const [proposte, setProposte] = useState([]);
  const [message, setMessage] = useState('');
  const [errore, setErrore] = useState('');
  const [loading, setLoading] = useState(false);

  const cerca = async (finale = frammento) => {
    if (!dati.id) return;
    setLoading(true);
    setErrore('');
    setProposte([]);
    try {
      const { data } = await api.get('/api/prima-nota/provvisori/assegni-proposti', {
        params: { fattura_id: dati.id, frammento: finale },
      });
      setProposte(data?.candidati || []);
      setMessage(data?.message || '');
    } catch (e) {
      setMessage('');
      setErrore(e.response?.data?.detail || e.response?.data?.message || e.message);
    } finally {
      setLoading(false);
    }
  };

  const commuta = () => {
    if (aperto) {
      setAperto(false);
      return;
    }
    setAperto(true);
    cerca('');
  };

  const collega = async candidato => {
    const approvato = await confirm({
      title: 'Collega assegno alla fattura',
      message: `Colleghi l'assegno ${candidato.numero_completo} alla fattura ${dati.numero || 'senza numero'} per ${formatEuroD(dati.importo)}?`,
      confirmText: 'Collega assegno',
      cancelText: 'Annulla',
      variant: 'warning',
    });
    if (!approvato) return;
    setLoading(true);
    setErrore('');
    try {
      const { data } = await api.post('/api/prima-nota/provvisori/associa-assegno', {
        fattura_id: dati.id,
        assegno_id: candidato.assegno_id,
        movimento_estratto_conto_id: candidato.movimento_estratto_conto_id,
        numero_completo: candidato.numero_completo,
      });
      setAperto(false);
      await onSuccess?.(data);
    } catch (e) {
      setErrore(e.response?.data?.detail || e.response?.data?.message || e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={commuta}
        disabled={!dati.id || loading}
        title="Cerca il numero assegno nel registro e nell'estratto conto BPM"
        aria-label={`Associa assegno alla fattura ${dati.numero}`.trim()}
        style={{
          minHeight: 40,
          background: '#f5f3ff',
          color: '#6d28d9',
          border: '1px solid #c4b5fd',
          borderRadius: 7,
          padding: '4px 12px',
          fontSize: 11.5,
          fontWeight: 800,
          cursor: !dati.id || loading ? 'wait' : 'pointer',
          ...buttonStyle,
        }}
      >
        {loading && !aperto ? 'Ricerca…' : buttonLabel}
      </button>

      {aperto && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={`Collega un assegno reale alla fattura ${dati.numero || 'senza numero'}`}
          onMouseDown={e => e.target === e.currentTarget && setAperto(false)}
          style={{
            position: 'fixed', inset: 0, zIndex: 1200,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            padding: 16, background: 'rgba(15, 39, 68, 0.52)',
          }}
        >
          <div style={{
            width: 'min(680px, 100%)', maxHeight: 'calc(100vh - 32px)', overflowY: 'auto',
            background: '#faf5ff', border: '1px solid #c4b5fd',
            borderRadius: 12, padding: 16, textAlign: 'left',
            boxShadow: '0 24px 70px rgba(15, 39, 68, 0.28)',
          }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, marginBottom: 12 }}>
            <div style={{ color: '#5b21b6', fontWeight: 800, flex: 1 }}>
              Collega un assegno reale alla fattura {dati.numero || 'senza numero'}
            </div>
            <button
              type="button"
              onClick={() => setAperto(false)}
              aria-label="Chiudi associazione assegno"
              style={{
                width: 36, height: 36, borderRadius: 8, border: '1px solid #ddd6fe',
                background: 'white', color: '#5b21b6', fontWeight: 800, cursor: 'pointer',
              }}
            >
              ×
            </button>
          </div>
          <div style={{ display: 'flex', gap: 7, flexWrap: 'wrap' }}>
            <input
              aria-label="Finale assegno nel formato 123-01"
              placeholder="Es. 328-01"
              inputMode="numeric"
              maxLength={6}
              value={frammento}
              onChange={e => setFrammento(formattaFinaleAssegno(e.target.value))}
              style={{
                minHeight: 40, flex: '1 1 240px', border: '1px solid #a78bfa',
                borderRadius: 8, padding: '7px 10px', fontSize: 12.5,
              }}
            />
            <button
              type="button"
              onClick={() => cerca(frammento)}
              disabled={loading}
              style={{
                minHeight: 40, background: '#6d28d9', color: 'white', border: 0,
                borderRadius: 8, padding: '7px 13px', fontWeight: 800,
                cursor: loading ? 'wait' : 'pointer',
              }}
            >
              {loading ? 'Ricerca…' : 'Cerca assegno'}
            </button>
          </div>
          <div style={{ color: '#64748b', marginTop: 6, fontSize: 11.5 }}>
            Digita il finale come 328-01. Il sistema ritrova anche il numero BPM
            completo 0208769328, che nell'estratto non contiene il suffisso del
            foglio. Nessun collegamento viene creato sul solo importo.
          </div>
          {errore && <div role="alert" style={{ color: '#b91c1c', marginTop: 7 }}>{errore}</div>}
          {!loading && message && (
            <div role="status" style={{ color: '#5b21b6', marginTop: 7, fontWeight: 700 }}>
              {message}
            </div>
          )}
          {!loading && proposte.map(candidato => {
            const collegatoAltrove = candidato.gia_collegato_fattura_id
              && candidato.gia_collegato_fattura_id !== dati.id;
            return (
              <div
                key={`${candidato.assegno_id || 'ec'}-${candidato.numero_completo}`}
                style={{
                  marginTop: 7, padding: '7px 9px', background: 'white',
                  border: '1px solid #ddd6fe', borderRadius: 8, display: 'flex',
                  justifyContent: 'space-between', gap: 8, alignItems: 'center',
                  flexWrap: 'wrap',
                }}
              >
                <span>
                  <b>Assegno {candidato.numero_completo}</b> · {formatEuroD(candidato.importo)}
                  {candidato.data ? ` · ${formatDateIT(candidato.data)}` : ''}
                  <span style={{ color: '#64748b' }}>
                    {' '}· {candidato.fonte_estratto_conto
                      ? 'presente in estratto conto'
                      : 'in attesa di estratto conto'}
                  </span>
                </span>
                <button
                  type="button"
                  onClick={() => collega(candidato)}
                  disabled={collegatoAltrove || loading}
                  title={collegatoAltrove
                    ? 'Assegno già collegato a un altra fattura'
                    : 'Conferma questo numero completo'}
                  aria-label={`Collega ${candidato.numero_completo}`}
                  style={{
                    minHeight: 36, background: collegatoAltrove ? '#cbd5e1' : '#6d28d9',
                    color: 'white', border: 0, borderRadius: 7, padding: '6px 11px',
                    fontWeight: 800, cursor: collegatoAltrove ? 'not-allowed' : 'pointer',
                  }}
                >
                  {collegatoAltrove ? 'Già collegato' : `Collega ${candidato.numero_completo}`}
                </button>
              </div>
            );
          })}
          </div>
        </div>
      )}
    </>
  );
}
