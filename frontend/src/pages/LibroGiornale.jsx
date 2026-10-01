import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import api from '../api';
import { toast } from 'sonner';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { COLORS, formatDateIT, useIsMobile } from '../lib/utils.js';
import { euroOppure } from '../lib/vista';
import { Check, X, ChevronUp, ChevronDown } from 'lucide-react';
import { PageHeader } from '../components/ds/PageHeader';
import LinkContropartita, {
  PALETTE_CONTROPARTITA, ROTTE_CONTROPARTITA, rottaDocumentoOrigine,
} from '../components/LinkContropartita';

const periodoScrittura = scrittura => String(
  scrittura?.data_documento || scrittura?.data || '',
).slice(0, 7);

const scritturaRiguardaIva = scrittura => (scrittura?.righe || []).some(riga =>
  /\biva\b/i.test(`${riga.conto_nome || ''} ${riga.descrizione || ''}`),
);

function ProveFiscaliPeriodo({ prova, compatto = false }) {
  if (!prova) return null;
  const stato = {
    PAGATA_E_VERIFICATA: 'IVA pagata e verificata',
    VERSATA_O_COMPENSATA_CON_QUIETANZA: 'IVA versata o compensata — quietanza presente',
    DA_VERIFICARE: 'IVA da verificare',
    NESSUN_F24_IVA_TROVATO: 'Nessun F24 IVA trovato',
  }[prova.stato_iva] || prova.stato_iva;
  return (
    <div data-testid={`prove-fiscali-${prova.periodo}`} style={{
      padding: compatto ? 8 : 12, borderRadius: 9,
      background: PALETTE_CONTROPARTITA.salviaChiara,
      border: `1px solid ${PALETTE_CONTROPARTITA.bordo}`,
      color: COLORS.text, fontSize: 12, marginBottom: compatto ? 6 : 10,
    }}>
      <div style={{ fontWeight: 800, marginBottom: 6 }}>
        {prova.periodo} · {stato}
      </div>
      {(prova.f24 || []).map(modello => (
        <div key={modello.f24_id} style={{ marginBottom: 7 }}>
          <div>{modello.messaggio}</div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 4 }}>
            <LinkContropartita to={modello.f24_url} esterno compatto>Apri F24</LinkContropartita>
            {modello.quietanza_url && (
              <LinkContropartita to={modello.quietanza_url} esterno compatto>Vedi quietanza</LinkContropartita>
            )}
            {modello.movimento_bancario_id && (
              <LinkContropartita
                to={ROTTE_CONTROPARTITA.primaNotaBanca(modello.movimento_bancario_id)}
                compatto
              >
                Vedi movimento pagante
              </LinkContropartita>
            )}
          </div>
        </div>
      ))}
      {(prova.avvisi_ade || []).map(avviso => (
        <div key={avviso.id} style={{ paddingTop: 6, borderTop: `1px solid ${PALETTE_CONTROPARTITA.bordo}` }}>
          <strong>Lettera Agenzia delle Entrate:</strong> {avviso.filename}
          {avviso.messaggio_pagamento && (
            <div style={{ color: '#166534', fontWeight: 800, marginTop: 3 }}>
              {avviso.messaggio_pagamento}
            </div>
          )}
          {!avviso.associazione_certa && (
            <div style={{ color: '#92400e', marginTop: 3 }}>
              Periodo individuato, ma collegamento al tributo da verificare.
            </div>
          )}
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 4 }}>
            <LinkContropartita to={avviso.url} esterno compatto>Apri lettera</LinkContropartita>
            {avviso.quietanza_url && (
              <LinkContropartita to={avviso.quietanza_url} esterno compatto>Vedi quietanza</LinkContropartita>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

/**
 * Scrittura → documento d'origine (fattura / corrispettivo). Audit
 * 03/09/2026 §6 (PR 16): `fonte_documento` era salvato ma mai mostrato.
 */
function DocumentoOrigine({ scrittura, compatto = true }) {
  const fonte = scrittura?.fonte_documento;
  const doc = rottaDocumentoOrigine(fonte);
  if (!doc) return null;
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
      <span style={{ fontSize: 11.5, color: COLORS.textMuted }}>
        Origine: {fonte.tipo} {fonte.numero || fonte.id}
      </span>
      <LinkContropartita
        to={doc.to}
        esterno={doc.esterno}
        compatto={compatto}
        testId={`link-documento-${scrittura.id}`}
        title={`${fonte.tipo} ${fonte.numero || ''} · id ${fonte.id} · ${formatDateIT(scrittura.data_documento || scrittura.data || '')} · origine della scrittura n. ${scrittura.numero_registrazione}`}
      >
        {doc.etichetta}
      </LinkContropartita>
    </span>
  );
}

/**
 * Libro Giornale e Libro Mastro (art. 2216 c.c.) — registro UNICO
 * `movimenti_contabili` in partita doppia (motore §6.1).
 *
 * - Giornale: elenco CRONOLOGICO delle scritture definitive, ognuna col suo
 *   numero di protocollo (numero_registrazione) immutabile.
 * - Mastro: le stesse righe riclassificate per conto (mastrini).
 * - Esporta/Reimporta: il registro è ricostruibile "pari pari" — anche dopo
 *   una cancellazione totale, reimportando l'export si ricreano le scritture
 *   con protocollo, date e righe originali (reimport riservato all'Admin).
 * - Le operazioni PROVVISORIE vivono in Prima Nota Provvisoria (registro
 *   protocollo provvisorio) e NON compaiono qui finché non diventano definitive.
 */
export default function LibroGiornale() {
  const { anno } = useAnnoGlobale();
  // Su telefono le scritture/mastrini diventano card (16/07/2026, stessa
  // ricetta di Fatture/Prima Nota); su monitor resta la tabella.
  const isMobile = useIsMobile();
  const [vista, setVista] = useState('giornale'); // giornale | mastro
  const [giornale, setGiornale] = useState(null);
  const [mastro, setMastro] = useState(null);
  const [loading, setLoading] = useState(true);
  const [registerError, setRegisterError] = useState(null);
  const [espansa, setEspansa] = useState(null); // id scrittura espansa
  const [controllo60, setControllo60] = useState(null);
  const [proveFiscali, setProveFiscali] = useState([]);
  const [mostraProveFiscali, setMostraProveFiscali] = useState(false);
  // Una scrittura sbagliata si storna, non si cancella (regola vincolante): resta nel registro con il
  // suo storno. Qui, per leggere, si possono nascondere le coppie «stornata + storno».
  const [nascondiStornate, setNascondiStornate] = useState(true);
  const scritturaStornata = React.useMemo(() => {
    const tutte = giornale?.scritture || [];
    const stornata = scrittura => scrittura.stato === 'stornato' || String(scrittura.tipo || '').startsWith('storno_');
    return { contate: tutte.filter(stornata).length, e: stornata };
  }, [giornale]);
  const [limiteScritture, setLimiteScritture] = useState(200);
  const scrittureMostrate = React.useMemo(() => {
    const tutte = giornale?.scritture || [];
    return nascondiStornate ? tutte.filter(sc => !scritturaStornata.e(sc)) : tutte;
  }, [giornale, nascondiStornate, scritturaStornata]);

  // Deep-link dal bilancio di verifica (audit 03/09/2026 §6, PR 16):
  //   ?conto=<codice>&data_da=&data_a=  → solo le scritture di quel conto
  //   ?scrittura=<id>                   → scrittura aperta ed evidenziata
  const [searchParams, setSearchParams] = useSearchParams();
  const contoFiltro = searchParams.get('conto') || '';
  const scritturaRichiesta = searchParams.get('scrittura') || '';
  const dataDaParam = searchParams.get('data_da') || '';
  const dataAParam = searchParams.get('data_a') || '';
  const rigaEvidenziataRef = useRef(null);

  const carica = useCallback(async () => {
    setLoading(true);
    setRegisterError(null);
    setGiornale(null);
    setMastro(null);
    try {
      const dataDa = dataDaParam || `${anno}-01-01`;
      const dataA = dataAParam || `${anno}-12-31`;
      const range = `data_da=${dataDa}&data_a=${dataA}`;
      const filtroConto = contoFiltro ? `&conto=${encodeURIComponent(contoFiltro)}` : '';
      const controlloPromise = api
        .get('/api/contabilita-gestionale/libro-giornale/controllo-60-giorni')
        .catch(e => {
          setControllo60(null);
          toast.warning('Controllo 60 giorni non disponibile', {
            description: e.response?.data?.detail || e.message,
          });
          return null;
        });
      const proveFiscaliPromise = api
        .get(`/api/contabilita-gestionale/libro-giornale/prove-fiscali?anno=${anno}`)
        .catch(e => {
          setProveFiscali([]);
          toast.warning('Prove fiscali non disponibili', {
            description: e.response?.data?.detail || e.message,
          });
          return null;
        });
      const [g, m, c60, prove] = await Promise.all([
        api.get(`/api/contabilita-gestionale/libro-giornale?${range}&limit=2000${filtroConto}`),
        api.get(`/api/contabilita-gestionale/libro-mastro?${range}`),
        controlloPromise,
        proveFiscaliPromise,
      ]);
      setGiornale(g.data);
      setMastro(m.data);
      if (c60) setControllo60(c60.data);
      if (prove) setProveFiscali(prove.data?.periodi || []);
    } catch (e) {
      setRegisterError(e.response?.data?.detail || e.message || 'Servizio non disponibile');
      toast.error('Errore caricamento registro', {
        description: e.response?.data?.detail || e.message,
      });
    } finally {
      setLoading(false);
    }
  }, [anno, contoFiltro, dataDaParam, dataAParam]);

  useEffect(() => { carica(); }, [carica]);

  // Scrittura richiesta: aperta, evidenziata e portata a video appena caricata.
  useEffect(() => {
    if (!scritturaRichiesta || loading || !giornale?.scritture) return;
    const trovata = giornale.scritture.find(s => s.id === scritturaRichiesta);
    if (!trovata) return;
    setVista('giornale');
    setEspansa(trovata.id);
    const t = setTimeout(() => {
      rigaEvidenziataRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'center' });
    }, 100);
    return () => clearTimeout(t);
  }, [scritturaRichiesta, giornale, loading]);

  const rimuoviFiltri = () => {
    const p = new URLSearchParams(searchParams);
    ['conto', 'scrittura', 'data_da', 'data_a'].forEach(k => p.delete(k));
    setSearchParams(p, { replace: true });
  };

  const stileRigaScrittura = (s, base) => (
    s.id === scritturaRichiesta
      ? { ...base, background: PALETTE_CONTROPARTITA.evidenza, outline: `2px solid ${PALETTE_CONTROPARTITA.salvia}` }
      : base
  );

  const esporta = async () => {
    try {
      const res = await api.get(`/api/contabilita-gestionale/libro-giornale/export?anno=${anno}`);
      const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `libro_giornale_${anno}.json`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      toast.success(`Registro ${anno} esportato`, {
        description: `${res.data.numero_scritture} scritture nel file`,
      });
    } catch (e) {
      toast.error('Errore export', { description: e.response?.data?.detail || e.message });
    }
  };

  const eur = euroOppure;

  const Badge = ({ ok, children }) => (
    <span style={{
      padding: '3px 10px', borderRadius: 12, fontSize: 12, fontWeight: 700,
      background: ok ? '#e2f0e7' : '#f8e5e2', color: ok ? '#166534' : '#991b1b',
    }}>{children}</span>
  );

  return (
    <div>
      <PageHeader
        title="Libro giornale"
        actions={
          <button onClick={esporta} data-testid="export-giornale" style={btnGhost}
            disabled={loading || !giornale}>
            Esporta registro {anno}
          </button>
        }
        style={{ marginBottom: 14 }}
      />

      {/* Scelta della vista */}
      <div style={{
        display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 14,
      }}>
        {['giornale', 'mastro'].map(v => (
          <button key={v} onClick={() => setVista(v)} data-testid={`vista-${v}`}
            style={{
              padding: '8px 16px', borderRadius: 8, cursor: 'pointer', fontWeight: 700,
              border: `1px solid ${COLORS.border}`,
              background: vista === v ? COLORS.primary : 'transparent',
              color: vista === v ? '#fff' : COLORS.text,
            }}>
            {v === 'giornale' ? 'Libro Giornale' : 'Libro Mastro'}
          </button>
        ))}
      </div>

      <p style={{ color: COLORS.textMuted, fontSize: 12, margin: '0 0 14px' }}>
        Registro definitivo in partita doppia: ogni scrittura ha il suo numero di
        protocollo immutabile. Le operazioni provvisorie restano in Prima Nota
        Provvisoria finché non vengono confermate. L'export permette di ricostruire
        la contabilità pari pari, come registrata all'epoca dei fatti.
      </p>

      <div style={{ marginBottom: 14 }}>
        <button
          type="button"
          data-testid="toggle-prove-fiscali"
          onClick={() => setMostraProveFiscali(value => !value)}
          style={btnGhost}
        >
          {mostraProveFiscali ? 'Nascondi' : 'Mostra'} prove IVA, F24 e lettere ADE
        </button>
        {mostraProveFiscali && (
          <div style={{ marginTop: 10 }}>
            {proveFiscali.length > 0 ? proveFiscali.map(prova => (
              <ProveFiscaliPeriodo key={prova.periodo} prova={prova} />
            )) : (
              <div style={{ color: COLORS.textMuted, fontSize: 12 }}>
                Nessuna prova fiscale collegabile con certezza al {anno}.
              </div>
            )}
          </div>
        )}
      </div>

      {(contoFiltro || scritturaRichiesta) && (
        <div data-testid="filtro-contropartita" style={{
          display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap',
          padding: '8px 12px', marginBottom: 14, borderRadius: 8,
          background: PALETTE_CONTROPARTITA.salviaChiara,
          border: `1px solid ${PALETTE_CONTROPARTITA.bordo}`, color: PALETTE_CONTROPARTITA.salviaScura, fontSize: 13,
        }}>
          {contoFiltro && <span>Solo le scritture del conto <strong>{contoFiltro}</strong>
            {dataDaParam || dataAParam ? ` dal ${formatDateIT(dataDaParam)} al ${formatDateIT(dataAParam)}` : ''}
            {giornale ? ` · ${giornale.totale_disponibile ?? giornale.totale} scritture` : ''}</span>}
          {scritturaRichiesta && <span>Scrittura <strong>{scritturaRichiesta}</strong> in evidenza</span>}
          <Link to="/contabilita/giornale" onClick={rimuoviFiltri} style={{ color: PALETTE_CONTROPARTITA.sabbia, fontWeight: 700 }}>
            Rimuovi filtro
          </Link>
        </div>
      )}

      {/* Controllo 60 giorni (DPR 600/73 art. 22) */}
      {controllo60 && !controllo60.conforme && (
        <div data-testid="alert-60-giorni" style={{
          padding: '10px 14px', background: '#fffbeb', border: '1px solid #fcd34d',
          borderRadius: 8, color: '#92400e', fontSize: 13, marginBottom: 14,
        }}>
          <strong>{controllo60.totale_in_ritardo} documenti oltre i 60 giorni</strong> non
          ancora registrati in contabilità ({controllo60.fatture_non_registrate_oltre_60gg} fatture,{' '}
          {controllo60.corrispettivi_non_registrati_oltre_60gg} corrispettivi).
          Le registrazioni cronologiche vanno eseguite entro 60 giorni: {controllo60.azione}
        </div>
      )}

      {!loading && giornale?.troncato && (
        <div role="alert" style={{
          padding: '10px 14px', background: '#fffbeb', border: '1px solid #fcd34d',
          borderRadius: 8, color: '#92400e', fontSize: 13, marginBottom: 14,
        }}>
          <strong>Vista parziale:</strong> mostrate {giornale.totale} scritture su{' '}
          {giornale.totale_disponibile}. Totali e quadratura non rappresentano l'intero periodo.
        </div>
      )}

      {!loading && giornale?.qualita_registro && !giornale.qualita_registro.registro_valido && (
        <div role="alert" data-testid="alert-qualita-giornale" style={{
          padding: '10px 14px', background: '#fef2f2', border: '1px solid #fecaca',
          borderRadius: 8, color: '#991b1b', fontSize: 13, marginBottom: 14,
        }}>
          <strong>Registro non valido:</strong>{' '}
          {giornale.qualita_registro.scritture_sbilanciate || 0} scritture sbilanciate,{' '}
          {giornale.qualita_registro.protocolli_duplicati || 0} protocolli duplicati,{' '}
          {giornale.qualita_registro.scritture_senza_protocollo || 0} senza protocollo,{' '}
          {giornale.qualita_registro.righe_non_numeriche || 0} righe non numeriche e{' '}
          {giornale.qualita_registro.righe_senza_conto || 0} righe senza conto. Nessuna
          correzione automatica è stata eseguita.
        </div>
      )}

      {loading ? (
        <div style={{ color: COLORS.textMuted, padding: 24 }}>Caricamento registro…</div>
      ) : registerError ? (
        <div role="alert" style={{
          color: '#991b1b', background: '#fef2f2', border: '1px solid #fecaca',
          borderRadius: 8, padding: 18,
        }}>
          <strong>Impossibile caricare Libro Giornale e Libro Mastro.</strong>
          <div style={{ marginTop: 4, fontSize: 13 }}>{String(registerError)}</div>
          <button type="button" onClick={carica} style={{ ...btnGhost, marginTop: 12 }}>
            Riprova
          </button>
        </div>
      ) : vista === 'giornale' ? (
        <>
          <div style={{ display: 'flex', gap: 16, marginBottom: 12, flexWrap: 'wrap', alignItems: 'center' }}>
            <strong style={{ color: COLORS.text }}>{giornale?.totale ?? 0} scritture</strong>
            {scritturaStornata.contate > 0 && (
              <label data-testid="nascondi-stornate" style={{ display: 'inline-flex', gap: 8, alignItems: 'center', minHeight: 44, fontSize: 13, cursor: 'pointer' }}>
                <input
                  type="checkbox" checked={nascondiStornate} style={{ width: 20, height: 20 }}
                  onChange={e => setNascondiStornate(e.target.checked)}
                />
                Nascondi le {scritturaStornata.contate} scritture stornate e i loro storni
                <span style={{ color: COLORS.textMuted }}>(restano nel registro, il saldo non cambia)</span>
              </label>
            )}
            <span style={{ color: COLORS.textMuted, fontSize: 13 }}>
              DARE {eur(giornale?.totale_dare)} · AVERE {eur(giornale?.totale_avere)}
            </span>
            <Badge ok={giornale?.quadratura}>
              {giornale?.quadratura ? <><Check size={12} aria-hidden /> Quadra</> : <><X size={12} aria-hidden /> Non quadra</>}
            </Badge>
          </div>
          {isMobile ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {scrittureMostrate.slice(0, limiteScritture).map(s => (
                <div
                  key={s.id}
                  ref={s.id === scritturaRichiesta ? rigaEvidenziataRef : null}
                  onClick={() => setEspansa(espansa === s.id ? null : s.id)}
                  data-testid={`scrittura-${s.numero_registrazione}`}
                  style={stileRigaScrittura(s, {
                    background: 'white', borderRadius: 12, border: `1px solid ${COLORS.border}`,
                    borderLeft: '4px solid #c15f3c', boxShadow: '0 1px 2px rgba(20, 20, 19,0.06)',
                    padding: '10px 12px', cursor: 'pointer', minWidth: 0,
                  })}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
                    <div style={{ minWidth: 0 }}>
                      <span style={{ fontWeight: 800, color: '#141413', fontSize: 13 }}>
                        n. {s.numero_registrazione}
                      </span>
                      <span style={{ marginLeft: 8, fontFamily: 'ui-monospace, Menlo, monospace', fontSize: 11.5, color: '#5f5c55' }}>
                        {formatDateIT(s.data_documento || s.data)}
                      </span>
                      <span style={{ marginLeft: 8, background: '#f2f0e9', color: '#5f5c55', padding: '2px 7px', borderRadius: 999, fontSize: 10.5, fontWeight: 600 }}>
                        {s.tipo}
                      </span>
                    </div>
                    <span style={{ color: COLORS.textMuted, flexShrink: 0 }}>{espansa === s.id ? <ChevronUp size={14} aria-hidden /> : <ChevronDown size={14} aria-hidden />}</span>
                  </div>
                  <div style={{ marginTop: 4, fontSize: 12.5, color: '#2c2b28', overflowWrap: 'anywhere' }}>
                    {s.descrizione}
                  </div>
                  <div style={{ marginTop: 6, display: 'flex', gap: 14, fontSize: 12, fontFamily: 'ui-monospace, Menlo, monospace' }}>
                    <span style={{ color: '#16a34a', fontWeight: 700 }}>DARE {eur(s.totale_dare)}</span>
                    <span style={{ color: '#dc2626', fontWeight: 700 }}>AVERE {eur(s.totale_avere)}</span>
                  </div>
                  {espansa === s.id && (
                    <div style={{ marginTop: 8, borderTop: `1px solid ${COLORS.border}`, paddingTop: 6 }}>
                      <div style={{ marginBottom: 6 }} onClick={e => e.stopPropagation()}>
                        <DocumentoOrigine scrittura={s} />
                      </div>
                      {scritturaRiguardaIva(s) && (
                        <div onClick={e => e.stopPropagation()}>
                          <ProveFiscaliPeriodo
                            compatto
                            prova={proveFiscali.find(p => p.periodo === periodoScrittura(s))}
                          />
                        </div>
                      )}
                      {(s.righe || []).map((r, i) => (
                        <div key={i} style={{ fontSize: 11.5, color: '#5f5c55', padding: '3px 0', display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                          <span style={{ minWidth: 0, overflowWrap: 'anywhere' }}>
                            {r.conto_codice || r.conto} — {r.conto_nome}
                          </span>
                          <span style={{ whiteSpace: 'nowrap', fontFamily: 'ui-monospace, Menlo, monospace' }}>
                            {r.dare ? `D ${eur(r.dare)}` : `A ${eur(r.avere)}`}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ background: COLORS.bgAlt, textAlign: 'left' }}>
                  <th style={th}>Prot. n.</th>
                  <th style={th}>Data</th>
                  <th style={th}>Tipo</th>
                  <th style={th}>Descrizione</th>
                  <th style={{ ...th, textAlign: 'right' }}>DARE</th>
                  <th style={{ ...th, textAlign: 'right' }}>AVERE</th>
                  <th style={th}></th>
                </tr>
              </thead>
              <tbody>
                {scrittureMostrate.slice(0, limiteScritture).map(s => (
                  <React.Fragment key={s.id}>
                    <tr style={stileRigaScrittura(s, { borderBottom: `1px solid ${COLORS.border}`, cursor: 'pointer' })}
                      ref={s.id === scritturaRichiesta ? rigaEvidenziataRef : null}
                      onClick={() => setEspansa(espansa === s.id ? null : s.id)}
                      data-testid={`scrittura-${s.numero_registrazione}`}>
                      <td style={{ ...td, fontWeight: 700 }}>{s.numero_registrazione}</td>
                      <td style={td}>{formatDateIT(s.data_documento || s.data)}</td>
                      <td style={td}>{s.tipo}</td>
                      <td style={td}>{s.descrizione}</td>
                      <td style={{ ...td, textAlign: 'right' }}>{eur(s.totale_dare)}</td>
                      <td style={{ ...td, textAlign: 'right' }}>{eur(s.totale_avere)}</td>
                      <td style={{ ...td, color: COLORS.textMuted }}>
                        {espansa === s.id ? <ChevronUp size={14} aria-hidden /> : <ChevronDown size={14} aria-hidden />}
                      </td>
                    </tr>
                    {espansa === s.id && rottaDocumentoOrigine(s.fonte_documento) && (
                      <tr style={{ background: COLORS.bgAlt, fontSize: 12 }}>
                        <td style={td}></td>
                        <td style={td} colSpan={6}><DocumentoOrigine scrittura={s} /></td>
                      </tr>
                    )}
                    {espansa === s.id && scritturaRiguardaIva(s) && proveFiscali.some(
                      prova => prova.periodo === periodoScrittura(s),
                    ) && (
                      <tr style={{ background: COLORS.bgAlt, fontSize: 12 }}>
                        <td style={td}></td>
                        <td style={td} colSpan={6}>
                          <ProveFiscaliPeriodo
                            compatto
                            prova={proveFiscali.find(p => p.periodo === periodoScrittura(s))}
                          />
                        </td>
                      </tr>
                    )}
                    {espansa === s.id && (s.righe || []).map((r, i) => (
                      <tr key={i} style={{ background: COLORS.bgAlt, fontSize: 12 }}>
                        <td style={td}></td>
                        <td style={td} colSpan={2}>{r.conto_codice || r.conto} — {r.conto_nome}</td>
                        <td style={td}>{r.descrizione}</td>
                        <td style={{ ...td, textAlign: 'right' }}>{r.dare ? `${eur(r.dare)}` : ''}</td>
                        <td style={{ ...td, textAlign: 'right' }}>{r.avere ? `${eur(r.avere)}` : ''}</td>
                        <td style={td}></td>
                      </tr>
                    ))}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>
          )}
          {scrittureMostrate.length > limiteScritture && (
            <div style={{ textAlign: 'center', padding: 12 }}>
              <button type="button" onClick={() => setLimiteScritture(n => n + 200)}
                style={{ minHeight: 44, padding: '10px 18px', borderRadius: 8, border: `1px solid ${COLORS.border}`, background: COLORS.card, cursor: 'pointer', fontWeight: 600 }}>
                Mostra altre ({scrittureMostrate.length - limiteScritture})
              </button>
            </div>
          )}
          {scrittureMostrate.length === 0 && (
            <div style={{ color: COLORS.textMuted, padding: 24, textAlign: 'center' }}>
              Nessuna scrittura definitiva per il {anno}{contoFiltro ? ` sul conto ${contoFiltro}` : ''}.
              Le scritture nascono da sole all'arrivo di fatture e corrispettivi
              (registrazione automatica), dal comando "Registra pregresso" del
              Piano dei Conti per i documenti importati prima, e dalle operazioni
              di TFR e ammortamenti.
            </div>
          )}
        </>
      ) : (
        <>
          <div style={{ display: 'flex', gap: 16, marginBottom: 12, flexWrap: 'wrap', alignItems: 'center' }}>
            <strong style={{ color: COLORS.text }}>{mastro?.totale_conti ?? 0} mastrini</strong>
            <span style={{ color: COLORS.textMuted, fontSize: 13 }}>
              DARE {eur(mastro?.totale_dare)} · AVERE {eur(mastro?.totale_avere)}
            </span>
            <Badge ok={mastro?.quadratura}>
              {mastro?.quadratura ? <><Check size={12} aria-hidden /> Quadra</> : <><X size={12} aria-hidden /> Non quadra</>}
            </Badge>
          </div>
          {isMobile ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {(mastro?.mastrini || []).map(m => (
                <div
                  key={m.conto}
                  style={{
                    background: 'white', borderRadius: 12, border: `1px solid ${COLORS.border}`,
                    borderLeft: `4px solid ${m.saldo >= 0 ? '#c15f3c' : '#dc2626'}`,
                    boxShadow: '0 1px 2px rgba(20, 20, 19,0.06)', padding: '10px 12px', minWidth: 0,
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
                    <div style={{ minWidth: 0 }}>
                      <span style={{ fontWeight: 800, color: '#141413', fontSize: 13, fontFamily: 'ui-monospace, Menlo, monospace' }}>
                        {m.conto}
                      </span>
                      <div style={{ fontSize: 12.5, color: '#2c2b28', overflowWrap: 'anywhere' }}>{m.conto_nome}</div>
                      {m.conto_ufficiale && (
                        <div style={{ fontSize: 11, color: COLORS.textMuted, overflowWrap: 'anywhere' }}>
                          CEE {m.conto_ufficiale} — {m.conto_ufficiale_nome || ''}
                        </div>
                      )}
                    </div>
                    <div style={{ textAlign: 'right', flexShrink: 0 }}>
                      <div style={{
                        fontWeight: 800, fontSize: 14.5, fontFamily: 'ui-monospace, Menlo, monospace',
                        color: m.saldo >= 0 ? '#141413' : '#dc2626',
                      }}>
                        {eur(m.saldo)}
                      </div>
                      <div style={{ fontSize: 10.5, color: COLORS.textMuted }}>{m.movimenti} righe</div>
                    </div>
                  </div>
                  <div style={{ marginTop: 6, display: 'flex', gap: 14, fontSize: 11.5, fontFamily: 'ui-monospace, Menlo, monospace' }}>
                    <span style={{ color: '#16a34a' }}>DARE {eur(m.dare)}</span>
                    <span style={{ color: '#dc2626' }}>AVERE {eur(m.avere)}</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ background: COLORS.bgAlt, textAlign: 'left' }}>
                  <th style={th}>Conto</th>
                  <th style={th}>Nome</th>
                  <th style={th}>Conto CEE ufficiale</th>
                  <th style={{ ...th, textAlign: 'right' }}>DARE</th>
                  <th style={{ ...th, textAlign: 'right' }}>AVERE</th>
                  <th style={{ ...th, textAlign: 'right' }}>Saldo</th>
                  <th style={{ ...th, textAlign: 'right' }}>Righe</th>
                </tr>
              </thead>
              <tbody>
                {(mastro?.mastrini || []).map(m => (
                  <tr key={m.conto} style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                    <td style={{ ...td, fontWeight: 700 }}>{m.conto}</td>
                    <td style={td}>{m.conto_nome}</td>
                    <td style={td}>
                      {m.conto_ufficiale
                        ? `${m.conto_ufficiale} — ${m.conto_ufficiale_nome || ''}`
                        : <span style={{ color: COLORS.textMuted }}>—</span>}
                    </td>
                    <td style={{ ...td, textAlign: 'right' }}>{eur(m.dare)}</td>
                    <td style={{ ...td, textAlign: 'right' }}>{eur(m.avere)}</td>
                    <td style={{
                      ...td, textAlign: 'right', fontWeight: 700,
                      color: m.saldo >= 0 ? COLORS.text : COLORS.danger,
                    }}>{eur(m.saldo)}</td>
                    <td style={{ ...td, textAlign: 'right' }}>{m.movimenti}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          )}
        </>
      )}
    </div>
  );
}

const th = { padding: '10px 12px', color: '#5f5c55', fontWeight: 700, whiteSpace: 'nowrap' };
const td = { padding: '9px 12px', color: '#141413' };
const btnGhost = {
  background: 'transparent', border: '1px solid #e6e3d9', color: '#141413',
  borderRadius: 8, padding: '8px 14px', cursor: 'pointer', fontSize: 13, fontWeight: 600,
};
