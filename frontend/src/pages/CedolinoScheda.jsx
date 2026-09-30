import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Badge, PageHeader, PageLoader } from '../components/ds';
import ApriOriginale from '../components/vista/ApriOriginale';
import LegendaRegole from '../components/vista/LegendaRegole';
import { Campo, GrigliaCampi, Messaggio, Riquadro, paginaStile } from '../components/vista/Elementi';
import { CANALI, NETTO_FONTE } from '../lib/legendaRegole';
import { dataOppure, euroOppure, testoOppure } from '../lib/vista';
import { COLORS, FONT } from '../lib/utils';
import api from '../api';

/**
 * VISTA BUSTA PAGA — `/personale/cedolini/:id`.
 *
 * Una busta con il suo netto e da dove viene (cella del PDF o Libro Unico
 * senza cella), il canale d'arrivo, le versioni della stessa busta e la
 * decisione del motore unico (`services/cedolini_versioni`). Sola lettura da
 * `GET /api/cedolini/{id}`. Un importo che il server non ha e' «Dato non
 * disponibile»: mai zero (regola del netto).
 */

const TIPI = { mensile: 'Mensile', tredicesima: '13ª mensilità', quattordicesima: '14ª mensilità' };
const ESITI = {
  vincitore: 'Una versione vale più delle altre',
  da_decidere: 'Da decidere: due netti diversi senza un segno per scegliere',
  stesso_netto: 'Stesso netto: sono copie',
  unica: 'Versione unica',
};

const Importo = ({ valore }) => (
  <span style={{ fontFamily: FONT.mono, fontVariantNumeric: 'tabular-nums' }}>{euroOppure(valore)}</span>
);

export default function CedolinoScheda() {
  const { id } = useParams();
  const [dati, setDati] = useState(null);
  const [errore, setErrore] = useState('');
  const [nonTrovato, setNonTrovato] = useState(false);

  useEffect(() => {
    let attivo = true;
    setDati(null); setErrore(''); setNonTrovato(false);
    api.get(`/api/cedolini/${encodeURIComponent(id)}`)
      .then(r => { if (attivo) setDati(r.data); })
      .catch(e => {
        if (!attivo) return;
        if (e.response?.status === 404) setNonTrovato(true);
        else setErrore(e.response?.data?.detail || e.message || 'Lettura non riuscita');
      });
    return () => { attivo = false; };
  }, [id]);

  const v = dati?.versione || {};
  const titolo = dati ? `Busta paga ${testoOppure(dati.periodo)}` : 'Busta paga';

  return (
    <div style={paginaStile} data-testid="vista-cedolino">
      <PageHeader
        title={titolo}
        famiglia={{ titolo: 'PERSONALE', colore: COLORS.primary }}
        subtitle={dati?.dipendente || 'Il netto letto dal PDF, le versioni e il canale da cui è arrivata.'}
        pastiglie={dati ? [
          { etichetta: 'Netto', valore: euroOppure(dati.netto), nota: NETTO_FONTE[dati.netto_fonte] || 'Fonte del netto non indicata', tono: dati.netto === null ? 'attenzione' : 'neutro' },
          { etichetta: 'Lordo', valore: euroOppure(dati.lordo) },
          { etichetta: 'Trattenute', valore: euroOppure(dati.totale_trattenute) },
        ] : null}
      />

      {errore && <Messaggio tono="errore" testId="cedolino-errore">{errore}</Messaggio>}
      {nonTrovato && <Messaggio testId="cedolino-non-trovato">Nessuna busta paga con questo identificativo.</Messaggio>}
      {!dati && !errore && !nonTrovato && <PageLoader />}

      {dati && (<>
        <Riquadro titolo="Busta" testId="cedolino-scheda">
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
            {dati.sostituito && <Badge variant="warning" data-testid="badge-sostituita">Sostituita da un'altra versione</Badge>}
            {v.stampa_di_controllo && <Badge variant="neutral">Stampa di controllo</Badge>}
            {v.rettificato && <Badge variant="accent">Rettificata</Badge>}
            {v.da_decidere && <Badge variant="danger">Da decidere</Badge>}
            {dati.pagato ? <Badge variant="success">Pagata</Badge> : <Badge variant="neutral">Non risulta pagata</Badge>}
          </div>
          <GrigliaCampi>
            <Campo etichetta="Dipendente">{dati.dipendente}</Campo>
            <Campo etichetta="Periodo">{dati.periodo}</Campo>
            <Campo etichetta="Tipo">{dati.tipo ? (TIPI[dati.tipo] || dati.tipo) : null}</Campo>
            <Campo etichetta="Canale" testId="cedolino-canale">{dati.canale ? (CANALI[dati.canale] || dati.canale) : null}</Campo>
            <Campo etichetta="Fonte del netto" testId="cedolino-netto-fonte">{dati.netto_fonte ? (NETTO_FONTE[dati.netto_fonte] || dati.netto_fonte) : null}</Campo>
            <Campo etichetta="Variante" testId="cedolino-variante">{v.variante === null || v.variante === undefined ? null : `Variante ${v.variante}`}</Campo>
            <Campo etichetta="Versioni della stessa busta">{v.n_versioni_totali}</Campo>
            <Campo etichetta="File">{dati.filename}</Campo>
          </GrigliaCampi>
          <div style={{ marginTop: 12 }}>
            <ApriOriginale
              tipo="cedolino" id={dati.pdf_url ? dati.id : null} url={dati.pdf_url}
              titolo={`Busta paga ${dati.periodo || ''}`.trim()} documentType="cedolino" testId="cedolino-apri-originale"
            />
          </div>
        </Riquadro>

        {(dati.versioni_gruppo || []).length > 1 && (
          <Riquadro titolo="Versioni della stessa busta" testId="cedolino-versioni">
            {dati.decisione && (
              <p style={{ margin: '0 0 10px', fontSize: 13.5 }} data-testid="cedolino-decisione">
                <strong>{ESITI[dati.decisione.esito] || testoOppure(dati.decisione.esito)}.</strong>{' '}
                {dati.decisione.motivo}
              </p>
            )}
            <div style={{ display: 'grid', gap: 8 }}>
              {dati.versioni_gruppo.map(r => (
                <div key={r.id} data-testid="cedolino-versione" style={{
                  border: `1px solid ${r.corrente ? COLORS.primary : COLORS.border}`, borderRadius: 10, padding: '8px 12px',
                  display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center', fontSize: 13,
                }}>
                  <strong>{r.corrente ? 'Questa busta' : 'Altra versione'}</strong>
                  <span>Netto <Importo valore={r.netto} /></span>
                  {r.variante !== null && r.variante !== undefined && <span>Variante {r.variante}</span>}
                  {r.stampa_di_controllo && <Badge variant="neutral">Stampa di controllo</Badge>}
                  <span style={{ color: COLORS.textMuted }}>{testoOppure(r.filename)}</span>
                </div>
              ))}
            </div>
          </Riquadro>
        )}

        {(v.storico_netto || []).length > 0 && (
          <Riquadro titolo="Storico del netto" testId="cedolino-storico">
            <div style={{ display: 'grid', gap: 6, fontSize: 13 }}>
              {v.storico_netto.map((s, i) => (
                <div key={`${s.at}-${i}`}>
                  {dataOppure(s.at)}: da <Importo valore={s.prima} /> a <Importo valore={s.dopo} />
                </div>
              ))}
            </div>
          </Riquadro>
        )}
      </>)}

      <LegendaRegole gruppo="cedolini" />
    </div>
  );
}
