import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';

import api from '../api';
import { PageLayout } from '../components/PageLayout';
import { PageHeader } from '../components/ds/PageHeader';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { useIsMobile } from '../hooks/useData';

const denaro = (valore, valuta = 'EUR') => {
  const currency = String(valuta || 'EUR').toUpperCase();
  try {
    return new Intl.NumberFormat('it-IT', { style: 'currency', currency })
      .format(Number(valore || 0));
  } catch {
    return `${Number(valore || 0).toFixed(2)} ${currency}`;
  }
};

const dataIT = valore => {
  if (!valore) return '-';
  const data = new Date(valore);
  return Number.isNaN(data.getTime()) ? String(valore) : data.toLocaleDateString('it-IT');
};

const statoFatturaLabel = stato => ({
  associata_validata: 'Associata validata',
  da_rivalidare: 'Da rivalidare',
  non_associata: 'Non associata',
}[stato] || 'Da verificare');

const fonteLabel = fonte => (
  String(fonte.source_type || '').toLowerCase() === 'api'
    ? 'PayPal API'
    : (fonte.nome_file || fonte.tipo_documento || 'Fonte PayPal')
);

const compactId = valore => {
  const text = String(valore || '');
  return text.length > 10 ? `…${text.slice(-8)}` : (text || '-');
};

export default function RiconciliazionePaypal() {
  const { anno } = useAnnoGlobale();
  const isMobile = useIsMobile();
  const location = useLocation();
  const tabIniziale = new URLSearchParams(location.search).get('tab') || 'transazioni';
  const [tab, setTab] = useState(tabIniziale);
  const [loading, setLoading] = useState(true);
  const [errore, setErrore] = useState('');
  const [statoApi, setStatoApi] = useState(null);
  const [dashboard, setDashboard] = useState({});
  const [transazioni, setTransazioni] = useState([]);
  const [movimentiBanca, setMovimentiBanca] = useState([]);
  const [riepilogoBanca, setRiepilogoBanca] = useState({});
  const [fonti, setFonti] = useState([]);
  const transactionIdIniziale = new URLSearchParams(location.search).get('transaction_id') || '';
  const [ricerca, setRicerca] = useState(transactionIdIniziale);
  const [statoCollegamento, setStatoCollegamento] = useState('tutti');
  const [sincronizzazione, setSincronizzazione] = useState('in_attesa');
  const [riprocessamento, setRiprocessamento] = useState('');

  const caricaDati = useCallback(async () => {
    const paramsTx = new URLSearchParams({ limit: '1000', solo_pagamenti: 'true' });
    const paramsBanca = new URLSearchParams({ limit: '5000' });
    if (anno) {
      paramsTx.append('anno', anno);
      paramsBanca.append('anno', anno);
    }

    const risultati = await Promise.allSettled([
      api.get(`/api/paypal-statements/dashboard?anno=${anno}`),
      api.get(`/api/paypal-statements/transactions?${paramsTx}`),
      api.get(`/api/paypal-statements/report?anno=${anno}`),
      api.get(`/api/paypal-statements/statements?anno=${anno}`),
      api.get(`/api/paypal-statements/bank-movements?${paramsBanca}`),
      api.get('/api/paypal-api/status'),
    ]);

    const valore = (indice, fallback = {}) => (
      risultati[indice].status === 'fulfilled' ? (risultati[indice].value.data || fallback) : fallback
    );
    const datiDashboard = valore(0);
    const datiTransazioni = valore(1);
    const datiFonti = valore(3);
    const datiBanca = valore(4);

    setDashboard(datiDashboard);
    setTransazioni(Array.isArray(datiTransazioni.transactions) ? datiTransazioni.transactions : []);
    setFonti(Array.isArray(datiFonti.fonti) ? datiFonti.fonti : (Array.isArray(datiFonti.statements) ? datiFonti.statements : []));
    setMovimentiBanca(Array.isArray(datiBanca.movimenti) ? datiBanca.movimenti : []);
    setRiepilogoBanca(datiBanca);
    setStatoApi(valore(5, null));
    setErrore(risultati.some(risultato => risultato.status === 'rejected')
      ? 'Alcuni dati PayPal non sono stati caricati. Riprova senza considerare certi i valori mancanti.'
      : '');
  }, [anno]);

  useEffect(() => {
    let attivo = true;
    setLoading(true);
    const avvia = async () => {
      const status = await api.get('/api/paypal-api/status');
      if (status.data?.api_configurata) {
        setSincronizzazione('in_corso');
        await api.post('/api/paypal-api/sync/incremental');
        setSincronizzazione('completata');
      } else {
        setSincronizzazione('non_configurata');
      }
      // Applica sempre il motore end-to-end anche allo storico gia' presente:
      // la sincronizzazione API da sola non associa fattura e prova bancaria.
      const riprocessato = await api.post(`/api/paypal-statements/riprocessa?anno=${anno}`);
      const dopo = riprocessato.data?.collegamenti_dopo || {};
      setRiprocessamento(`Associate ${dopo.associate || 0} · finalizzate ${dopo.finalizzate || 0} · ambigue ${dopo.ambigue || 0}`);
      await caricaDati();
    };
    avvia()
      .catch(() => {
        if (attivo) {
          setSincronizzazione('errore');
          setErrore('Sincronizzazione PayPal non completata. I dati mostrati possono non essere aggiornati.');
          caricaDati().catch(() => {});
        }
      })
      .finally(() => { if (attivo) setLoading(false); });
    return () => { attivo = false; };
  }, [caricaDati]);

  const riprocessaStorico = async () => {
    setLoading(true);
    setRiprocessamento('Riprocessamento in corso…');
    try {
      const risposta = await api.post(`/api/paypal-statements/riprocessa?anno=${anno}`);
      const dopo = risposta.data?.collegamenti_dopo || {};
      setRiprocessamento(`Associate ${dopo.associate || 0} · finalizzate ${dopo.finalizzate || 0} · ambigue ${dopo.ambigue || 0}`);
      await caricaDati();
    } catch (e) {
      setRiprocessamento('Riprocessamento non riuscito');
      setErrore(e.response?.data?.detail || 'Riprocessamento PayPal non riuscito.');
    } finally {
      setLoading(false);
    }
  };

  const salvaDescrizione = async (tx, descrizione_utente) => {
    const id = tx.transaction_id || tx.id;
    await api.put(`/api/paypal-statements/transactions/${encodeURIComponent(id)}/descrizione`, { descrizione_utente });
    setTransazioni(prev => prev.map(item =>
      (item.transaction_id || item.id) === id ? { ...item, descrizione_utente } : item
    ));
  };

  const transazioniConBanca = useMemo(() => {
    const perId = new Map();
    movimentiBanca.forEach(movimento => {
      const id = String(movimento.paypal_transaction_id || '');
      if (id) perId.set(id, movimento);
    });
    return transazioni.map(tx => ({
      ...tx,
      bank_movement: perId.get(String(tx.transaction_id || tx.id || '')) || null,
    }));
  }, [transazioni, movimentiBanca]);

  const righe = useMemo(() => {
    const termine = ricerca.trim().toLowerCase();
    return transazioniConBanca.filter(tx => {
      const compatibileTesto = !termine || `${tx.transaction_id || tx.id || ''} ${tx.nome_controparte || ''} ${tx.descrizione || ''} ${tx.email_controparte || ''}`
        .toLowerCase().includes(termine);
      const compatibileStato = statoCollegamento === 'tutti' || tx.stato_collegamento_fattura === statoCollegamento;
      return compatibileTesto && compatibileStato;
    });
  }, [transazioniConBanca, ricerca, statoCollegamento]);

  const riconciliati = Number(riepilogoBanca.riconciliati ?? movimentiBanca.filter(m => m.riconciliato_paypal).length);
  const daVerificare = Number(riepilogoBanca.da_associare ?? Math.max(0, movimentiBanca.length - riconciliati));

  return (
    <PageLayout>
      <main style={{ maxWidth: 1400, margin: '0 auto', padding: 16 }}>
        <PageHeader
          title="PayPal"
          style={{ marginBottom: 16 }}
          pastiglie={[
            { etichetta: 'Transazioni', valore: String(dashboard.total_transactions ?? transazioni.length) },
            { etichetta: 'Movimenti banca', valore: String(dashboard.movimenti_banca_paypal ?? movimentiBanca.length) },
            { etichetta: 'Riconciliati', valore: String(riconciliati), tono: 'ok' },
            { etichetta: 'Da verificare', valore: String(daVerificare), tono: daVerificare > 0 ? 'attenzione' : 'ok' },
          ]}
          actions={(
            <>
          <span data-testid="paypal-sync-status" style={{ color: '#5f5c55', fontSize: 13 }}>
            {sincronizzazione === 'in_corso' ? 'Sincronizzazione incrementale…' :
              sincronizzazione === 'completata' ? `Aggiornato${statoApi?.ultimo_sync ? ` alle ${new Date(statoApi.ultimo_sync).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' })}` : ''}` :
                sincronizzazione === 'non_configurata' ? 'API non configurata' :
                  sincronizzazione === 'errore' ? 'Sincronizzazione da verificare' : 'Verifica aggiornamenti…'}
          </span>
          <button type="button" onClick={riprocessaStorico} disabled={loading} style={buttonStyle}>
            Riprocessa {anno}
          </button>
            </>
          )}
        />

        {riprocessamento && <div data-testid="paypal-reprocess-result" style={{ ...messageStyle, background: '#ecfdf5', color: '#166534' }}>{riprocessamento}</div>}

        {loading && <div role="status" style={messageStyle}>Caricamento dati PayPal...</div>}
        {errore && <div role="alert" style={{ ...messageStyle, background: '#fef2f2', color: '#991b1b' }}>{errore}</div>}
        {statoApi && !statoApi.api_configurata && (
          <div style={{ ...messageStyle, background: '#eef3ef', color: '#4c4a44' }}>
            API PayPal non configurata. Le transazioni già presenti restano consultabili e riconciliabili.
          </div>
        )}


        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
          {[
            ['transazioni', 'Transazioni'],
            ['estratti', 'Movimenti banca'],
            ['documenti', 'Fonti'],
          ].map(([id, label]) => (
            <button key={id} type="button" onClick={() => setTab(id)} style={{ ...buttonStyle, background: tab === id ? '#c15f3c' : '#fff', color: tab === id ? '#fff' : '#c15f3c' }}>{label}</button>
          ))}
        </div>

        {!loading && tab === 'transazioni' && (
          <>
            <div style={{ display: 'grid', gridTemplateColumns: 'minmax(240px, 1fr) minmax(190px, 260px)', gap: 10, marginBottom: 12 }}>
              <input value={ricerca} onChange={e => setRicerca(e.target.value)} placeholder="Cerca ID, controparte, descrizione o email" style={inputStyle} />
              <select aria-label="Stato collegamento fattura" value={statoCollegamento} onChange={e => setStatoCollegamento(e.target.value)} style={inputStyle}>
                <option value="tutti">Tutti gli stati</option>
                <option value="associata_validata">Associata validata</option>
                <option value="da_rivalidare">Da rivalidare</option>
                <option value="non_associata">Non associata</option>
              </select>
            </div>
            <TransactionCards righe={righe} onSaveDescription={salvaDescrizione} onLinked={() => caricaDati()} />
          </>
        )}

        {!loading && tab === 'estratti' && (
          <>
            <p style={{ color: '#7a776e' }}>Fonti duplicate unificate: <strong>{riepilogoBanca.duplicati_unificati || 0}</strong></p>
            {isMobile ? <BankCards righe={movimentiBanca} /> : <BankTable righe={movimentiBanca} />}
          </>
        )}

        {!loading && tab === 'documenti' && (
          isMobile ? <SourceCards fonti={fonti} /> : <SourceTable fonti={fonti} />
        )}
      </main>
    </PageLayout>
  );
}

function TransactionId({ value: id }) {
  if (!id) return <span>-</span>;
  return <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}><code title={id} style={{ overflowWrap: 'anywhere' }}>{id}</code><button type="button" aria-label={`Copia ID transazione ${id}`} title="Copia ID" onClick={() => navigator.clipboard?.writeText(String(id))} style={copyButton}>Copia</button></span>;
}

function TransactionAmount({ tx }) {
  const gross = denaro(tx.gross_amount ?? tx.importo ?? tx.lordo, tx.gross_currency || tx.currency);
  if (tx.settlement_amount != null && tx.settlement_currency) {
    return <span>{gross} → {denaro(tx.settlement_amount, tx.settlement_currency)}</span>;
  }
  return <span>{gross}</span>;
}

/**
 * Una card per ogni transazione, a qualsiasi larghezza: l'ID lungo e la descrizione
 * restano leggibili per intero invece di essere schiacciati in una colonna di tabella.
 */
function TransactionCards({ righe, onSaveDescription, onLinked }) {
  return (
    <div data-testid="paypal-transaction-cards" style={cards}>
      {righe.map(tx => <TransactionCard key={tx.transaction_id || tx.id} tx={tx} onSaveDescription={onSaveDescription} onLinked={onLinked} />)}
    </div>
  );
}

function Campo({ etichetta, children }) {
  return <div style={{ minWidth: 0 }}><div style={campoEtichetta}>{etichetta}</div><div style={{ fontSize: 14, overflowWrap: 'anywhere' }}>{children}</div></div>;
}

function TransactionCard({ tx, onSaveDescription, onLinked }) {
  const id = tx.transaction_id || tx.id;
  return (
    <article data-testid="paypal-transaction-card" style={card}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', alignItems: 'baseline' }}>
        <strong style={{ fontSize: 15 }}>{tx.nome_controparte || '-'}</strong>
        <strong style={{ fontVariantNumeric: 'tabular-nums' }}><TransactionAmount tx={tx} /></strong>
      </div>
      <div style={{ ...campi }}>
        <Campo etichetta="Data">{dataIT(tx.data || tx.date)}</Campo>
        <Campo etichetta="Descrizione PayPal">{tx.descrizione || '-'}</Campo>
        <Campo etichetta="Fattura">{tx.fattura_associata?.numero || tx.fattura_numero || '-'}</Campo>
        <Campo etichetta="Stato fattura">{statoFatturaLabel(tx.stato_collegamento_fattura)}</Campo>
        <Campo etichetta="ID transazione"><TransactionId value={id} /></Campo>
      </div>
      <UserDescription tx={tx} onSave={onSaveDescription} />
      <BankLink tx={tx} onLinked={onLinked} />
    </article>
  );
}

function BankLink({ tx, onLinked }) {
  const id = tx.transaction_id || tx.id;
  const [aperto, setAperto] = useState(false);
  const [stato, setStato] = useState({ caricamento: false, candidati: null, motivo: '', errore: '' });

  if (tx.bank_movement) {
    return (
      <div style={rigaBanca}>
        <span style={campoEtichetta}>Banca</span>
        <a href={`/prima-nota#sezione=banca&selected=${encodeURIComponent(tx.bank_movement.id)}`}>Prova in Prima Nota Banca · {compactId(tx.bank_movement.id)}</a>
      </div>
    );
  }

  const apri = async () => {
    setAperto(true);
    setStato({ caricamento: true, candidati: null, motivo: '', errore: '' });
    try {
      const r = await api.get(`/api/paypal-statements/transazione/${encodeURIComponent(id)}/candidati-banca`);
      setStato({ caricamento: false, candidati: r.data?.candidati || [], motivo: r.data?.motivo || '', errore: '' });
    } catch (e) {
      setStato({ caricamento: false, candidati: null, motivo: '', errore: e.response?.data?.detail || 'Ricerca dei movimenti non riuscita.' });
    }
  };

  const scegli = async movimento => {
    setStato(prev => ({ ...prev, errore: '' }));
    try {
      await api.post(`/api/paypal-statements/transazione/${encodeURIComponent(id)}/collega-banca`, { movimento_id: movimento.id });
      setAperto(false);
      onLinked?.(tx, movimento);
    } catch (e) {
      const detail = e.response?.data?.detail;
      setStato(prev => ({ ...prev, errore: (typeof detail === 'string' ? detail : detail?.messaggio) || 'Collegamento non riuscito.' }));
    }
  };

  return (
    <div style={{ display: 'grid', gap: 8 }}>
      <div style={rigaBanca}>
        <span style={campoEtichetta}>Banca</span>
        <span>Nessuna prova bancaria</span>
        {!aperto && <button type="button" onClick={apri} style={buttonStyle}>Collega a un addebito in banca</button>}
      </div>
      {aperto && (
        <div data-testid="paypal-candidati-banca" style={{ border: '1px solid #e6e3d9', borderRadius: 8, padding: 10, display: 'grid', gap: 8, background: '#faf9f5' }}>
          <div style={{ fontSize: 13, color: '#5f5c55' }}>
            Per i pagamenti PayPal addebitati sul conto e non su carta. Compaiono gli addebiti non ancora collegati con lo stesso importo al centesimo, vicini nel tempo.
          </div>
          {stato.caricamento && <span role="status">Cerco gli addebiti…</span>}
          {stato.errore && <span role="alert" style={{ color: '#b0362b' }}>{stato.errore}</span>}
          {stato.candidati && stato.candidati.length === 0 && <span>{stato.motivo || 'Nessun addebito in banca con questo importo nelle date vicine.'}</span>}
          {(stato.candidati || []).map(m => (
            <div key={m.id} style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', borderTop: '1px solid #e6e3d9', paddingTop: 8 }}>
              <span style={{ minWidth: 0, overflowWrap: 'anywhere' }}>
                <strong>{dataIT(m.data)}</strong> · {m.descrizione || '-'} · {denaro(m.importo)}
                {m.citata_paypal ? ' · cita PayPal' : ''}
              </span>
              <button type="button" onClick={() => scegli(m)} style={{ ...buttonStyle, background: '#c15f3c', color: '#fff' }}>Collega questo</button>
            </div>
          ))}
          <button type="button" onClick={() => setAperto(false)} style={{ ...buttonStyle, justifySelf: 'start' }}>Chiudi</button>
        </div>
      )}
    </div>
  );
}

function UserDescription({ tx, onSave }) {
  const [value, setValue] = useState(tx.descrizione_utente || '');
  const [saving, setSaving] = useState(false);
  useEffect(() => setValue(tx.descrizione_utente || ''), [tx.descrizione_utente]);
  const save = async () => {
    setSaving(true);
    try { await onSave(tx, value); } finally { setSaving(false); }
  };
  return <div style={{ display: 'grid', gap: 5 }}><textarea aria-label={`Descrizione utente ${tx.transaction_id || tx.id}`} value={value} onChange={e => setValue(e.target.value)} placeholder="Es. fattura al socio, pagata con carta bancaria" rows={2} style={{ ...inputStyle, minHeight: 54, resize: 'vertical' }} /><button type="button" onClick={save} disabled={saving || value === (tx.descrizione_utente || '')} style={{ ...copyButton, justifySelf: 'start' }}>{saving ? 'Salvo…' : 'Salva descrizione'}</button></div>;
}

function BankCards({ righe }) {
  return <div data-testid="paypal-bank-cards" style={cards}>{righe.map(riga => <article key={riga.id} style={card}><strong>{riga.descrizione || '-'}</strong><span>{dataIT(riga.data)} - {denaro(riga.importo, riga.valuta || 'EUR')}</span><span>{riga.riconciliato_paypal ? 'Riconciliato' : 'Da associare'}</span>{riga.paypal_transaction_id && <a href={`/riconciliazione/paypal?tab=transazioni&transaction_id=${encodeURIComponent(riga.paypal_transaction_id)}`}>Apri transazione {compactId(riga.paypal_transaction_id)}</a>}</article>)}</div>;
}

function BankTable({ righe }) {
  return <div data-testid="paypal-bank-table" style={tableWrap}><table style={table}><thead><tr>{['Data', 'Descrizione', 'Importo', 'Transazione', 'Stato'].map(t => <th key={t} style={th}>{t}</th>)}</tr></thead><tbody>{righe.map(riga => <tr key={riga.id}><td style={td}>{dataIT(riga.data)}</td><td style={td}>{riga.descrizione || '-'}</td><td style={td}>{denaro(riga.importo, riga.valuta || 'EUR')}</td><td style={td}>{riga.paypal_transaction_id ? <a href={`/riconciliazione/paypal?tab=transazioni&transaction_id=${encodeURIComponent(riga.paypal_transaction_id)}`}>{compactId(riga.paypal_transaction_id)}</a> : '-'}</td><td style={td}>{riga.riconciliato_paypal ? 'Riconciliato' : 'Da associare'}</td></tr>)}</tbody></table></div>;
}

function SourceDetails({ fonte }) {
  return <><strong>{fonteLabel(fonte)}</strong><span>{fonte.periodo_inizio || '-'} - {fonte.periodo_fine || '-'}</span><span>{fonte.totale_transazioni || 0} transazioni</span><span>{fonte.totale_pagamenti || 0} pagamenti</span>{fonte.documento_presente === false && <span>Nessun file: fonte API</span>}</>;
}

function SourceCards({ fonti }) {
  return <div data-testid="paypal-source-cards" style={cards}>{fonti.map(fonte => <article key={fonte.id} style={card}><SourceDetails fonte={fonte} /></article>)}</div>;
}

function SourceTable({ fonti }) {
  return <div data-testid="paypal-source-table" style={tableWrap}><table style={table}><thead><tr>{['Fonte', 'Periodo', 'Transazioni', 'Pagamenti', 'Documento'].map(t => <th key={t} style={th}>{t}</th>)}</tr></thead><tbody>{fonti.map(fonte => <tr key={fonte.id}><td style={td}>{fonteLabel(fonte)}</td><td style={td}>{fonte.periodo_inizio || '-'} - {fonte.periodo_fine || '-'}</td><td style={td}>{fonte.totale_transazioni || 0}</td><td style={td}>{fonte.totale_pagamenti || 0}</td><td style={td}>{fonte.documento_presente === false ? 'Nessun file: fonte API' : 'Documento acquisito'}</td></tr>)}</tbody></table></div>;
}

const card = { background: '#fff', border: '1px solid #e6e3d9', borderRadius: 10, padding: 14, display: 'grid', gap: 6 };
const cards = { display: 'grid', gap: 10 };
const campi = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: '8px 16px' };
const campoEtichetta = { fontSize: 11, fontWeight: 700, letterSpacing: '0.04em', textTransform: 'uppercase', color: '#7a776e' };
const rigaBanca = { display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center', fontSize: 14 };
const buttonStyle = { minHeight: 40, padding: '8px 14px', borderRadius: 8, border: '1px solid #d0ccbe', background: '#fff', cursor: 'pointer', fontWeight: 700 };
const inputStyle = { width: '100%', minHeight: 40, padding: '8px 10px', border: '1px solid #d0ccbe', borderRadius: 8 };
const messageStyle = { padding: 12, color: '#7a776e', borderRadius: 8, marginBottom: 12 };
const tableWrap = { overflowX: 'auto', background: '#fff', border: '1px solid #e6e3d9', borderRadius: 10 };
const table = { width: '100%', borderCollapse: 'collapse', minWidth: 760 };
const th = { padding: '10px 12px', textAlign: 'left', fontSize: 12, color: '#5f5c55', background: '#f6f4ee' };
const td = { padding: '10px 12px', fontSize: 13, color: '#2c2b28', borderTop: '1px solid #e6e3d9' };
const copyButton = { minHeight: 28, padding: '2px 6px', border: '1px solid #d0ccbe', borderRadius: 5, background: '#fff', cursor: 'pointer', fontSize: 11 };
