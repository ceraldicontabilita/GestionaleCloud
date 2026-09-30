import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Ban, Check, Download, Mail, MailCheck, Minus, Package, Send, TriangleAlert,
} from 'lucide-react';

import api from '../../api';
import { COLORS, BORDER_RADIUS, FONT, SHADOWS, formatDateIT } from '../../lib/utils';
import { queryPeriodo } from '../../lib/periodoCommercialista';
import { scaricaOriginale } from '../../lib/scaricaOriginale';
import { Badge, Button, Card } from '../ds';
import Portal from '../Portal';

/**
 * «Pacchetto da inviare»: una scheda per ogni documento del commercialista (Prima Nota
 * Cassa, banca, PayPal, SumUp, bonifici, corrispettivi...). Ogni scheda dice quante righe
 * ci sono, il totale e se e' pronta, incompleta (col motivo), vuota o non disponibile; si
 * spunta «Includi» e un solo bottone manda UNA email con tutti gli allegati, costruiti dal
 * server (non dal browser).
 */
export const STATI_VOCE = {
  pronto: { label: 'Pronto', variant: 'success', Icona: Check },
  incompleto: { label: 'Incompleto', variant: 'warning', Icona: TriangleAlert },
  vuoto: { label: 'Vuoto', variant: 'neutral', Icona: Minus },
  non_disponibile: { label: 'Non disponibile', variant: 'danger', Icona: Ban },
  da_inviare: { label: 'Da inviare', variant: 'primary', Icona: Send },
  gia_inviato: { label: 'Già inviato', variant: 'info', Icona: MailCheck },
};

const SELEZIONABILI = ['pronto', 'incompleto', 'da_inviare'];

const euro = testo => (testo ? `€ ${testo}` : '');

function Chip({ selezionata, disabilitata, onClick, testId, children }) {
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={selezionata}
      aria-disabled={disabilitata}
      disabled={disabilitata}
      data-testid={testId}
      onClick={onClick}
      style={{
        minHeight: 44, padding: '0 14px', display: 'inline-flex', alignItems: 'center', gap: 6,
        borderRadius: BORDER_RADIUS.full, fontWeight: 700, fontSize: 13, fontFamily: FONT.family,
        border: `1px solid ${selezionata ? COLORS.primary : COLORS.border}`,
        background: selezionata ? COLORS.primary : COLORS.card,
        color: selezionata ? '#fff' : (disabilitata ? COLORS.textSubtle : COLORS.text),
        cursor: disabilitata ? 'not-allowed' : 'pointer',
      }}
    >
      {selezionata && <Check size={14} aria-hidden="true" />}
      {children}
    </button>
  );
}

const RIGHE_ANTEPRIMA = 8;

/** Le prime righe di ogni sezione del documento, come testo: si controlla prima di inviare. */
function Anteprima({ dettaglio }) {
  const sezioni = (dettaglio?.sezioni || []).filter(sez => sez.righe?.length);
  if (!sezioni.length) return <p style={{ margin: 0, fontSize: 12, color: COLORS.textMuted }}>Nessuna riga nel periodo.</p>;
  return (
    <div style={{ fontSize: 12 }}>
      {sezioni.map((sez, i) => (
        <div key={i} style={{ marginTop: i ? 8 : 0 }}>
          {sez.titolo && <div style={{ fontWeight: 700, color: COLORS.text }}>{sez.titolo}</div>}
          {sez.righe.slice(0, RIGHE_ANTEPRIMA).map((riga, r) => (
            <div key={r} style={{ padding: '3px 0', borderTop: `1px solid ${COLORS.border}`, overflowWrap: 'anywhere' }}>
              {riga.filter(Boolean).join(' · ')}
            </div>
          ))}
          {sez.righe.length > RIGHE_ANTEPRIMA && (
            <div style={{ color: COLORS.textMuted }}>e altre {sez.righe.length - RIGHE_ANTEPRIMA} righe nel PDF</div>
          )}
        </div>
      ))}
    </div>
  );
}

function SchedaVoce({ voce, urlDettaglio, selezionata, onSeleziona, onScarica, scaricando, onRinvia, confermaRinvia, onConfermaRinvio, onAnnullaRinvio }) {
  const [anteprima, setAnteprima] = useState(null); // null = chiusa
  const [caricandoAnteprima, setCaricandoAnteprima] = useState(false);
  const apriAnteprima = async () => {
    if (anteprima) {
      setAnteprima(null);
      return;
    }
    setCaricandoAnteprima(true);
    try {
      const { data } = await api.get(urlDettaglio);
      setAnteprima({ dettaglio: data });
    } catch (e) {
      setAnteprima({ errore: e.response?.data?.detail || e.message || 'Anteprima non disponibile' });
    } finally {
      setCaricandoAnteprima(false);
    }
  };
  const stato = STATI_VOCE[voce.stato] || STATI_VOCE.vuoto;
  const Icona = stato.Icona;
  const inviabile = SELEZIONABILI.includes(voce.stato);
  const presenzeGiaInviate = voce.voce === 'presenze' && voce.stato === 'gia_inviato';
  const ultimo = voce.ultimo_invio;
  return (
    <div
      data-testid={`voce-${voce.voce}`}
      style={{
        background: COLORS.card, border: `1px solid ${selezionata ? COLORS.primary : COLORS.border}`,
        borderRadius: BORDER_RADIUS.md, padding: 14, display: 'flex', flexDirection: 'column', gap: 8,
        minWidth: 0, boxShadow: SHADOWS.sm,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
        <strong style={{ fontSize: 14, color: COLORS.text, overflowWrap: 'anywhere' }}>{voce.titolo}</strong>
        <Badge variant={stato.variant} data-testid={`stato-${voce.voce}`} style={{ whiteSpace: 'nowrap', flexShrink: 0 }}>
          <Icona size={11} aria-hidden="true" style={{ marginRight: 4, verticalAlign: '-1px' }} />
          {stato.label}
        </Badge>
      </div>

      <div style={{ fontSize: 13, color: COLORS.text }} data-testid={`conteggio-${voce.voce}`}>
        {voce.voce === 'presenze'
          ? `${voce.conteggio} ${voce.conteggio === 1 ? 'mese' : 'mesi'} con presenze`
          : `${voce.conteggio} ${voce.conteggio === 1 ? 'riga' : 'righe'}`}
        {voce.totale && voce.voce !== 'presenze' ? ` · ${euro(voce.totale)}` : ''}
      </div>

      {voce.motivo && voce.stato !== 'pronto' && (
        <div style={{ fontSize: 12, color: voce.stato === 'non_disponibile' ? COLORS.danger : COLORS.warning }}
          data-testid={`motivo-${voce.voce}`}>
          {voce.motivo}
        </div>
      )}
      {voce.voce === 'carnet_assegni' && voce.carnetScelti > 0 && (
        <div style={{ fontSize: 12, color: COLORS.textMuted }}>{voce.carnetScelti} carnet scelti nella card Carnet</div>
      )}

      <div style={{ fontSize: 12, color: COLORS.textMuted }} data-testid={`ultimo-${voce.voce}`}>
        {ultimo ? `Ultimo invio ${formatDateIT(ultimo.data)}${ultimo.destinatario ? ` a ${ultimo.destinatario}` : ''}`
          : 'Mai inviato per questo periodo'}
      </div>

      {confermaRinvia && (
        <div role="alert" style={{ background: COLORS.warningLight, borderRadius: BORDER_RADIUS.sm, padding: 10, fontSize: 12 }}>
          Le presenze risultano già inviate. Rimandarle al commercialista?
          <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
            <Button size="sm" variant="primary" onClick={onConfermaRinvio} style={{ minHeight: 44 }}>Sì, rinvia</Button>
            <Button size="sm" variant="secondary" onClick={onAnnullaRinvio} style={{ minHeight: 44 }}>Annulla</Button>
          </div>
        </div>
      )}

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 'auto' }}>
        {presenzeGiaInviate && !selezionata ? (
          <Button variant="secondary" onClick={onRinvia} data-testid="rinvia-presenze" style={{ minHeight: 44 }}>
            Rinvia
          </Button>
        ) : (
          <Chip
            selezionata={selezionata}
            disabilitata={!inviabile && !(presenzeGiaInviate && selezionata)}
            onClick={onSeleziona}
            testId={`includi-${voce.voce}`}
          >
            Includi
          </Chip>
        )}
        <Button
          variant="secondary"
          onClick={onScarica}
          disabled={scaricando || voce.stato === 'vuoto' || voce.stato === 'non_disponibile'}
          data-testid={`scarica-${voce.voce}`}
          iconLeft={<Download size={14} aria-hidden="true" />}
          style={{ minHeight: 44 }}
        >
          {scaricando ? 'Scarico…' : 'Scarica'}
        </Button>
        <Button
          variant="ghost"
          onClick={apriAnteprima}
          disabled={caricandoAnteprima || voce.stato === 'vuoto' || voce.stato === 'non_disponibile'}
          aria-expanded={!!anteprima}
          data-testid={`anteprima-${voce.voce}`}
          style={{ minHeight: 44 }}
        >
          {anteprima ? 'Nascondi' : caricandoAnteprima ? 'Carico…' : 'Anteprima'}
        </Button>
      </div>

      {anteprima && (
        <div data-testid={`dettaglio-${voce.voce}`} style={{ borderTop: `1px solid ${COLORS.border}`, paddingTop: 8 }}>
          {anteprima.errore
            ? <p role="alert" style={{ margin: 0, fontSize: 12, color: COLORS.danger }}>{anteprima.errore}</p>
            : <Anteprima dettaglio={anteprima.dettaglio} />}
        </div>
      )}
    </div>
  );
}

function ModaleInvio({ periodo, destinatario, voci, esiti, inviando, errore, onConferma, onChiudi }) {
  const primoRef = useRef(null);
  useEffect(() => {
    primoRef.current?.focus();
    const esc = e => { if (e.key === 'Escape' && !inviando) onChiudi(); };
    window.addEventListener('keydown', esc);
    return () => window.removeEventListener('keydown', esc);
  }, [inviando, onChiudi]);

  return (
    <Portal>
      <div
        style={{
          position: 'fixed', inset: 0, background: 'rgba(20,20,19,0.45)', zIndex: 1000,
          display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16,
        }}
      >
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="titolo-invio-pacchetto"
          data-testid="modale-invio-pacchetto"
          style={{
            background: COLORS.card, borderRadius: BORDER_RADIUS.lg, width: '100%', maxWidth: 560,
            maxHeight: '90vh', overflowY: 'auto', padding: 20, boxSizing: 'border-box',
          }}
        >
          <h2 id="titolo-invio-pacchetto" style={{ margin: '0 0 4px', fontSize: 18, color: COLORS.text }}>
            {esiti ? 'Esito dell\'invio' : 'Confermi l\'invio?'}
          </h2>
          <p style={{ margin: '0 0 12px', fontSize: 13, color: COLORS.textMuted }}>
            {periodo.etichetta} ({formatDateIT(periodo.dal)} - {formatDateIT(periodo.al)})
          </p>

          {!esiti && (
            <>
              <p style={{ margin: '0 0 8px', fontSize: 13 }}>
                Una sola email a <strong data-testid="destinatario-invio">{destinatario}</strong> con {voci.length}{' '}
                {voci.length === 1 ? 'documento' : 'documenti'}:
              </p>
              <ul style={{ margin: 0, padding: 0, listStyle: 'none' }}>
                {voci.map(v => (
                  <li key={v.voce} data-testid={`conferma-${v.voce}`}
                    style={{ padding: '8px 0', borderTop: `1px solid ${COLORS.border}`, fontSize: 13 }}>
                    <strong>{v.titolo}</strong>
                    <span style={{ color: COLORS.textMuted }}>
                      {' '}· {v.conteggio} {v.voce === 'presenze' ? 'mesi' : 'righe'}{v.totale && v.voce !== 'presenze' ? ` · ${euro(v.totale)}` : ''}
                    </span>
                    {v.stato === 'incompleto' && (
                      <div style={{ color: COLORS.warning, fontSize: 12 }}>Incompleto: {v.motivo}</div>
                    )}
                  </li>
                ))}
              </ul>
            </>
          )}

          {esiti && (
            <ul style={{ margin: 0, padding: 0, listStyle: 'none' }} data-testid="esiti-invio">
              {esiti.map(e => (
                <li key={e.voce} data-testid={`esito-${e.voce}`}
                  style={{ padding: '8px 0', borderTop: `1px solid ${COLORS.border}`, fontSize: 13,
                    display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                  {e.esito === 'allegata'
                    ? <Check size={16} aria-hidden="true" style={{ color: COLORS.success, flexShrink: 0, marginTop: 1 }} />
                    : <Minus size={16} aria-hidden="true" style={{ color: COLORS.warning, flexShrink: 0, marginTop: 1 }} />}
                  <span>
                    <strong>{e.titolo}</strong>: {e.esito === 'allegata' ? 'inviato' : `saltato, ${e.motivo}`}
                    {e.esito === 'allegata' && e.file?.length > 1 && ` (${e.file.length} file)`}
                  </span>
                </li>
              ))}
            </ul>
          )}

          {errore && (
            <p role="alert" style={{ color: COLORS.danger, fontSize: 13, margin: '12px 0 0' }}>{errore}</p>
          )}

          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', flexWrap: 'wrap', marginTop: 16 }}>
            {!esiti && (
              <Button variant="secondary" onClick={onChiudi} disabled={inviando} style={{ minHeight: 44 }}>
                Annulla
              </Button>
            )}
            {!esiti ? (
              <button
                ref={primoRef}
                type="button"
                onClick={onConferma}
                disabled={inviando}
                data-testid="conferma-invio-pacchetto"
                style={{
                  minHeight: 44, padding: '0 18px', borderRadius: BORDER_RADIUS.sm, border: 'none',
                  background: COLORS.primary, color: '#fff', fontWeight: 700, fontSize: 14, fontFamily: FONT.family,
                  cursor: inviando ? 'wait' : 'pointer', opacity: inviando ? 0.7 : 1,
                }}
              >
                {inviando ? 'Invio in corso…' : 'Conferma e invia'}
              </button>
            ) : (
              <button
                ref={primoRef}
                type="button"
                onClick={onChiudi}
                style={{
                  minHeight: 44, padding: '0 18px', borderRadius: BORDER_RADIUS.sm, border: `1px solid ${COLORS.border}`,
                  background: COLORS.card, color: COLORS.text, fontWeight: 700, fontSize: 14, fontFamily: FONT.family,
                  cursor: 'pointer',
                }}
              >
                Chiudi
              </button>
            )}
          </div>
        </div>
      </div>
    </Portal>
  );
}

export default function PacchettoDaInviare({ periodo, carnetIds = [], config, onInviato, avviso }) {
  const [dati, setDati] = useState(null);
  const [caricando, setCaricando] = useState(true);
  const [errore, setErrore] = useState('');
  const [selezione, setSelezione] = useState(() => new Set());
  const [rinvia, setRinvia] = useState(false);
  const [confermaRinvia, setConfermaRinvia] = useState(false);
  const [modale, setModale] = useState(false);
  const [inviando, setInviando] = useState(false);
  const [erroreInvio, setErroreInvio] = useState('');
  const [esiti, setEsiti] = useState(null);
  const [scaricando, setScaricando] = useState('');

  const chiaveCarnet = carnetIds.join(',');
  const parametri = useMemo(
    () => queryPeriodo(periodo, { carnet_ids: chiaveCarnet }),
    [periodo.dal, periodo.al, chiaveCarnet], // eslint-disable-line react-hooks/exhaustive-deps
  );

  const carica = useCallback(async () => {
    setCaricando(true);
    setErrore('');
    try {
      const { data } = await api.get(`/api/commercialista/pacchetto${parametri}`);
      setDati(data);
      setSelezione(new Set(data.voci.filter(v => SELEZIONABILI.includes(v.stato)).map(v => v.voce)));
      setRinvia(false);
      setConfermaRinvia(false);
    } catch (e) {
      setDati(null);
      setErrore(e.response?.data?.detail || e.message || 'Pacchetto non leggibile');
    } finally {
      setCaricando(false);
    }
  }, [parametri]);

  useEffect(() => { carica(); }, [carica]);

  const voci = useMemo(
    () => (dati?.voci || []).map(v => (v.voce === 'carnet_assegni' ? { ...v, carnetScelti: carnetIds.length } : v)),
    [dati, carnetIds.length],
  );
  const scelte = voci.filter(v => selezione.has(v.voce));
  const destinatario = config?.email || dati?.destinatario || '';

  const alterna = voce => setSelezione(prima => {
    const dopo = new Set(prima);
    if (dopo.has(voce)) dopo.delete(voce); else dopo.add(voce);
    return dopo;
  });

  const confermaRinvio = () => {
    setRinvia(true);
    setConfermaRinvia(false);
    setSelezione(prima => new Set(prima).add('presenze'));
  };

  const scarica = async voce => {
    setScaricando(voce.voce);
    try {
      await scaricaOriginale(
        `/api/commercialista/voce/${voce.voce}/scarica${queryPeriodo(periodo, { carnet_ids: chiaveCarnet })}`,
        `${voce.titolo}_${periodo.dal}_${periodo.al}.pdf`,
      );
    } catch (e) {
      avviso?.(`Download non riuscito: ${e.response?.status === 404 ? 'nessun dato nel periodo' : (e.message || 'errore')}`, 'error');
    } finally {
      setScaricando('');
    }
  };

  const chiudiModale = useCallback(() => {
    if (inviando) return;
    setModale(false);
    setEsiti(null);
    setErroreInvio('');
  }, [inviando]);

  const invia = async () => {
    setInviando(true);
    setErroreInvio('');
    try {
      const { data } = await api.post('/api/commercialista/invia-pacchetto', {
        dal: periodo.dal,
        al: periodo.al,
        voci: scelte.map(v => v.voce),
        carnet_ids: carnetIds,
        presenze_rinvia: rinvia,
        email: destinatario || undefined,
      });
      setEsiti(data.esiti || []);
      avviso?.(data.message || 'Pacchetto inviato', 'success');
      onInviato?.();
      carica();
    } catch (e) {
      setErroreInvio(e.response?.data?.detail || e.response?.data?.message || e.message || 'Invio non riuscito');
    } finally {
      setInviando(false);
    }
  };

  const senzaSmtp = config && config.smtp_configured === false;

  return (
    <Card style={{ marginBottom: 25 }}>
      <div data-testid="pacchetto-da-inviare">
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', minWidth: 0 }}>
            <Package size={20} aria-hidden="true" style={{ color: COLORS.primary, flexShrink: 0 }} />
            <div>
              <h2 style={{ margin: 0, fontSize: 17, color: COLORS.text }}>Pacchetto da inviare</h2>
              <div style={{ fontSize: 12, color: COLORS.textMuted }}>
                Una sola email a {destinatario || 'destinatario da impostare'} con i documenti spuntati
              </div>
            </div>
          </div>
          <Button
            variant="primary"
            size="lg"
            disabled={!scelte.length || senzaSmtp || caricando}
            onClick={() => setModale(true)}
            data-testid="invia-selezionati"
            iconLeft={<Mail size={16} aria-hidden="true" />}
            style={{ minHeight: 44 }}
          >
            Invia selezionati ({scelte.length})
          </Button>
        </div>
        {senzaSmtp && (
          <p role="alert" style={{ margin: '10px 0 0', fontSize: 13, color: COLORS.danger }}>
            Email non configurata: l'invio non è disponibile, i documenti si possono solo scaricare.
          </p>
        )}

        {errore && <p role="alert" style={{ color: COLORS.danger, fontSize: 13 }}>{errore}</p>}
        {caricando && !dati && <p style={{ color: COLORS.textMuted, fontSize: 13 }}>Carico i documenti del periodo…</p>}

        {dati && (
          <div
            style={{
              display: 'grid', gap: 12, marginTop: 14,
              gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 260px), 1fr))',
              opacity: caricando ? 0.6 : 1,
            }}
          >
            {voci.map(v => (
              <SchedaVoce
                key={v.voce}
                voce={v}
                urlDettaglio={`/api/commercialista/voce/${v.voce}${parametri}`}
                selezionata={selezione.has(v.voce)}
                onSeleziona={() => alterna(v.voce)}
                onScarica={() => scarica(v)}
                scaricando={scaricando === v.voce}
                onRinvia={() => setConfermaRinvia(true)}
                confermaRinvia={v.voce === 'presenze' && confermaRinvia}
                onConfermaRinvio={confermaRinvio}
                onAnnullaRinvio={() => setConfermaRinvia(false)}
              />
            ))}
          </div>
        )}
      </div>

      {modale && (
        <ModaleInvio
          periodo={periodo}
          destinatario={destinatario}
          voci={scelte}
          esiti={esiti}
          inviando={inviando}
          errore={erroreInvio}
          onConferma={invia}
          onChiudi={chiudiModale}
        />
      )}
    </Card>
  );
}
