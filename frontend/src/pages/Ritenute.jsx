import React, { useEffect, useState } from 'react';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { formatEuroD, formatDateIT, useIsMobile } from '../lib/utils';

/**
 * RITENUTE D'ACCONTO (richiesta utente 18/07/2026): le fatture con
 * DatiRitenuta (RT01/RT02) generano una riga con scadenza al 16 del mese
 * successivo; l'F24 con codice 1040 viene associato e la riga classificata:
 * puntuale, con ravvedimento (8906+1989), in ritardo senza ravvedimento.
 */

const BLU = '#0f2744';
const STATI = {
  da_pagare: { label: 'Da pagare', bg: '#fef3c7', fg: '#92400e' },
  scaduta_da_versare: { label: '⚠️ SCADUTA da versare', bg: '#fee2e2', fg: '#991b1b' },
  f24_associato_da_pagare: { label: 'F24 trovato, banca da verificare', bg: '#dbeafe', fg: '#1e40af' },
  da_verificare_associazione_f24: { label: 'Più F24 compatibili: verifica', bg: '#fef3c7', fg: '#92400e' },
  pagata_puntuale: { label: '✓ Pagata puntuale', bg: '#dcfce7', fg: '#166534' },
  pagata_con_ravvedimento: { label: 'Pagata con ravvedimento', bg: '#fef9c3', fg: '#854d0e' },
  pagata_in_ritardo_senza_ravvedimento: { label: '⚠️ In ritardo SENZA ravvedimento', bg: '#fee2e2', fg: '#991b1b' },
};

const eur = v => formatEuroD(v || 0);

export default function Ritenute() {
  const { anno } = useAnnoGlobale();
  const isMobile = useIsMobile();
  const [dati, setDati] = useState({ ritenute: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filtroStato, setFiltroStato] = useState('tutti');

  const carica = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await api.get(`/api/ritenute?anno=${anno}`);
      setDati(res.data || { ritenute: [] });
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || 'Caricamento non riuscito');
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { carica(); }, [anno]);

  const badge = stato => {
    const s = STATI[stato] || { label: stato || '—', bg: '#f1f5f9', fg: '#334155' };
    return (
      <span style={{ background: s.bg, color: s.fg, borderRadius: 6, padding: '3px 9px', fontSize: 11.5, fontWeight: 700, whiteSpace: 'nowrap' }}>
        {s.label}
      </span>
    );
  };

  const tutteLeRighe = dati.ritenute || [];
  const righe = filtroStato === 'tutti'
    ? tutteLeRighe
    : tutteLeRighe.filter(r => r.stato === filtroStato);

  return (
    <div style={{ padding: '14px clamp(10px, 3vw, 28px)', maxWidth: 1100, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 12 }}>
        <h2 style={{ margin: 0, color: BLU, fontSize: 19 }}>🧾 Ritenute d'acconto {anno}</h2>
        <button
          onClick={carica} disabled={loading}
          style={{ background: BLU, color: 'white', border: 'none', borderRadius: 8, padding: '9px 16px', fontWeight: 700, cursor: 'pointer', opacity: loading ? 0.6 : 1 }}
        >
          {loading ? 'Aggiornamento…' : 'Aggiorna vista'}
        </button>
      </div>

      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
        <label htmlFor="ritenute-stato" style={{ fontSize: 12, fontWeight: 700, color: '#475569' }}>Stato</label>
        <select id="ritenute-stato" value={filtroStato} onChange={e => setFiltroStato(e.target.value)}>
          <option value="tutti">Tutti</option>
          {Object.keys(dati.per_stato || {}).map(stato => (
            <option key={stato} value={stato}>{STATI[stato]?.label || stato}</option>
          ))}
        </select>
        <span style={{ fontSize: 12, color: '#64748b' }}>
          I dati si aggiornano automaticamente dall'importazione Documenti.
        </span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 10, marginBottom: 14 }}>
        <div style={{ background: 'white', border: '1px solid #e2e8f0', borderLeft: `4px solid ${BLU}`, borderRadius: 12, padding: '10px 14px' }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: '#64748b', textTransform: 'uppercase' }}>Ritenute {anno}</div>
          <div style={{ fontSize: 17, fontWeight: 800, color: BLU }}>{tutteLeRighe.length} — {eur(dati.totale_importo)}</div>
        </div>
        {Object.entries(dati.per_stato || {}).map(([st, n]) => (
          <div key={st} style={{ background: 'white', border: '1px solid #e2e8f0', borderRadius: 12, padding: '10px 14px' }}>
            <div style={{ marginBottom: 4 }}>{badge(st)}</div>
            <div style={{ fontSize: 17, fontWeight: 800, color: BLU }}>{n}</div>
          </div>
        ))}
      </div>

      {error ? (
        <div role="alert" style={{ padding: 20, border: '1px solid #ef4444', borderRadius: 10, color: '#991b1b' }}>
          {error} <button onClick={carica}>Riprova</button>
        </div>
      ) : loading ? (
        <div style={{ padding: 30, textAlign: 'center', color: '#6b7280' }}>⏳ Caricamento…</div>
      ) : righe.length === 0 ? (
        <div style={{ background: 'white', border: '1px solid #e2e8f0', borderRadius: 12, padding: 30, textAlign: 'center', color: '#6b7280' }}>
          Nessuna ritenuta trovata nelle fatture {anno} per il filtro selezionato.
        </div>
      ) : isMobile ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {righe.map(r => (
            <div key={r.id} style={{ background: 'white', border: '1px solid #e2e8f0', borderLeft: '4px solid #d97706', borderRadius: 11, padding: '10px 12px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                <b style={{ fontSize: 13, color: BLU }}>{r.fornitore || '—'}</b>
                <b style={{ fontFamily: 'ui-monospace, Menlo, monospace' }}>{eur(r.importo)}</b>
              </div>
              <div style={{ fontSize: 12, color: '#64748b', margin: '4px 0' }}>
                Fatt. {r.numero_fattura} del {formatDateIT(r.data_fattura)} · {r.tipo_label}
                {r.aliquota ? ` ${r.aliquota}%` : ''}{r.causale ? ` · causale ${r.causale}` : ''}
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                <span style={{ fontSize: 12 }}>
                  Scadenza legale <b>{formatDateIT(r.scadenza_legale || r.scadenza)}</b>
                  {r.data_pagamento ? <> · pagata il <b>{formatDateIT(r.data_pagamento)}</b></> : null}
                </span>
                {badge(r.stato)}
              </div>
              {r.f24_id && (
                <div style={{ fontSize: 11.5, color: '#1e40af', marginTop: 4 }}>
                  🔗 F24, riga 1040 {r.f24_periodo ? `(${r.f24_periodo})` : ''}:{' '}
                  {r.f24_descrizione || r.f24_id}
                  <div>
                    Quota {eur(r.f24_quota_ritenuta)}
                    {r.f24_associazione_tipo === 'aggregata'
                      ? ` su riga aggregata ${eur(r.f24_importo_tributo)}`
                      : ''}
                    {r.f24_multi_tributo ? ' · F24 multi-tributo' : ''}
                  </div>
                  {r.stato_evidenza_pagamento !== 'PAGATO_BANCA' && (
                    <div style={{ color: '#92400e' }}>Addebito bancario dell'intero F24 non verificato.</div>
                  )}
                  <div style={{ marginTop: 3 }}>
                    <a href="/riconciliazione/f24">Apri F24</a>
                    {r.movimento_bancario_f24_id ? <> · <a href="/prima-nota">Apri banca/Prima Nota</a></> : null}
                  </div>
                </div>
              )}
              {!r.f24_id && r.stato === 'da_verificare_associazione_f24' && (
                <div style={{ fontSize: 11.5, color: '#92400e', marginTop: 4 }}>
                  Candidati F24: {(r.f24_candidati || []).join(', ') || 'più documenti equivalenti'}
                </div>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div style={{ background: 'white', border: '1px solid #e2e8f0', borderRadius: 12, overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
            <thead>
              <tr style={{ background: '#f8fafc', borderBottom: '2px solid #e2e8f0' }}>
                {['Fornitore', 'Fattura', 'Ritenuta', 'Importo', 'Scadenza (16 mese succ.)', 'Pagata il', 'F24', 'Stato'].map((h, i) => (
                  <th key={h} style={{ padding: '9px 10px', fontSize: 11, color: '#64748b', textTransform: 'uppercase', textAlign: i === 3 ? 'right' : 'left' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {righe.map((r, i) => (
                <tr key={r.id} style={{ borderBottom: '1px solid #f1f5f9', background: i % 2 ? '#f8fafc' : 'white' }}>
                  <td style={{ padding: '8px 10px', fontWeight: 600 }}>{r.fornitore || '—'}</td>
                  <td style={{ padding: '8px 10px', fontFamily: 'monospace', whiteSpace: 'nowrap' }}>
                    {r.numero_fattura} · {formatDateIT(r.data_fattura)}
                  </td>
                  <td style={{ padding: '8px 10px', fontSize: 11.5 }}>
                    {r.tipo}{r.aliquota ? ` ${r.aliquota}%` : ''}{r.causale ? ` (${r.causale})` : ''}
                  </td>
                  <td style={{ padding: '8px 10px', textAlign: 'right', fontWeight: 800, fontFamily: 'ui-monospace, Menlo, monospace' }}>{eur(r.importo)}</td>
                  <td style={{ padding: '8px 10px', whiteSpace: 'nowrap' }}>{formatDateIT(r.scadenza_legale || r.scadenza)}</td>
                  <td style={{ padding: '8px 10px', whiteSpace: 'nowrap' }}>{r.data_pagamento ? formatDateIT(r.data_pagamento) : '—'}</td>
                  <td style={{ padding: '8px 10px', fontSize: 11.5, color: '#1e40af' }}>
                    {r.f24_id ? (
                      <div>
                        <div>🔗 1040 {r.f24_periodo || 'periodo da verificare'}</div>
                        <div>
                          quota {eur(r.f24_quota_ritenuta)}
                          {r.f24_associazione_tipo === 'aggregata'
                            ? ` / riga ${eur(r.f24_importo_tributo)}`
                            : ''}
                        </div>
                        {r.f24_multi_tributo && <div>F24 multi-tributo</div>}
                        {r.stato_evidenza_pagamento !== 'PAGATO_BANCA' && (
                          <div style={{ color: '#92400e' }}>Banca non verificata</div>
                        )}
                      </div>
                    ) : r.stato === 'da_verificare_associazione_f24' ? (
                      <span style={{ color: '#92400e' }}>Più candidati</span>
                    ) : '—'}
                  </td>
                  <td style={{ padding: '8px 10px' }}>{badge(r.stato)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div style={{ marginTop: 14, background: '#fefce8', border: '1px solid #d97706', borderRadius: 10, padding: '10px 14px', fontSize: 12.5, color: '#854d0e' }}>
        📖 <b>Ravvedimento</b>: {dati.logica_ravvedimento || 'sanzione ridotta (codice 8906) + interessi (codice 1989) nello stesso F24 del tributo 1040.'}
      </div>
    </div>
  );
}
