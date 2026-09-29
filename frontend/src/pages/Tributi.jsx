import React, { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Badge, Button, PageHeader, PageLoader } from '../components/ds';
import DocumentViewerModal from '../components/DocumentViewerModal';
import { COLORS, FONT, formatEuro, useIsMobile } from '../lib/utils';
import api from '../api';

/**
 * TRIBUTI — richiesta del titolare del 28/09/2026: una pagina in ordine di
 * codice tributo dove si guarda che cosa si e' pagato e quando, se con
 * ravvedimento, che cosa resta da pagare e che cosa e' andato in
 * compensazione. Colonne: inviato dal commercialista, pagato con quietanza,
 * pagato con ravvedimento, a credito / compensato, resta da pagare. Le
 * ritenute d'acconto lette dalle fatture entrano come attese sul 1040.
 *
 * Sola lettura: i numeri li fa il backend (`/api/f24/tributi`) sul registro
 * unico F24; la pagina li mostra.
 */

const RIGHE_PER_PAGINA = 200;

// Il colore accompagna sempre la parola.
const VARIANTE = {
  PAGATO: 'success',
  PAGATO_IN_RITARDO: 'warning',
  RAVVEDUTO: 'accent',
  PAGATO_BANCA: 'info',
  DA_PAGARE: 'primary',
  SCADUTO: 'danger',
  ATTESO: 'warning',
  CREDITO: 'info',
  SANZIONE: 'accent',
  INTERESSI: 'accent',
  SENZA_PROVA: 'neutral',
  NON_TORNA: 'danger',
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

const ESITO_MODELLO = {
  COPERTO: 'pagato',
  PAGATO_SENZA_QUIETANZA: 'pagato in banca, quietanza mancante',
  DA_PAGARE: 'nessun pagamento trovato',
};

function Riferimento({ doc, onApri }) {
  const riga = { marginTop: 8, paddingTop: 8, borderTop: `1px solid ${COLORS.border}`, fontSize: 13, lineHeight: 1.5 };
  const bottone = doc.pdf_url && (
    <Button size="sm" variant="secondary" style={{ minHeight: 36, marginTop: 4 }}
      onClick={() => onApri(doc.pdf_url, doc.tipo === 'commercialista' ? 'F24 del commercialista' : `Quietanza ${doc.protocollo || ''}`)}>
      {doc.tipo === 'commercialista' ? 'Apri F24' : 'Apri quietanza'}
    </Button>
  );
  if (doc.tipo === 'commercialista') {
    return (
      <div style={riga} data-testid="riferimento-commercialista">
        <strong>F24 del commercialista</strong> · scadenza {dataIt(doc.data)} · {euro(doc.importo_cents)}
        {doc.credito_cents > 0 && <> · credito {euro(doc.credito_cents)}</>}
        {' · '}{ESITO_MODELLO[doc.esito] || doc.motivo || 'da verificare'}
        {doc.ravveduto && ' · pagato poi con ravvedimento'}
        {(doc.addebiti_banca || []).filter(a => a.link).map(a => (
          <div key={a.link}>Banca: <Link to={a.link}>addebito del {dataIt(a.data)}</Link>{a.agganciato ? '' : ' (compatibile, da confermare)'}</div>
        ))}
        <div>{bottone}</div>
      </div>
    );
  }
  if (doc.tipo === 'ritenuta') {
    return (
      <div style={riga} data-testid="riferimento-ritenuta">
        <strong>Ritenuta d'acconto</strong> · fattura {doc.numero_fattura || '?'} di {doc.fornitore || 'fornitore sconosciuto'} del {dataIt(doc.data)}
        {' · '}{euro(doc.importo_cents)} · da versare entro il {dataIt(doc.scadenza)}
        <div style={{ color: doc.versata ? COLORS.success : COLORS.danger, fontWeight: 700 }}>
          {doc.versata
            ? `Pagata il ${dataIt(doc.data_pagamento)}${doc.quietanza_protocollo ? ` · quietanza protocollo ${doc.quietanza_protocollo}` : ''}`
            : 'Non ancora pagata'}
        </div>
        {doc.link && <Link to={doc.link}>Apri la fattura</Link>}
      </div>
    );
  }
  const titolo = doc.tipo === 'ravvedimento' ? 'Pagato con ravvedimento' : doc.tipo === 'credito' ? 'Credito compensato' : 'Pagato con quietanza';
  return (
    <div style={riga} data-testid={`riferimento-${doc.tipo}`}>
      <strong>{titolo}</strong> · {dataIt(doc.data)}{doc.protocollo && <> · protocollo {doc.protocollo}</>}
      {doc.importo_cents > 0 && <> · {euro(doc.importo_cents)}</>}
      {doc.credito_cents > 0 && <> · a credito {euro(doc.credito_cents)}</>}
      {doc.copie > 1 && <> · {doc.copie} copie dello stesso file</>}
      {(doc.compensato_con || []).length > 0 && (
        <div>Ha pagato in compensazione: {doc.compensato_con.map(c => `${c.codice} ${c.periodo} ${euro(c.importo_cents)}`).join(' · ')}</div>
      )}
      {(doc.crediti_usati || []).length > 0 && (
        <div>Nella stessa delega crediti compensati: {doc.crediti_usati.map(c => `${c.codice} ${c.periodo} ${euro(c.importo_cents)}`).join(' · ')}
          {' · '}saldo versato {euro(doc.saldo_delega_cents)}</div>
      )}
      <div>{bottone}</div>
    </div>
  );
}

function Dettaglio({ voce, onApri }) {
  return (
    <div style={{ padding: '4px 4px 10px' }} data-testid={`dettaglio-${voce.chiave}`}>
      <div style={{ fontSize: 13, color: COLORS.textMuted }}>
        {voce.sezione_label} · {voce.natura === 'tributo' ? 'tributo' : voce.natura}
        {voce.scadenza && <> · scadenza {dataIt(voce.scadenza)}</>}
        {voce.ultimo_pagamento && <> · ultimo pagamento {dataIt(voce.ultimo_pagamento)}</>}
        {voce.in_ritardo && <strong style={{ color: COLORS.warning }}> · pagato dopo la scadenza</strong>}
        {voce.versato_due_volte_cents > 0 && (
          <strong style={{ color: COLORS.danger }} data-testid="versato-due-volte">
            {' · '}stesso importo versato con due deleghe diverse ({euro(voce.versato_due_volte_cents)} in più): da verificare col commercialista
          </strong>
        )}
      </div>
      {voce.scarto_cents ? (
        <div role="alert" style={{ marginTop: 8, color: COLORS.danger, fontSize: 13 }} data-testid="scarto-ritenute">
          <strong>Non torna:</strong> le fatture fanno {euro(voce.atteso_cents)}, la quietanza ha versato{' '}
          {euro(voce.pagato_cents)} ({voce.scarto_cents > 0 ? 'in più' : 'in meno'} di {euro(Math.abs(voce.scarto_cents))}).
          Controlla le fatture prima di considerarlo pagato.
        </div>
      ) : null}
      {voce.fatture_da_associare && (
        <div style={{ marginTop: 8, color: COLORS.textMuted, fontSize: 13 }} data-testid="fatture-da-associare">
          Nessuna fattura associata a questo 1040: le fatture di {voce.periodo} non sono in archivio.
        </div>
      )}
      {voce.documenti.map((doc, i) => <Riferimento key={`${doc.tipo}-${i}`} doc={doc} onApri={onApri} />)}
    </div>
  );
}

function Importo({ cents, colore }) {
  return (
    <span style={{ fontFamily: FONT.mono, fontVariantNumeric: 'tabular-nums', color: cents ? colore || COLORS.text : COLORS.textSubtle, whiteSpace: 'nowrap' }}>
      {euro(cents)}
    </span>
  );
}

const COLONNE = [
  { id: 'inviato_cents', label: 'Inviato commercialista' },
  { id: 'quietanza_cents', label: 'Pagato con quietanza' },
  { id: 'ravvedimento_cents', label: 'Con ravvedimento' },
  { id: 'credito_cents', label: 'A credito / compensato' },
  { id: 'residuo_cents', label: 'Resta da pagare' },
];

export default function Tributi() {
  const isMobile = useIsMobile(1024);
  const [params, setParams] = useSearchParams();
  const [dati, setDati] = useState(null);
  const [errore, setErrore] = useState('');
  const [aperta, setAperta] = useState(null);
  const [mostrate, setMostrate] = useState(RIGHE_PER_PAGINA);
  const [pdf, setPdf] = useState(null);
  const [cercaTesto, setCercaTesto] = useState(params.get('cerca') || '');

  const anno = params.get('anno') || '';
  const stato = params.get('stato') || '';
  const sezione = params.get('sezione') || '';
  const cerca = params.get('cerca') || '';

  const imposta = (chiave, valore) => {
    const nuovi = new URLSearchParams(params);
    if (valore) nuovi.set(chiave, valore); else nuovi.delete(chiave);
    setParams(nuovi, { replace: true });
  };

  useEffect(() => {
    const t = setTimeout(() => { if (cercaTesto !== cerca) imposta('cerca', cercaTesto.trim()); }, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cercaTesto]);

  useEffect(() => {
    let attivo = true;
    setErrore('');
    const qs = new URLSearchParams();
    if (anno) qs.set('anno', anno);
    if (stato) qs.set('stato', stato);
    if (sezione) qs.set('sezione', sezione);
    if (cerca) qs.set('cerca', cerca);
    api.get(`/api/f24/tributi?${qs}`)
      .then(r => { if (attivo) { setDati(r.data); setMostrate(RIGHE_PER_PAGINA); } })
      .catch(e => { if (attivo) setErrore(e.response?.data?.detail || e.message || 'Lettura non riuscita'); });
    return () => { attivo = false; };
  }, [anno, stato, sezione, cerca]);

  const voci = dati?.voci || [];
  const totali = dati?.totali || {};
  const visibili = useMemo(() => voci.slice(0, mostrate), [voci, mostrate]);
  const rimanenti = voci.length - visibili.length;

  const pastiglie = dati ? [
    { etichetta: 'Pagato con quietanza', valore: euro(totali.quietanza_cents), nota: `${totali.voci || 0} righe · ${totali.codici || 0} codici`, tono: 'ok' },
    { etichetta: 'Con ravvedimento', valore: euro(totali.ravvedimento_cents), nota: 'tributo, sanzioni e interessi', tono: totali.ravvedimento_cents ? 'attenzione' : 'neutro' },
    { etichetta: 'Compensato', valore: euro(totali.credito_cents), nota: 'crediti usati nelle deleghe' },
    { etichetta: 'Resta da pagare', valore: euro(totali.residuo_cents), nota: `${totali.aperte || 0} righe aperte`, tono: totali.residuo_cents ? 'male' : 'ok' },
  ] : [];

  const apriPdf = (url, titolo) => setPdf({ url, titolo });
  const apri = voce => setAperta(a => (a === voce.chiave ? null : voce.chiave));

  return (
    <div style={{ maxWidth: 1280, margin: '0 auto', fontFamily: FONT.family }}>
      <PageHeader title="Tributi" pastiglie={pastiglie} style={{ marginBottom: 14 }} />

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 12 }} data-testid="filtri-tributi">
        <select aria-label="Anno di riferimento" value={anno} onChange={e => imposta('anno', e.target.value)} style={selettore}>
          <option value="">Tutti gli anni</option>
          {(dati?.facets?.anni || []).map(a => <option key={a} value={a}>{a}</option>)}
        </select>
        <select aria-label="Stato" value={stato} onChange={e => imposta('stato', e.target.value)} style={selettore}>
          <option value="">Tutti gli stati</option>
          <option value="APERTO">Resta da pagare</option>
          {(dati?.facets?.stati || []).map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
        </select>
        <select aria-label="Sezione" value={sezione} onChange={e => imposta('sezione', e.target.value)} style={selettore}>
          <option value="">Tutte le sezioni</option>
          {(dati?.facets?.sezioni || []).map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
        </select>
        <input
          aria-label="Cerca codice o descrizione" value={cercaTesto} onChange={e => setCercaTesto(e.target.value)}
          placeholder="Codice o descrizione (es. 1040)" style={{ ...selettore, flex: '1 1 200px', minWidth: 0 }}
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
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }} data-testid="tributi-card">
          {visibili.map(v => (
            <div key={v.chiave} style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 12, padding: '10px 12px' }}>
              <button type="button" onClick={() => apri(v)} aria-expanded={aperta === v.chiave}
                style={{ all: 'unset', display: 'block', width: '100%', cursor: 'pointer', minHeight: 44 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                  <strong>{v.codice || '—'} · {v.periodo}</strong>
                  <Badge variant={VARIANTE[v.stato]}>{v.stato_label}</Badge>
                </div>
                {v.versato_due_volte_cents > 0 && <Badge variant="danger">Versato due volte</Badge>}
                <div style={{ fontSize: 12, color: COLORS.textMuted, margin: '2px 0 6px' }}>{v.descrizione}</div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 12px', fontSize: 12 }}>
                  {COLONNE.map(c => (
                    <div key={c.id}>
                      <div style={{ color: COLORS.textMuted }}>{c.label}</div>
                      <Importo cents={v[c.id]} colore={c.id === 'residuo_cents' ? COLORS.danger : undefined} />
                    </div>
                  ))}
                </div>
              </button>
              {aperta === v.chiave && <Dettaglio voce={v} onApri={apriPdf} />}
            </div>
          ))}
        </div>
      ) : (
        <div style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 12 }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }} data-testid="tabella-tributi">
            <thead>
              <tr style={{ background: COLORS.bgAlt }}>
                {['Codice', 'Periodo', ...COLONNE.map(c => c.label), 'Stato'].map((h, i) => (
                  <th key={h} style={{
                    padding: '10px 10px', fontSize: 11, fontWeight: 700, color: COLORS.textMuted, textTransform: 'uppercase',
                    textAlign: i >= 2 && i < 2 + COLONNE.length ? 'right' : 'left', borderBottom: `1px solid ${COLORS.border}`,
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {visibili.map((v, i) => {
                const nuovoCodice = i === 0 || visibili[i - 1].codice !== v.codice;
                return (
                  <React.Fragment key={v.chiave}>
                    <tr
                      onClick={() => apri(v)} data-testid={`riga-${v.chiave}`}
                      style={{ cursor: 'pointer', borderTop: nuovoCodice ? `2px solid ${COLORS.border}` : `1px solid ${COLORS.gray[100]}`, background: aperta === v.chiave ? COLORS.primarySoft : undefined }}
                    >
                      <td style={{ padding: '8px 10px', maxWidth: 280 }}>
                        {nuovoCodice ? (
                          <>
                            <strong>{v.codice || '—'}</strong>
                            <div style={{ fontSize: 11.5, color: COLORS.textMuted }}>{v.descrizione}</div>
                          </>
                        ) : <span style={{ color: COLORS.textSubtle }}>{v.codice}</span>}
                      </td>
                      <td style={{ padding: '8px 10px', whiteSpace: 'nowrap' }}>{v.periodo}</td>
                      {COLONNE.map(c => (
                        <td key={c.id} style={{ padding: '8px 10px', textAlign: 'right' }}>
                          <Importo cents={v[c.id]} colore={c.id === 'residuo_cents' ? COLORS.danger : undefined} />
                          {c.id === 'inviato_cents' && !v.inviato_cents && v.atteso_cents > 0 && (
                            <div style={{ fontSize: 11, color: COLORS.warning }}>atteso {euro(v.atteso_cents)}</div>
                          )}
                          {c.id === 'quietanza_cents' && v.banca_cents > 0 && (
                            <div style={{ fontSize: 11, color: COLORS.info }}>banca {euro(v.banca_cents)}</div>
                          )}
                        </td>
                      ))}
                      <td style={{ padding: '8px 10px' }}>
                        <Badge variant={VARIANTE[v.stato]}>{v.stato_label}</Badge>
                        {v.versato_due_volte_cents > 0 && <div style={{ marginTop: 3 }}><Badge variant="danger">Versato due volte</Badge></div>}
                        {v.ultimo_pagamento && <div style={{ fontSize: 11, color: COLORS.textMuted, marginTop: 2 }}>il {dataIt(v.ultimo_pagamento)}</div>}
                      </td>
                    </tr>
                    {aperta === v.chiave && (
                      <tr><td colSpan={3 + COLONNE.length} style={{ padding: '0 14px', background: COLORS.bgAlt }}>
                        <Dettaglio voce={v} onApri={apriPdf} />
                      </td></tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      ))}

      {rimanenti > 0 && (
        <div style={{ textAlign: 'center', marginTop: 12 }}>
          <Button variant="secondary" style={{ minHeight: 44 }} data-testid="tributi-mostra-altre"
            onClick={() => setMostrate(n => n + RIGHE_PER_PAGINA)}>
            Mostra altre {Math.min(RIGHE_PER_PAGINA, rimanenti)} · {rimanenti} rimanenti
          </Button>
        </div>
      )}

      {pdf && (
        <DocumentViewerModal title={pdf.titolo} fetchUrl={pdf.url} documentType="documento_fiscale" onClose={() => setPdf(null)} />
      )}
    </div>
  );
}
