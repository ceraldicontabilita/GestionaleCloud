import React, { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Badge, PageHeader, PageLoader } from '../components/ds';
import LegendaRegole from '../components/vista/LegendaRegole';
import { Campo, GrigliaCampi, Messaggio, Riquadro, paginaStile } from '../components/vista/Elementi';
import { AMBITI, CAMPI_SCHEDA_PROTOCOLLO as CAMPI, STATO_PROTOCOLLO, leggiProtocollo } from '../lib/protocolloVista';
import { CANALI } from '../lib/legendaRegole';
import { dataOppure, euroOppure } from '../lib/vista';
import { COLORS } from '../lib/utils';

/**
 * VISTA PROTOCOLLO — `/protocollo/:id` (id = `AAAA/NNNNNN`, anche come
 * `/protocollo/AAAA/NNNNNN`).
 *
 * Scheda di un documento del protocollo personale e familiare (API di
 * MINI-07). Il documento personale non entra mai nei conti dell'azienda: lo
 * dice la pagina, sempre. I documenti che la contabilita' conosce gia' (stessa
 * impronta SHA-256) sono un ponte solo informativo: link alla sezione
 * esistente, mai dati copiati qui. L'originale si apre con DRV-04, che per il
 * protocollo non c'e' ancora: la pagina mostra il nome del file, senza
 * aprire indirizzi Drive da fuori.
 * `carica` si puo' sostituire (test, anteprime).
 */
export default function ProtocolloScheda({ carica = leggiProtocollo }) {
  const { id, anno, progressivo } = useParams();
  const numero = id ?? `${anno}/${progressivo}`;
  const [esito, setEsito] = useState(null);

  useEffect(() => {
    let attivo = true;
    setEsito(null);
    carica(numero)
      .then(r => { if (attivo) setEsito(r); })
      .catch(e => { if (attivo) setEsito({ stato: STATO_PROTOCOLLO.ERRORE, messaggio: e?.message || 'Lettura non riuscita' }); });
    return () => { attivo = false; };
  }, [numero, carica]);

  const dati = esito?.stato === STATO_PROTOCOLLO.DISPONIBILE ? (esito.dati || {}) : null;
  const collegati = dati?.collegati?.documenti || [];

  return (
    <div style={paginaStile} data-testid="vista-protocollo">
      <PageHeader
        title={dati?.numero ? `Protocollo ${dati.numero}` : 'Protocollo personale'}
        famiglia={{ titolo: 'ARCHIVIO', colore: COLORS.primary }}
        subtitle={dati?.oggetto || "Documenti personali e di famiglia, conservati per ricerca. Non entrano mai nei conti dell'azienda."}
      />

      {!esito && <PageLoader />}
      {esito?.stato === STATO_PROTOCOLLO.NON_DISPONIBILE && (
        <Messaggio testId="protocollo-non-disponibile">
          Il protocollo personale non è ancora disponibile su questo servizio.
        </Messaggio>
      )}
      {esito?.stato === STATO_PROTOCOLLO.NON_TROVATO && (
        <Messaggio testId="protocollo-non-trovato">Nessun documento con questo numero di protocollo.</Messaggio>
      )}
      {esito?.stato === STATO_PROTOCOLLO.ERRORE && <Messaggio tono="errore" testId="protocollo-errore">{esito.messaggio}</Messaggio>}

      {dati && (<>
        <Riquadro titolo="Documento" testId="protocollo-scheda">
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
            <Badge variant="neutral" data-testid="protocollo-ambito">{AMBITI[dati.ambito] || 'Ambito non indicato'}</Badge>
            {dati.stato === 'rimosso' && <Badge variant="warning">Rimosso dall'archivio</Badge>}
          </div>
          <GrigliaCampi>
            <Campo etichetta={CAMPI.numero} mono>{dati.numero}</Campo>
            <Campo etichetta={CAMPI.data_protocollo}>{dati.data_protocollo ? dataOppure(dati.data_protocollo) : null}</Campo>
            <Campo etichetta={CAMPI.data_documento}>{dati.data_documento ? dataOppure(dati.data_documento) : null}</Campo>
            <Campo etichetta={CAMPI.tipo_documento}>{dati.tipo_documento}</Campo>
            <Campo etichetta={CAMPI.direzione}>{dati.direzione}</Campo>
            <Campo etichetta={CAMPI.controparte}>{dati.controparte}</Campo>
            <Campo etichetta={CAMPI.pratica}>{dati.pratica}</Campo>
            <Campo etichetta={CAMPI.importo} mono>{dati.importo === null || dati.importo === undefined || dati.importo === '' ? null : euroOppure(dati.importo)}</Campo>
            <Campo etichetta={CAMPI.nome_file}>{dati.nome_file}</Campo>
            <Campo etichetta={CAMPI.canale}>{dati.canale ? (CANALI[dati.canale] || dati.canale) : null}</Campo>
          </GrigliaCampi>
          {dati.stato === 'rimosso' && dati.rimosso_motivo && (
            <p style={{ margin: '12px 0 0', fontSize: 13.5 }}>Motivo: {dati.rimosso_motivo}</p>
          )}
        </Riquadro>

        <Riquadro titolo="Documenti collegati (solo da consultare)" testId="protocollo-collegati">
          {collegati.length === 0 ? (
            <p data-testid="protocollo-nessun-collegato" style={{ margin: 0, color: COLORS.textMuted, fontSize: 14 }}>
              Nessun documento dell'azienda risulta collegato a questo file.
            </p>
          ) : (
            <div style={{ display: 'grid', gap: 8 }}>
              {collegati.map(c => (
                <div key={`${c.collezione || c.tipo}-${c.id}`} data-testid="protocollo-collegato"
                  style={{ border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: '8px 12px', fontSize: 13.5 }}>
                  <strong>{c.tipo || 'Documento'}</strong>{' '}
                  {c.rotta
                    ? <Link to={c.rotta} style={{ minHeight: 44, display: 'inline-flex', alignItems: 'center' }}>Apri nella sua sezione</Link>
                    : <span style={{ color: COLORS.textMuted }}>sezione non indicata</span>}
                </div>
              ))}
            </div>
          )}
        </Riquadro>
      </>)}

      <LegendaRegole gruppo="protocollo" />
    </div>
  );
}
