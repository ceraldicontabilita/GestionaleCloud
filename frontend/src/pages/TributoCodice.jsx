import React, { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Badge, PageHeader, PageLoader } from '../components/ds';
import ApriOriginale from '../components/vista/ApriOriginale';
import FiltroAnnoVista, { useAnnoVista } from '../components/vista/FiltroAnnoVista';
import LegendaRegole from '../components/vista/LegendaRegole';
import { Messaggio, Riquadro, paginaStile } from '../components/vista/Elementi';
import { STATI_INCROCIO } from '../lib/legendaRegole';
import {
  codiceTributo, dataOppure, euroCentesimiOppure, euroCentesimiOTrattino, euroOppure, idF24DaUrl,
  percorsoF24, testoOppure,
} from '../lib/vista';
import { COLORS, FONT, useIsMobile } from '../lib/utils';
import api from '../api';

/**
 * VISTA TRIBUTO — `/fiscale/tributi/:codice`.
 *
 * Un codice tributo, anno per anno: che cosa e' stato pagato, con quale
 * quietanza (l'importo versato e' un bottone che apre l'originale), che cosa
 * resta da pagare. Per i codici che hanno un dovuto certo altrove (IVA
 * mensile 6001–6012 dalla LIPE, IRAP 3800 dalla dichiarazione, 6099 dall'IVA
 * annuale) sotto c'e' l'incrocio, dal motore unico `/api/fiscale/incroci`.
 *
 * Sola lettura. Il filtro anno e' quello globale (`?anno=tutti` per tutti).
 */

const RIGHE_PER_PAGINA = 200;
const IVA_MENSILE = /^60(0[1-9]|1[0-2])$/;

const VARIANTE_STATO = {
  PAGATO: 'success', PAGATO_IN_RITARDO: 'warning', RAVVEDUTO: 'accent', PAGATO_BANCA: 'info',
  COMPENSATO: 'info', DA_PAGARE: 'primary', SCADUTO: 'danger', ATTESO: 'warning', CREDITO: 'info',
};
const VARIANTE_INCROCIO = { OK: 'success', MANCANTE: 'danger', PARZIALE: 'warning', ECCEDENTE: 'warning', NON_DETERMINABILE: 'neutral' };

const TIPI_QUIETANZA = ['quietanza', 'ravvedimento', 'compensazione', 'credito'];

const quietanzaDi = voce => (voce.documenti || []).find(d => TIPI_QUIETANZA.includes(d.tipo) && d.pdf_url) || null;

/** Le righe dell'incrocio che riguardano il codice, con la stessa forma per i tre casi. */
export function righeIncrocio(dati, codice) {
  if (!dati) return [];
  if (IVA_MENSILE.test(codice)) {
    return (dati.confronti_iva_mensile || []).filter(r => r.codice_tributo === codice).map(r => ({
      chiave: `mese-${r.lipe_id}`, periodo: `${r.mese_nome} ${r.anno}`, fonteDovuto: 'LIPE',
      dovuto: r.dovuto_da_lipe, versato: r.versato_f24, differenza: r.differenza, stato: r.stato,
      nota: r.nota, versamenti: r.f24_versamenti || [],
    }));
  }
  const annuali = codice === '3800' ? dati.irap_riscontro : codice === '6099' ? dati.iva_annuale_riscontro : [];
  return (annuali || []).filter(r => r.codice_tributo === codice).map(r => ({
    chiave: `anno-${r.anno_imposta}-${r.document_id}`, periodo: `Anno d'imposta ${r.anno_imposta}`,
    fonteDovuto: `Dichiarazione (rigo ${r.rigo})`, dovuto: r.importo_dichiarato, versato: r.importo_versato,
    differenza: r.differenza, stato: r.stato, nota: r.nota, versamenti: r.f24_versamenti || [],
  }));
}

function Importo({ children }) {
  return <span style={{ fontFamily: FONT.mono, fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }}>{children}</span>;
}

/** L'importo versato: se c'e' una quietanza con originale, e' il bottone che la apre. */
function ImportoVersato({ voce }) {
  const testo = euroCentesimiOTrattino(voce.quietanza_cents);
  const q = quietanzaDi(voce);
  if (!q || !voce.quietanza_cents) return <Importo>{testo}</Importo>;
  const idF24 = idF24DaUrl(q.pdf_url);
  return (
    <span style={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'flex-end', gap: 2 }}>
      <ApriOriginale
        url={q.pdf_url} variante="ghost" testId={`apri-quietanza-${voce.chiave}`}
        titolo={`Quietanza ${q.protocollo || ''}`.trim()} style={{ padding: '0 8px', fontWeight: 700, color: COLORS.primaryDark }}
      >
        <Importo>{testo}</Importo>
      </ApriOriginale>
      {idF24 && (
        <Link to={percorsoF24(idF24)} style={{ fontSize: 12, minHeight: 44, display: 'inline-flex', alignItems: 'center' }} data-testid={`scheda-f24-${voce.chiave}`}>
          Scheda dell'F24
        </Link>
      )}
    </span>
  );
}

function Incroci({ stato, codice }) {
  if (stato.errore) return <Messaggio tono="errore" testId="incroci-errore">Incrocio non disponibile: {stato.errore}</Messaggio>;
  if (!stato.dati) return <PageLoader />;
  const righe = righeIncrocio(stato.dati, codice);
  if (!righe.length) {
    return <p data-testid="incroci-vuoto" style={{ margin: 0, color: COLORS.textMuted, fontSize: 14 }}>
      Nessun dovuto da incrociare per questo codice e questo anno.
    </p>;
  }
  return (
    <div style={{ display: 'grid', gap: 10 }} data-testid="incroci-righe">
      {righe.map(r => (
        <div key={r.chiave} style={{ border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: '10px 12px' }}>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <strong>{r.periodo}</strong>
            <Badge variant={VARIANTE_INCROCIO[r.stato] || 'neutral'}>{STATI_INCROCIO[r.stato] || testoOppure(r.stato)}</Badge>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 8, marginTop: 6, fontSize: 13 }}>
            <div><div style={{ color: COLORS.textMuted, fontSize: 11.5 }}>Dovuto ({r.fonteDovuto})</div><Importo>{euroOppure(r.dovuto)}</Importo></div>
            <div><div style={{ color: COLORS.textMuted, fontSize: 11.5 }}>Versato con F24</div><Importo>{euroOppure(r.versato)}</Importo></div>
            <div><div style={{ color: COLORS.textMuted, fontSize: 11.5 }}>Differenza</div><Importo>{euroOppure(r.differenza)}</Importo></div>
          </div>
          {r.nota && <p style={{ margin: '6px 0 0', fontSize: 12.5, color: COLORS.textMuted }}>{r.nota}</p>}
          {r.versamenti.length > 0 && (
            <div style={{ marginTop: 6, display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              {r.versamenti.map(v => (
                <span key={`${v.id}-${v.periodo}`} style={{ display: 'inline-flex', gap: 6, alignItems: 'center', fontSize: 12.5 }}>
                  <ApriOriginale
                    tipo={v.quietanza ? 'quietanza' : 'f24'} id={v.id} variante="secondary"
                    testId={`apri-versamento-${v.id}`} titolo={`${v.quietanza ? 'Quietanza' : 'Modello'} ${v.protocollo || ''}`.trim()}
                  >
                    {euroOppure(v.importo)} del {dataOppure(v.data_versamento)}
                  </ApriOriginale>
                  <Link to={percorsoF24(v.id)}>Scheda</Link>
                </span>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

export default function TributoCodice() {
  const { codice: codiceGrezzo } = useParams();
  const codice = codiceTributo(codiceGrezzo);
  const isMobile = useIsMobile(1024);
  const filtro = useAnnoVista();
  const [dati, setDati] = useState(null);
  const [errore, setErrore] = useState('');
  const [incroci, setIncroci] = useState({ dati: null, errore: '' });
  const [mostrate, setMostrate] = useState(RIGHE_PER_PAGINA);

  const haIncrocio = IVA_MENSILE.test(codice) || codice === '3800' || codice === '6099';

  useEffect(() => {
    let attivo = true;
    setDati(null); setErrore(''); setMostrate(RIGHE_PER_PAGINA);
    const qs = new URLSearchParams({ cerca: codice });
    if (filtro.anno) qs.set('anno', String(filtro.anno));
    api.get(`/api/f24/tributi?${qs}`)
      .then(r => { if (attivo) setDati(r.data || {}); })
      .catch(e => { if (attivo) setErrore(e.response?.data?.detail || e.message || 'Lettura non riuscita'); });
    return () => { attivo = false; };
  }, [codice, filtro.anno]);

  useEffect(() => {
    if (!haIncrocio) return undefined;
    let attivo = true;
    setIncroci({ dati: null, errore: '' });
    const qs = filtro.anno ? `?anni=${filtro.anno}` : '';
    api.get(`/api/fiscale/incroci${qs}`)
      .then(r => { if (attivo) setIncroci({ dati: r.data, errore: '' }); })
      .catch(e => { if (attivo) setIncroci({ dati: null, errore: e.response?.data?.detail || e.message || 'lettura non riuscita' }); });
    return () => { attivo = false; };
  }, [haIncrocio, filtro.anno]);

  // `cerca` e' una ricerca per testo: il codice vero si tiene per uguaglianza.
  const voci = useMemo(() => (dati?.voci || []).filter(v => codiceTributo(v.codice) === codice), [dati, codice]);
  const visibili = voci.slice(0, mostrate);
  const rimanenti = voci.length - visibili.length;
  const descrizione = voci[0]?.descrizione || null;
  const somma = campo => voci.reduce((s, v) => s + Number(v[campo] || 0), 0);

  return (
    <div style={paginaStile} data-testid="vista-tributo">
      <PageHeader
        title={`Tributo ${codice}`}
        famiglia={{ titolo: 'FISCALE', colore: COLORS.primary }}
        subtitle={descrizione || 'Che cosa è stato pagato e che cosa resta da pagare, periodo per periodo.'}
        pastiglie={dati && voci.length ? [
          { etichetta: 'Pagato con quietanza', valore: euroCentesimiOppure(somma('quietanza_cents')), nota: voci.length === 1 ? '1 periodo' : `${voci.length} periodi`, tono: 'ok' },
          { etichetta: 'Con ravvedimento', valore: euroCentesimiOppure(somma('ravvedimento_cents')) },
          { etichetta: 'Resta da pagare', valore: euroCentesimiOppure(somma('residuo_cents')), tono: somma('residuo_cents') ? 'male' : 'ok' },
        ] : null}
      />

      <div style={{ margin: '12px 0' }}><FiltroAnnoVista stato={filtro} /></div>
      <Link to="/tributi" style={{ fontSize: 13, minHeight: 44, display: 'inline-flex', alignItems: 'center' }}>Tutti i codici tributo</Link>

      {errore && <Messaggio tono="errore" testId="tributo-errore">{errore}</Messaggio>}
      {!dati && !errore && <PageLoader />}
      {dati && voci.length === 0 && (
        <Messaggio testId="tributo-vuoto">
          Nessun pagamento del codice {codice} {filtro.tutti ? 'in archivio' : `nel ${filtro.anno}`}.
          {!filtro.tutti && ' Prova con «Tutti gli anni».'}
        </Messaggio>
      )}

      {voci.length > 0 && (
        <Riquadro titolo="Periodo per periodo" testId="tributo-periodi" style={{ padding: isMobile ? '12px' : '14px 16px' }}>
          {isMobile ? (
            <div style={{ display: 'grid', gap: 10 }} data-testid="tributo-card">
              {visibili.map(v => (
                <div key={v.chiave} style={{ border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: '10px 12px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center' }}>
                    <strong>{testoOppure(v.periodo)}</strong>
                    <Badge variant={VARIANTE_STATO[v.stato] || 'neutral'}>{testoOppure(v.stato_label)}</Badge>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px 12px', fontSize: 12.5, marginTop: 6 }}>
                    <div><div style={{ color: COLORS.textMuted }}>Inviato dal commercialista</div><Importo>{euroCentesimiOTrattino(v.inviato_cents)}</Importo></div>
                    <div><div style={{ color: COLORS.textMuted }}>Versato con quietanza</div><ImportoVersato voce={v} /></div>
                    <div><div style={{ color: COLORS.textMuted }}>Resta da pagare</div><Importo>{euroCentesimiOppure(v.residuo_cents)}</Importo></div>
                    <div><div style={{ color: COLORS.textMuted }}>Ultimo pagamento</div>{dataOppure(v.ultimo_pagamento)}</div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }} data-testid="tributo-tabella">
              <thead>
                <tr style={{ background: COLORS.bgAlt }}>
                  {[
                    ['Periodo', 'Mese o anno a cui si riferisce il tributo'],
                    ['Inviato', 'Importo inviato dal commercialista'],
                    ['Versato', 'Pagato con quietanza: si apre cliccando l\'importo'],
                    ['Ravvedimento', 'Pagato in ritardo con sanzioni e interessi'],
                    ['Credito', 'A credito o compensato in altre deleghe'],
                    ['Resta', 'Resta da pagare'],
                    ['Ultimo versamento', 'Data dell\'ultimo pagamento'],
                    ['Stato', 'Stato del periodo'],
                  ].map(([h, spiega], i) => (
                    <th key={h} title={spiega} style={{ padding: '8px 10px', fontSize: 11, textTransform: 'uppercase', color: COLORS.textMuted, textAlign: i >= 1 && i <= 5 ? 'right' : 'left' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {visibili.map(v => (
                  <tr key={v.chiave} data-testid={`riga-${v.chiave}`} style={{ borderTop: `1px solid ${COLORS.border}` }}>
                    <td style={{ padding: '6px 10px', whiteSpace: 'nowrap' }}>{testoOppure(v.periodo)}</td>
                    <td style={{ padding: '6px 10px', textAlign: 'right' }}><Importo>{euroCentesimiOTrattino(v.inviato_cents)}</Importo></td>
                    <td style={{ padding: '6px 10px', textAlign: 'right' }}><ImportoVersato voce={v} /></td>
                    <td style={{ padding: '6px 10px', textAlign: 'right' }}><Importo>{euroCentesimiOTrattino(v.ravvedimento_cents)}</Importo></td>
                    <td style={{ padding: '6px 10px', textAlign: 'right' }}><Importo>{euroCentesimiOTrattino(v.credito_cents)}</Importo></td>
                    <td style={{ padding: '6px 10px', textAlign: 'right' }}><Importo>{euroCentesimiOppure(v.residuo_cents)}</Importo></td>
                    <td style={{ padding: '6px 10px', whiteSpace: 'nowrap' }}>{dataOppure(v.ultimo_pagamento)}</td>
                    <td style={{ padding: '6px 10px' }}><Badge variant={VARIANTE_STATO[v.stato] || 'neutral'}>{testoOppure(v.stato_label)}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          )}
          {rimanenti > 0 && (
            <div style={{ textAlign: 'center', marginTop: 12 }}>
              <button type="button" data-testid="tributo-mostra-altre" onClick={() => setMostrate(n => n + RIGHE_PER_PAGINA)}
                style={{ minHeight: 44, padding: '0 16px', borderRadius: 8, border: `1px solid ${COLORS.border}`, background: COLORS.card, cursor: 'pointer', fontFamily: FONT.family }}>
                Mostra altre {Math.min(RIGHE_PER_PAGINA, rimanenti)} · {rimanenti} rimanenti
              </button>
            </div>
          )}
        </Riquadro>
      )}

      {haIncrocio && (
        <Riquadro
          titolo={IVA_MENSILE.test(codice) ? 'Incrocio con la LIPE' : 'Incrocio con la dichiarazione'}
          testId="tributo-incroci"
        >
          <Incroci stato={incroci} codice={codice} />
        </Riquadro>
      )}

      <LegendaRegole gruppo="tributi" />
    </div>
  );
}
