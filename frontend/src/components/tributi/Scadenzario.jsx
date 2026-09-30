import React, { useEffect, useState } from 'react';
import { Badge, PageLoader } from '../ds';
import { COLORS, FONT, formatEuro } from '../../lib/utils';
import api from '../../api';

/**
 * Scadenzario tributi (richiesta del 30/09/2026): per ogni codice e periodo
 * pagato, la scadenza di legge e la data della quietanza. In ritardo? Con
 * il ravvedimento (codici sanzione/interessi nella delega) e per l'importo
 * giusto? Sola lettura: `/api/f24/tributi/scadenzario` (persistente,
 * aggiornato a ogni quietanza e ogni 30 minuti).
 */

const VARIANTE = {
  PUNTUALE: 'success',
  RAVVEDUTO: 'accent',
  RAVVEDIMENTO_INSUFFICIENTE: 'danger',
  RITARDO_NON_RAVVEDUTO: 'danger',
  RITARDO_DA_VERIFICARE: 'warning',
  SCADENZA_NON_DETERMINATA: 'neutral',
};
const euro = cents => (cents ? formatEuro(cents / 100) : '—');
const dataIt = iso => {
  const [a, m, g] = String(iso || '').slice(0, 10).split('-');
  return a && m && g ? `${g}/${m}/${a}` : '—';
};
const selettore = {
  minHeight: 44, padding: '0 10px', borderRadius: 8, border: `1px solid ${COLORS.border}`,
  background: COLORS.card, fontSize: 14, fontFamily: FONT.family, color: COLORS.text,
};

export default function Scadenzario({ anno, stato, imposta }) {
  const [dati, setDati] = useState(null);
  const [errore, setErrore] = useState('');
  const [aperta, setAperta] = useState(null);
  const [mostrate, setMostrate] = useState(200);

  useEffect(() => {
    let attivo = true;
    const qs = new URLSearchParams();
    if (anno) qs.set('anno', anno);
    if (stato) qs.set('stato', stato);
    api.get(`/api/f24/tributi/scadenzario?${qs}`)
      .then(r => { if (attivo) { setDati(r.data); setMostrate(200); } })
      .catch(e => { if (attivo) setErrore(e.response?.data?.detail || e.message || 'Lettura non riuscita'); });
    return () => { attivo = false; };
  }, [anno, stato]);

  const voci = dati?.voci || [];
  return (
    <div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
        <select aria-label="Anno del periodo" value={anno} onChange={e => imposta('anno', e.target.value)} style={selettore}>
          <option value="">Tutti gli anni</option>
          {(dati?.anni || []).map(a => <option key={a} value={a}>{a}</option>)}
        </select>
        <select aria-label="Esito" value={stato} onChange={e => imposta('stato', e.target.value)} style={selettore}>
          <option value="">Tutti gli esiti</option>
          {(dati?.per_stato || []).map(s => <option key={s.id} value={s.id}>{s.label} ({s.n})</option>)}
        </select>
      </div>
      {errore && <div role="alert" style={{ color: COLORS.danger, marginBottom: 12 }}>{errore}</div>}
      {!dati && !errore && <PageLoader />}
      {dati && !voci.length && (
        <div style={{ padding: 30, textAlign: 'center', color: COLORS.textMuted }}>Nessun tributo con questi filtri.</div>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }} data-testid="scadenzario">
        {voci.slice(0, mostrate).map(v => (
          <div key={v.chiave} style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 12, padding: '10px 12px' }}>
            <button type="button" onClick={() => setAperta(a => (a === v.chiave ? null : v.chiave))} aria-expanded={aperta === v.chiave}
              style={{ all: 'unset', display: 'block', width: '100%', cursor: 'pointer', minHeight: 44 }} data-testid={`scad-${v.chiave}`}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
                <strong>{v.codice} · {v.periodo}</strong>
                <Badge variant={VARIANTE[v.stato] || 'neutral'}>{v.stato_label}</Badge>
              </div>
              <div style={{ fontSize: 12.5, color: COLORS.textMuted, marginTop: 2 }}>
                Scadenza {dataIt(v.scadenza)} · pagato {dataIt(v.ultimo_pagamento)} · {euro(v.pagato_cents)}
              </div>
            </button>
            {aperta === v.chiave && (v.pagamenti || []).map((p, i) => (
              <div key={`${p.protocollo}-${i}`} style={{ marginTop: 8, paddingTop: 8, borderTop: `1px solid ${COLORS.border}`, fontSize: 12.5, lineHeight: 1.5 }}
                data-testid="scad-pagamento">
                <strong>{dataIt(p.data)}</strong> · protocollo {p.protocollo || '—'} · {euro(p.importo_cents)}
                {p.giorni_ritardo > 0 && <> · <strong style={{ color: COLORS.warning }}>{p.giorni_ritardo} giorni di ritardo</strong></>}
                {p.compensazione_totale && <> · in compensazione</>}
                <div>{p.motivazione}</div>
              </div>
            ))}
          </div>
        ))}
      </div>
      {voci.length > mostrate && (
        <div style={{ textAlign: 'center', marginTop: 10 }}>
          <button type="button" style={{ ...selettore, cursor: 'pointer' }} onClick={() => setMostrate(n => n + 200)}>
            Mostra altre · {voci.length - mostrate} rimanenti
          </button>
        </div>
      )}
    </div>
  );
}
