import React, { useState } from 'react';

import api from '../api';
import { formatDateIT, formatEuroD } from '../lib/utils';
import { useConfirm } from './ui/ConfirmDialog';


function datiFattura(fattura = {}) {
  return {
    id: fattura.fattura_id || fattura.id,
    numero: fattura.fattura_numero || fattura.invoice_number
      || fattura.numero_documento || fattura.numero_fattura || '',
  };
}


const etichettaLivello = livello => ({
  verificato: 'Numero fattura + importo',
  forte: 'Fornitore/IBAN + importo',
  solo_importo: 'Solo importo: verifica necessaria',
}[livello] || 'Da verificare');


export default function AssociaBonificoFattura({
  fattura,
  onSuccess,
  buttonLabel = 'Abbina bonifico',
  buttonStyle = {},
}) {
  const confirm = useConfirm();
  const dati = datiFattura(fattura);
  const [aperto, setAperto] = useState(false);
  const [candidati, setCandidati] = useState([]);
  const [residuo, setResiduo] = useState(0);
  const [errore, setErrore] = useState('');
  const [loading, setLoading] = useState(false);

  const cerca = async () => {
    if (!dati.id) return;
    setLoading(true);
    setErrore('');
    try {
      const { data } = await api.get(`/api/fatture-ricevute/fattura/${encodeURIComponent(dati.id)}/candidati-bancari`);
      setCandidati(data?.candidati || []);
      setResiduo(data?.importo_residuo || 0);
    } catch (e) {
      setErrore(e.response?.data?.detail || e.response?.data?.message || e.message);
    } finally {
      setLoading(false);
    }
  };

  const commuta = () => {
    if (aperto) return setAperto(false);
    setAperto(true);
    cerca();
  };

  const collega = async candidato => {
    const nonUnivoco = candidato.richiede_conferma;
    const approvato = await confirm({
      title: nonUnivoco ? 'Conferma il bonifico candidato' : 'Collega il bonifico verificato',
      message: `${formatDateIT(candidato.data)} · ${formatEuroD(candidato.importo)}\n${candidato.descrizione || 'Senza causale'}\n\n${etichettaLivello(candidato.livello)}. Colleghi questo movimento alla fattura ${dati.numero}?`,
      confirmText: 'Collega bonifico',
      cancelText: 'Annulla',
      variant: nonUnivoco ? 'warning' : 'info',
    });
    if (!approvato) return;
    setLoading(true);
    setErrore('');
    try {
      const payload = {
        fattura_id: dati.id,
        movimento_id: candidato.movimento_id,
      };
      if (nonUnivoco) {
        payload.override_reason = `Conferma operatore dalla scheda fattura: movimento candidato per importo esatto; livello ${candidato.livello}.`;
      }
      const { data } = await api.post('/api/fatture-ricevute/riconcilia-con-estratto-conto', payload);
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
      <button type="button" onClick={commuta} disabled={!dati.id || loading}
        aria-label={`Associa bonifico alla fattura ${dati.numero}`.trim()}
        style={{ minHeight: 40, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          whiteSpace: 'nowrap', background: '#ecfdf5', color: '#047857', border: '1px solid #6ee7b7',
          borderRadius: 7, padding: '4px 12px', fontSize: 11.5, fontWeight: 800,
          cursor: !dati.id || loading ? 'wait' : 'pointer', ...buttonStyle }}>
        {loading && !aperto ? 'Ricerca…' : buttonLabel}
      </button>
      {aperto && (
        <div role="dialog" aria-modal="true" aria-label={`Bonifici candidati per la fattura ${dati.numero}`}
          onMouseDown={e => e.target === e.currentTarget && setAperto(false)}
          style={{ position: 'fixed', inset: 0, zIndex: 1200, display: 'flex', alignItems: 'center',
            justifyContent: 'center', padding: 16, background: 'rgba(15, 39, 68, 0.52)' }}>
          <div style={{ width: 'min(760px, 100%)', maxHeight: 'calc(100vh - 32px)', overflowY: 'auto',
            background: '#f8fafc', border: '1px solid #6ee7b7', borderRadius: 12, padding: 16,
            boxShadow: '0 24px 70px rgba(15, 39, 68, 0.28)' }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
              <div style={{ flex: 1 }}>
                <div style={{ color: '#065f46', fontWeight: 800 }}>Bonifici per fattura {dati.numero}</div>
                <div style={{ color: '#64748b', fontSize: 12, marginTop: 3 }}>Residuo: {formatEuroD(residuo)}. L’importo da solo non chiude la fattura.</div>
              </div>
              <button type="button" onClick={() => setAperto(false)} aria-label="Chiudi bonifici candidati"
                style={{ width: 36, height: 36, borderRadius: 8, border: '1px solid #a7f3d0', background: 'white', cursor: 'pointer' }}>×</button>
            </div>
            {loading && <div style={{ marginTop: 14 }}>Ricerca nell’estratto conto…</div>}
            {errore && <div role="alert" style={{ color: '#b91c1c', marginTop: 12 }}>{errore}</div>}
            {!loading && !errore && candidati.length === 0 && (
              <div role="status" style={{ marginTop: 14, padding: 12, background: 'white', borderRadius: 8 }}>
                Nessun movimento in uscita con importo esatto trovato dopo la data fattura.
              </div>
            )}
            {!loading && candidati.map(candidato => (
              <div key={candidato.movimento_id} style={{ marginTop: 10, padding: 12, background: 'white',
                border: `1px solid ${candidato.livello === 'solo_importo' ? '#fbbf24' : '#a7f3d0'}`, borderRadius: 9 }}>
                <div style={{ display: 'flex', gap: 10, justifyContent: 'space-between', flexWrap: 'wrap' }}>
                  <div style={{ flex: '1 1 420px' }}>
                    <b>{formatDateIT(candidato.data)} · {formatEuroD(candidato.importo)}</b>
                    <div style={{ color: '#334155', marginTop: 4, overflowWrap: 'anywhere' }}>{candidato.descrizione || 'Senza causale'}</div>
                    <div style={{ color: candidato.livello === 'solo_importo' ? '#92400e' : '#047857', fontSize: 12, fontWeight: 700, marginTop: 6 }}>
                      {etichettaLivello(candidato.livello)}
                    </div>
                  </div>
                  <button type="button" onClick={() => collega(candidato)} disabled={loading}
                    style={{ minHeight: 38, alignSelf: 'center', background: '#047857', color: 'white', border: 0,
                      borderRadius: 7, padding: '7px 12px', fontWeight: 800, cursor: loading ? 'wait' : 'pointer' }}>
                    Collega
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  );
}
