import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { FileText, Download } from 'lucide-react';
import api from '../../api';
import { COLORS } from '../../lib/utils';

const ANNO_CORRENTE = new Date().getFullYear();
const ANNI = [ANNO_CORRENTE, ANNO_CORRENTE - 1, ANNO_CORRENTE - 2];
const MESI = ['Gen','Feb','Mar','Apr','Mag','Giu','Lug','Ago','Set','Ott','Nov','Dic'];

function formatEuro(v) {
  if (v == null || isNaN(v)) return '—';
  return new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' }).format(v);
}

export default function HRCedolini() {
  const { anno: annoParam } = useParams();
  const [anno, setAnno] = useState(Number(annoParam) || ANNO_CORRENTE);
  const [tab, setTab] = useState('buste-paga');
  const [bustePaga, setBustePaga] = useState([]);
  const [f24, setF24] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      api.get('/api/paghe/buste-paga', { params: { anno } }),
      api.get('/api/paghe/distinte-f24', { params: { anno } }),
    ])
      .then(([b, f]) => {
        setBustePaga(Array.isArray(b.data) ? b.data : b.data?.buste_paga || b.data?.cedolini || []);
        setF24(Array.isArray(f.data) ? f.data : f.data?.distinte || []);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [anno]);

  const totaleLordo = bustePaga.reduce((s, b) => s + (Number(b.lordo) || 0), 0);
  const totaleNetto = bustePaga.reduce((s, b) => s + (Number(b.netto) || 0), 0);
  const daPagare = bustePaga.filter(b => !b.pagato).reduce((s, b) => s + (Number(b.netto) || 0), 0);

  return (
    <div style={{ padding: 24 }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: COLORS.text }}>Cedolini & Paghe</h1>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <select
            data-testid="select-anno-cedolini-globale"
            value={anno}
            onChange={e => setAnno(Number(e.target.value))}
            style={{ padding: '8px 14px', border: `1px solid ${COLORS.border}`, borderRadius: 6, fontSize: 14, background: 'white' }}
          >
            {ANNI.map(a => <option key={a} value={a}>{a}</option>)}
          </select>
        </div>
      </div>

      {/* KPI */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 24 }}>
        {[
          { label: 'Cedolini Totali', value: bustePaga.length },
          { label: 'Lordo Annuo', value: formatEuro(totaleLordo) },
          { label: 'Da Pagare', value: formatEuro(daPagare), highlight: daPagare > 0 },
        ].map(s => (
          <div key={s.label} style={{ background: s.highlight ? `${COLORS.primary}08` : 'white', border: `1px solid ${s.highlight ? COLORS.primary + '30' : COLORS.border}`, borderRadius: 10, padding: '16px 20px' }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.textMuted, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{s.label}</div>
            <div style={{ fontSize: 24, fontWeight: 700, color: s.highlight ? COLORS.primary : COLORS.text, marginTop: 6 }}>{s.value}</div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div style={{ background: 'white', border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: 'hidden' }}>
        <div style={{ display: 'flex', borderBottom: `1px solid ${COLORS.border}` }}>
          {[
            { id: 'buste-paga', label: 'Buste Paga' },
            { id: 'f24', label: 'Distinte F24' },
          ].map(t => (
            <button
              key={t.id}
              data-testid={`tab-cedolini-${t.id}`}
              onClick={() => setTab(t.id)}
              style={{
                padding: '12px 20px', background: 'none', border: 'none',
                borderBottom: tab === t.id ? `3px solid ${COLORS.primary}` : '3px solid transparent',
                color: tab === t.id ? COLORS.primary : COLORS.textMuted,
                fontWeight: tab === t.id ? 700 : 400, cursor: 'pointer', fontSize: 13,
                marginBottom: -1,
              }}
            >{t.label}</button>
          ))}
        </div>

        <div style={{ padding: 20 }}>
          {loading && <div style={{ padding: 40, textAlign: 'center', color: COLORS.textMuted }}>Caricamento…</div>}

          {!loading && tab === 'buste-paga' && (
            bustePaga.length === 0
              ? <div style={{ padding: 40, textAlign: 'center', color: COLORS.textMuted }}>Nessuna busta paga per il {anno}</div>
              : <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                  <thead>
                    <tr style={{ background: '#f8fafc' }}>
                      {['Dipendente', 'Mese', 'Lordo', 'Netto', 'Contributi', 'Stato'].map(h => (
                        <th key={h} style={{ padding: '10px 12px', textAlign: 'left', fontSize: 11, fontWeight: 700, color: COLORS.textMuted, textTransform: 'uppercase', borderBottom: `1px solid ${COLORS.border}` }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {bustePaga.map((b, i) => (
                      <tr key={i} style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                        <td style={{ padding: '10px 12px', fontWeight: 600 }}>{b.dipendente_nome || b.nome || '—'}</td>
                        <td style={{ padding: '10px 12px' }}>{MESI[Number(b.mese) - 1] || b.mese || '—'} {b.anno || anno}</td>
                        <td style={{ padding: '10px 12px' }}>{formatEuro(b.lordo)}</td>
                        <td style={{ padding: '10px 12px', fontWeight: 700, color: COLORS.primary }}>{formatEuro(b.netto)}</td>
                        <td style={{ padding: '10px 12px' }}>{formatEuro(b.contributi)}</td>
                        <td style={{ padding: '10px 12px' }}>
                          <span style={{ padding: '3px 10px', borderRadius: 99, fontSize: 11, fontWeight: 600, background: b.pagato ? '#dcfce7' : '#fef9c3', color: b.pagato ? '#16a34a' : '#a16207' }}>
                            {b.pagato ? 'Pagato' : 'Da pagare'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
          )}

          {!loading && tab === 'f24' && (
            f24.length === 0
              ? <div style={{ padding: 40, textAlign: 'center', color: COLORS.textMuted }}>Nessuna distinta F24 per il {anno}</div>
              : <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                  <thead>
                    <tr style={{ background: '#f8fafc' }}>
                      {['Riferimento', 'Mese', 'Importo', 'Scadenza', 'Stato'].map(h => (
                        <th key={h} style={{ padding: '10px 12px', textAlign: 'left', fontSize: 11, fontWeight: 700, color: COLORS.textMuted, textTransform: 'uppercase', borderBottom: `1px solid ${COLORS.border}` }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {f24.map((f, i) => (
                      <tr key={i} style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                        <td style={{ padding: '10px 12px', fontWeight: 600 }}>{f.riferimento || f.codice || `F24 ${i + 1}`}</td>
                        <td style={{ padding: '10px 12px' }}>{MESI[Number(f.mese) - 1] || f.mese || '—'}</td>
                        <td style={{ padding: '10px 12px', fontWeight: 700, color: COLORS.primary }}>{formatEuro(f.importo || f.totale)}</td>
                        <td style={{ padding: '10px 12px' }}>{f.scadenza ? new Date(f.scadenza).toLocaleDateString('it-IT') : '—'}</td>
                        <td style={{ padding: '10px 12px' }}>
                          <span style={{ padding: '3px 10px', borderRadius: 99, fontSize: 11, fontWeight: 600, background: f.pagato ? '#dcfce7' : '#fef9c3', color: f.pagato ? '#16a34a' : '#a16207' }}>
                            {f.pagato ? 'Pagato' : 'Da pagare'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
          )}
        </div>
      </div>
    </div>
  );
}
