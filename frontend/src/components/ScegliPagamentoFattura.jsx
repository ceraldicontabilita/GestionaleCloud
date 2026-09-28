import React, { useState } from 'react';

import api from '../api';
import { COLORS, BORDER_RADIUS, formatEuroD } from '../lib/utils';
import AssociaAssegnoFattura from './AssociaAssegnoFattura';
import AssociaBonificoFattura from './AssociaBonificoFattura';

/**
 * Una tendina sola per dire come e' stata pagata una fattura ancora aperta:
 * Cassa, Banca o Assegno. Nessun motore nuovo:
 * - Cassa  -> `/api/prima-nota/provvisori/conferma` (metodo cassa, conferma
 *   esplicita del titolare per questa fattura, data scelta qui);
 * - Banca  -> la ricerca del movimento reale in estratto conto
 *   (`AssociaBonificoFattura`);
 * - Assegno -> il registro assegni (`AssociaAssegnoFattura`).
 * La tendina compare solo sulle fatture non pagate: una fattura gia' in
 * Cassa o in Banca non offre piu' l'assegno.
 */
export const OPZIONI_PAGAMENTO = [
  { value: 'cassa', label: 'Cassa (contanti)' },
  { value: 'banca', label: 'Banca (bonifico)' },
  { value: 'assegno', label: 'Assegno' },
];

const oggi = () => new Date().toISOString().slice(0, 10);

export default function ScegliPagamentoFattura({ fattura, onSuccess, style = {} }) {
  const [scelta, setScelta] = useState('');
  const [dataCassa, setDataCassa] = useState(
    () => String(fattura.invoice_date || fattura.data_documento || '').slice(0, 10) || oggi()
  );
  const [salvando, setSalvando] = useState(false);
  const [errore, setErrore] = useState('');
  const numero = fattura.invoice_number || fattura.numero_documento || '';
  const importo = fattura.total_amount ?? fattura.importo_totale ?? 0;

  const chiudi = () => {
    setScelta('');
    setErrore('');
  };

  const registraCassa = async () => {
    setSalvando(true);
    setErrore('');
    try {
      const { data } = await api.post('/api/prima-nota/provvisori/conferma', {
        fattura_id: fattura.id,
        metodo: 'cassa',
        approva_metodo_fattura: true,
        data_pagamento: dataCassa,
      });
      chiudi();
      await onSuccess?.({ ...data, message: `Fattura ${numero} pagata in cassa.` });
    } catch (e) {
      setErrore(e.response?.data?.detail || e.response?.data?.message || e.message);
    } finally {
      setSalvando(false);
    }
  };

  return (
    <>
      <select
        value={scelta}
        onChange={e => setScelta(e.target.value)}
        aria-label={`Come e' stata pagata la fattura ${numero}`.trim()}
        data-testid={`scegli-pagamento-${fattura.id}`}
        style={{
          minHeight: 40, width: '100%', maxWidth: 150, padding: '6px 8px', fontSize: 12.5,
          fontWeight: 700, color: COLORS.text, background: COLORS.card,
          border: `1px solid ${COLORS.border}`, borderRadius: BORDER_RADIUS.md, cursor: 'pointer',
          ...style,
        }}
      >
        <option value="">Pagata con…</option>
        {OPZIONI_PAGAMENTO.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>

      {scelta === 'banca' && (
        <AssociaBonificoFattura fattura={fattura} onSuccess={onSuccess} apriSubito onChiudi={chiudi} />
      )}
      {scelta === 'assegno' && (
        <AssociaAssegnoFattura fattura={fattura} onSuccess={onSuccess} apriSubito onChiudi={chiudi} />
      )}
      {scelta === 'cassa' && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={`Pagamento in cassa della fattura ${numero}`}
          onMouseDown={e => e.target === e.currentTarget && chiudi()}
          style={{
            position: 'fixed', inset: 0, zIndex: 1200, display: 'flex', alignItems: 'center',
            justifyContent: 'center', padding: 16, background: 'rgba(20, 20, 19, 0.52)',
          }}
        >
          <div style={{
            width: 'min(440px, 100%)', background: COLORS.card, borderRadius: 12, padding: 18,
            border: `1px solid ${COLORS.border}`, textAlign: 'left',
            boxShadow: '0 24px 70px rgba(20, 20, 19, 0.28)',
          }}>
            <div style={{ fontWeight: 800, fontSize: 15, color: COLORS.text }}>
              Pagata in contanti
            </div>
            <div style={{ color: COLORS.textMuted, fontSize: 13, marginTop: 6 }}>
              Fattura {numero} · {fattura.supplier_name || fattura.fornitore_ragione_sociale || ''} ·{' '}
              <b>{formatEuroD(importo)}</b>. Entra in Prima Nota Cassa per l'intero importo.
            </div>
            <label style={{ display: 'block', marginTop: 14, fontSize: 12.5, fontWeight: 700, color: COLORS.textMuted }}>
              Giorno del pagamento
              <input
                type="date"
                value={dataCassa}
                onChange={e => setDataCassa(e.target.value)}
                style={{
                  display: 'block', marginTop: 6, minHeight: 44, width: '100%', padding: '6px 10px',
                  fontSize: 14, border: `1px solid ${COLORS.border}`, borderRadius: BORDER_RADIUS.md,
                }}
              />
            </label>
            {errore && <div role="alert" style={{ color: COLORS.danger, marginTop: 10, fontSize: 13 }}>{errore}</div>}
            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 16 }}>
              <button
                type="button"
                onClick={chiudi}
                style={{
                  minHeight: 44, padding: '8px 14px', borderRadius: 8, fontWeight: 700,
                  border: `1px solid ${COLORS.border}`, background: COLORS.card, cursor: 'pointer',
                }}
              >
                Annulla
              </button>
              <button
                type="button"
                onClick={registraCassa}
                disabled={salvando || !dataCassa}
                style={{
                  minHeight: 44, padding: '8px 14px', borderRadius: 8, fontWeight: 800, border: 0,
                  background: COLORS.primary, color: 'white', cursor: salvando ? 'wait' : 'pointer',
                }}
              >
                {salvando ? 'Registro…' : 'Registra in cassa'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
