import React, { useEffect, useMemo, useState } from 'react';
import { ArrowUpRight, FileText, RefreshCw } from 'lucide-react';
import api from '../api';
import { COLORS, formatEuro, formatDateIT } from '../lib/utils';
import { Esito, ListaAdattiva } from './ds';
import { VisoreOriginale } from './ApriOriginale';
import ConfermaAddebitoF24, { LIVELLI_CONFERMABILI } from './ConfermaAddebitoF24';

/**
 * Quietanze F24 ↔ addebiti I24 in banca.
 *
 * Quietanza e addebito sono due prove dello stesso pagamento: qui si vedono
 * affiancate, con l'esito e la sua motivazione (importo, date e causale
 * confrontati). Il motore e' uno solo, `f24_controllo_incrociato`, a livelli
 * (certo, probabile, parziale, nessun match, movimento orfano): scrive solo il
 * certo, nel giro dei 30 minuti; questa pagina legge soltanto. L'unica azione
 * e' la conferma del titolare su un probabile o parziale
 * (`ConfermaAddebitoF24`): sceglie fra i candidati del motore e dice il
 * perche' a chip; la scrittura e' la stessa del certo, sul backend. Nessun
 * giudizio fiscale: fatti e discrepanze, da verificare col commercialista.
 */
const GRUPPI_CONFERMABILI = ['da_verificare', 'modelli_da_verificare'];

const LIVELLI = {
  CERTO: 'Certo',
  PROBABILE: 'Probabile',
  PARZIALE: 'Parziale',
  NESSUN_MATCH: 'Nessuna corrispondenza bancaria',
  MOVIMENTO_ORFANO: 'Movimento orfano',
};

// Senza protocollo la quietanza non prova da sola il pagamento: resta da verificare.
const etichettaLivello = r =>
  (r.livello === 'NESSUN_MATCH' && !r.protocollo ? 'Nessun match, da verificare' : (LIVELLI[r.livello] || r.livello));

const GRUPPI = [
  { chiave: 'riscontrati', etichetta: 'Riscontrati', esito: 'chiuso', testo: 'Riscontrato' },
  { chiave: 'da_verificare', etichetta: 'Da verificare', esito: 'verificare', testo: 'Da verificare' },
  {
    chiave: 'addebiti_senza_quietanza', etichetta: 'Addebiti senza quietanza',
    esito: 'intervento', testo: 'Quietanza mancante',
  },
  {
    chiave: 'quietanze_senza_addebito', etichetta: 'Quietanze senza addebito',
    esito: 'intervento', testo: 'Addebito non trovato',
  },
  {
    chiave: 'quietanze_senza_estratto', etichetta: 'Periodi senza estratto',
    esito: 'verificare', testo: 'Estratto assente',
  },
  {
    chiave: 'modelli_da_verificare', etichetta: 'Modelli F24 da verificare',
    esito: 'verificare', testo: 'Da verificare',
  },
  { chiave: 'quietanze_incomplete', etichetta: 'Quietanze illeggibili', esito: 'verificare', testo: 'Dati mancanti' },
  {
    chiave: 'tributi_ripetuti', etichetta: 'Stesso tributo in più deleghe',
    esito: 'intervento', testo: 'Possibile duplicazione',
  },
];

const TIPI_VERSAMENTO = {
  ordinario: 'Ordinario',
  ravvedimento: 'Ravvedimento',
  regolarizzazione: 'Regolarizzazione RC01',
};

// Da dove viene la delega: la data d'invio sta nelle prime cifre del protocollo.
function Invio({ p }) {
  if (!p?.inviato_il_it) return null;
  const parti = [
    `inviata il ${p.inviato_il_it}`,
    p.programmato === true ? 'programmata' : p.programmato === false ? 'non programmata' : null,
    p.dilazione_inps
      ? `Rata ${p.dilazione_inps.rata}/${p.dilazione_inps.di} dilazione INPS`
        + (p.dilazione_inps.importo_diverso ? ' (importo diverso dal piano)' : '')
      : TIPI_VERSAMENTO[p.tipo_versamento] || null,
    p.senza_modello && !p.dilazione_inps ? 'senza modello del commercialista' : null,
  ].filter(Boolean);
  return (
    <span style={{ fontSize: 11.5, color: COLORS.textMuted }} data-testid="invio-delega">
      {parti.join(' · ')}
    </span>
  );
}

const stileChip = attivo => ({
  minHeight: 44,
  padding: '8px 14px',
  borderRadius: 999,
  border: `1px solid ${attivo ? COLORS.primary : COLORS.borderDark}`,
  background: attivo ? COLORS.primarySoft : COLORS.card,
  color: attivo ? COLORS.primary : COLORS.text,
  fontWeight: 600,
  fontSize: 13,
  cursor: 'pointer',
});

const stileLink = {
  display: 'inline-flex', alignItems: 'center', gap: 4, minHeight: 32,
  color: COLORS.primary, fontWeight: 600, fontSize: 12.5, textDecoration: 'none',
  background: 'none', border: 'none', padding: 0, cursor: 'pointer',
};

const stileDato = { display: 'grid', gridTemplateColumns: 'minmax(130px, 0.35fr) 1fr', gap: 8, fontSize: 12.5 };

function Dato({ etichetta, children, testId }) {
  if (children == null || children === '') return null;
  return (
    <div style={stileDato} data-testid={testId}>
      <strong style={{ color: COLORS.textMuted }}>{etichetta}</strong>
      <span style={{ overflowWrap: 'anywhere' }}>{children}</span>
    </div>
  );
}

const testoEsito = r => (
  r._gruppo.chiave === 'tributi_ripetuti' && r.doppio_versamento_confermato
    ? 'Versato due volte'
    : r._gruppo.testo
);

function DettaglioF24({ riga, quietanzeDi, onApriQuietanza, onClose }) {
  const pagamenti = riga.pagamenti || [{ ...riga, quietanze: quietanzeDi(riga) }];
  const candidati = riga.candidati || [];
  const doppio = riga._gruppo.chiave === 'tributi_ripetuti';
  return (
    <div
      role="dialog" aria-modal="true" aria-labelledby="dettaglio-f24-titolo"
      data-testid={`dettaglio-f24-${riga._id}`}
      style={{ position: 'fixed', inset: 0, zIndex: 10000, background: 'rgba(30, 35, 32, 0.58)', display: 'grid', placeItems: 'center', padding: 18 }}
      onMouseDown={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div style={{ width: 'min(900px, 100%)', maxHeight: '92vh', overflow: 'auto', background: COLORS.card, borderRadius: 14, border: `1px solid ${COLORS.border}`, padding: 18 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' }}>
          <div>
            <h3 id="dettaglio-f24-titolo" style={{ margin: 0, fontSize: 18 }}>Dettaglio quietanza F24 e banca</h3>
            <div style={{ marginTop: 4, color: COLORS.textMuted, fontSize: 13 }}>
              {formatDateIT(riga.data) || 'Data non letta'} · {testoEsito(riga)}
            </div>
          </div>
          <button type="button" onClick={onClose} aria-label="Chiudi dettaglio" style={{ ...stileLink, fontSize: 20 }}>×</button>
        </div>

        {doppio && (
          <div role="alert" data-testid="segnalazione-doppio-versamento" style={{ marginTop: 14, padding: 12, borderRadius: 8, background: COLORS.dangerLight, color: COLORS.danger, fontWeight: 700 }}>
            {riga.doppio_versamento_confermato
              ? `Doppio versamento riscontrato: ${pagamenti.length} deleghe hanno movimenti bancari distinti.`
              : `Possibile duplicazione: sono presenti ${pagamenti.length} deleghe, ma non sono provati altrettanti addebiti bancari distinti.`}
          </div>
        )}
        <div style={{ marginTop: 12, padding: 12, background: COLORS.bgAlt, borderRadius: 8 }}>
          <Dato etichetta="Stato">{riga.livello ? `Livello ${etichettaLivello(riga)}` : testoEsito(riga)}</Dato>
          {riga.conferma_titolare && (
            <Dato etichetta="Correzione salvata" testId="conferma-titolare-salvata">
              {riga.conferma_titolare.motivo_testo || riga.conferma_titolare.motivo}
            </Dato>
          )}
          <Dato etichetta="Spiegazione" testId="spiegazione-riscontro">{riga.motivazione || riga.motivo || 'Mancata corrispondenza: nessun motivo tecnico disponibile.'}</Dato>
          {riga.righe && <Dato etichetta="Righe ripetute">{riga.righe}</Dato>}
        </div>

        {pagamenti.map((p, indice) => {
          const quietanze = p.quietanze || [];
          const addebito = p.addebito || (!riga.pagamenti ? riga.addebito : null);
          return (
            <section key={p.chiave || indice} data-testid={`delega-dettaglio-${indice}`} style={{ marginTop: 14, padding: 14, border: `1px solid ${COLORS.border}`, borderRadius: 10 }}>
              <h4 style={{ margin: '0 0 9px', fontSize: 14 }}>Delega {pagamenti.length > 1 ? `${indice + 1} di ${pagamenti.length}` : ''}</h4>
              <Dato etichetta="Protocollo">{p.protocollo || 'Non letto'}</Dato>
              <Dato etichetta="Data quietanza">{formatDateIT(p.data) || 'Non letta'}</Dato>
              <Dato etichetta="Importo quietanza">{p.importo ? formatEuro(p.importo) : 'Saldo non letto'}</Dato>
              <Dato etichetta="Invio"><Invio p={p} /></Dato>
              {quietanze.map((q, qi) => (
                <div key={q.id || qi} style={{ marginTop: 8, paddingTop: 8, borderTop: `1px solid ${COLORS.border}` }}>
                  <Dato etichetta="ID quietanza" testId={`quietanza-id-${q.id}`}>{q.id || 'Non disponibile'}</Dato>
                  <Dato etichetta="File">{q.filename}</Dato>
                  <Dato etichetta="Fonte">{q.fonte}</Dato>
                  {q.pdf_url ? (
                    <button type="button" style={{ ...stileLink, marginTop: 5 }} onClick={() => onApriQuietanza(q, p)}>
                      <FileText size={14} aria-hidden="true" /> Apri originale della quietanza
                    </button>
                  ) : <div style={{ color: COLORS.textMuted, fontSize: 12.5 }}>Originale non disponibile; resta visibile l'ID archivio.</div>}
                </div>
              ))}
              {addebito ? (
                <div data-testid={`movimento-dettaglio-${addebito.movimento_id}`} style={{ marginTop: 10, padding: 12, background: COLORS.primarySoft, borderRadius: 8 }}>
                  <strong>Movimento dell'estratto conto associato</strong>
                  <Dato etichetta="ID movimento">{addebito.movimento_id}</Dato>
                  <Dato etichetta="Data contabile">{formatDateIT(addebito.data)}</Dato>
                  <Dato etichetta="Importo">{formatEuro(addebito.importo)}</Dato>
                  <Dato etichetta="Causale">{addebito.descrizione}</Dato>
                  <Dato etichetta="Data incasso">{formatDateIT(addebito.data_incasso)}</Dato>
                  <Dato etichetta="Riferimento banca">{addebito.riferimento}</Dato>
                  <Dato etichetta="Riferimento operazione">{addebito.riferimento_operazione}</Dato>
                  <Dato etichetta="Fonte / banca">{[addebito.fonte, addebito.banca].filter(Boolean).join(' · ')}</Dato>
                  <Dato etichetta="Conto">{addebito.conto}</Dato>
                  <Dato etichetta="Stato movimento">{addebito.stato_riconciliazione || addebito.tipo_riconciliazione || (riga.livello === 'CERTO' ? 'Riscontrato con questa quietanza' : 'Associato alla delega')}</Dato>
                  {(addebito.copie_tecniche || []).length > 0 && (
                    <Dato etichetta="Copie tecniche escluse" testId="copie-tecniche-movimento">
                      {(addebito.copie_tecniche || []).map(c => `${c.movimento_id} (${formatDateIT(c.data)}${c.fonte ? ` · ${c.fonte}` : ''})`).join('; ')}
                    </Dato>
                  )}
                </div>
              ) : (
                <div data-testid="mancata-corrispondenza-banca" style={{ marginTop: 10, padding: 12, borderRadius: 8, background: COLORS.warningLight, color: COLORS.text }}>
                  <strong>Mancata corrispondenza bancaria.</strong> Nessun movimento dell'estratto conto è associato a questa delega.
                </div>
              )}
            </section>
          );
        })}

        {candidati.length > 0 && (
          <section style={{ marginTop: 14, padding: 14, border: `1px solid ${COLORS.border}`, borderRadius: 10 }}>
            <h4 style={{ margin: '0 0 8px', fontSize: 14 }}>Candidati non confermati</h4>
            <p style={{ margin: '0 0 8px', fontSize: 12.5 }}>Non sono collegamenti contabili: richiedono una scelta umana motivata.</p>
            {candidati.map(a => <Dato key={a.movimento_id} etichetta={a.movimento_id}>{formatDateIT(a.data)} · {formatEuro(a.importo)} · {a.descrizione}</Dato>)}
          </section>
        )}
      </div>
    </div>
  );
}

export default function RiscontroQuietanzeBanca({ anno }) {
  const [dati, setDati] = useState(null);
  const [errore, setErrore] = useState(null);
  const [caricamento, setCaricamento] = useState(false);
  const [gruppo, setGruppo] = useState('tutti');
  const [pdf, setPdf] = useState(null);
  const [dettaglio, setDettaglio] = useState(null);

  const carica = async () => {
    setCaricamento(true);
    setErrore(null);
    try {
      const qs = anno ? `?anno=${anno}` : '';
      const res = await api.get(`/api/f24-riconciliazione/quietanze-banca${qs}`);
      setDati(res.data);
    } catch (e) {
      setErrore(e.response?.data?.message || e.response?.data?.detail || e.message);
    } finally {
      setCaricamento(false);
    }
  };

  useEffect(() => {
    carica();
  }, [anno]);

  const righe = useMemo(() => {
    if (!dati) return [];
    const scelti = gruppo === 'tutti' ? GRUPPI : GRUPPI.filter(g => g.chiave === gruppo);
    return scelti
      .flatMap(g => (dati[g.chiave] || []).map((r, i) => ({
        ...r, _gruppo: g, _id: `${g.chiave}:${r.chiave || r.movimento_id || i}`,
      })))
      .sort((a, b) => String(b.data || '').localeCompare(String(a.data || '')));
  }, [dati, gruppo]);

  const quietanzeDi = r => r.quietanze || (r.pagamenti || []).flatMap(p => p.quietanze || []);
  const addebitiDi = r => {
    if (r.pagamenti) return r.pagamenti.map(p => p.addebito).filter(Boolean);
    return r.addebito ? [r.addebito] : r.candidati || (r.movimento_id ? [r] : []);
  };

  const colonne = [
    {
      key: 'data', label: 'Data', ruoloCard: 'sottotitolo',
      render: r => formatDateIT(r.data) || '—',
      tdStyle: { whiteSpace: 'nowrap' },
    },
    {
      key: 'importo', label: 'Importo', align: 'right', mono: true, ruoloCard: 'importo',
      render: r => (r.importo ? formatEuro(r.importo) : '—'),
    },
    {
      key: 'esito', label: 'Esito', ruoloCard: 'titolo',
      render: r => (
        <span style={{ display: 'inline-flex', flexDirection: 'column', gap: 2 }}>
          <Esito esito={r._gruppo.esito} data-testid={`esito-${r._id}`}>{testoEsito(r)}</Esito>
          {r.livello && (
            <span style={{ fontSize: 11.5, color: COLORS.textMuted }} data-testid={`livello-${r._id}`}>
              Livello: {etichettaLivello(r)}
              {r.differenza ? ` · differenza ${formatEuro(r.differenza)}` : ''}
            </span>
          )}
        </span>
      ),
    },
    {
      key: 'quietanza', label: 'Quietanza', ruoloCard: 'dettaglio',
      render: r => {
        const qs = quietanzeDi(r);
        if (!qs.length) return <span style={{ color: COLORS.textMuted }}>nessuna</span>;
        return (
          <span style={{ display: 'inline-flex', flexDirection: 'column', gap: 2 }}>
            {qs[0].pdf_url ? (
              <button
                type="button"
                style={stileLink}
                data-testid={`apri-quietanza-${r._id}`}
                onClick={() => setPdf({
                  title: `Quietanza F24 del ${formatDateIT(r.data)}${r.protocollo ? ` · protocollo ${r.protocollo}` : ''}`,
                  fetchUrl: qs[0].pdf_url,
                })}
              >
                <FileText size={14} aria-hidden="true" /> Apri quietanza
              </button>
            ) : null}
            <span style={{ fontSize: 11.5, color: COLORS.textMuted }}>
              {r.protocollo ? `prot. ${r.protocollo}` : qs[0].filename}
              {qs.length > 1 && !r.pagamenti ? ` · ${qs.length} copie dello stesso pagamento` : ''}
            </span>
            {r.pagamenti ? r.pagamenti.map(p => (
              <span key={p.chiave} style={{ display: 'inline-flex', flexDirection: 'column' }}>
                <span style={{ fontSize: 11.5 }}>prot. {p.protocollo} · {formatEuro(p.importo)}</span>
                <Invio p={p} />
              </span>
            )) : <Invio p={r} />}
            {(r.ravvedimento_di || []).length > 0 && (
              <span style={{ display: 'inline-flex', flexDirection: 'column', gap: 2 }}>
                <Esito esito="verificare" data-testid={`ravvedimento-${r._id}`}>Ravvedimento</Esito>
                {r.ravvedimento_di.map(o => (
                  <button
                    key={o.f24_id}
                    type="button"
                    style={stileLink}
                    data-testid={`apri-originale-${o.f24_id}`}
                    onClick={() => setPdf({ title: 'F24 originale del commercialista', fetchUrl: o.pdf_url })}
                  >
                    <FileText size={14} aria-hidden="true" /> F24 del commercialista
                  </button>
                ))}
              </span>
            )}
          </span>
        );
      },
    },
    {
      key: 'addebito', label: 'Addebito in banca', ruoloCard: 'dettaglio',
      render: r => {
        const as = addebitiDi(r);
        const confermabile = GRUPPI_CONFERMABILI.includes(r._gruppo.chiave) && LIVELLI_CONFERMABILI.includes(r.livello);
        const f24Id = r.f24_id || quietanzeDi(r)[0]?.id;
        return (
          <span style={{ display: 'inline-flex', flexDirection: 'column', gap: 6 }}>
            <button type="button" style={stileLink} data-testid={`apri-dettaglio-${r._id}`} onClick={() => setDettaglio(r)}>
              {r.candidati?.length
                ? `${r.candidati.length} ${r.candidati.length === 1 ? 'candidato non confermato' : 'candidati non confermati'}`
                : as.length ? `${as.length} ${as.length === 1 ? 'movimento associato' : 'movimenti associati'}` : 'Nessun movimento associato'}
              <ArrowUpRight size={14} aria-hidden="true" />
            </button>
            {confermabile && f24Id && (
              <ConfermaAddebitoF24
                f24Id={f24Id}
                livello={r.livello}
                candidati={as}
                motivi={dati?.conferma?.motivi || {}}
                onConfermato={carica}
              />
            )}
          </span>
        );
      },
    },
    {
      key: 'motivazione', label: 'Perché', ruoloCard: 'dettaglio',
      render: r => <span style={{ fontSize: 12.5 }}>{r.motivazione || r.motivo || '—'}</span>,
    },
  ];

  const conteggi = dati?.conteggi || {};

  return (
    <section
      data-testid="riscontro-quietanze-banca"
      style={{ padding: 16, borderBottom: `1px solid ${COLORS.border}`, background: COLORS.card }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <h3 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: COLORS.text }}>
          Quietanze F24 e addebiti in banca{anno ? ` — ${anno}` : ''}
        </h3>
        <button
          type="button"
          onClick={carica}
          disabled={caricamento}
          style={{ ...stileChip(false), display: 'inline-flex', alignItems: 'center', gap: 6 }}
          data-testid="ricarica-riscontro-quietanze"
        >
          <RefreshCw size={14} aria-hidden="true" /> {caricamento ? 'Carico…' : 'Aggiorna'}
        </button>
      </div>
      <p style={{ margin: '6px 0 10px', fontSize: 12.5, color: COLORS.textMuted, maxWidth: 820 }}>
        Riscontrato (livello certo) solo con importo uguale al centesimo, addebito entro due giorni
        lavorativi e la «data incasso» della causale uguale alla data della quietanza. Senza quella
        data il livello è probabile; con una differenza sotto 5 euro è parziale; con più candidati
        si mostrano tutti e non se ne sceglie uno. Se l'estratto del periodo manca non si può dire
        che il pagamento manchi. Solo fatti e discrepanze, da verificare con il commercialista.
        {dati?.copertura_banca?.dal && (
          <> Estratto conto disponibile dal {formatDateIT(dati.copertura_banca.dal)} al{' '}
            {formatDateIT(dati.copertura_banca.al)}: le {conteggi.fuori_periodo_estratto || 0} quietanze
            fuori da queste date non si possono riscontrare.</>
        )}
      </p>

      {errore && (
        <div role="alert" style={{ color: COLORS.danger, fontWeight: 600, fontSize: 13, marginBottom: 8 }}>
          {errore}
        </div>
      )}

      {dati && (
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
          <button type="button" style={stileChip(gruppo === 'tutti')} onClick={() => setGruppo('tutti')}>
            Tutti
          </button>
          {GRUPPI.map(g => (
            <button
              key={g.chiave}
              type="button"
              style={stileChip(gruppo === g.chiave)}
              onClick={() => setGruppo(g.chiave)}
              data-testid={`filtro-${g.chiave}`}
            >
              {g.etichetta} ({(dati[g.chiave] || []).length})
            </button>
          ))}
        </div>
      )}

      {dati && righe.length === 0 && (
        <div style={{ padding: 20, color: COLORS.textMuted, fontSize: 13 }}>
          Niente da mostrare per questo filtro.
        </div>
      )}
      {righe.length > 0 && (
        <ListaAdattiva
          colonne={colonne}
          dati={righe}
          pageSize={200}
          chiave={r => r._id}
          resetKey={`${gruppo}:${anno}`}
          testId="lista-riscontro-quietanze"
          cardBreakpoint={1600}
        />
      )}

      {pdf && (
        <VisoreOriginale
          title={pdf.title}
          url={pdf.fetchUrl}
          documentType="f24"
          onClose={() => setPdf(null)}
        />
      )}
      {dettaglio && (
        <DettaglioF24
          riga={dettaglio}
          quietanzeDi={quietanzeDi}
          onClose={() => setDettaglio(null)}
          onApriQuietanza={(q, p) => {
            setDettaglio(null);
            setPdf({
              title: `Quietanza F24 del ${formatDateIT(p.data)}${p.protocollo ? ` · protocollo ${p.protocollo}` : ''}`,
              fetchUrl: q.pdf_url,
            });
          }}
        />
      )}
    </section>
  );
}
