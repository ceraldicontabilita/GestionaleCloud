import React, { useEffect, useState } from 'react';
import { Badge, PageLoader } from '../ds';
import { COLORS, FONT, formatEuro } from '../../lib/utils';
import api from '../../api';
import { Protocollo } from './RegistroVersamenti';

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
  DICHIARATO_770_SENZA_QUIETANZA: 'warning',
};

/** La riga del quadro ST del 770 agganciata alla voce: cosa il commercialista dichiara versato. */
function Dichiarato770({ voce }) {
  const righe = voce.dichiarato_770 || [];
  if (!righe.length) return null;
  const c = voce.confronto_770 || {};
  const esito = c.importo === 'COINCIDE' ? 'coincide con le quietanze'
    : c.importo === 'DIFFERENZA' ? `differenza ${euro(Math.abs(c.differenza_cents || 0))} rispetto alle quietanze`
      : 'quietanza non in archivio';
  return (
    <div style={{ marginTop: 6, fontSize: 12.5, color: COLORS.textMuted }} data-testid="dichiarato-770">
      {righe.map((d, i) => (
        <div key={`${d.rigo}-${i}`}>
          770 {d.fonte?.anno_imposta || ''} rigo {d.rigo}: ritenute operate {euro(d.ritenute_operate_cents)} · versato {euro(d.importo_versato_cents)}
          {d.data_versamento ? ` il ${dataIt(d.data_versamento)}` : ''}{d.ravvedimento ? ' · ravvedimento (X)' : ''} · {esito}
        </div>
      ))}
    </div>
  );
}
const euro = cents => (cents ? formatEuro(cents / 100) : '—');
const dataIt = iso => {
  const [a, m, g] = String(iso || '').slice(0, 10).split('-');
  return a && m && g ? `${g}/${m}/${a}` : '—';
};
const selettore = {
  minHeight: 44, padding: '0 10px', borderRadius: 8, border: `1px solid ${COLORS.border}`,
  background: COLORS.card, fontSize: 14, fontFamily: FONT.family, color: COLORS.text,
};

/**
 * Scadenza e ravvedimento di UN F24 (pannello di dettaglio): le voci dello
 * scadenzario i cui pagamenti vengono da questa quietanza. Nessun calcolo qui:
 * legge lo stesso endpoint dello Scadenzario e filtra per id.
 */
export function ScadenzaF24({ id }) {
  const [voci, setVoci] = useState(null);
  const [errore, setErrore] = useState('');
  useEffect(() => {
    let attivo = true;
    setVoci(null); setErrore('');
    api.get('/api/f24/tributi/scadenzario')
      .then(r => {
        if (!attivo) return;
        const mie = [];
        (r.data?.voci || []).forEach(v => {
          const p = (v.pagamenti || []).find(x => String(x.quietanza_id) === String(id));
          if (p) mie.push({ v, p });
        });
        setVoci(mie);
      })
      .catch(e => { if (attivo) setErrore(e.response?.data?.detail || e.message || 'Lettura non riuscita'); });
    return () => { attivo = false; };
  }, [id]);

  if (errore) return <div role="alert" style={{ color: COLORS.danger }}>Scadenzario non disponibile: {errore}</div>;
  if (!voci) return <PageLoader />;
  if (!voci.length) {
    return <p data-testid="scadenza-vuota" style={{ margin: 0, color: COLORS.textMuted, fontSize: 14 }}>
      Nessuna scadenza calcolata per questo F24 (serve la quietanza con le righe a debito).
    </p>;
  }
  return (
    <div style={{ display: 'grid', gap: 10 }} data-testid="scadenza-f24">
      {voci.map(({ v, p }) => {
        const ravvedimento = p.giorni_ritardo > 0;
        return (
          <div key={v.chiave} style={{ border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: '10px 12px', fontSize: 13 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <strong>{v.codice} · {v.periodo}</strong>
              <Badge variant={VARIANTE[p.stato] || 'neutral'}>{v.stato_label || p.stato}</Badge>
            </div>
            <div style={{ marginTop: 4, color: COLORS.textMuted }}>
              Scadenza {dataIt(v.scadenza)}{v.scadenza_fonte ? ` (${v.scadenza_fonte})` : ''} · pagato il {dataIt(p.data)} · {euro(p.importo_cents)}
              {ravvedimento && <> · <strong style={{ color: COLORS.warning }}>{p.giorni_ritardo} giorni di ritardo</strong></>}
            </div>
            {ravvedimento && (
              <div style={{ marginTop: 6, display: 'grid', gridTemplateColumns: 'auto 1fr 1fr', gap: '2px 14px' }} data-testid="ravvedimento-f24">
                <span />
                <strong style={{ fontSize: 11, color: COLORS.textMuted }}>VERSATO</strong>
                <strong style={{ fontSize: 11, color: COLORS.textMuted }}>ATTESO</strong>
                <span>Sanzioni</span><span>{euro(p.sanzioni_periodo_cents)}</span><span>{euro(p.sanzioni_periodo_attese_cents)}</span>
                <span>Interessi</span><span>{euro(p.interessi_periodo_cents)}</span><span>{euro(p.interessi_periodo_attesi_cents)}</span>
              </div>
            )}
            {(p.fascia || p.regime) && ravvedimento && (
              <div style={{ marginTop: 4, fontSize: 12, color: COLORS.textMuted }}>{[p.fascia, p.regime].filter(Boolean).join(' · ')}</div>
            )}
            {p.motivazione && <div style={{ marginTop: 4, fontSize: 12.5 }}>{p.motivazione}</div>}
          </div>
        );
      })}
    </div>
  );
}

export default function Scadenzario({ anno, stato, imposta, onApri = () => {}, onDettaglio }) {
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
              <Dichiarato770 voce={v} />
            </button>
            {aperta === v.chiave && !(v.pagamenti || []).length && (
              <div style={{ marginTop: 8, paddingTop: 8, borderTop: `1px solid ${COLORS.border}`, fontSize: 12.5, lineHeight: 1.5 }}>{v.motivazione}</div>
            )}
            {aperta === v.chiave && (v.pagamenti || []).map((p, i) => (
              <div key={`${p.protocollo}-${i}`} style={{ marginTop: 8, paddingTop: 8, borderTop: `1px solid ${COLORS.border}`, fontSize: 12.5, lineHeight: 1.5 }}
                data-testid="scad-pagamento">
                <strong>{dataIt(p.data)}</strong> · <Protocollo numero={p.protocollo} pdfUrl={p.pdf_url} quietanzaId={p.quietanza_id} onApri={onApri} onDettaglio={onDettaglio} /> · {euro(p.importo_cents)}
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
