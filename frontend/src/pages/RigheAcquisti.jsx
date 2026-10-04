import React, { useEffect, useMemo, useState } from 'react';
import { Ban, Check, ExternalLink, Filter, Pencil, Search, TriangleAlert, X } from 'lucide-react';
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

function DettaglioRiga({ riga, onClose, onDecision, busy }) {
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
            {ai.stato === 'PROPOSTA' && (
              <div style={{ display: 'grid', gap: 10, marginTop: 14 }}>
                {correggi && (
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 8 }}>
                    {[
                      ['natura', 'Natura'], ['categoria', 'Categoria'], ['conto', 'Conto'],
                      ['centro_costo', 'Centro di costo'], ['destinazione_operativa', 'Destinazione operativa'],
                    ].map(([key, label]) => (
                      <label key={key} style={{ display: 'grid', gap: 4, fontSize: 12, color: COLORS.textMuted }}>
                        {label}<Input aria-label={label} value={campi[key]} onChange={event => aggiornaCampo(key, event.target.value)} />
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
      {dettaglio && <DettaglioRiga riga={dettaglio} onClose={() => setDettaglio(null)} onDecision={decidi} busy={decisioneBusy} />}
    </div>
  );
}
