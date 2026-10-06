import React, { useEffect, useState } from 'react';
import { Badge, Button, PageLoader } from '../ds';
import { COLORS, FONT, formatEuro, useIsMobile } from '../../lib/utils';
import api from '../../api';

/**
 * Registro versamenti F24 — il «Cassetto fiscale» interno (richiesta del
 * titolare del 30/09/2026). Fonte: le quietanze AdE. Per anno di versamento:
 *
 *  - Codici: debito e credito di ogni codice mese per mese, e i mesi di
 *    riferimento non pervenuti per i codici che si versano ogni mese (il
 *    Cassetto non lo dice);
 *  - Crediti: ogni codice a credito con gli F24 che lo hanno scaricato e i
 *    debiti che ha pagato;
 *  - Deleghe: ogni F24 quietanzato, anche a saldo zero (tutto in
 *    compensazione), con da dove e' arrivato (Posta, Drive, Caricato).
 *
 * Sola lettura: i numeri li fa `/api/f24/tributi/versamenti`.
 */

const euro = cents => (cents ? formatEuro(cents / 100) : '—');
const dataIt = iso => {
  const [a, m, g] = String(iso || '').slice(0, 10).split('-');
  return a && m && g ? `${g}/${m}/${a}` : '—';
};
const MESI_LUNGHI = ['gennaio', 'febbraio', 'marzo', 'aprile', 'maggio', 'giugno', 'luglio', 'agosto',
  'settembre', 'ottobre', 'novembre', 'dicembre'];
const ORIGINE_LABEL = { posta: 'Posta', drive: 'Drive', caricato: 'Caricato', altro: 'Altro' };

const selettore = {
  minHeight: 44, padding: '0 10px', borderRadius: 8, border: `1px solid ${COLORS.border}`,
  background: COLORS.card, fontSize: 14, fontFamily: FONT.family, color: COLORS.text,
};
const riquadro = { background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 12 };
const num = { fontFamily: FONT.mono, fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' };
const th = {
  padding: '8px 8px', fontSize: 11, fontWeight: 700, color: COLORS.textMuted, textTransform: 'uppercase',
  borderBottom: `1px solid ${COLORS.border}`, textAlign: 'right', whiteSpace: 'nowrap',
};

function Origini({ origini }) {
  return (origini || []).map(o => <Badge key={o} variant="neutral" style={{ marginRight: 4 }}>{ORIGINE_LABEL[o] || o}</Badge>);
}

function Cella({ debito, credito }) {
  if (!debito && !credito) return <span style={{ color: COLORS.textSubtle }}>—</span>;
  return (
    <>
      {debito > 0 && <div style={num}>{euro(debito)}</div>}
      {credito > 0 && <div style={{ ...num, color: COLORS.success }}>−{euro(credito)}</div>}
    </>
  );
}

function Mancanti({ codice }) {
  if (!codice.mancanti?.length) return null;
  return (
    <div role="alert" style={{ color: COLORS.danger, fontSize: 12, marginTop: 2 }} data-testid={`mancanti-${codice.chiave}`}>
      Non pervenuto: {codice.mancanti.map(m => MESI_LUNGHI[m - 1]).join(', ')}
    </div>
  );
}

function Codici({ dati, isMobile }) {
  const codici = dati.codici || [];
  if (!codici.length) return <Vuoto testo="Nessuna quietanza in questo anno." />;
  if (isMobile) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }} data-testid="versamenti-card">
        {codici.map(c => (
          <div key={c.chiave} style={{ ...riquadro, padding: '10px 12px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
              <strong>{c.codice}</strong>
              <span style={num}>{euro(c.debito_cents)}{c.credito_cents > 0 && <span style={{ color: COLORS.success }}> · −{euro(c.credito_cents)}</span>}</span>
            </div>
            <div style={{ fontSize: 12, color: COLORS.textMuted }}>{c.descrizione}</div>
            <Mancanti codice={c} />
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 6, marginTop: 6, fontSize: 11.5 }}>
              {c.mesi.filter(m => m.debito_cents || m.credito_cents).map(m => (
                <div key={m.mese}>
                  <div style={{ color: COLORS.textMuted }}>{dati.mesi[m.mese - 1]}</div>
                  <Cella debito={m.debito_cents} credito={m.credito_cents} />
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    );
  }
  return (
    <div style={{ ...riquadro, overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }} data-testid="tabella-versamenti">
        <thead>
          <tr style={{ background: COLORS.bgAlt }}>
            <th style={{ ...th, textAlign: 'left' }}>Codice</th>
            {dati.mesi.map(m => <th key={m} style={th}>{m}</th>)}
            <th style={th}>Debito</th>
            <th style={th}>Credito</th>
          </tr>
        </thead>
        <tbody>
          {codici.map(c => (
            <tr key={c.chiave} style={{ borderTop: `1px solid ${COLORS.gray[100]}` }} data-testid={`codice-${c.chiave}`}>
              <td style={{ padding: '6px 8px', minWidth: 180, maxWidth: 260 }}>
                <strong>{c.codice}</strong>
                <div style={{ fontSize: 11, color: COLORS.textMuted }}>{c.descrizione}</div>
                <Mancanti codice={c} />
              </td>
              {c.mesi.map(m => (
                <td key={m.mese} style={{ padding: '6px 8px', textAlign: 'right', verticalAlign: 'top',
                  background: c.mancanti?.includes(m.mese) ? COLORS.dangerLight : undefined }}>
                  <Cella debito={m.debito_cents} credito={m.credito_cents} />
                </td>
              ))}
              <td style={{ padding: '6px 8px', textAlign: 'right', ...num, fontWeight: 700 }}>{euro(c.debito_cents)}</td>
              <td style={{ padding: '6px 8px', textAlign: 'right', ...num, fontWeight: 700, color: COLORS.success }}>{euro(c.credito_cents)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ padding: '8px 10px', fontSize: 12, color: COLORS.textMuted }}>
        Colonne = mese del versamento (data della quietanza). «Non pervenuto» = mese di riferimento già scaduto
        (il 16 del mese dopo) senza versamento, per i codici versati almeno 3 mesi nell'anno.
      </div>
    </div>
  );
}

function Crediti({ dati, onApri }) {
  const crediti = dati.crediti || [];
  if (!crediti.length) return <Vuoto testo="Nessun credito usato in compensazione in questo anno." />;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }} data-testid="crediti-f24">
      {crediti.map(k => (
        <div key={k.chiave} style={{ ...riquadro, padding: '10px 12px' }} data-testid={`credito-${k.chiave}`}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
            <div>
              <strong>{k.codice}</strong>{k.anno_riferimento && <> · anno {k.anno_riferimento}</>}
              <div style={{ fontSize: 12, color: COLORS.textMuted }}>{k.descrizione}</div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: 11, color: COLORS.textMuted }}>Utilizzato in compensazione</div>
              <div style={{ ...num, fontWeight: 700, color: COLORS.success }}>{euro(k.utilizzato_cents)}</div>
            </div>
          </div>
          {k.utilizzi.map((u, i) => (
            <div key={`${u.protocollo}-${i}`} style={{ marginTop: 8, paddingTop: 8, borderTop: `1px solid ${COLORS.border}`, fontSize: 12.5, lineHeight: 1.5 }}>
              <strong>{dataIt(u.data)}</strong> · <Protocollo numero={u.protocollo} pdfUrl={u.pdf_url} onApri={onApri} /> · usati {euro(u.importo_cents)}
              {' '}(progressivo {euro(u.utilizzato_progressivo_cents)}) · <Origini origini={u.origini} />
              {u.compensazione_totale && <Badge variant="info">F24 a saldo zero</Badge>}
              <div>Ha pagato: {u.debiti_compensati.map(d => `${d.codice} ${d.periodo} ${euro(d.importo_cents)}`).join(' · ') || '—'}
                {!u.compensazione_totale && <> · saldo versato {euro(u.saldo_delega_cents)}</>}</div>
              {u.pdf_url && (
                <Button size="sm" variant="secondary" style={{ minHeight: 36, marginTop: 4 }}
                  onClick={() => onApri(u.pdf_url, `Quietanza ${u.protocollo || ''}`)}>Apri quietanza</Button>
              )}
            </div>
          ))}
        </div>
      ))}
      <div style={{ fontSize: 12, color: COLORS.textMuted }}>
        Il credito spettante lo dichiara il commercialista (dichiarazione): qui c'è quanto è stato usato, delega per delega.
      </div>
    </div>
  );
}

// Il protocollo e' il modo di arrivare all'originale: se c'e' il PDF si apre da qui.
function Protocollo({ numero, pdfUrl, onApri }) {
  if (!pdfUrl) return <>protocollo {numero || '—'}</>;
  const apri = e => { e.stopPropagation(); onApri(pdfUrl, `Quietanza ${numero || ''}`); };
  return (
    <>protocollo{' '}
      <span role="link" tabIndex={0} onClick={apri}
        onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); apri(e); } }}
        title="Apri la delega originale" data-testid="apri-protocollo"
        style={{ color: COLORS.primary, textDecoration: 'underline', cursor: 'pointer' }}>{numero || '—'}</span>
    </>
  );
}

function Deleghe({ dati, onApri }) {
  const [aperta, setAperta] = useState(null);
  const deleghe = dati.deleghe || [];
  if (!deleghe.length) return <Vuoto testo="Nessun F24 quietanzato con questi filtri." />;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }} data-testid="deleghe-f24">
      {deleghe.map(d => (
        <div key={d.chiave} style={{ ...riquadro, padding: '10px 12px' }}>
          <button type="button" onClick={() => setAperta(a => (a === d.chiave ? null : d.chiave))} aria-expanded={aperta === d.chiave}
            style={{ all: 'unset', display: 'block', width: '100%', cursor: 'pointer', minHeight: 44 }} data-testid={`delega-${d.chiave}`}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
              <div>
                <strong>{dataIt(d.data)}</strong> · <Protocollo numero={d.protocollo} pdfUrl={d.pdf_url} onApri={onApri} />
                <div style={{ marginTop: 2 }}><Origini origini={d.origini} />
                  {d.compensazione_totale && <Badge variant="info">Saldo zero · tutto in compensazione</Badge>}</div>
              </div>
              <div style={{ textAlign: 'right', fontSize: 12 }}>
                <div>Debito <span style={num}>{euro(d.debito_cents)}</span></div>
                <div style={{ color: COLORS.success }}>Credito <span style={num}>{euro(d.credito_cents)}</span></div>
                <div><strong>Saldo <span style={num}>{d.saldo_cents === 0 ? formatEuro(0) : euro(d.saldo_cents)}</span></strong></div>
              </div>
            </div>
          </button>
          {aperta === d.chiave && (
            <div style={{ marginTop: 8, fontSize: 12.5 }}>
              {d.righe.map((r, i) => (
                <div key={`${r.codice}-${i}`} style={{ display: 'flex', justifyContent: 'space-between', gap: 8, padding: '3px 0', borderTop: `1px solid ${COLORS.gray[100]}` }}>
                  <span><strong>{r.codice}</strong> {r.periodo}</span>
                  <span style={num}>{r.debito_cents > 0 && euro(r.debito_cents)}{r.credito_cents > 0 && <span style={{ color: COLORS.success }}>−{euro(r.credito_cents)}</span>}</span>
                </div>
              ))}
              {d.pdf_url && (
                <Button size="sm" variant="secondary" style={{ minHeight: 36, marginTop: 6 }}
                  onClick={() => onApri(d.pdf_url, `Quietanza ${d.protocollo || ''}`)}>Apri quietanza</Button>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function Vuoto({ testo }) {
  return <div style={{ ...riquadro, padding: 30, textAlign: 'center', color: COLORS.textMuted }}>{testo}</div>;
}

export default function RegistroVersamenti({ vista, anno, origine, imposta, onApri }) {
  const isMobile = useIsMobile(1024);
  const [dati, setDati] = useState(null);
  const [errore, setErrore] = useState('');

  useEffect(() => {
    let attivo = true;
    setErrore('');
    const qs = new URLSearchParams();
    if (anno) qs.set('anno', anno);
    if (origine) qs.set('origine', origine);
    api.get(`/api/f24/tributi/versamenti?${qs}`)
      .then(r => { if (attivo) setDati(r.data); })
      .catch(e => { if (attivo) setErrore(e.response?.data?.detail || e.message || 'Lettura non riuscita'); });
    return () => { attivo = false; };
  }, [anno, origine]);

  const t = dati?.totali || {};
  return (
    <div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 12 }} data-testid="filtri-versamenti">
        <select aria-label="Anno di versamento" value={anno || dati?.anno || ''} onChange={e => imposta('anno', e.target.value)} style={selettore}>
          {(dati?.anni || []).map(a => <option key={a} value={a}>{a}</option>)}
        </select>
        <select aria-label="Arrivato da" value={origine} onChange={e => imposta('origine', e.target.value)} style={selettore}>
          <option value="">Posta, Drive e caricati</option>
          {(dati?.origini || []).map(o => <option key={o.id} value={o.id}>{o.label} ({o.deleghe})</option>)}
        </select>
      </div>
      {errore && <div role="alert" style={{ color: COLORS.danger, marginBottom: 12 }}>{errore}</div>}
      {!dati && !errore && <PageLoader />}
      {dati && (
        <>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, marginBottom: 12, fontSize: 13 }} data-testid="totali-versamenti">
            <span>{t.deleghe || 0} F24 quietanzati{t.compensate_saldo_zero ? ` (${t.compensate_saldo_zero} a saldo zero)` : ''}</span>
            <span>Debito <strong style={num}>{euro(t.debito_cents)}</strong></span>
            <span style={{ color: COLORS.success }}>Credito <strong style={num}>{euro(t.credito_cents)}</strong></span>
            <span>Versato <strong style={num}>{euro(t.saldo_cents)}</strong></span>
            {t.codici_con_mancanti > 0 && <span style={{ color: COLORS.danger }}><strong>{t.codici_con_mancanti}</strong> codici con mesi non pervenuti</span>}
          </div>
          {vista === 'versamenti' && <Codici dati={dati} isMobile={isMobile} />}
          {vista === 'crediti' && <Crediti dati={dati} onApri={onApri} />}
          {vista === 'deleghe' && <Deleghe dati={dati} onApri={onApri} />}
        </>
      )}
    </div>
  );
}
