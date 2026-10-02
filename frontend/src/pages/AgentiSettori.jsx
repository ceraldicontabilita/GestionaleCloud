import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertTriangle, Car, Check, CheckCheck, FileText, Landmark, Receipt, Users, Wallet, X,
} from 'lucide-react';
import api from '../api';
import ApriOriginale from '../components/ApriOriginale';
import { Button } from '../components/ds';
import { COLORS, FONT, formatIstanteIT } from '../lib/utils';
import { NON_DISPONIBILE, euroCentesimiOppure } from '../lib/vista';

/**
 * Scheda «Settori» del cruscotto Agenti (titolare, 02/10/2026): una card per
 * settore con l'ultimo giro, le code ferme (numero + link alla pagina) e le
 * proposte dell'agente AI sui documenti che i lettori non riconoscono.
 * Confermare passa dal motore deterministico esistente; qui si tocca e basta.
 * Un numero che manca e' «Dato non disponibile», mai zero.
 */

const ICONE = { verbali: Car, cedolini: Users, bonifici: Landmark, fatture: FileText, corrispettivi: Receipt, f24: Wallet };

export const MOTIVI_RIFIUTO = [
  { key: 'tipo_sbagliato', label: 'Tipo sbagliato' },
  { key: 'dati_sbagliati', label: 'Dati sbagliati' },
  { key: 'non_contabile', label: 'Non contabile' },
  { key: 'doppione', label: 'Doppione' },
  { key: 'altro', label: 'Altro (scrivi tu)' },
];

const ETICHETTE_CONTEGGI = {
  letti: 'letti', associati: 'associati', errori: 'errori', da_agganciare: 'da agganciare',
  stipendi: 'stipendi', assegni: 'assegni', gruppi: 'gruppi', rimasti: 'rimasti',
};

const CONFIDENZA = {
  alta: { label: 'Sicura', bg: COLORS.successLight, fg: COLORS.success },
  media: { label: 'Da guardare', bg: COLORS.warningLight, fg: COLORS.warning },
  bassa: { label: 'Incerta', bg: COLORS.dangerLight, fg: COLORS.danger },
};

export function numeroOppure(v) {
  return v === null || v === undefined ? NON_DISPONIBILE : String(v);
}

function Pastiglia({ children, bg, fg }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4, padding: '2px 8px', borderRadius: 999,
      fontSize: 11.5, fontWeight: 700, background: bg, color: fg, letterSpacing: '0.01em',
    }}>
      {children}
    </span>
  );
}

function CollegamentoCoda({ coda }) {
  const corpo = (
    <>
      <span style={{ fontWeight: 700, fontSize: 15, color: coda.conteggio ? COLORS.text : COLORS.textMuted }}>
        {numeroOppure(coda.conteggio)}
      </span>
      <span style={{ fontSize: 13, color: COLORS.text }}>{coda.nome}</span>
      <span style={{ fontSize: 11.5, color: COLORS.textMuted }}>{coda.motivo}</span>
    </>
  );
  const stile = {
    display: 'flex', flexDirection: 'column', gap: 2, minHeight: 44, padding: '8px 10px',
    borderRadius: 8, border: `1px solid ${COLORS.border}`, background: COLORS.bgAlt, textDecoration: 'none',
  };
  if (!coda.rotta_pagina) return <div style={stile}>{corpo}</div>;
  if (coda.rotta_pagina.startsWith('/hr/')) {
    return <a href={coda.rotta_pagina} target="_blank" rel="noreferrer" style={stile}>{corpo}</a>;
  }
  return <Link to={coda.rotta_pagina} style={stile}>{corpo}</Link>;
}

function Giro({ giro }) {
  const conteggi = Object.entries(giro.conteggi || {});
  return (
    <div style={{ fontSize: 12.5, color: COLORS.textMuted, display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'baseline' }}>
      <span style={{ fontWeight: 600, color: COLORS.text }}>{giro.etichetta}:</span>
      <span>{giro.mai_eseguito || !giro.at ? 'mai eseguito' : formatIstanteIT(giro.at)}</span>
      {conteggi.map(([k, v]) => (
        <span key={k}>· {ETICHETTE_CONTEGGI[k] || k} {numeroOppure(v)}</span>
      ))}
      {giro.errore && <span style={{ color: COLORS.danger }}>· errore: {giro.errore}</span>}
    </div>
  );
}

function CampiProposta({ campi }) {
  const voci = Object.entries(campi || {}).filter(([, v]) => v !== null && v !== undefined && v !== '');
  if (voci.length === 0) return <span style={{ fontSize: 12, color: COLORS.textMuted }}>Nessun dato letto</span>;
  return (
    <dl style={{ margin: 0, display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '2px 10px', fontSize: 12.5 }}>
      {voci.map(([k, v]) => (
        <React.Fragment key={k}>
          <dt style={{ color: COLORS.textMuted }}>{k.replace(/_/g, ' ')}</dt>
          <dd style={{ margin: 0, color: COLORS.text, fontFamily: k === 'importo_cents' ? FONT.mono : undefined }}>
            {k === 'importo_cents' ? euroCentesimiOppure(v) : Array.isArray(v) ? v.join(', ') : String(v)}
          </dd>
        </React.Fragment>
      ))}
    </dl>
  );
}

export function PropostaCard({ proposta, onConferma, onRifiuta, occupata }) {
  const [rifiuto, setRifiuto] = useState(false);
  const [motivo, setMotivo] = useState(null);
  const [nota, setNota] = useState('');
  const p = proposta.proposta || {};
  const doc = proposta.documento || {};
  const conf = CONFIDENZA[proposta.confidenza] || CONFIDENZA.bassa;
  const applicabile = p.tipo_documento && p.tipo_documento !== 'non_riconosciuto';
  const originale = doc.drive_id
    ? { driveId: doc.drive_id }
    : doc.inbox_id ? { tipo: 'documento', id: doc.inbox_id } : {};
  return (
    <div data-testid={`proposta-${proposta.id}`} style={{
      border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 12, background: COLORS.card,
      display: 'flex', flexDirection: 'column', gap: 8,
    }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <Pastiglia bg={conf.bg} fg={conf.fg}>{conf.label}</Pastiglia>
        <span style={{ fontWeight: 700, fontSize: 14, color: COLORS.text }}>
          {applicabile ? p.tipo_documento.replace(/_/g, ' ') : 'non riconosciuto'}
        </span>
        <span style={{ fontSize: 12, color: COLORS.textMuted, wordBreak: 'break-all' }}>{doc.nome || 'documento'}</span>
      </div>
      <CampiProposta campi={p.campi} />
      {p.motivo && <div style={{ fontSize: 12, color: COLORS.textMuted }}>{p.motivo}</div>}
      {Array.isArray(p.prove) && p.prove.length > 0 && (
        <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, color: COLORS.textMuted }}>
          {p.prove.slice(0, 3).map((prova, i) => <li key={i}>«{prova}»</li>)}
        </ul>
      )}
      {!rifiuto ? (
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <ApriOriginale {...originale} titolo={doc.nome || 'Documento'} testId={`vedi-${proposta.id}`}>
            <FileText size={14} aria-hidden="true" /> Vedi
          </ApriOriginale>
          <Button
            type="button" size="sm" variant="primary" disabled={occupata || !applicabile}
            style={{ minHeight: 44 }} data-testid={`conferma-${proposta.id}`}
            onClick={() => onConferma(proposta)}
          >
            <Check size={14} aria-hidden="true" /> Conferma
          </Button>
          <Button
            type="button" size="sm" variant="secondary" disabled={occupata} style={{ minHeight: 44 }}
            data-testid={`rifiuta-${proposta.id}`} onClick={() => setRifiuto(true)}
          >
            <X size={14} aria-hidden="true" /> Rifiuta
          </Button>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {MOTIVI_RIFIUTO.map(m => (
              <button
                key={m.key} type="button" data-testid={`motivo-${proposta.id}-${m.key}`}
                onClick={() => setMotivo(m.key)}
                style={{
                  minHeight: 44, padding: '8px 12px', borderRadius: 999, cursor: 'pointer', fontSize: 12.5,
                  fontWeight: motivo === m.key ? 700 : 500, fontFamily: FONT.family,
                  border: `1px solid ${motivo === m.key ? COLORS.primary : COLORS.border}`,
                  background: motivo === m.key ? COLORS.primarySoft : COLORS.card,
                  color: motivo === m.key ? COLORS.primary : COLORS.text,
                }}
              >
                {m.label}
              </button>
            ))}
          </div>
          {motivo === 'altro' && (
            <label style={{ fontSize: 12.5, color: COLORS.textMuted, display: 'flex', flexDirection: 'column', gap: 4 }}>
              Scrivi il motivo
              <input
                value={nota} onChange={e => setNota(e.target.value)} maxLength={300}
                style={{ minHeight: 44, padding: '8px 10px', border: `1px solid ${COLORS.border}`, borderRadius: 8, fontFamily: FONT.family }}
              />
            </label>
          )}
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <Button
              type="button" size="sm" variant="danger" disabled={occupata || !motivo || (motivo === 'altro' && !nota.trim())}
              style={{ minHeight: 44 }} data-testid={`conferma-rifiuto-${proposta.id}`}
              onClick={() => onRifiuta(proposta, motivo, nota)}
            >
              Rifiuta con questo motivo
            </Button>
            <Button type="button" size="sm" variant="secondary" style={{ minHeight: 44 }} onClick={() => setRifiuto(false)}>
              Annulla
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function SettoreCard({ settore, proposte, onConferma, onRifiuta, onConfermaSicure, occupata }) {
  const Icona = ICONE[settore.id] || FileText;
  const sicure = proposte.filter(p => p.confidenza === 'alta' && p.proposta?.tipo_documento !== 'non_riconosciuto').length;
  const ferme = settore.code_ferme.reduce((n, c) => n + (c.conteggio || 0), 0);
  return (
    <section
      data-testid={`settore-${settore.id}`}
      style={{
        background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 12, padding: 16,
        display: 'flex', flexDirection: 'column', gap: 12, minWidth: 0,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <span style={{
          width: 40, height: 40, borderRadius: 10, background: COLORS.primarySoft, color: COLORS.primary,
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
        }}>
          <Icona size={20} aria-hidden="true" />
        </span>
        <h2 style={{ margin: 0, fontSize: 16, fontWeight: 800, letterSpacing: '-0.02em', color: COLORS.text, flex: 1 }}>
          {settore.nome}
        </h2>
        {ferme > 0 && <Pastiglia bg={COLORS.warningLight} fg={COLORS.warning}><AlertTriangle size={12} aria-hidden="true" /> {ferme} fermi</Pastiglia>}
        {proposte.length > 0 && <Pastiglia bg={COLORS.primarySoft} fg={COLORS.primary}>{proposte.length} proposte AI</Pastiglia>}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {settore.giri.length === 0
          ? <span style={{ fontSize: 12.5, color: COLORS.textMuted }}>Ultimo giro: {NON_DISPONIBILE}</span>
          : settore.giri.map(g => <Giro key={g.chiave} giro={g} />)}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 8 }}>
        {settore.code_ferme.map(c => <CollegamentoCoda key={c.nome} coda={c} />)}
      </div>

      {proposte.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 13, fontWeight: 700, color: COLORS.text }}>Proposte AI in attesa</span>
            {sicure > 0 && (
              <Button
                type="button" size="sm" variant="secondary" disabled={occupata} style={{ minHeight: 44 }}
                data-testid={`conferma-sicure-${settore.id}`} onClick={() => onConfermaSicure(settore.id)}
              >
                <CheckCheck size={14} aria-hidden="true" /> Conferma tutte le sicure ({sicure})
              </Button>
            )}
          </div>
          {proposte.map(p => (
            <PropostaCard key={p.id} proposta={p} onConferma={onConferma} onRifiuta={onRifiuta} occupata={occupata} />
          ))}
        </div>
      )}
    </section>
  );
}

function RiquadroAgenti({ agenti }) {
  if (!agenti) return null;
  const stato = !agenti.attivo
    ? { label: 'Spento (AGENTI_AI=false)', bg: COLORS.dangerLight, fg: COLORS.danger }
    : !agenti.chiave_presente
      ? { label: 'Senza chiave: nessuna lettura', bg: COLORS.warningLight, fg: COLORS.warning }
      : { label: 'Acceso', bg: COLORS.successLight, fg: COLORS.success };
  return (
    <div data-testid="riquadro-agenti-ai" style={{
      border: `1px solid ${COLORS.border}`, borderRadius: 12, padding: '12px 16px', background: COLORS.bgAlt,
      display: 'flex', gap: 14, flexWrap: 'wrap', alignItems: 'center', fontSize: 12.5, color: COLORS.textMuted,
    }}>
      <Pastiglia bg={stato.bg} fg={stato.fg}>Agente AI: {stato.label}</Pastiglia>
      <span>Ultimo giro: {agenti.ultimo_giro ? formatIstanteIT(agenti.ultimo_giro) : 'mai eseguito'}</span>
      <span>Chiamate oggi: {numeroOppure(agenti.chiamate_oggi)} su {numeroOppure(agenti.tetto)}</span>
      <span>Non riconosciuti in ERRORI: {numeroOppure(agenti.non_riconosciuti_errori)}</span>
      <span>Inbox senza categoria: {numeroOppure(agenti.inbox_non_classificata)}</span>
      <span>Arretrato: {numeroOppure(agenti.arretrato)}</span>
      {agenti.ultimo_esito?.motivo && <span style={{ color: COLORS.warning }}>{agenti.ultimo_esito.motivo}</span>}
    </div>
  );
}

export default function AgentiSettori({ onMessaggio = () => {} }) {
  const [dati, setDati] = useState(null);
  const [proposte, setProposte] = useState([]);
  const [errore, setErrore] = useState('');
  const [occupata, setOccupata] = useState(false);

  const carica = useCallback(async () => {
    try {
      const [settoriRes, proposteRes] = await Promise.all([
        api.get('/api/agenti/settori'),
        api.get('/api/agenti/proposte?stato=proposta&limit=500'),
      ]);
      setDati(settoriRes.data || null);
      setProposte(proposteRes.data?.proposte || []);
      setErrore('');
    } catch {
      setErrore('Cruscotto dei settori non caricato');
    }
  }, []);

  useEffect(() => { carica(); }, [carica]);

  const esegui = async (azione, testoOk) => {
    setOccupata(true);
    try {
      const r = await azione();
      onMessaggio(typeof testoOk === 'function' ? testoOk(r) : testoOk);
      await carica();
    } catch (e) {
      const d = e.response?.data?.detail;
      onMessaggio(`Errore: ${typeof d === 'string' ? d : d?.message || 'operazione non riuscita'}`);
    } finally {
      setOccupata(false);
    }
  };

  const conferma = p => esegui(
    () => api.post(`/api/agenti/proposte/${encodeURIComponent(p.id)}/conferma`),
    r => (r?.data?.gia_decisa ? 'Proposta già decisa: non si riapplica.' : 'Proposta applicata dal motore del tipo scelto.'),
  );
  const rifiuta = (p, motivo, nota) => esegui(
    () => api.post(`/api/agenti/proposte/${encodeURIComponent(p.id)}/rifiuta`, { motivo, nota }),
    'Proposta rifiutata.',
  );
  const confermaSicure = settore => esegui(
    () => api.post(`/api/agenti/proposte/conferma-sicure?settore=${encodeURIComponent(settore)}`),
    r => `Sicure: ${r?.data?.confermate ?? 0} applicate, ${r?.data?.non_applicate ?? 0} non applicate.`,
  );

  if (errore) return <div role="alert" style={{ color: COLORS.danger, fontSize: 13 }}>{errore}</div>;
  if (!dati) return <div style={{ fontSize: 13, color: COLORS.textMuted }}>Caricamento…</div>;

  const perSettore = id => proposte.filter(p => p.settore === id);
  const altre = perSettore('altro');
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <RiquadroAgenti agenti={dati.agenti_ai} />
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 340px), 1fr))', gap: 12 }}>
        {(dati.settori || []).map(s => (
          <SettoreCard
            key={s.id} settore={s} proposte={perSettore(s.id)} occupata={occupata}
            onConferma={conferma} onRifiuta={rifiuta} onConfermaSicure={confermaSicure}
          />
        ))}
        {altre.length > 0 && (
          <SettoreCard
            settore={{ id: 'altro', nome: 'Altri documenti', giri: [], code_ferme: [] }}
            proposte={altre} occupata={occupata}
            onConferma={conferma} onRifiuta={rifiuta} onConfermaSicure={confermaSicure}
          />
        )}
      </div>
    </div>
  );
}
