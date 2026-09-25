import React, { useCallback, useEffect, useState } from 'react';
import { RefreshCw, Database } from 'lucide-react';
import api from '../api';
import { COLORS } from '../lib/utils';

/**
 * Riquadro «Aggiornamento dati» della Dashboard — SOLA LETTURA.
 *
 * Per ogni fonte (sempre nello stesso ordine: banca, fatture, corrispettivi,
 * cedolini e F24, riconciliazione) mostra l'ultimo giro, l'ultimo dato e i
 * conteggi che il backend legge da dove i motori li scrivono
 * (`GET /api/dashboard/aggiornamento-dati`). Un dato assente e' «non
 * disponibile», mai zero; ogni colore ha anche il suo testo.
 */

const STATI = {
  verde: { etichetta: 'OK', colore: COLORS.success, fondo: COLORS.successLight },
  giallo: { etichetta: 'Attenzione', colore: COLORS.warning, fondo: COLORS.warningLight },
  rosso: { etichetta: 'Fermo', colore: COLORS.danger, fondo: COLORS.dangerLight },
  non_disponibile: { etichetta: 'Non disponibile', colore: COLORS.textMuted, fondo: COLORS.bgAlt },
};

const ETICHETTE_CONTEGGI = {
  movimenti: 'movimenti in archivio',
  file_in_attesa: 'file in attesa',
  fatture: 'fatture',
  importate_ultimo_giro: "importate nell'ultimo giro",
  in_attesa: 'in attesa',
  giornate: 'giornate',
  cedolini: 'cedolini',
  f24: 'F24',
  cedolini_illeggibili: 'cedolini illeggibili',
  assegni: 'assegni collegati',
  stipendi: 'stipendi collegati',
  bonifici: 'bonifici collegati',
};

export function dataOra(iso) {
  if (!iso) return 'non disponibile';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return 'non disponibile';
  return d.toLocaleString('it-IT', {
    timeZone: 'Europe/Rome', day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  }).replace(',', '');
}

export function giorno(iso) {
  if (!iso) return 'non disponibile';
  const [a, m, g] = String(iso).slice(0, 10).split('-');
  return a && m && g ? `${g}/${m}/${a}` : 'non disponibile';
}

export default function AggiornamentoDati() {
  const [dati, setDati] = useState(null);
  const [errore, setErrore] = useState(null);
  const [carico, setCarico] = useState(true);

  const carica = useCallback(async () => {
    setCarico(true);
    setErrore(null);
    try {
      const res = await api.get('/api/dashboard/aggiornamento-dati', { timeout: 20000 });
      setDati(res.data);
    } catch (e) {
      setErrore(e?.response?.data?.correlation_id || e?.code || e?.response?.status || 'errore');
    } finally {
      setCarico(false);
    }
  }, []);

  useEffect(() => { carica(); }, [carica]);

  return (
    <section style={S.box} data-testid="aggiornamento-dati" aria-live="polite">
      <div style={S.testata}>
        <span style={S.icona}><Database size={16} color="#fff" /></span>
        <h2 style={S.titolo}>Aggiornamento dati</h2>
        <button type="button" onClick={carica} disabled={carico} style={S.bottone}
          aria-label="Rileggi lo stato delle fonti">
          <RefreshCw size={14} /> {carico ? 'Lettura…' : 'Rileggi'}
        </button>
      </div>

      {errore && (
        <div style={S.errore} role="alert">
          Servizio temporaneamente non disponibile. Riprova tra poco.
          <span style={S.idRichiesta}>Riferimento: {errore}</span>
        </div>
      )}
      {!dati && carico && !errore && <div style={S.nota}>Lettura dello stato delle fonti…</div>}

      {dati && (
        <ol style={S.lista}>
          {dati.fonti.map(f => {
            const st = STATI[f.stato] || STATI.non_disponibile;
            const conteggi = Object.entries(f.conteggi || {});
            return (
              <li key={f.codice} style={S.riga} data-testid={`fonte-${f.codice}`}>
                <div style={S.rigaTesta}>
                  <strong style={S.nome}>{f.ordine}. {f.nome}</strong>
                  <span style={{ ...S.badge, color: st.colore, background: st.fondo, borderColor: st.colore }}>
                    {st.etichetta}
                  </span>
                </div>
                <div style={S.testo}>{f.testo}</div>
                <div style={S.dettagli}>
                  <span>Ultimo giro: <strong>{dataOra(f.ultimo_aggiornamento)}</strong></span>
                  {'ultimo_dato' in f && f.codice !== 'cedolini_f24' && f.codice !== 'riconciliazione' && (
                    <span>Ultimo dato: <strong>{giorno(f.ultimo_dato)}</strong></span>
                  )}
                  {conteggi.map(([k, v]) => (
                    <span key={k}>
                      {ETICHETTE_CONTEGGI[k] || k}: <strong>{v == null ? 'non disponibile' : v.toLocaleString('it-IT')}</strong>
                    </span>
                  ))}
                </div>
                {f.nota && <div style={S.nota}>{f.nota}</div>}
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}

const S = {
  box: {
    background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 10,
    padding: 16, marginBottom: 14, maxWidth: '100%', boxSizing: 'border-box',
  },
  testata: { display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' },
  icona: {
    width: 30, height: 30, borderRadius: 8, background: COLORS.primary,
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
  },
  titolo: { margin: 0, fontSize: 17, fontWeight: 800, color: COLORS.text, flex: 1 },
  bottone: {
    display: 'inline-flex', alignItems: 'center', gap: 6, minHeight: 44, padding: '0 14px',
    border: `1px solid ${COLORS.border}`, borderRadius: 8, background: COLORS.card,
    color: COLORS.text, fontWeight: 600, cursor: 'pointer',
  },
  lista: { listStyle: 'none', margin: '12px 0 0', padding: 0, display: 'grid', gap: 10 },
  riga: {
    border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: 12,
    overflowWrap: 'anywhere',
  },
  rigaTesta: { display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' },
  nome: { fontSize: 14, color: COLORS.text, flex: 1, minWidth: 0 },
  badge: {
    fontSize: 12, fontWeight: 700, border: '1px solid', borderRadius: 6, padding: '2px 8px',
  },
  testo: { fontSize: 13, color: COLORS.text, marginTop: 4 },
  dettagli: {
    display: 'flex', flexWrap: 'wrap', gap: '4px 16px', fontSize: 12,
    color: COLORS.textMuted, marginTop: 6,
  },
  nota: { fontSize: 12, color: COLORS.textMuted, marginTop: 6 },
  errore: {
    marginTop: 10, padding: 10, borderRadius: 8, background: COLORS.dangerLight,
    color: COLORS.danger, fontSize: 13, display: 'flex', flexWrap: 'wrap', gap: 8,
  },
  idRichiesta: { fontSize: 11, opacity: 0.8 },
};
