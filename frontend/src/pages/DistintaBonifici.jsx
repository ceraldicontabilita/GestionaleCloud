import React, { useEffect, useMemo, useState } from 'react';
import { Download, RefreshCw } from 'lucide-react';
import api from '../api';
import { COLORS, formatEuroD, formatDateIT, useIsMobile } from '../lib/utils';
import { PageHeader } from '../components/ds/PageHeader';

/**
 * Distinta bonifici fornitori: si scelgono le fatture aperte e si scarica il
 * file SEPA (pain.001) da caricare nell'home banking. Il gestionale non paga:
 * la fattura resta aperta finché l'addebito non arriva sull'estratto conto.
 * IBAN e nome dell'ordinante restano solo in questo browser.
 */

const MOTIVI = {
  iban_mancante: 'IBAN non trovato',
  nota_di_credito: 'Nota di credito',
  gia_pagata_o_annullata: 'Già pagata o annullata',
  residuo_zero: 'Niente da pagare',
  fattura_non_attiva: 'Fattura non attiva',
  fattura_non_trovata: 'Fattura non trovata',
};
const FONTI = {
  anagrafica_fornitore: 'Anagrafica',
  xml_fattura: 'XML fattura',
  fattura_precedente: 'Fattura precedente',
};
const motivo = m => MOTIVI[m] || (m?.startsWith('iban_non_valido') ? 'IBAN con cifra di controllo sbagliata' : m);
const RIGHE_PAGINA = 200;

function leggi(chiave) {
  try { return window.localStorage.getItem(chiave) || ''; } catch { return ''; }
}
function scrivi(chiave, valore) {
  try { window.localStorage.setItem(chiave, valore); } catch { /* browser senza storage */ }
}
function domani() {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return d.toISOString().slice(0, 10);
}

const cella = { padding: '8px 10px', borderBottom: `1px solid ${COLORS.border}`, fontSize: 13 };
const numero = { ...cella, textAlign: 'right', fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' };
const campo = { minHeight: 44, padding: '0 10px', border: `1px solid ${COLORS.border}`, borderRadius: 8, background: COLORS.card, color: COLORS.text, fontSize: 14, width: '100%', boxSizing: 'border-box' };

export default function DistintaBonifici() {
  const isMobile = useIsMobile();
  const [fatture, setFatture] = useState([]);
  const [scelte, setScelte] = useState(() => new Set());
  const [cerca, setCerca] = useState('');
  const [mostra, setMostra] = useState(RIGHE_PAGINA);
  const [anteprima, setAnteprima] = useState(null);
  const [iban, setIban] = useState(() => leggi('distinta.iban_ordinante'));
  const [nome, setNome] = useState(() => leggi('distinta.nome_ordinante'));
  const [data, setData] = useState(domani);
  const [stato, setStato] = useState({ loading: true, errore: '' });

  const carica = async () => {
    setStato({ loading: true, errore: '' });
    try {
      const res = await api.get('/api/distinta-bonifici/candidate');
      setFatture(res.data?.fatture || []);
      setStato({ loading: false, errore: '' });
    } catch (err) {
      setStato({ loading: false, errore: err?.response?.data?.detail || err.message || 'Caricamento non riuscito' });
    }
  };
  useEffect(() => { carica(); }, []);

  const filtrate = useMemo(() => {
    const q = cerca.trim().toLowerCase();
    if (!q) return fatture;
    return fatture.filter(f => `${f.fornitore} ${f.numero} ${f.partita_iva}`.toLowerCase().includes(q));
  }, [fatture, cerca]);

  const ids = [...scelte];
  useEffect(() => {
    if (!ids.length) { setAnteprima(null); return; }
    let vivo = true;
    api.post('/api/distinta-bonifici/anteprima', { fattura_ids: ids })
      .then(res => { if (vivo) setAnteprima(res.data); })
      .catch(err => { if (vivo) setStato(s => ({ ...s, errore: err?.response?.data?.detail || err.message })); });
    return () => { vivo = false; };
  }, [scelte]);

  const alterna = id => setScelte(prec => {
    const nuovo = new Set(prec);
    if (nuovo.has(id)) nuovo.delete(id); else nuovo.add(id);
    return nuovo;
  });

  const scarica = async () => {
    setStato(s => ({ ...s, errore: '' }));
    scrivi('distinta.iban_ordinante', iban);
    scrivi('distinta.nome_ordinante', nome);
    try {
      const res = await api.post('/api/distinta-bonifici/xml', {
        fattura_ids: ids, iban_ordinante: iban, nome_ordinante: nome, data_esecuzione: data,
      }, { responseType: 'blob' });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = `distinta_bonifici_${data}.xml`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      let messaggio = err.message;
      try { messaggio = JSON.parse(await err.response.data.text()).detail || messaggio; } catch { /* risposta non JSON */ }
      setStato(s => ({ ...s, errore: messaggio }));
    }
  };

  const totaleScelto = anteprima ? formatEuroD(Number(anteprima.totale)) : '—';
  const senzaIban = fatture.filter(f => !f.iban).length;

  return (
    <div style={{ padding: '14px clamp(10px, 3vw, 28px)', maxWidth: 1100, margin: '0 auto' }}>
      <PageHeader
        title="Distinta bonifici"
        subtitle="Scegli le fatture da pagare e scarica il file per la banca: il pagamento lo fai tu nell'home banking."
        pastiglie={[
          { etichetta: 'Fatture aperte', valore: String(fatture.length), nota: 'attive, non pagate, con residuo' },
          { etichetta: 'Senza IBAN', valore: String(senzaIban), nota: "da completare in anagrafica", tono: senzaIban ? 'attenzione' : 'ok' },
          { etichetta: 'In distinta', valore: totaleScelto, nota: anteprima ? `${anteprima.numero_bonifici} bonifici` : 'nessuna fattura scelta' },
        ]}
        actions={
          <button type="button" onClick={carica} disabled={stato.loading}
            style={{ minHeight: 44, display: 'inline-flex', alignItems: 'center', gap: 6, background: COLORS.card, color: COLORS.text, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: '0 14px', fontWeight: 700, cursor: 'pointer' }}>
            <RefreshCw size={16} /> Rileggi
          </button>
        }
        style={{ marginBottom: 14 }}
      />

      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '2fr 2fr 1fr', gap: 10, marginBottom: 12 }}>
        <label style={{ fontSize: 12, fontWeight: 700, color: COLORS.textMuted }}>IBAN ordinante
          <input style={campo} value={iban} onChange={e => setIban(e.target.value.toUpperCase())} placeholder="IT.." />
        </label>
        <label style={{ fontSize: 12, fontWeight: 700, color: COLORS.textMuted }}>Nome ordinante
          <input style={campo} value={nome} onChange={e => setNome(e.target.value)} />
        </label>
        <label style={{ fontSize: 12, fontWeight: 700, color: COLORS.textMuted }}>Data esecuzione
          <input style={campo} type="date" value={data} onChange={e => setData(e.target.value)} />
        </label>
      </div>

      {anteprima && (
        <div style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 12, padding: 12, marginBottom: 12 }}>
          {anteprima.bonifici.map(b => (
            <div key={b.iban + b.partita_iva} style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap', padding: '6px 0', borderBottom: `1px solid ${COLORS.border}` }}>
              <span><b>{b.fornitore}</b> · <span style={{ fontFamily: 'ui-monospace, Menlo, monospace', fontSize: 12 }}>{b.iban}</span><br />
                <span style={{ fontSize: 12, color: COLORS.textMuted }}>{b.causale}</span></span>
              <b style={{ fontVariantNumeric: 'tabular-nums' }}>{formatEuroD(Number(b.importo))}</b>
            </div>
          ))}
          {anteprima.scartate.map(s => (
            <div key={s.id} style={{ fontSize: 12, color: COLORS.danger, paddingTop: 6 }}>
              Esclusa: {s.fornitore || s.id} {s.numero ? `n. ${s.numero}` : ''} — {motivo(s.motivo)}
            </div>
          ))}
          <button type="button" onClick={scarica} disabled={!anteprima.numero_bonifici}
            style={{ marginTop: 10, minHeight: 44, display: 'inline-flex', alignItems: 'center', gap: 6, background: COLORS.primary, color: COLORS.card, border: 'none', borderRadius: 8, padding: '0 16px', fontWeight: 700, cursor: 'pointer', opacity: anteprima.numero_bonifici ? 1 : 0.5 }}>
            <Download size={16} /> Scarica il file per la banca
          </button>
        </div>
      )}

      <input style={{ ...campo, marginBottom: 10 }} value={cerca} onChange={e => setCerca(e.target.value)}
        placeholder="Cerca fornitore, numero o P.IVA" aria-label="Cerca fattura" />

      {stato.errore && (
        <div role="alert" style={{ padding: 12, border: `1px solid ${COLORS.danger}`, borderRadius: 10, color: COLORS.danger, marginBottom: 10 }}>{stato.errore}</div>
      )}

      {stato.loading ? (
        <div style={{ padding: 30, textAlign: 'center', color: COLORS.textMuted }}>Caricamento…</div>
      ) : isMobile ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {filtrate.slice(0, mostra).map(f => (
            <label key={f.id} style={{ display: 'flex', gap: 10, alignItems: 'center', minHeight: 44, background: COLORS.card, border: `1px solid ${scelte.has(f.id) ? COLORS.primary : COLORS.border}`, borderRadius: 10, padding: '8px 12px' }}>
              <input type="checkbox" checked={scelte.has(f.id)} disabled={!f.iban} onChange={() => alterna(f.id)} style={{ width: 22, height: 22 }} />
              <span style={{ flex: 1, minWidth: 0 }}>
                <b style={{ fontSize: 13 }}>{f.fornitore}</b><br />
                <span style={{ fontSize: 12, color: COLORS.textMuted }}>n. {f.numero} · {formatDateIT(f.data)} · {f.iban ? FONTI[f.fonte_iban] : motivo(f.fonte_iban)}</span>
              </span>
              <b style={{ fontVariantNumeric: 'tabular-nums' }}>{formatEuroD(Number(f.importo))}</b>
            </label>
          ))}
        </div>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse', background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 12 }}>
          <thead>
            <tr style={{ textAlign: 'left', color: COLORS.textMuted, fontSize: 12 }}>
              <th style={cella} aria-label="Scegli" />
              <th style={cella}>Data</th><th style={cella}>Fornitore</th><th style={cella}>Numero</th>
              <th style={cella}>IBAN</th><th style={{ ...cella, textAlign: 'right' }}>Da pagare</th>
            </tr>
          </thead>
          <tbody>
            {filtrate.slice(0, mostra).map(f => (
              <tr key={f.id} style={{ background: scelte.has(f.id) ? COLORS.primarySoft : undefined }}>
                <td style={cella}>
                  <input type="checkbox" checked={scelte.has(f.id)} disabled={!f.iban} onChange={() => alterna(f.id)}
                    aria-label={`Scegli fattura ${f.numero} di ${f.fornitore}`} style={{ width: 20, height: 20 }} />
                </td>
                <td style={cella}>{formatDateIT(f.data)}</td>
                <td style={cella}>{f.fornitore}</td>
                <td style={cella}>{f.numero}</td>
                <td style={{ ...cella, fontSize: 12, color: f.iban ? COLORS.text : COLORS.danger }}>
                  {f.iban ? `${f.iban} (${FONTI[f.fonte_iban] || f.fonte_iban})` : motivo(f.fonte_iban)}
                </td>
                <td style={numero}>{formatEuroD(Number(f.importo))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {filtrate.length > mostra && (
        <button type="button" onClick={() => setMostra(m => m + RIGHE_PAGINA)}
          style={{ marginTop: 10, minHeight: 44, width: '100%', background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 8, fontWeight: 700, cursor: 'pointer' }}>
          Mostra altre
        </button>
      )}
    </div>
  );
}
