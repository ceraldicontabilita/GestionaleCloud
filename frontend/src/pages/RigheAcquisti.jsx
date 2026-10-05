import React, { useEffect, useMemo, useState } from 'react';
import { Ban, Check, ExternalLink, Filter, Link2, Pencil, Search, Settings, TriangleAlert, X } from 'lucide-react';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { COLORS, BORDER_RADIUS, useIsMobile } from '../lib/utils';
import {
  Badge,
  Button,
  Card,
  Input,
  PageLoader,
  StatCard,
  Table,
  TableWrap,
  Td,
  Th,
} from '../components/ds';

const PER_PAGINA = 200;
const NATURE_RIGA = [
  'prodotto', 'ingrediente', 'servizio', 'trasporto', 'sconto', 'arrotondamento',
  'utensile', 'attrezzatura', 'cespite', 'pulizia', 'cancelleria', 'canone',
  'consulenza', 'spesa', 'reso', 'altro',
];

const euro = value => {
  if (value === null || value === undefined || value === '') return '—';
  return new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR' }).format(Number(value));
};

const dataIT = value => {
  if (!value) return '—';
  const [y, m, d] = String(value).slice(0, 10).split('-');
  return y && m && d ? `${d}/${m}/${y}` : value;
};

const badgeAI = stato => {
  if (stato === 'CONFERMATA') return { variant: 'success', label: 'Confermata' };
  if (stato === 'PROPOSTA') return { variant: 'warning', label: 'Proposta' };
  return { variant: 'neutral', label: 'Da verificare' };
};

function SelectFiltro({ label, value, onChange, children }) {
  return (
    <label style={{ display: 'grid', gap: 5, minWidth: 150, fontSize: 12, color: COLORS.textMuted }}>
      {label}
      <select
        aria-label={label}
        value={value}
        onChange={event => onChange(event.target.value)}
        style={{ minHeight: 42, border: `1px solid ${COLORS.border}`, borderRadius: 9, padding: '0 10px', background: COLORS.card, color: COLORS.text }}
      >
        {children}
      </select>
    </label>
  );
}


const ALTRO = '__altro__';

const stileSelect = {
  minHeight: 42, border: `1px solid ${COLORS.border}`, borderRadius: 9, padding: '0 10px',
  background: COLORS.card, color: COLORS.text,
};

/**
 * Classificazione della riga, modificabile da qui: propone dal nome (articolo,
 * categoria, natura), il titolare corregge ogni campo e salva. Il salvataggio
 * popola Lotti e aggiorna tutte le righe dello stesso fornitore con lo stesso nome.
 */
function ClassificazioneRiga({ riga, ai, onAssegna, busy }) {
  const [prodotti, setProdotti] = useState([]);
  const [categorie, setCategorie] = useState([]);
  const [centri, setCentri] = useState([]);
  const [ricerca, setRicerca] = useState('');
  const [proposta, setProposta] = useState(null);
  const [toccato, setToccato] = useState(false);
  const [errore, setErrore] = useState('');
  const [f, setF] = useState({
    scelto: '', nuovoNome: '', categoria: '', natura: '', conto: '', centro_costo: '',
    destinazione: '', nonCespite: false, alimentare: true,
  });
  const imposta = (campi, daUtente = true) => {
    if (daUtente) setToccato(true);
    setF(corrente => ({ ...corrente, ...campi }));
  };

  useEffect(() => {
    let active = true;
    const timer = setTimeout(() => {
      api.get('/api/righe-acquisti/prodotti-lotti', { params: { q: ricerca } })
        .then(({ data }) => {
          if (!active) return;
          setProdotti(data.prodotti || []);
          setCategorie(data.categorie || []);
          setCentri(data.centri_costo || []);
        })
        .catch(() => { if (active) setErrore('Elenco articoli di Lotti non disponibile.'); });
    }, 200);
    return () => { active = false; clearTimeout(timer); };
  }, [ricerca]);

  useEffect(() => {
    let active = true;
    api.get(`/api/righe-acquisti/${encodeURIComponent(riga.id)}/proposta-lotti`)
      .then(({ data }) => { if (active) setProposta(data); })
      .catch(() => { if (active) setProposta(null); });
    return () => { active = false; };
  }, [riga.id]);

  // La proposta (o la classificazione già confermata) riempie il form finché il titolare non lo tocca.
  useEffect(() => {
    if (!proposta || toccato) return;
    const confermata = ai.stato === 'CONFERMATA';
    const base = confermata ? ai : proposta;
    setF({
      scelto: proposta.nome_canc || '', nuovoNome: '', categoria: base.categoria || '',
      natura: base.natura || '', conto: base.conto || '', centro_costo: base.centro_costo || '',
      destinazione: (confermata ? ai.destinazione_operativa : (proposta.alimentare ? 'magazzino_lotti' : '')) || '',
      nonCespite: confermata ? ai.non_cespite === true : proposta.non_cespite === true,
      alimentare: proposta.alimentare !== false,
    });
  }, [proposta, toccato, ai]);

  const nome = f.scelto === ALTRO ? f.nuovoNome.trim() : f.scelto;
  const elencoArticoli = prodotti.some(p => p.nome_canc === f.scelto) || !f.scelto || f.scelto === ALTRO
    ? prodotti : [{ nome_canc: f.scelto }, ...prodotti];
  const pronto = !f.alimentare || (!!nome && !!f.categoria);
  const incoerente = f.nonCespite && f.natura === 'cespite';
  const etichetta = ({ lotti_confermato: 'Lotti conosce già questo articolo', lotti_proposta: 'Proposta di Lotti', dal_nome: 'Dal nome della riga' })[proposta?.fonte];

  return (
    <div style={{ display: 'grid', gap: 10, marginTop: 10 }}>
      {proposta?.fonte && !toccato && ai.stato !== 'CONFERMATA' && (
        <div role="status" style={{ fontSize: 12, padding: '8px 10px', borderRadius: 9, background: COLORS.bgSecondary || COLORS.card, border: `1px solid ${COLORS.border}` }}>
          <strong>Proposta · {etichetta}.</strong> {proposta.spiegazione} Correggi i campi e salva.
        </div>
      )}
      {proposta && !proposta.fonte && ai.stato !== 'CONFERMATA' && (
        <div style={{ fontSize: 12, color: COLORS.textMuted }}>{proposta.spiegazione}</div>
      )}
      <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, minHeight: 44 }}>
        <input type="checkbox" aria-label="Non è merce alimentare" checked={!f.alimentare} onChange={event => imposta({ alimentare: !event.target.checked })} />
        Non è merce alimentare (non va a magazzino in Lotti)
      </label>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 8 }}>
        {f.alimentare && (
          <>
            <label style={{ display: 'grid', gap: 4, fontSize: 12, color: COLORS.textMuted }}>
              Cerca articolo
              <Input aria-label="Cerca articolo di Lotti" value={ricerca} onChange={event => setRicerca(event.target.value)} />
            </label>
            <label style={{ display: 'grid', gap: 4, fontSize: 12, color: COLORS.textMuted }}>
              Articolo di Lotti
              <select aria-label="Articolo di Lotti" value={f.scelto} onChange={event => imposta({ scelto: event.target.value })} style={stileSelect}>
                <option value="">Da verificare</option>
                {elencoArticoli.map(p => <option key={p.nome_canc} value={p.nome_canc}>{p.nome_canc}</option>)}
                <option value={ALTRO}>Altro (scrivi tu)</option>
              </select>
            </label>
            {f.scelto === ALTRO && (
              <label style={{ display: 'grid', gap: 4, fontSize: 12, color: COLORS.textMuted }}>
                Nome del nuovo articolo
                <Input aria-label="Nome del nuovo articolo" value={f.nuovoNome} onChange={event => imposta({ nuovoNome: event.target.value })} />
              </label>
            )}
            <label style={{ display: 'grid', gap: 4, fontSize: 12, color: COLORS.textMuted }}>
              Categoria
              <select aria-label="Categoria Lotti" value={f.categoria} onChange={event => imposta({ categoria: event.target.value })} style={stileSelect}>
                <option value="">Da verificare</option>
                {categorie.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </label>
          </>
        )}
        <label style={{ display: 'grid', gap: 4, fontSize: 12, color: COLORS.textMuted }}>
          Natura
          <select aria-label="Natura" value={f.natura} onChange={event => imposta({ natura: event.target.value })} style={stileSelect}>
            <option value="">Da verificare</option>
            {NATURE_RIGA.map(n => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        <label style={{ display: 'grid', gap: 4, fontSize: 12, color: COLORS.textMuted }}>
          Conto (es. 33.03.01)
          <Input aria-label="Conto" value={f.conto} placeholder="Da verificare" onChange={event => imposta({ conto: event.target.value })} />
        </label>
        <label style={{ display: 'grid', gap: 4, fontSize: 12, color: COLORS.textMuted }}>
          Centro di costo
          <select aria-label="Centro di costo" value={f.centro_costo} onChange={event => imposta({ centro_costo: event.target.value })} style={stileSelect}>
            <option value="">Da verificare</option>
            {centri.map(c => <option key={c.codice} value={c.codice}>{c.codice}{c.nome ? ` · ${c.nome}` : ''}</option>)}
          </select>
        </label>
        <label style={{ display: 'grid', gap: 4, fontSize: 12, color: COLORS.textMuted }}>
          Destinazione operativa
          <select aria-label="Destinazione operativa" value={f.destinazione} onChange={event => imposta({ destinazione: event.target.value })} style={stileSelect}>
            <option value="">Da verificare</option>
            <option value="magazzino_lotti">Magazzino Lotti</option>
          </select>
        </label>
      </div>
      <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, minHeight: 44 }}>
        <input type="checkbox" aria-label="Non è un cespite" checked={f.nonCespite} onChange={event => imposta({ nonCespite: event.target.checked })} />
        Non è un cespite (shopper, buste, materiale di consumo: non entra mai nei cespiti)
      </label>
      {incoerente && <div role="alert" style={{ fontSize: 12, color: COLORS.danger }}>«Non è un cespite» e natura «cespite» non possono stare insieme.</div>}
      {errore && <div role="alert" style={{ fontSize: 12, color: COLORS.danger }}>{errore}</div>}
      <div>
        <Button
          type="button"
          disabled={busy || !pronto || incoerente}
          onClick={() => onAssegna({
            nome_canc: nome, categoria: f.categoria, alimentare: f.alimentare, natura: f.natura,
            conto: f.conto, centro_costo: f.centro_costo, destinazione_operativa: f.destinazione,
            non_cespite: f.nonCespite,
          })}
          style={{ minHeight: 44 }}
        >
          <Link2 size={16} /> Salva e aggiorna le righe uguali
        </Button>
        <div style={{ marginTop: 6, fontSize: 12, color: COLORS.textMuted }}>
          Vale anche per le altre righe dello stesso fornitore con lo stesso nome (quelle già decise da te non si toccano) e popola Lotti.
        </div>
      </div>
    </div>
  );
}

/** Conto e centro di costo per categoria di Lotti: partono vuoti, li decide il titolare. */
function RegoleCategoria() {
  const [aperto, setAperto] = useState(false);
  const [dati, setDati] = useState(null);
  const [bozze, setBozze] = useState({});
  const [messaggio, setMessaggio] = useState('');

  useEffect(() => {
    if (!aperto || dati) return;
    api.get('/api/righe-acquisti/regole-categoria')
      .then(({ data }) => setDati(data))
      .catch(() => setMessaggio('Regole non disponibili.'));
  }, [aperto, dati]);

  const valore = (r, campo) => (bozze[r.categoria]?.[campo] ?? r[campo] ?? '');
  const cambia = (r, campo, v) => setBozze(c => ({ ...c, [r.categoria]: { ...(c[r.categoria] || {}), [campo]: v } }));
  const salva = async r => {
    setMessaggio('');
    try {
      await api.put(`/api/righe-acquisti/regole-categoria/${encodeURIComponent(r.categoria)}`, {
        conto: valore(r, 'conto'), centro_costo: valore(r, 'centro_costo'),
      });
      setDati(null);
      setBozze(c => { const n = { ...c }; delete n[r.categoria]; return n; });
      setMessaggio(`Regola «${r.categoria}» salvata.`);
    } catch (error) {
      setMessaggio(error?.response?.data?.detail || 'Regola non salvata.');
    }
  };

  return (
    <Card style={{ padding: 12, fontSize: 13 }}>
      <Button type="button" variant="secondary" onClick={() => setAperto(v => !v)} style={{ minHeight: 44 }}>
        <Settings size={16} /> Conto e centro di costo per categoria
      </Button>
      {aperto && (
        <div style={{ display: 'grid', gap: 10, marginTop: 12 }}>
          <div style={{ color: COLORS.textMuted, fontSize: 12 }}>
            Quando associ un articolo di Lotti a una riga, conto e centro di costo si compilano da qui.
            Una categoria senza regola lascia i due campi «Da verificare».
          </div>
          {(dati?.regole || []).map(r => (
            <div key={r.categoria} style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 8, alignItems: 'end' }}>
              <strong style={{ alignSelf: 'center' }}>{r.categoria}</strong>
              <label style={{ display: 'grid', gap: 4, fontSize: 12, color: COLORS.textMuted }}>
                Conto (es. 33.03.01)
                <Input aria-label={`Conto ${r.categoria}`} value={valore(r, 'conto')} onChange={event => cambia(r, 'conto', event.target.value)} />
              </label>
              <label style={{ display: 'grid', gap: 4, fontSize: 12, color: COLORS.textMuted }}>
                Centro di costo
                <select aria-label={`Centro di costo ${r.categoria}`} value={valore(r, 'centro_costo')} onChange={event => cambia(r, 'centro_costo', event.target.value)} style={stileSelect}>
                  <option value="">Nessuno</option>
                  {(dati?.centri_costo || []).map(c => <option key={c.codice} value={c.codice}>{c.codice}{c.nome ? ` · ${c.nome}` : ''}</option>)}
                </select>
              </label>
              <Button type="button" variant="secondary" onClick={() => salva(r)} style={{ minHeight: 44 }}>Salva</Button>
            </div>
          ))}
        </div>
      )}
      {messaggio && <div role="status" style={{ marginTop: 8, fontSize: 12 }}>{messaggio}</div>}
    </Card>
  );
}

function DettaglioRiga({ riga, onClose, onDecision, onAssegna, busy }) {
  const ai = riga.classificazione || {};
  const codici = (riga.codici_articolo || []).map(item => [item.tipo, item.valore].filter(Boolean).join(': '));
  const [motivazione, setMotivazione] = useState('');
  const [regolaFiscale, setRegolaFiscale] = useState('');
  const [correggi, setCorreggi] = useState(false);
  const [campi, setCampi] = useState({
    natura: ai.natura || '', categoria: ai.categoria || '', conto: ai.conto || '',
    centro_costo: ai.centro_costo || '', destinazione_operativa: ai.destinazione_operativa || '',
    confidenza: ai.confidenza ?? 0, spiegazione: ai.spiegazione || '', regola: ai.regola || '',
  });
  const aggiornaCampo = (key, value) => setCampi(current => ({ ...current, [key]: value }));
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Dettaglio riga acquisto"
      onClick={onClose}
      style={{ position: 'fixed', inset: 0, zIndex: 1200, background: 'rgba(18,18,17,.55)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 14 }}
    >
      <div onClick={event => event.stopPropagation()} style={{ width: '100%', maxWidth: 720, maxHeight: '90vh', overflowY: 'auto', background: COLORS.card, borderRadius: BORDER_RADIUS.lg, padding: 18 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'start' }}>
          <div>
            <div style={{ fontSize: 12, color: COLORS.textMuted }}>Riga {riga.numero_linea} · fattura {riga.numero_fattura}</div>
            <h2 style={{ margin: '4px 0 0', fontSize: 19 }}>{riga.descrizione_originale || 'Descrizione assente'}</h2>
          </div>
          <Button type="button" variant="ghost" aria-label="Chiudi dettaglio" onClick={onClose}><X size={18} /></Button>
        </div>

        <div style={{ display: 'grid', gap: 12, marginTop: 16 }}>
          <Card style={{ padding: 14 }}>
            <strong>Provenienza documentale</strong>
            <div style={{ marginTop: 8, fontSize: 13, lineHeight: 1.6, overflowWrap: 'anywhere' }}>
              <div>ID fattura: {riga.fattura_id || 'non disponibile'}</div>
              <div>ID documento: {riga.documento_id || 'non disponibile'}</div>
              <div>SHA-256: {riga.hash_originale || 'non disponibile'}</div>
              <div>Codice articolo: {codici.join(', ') || 'non dichiarato'}</div>
              <div>Ordine: {(riga.ordini || []).join(', ') || 'non dichiarato'}</div>
              <div>Contratto: {(riga.contratti || []).join(', ') || 'non dichiarato'}</div>
              <div>DDT: {(riga.ddt || []).join(', ') || 'non dichiarato'}</div>
            </div>
            {riga.url_originale && (
              <Button
                type="button"
                variant="secondary"
                onClick={() => window.open(riga.url_originale, '_blank', 'noopener,noreferrer')}
                style={{ marginTop: 10, minHeight: 42 }}
              >
                <ExternalLink size={16} /> Apri fattura/originale
              </Button>
            )}
          </Card>

          <Card style={{ padding: 14 }}>
            <strong>Classificazione della singola riga</strong>
            <div style={{ marginTop: 8 }}><Badge variant={badgeAI(ai.stato).variant}>{badgeAI(ai.stato).label}</Badge></div>
            {ai.stato === 'PROPOSTA' && (
              <div style={{ marginTop: 8, fontSize: 13, lineHeight: 1.6 }}>
              <div>Natura: {ai.natura || 'DA_VERIFICARE'}</div>
              <div>Categoria: {ai.categoria || 'DA_VERIFICARE'}</div>
              <div>Conto: {ai.conto || 'DA_VERIFICARE'}</div>
              <div>Centro di costo: {ai.centro_costo || 'DA_VERIFICARE'}</div>
              <div>Destinazione operativa: {ai.destinazione_operativa || 'DA_VERIFICARE'}</div>
              <div>Confidenza: {ai.confidenza ?? 'non disponibile'}</div>
              <div>Spiegazione: {ai.spiegazione || 'Nessuna proposta salvata per questa riga.'}</div>
              <div>Regola/versione: {[ai.regola, ai.versione].filter(Boolean).join(' · ') || 'non disponibile'}</div>
            </div>
            )}
            <ClassificazioneRiga riga={riga} ai={ai} onAssegna={onAssegna} busy={busy} />
            {ai.stato === 'PROPOSTA' && (
              <div style={{ display: 'grid', gap: 10, marginTop: 14 }}>
                {correggi && (
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 8 }}>
                    {[
                      ['natura', 'Natura'], ['categoria', 'Categoria'], ['conto', 'Conto'],
                      ['centro_costo', 'Centro di costo'], ['destinazione_operativa', 'Destinazione operativa'],
                    ].map(([key, label]) => (
                      <label key={key} style={{ display: 'grid', gap: 4, fontSize: 12, color: COLORS.textMuted }}>
                        {label}
                        {key === 'natura' ? (
                          <select
                            aria-label={label}
                            value={campi[key]}
                            onChange={event => aggiornaCampo(key, event.target.value)}
                            style={{ minHeight: 42, border: `1px solid ${COLORS.border}`, borderRadius: 9, padding: '0 10px', background: COLORS.card, color: COLORS.text }}
                          >
                            {NATURE_RIGA.map(natura => <option key={natura} value={natura}>{natura}</option>)}
                          </select>
                        ) : (
                          <Input aria-label={label} value={campi[key]} onChange={event => aggiornaCampo(key, event.target.value)} />
                        )}
                      </label>
                    ))}
                  </div>
                )}
                <label style={{ display: 'grid', gap: 4, fontSize: 12, color: COLORS.textMuted }}>
                  Motivazione obbligatoria
                  <Input aria-label="Motivazione decisione" value={motivazione} onChange={event => setMotivazione(event.target.value)} />
                </label>
                {(ai.natura === 'cespite' || (correggi && campi.natura === 'cespite')) && (
                  <label style={{ display: 'grid', gap: 4, fontSize: 12, color: COLORS.textMuted }}>
                    Regola fiscale esplicita obbligatoria per il cespite
                    <Input aria-label="Regola fiscale cespite" value={regolaFiscale} onChange={event => setRegolaFiscale(event.target.value)} />
                  </label>
                )}
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                  <Button type="button" disabled={busy || !motivazione.trim() || (ai.natura === 'cespite' && !regolaFiscale.trim())} onClick={() => onDecision('conferma', motivazione, null, regolaFiscale)}><Check size={16} /> Conferma</Button>
                  <Button type="button" variant="secondary" disabled={busy} onClick={() => setCorreggi(value => !value)}><Pencil size={16} /> Correggi</Button>
                  {correggi && <Button type="button" disabled={busy || !motivazione.trim() || (campi.natura === 'cespite' && !regolaFiscale.trim())} onClick={() => onDecision('correggi', motivazione, campi, regolaFiscale)}>Salva correzione</Button>}
                  <Button type="button" variant="danger" disabled={busy || !motivazione.trim()} onClick={() => onDecision('rifiuta', motivazione)}><Ban size={16} /> Rifiuta</Button>
                </div>
                <div style={{ fontSize: 12, color: COLORS.textMuted }}>La decisione riguarda solo questa riga e conserva prima/dopo, autore, data e motivazione.</div>
              </div>
            )}
          </Card>

          <Card style={{ padding: 14 }}>
            <strong>Pagamenti: dichiarato, previsto ed effettivo restano distinti</strong>
            <div style={{ marginTop: 8, fontSize: 13, lineHeight: 1.6 }}>
              {(riga.pagamenti_dichiarati || []).length ? riga.pagamenti_dichiarati.map((p, index) => (
                <div key={`${p.codice}-${index}`}>{p.codice || '—'} - {p.descrizione} · {euro(p.importo)}{p.scadenza ? ` · scad. ${dataIT(p.scadenza)}` : ''}</div>
              )) : <div>Metodo dichiarato nell'XML: non disponibile</div>}
              <div>Metodo previsto dal fornitore: {riga.metodo_previsto || 'non configurato'}</div>
              <div>Metodo effettivo provato: {riga.metodo_effettivo || 'non documentato'}</div>
            </div>
          </Card>

          {riga.nota_credito && (
            <Card style={{ padding: 14, borderColor: riga.nota_credito.stato === 'collegata' ? COLORS.success : COLORS.warning }}>
              <strong>Nota di credito</strong>
              <p style={{ margin: '8px 0 0', fontSize: 13 }}>{riga.nota_credito.messaggio}</p>
            </Card>
          )}

          {!!(riga.anomalie || []).length && (
            <Card style={{ padding: 14, borderColor: COLORS.warning }}>
              <strong>Anomalie da verificare</strong>
              <div style={{ marginTop: 8, fontSize: 13 }}>{riga.anomalie.join(' · ')}</div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

function RigaMobile({ riga, onOpen }) {
  const aiBadge = badgeAI(riga.classificazione?.stato);
  return (
    <Card style={{ padding: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'start' }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 12, color: COLORS.textMuted }}>{dataIT(riga.data_fattura)} · {riga.numero_fattura} · riga {riga.numero_linea}</div>
          <strong style={{ display: 'block', marginTop: 4, overflowWrap: 'anywhere' }}>{riga.descrizione_originale || 'Descrizione assente'}</strong>
          <div style={{ fontSize: 13, marginTop: 4 }}>{riga.fornitore || 'Fornitore non disponibile'}</div>
        </div>
        {!!riga.anomalie?.length && <TriangleAlert size={18} color={COLORS.warning} aria-label="Anomalia" />}
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7, alignItems: 'center', marginTop: 10 }}>
        <Badge variant={aiBadge.variant}>{aiBadge.label}</Badge>
        <span style={{ fontWeight: 700 }}>{euro(riga.imponibile)}</span>
        <span style={{ fontSize: 12, color: COLORS.textMuted }}>IVA {riga.aliquota_iva ?? '—'}%</span>
      </div>
      <Button type="button" variant="secondary" onClick={() => onOpen(riga)} style={{ width: '100%', marginTop: 12, minHeight: 44 }}>Dettagli e originale</Button>
    </Card>
  );
}

export default function RigheAcquisti() {
  const { anno } = useAnnoGlobale();
  const isMobile = useIsMobile();
  const [filtri, setFiltri] = useState({ anno: String(anno), fornitore: '', testo: '', natura: '', conto: '', metodo: '', stato_ai: '', anomalie: false });
  const [righe, setRighe] = useState([]);
  const [meta, setMeta] = useState({ totale: 0, da_verificare: 0, anomalie: 0, has_more: false });
  const [loading, setLoading] = useState(true);
  const [errore, setErrore] = useState('');
  const [dettaglio, setDettaglio] = useState(null);
  const [aiStato, setAiStato] = useState(null);
  const [decisioneBusy, setDecisioneBusy] = useState(false);
  const [esitoLotti, setEsitoLotti] = useState('');
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    setFiltri(current => ({ ...current, anno: String(anno) }));
  }, [anno]);

  const paramsBase = useMemo(() => {
    const params = { limit: PER_PAGINA };
    if (filtri.anno) params.anno = filtri.anno;
    ['fornitore', 'testo', 'natura', 'conto', 'metodo', 'stato_ai'].forEach(key => {
      if (filtri[key]) params[key] = filtri[key];
    });
    if (filtri.anomalie) params.anomalie = true;
    return params;
  }, [filtri]);

  useEffect(() => {
    let active = true;
    const timer = setTimeout(async () => {
      setLoading(true);
      setErrore('');
      try {
        const { data } = await api.get('/api/righe-acquisti', { params: { ...paramsBase, skip: 0 } });
        if (!active) return;
        setRighe(data.righe || []);
        setMeta(data);
      } catch (error) {
        if (!active) return;
        setErrore(error?.response?.data?.detail || 'Impossibile caricare le righe acquisti.');
        setRighe([]);
      } finally {
        if (active) setLoading(false);
      }
    }, 250);
    return () => { active = false; clearTimeout(timer); };
  }, [paramsBase, reloadKey]);

  useEffect(() => {
    let active = true;
    api.get('/api/righe-acquisti/classificazione/stato')
      .then(({ data }) => { if (active) setAiStato(data); })
      .catch(() => { if (active) setAiStato(null); });
    return () => { active = false; };
  }, [reloadKey]);

  const aggiorna = (key, value) => setFiltri(current => ({ ...current, [key]: value }));

  const mostraAltre = async () => {
    setLoading(true);
    setErrore('');
    try {
      const { data } = await api.get('/api/righe-acquisti', { params: { ...paramsBase, skip: righe.length } });
      setRighe(current => [...current, ...(data.righe || [])]);
      setMeta(data);
    } catch (error) {
      setErrore(error?.response?.data?.detail || 'Impossibile caricare altre righe.');
    } finally {
      setLoading(false);
    }
  };

  const decidi = async (azione, motivazione, classificazione, regolaFiscale) => {
    setDecisioneBusy(true);
    setErrore('');
    try {
      await api.post(`/api/righe-acquisti/classificazione/${encodeURIComponent(dettaglio.id)}/decisione`, {
        azione, motivazione, regola_fiscale: regolaFiscale || '',
        ...(classificazione ? { classificazione } : {}),
      });
      setDettaglio(null);
      setReloadKey(value => value + 1);
    } catch (error) {
      setErrore(error?.response?.data?.detail || 'Decisione non salvata. Riprova senza perdere la proposta.');
    } finally {
      setDecisioneBusy(false);
    }
  };

  const assegnaLotti = async scelta => {
    setDecisioneBusy(true);
    setErrore('');
    try {
      const { data } = await api.post(`/api/righe-acquisti/${encodeURIComponent(dettaglio.id)}/prodotto-lotti`, scelta);
      const uguali = data?.righe_estese || 0;
      const cespiti = data?.cespiti_gia_creati || 0;
      setEsitoLotti(
        `Salvato: ${uguali ? `aggiornate anche ${uguali} righe uguali` : 'nessun\'altra riga uguale da aggiornare'}.`
        + (cespiti ? ` Attenzione: da queste righe risultano già ${cespiti} cespiti creati; verificali in Cespiti (non li ho toccati).` : ''),
      );
      setDettaglio(null);
      setReloadKey(value => value + 1);
    } catch (error) {
      setErrore(error?.response?.data?.detail || 'Associazione a Lotti non salvata. Riprova.');
    } finally {
      setDecisioneBusy(false);
    }
  };

  return (
    <div style={{ display: 'grid', gap: 14 }}>
      <div>
        <h1 style={{ margin: 0, fontSize: 24 }}>Righe acquisti</h1>
        <p style={{ margin: '5px 0 0', color: COLORS.textMuted, fontSize: 13 }}>
          Vista delle fatture canoniche: nessuna copia di XML/PDF e nessuna classificazione estesa automaticamente all'intero fornitore.
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, minmax(0, 1fr))', gap: 10 }}>
        <StatCard label="Righe trovate" value={meta.totale || 0} />
        <StatCard label="Da verificare" value={meta.da_verificare || 0} />
        <StatCard label="Con anomalie" value={meta.anomalie || 0} />
      </div>

      {aiStato && (
        <Card style={{ padding: 12, fontSize: 13 }}>
          <strong>Classificazione propositiva per singola riga</strong>
          <div style={{ marginTop: 5, color: COLORS.textMuted }}>
            {aiStato.abilitato ? 'Attiva' : 'Disattivata per evitare consumo di quota AI non approvato'} · proposte aperte {aiStato.proposte_aperte || 0}
            {aiStato.ultimo_giro ? ` · ultimo giro ${dataIT(aiStato.ultimo_giro)}` : ''}
          </div>
        </Card>
      )}

      {esitoLotti && <Card style={{ padding: 12, fontSize: 13 }}><div role="status">{esitoLotti}</div></Card>}

      <RegoleCategoria />

      <Card style={{ padding: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 10 }}><Filter size={17} /><strong>Filtri</strong></div>
        <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(auto-fit, minmax(170px, 1fr))', gap: 10 }}>
          <SelectFiltro label="Anno" value={filtri.anno} onChange={value => aggiorna('anno', value)}>
            <option value="">Tutti gli anni</option>
            {Array.from({ length: 10 }, (_, index) => Number(anno) + 1 - index).map(value => <option key={value} value={value}>{value}</option>)}
          </SelectFiltro>
          <label style={{ display: 'grid', gap: 5, fontSize: 12, color: COLORS.textMuted }}>
            Fornitore o P.IVA
            <Input aria-label="Fornitore o P.IVA" value={filtri.fornitore} onChange={event => aggiorna('fornitore', event.target.value)} />
          </label>
          <label style={{ display: 'grid', gap: 5, fontSize: 12, color: COLORS.textMuted }}>
            Testo, codice, fattura o ordine
            <div style={{ position: 'relative' }}>
              <Search size={16} style={{ position: 'absolute', left: 10, top: 13, color: COLORS.textMuted }} />
              <Input aria-label="Testo, codice, fattura o ordine" value={filtri.testo} onChange={event => aggiorna('testo', event.target.value)} style={{ paddingLeft: 34 }} />
            </div>
          </label>
          <label style={{ display: 'grid', gap: 5, fontSize: 12, color: COLORS.textMuted }}>
            Natura o categoria
            <Input aria-label="Natura o categoria" value={filtri.natura} onChange={event => aggiorna('natura', event.target.value)} />
          </label>
          <label style={{ display: 'grid', gap: 5, fontSize: 12, color: COLORS.textMuted }}>
            Conto, centro o destinazione
            <Input aria-label="Conto, centro o destinazione" value={filtri.conto} onChange={event => aggiorna('conto', event.target.value)} />
          </label>
          <label style={{ display: 'grid', gap: 5, fontSize: 12, color: COLORS.textMuted }}>
            Metodo dichiarato
            <Input aria-label="Metodo dichiarato" value={filtri.metodo} onChange={event => aggiorna('metodo', event.target.value)} placeholder="es. MP08 o SEPA" />
          </label>
          <SelectFiltro label="Stato classificazione" value={filtri.stato_ai} onChange={value => aggiorna('stato_ai', value)}>
            <option value="">Tutti</option>
            <option value="DA_VERIFICARE">Da verificare</option>
            <option value="PROPOSTA">Proposta</option>
            <option value="CONFERMATA">Confermata</option>
          </SelectFiltro>
        </div>
        <label style={{ display: 'inline-flex', alignItems: 'center', gap: 8, minHeight: 44, marginTop: 8, fontSize: 13 }}>
          <input type="checkbox" checked={filtri.anomalie} onChange={event => aggiorna('anomalie', event.target.checked)} /> Solo anomalie
        </label>
      </Card>

      {errore && (
        <div role="alert">
          <Card style={{ padding: 14, borderColor: COLORS.danger, color: COLORS.danger }}>{errore}</Card>
        </div>
      )}
      {loading && !righe.length ? <PageLoader /> : null}
      {!loading && !errore && !righe.length ? <Card style={{ padding: 22, textAlign: 'center' }}>Nessuna riga trovata con questi filtri.</Card> : null}

      {isMobile ? (
        <div style={{ display: 'grid', gap: 10 }}>{righe.map(riga => <RigaMobile key={riga.id} riga={riga} onOpen={setDettaglio} />)}</div>
      ) : righe.length ? (
        <TableWrap>
          <Table>
            <thead><tr><Th>Fattura</Th><Th>Fornitore</Th><Th>Riga</Th><Th>Imponibile</Th><Th>IVA</Th><Th>Classificazione</Th><Th>Azioni</Th></tr></thead>
            <tbody>{righe.map(riga => {
              const aiBadge = badgeAI(riga.classificazione?.stato);
              return (
                <tr key={riga.id}>
                  <Td><strong>{riga.numero_fattura || '—'}</strong><div style={{ fontSize: 12, color: COLORS.textMuted }}>{dataIT(riga.data_fattura)} · {riga.tipo_documento}</div></Td>
                  <Td>{riga.fornitore || '—'}<div style={{ fontSize: 12, color: COLORS.textMuted }}>{riga.partita_iva || ''}</div></Td>
                  <Td style={{ maxWidth: 360 }}><div style={{ overflowWrap: 'anywhere' }}>{riga.descrizione_originale || 'Descrizione assente'}</div><div style={{ fontSize: 12, color: COLORS.textMuted }}>n. {riga.numero_linea}{riga.anomalie?.length ? ' · anomalia' : ''}</div></Td>
                  <Td>{euro(riga.imponibile)}</Td>
                  <Td>{riga.aliquota_iva ?? '—'}%{riga.natura_iva ? <div style={{ fontSize: 12 }}>{riga.natura_iva}</div> : null}</Td>
                  <Td><Badge variant={aiBadge.variant}>{aiBadge.label}</Badge></Td>
                  <Td><Button type="button" size="sm" variant="secondary" onClick={() => setDettaglio(riga)}>Dettagli</Button></Td>
                </tr>
              );
            })}</tbody>
          </Table>
        </TableWrap>
      ) : null}

      {meta.has_more && <Button type="button" variant="secondary" disabled={loading} onClick={mostraAltre} style={{ justifySelf: 'center', minHeight: 44 }}>Mostra altre 200</Button>}
      {dettaglio && <DettaglioRiga onAssegna={assegnaLotti} riga={dettaglio} onClose={() => setDettaglio(null)} onDecision={decidi} busy={decisioneBusy} />}
    </div>
  );
}
