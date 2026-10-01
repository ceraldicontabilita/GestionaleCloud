import React, { useEffect, useState } from 'react';
import { Badge, PageLoader } from '../ds';
import { COLORS, FONT, useIsMobile } from '../../lib/utils';
import api from '../../api';

/**
 * Termini di recupero (richiesta del 01/10/2026): per ogni tributo che risulta
 * non versato (o con l'F24 ma senza quietanza), entro quando l'ente — Agenzia,
 * INPS, Comune — puo' ancora chiederlo. Sola lettura: i termini li calcola la
 * vista `verifica.tabulato_tributi_termini`, che il backend legge da
 * `/api/f24/tributi/termini`. Si parte dalle righe senza versamento, la piu'
 * vicina a scadere per prima; sotto i 120 giorni la riga e' in rosso, con la
 * scritta (il colore non e' mai l'unica informazione).
 *
 * I termini sono indicativi: il banner in cima resta sempre visibile.
 */

export const AVVISO_TERMINI = 'Termini indicativi, da confermare con il commercialista.';
const RIGHE_PER_PAGINA = 200;
const SOGLIA_GIORNI = 120;

const dataIt = iso => {
  const [a, m, g] = String(iso || '').slice(0, 10).split('-');
  return a && m && g ? `${g}/${m}/${a}` : '—';
};
const giorniTesto = n => (n === 1 ? '1 giorno' : `${n} giorni`);
const VARIANTE_SITUAZIONE = { ANCORA_RECUPERABILE: 'warning', TERMINE_SCADUTO: 'neutral', DA_VERIFICARE: 'info' };

const selettore = {
  minHeight: 44, padding: '0 10px', borderRadius: 8, border: `1px solid ${COLORS.border}`,
  background: COLORS.card, fontSize: 14, fontFamily: FONT.family, color: COLORS.text,
};
const cella = { padding: '8px 10px', borderBottom: `1px solid ${COLORS.border}`, verticalAlign: 'top', textAlign: 'left' };

function Situazione({ voce }) {
  if (!voce.situazione) return <span style={{ color: COLORS.textMuted }}>—</span>;
  return (
    <span style={{ display: 'inline-flex', flexDirection: 'column', gap: 4, alignItems: 'flex-start' }}>
      <Badge variant={VARIANTE_SITUAZIONE[voce.situazione] || 'neutral'}>{voce.situazione_label}</Badge>
      {voce.urgente && (
        <Badge variant="danger">Meno di {SOGLIA_GIORNI} giorni: {giorniTesto(voce.giorni_rimasti)}</Badge>
      )}
    </span>
  );
}

function Entro({ voce }) {
  return (
    <span style={{ whiteSpace: 'nowrap' }}>
      <strong>{dataIt(voce.recuperabile_entro)}</strong>
      {voce.giorni_rimasti != null && (
        <span style={{ color: voce.urgente ? COLORS.danger : COLORS.textMuted, fontWeight: voce.urgente ? 700 : 400 }}>
          {' · '}{giorniTesto(voce.giorni_rimasti)}
        </span>
      )}
    </span>
  );
}

export default function TerminiRecupero() {
  const isMobile = useIsMobile(1024);
  const [dati, setDati] = useState(null);
  const [errore, setErrore] = useState('');
  const [stato, setStato] = useState('');
  const [situazione, setSituazione] = useState('');
  const [codice, setCodice] = useState('');
  const [cercaTesto, setCercaTesto] = useState('');
  const [cerca, setCerca] = useState('');
  const [mostrate, setMostrate] = useState(RIGHE_PER_PAGINA);

  useEffect(() => {
    const t = setTimeout(() => setCerca(cercaTesto.trim()), 300);
    return () => clearTimeout(t);
  }, [cercaTesto]);

  useEffect(() => {
    let attivo = true;
    setErrore('');
    const qs = new URLSearchParams();
    if (stato) qs.set('stato', stato);
    if (situazione) qs.set('situazione', situazione);
    if (codice) qs.set('codice', codice);
    if (cerca) qs.set('cerca', cerca);
    api.get(`/api/f24/tributi/termini?${qs}`)
      .then(r => { if (attivo) { setDati(r.data); setMostrate(RIGHE_PER_PAGINA); } })
      .catch(e => { if (attivo) setErrore(e.response?.data?.detail || e.message || 'Lettura non riuscita'); });
    return () => { attivo = false; };
  }, [stato, situazione, codice, cerca]);

  const voci = dati?.voci || [];
  const visibili = voci.slice(0, mostrate);
  const rimanenti = voci.length - visibili.length;
  const conteggi = dati?.conteggi || {};
  const primo = dati?.primo_termine;

  return (
    <div data-testid="termini-recupero">
      <div role="note" data-testid="avviso-termini" style={{
        background: COLORS.warningLight, color: COLORS.warning, border: `1px solid ${COLORS.accentLight}`,
        borderRadius: 10, padding: '10px 12px', marginBottom: 12, fontSize: 14, lineHeight: 1.45,
      }}>
        <strong>{AVVISO_TERMINI}</strong>{' '}
        Un atto già notificato, una sospensione o la denuncia di un lavoratore possono allungarli.
      </div>

      {dati && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 12 }} data-testid="riepilogo-termini">
          <Badge variant="warning">Ancora recuperabili: {conteggi.ancora_recuperabili ?? 0}</Badge>
          <Badge variant={conteggi.urgenti ? 'danger' : 'neutral'}>Sotto i {SOGLIA_GIORNI} giorni: {conteggi.urgenti ?? 0}</Badge>
          <Badge variant="neutral">Termine scaduto: {conteggi.scadute ?? 0}</Badge>
          {conteggi.da_verificare ? <Badge variant="info">Termine non determinabile: {conteggi.da_verificare}</Badge> : null}
          {primo && (
            <span style={{ fontSize: 13, color: COLORS.textMuted, alignSelf: 'center' }}>
              Primo termine: <strong>{dataIt(primo.recuperabile_entro)}</strong> ({giorniTesto(primo.giorni_rimasti)}) · {primo.codice} {primo.periodo}
            </span>
          )}
        </div>
      )}

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 12 }} data-testid="filtri-termini">
        <select aria-label="Esito del controllo" value={stato} onChange={e => setStato(e.target.value)} style={selettore}>
          <option value="">Versamento mancante (predefinito)</option>
          <option value="TUTTI">Tutti i tributi</option>
          {(dati?.facets?.stati || []).map(s => <option key={s.id} value={s.id}>{s.label} ({s.n})</option>)}
        </select>
        <select aria-label="Situazione del termine" value={situazione} onChange={e => setSituazione(e.target.value)} style={selettore}>
          <option value="">Tutte le situazioni</option>
          {(dati?.facets?.situazioni || []).map(s => <option key={s.id} value={s.id}>{s.label} ({s.n})</option>)}
        </select>
        <select aria-label="Codice tributo" value={codice} onChange={e => setCodice(e.target.value)} style={selettore}>
          <option value="">Tutti i codici</option>
          {(dati?.facets?.codici || []).map(c => <option key={c.id} value={c.id}>{c.id} ({c.n})</option>)}
        </select>
        <input
          aria-label="Cerca codice, tributo o periodo" value={cercaTesto} onChange={e => setCercaTesto(e.target.value)}
          placeholder="Codice, tributo o periodo" style={{ ...selettore, flex: '1 1 200px', minWidth: 0 }}
        />
      </div>

      {errore && <div role="alert" style={{ color: COLORS.danger, marginBottom: 12 }}>{errore}</div>}
      {!dati && !errore && <PageLoader />}
      {dati && voci.length === 0 && (
        <div style={{ padding: 30, textAlign: 'center', color: COLORS.textMuted, background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 12 }}>
          Nessun tributo con questi filtri.
        </div>
      )}

      {dati && voci.length > 0 && (isMobile ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }} data-testid="termini-card">
          {visibili.map(v => (
            <div key={v.chiave} data-testid="termine-riga" data-urgente={v.urgente ? 'si' : 'no'} style={{
              background: v.urgente ? COLORS.dangerLight : COLORS.card,
              border: `1px solid ${v.urgente ? COLORS.danger : COLORS.border}`, borderRadius: 12, padding: '10px 12px',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
                <strong>{v.codice} · {v.periodo}</strong>
                <Situazione voce={v} />
              </div>
              <div style={{ fontSize: 12.5, color: COLORS.textMuted, margin: '2px 0 6px' }}>{v.tributo}</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 12px', fontSize: 12.5 }}>
                <div><div style={{ color: COLORS.textMuted }}>Scadenza</div>{dataIt(v.scadenza)}</div>
                <div><div style={{ color: COLORS.textMuted }}>Termine ordinario</div>{dataIt(v.termine_ordinario)}</div>
                <div><div style={{ color: COLORS.textMuted }}>Esito</div>{v.esito || v.stato_label}</div>
                <div><div style={{ color: COLORS.textMuted }}>Recuperabile entro</div><Entro voce={v} /></div>
              </div>
              <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 6 }}>{v.slittamento_covid}</div>
            </div>
          ))}
        </div>
      ) : (
        <div style={{ overflowX: 'auto', background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 12 }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }} data-testid="tabella-termini">
            <thead>
              <tr style={{ background: COLORS.bgAlt }}>
                {['Codice', 'Tributo', 'Periodo', 'Scadenza', 'Esito', 'Termine ordinario', 'Slittamento Covid', 'Recuperabile entro', 'Situazione'].map(h => (
                  <th key={h} scope="col" style={{ ...cella, color: COLORS.textMuted, fontWeight: 600 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {visibili.map(v => (
                <tr key={v.chiave} data-testid="termine-riga" data-urgente={v.urgente ? 'si' : 'no'}
                  style={{ background: v.urgente ? COLORS.dangerLight : 'transparent' }}>
                  <td style={cella}><strong>{v.codice}</strong></td>
                  <td style={cella}>{v.tributo}</td>
                  <td style={cella}>{v.periodo}</td>
                  <td style={cella}>{dataIt(v.scadenza)}</td>
                  <td style={cella}>{v.esito || v.stato_label}</td>
                  <td style={cella}>{dataIt(v.termine_ordinario)}</td>
                  <td style={cella}>{v.slittamento_covid || '—'}</td>
                  <td style={cella}><Entro voce={v} /></td>
                  <td style={cella}><Situazione voce={v} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}

      {rimanenti > 0 && (
        <div style={{ textAlign: 'center', marginTop: 10 }}>
          <button type="button" style={{ ...selettore, cursor: 'pointer' }} onClick={() => setMostrate(n => n + RIGHE_PER_PAGINA)}>
            Mostra altre · {rimanenti} rimanenti
          </button>
        </div>
      )}
    </div>
  );
}
