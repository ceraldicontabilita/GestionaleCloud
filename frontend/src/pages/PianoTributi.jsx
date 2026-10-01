import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Badge, Button, Card, PageHeader, PageLoader, StatCard } from '../components/ds';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { COLORS, FONT, formatEuro } from '../lib/utils';
import api from '../api';

const MESI = ['Gen', 'Feb', 'Mar', 'Apr', 'Mag', 'Giu', 'Lug', 'Ago', 'Set', 'Ott', 'Nov', 'Dic'];

// Il colore accompagna sempre la parola: mai l'unica informazione.
const VARIANTE = {
  pagato: 'success',
  da_confermare_banca: 'warning',
  quietanza_senza_banca: 'warning',
  da_verificare_a_mano: 'warning',
  da_pagare: 'accent',
  scaduto_non_pagato: 'danger',
  manca_f24: 'danger',
  futuro: 'neutral',
  credito_usato: 'info',
  credito_assente: 'neutral',
};

const FONDO = {
  success: COLORS.successLight,
  warning: COLORS.warningLight,
  accent: COLORS.accentSoft,
  danger: COLORS.dangerLight,
  info: COLORS.infoLight,
  neutral: COLORS.card,
};

// Interfaccia sempre gg/mm/aaaa.
const dataIt = iso => {
  const [a, m, g] = String(iso || '').slice(0, 10).split('-');
  return a && m && g ? `${g}/${m}/${a}` : '-';
};

const importo = valore => (valore === null || valore === undefined ? null : formatEuro(Number(valore)));

// Una fila di piccole card che va a capo da sola: mai una colonna lunga.
const FILA_CARD = { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(210px, 1fr))', gap: 8 };
const PICCOLA_CARD = {
  padding: '8px 10px', borderRadius: 8, fontSize: 12, lineHeight: 1.35,
  border: `1px solid ${COLORS.border}`, background: COLORS.card, color: COLORS.text,
};

// «ritardo» e' sul termine EFFETTIVO: il 16 festivo slitta al primo giorno lavorativo.
const giorni = n => `${n} ${n === 1 ? 'giorno' : 'giorni'}`;

function testoRitardo(casella) {
  if (casella.giorni_ritardo === null || casella.giorni_ritardo === undefined) {
    return casella.giorni_scaduto > 0 ? `scaduto da ${giorni(casella.giorni_scaduto)}` : null;
  }
  return casella.giorni_ritardo === 0 ? 'nei termini' : `ritardo ${giorni(casella.giorni_ritardo)}`;
}

function etichettaCasella(voce, casella) {
  if (voce.periodo === 'mese') return MESI[Number(casella.periodo) - 1] || casella.periodo;
  return casella.etichetta_periodo;
}

function Casella({ voce, casella, aperta, onApri }) {
  const variante = VARIANTE[casella.stato] || 'neutral';
  return (
    <button
      type="button"
      onClick={onApri}
      aria-expanded={aperta}
      aria-label={`${voce.etichetta} ${casella.etichetta_periodo}: ${casella.etichetta_stato}`}
      style={{
        minHeight: 64, padding: '8px 10px', textAlign: 'left', cursor: 'pointer',
        borderRadius: 8, fontFamily: FONT.family,
        border: `1px solid ${aperta ? COLORS.primary : COLORS.border}`,
        background: FONDO[variante],
      }}
    >
      <div style={{ fontWeight: 700, fontSize: 13, color: COLORS.text }}>{etichettaCasella(voce, casella)}</div>
      <div style={{ fontSize: 11, color: COLORS.text, lineHeight: 1.3 }}>{casella.etichetta_stato}</div>
      {testoRitardo(casella) && (
        <div style={{
          fontSize: 11, fontWeight: 700,
          color: casella.giorni_ritardo > 0 || casella.giorni_scaduto > 0 ? COLORS.danger : COLORS.success,
        }}
        >
          {testoRitardo(casella)}
        </div>
      )}
      {(casella.importo || casella.credito) && (
        <div style={{ fontSize: 11, fontFamily: FONT.mono, fontVariantNumeric: 'tabular-nums', color: COLORS.textMuted }}>
          {casella.importo ? importo(casella.importo) : `credito ${importo(casella.credito)}`}
        </div>
      )}
      {casella.modelli_doppi > 0 && (
        <div style={{ fontSize: 10, color: COLORS.warning, fontWeight: 700 }}>F24 doppio</div>
      )}
    </button>
  );
}

function DettaglioCasella({ voce, casella }) {
  return (
    <div style={{ marginTop: 10, padding: 12, borderRadius: 8, background: COLORS.bgAlt, fontSize: 13 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
        <strong>{voce.etichetta} · {casella.etichetta_periodo}</strong>
        <Badge variant={VARIANTE[casella.stato]}>{casella.etichetta_stato}</Badge>
      </div>
      <div style={{ marginTop: 6, color: COLORS.textMuted }}>
        Scadenza: {casella.scadenza ? dataIt(casella.scadenza) : 'da impostare'}
        {' · '}Codici: {(voce.codici || []).join(', ') || 'nessuno (fuori F24)'}
      </div>
      {casella.slittamento && (
        <div style={{ marginTop: 6 }}>
          Il {dataIt(casella.scadenza_nominale)} cade in {casella.slittamento === 'proroga di agosto'
            ? 'agosto: la scadenza e\' prorogata al 20' : 'un giorno festivo'}: si paga entro il {dataIt(casella.scadenza)}
          {' '}senza ravvedimento (fino a {giorni(Math.max(0, Math.round((new Date(casella.scadenza) - new Date(casella.scadenza_nominale)) / 86400000)))} dopo la data scritta).
        </div>
      )}
      {voce.nota && <div style={{ marginTop: 6 }}>{voce.nota}</div>}
      {!casella.modelli.length && casella.stato === 'manca_f24' && (
        <div style={{ marginTop: 6 }}>Nessun F24 in archivio per questo periodo: la scadenza e' passata.</div>
      )}
      {casella.modelli.map(m => (
        <div key={m.f24_id} style={{ marginTop: 8, paddingTop: 8, borderTop: `1px solid ${COLORS.border}` }}>
          <div>
            F24 del {m.data_versamento ? dataIt(m.data_versamento) : 'data non letta'}
            {' · '}{importo(m.debito_cents / 100)}
            {m.credito_cents > 0 && <> · credito {importo(m.credito_cents / 100)}</>}
            {' · '}<a href={m.pdf_url} target="_blank" rel="noreferrer">apri il PDF</a>
            {m.giorni_ritardo !== null && m.giorni_ritardo !== undefined && (
              <> · {m.giorni_ritardo === 0 ? 'versato nei termini' : `versato con ${giorni(m.giorni_ritardo)} di ritardo`}</>
            )}
          </div>
          {m.movimenti.map(mov => (
            <div key={mov.id}>
              Banca: <Link to={mov.link}>movimento del {dataIt(mov.data)}</Link>
              {mov.agganciato ? ' (agganciato)' : ' (compatibile, da confermare)'}
            </div>
          ))}
          {m.quietanze.length > 0 && <div>Quietanza presente ({m.quietanze.length})</div>}
        </div>
      ))}
    </div>
  );
}

function RicercaCodice({ anno }) {
  const [codice, setCodice] = useState('');
  const [mese, setMese] = useState('');
  const [esito, setEsito] = useState(null);
  const [errore, setErrore] = useState('');
  const [carico, setCarico] = useState(false);

  const cerca = async event => {
    event.preventDefault();
    if (!codice.trim()) return;
    setCarico(true);
    setErrore('');
    try {
      const params = new URLSearchParams({ anno: String(anno) });
      if (mese) params.set('mese', mese);
      const { data } = await api.get(`/api/f24-riconciliazione/verifica-codice/${encodeURIComponent(codice.trim())}?${params}`);
      setEsito(data);
    } catch (e) {
      setEsito(null);
      setErrore(e.response?.data?.detail || e.message || 'Ricerca non riuscita');
    } finally {
      setCarico(false);
    }
  };

  return (
    <Card style={{ marginBottom: 16 }}>
      <form onSubmit={cerca} style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'flex-end' }}>
        <label style={{ display: 'flex', flexDirection: 'column', fontSize: 12, fontWeight: 600 }}>
          Codice tributo
          <input
            value={codice} onChange={e => setCodice(e.target.value)} placeholder="es. 1001, DM10, 3802"
            style={{ minHeight: 44, padding: '0 10px', borderRadius: 6, border: `1px solid ${COLORS.border}`, fontSize: 14 }}
          />
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', fontSize: 12, fontWeight: 600 }}>
          Mese
          <select
            value={mese} onChange={e => setMese(e.target.value)}
            style={{ minHeight: 44, padding: '0 10px', borderRadius: 6, border: `1px solid ${COLORS.border}`, fontSize: 14 }}
          >
            <option value="">Tutto il {anno}</option>
            {MESI.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
          </select>
        </label>
        <Button type="submit" disabled={carico} style={{ minHeight: 44 }}>{carico ? 'Cerco...' : 'Cerca'}</Button>
      </form>
      {errore && <div role="alert" style={{ marginTop: 8, color: COLORS.danger }}>{errore}</div>}
      {esito && (
        <div style={{ marginTop: 12, fontSize: 13 }}>
          <div style={{ fontWeight: 700 }}>
            {esito.codice_tributo}{esito.descrizione ? ` · ${esito.descrizione}` : ''} · periodo {esito.periodo_cercato}
          </div>
          {!esito.righe_f24.length && <div style={{ marginTop: 6 }}>Nessun F24 con questo codice nel periodo cercato.</div>}
          <div style={{ ...FILA_CARD, marginTop: 8 }}>
            {esito.righe_f24.map(r => (
              <div key={r.f24_id} style={PICCOLA_CARD}>
                <div style={{ fontWeight: 700, fontSize: 13 }}>F24 del {r.data_versamento_it || 'data non letta'}</div>
                <div style={{ margin: '4px 0' }}>
                  <Badge variant={r.pagamento_verificato_banca ? 'success' : r.quietanze.length ? 'warning' : 'danger'}>
                    {r.pagamento_verificato_banca ? 'Pagato (banca)' : r.quietanze.length ? 'Quietanza, banca da verificare' : 'Nessun pagamento trovato'}
                  </Badge>
                </div>
                {r.righe.map((riga, i) => (
                  <div key={i} style={{ color: COLORS.textMuted }}>
                    {riga.codice_tributo} · {riga.periodo_riferimento || 'periodo non letto'} · {importo(riga.importo_debito)}
                    {riga.importo_credito ? ` · credito ${importo(riga.importo_credito)}` : ''}
                  </div>
                ))}
                <a href={r.pdf_url} target="_blank" rel="noreferrer">apri il PDF</a>
              </div>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}

// Il piano di un anno: i gruppi di voci con le loro caselle, poi gli altri codici versati.
function GrigliaAnno({ g, aperta, setAperta }) {
  const gruppi = useMemo(() => {
    const out = [];
    for (const riga of g.voci || []) {
      let gr = out.find(x => x.nome === riga.voce.gruppo);
      if (!gr) { gr = { nome: riga.voce.gruppo, righe: [] }; out.push(gr); }
      gr.righe.push(riga);
    }
    return out;
  }, [g]);

  return (
    <>
      {gruppi.map(gr => (
        <section key={gr.nome} style={{ marginBottom: 16 }}>
          <h2 style={{ fontSize: 15, fontWeight: 800, letterSpacing: '-0.02em', margin: '8px 0' }}>{gr.nome}</h2>
          {gr.righe.map(({ voce, caselle }) => (
            <Card key={voce.id} style={{ marginBottom: 10 }}>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'baseline', marginBottom: 8 }}>
                <strong>{voce.etichetta}</strong>
                <span style={{ fontSize: 12, color: COLORS.textMuted }}>{(voce.codici || []).join(' · ')}</span>
                {!voce.obbligatorio && <Badge variant="neutral">Non obbligatorio</Badge>}
              </div>
              {!caselle.length && (
                <div style={{ fontSize: 13, color: COLORS.textMuted }}>{voce.nota || 'Nessuna scadenza impostata.'}</div>
              )}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(104px, 1fr))', gap: 6 }}>
                {caselle.map(c => {
                  const chiave = `${g.anno}:${voce.id}:${c.periodo}`;
                  return (
                    <Casella
                      key={chiave} voce={voce} casella={c} aperta={aperta === chiave}
                      onApri={() => setAperta(aperta === chiave ? null : chiave)}
                    />
                  );
                })}
              </div>
              {caselle.filter(c => aperta === `${g.anno}:${voce.id}:${c.periodo}`).map(c => (
                <DettaglioCasella key={c.periodo} voce={voce} casella={c} />
              ))}
            </Card>
          ))}
        </section>
      ))}

      {(g.fuori_piano || []).length > 0 && (
        <section>
          <h2 style={{ fontSize: 15, fontWeight: 800, letterSpacing: '-0.02em', margin: '8px 0' }}>Altri codici versati nel {g.anno}</h2>
          <div style={FILA_CARD}>
            {g.fuori_piano.map(v => (
              <div key={v.codice} style={PICCOLA_CARD}>
                <div style={{ fontWeight: 700, fontSize: 13 }}>{v.codice}</div>
                {v.descrizione && <div style={{ color: COLORS.textMuted }}>{v.descrizione}</div>}
                <div>{v.versamenti.length} versamenti</div>
              </div>
            ))}
          </div>
        </section>
      )}
    </>
  );
}

const PERIODI = [
  { id: 'anno', etichetta: anno => `Anno ${anno}` },
  { id: 'ultimi3', etichetta: () => 'Ultimi 3 anni' },
  { id: 'tutti', etichetta: () => 'Tutti gli anni' },
];

const parametroAnni = (periodo, anno) => {
  if (periodo === 'tutti') return 'tutti';
  if (periodo === 'ultimi3') return `${Math.max(2019, Number(anno) - 2)}-${anno}`;
  return String(anno);
};

export default function PianoTributi() {
  const { anno } = useAnnoGlobale();
  const [periodo, setPeriodo] = useState('anno');
  const [dati, setDati] = useState(null);
  const [errore, setErrore] = useState('');
  const [carico, setCarico] = useState(true);
  const [aperta, setAperta] = useState(null);

  const carica = useCallback(() => {
    let attivo = true;
    setCarico(true);
    setErrore('');
    api.get(`/api/f24/piano-tributi?anno=${parametroAnni(periodo, anno)}`)
      .then(r => { if (attivo) setDati(r.data); })
      .catch(e => { if (attivo) { setDati(null); setErrore(e.response?.data?.detail || e.message || 'Piano non disponibile'); } })
      .finally(() => { if (attivo) setCarico(false); });
    return () => { attivo = false; };
  }, [anno, periodo]);

  useEffect(() => carica(), [carica]);

  // Un anno solo e' la forma di sempre; piu' anni arrivano come elenco, dal piu' recente.
  const anni = dati ? (dati.multi ? dati.anni : [dati]) : [];
  const conta = stato => (dati?.conteggi?.[stato] || 0);
  const sottotitolo = periodo === 'anno' ? `${anno}` : (periodo === 'tutti' ? 'tutti gli anni' : `${Math.max(2019, Number(anno) - 2)}-${anno}`);

  return (
    <div style={{ padding: '0 16px 24px', maxWidth: 1200, margin: '0 auto' }}>
      <PageHeader
        title="Piano tributi"
        subtitle={`${sottotitolo}: i tributi che devono arrivare, quelli pagati e quelli che mancano`}
      />
      <div role="group" aria-label="Periodo" style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
        {PERIODI.map(p => (
          <Button
            key={p.id} type="button" onClick={() => setPeriodo(p.id)}
            variant={periodo === p.id ? 'primary' : 'secondary'} aria-pressed={periodo === p.id}
            style={{ minHeight: 44 }}
          >
            {p.etichetta(anno)}
          </Button>
        ))}
      </div>
      {carico && <PageLoader />}
      {errore && <div role="alert" style={{ padding: 12, color: COLORS.danger }}>Errore: {errore}</div>}

      {dati && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12, marginBottom: 16 }}>
            <StatCard label="Pagati (banca)" value={conta('pagato')} accent="success" />
            <StatCard label="Da verificare" value={conta('quietanza_senza_banca') + conta('da_confermare_banca') + conta('da_verificare_a_mano')} accent="warning" />
            <StatCard label="Mancano o scaduti" value={(dati.mancano || []).length} accent="danger" />
            <StatCard label="Non ancora scaduti" value={conta('futuro') + conta('da_pagare')} accent="none" />
          </div>

          {(dati.mancano || []).length > 0 && (
            <Card style={{ marginBottom: 16, borderLeft: `4px solid ${COLORS.danger}` }}>
              <div style={{ fontWeight: 700, marginBottom: 8 }}>Da guardare subito</div>
              <div style={FILA_CARD}>
                {dati.mancano.map((m, i) => (
                  <div
                    key={i}
                    style={{ ...PICCOLA_CARD, borderLeft: `3px solid ${COLORS.danger}`, background: COLORS.dangerLight }}
                  >
                    <div style={{ fontWeight: 700, fontSize: 13 }}>{m.voce}</div>
                    <div style={{ color: COLORS.textMuted }}>{m.codici.join(', ')} · {m.periodo}</div>
                    <div>scadenza {m.scadenza ? dataIt(m.scadenza) : '-'}</div>
                    {m.giorni_scaduto > 0 && (
                      <div style={{ color: COLORS.danger, fontWeight: 700 }}>scaduto da {giorni(m.giorni_scaduto)}</div>
                    )}
                    <div style={{ fontWeight: 700 }}>{dati.etichette[m.stato]}</div>
                  </div>
                ))}
              </div>
            </Card>
          )}
          {dati.modelli_doppi > 0 && (
            <div role="status" style={{ marginBottom: 16, fontSize: 13, color: COLORS.warning }}>
              {dati.modelli_doppi} F24 risultano registrati due volte: nel piano contano una volta sola.
            </div>
          )}

          <RicercaCodice anno={anno} />

          {anni.map(g => (
            <div key={g.anno}>
              {dati.multi && (
                <h2 style={{ fontSize: 18, fontWeight: 800, letterSpacing: '-0.02em', margin: '20px 0 8px' }}>Anno {g.anno}</h2>
              )}
              <GrigliaAnno g={g} aperta={aperta} setAperta={setAperta} />
            </div>
          ))}
        </>
      )}
    </div>
  );
}
