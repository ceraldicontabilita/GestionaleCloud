import React, { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Badge, PageHeader, PageLoader } from '../components/ds';
import ApriOriginale from '../components/ApriOriginale';
import ConfermaAddebitoF24 from '../components/ConfermaAddebitoF24';
import LegendaRegole from '../components/vista/LegendaRegole';
import { Campo, GrigliaCampi, Messaggio, Riquadro, paginaStile } from '../components/vista/Elementi';
import { CANALI, LIVELLI_RISCONTRO } from '../lib/legendaRegole';
import { dataOppure, euroOppure, percorsoTributo, testoOppure } from '../lib/vista';
import { COLORS, FONT, useIsMobile } from '../lib/utils';
import api from '../api';

/**
 * VISTA F24 — `/fiscale/f24/:id`.
 *
 * Un F24 (modello del commercialista o quietanza) con le sue righe tributo,
 * l'originale apribile e il riscontro con l'addebito in banca. Sola lettura:
 * righe da `/api/fiscal/f24-rows` (registro unico F24), riscontro da
 * `/api/f24-riconciliazione/quietanze-banca` (il motore a livelli, che qui
 * non ricalcola niente). Il riscontro e' una seconda lettura: se fallisce la
 * scheda resta e lo dice. L'unica azione e' «Conferma questo addebito» su un
 * riscontro probabile o parziale (`ConfermaAddebitoF24`): la scrittura e' la
 * stessa del certo, sul backend.
 */

const VARIANTE_LIVELLO = {
  CERTO: 'success', PROBABILE: 'warning', PARZIALE: 'warning',
  NESSUN_MATCH: 'danger', MOVIMENTO_ORFANO: 'danger',
};

const RIGHE_PER_PAGINA = 200;

const centesimi = v => Math.round(Number(v || 0) * 100);

const tocca = (riga, id) => {
  const testo = JSON.stringify(riga || {});
  return testo.includes(`"${id}"`);
};

function Importo({ valore }) {
  return (
    <span style={{ fontFamily: FONT.mono, fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }}>
      {euroOppure(valore)}
    </span>
  );
}

function Riscontro({ stato, f24Id, onConfermato }) {
  if (stato.errore) {
    return <Messaggio testId="riscontro-errore" tono="errore">Riscontro bancario non disponibile: {stato.errore}</Messaggio>;
  }
  if (!stato.dati) return <PageLoader />;
  if (stato.dati.length === 0) {
    return (
      <p data-testid="riscontro-vuoto" style={{ margin: 0, color: COLORS.textMuted, fontSize: 14 }}>
        Nessun riscontro con l'addebito in banca per questo F24.
      </p>
    );
  }
  return (
    <div style={{ display: 'grid', gap: 10 }}>
      {stato.dati.map((r, i) => {
        const addebito = r.addebito || (r.pagamenti || []).map(p => p.addebito).find(Boolean) || null;
        return (
          <div key={`${r.chiave || r.movimento_id || i}`} data-testid="riscontro-riga"
            style={{ border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: '10px 12px' }}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <Badge variant={VARIANTE_LIVELLO[r.livello] || 'neutral'}>{LIVELLI_RISCONTRO[r.livello] || testoOppure(r.livello)}</Badge>
              <span style={{ fontSize: 13 }}>{dataOppure(r.data)} · <Importo valore={r.importo} /></span>
              {r.differenza ? <span style={{ fontSize: 13, color: COLORS.warning }}>differenza <Importo valore={r.differenza} /></span> : null}
            </div>
            {r.motivazione && <p style={{ margin: '6px 0 0', fontSize: 13, color: COLORS.textMuted }}>{r.motivazione}</p>}
            {addebito?.link && (
              <div style={{ marginTop: 6, fontSize: 13 }}>
                <Link to={addebito.link} style={{ minHeight: 44, display: 'inline-flex', alignItems: 'center' }}>
                  Apri l'addebito in banca{addebito.data ? ` del ${dataOppure(addebito.data)}` : ''}
                </Link>
              </div>
            )}
            {!r.pagamenti && (
              <div style={{ marginTop: 8 }}>
                <ConfermaAddebitoF24
                  f24Id={f24Id}
                  livello={r.livello}
                  candidati={r.addebito ? [r.addebito] : (r.candidati || [])}
                  motivi={stato.motivi || {}}
                  onConfermato={onConfermato}
                />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

export default function F24Scheda() {
  const { id } = useParams();
  const isMobile = useIsMobile(900);
  const [righe, setRighe] = useState(null);
  const [errore, setErrore] = useState('');
  const [dettaglio, setDettaglio] = useState(null);
  const [riscontro, setRiscontro] = useState({ dati: null, errore: '' });
  const [mostrate, setMostrate] = useState(RIGHE_PER_PAGINA);
  const [versioneRiscontro, setVersioneRiscontro] = useState(0);

  useEffect(() => {
    let attivo = true;
    setRighe(null); setErrore(''); setDettaglio(null); setRiscontro({ dati: null, errore: '' }); setMostrate(RIGHE_PER_PAGINA);
    api.get(`/api/fiscal/f24-rows?document_id=${encodeURIComponent(id)}&limit=1000`)
      .then(r => { if (attivo) setRighe(r.data?.items || []); })
      .catch(e => { if (attivo) setErrore(e.response?.data?.detail || e.message || 'Lettura non riuscita'); });
    return () => { attivo = false; };
  }, [id]);

  const testata = righe && righe[0] ? righe[0] : null;
  const eQuietanza = Boolean(testata && String(testata.evidence_state || '').startsWith('QUIETANZA'));
  const anno = testata?.payment_year || null;

  useEffect(() => {
    if (!testata) return undefined;
    let attivo = true;
    if (eQuietanza) {
      api.get(`/api/f24/quietanze/${encodeURIComponent(id)}`)
        .then(r => { if (attivo) setDettaglio(r.data || {}); })
        .catch(() => { if (attivo) setDettaglio({}); });
    }
    const qs = anno ? `?anno=${encodeURIComponent(anno)}` : '';
    api.get(`/api/f24-riconciliazione/quietanze-banca${qs}`)
      .then(r => {
        if (!attivo) return;
        const gruppi = ['riscontrati', 'da_verificare', 'quietanze_senza_addebito', 'quietanze_senza_estratto',
          'modelli_da_verificare', 'addebiti_senza_quietanza', 'quietanze_incomplete', 'tributi_ripetuti', 'compensate_saldo_zero'];
        const trovati = gruppi.flatMap(g => (r.data?.[g] || []).filter(x => tocca(x, id)));
        setRiscontro({ dati: trovati, errore: '', motivi: r.data?.conferma?.motivi || {} });
      })
      .catch(e => { if (attivo) setRiscontro({ dati: null, errore: e.response?.data?.detail || e.message || 'lettura non riuscita' }); });
    return () => { attivo = false; };
  }, [id, testata, eQuietanza, anno, versioneRiscontro]);

  const totali = useMemo(() => {
    const debito = (righe || []).reduce((s, r) => s + centesimi(r.debit_amount), 0);
    const credito = (righe || []).reduce((s, r) => s + centesimi(r.credit_amount), 0);
    return { debito: debito / 100, credito: credito / 100, saldo: (debito - credito) / 100 };
  }, [righe]);

  const titolo = eQuietanza ? 'Quietanza F24' : 'Modello F24';
  const visibili = (righe || []).slice(0, mostrate);
  const rimanenti = (righe || []).length - visibili.length;
  const canale = dettaglio?.canale ? (CANALI[dettaglio.canale] || dettaglio.canale) : null;

  return (
    <div style={paginaStile} data-testid="vista-f24">
      <PageHeader
        title={testata ? `${titolo} del ${dataOppure(testata.payment_date)}` : 'F24'}
        famiglia={{ titolo: 'FISCALE', colore: COLORS.primary }}
        subtitle="Righe tributo, originale e riscontro con l'addebito in banca. Un modello non prova il pagamento: lo prova l'addebito."
        pastiglie={testata ? [
          { etichetta: 'Saldo da versare', valore: euroOppure(totali.saldo), nota: 'debiti meno crediti delle righe' },
          { etichetta: 'Righe tributo', valore: String(righe.length), nota: eQuietanza ? 'lette dalla quietanza' : 'lette dal modello' },
        ] : null}
      />

      {errore && <Messaggio tono="errore" testId="f24-errore">{errore}</Messaggio>}
      {!righe && !errore && <PageLoader />}
      {righe && righe.length === 0 && (
        <Messaggio testId="f24-non-trovato">
          Nessun F24 con questo identificativo, oppure il documento non ha righe tributo leggibili.
        </Messaggio>
      )}

      {testata && (<>
        <Riquadro titolo="Documento" testId="f24-documento">
          <GrigliaCampi>
            <Campo etichetta="Tipo">{titolo}</Campo>
            <Campo etichetta="Data di versamento">{dataOppure(testata.payment_date)}</Campo>
            <Campo etichetta="Protocollo" mono>{testata.protocol}</Campo>
            <Campo etichetta="File">{testata.filename}</Campo>
            <Campo etichetta="Canale" testId="f24-canale">{canale}</Campo>
            <Campo etichetta="Stato nel registro">{testata.registro_esito ? testoOppure(testata.registro_motivo || testata.registro_esito) : null}</Campo>
          </GrigliaCampi>
          <div style={{ marginTop: 12, display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
            <ApriOriginale
              tipo={eQuietanza ? 'quietanza' : 'f24'} id={id} url={testata.pdf_url}
              titolo={`${titolo} ${testata.protocol || ''}`.trim()} testId="f24-apri-originale"
            >
              {eQuietanza
                ? `Importo versato ${euroOppure(totali.saldo)}: apri la quietanza`
                : `Saldo del modello ${euroOppure(totali.saldo)}: apri il modello`}
            </ApriOriginale>
          </div>
        </Riquadro>

        <Riquadro titolo="Righe tributo" testId="f24-righe">
          {isMobile ? (
            <div style={{ display: 'grid', gap: 10 }} data-testid="f24-righe-card">
              {visibili.map(r => (
                <div key={r.id} style={{ border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: '10px 12px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                    <Link to={percorsoTributo(r.tax_code)} style={{ fontWeight: 700, minHeight: 44, display: 'inline-flex', alignItems: 'center' }}>
                      {testoOppure(r.tax_code)}
                    </Link>
                    <span style={{ fontSize: 13 }}>{testoOppure(r.reference_period)}</span>
                  </div>
                  <div style={{ fontSize: 12.5, color: COLORS.textMuted }}>{r.description || r.section}</div>
                  <div style={{ display: 'flex', gap: 16, fontSize: 13, marginTop: 4 }}>
                    <span>Debito <Importo valore={r.debit_amount} /></span>
                    <span>Credito <Importo valore={r.credit_amount} /></span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }} data-testid="f24-righe-tabella">
              <thead>
                <tr style={{ background: COLORS.bgAlt, textAlign: 'left' }}>
                  {['Sezione', 'Codice', 'Descrizione', 'Periodo', 'Debito', 'Credito'].map((h, i) => (
                    <th key={h} style={{ padding: '8px 10px', fontSize: 11, textTransform: 'uppercase', color: COLORS.textMuted, textAlign: i >= 4 ? 'right' : 'left' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {visibili.map(r => (
                  <tr key={r.id} style={{ borderTop: `1px solid ${COLORS.border}` }}>
                    <td style={{ padding: '8px 10px' }}>{testoOppure(r.section)}</td>
                    <td style={{ padding: '8px 10px' }}>
                      <Link to={percorsoTributo(r.tax_code)} style={{ fontWeight: 700 }}>{testoOppure(r.tax_code)}</Link>
                    </td>
                    <td style={{ padding: '8px 10px', color: COLORS.textMuted }}>{testoOppure(r.description)}</td>
                    <td style={{ padding: '8px 10px', whiteSpace: 'nowrap' }}>{testoOppure(r.reference_period)}</td>
                    <td style={{ padding: '8px 10px', textAlign: 'right' }}><Importo valore={r.debit_amount} /></td>
                    <td style={{ padding: '8px 10px', textAlign: 'right' }}><Importo valore={r.credit_amount} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {rimanenti > 0 && (
            <div style={{ textAlign: 'center', marginTop: 12 }}>
              <button type="button" data-testid="f24-mostra-altre" onClick={() => setMostrate(n => n + RIGHE_PER_PAGINA)}
                style={{ minHeight: 44, padding: '0 16px', borderRadius: 8, border: `1px solid ${COLORS.border}`, background: COLORS.card, cursor: 'pointer', fontFamily: FONT.family }}>
                Mostra altre {Math.min(RIGHE_PER_PAGINA, rimanenti)} · {rimanenti} rimanenti
              </button>
            </div>
          )}
        </Riquadro>

        <Riquadro titolo="Riscontro con la banca" testId="f24-riscontro">
          <Riscontro stato={riscontro} f24Id={id} onConfermato={() => setVersioneRiscontro(v => v + 1)} />
        </Riquadro>
      </>)}

      <LegendaRegole gruppo="f24" />
    </div>
  );
}
