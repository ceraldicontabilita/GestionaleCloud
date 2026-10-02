import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowUpRight, FileText, RefreshCw } from 'lucide-react';
import api from '../api';
import { COLORS, formatEuro, formatDateIT } from '../lib/utils';
import { Esito, ListaAdattiva } from './ds';
import { ROTTE_CONTROPARTITA } from './LinkContropartita';
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
  NESSUN_MATCH: 'Nessun match',
  MOVIMENTO_ORFANO: 'Movimento orfano',
};

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
    chiave: 'tributi_ripetuti', etichetta: 'Stesso tributo due volte',
    esito: 'intervento', testo: 'Versato due volte',
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

export default function RiscontroQuietanzeBanca({ anno }) {
  const [dati, setDati] = useState(null);
  const [errore, setErrore] = useState(null);
  const [caricamento, setCaricamento] = useState(false);
  const [gruppo, setGruppo] = useState('tutti');
  const [pdf, setPdf] = useState(null);

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
          <Esito esito={r._gruppo.esito} data-testid={`esito-${r._id}`}>{r._gruppo.testo}</Esito>
          {r.livello && (
            <span style={{ fontSize: 11.5, color: COLORS.textMuted }} data-testid={`livello-${r._id}`}>
              Livello: {LIVELLI[r.livello] || r.livello}
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
        if (!as.length) return <span style={{ color: COLORS.textMuted }}>nessuno</span>;
        const confermabile = GRUPPI_CONFERMABILI.includes(r._gruppo.chiave) && LIVELLI_CONFERMABILI.includes(r.livello);
        const f24Id = r.f24_id || quietanzeDi(r)[0]?.id;
        return (
          <span style={{ display: 'inline-flex', flexDirection: 'column', gap: 6 }}>
            {as.map(a => (
              <Link
                key={a.movimento_id}
                to={ROTTE_CONTROPARTITA.movimentoBanca(a.movimento_id)}
                style={stileLink}
                data-testid={`apri-addebito-${a.movimento_id}`}
              >
                {formatDateIT(a.data)} · {formatEuro(a.importo)} <ArrowUpRight size={14} aria-hidden="true" />
              </Link>
            ))}
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
    </section>
  );
}
