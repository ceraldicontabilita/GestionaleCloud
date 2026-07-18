import React, { useMemo, useState, useEffect } from 'react';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { formatEuroD, formatDateIT, useIsMobile } from '../lib/utils';
import { useHashState } from '../hooks/useHashState';
import { useConfirm } from '../components/ui/ConfirmDialog';
import ModalFattura from '../components/ModalFattura';

/**
 * PRIMA NOTA — ricostruita da zero (richiesta utente 17/07/2026).
 *
 * LOGICA UNICA, SEMPLICE:
 *  - Registro con SALDO PROGRESSIVO CONTINUO: riporto iniziale (modificabile)
 *    + ogni movimento aggiorna il saldo in ordine cronologico.
 *  - CASSA: si alimenta dal corrispettivo giornaliero — il TOTALE in DARE
 *    (entrata "Corrispettivi") e in AVERE la sola quota del PAGAMENTO
 *    ELETTRONICO (uscita "POS Verso Banca"). Più versamenti, prelevamenti
 *    e fatture pagate in contanti.
 *  - BANCA: solo operazioni del gestionale (Corrispettivi POS, Versamenti,
 *    Fatture, Utenze, F24, Stipendi, Assegni, PayPal). L'estratto conto
 *    NON viene sommato qui: sta nella pagina Riconciliazione.
 *  - A video dal più recente al meno recente; dentro la giornata prima
 *    l'entrata del corrispettivo, poi l'uscita POS.
 *
 * Niente card doppie, niente pannelli paralleli: 4 numeri (Riporto,
 * Entrate, Uscite, Saldo) e il registro.
 */

const BLU = '#0f2744';
const VERDE = '#16a34a';
const ROSSO = '#dc2626';
const MESI = ['Gen', 'Feb', 'Mar', 'Apr', 'Mag', 'Giu', 'Lug', 'Ago', 'Set', 'Ott', 'Nov', 'Dic'];
const PER_PAGINA = 50;

const CATEGORIE = {
  cassa: ['Corrispettivi', 'POS Verso Banca', 'Versamento Banca', 'Prelevamento Banca',
    'Fatture', 'Spese', 'Altro'],
  banca: ['Corrispettivi POS', 'Versamento Banca', 'Prelevamento Banca', 'Fatture', 'Utenze',
    'Pagamento PayPal', 'Rimborso', 'Stipendi', 'Commissioni bancarie', 'Assegni', 'F24', 'Altro'],
};

const eur = v => formatEuroD(v || 0);

function parseImportoIT(input) {
  const v = parseFloat(String(input ?? '').replace(/\./g, '').replace(',', '.'));
  return isNaN(v) ? null : v;
}

/* ------------------------------ card numero ------------------------------ */
function Card({ titolo, valore, colore, onEdit, testId }) {
  return (
    <div
      style={{
        background: 'white', borderRadius: 12, border: '1px solid #e2e8f0',
        borderLeft: `4px solid ${colore}`, padding: '10px 14px', minWidth: 0,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 6 }}>
        <span style={{ fontSize: 11, fontWeight: 700, color: '#64748b', textTransform: 'uppercase' }}>
          {titolo}
        </span>
        {onEdit && (
          <button
            onClick={onEdit}
            data-testid={testId}
            title="Modifica"
            style={{
              background: '#fef3c7', border: '1px solid #d97706', borderRadius: 6,
              padding: '2px 7px', fontSize: 12, cursor: 'pointer',
            }}
          >
            ✏️
          </button>
        )}
      </div>
      <div
        style={{
          fontSize: 17, fontWeight: 800, color: colore, whiteSpace: 'nowrap',
          fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
        }}
      >
        {eur(valore)}
      </div>
    </div>
  );
}

/* --------------------------- modal movimento --------------------------- */
function MovimentoModal({ tipo, movimento, onClose, onSaved }) {
  const oggi = new Date().toISOString().slice(0, 10);
  const [form, setForm] = useState({
    data: movimento?.data?.slice(0, 10) || oggi,
    tipo: movimento?.tipo || 'uscita',
    importo: movimento ? String(movimento.importo ?? '') : '',
    descrizione: movimento?.descrizione || '',
    categoria: movimento?.categoria || (tipo === 'cassa' ? 'Spese' : 'Altro'),
  });
  const [errore, setErrore] = useState('');
  const [saving, setSaving] = useState(false);

  const categorie = CATEGORIE[tipo].includes(form.categoria)
    ? CATEGORIE[tipo]
    : [form.categoria, ...CATEGORIE[tipo]];

  const salva = async () => {
    const importo = parseImportoIT(form.importo);
    if (!form.data || !importo || !form.descrizione.trim()) {
      setErrore('Servono data, importo e descrizione.');
      return;
    }
    setSaving(true);
    setErrore('');
    try {
      const body = { ...form, importo: Math.abs(importo) };
      if (movimento?.id) {
        await api.put(`/api/prima-nota/${tipo}/${movimento.id}`, body);
      } else {
        await api.post(`/api/prima-nota/${tipo}`, body);
      }
      onSaved();
    } catch (e) {
      setErrore(e.response?.data?.message || e.response?.data?.detail || e.message);
      setSaving(false);
    }
  };

  const campo = { width: '100%', padding: '9px 10px', border: '1px solid #d1d5db', borderRadius: 8, fontSize: 14, boxSizing: 'border-box' };
  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(15,39,68,0.55)', zIndex: 1000,
        display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 14,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{ background: 'white', borderRadius: 14, padding: 18, width: '100%', maxWidth: 420 }}
      >
        <h3 style={{ margin: '0 0 12px', color: BLU, fontSize: 16 }}>
          {movimento ? '📝 Modifica movimento' : '➕ Nuovo movimento'} — {tipo === 'cassa' ? 'Cassa' : 'Banca'}
        </h3>
        <div style={{ display: 'grid', gap: 10 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <input type="date" value={form.data} onChange={e => setForm({ ...form, data: e.target.value })} style={campo} />
            <select value={form.tipo} onChange={e => setForm({ ...form, tipo: e.target.value })} style={campo}>
              <option value="entrata">Entrata (Dare)</option>
              <option value="uscita">Uscita (Avere)</option>
            </select>
          </div>
          <input
            placeholder="Importo (es. 1.234,56)" inputMode="decimal" value={form.importo}
            onChange={e => setForm({ ...form, importo: e.target.value })} style={campo}
          />
          <input
            placeholder="Descrizione" value={form.descrizione}
            onChange={e => setForm({ ...form, descrizione: e.target.value })} style={campo}
          />
          <select value={form.categoria} onChange={e => setForm({ ...form, categoria: e.target.value })} style={campo}>
            {categorie.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
          {errore && <div style={{ color: ROSSO, fontSize: 13 }}>{errore}</div>}
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button onClick={onClose} style={{ padding: '9px 16px', borderRadius: 8, border: '1px solid #d1d5db', background: 'white', cursor: 'pointer' }}>
              Annulla
            </button>
            <button
              onClick={salva} disabled={saving}
              style={{ padding: '9px 18px', borderRadius: 8, border: 'none', background: BLU, color: 'white', fontWeight: 700, cursor: 'pointer', opacity: saving ? 0.6 : 1 }}
            >
              {saving ? '⏳…' : '💾 Salva'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------- registro ------------------------------- */
function Registro({ tipo, dati, mese, onRicarica, onModificaRiporto }) {
  const isMobile = useIsMobile();
  const confirm = useConfirm();
  const [pagina, setPagina] = useState(1);
  const [cerca, setCerca] = useState('');
  const [fCategoria, setFCategoria] = useState('');
  const [fTipo, setFTipo] = useState('');
  const [editing, setEditing] = useState(null);
  const [nuovo, setNuovo] = useState(false);
  const [fatturaView, setFatturaView] = useState(null);
  const [busy, setBusy] = useState(null);

  const movimenti = dati.movimenti || [];
  const riporto = dati.saldo_precedente || 0;

  useEffect(() => { setPagina(1); }, [mese, cerca, fCategoria, fTipo]);

  // ORDINE DENTRO LA GIORNATA (regola utente 17/07/2026): prima il
  // CORRISPETTIVO, poi l'uscita del POS, poi i pagamenti delle fatture,
  // per ultimo il versamento in banca. Vale sia a video sia per il
  // calcolo del saldo progressivo.
  const rango = m => {
    if (m.tipo === 'entrata') return m.categoria === 'Corrispettivi' ? 0 : 1;
    if (m.categoria === 'POS Verso Banca' || m.categoria === 'Corrispettivi POS') return 2;
    if (m.categoria === 'Versamento Banca') return 4;
    return 3; // fatture, utenze e altre uscite
  };

  // Ordine del registro A VIDEO: giorni dal più recente, dentro la
  // giornata corrispettivo → POS → fatture → versamento.
  const ordineVideo = (a, b) =>
    (b.data || '').localeCompare(a.data || '') ||
    rango(a) - rango(b) ||
    (a.created_at || '').localeCompare(b.created_at || '');

  // SALDO PROGRESSIVO CONTINUO nell'ORDINE DEL REGISTRO (regola utente
  // 18/07/2026, esempio 20-21/01): si parte dal riporto in fondo e si
  // sale riga per riga — OGNI riga vale la riga sotto ± il suo importo,
  // anche a cavallo dei giorni. La somma è commutativa, quindi i totali
  // di giornata e dell'anno non cambiano; cambia solo il punto in cui
  // ogni singola riga "fotografa" il saldo, che ora segue la lettura.
  // Sempre su TUTTO l'anno, mai sulla selezione filtrata.
  const saldoDi = useMemo(() => {
    const mappa = {};
    let saldo = riporto;
    const lista = [...movimenti].sort(ordineVideo);
    for (let i = lista.length - 1; i >= 0; i--) {
      const m = lista[i];
      saldo += (m.tipo === 'entrata' ? 1 : -1) * Math.abs(m.importo || 0);
      mappa[m.id] = saldo;
    }
    return mappa;
  }, [movimenti, riporto]);

  // Filtri di ricerca + ordine A VIDEO: dal più recente al meno recente,
  // dentro la giornata prima l'entrata (corrispettivo) poi l'uscita (POS).
  const visibili = useMemo(() => {
    let lista = movimenti;
    if (mese !== null) lista = lista.filter(m => parseInt((m.data || '').slice(5, 7), 10) === mese + 1);
    if (fCategoria) lista = lista.filter(m => m.categoria === fCategoria);
    if (fTipo) lista = lista.filter(m => m.tipo === fTipo);
    if (cerca.trim()) {
      const q = cerca.trim().toLowerCase();
      lista = lista.filter(m =>
        (m.descrizione || '').toLowerCase().includes(q) ||
        (m.numero_fattura || '').toLowerCase().includes(q) ||
        String(m.importo || '').includes(q));
    }
    return [...lista].sort(ordineVideo);
  }, [movimenti, mese, fCategoria, fTipo, cerca]);

  const totPagine = Math.max(1, Math.ceil(visibili.length / PER_PAGINA));
  const paginaCorrente = Math.min(pagina, totPagine);
  const righe = visibili.slice((paginaCorrente - 1) * PER_PAGINA, paginaCorrente * PER_PAGINA);
  const ultimaPagina = paginaCorrente === totPagine;

  const categorieUsate = useMemo(
    () => [...new Set(movimenti.map(m => m.categoria).filter(Boolean))].sort(),
    [movimenti]);

  const elimina = async mov => {
    const ok = await confirm({
      title: 'Eliminare il movimento?',
      message: `${formatDateIT(mov.data)} — ${mov.descrizione} (${eur(mov.importo)})`,
      confirmText: 'Elimina', danger: true,
    });
    if (!ok) return;
    setBusy(mov.id);
    try {
      try {
        await api.delete(`/api/prima-nota/${tipo}/${mov.id}`);
      } catch (e) {
        if (e.response?.status === 409) await api.delete(`/api/prima-nota/${tipo}/${mov.id}?force=true`);
        else throw e;
      }
      onRicarica();
    } finally {
      setBusy(null);
    }
  };

  const sposta = async mov => {
    const verso = tipo === 'cassa' ? 'banca' : 'cassa';
    setBusy(mov.id);
    try {
      await api.post('/api/prima-nota/sposta-movimento', { movimento_id: mov.id, da: tipo, a: verso });
      onRicarica();
    } finally {
      setBusy(null);
    }
  };

  const badgeDocumento = mov => {
    if (mov.fattura_id) {
      return (
        <button
          onClick={() => setFatturaView({ id: mov.fattura_id, numero: mov.numero_fattura })}
          style={{ background: '#3b82f6', color: 'white', border: 'none', borderRadius: 6, padding: '4px 9px', fontSize: 11, fontWeight: 700, cursor: 'pointer' }}
        >
          Fattura
        </button>
      );
    }
    if (mov.corrispettivo_id || mov.xml_filename) {
      const href = mov.corrispettivo_id
        ? `/api/corrispettivi/${mov.corrispettivo_id}/view`
        : `/api/corrispettivi/view-by-filename?filename=${encodeURIComponent(mov.xml_filename)}`;
      return (
        <a
          href={href} target="_blank" rel="noopener noreferrer"
          style={{ background: VERDE, color: 'white', borderRadius: 6, padding: '4px 9px', fontSize: 11, fontWeight: 700, textDecoration: 'none', whiteSpace: 'nowrap' }}
        >
          🧾 Corrisp.
        </a>
      );
    }
    return null;
  };

  const bottoniRiga = mov => (
    <span style={{ display: 'inline-flex', gap: 5, whiteSpace: 'nowrap' }}>
      <button
        onClick={() => sposta(mov)} disabled={busy === mov.id}
        title={tipo === 'cassa' ? 'Sposta in banca' : 'Sposta in cassa'}
        style={{ background: BLU, color: 'white', border: 'none', borderRadius: 6, padding: '5px 8px', fontSize: 12, cursor: 'pointer', opacity: busy === mov.id ? 0.5 : 1 }}
      >
        {tipo === 'cassa' ? '🏦' : '💵'}
      </button>
      <button
        onClick={() => setEditing(mov)}
        title="Modifica"
        style={{ background: '#f1f5f9', border: '1px solid #e2e8f0', borderRadius: 6, padding: '5px 8px', fontSize: 12, cursor: 'pointer' }}
      >
        📝
      </button>
      <button
        onClick={() => elimina(mov)} disabled={busy === mov.id}
        title="Elimina"
        style={{ background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 6, padding: '5px 8px', fontSize: 12, cursor: 'pointer', opacity: busy === mov.id ? 0.5 : 1 }}
      >
        🗑️
      </button>
    </span>
  );

  const rigaRiporto = (
    <div
      data-testid={`riga-saldo-iniziale-${tipo}`}
      style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8,
        padding: '10px 14px', background: '#fffbeb', border: '1px solid #d97706',
        borderRadius: 10, marginTop: 8,
      }}
    >
      <span style={{ fontSize: 13, fontWeight: 700, color: '#92400e' }}>
        🏁 Saldo iniziale al 01/01 (riporto)
      </span>
      <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontWeight: 800, fontFamily: 'ui-monospace, Menlo, monospace', color: riporto >= 0 ? BLU : ROSSO }}>
          {eur(riporto)}
        </span>
        <button
          onClick={onModificaRiporto}
          data-testid={`modifica-saldo-iniziale-${tipo}`}
          style={{ background: '#fef3c7', border: '1px solid #d97706', borderRadius: 7, padding: '4px 9px', fontSize: 12, cursor: 'pointer' }}
        >
          ✏️
        </button>
      </span>
    </div>
  );

  // Card giornaliere (mobile) raggruppate per data
  const gruppiGiorno = useMemo(() => {
    const gruppi = [];
    righe.forEach(m => {
      const ultimo = gruppi[gruppi.length - 1];
      if (!ultimo || ultimo.data !== m.data) gruppi.push({ data: m.data, righe: [] });
      gruppi[gruppi.length - 1].righe.push(m);
    });
    return gruppi;
  }, [righe]);

  const stileInput = { padding: '8px 10px', border: '1px solid #d1d5db', borderRadius: 8, fontSize: 13, minWidth: 0 };

  return (
    <div>
      {/* filtri + nuovo movimento */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', margin: '12px 0' }}>
        <input
          placeholder="🔍 Cerca…" value={cerca} onChange={e => setCerca(e.target.value)}
          style={{ ...stileInput, flex: '1 1 140px' }}
        />
        <select value={fCategoria} onChange={e => setFCategoria(e.target.value)} style={stileInput}>
          <option value="">Tutte le categorie</option>
          {categorieUsate.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <select value={fTipo} onChange={e => setFTipo(e.target.value)} style={stileInput}>
          <option value="">Dare + Avere</option>
          <option value="entrata">Solo Dare ↑</option>
          <option value="uscita">Solo Avere ↓</option>
        </select>
        <button
          onClick={() => setNuovo(true)}
          style={{ background: BLU, color: 'white', border: 'none', borderRadius: 8, padding: '8px 14px', fontSize: 13, fontWeight: 700, cursor: 'pointer' }}
        >
          ➕ Nuovo
        </button>
      </div>

      {/* paginazione */}
      {totPagine > 1 && (
        <div
          style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            background: BLU, color: 'white', borderRadius: 10, padding: '8px 12px', marginBottom: 10, fontSize: 13,
          }}
        >
          <span>📄 {paginaCorrente}/{totPagine} — {visibili.length} movimenti</span>
          <span style={{ display: 'flex', gap: 4 }}>
            {[['«', 1], ['‹', paginaCorrente - 1], ['›', paginaCorrente + 1], ['»', totPagine]].map(([s, p]) => (
              <button
                key={s} onClick={() => setPagina(Math.min(totPagine, Math.max(1, p)))}
                style={{ border: 'none', borderRadius: 6, padding: '4px 10px', cursor: 'pointer' }}
              >
                {s}
              </button>
            ))}
          </span>
        </div>
      )}

      {righe.length === 0 && (
        <div style={{ padding: 30, textAlign: 'center', color: '#6b7280', background: 'white', borderRadius: 12, border: '1px solid #e2e8f0' }}>
          Nessun movimento{mese !== null ? ` a ${MESI[mese]}` : ''}.
        </div>
      )}

      {isMobile ? (
        /* ------------------- MOBILE: card per giornata ------------------- */
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {gruppiGiorno.map(g => {
            const netto = g.righe.reduce((s, m) => s + (m.tipo === 'entrata' ? 1 : -1) * Math.abs(m.importo || 0), 0);
            return (
              <div key={g.data} style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
                <div
                  style={{
                    display: 'flex', justifyContent: 'space-between', gap: 8, padding: '6px 11px',
                    background: BLU, color: 'white', borderRadius: 8, fontSize: 12.5, fontWeight: 700,
                  }}
                >
                  <span>📅 {formatDateIT(g.data)}</span>
                  <span style={{ fontFamily: 'ui-monospace, Menlo, monospace', color: netto >= 0 ? '#86efac' : '#fca5a5' }}>
                    {netto >= 0 ? '+' : ''}{eur(netto)}
                  </span>
                </div>
                {g.righe.map(m => (
                  <div
                    key={m.id}
                    data-testid={`movimento-card-${m.id}`}
                    style={{
                      background: 'white', borderRadius: 11, border: '1px solid #e2e8f0',
                      borderLeft: `4px solid ${m.tipo === 'entrata' ? VERDE : ROSSO}`, padding: '9px 12px',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'flex-start' }}>
                      <span style={{ fontSize: 11, background: '#f1f5f9', borderRadius: 5, padding: '2px 7px', fontWeight: 600 }}>
                        {m.categoria || '—'}
                      </span>
                      <span
                        style={{
                          fontWeight: 800, whiteSpace: 'nowrap', fontFamily: 'ui-monospace, Menlo, monospace',
                          color: m.tipo === 'entrata' ? VERDE : ROSSO,
                        }}
                      >
                        {m.tipo === 'entrata' ? '+' : '−'}{eur(Math.abs(m.importo))}
                      </span>
                    </div>
                    <div style={{ fontSize: 12.5, color: '#334155', margin: '5px 0', wordBreak: 'break-word' }}>
                      {m.descrizione || '—'}
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                      <span style={{ fontSize: 11.5, color: '#64748b' }}>
                        Saldo:{' '}
                        <b style={{ color: (saldoDi[m.id] ?? 0) >= 0 ? VERDE : ROSSO, fontFamily: 'ui-monospace, Menlo, monospace' }}>
                          {eur(saldoDi[m.id])}
                        </b>
                      </span>
                      <span style={{ display: 'flex', gap: 5, alignItems: 'center' }}>
                        {badgeDocumento(m)}
                        {bottoniRiga(m)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            );
          })}
          {ultimaPagina && rigaRiporto}
        </div>
      ) : (
        /* ------------------------ DESKTOP: tabella ----------------------- */
        <div style={{ background: 'white', borderRadius: 12, border: '1px solid #e2e8f0', overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
            <thead>
              <tr style={{ background: '#f8fafc', borderBottom: '2px solid #e2e8f0' }}>
                {['Data', 'Categoria', 'Descrizione', 'Dare', 'Avere', 'Saldo', 'Doc.', 'Azioni'].map((h, i) => (
                  <th
                    key={h}
                    style={{
                      padding: '9px 10px', fontSize: 11, color: '#64748b', textTransform: 'uppercase',
                      textAlign: i >= 3 && i <= 5 ? 'right' : i >= 6 ? 'center' : 'left',
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {righe.map((m, i) => (
                <tr
                  key={m.id}
                  data-testid={`movimento-row-${m.id}`}
                  style={{ borderBottom: '1px solid #f1f5f9', background: i % 2 ? '#f8fafc' : 'white' }}
                >
                  <td style={{ padding: '7px 10px', fontFamily: 'monospace', whiteSpace: 'nowrap' }}>{formatDateIT(m.data)}</td>
                  <td style={{ padding: '7px 10px' }}>
                    <span style={{ background: '#f1f5f9', borderRadius: 5, padding: '2px 7px', fontSize: 11 }}>{m.categoria || '—'}</span>
                  </td>
                  <td style={{ padding: '7px 10px', maxWidth: 420, wordBreak: 'break-word' }}>{m.descrizione || '—'}</td>
                  <td style={{ padding: '7px 10px', textAlign: 'right', color: VERDE, fontWeight: m.tipo === 'entrata' ? 700 : 400, fontFamily: 'ui-monospace, Menlo, monospace', whiteSpace: 'nowrap' }}>
                    {m.tipo === 'entrata' ? eur(m.importo) : '—'}
                  </td>
                  <td style={{ padding: '7px 10px', textAlign: 'right', color: ROSSO, fontWeight: m.tipo === 'uscita' ? 700 : 400, fontFamily: 'ui-monospace, Menlo, monospace', whiteSpace: 'nowrap' }}>
                    {m.tipo === 'uscita' ? eur(m.importo) : '—'}
                  </td>
                  <td style={{ padding: '7px 10px', textAlign: 'right', fontWeight: 800, color: (saldoDi[m.id] ?? 0) >= 0 ? VERDE : ROSSO, fontFamily: 'ui-monospace, Menlo, monospace', whiteSpace: 'nowrap' }}>
                    {eur(saldoDi[m.id])}
                  </td>
                  <td style={{ padding: '7px 10px', textAlign: 'center' }}>{badgeDocumento(m) || '—'}</td>
                  <td style={{ padding: '7px 10px', textAlign: 'center' }}>{bottoniRiga(m)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {ultimaPagina && <div style={{ padding: '0 10px 10px' }}>{rigaRiporto}</div>}
        </div>
      )}

      {(nuovo || editing) && (
        <MovimentoModal
          tipo={tipo}
          movimento={editing}
          onClose={() => { setNuovo(false); setEditing(null); }}
          onSaved={() => { setNuovo(false); setEditing(null); onRicarica(); }}
        />
      )}
      {fatturaView && (
        <ModalFattura fatturaId={fatturaView.id} numero={fatturaView.numero} onClose={() => setFatturaView(null)} />
      )}
    </div>
  );
}

/* ------------------------------ provvisori ------------------------------ */
function Provvisori({ provvisori, attese, onRicarica }) {
  const [busy, setBusy] = useState(null);
  const [parziale, setParziale] = useState(null);
  const [importoCassa, setImportoCassa] = useState('');
  const [errore, setErrore] = useState('');

  const conferma = async (p, metodo) => {
    setBusy(p.fattura_id);
    setErrore('');
    try {
      await api.post('/api/prima-nota/provvisori/conferma', { fattura_id: p.fattura_id, metodo });
      onRicarica();
    } catch (e) {
      setErrore(e.response?.data?.message || e.message);
    } finally {
      setBusy(null);
    }
  };

  const confermaParziale = async () => {
    const cassa = parseImportoIT(importoCassa);
    const totale = parziale?.importo || 0;
    if (cassa === null || cassa <= 0 || cassa >= totale) {
      setErrore(`L'importo cassa deve stare tra 0 e ${eur(totale)}.`);
      return;
    }
    setBusy(parziale.fattura_id);
    try {
      await api.post('/api/pagamenti/registra', {
        fattura_id: parziale.fattura_id, metodo: 'misto', importo_cassa: cassa, importo_banca: totale - cassa,
      });
      setParziale(null);
      onRicarica();
    } catch (e) {
      setErrore(e.response?.data?.message || e.message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 12 }}>
      {errore && <div style={{ color: ROSSO, fontSize: 13 }}>{errore}</div>}
      {provvisori.length === 0 && (
        <div style={{ padding: 26, textAlign: 'center', color: '#6b7280', background: 'white', borderRadius: 12, border: '1px solid #e2e8f0' }}>
          Nessuna fattura in attesa di divisione cassa/banca.
        </div>
      )}
      {provvisori.map(p => (
        <div
          key={p.fattura_id || p.id}
          style={{ background: 'white', borderRadius: 11, border: '1px solid #e2e8f0', borderLeft: '4px solid #d97706', padding: '10px 13px' }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontWeight: 700, fontSize: 13.5, color: BLU }}>{p.fornitore || p.supplier_name || '—'}</div>
              <div style={{ fontSize: 12, color: '#64748b' }}>
                Fatt. {p.numero_fattura || p.invoice_number || '—'} del {formatDateIT(p.data || p.invoice_date)}
                {p.suggerimento === 'sospesa' && ' — ⏸ sospesa'}
              </div>
            </div>
            <div style={{ fontWeight: 800, fontFamily: 'ui-monospace, Menlo, monospace', color: BLU }}>{eur(p.importo)}</div>
          </div>
          <div style={{ display: 'flex', gap: 6, marginTop: 9, flexWrap: 'wrap' }}>
            {[['cassa', '💵 Cassa', VERDE], ['banca', '🏦 Banca', BLU]].map(([m, label, col]) => (
              <button
                key={m} onClick={() => conferma(p, m)} disabled={busy === p.fattura_id}
                style={{ background: col, color: 'white', border: 'none', borderRadius: 8, padding: '7px 13px', fontSize: 12.5, fontWeight: 700, cursor: 'pointer', opacity: busy === p.fattura_id ? 0.5 : 1 }}
              >
                {label}
              </button>
            ))}
            <button
              onClick={() => { setParziale(p); setImportoCassa(''); setErrore(''); }}
              style={{ background: '#f1f5f9', border: '1px solid #e2e8f0', borderRadius: 8, padding: '7px 13px', fontSize: 12.5, fontWeight: 700, cursor: 'pointer' }}
            >
              ✂️ Parziale
            </button>
            {p.suggerimento !== 'sospesa' && (
              <button
                onClick={() => conferma(p, 'sospesa')}
                style={{ background: '#fef3c7', border: '1px solid #d97706', borderRadius: 8, padding: '7px 13px', fontSize: 12.5, cursor: 'pointer' }}
              >
                ⏸ Sospendi
              </button>
            )}
          </div>
        </div>
      ))}

      {attese.length > 0 && (
        <div style={{ marginTop: 8 }}>
          <div style={{ fontSize: 12.5, fontWeight: 700, color: '#64748b', margin: '4px 0 8px' }}>
            📩 Fatture annunciate via email, XML in arrivo ({attese.length})
          </div>
          {attese.map(a => (
            <div
              key={a.id}
              style={{ background: 'white', borderRadius: 10, border: '1px dashed #cbd5e1', padding: '8px 12px', marginBottom: 6, display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: 12.5 }}
            >
              <span style={{ minWidth: 0 }}>{a.fornitore || '—'} — {a.numero_fattura || 's.n.'}</span>
              <b style={{ fontFamily: 'ui-monospace, Menlo, monospace' }}>{eur(a.importo)}</b>
            </div>
          ))}
        </div>
      )}

      {parziale && (
        <div
          onClick={() => setParziale(null)}
          style={{ position: 'fixed', inset: 0, background: 'rgba(15,39,68,0.55)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 14 }}
        >
          <div onClick={e => e.stopPropagation()} style={{ background: 'white', borderRadius: 14, padding: 18, width: '100%', maxWidth: 400 }}>
            <h3 style={{ margin: '0 0 6px', fontSize: 15, color: BLU }}>✂️ Pagamento parziale</h3>
            <div style={{ fontSize: 13, color: '#475569', marginBottom: 10 }}>
              {parziale.fornitore || '—'} — totale <b>{eur(parziale.importo)}</b>
            </div>
            <input
              placeholder="Quota pagata in CONTANTI (es. 100,00)" inputMode="decimal" value={importoCassa}
              onChange={e => setImportoCassa(e.target.value)}
              style={{ width: '100%', padding: '9px 10px', border: '1px solid #d1d5db', borderRadius: 8, boxSizing: 'border-box', marginBottom: 8 }}
            />
            {parseImportoIT(importoCassa) !== null && (
              <div style={{ fontSize: 12.5, color: '#475569', marginBottom: 8 }}>
                💵 Cassa {eur(parseImportoIT(importoCassa))} + 🏦 Banca {eur((parziale.importo || 0) - parseImportoIT(importoCassa))}
              </div>
            )}
            {errore && <div style={{ color: ROSSO, fontSize: 13, marginBottom: 8 }}>{errore}</div>}
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button onClick={() => setParziale(null)} style={{ padding: '8px 14px', borderRadius: 8, border: '1px solid #d1d5db', background: 'white', cursor: 'pointer' }}>
                Annulla
              </button>
              <button onClick={confermaParziale} style={{ padding: '8px 16px', borderRadius: 8, border: 'none', background: BLU, color: 'white', fontWeight: 700, cursor: 'pointer' }}>
                Conferma
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* -------------------------------- pagina -------------------------------- */
export default function PrimaNota() {
  const { anno } = useAnnoGlobale();
  const [hs, setHs] = useHashState({ sezione: 'cassa', mese: '' });
  const sezione = hs.sezione || 'cassa';
  const mese = hs.mese === '' ? null : parseInt(hs.mese, 10);

  const [cassa, setCassa] = useState({ movimenti: [] });
  const [banca, setBanca] = useState({ movimenti: [] });
  const [provvisori, setProvvisori] = useState([]);
  const [attese, setAttese] = useState([]);
  const [loading, setLoading] = useState(true);

  const carica = async () => {
    setLoading(true);
    try {
      const params = `anno=${anno}&limit=10000`;
      const [c, b, p, a] = await Promise.all([
        api.get(`/api/prima-nota/cassa?${params}`),
        api.get(`/api/prima-nota/banca?${params}`),
        api.get(`/api/prima-nota/provvisori?anno=${anno}`).catch(() => ({ data: {} })),
        api.get(`/api/prima-nota/attese?anno=${anno}`).catch(() => ({ data: {} })),
      ]);
      setCassa(c.data || { movimenti: [] });
      setBanca(b.data || { movimenti: [] });
      setProvvisori(p.data?.provvisori || []);
      setAttese(a.data?.attese || []);
    } catch (e) {
      console.error('Prima nota:', e);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { carica(); }, [anno]);

  // Modale dedicata (niente window.prompt: su telefono/PWA è inaffidabile)
  const [riportoModal, setRiportoModal] = useState(null); // {tipo}
  const [riportoInput, setRiportoInput] = useState('');
  const [riportoErr, setRiportoErr] = useState('');
  const [riportoSaving, setRiportoSaving] = useState(false);

  const modificaRiporto = tipo => {
    const attuale = (tipo === 'cassa' ? cassa : banca).saldo_precedente || 0;
    setRiportoInput(attuale ? String(attuale).replace('.', ',') : '');
    setRiportoErr('');
    setRiportoModal({ tipo });
  };

  const salvaRiporto = async () => {
    const importo = parseImportoIT(riportoInput);
    if (importo === null) {
      setRiportoErr('Scrivi un importo valido, es. 12.500,00');
      return;
    }
    setRiportoSaving(true);
    try {
      await api.put('/api/prima-nota/saldo-iniziale', { tipo: riportoModal.tipo, anno, importo });
      setRiportoModal(null);
      carica();
    } catch (e) {
      setRiportoErr(e.response?.data?.message || e.response?.data?.detail || e.message);
    } finally {
      setRiportoSaving(false);
    }
  };

  const datiAttivi = sezione === 'banca' ? banca : cassa;
  const saldoFinale = (datiAttivi.saldo_precedente || 0) +
    (datiAttivi.movimenti || []).reduce((s, m) => s + (m.tipo === 'entrata' ? 1 : -1) * Math.abs(m.importo || 0), 0);

  const tab = (chiave, etichetta) => (
    <button
      key={chiave}
      onClick={() => setHs('sezione', chiave)}
      style={{
        flex: 1, padding: '11px 8px', borderRadius: 10, fontSize: 13.5, fontWeight: 700, cursor: 'pointer',
        background: sezione === chiave ? BLU : 'white',
        color: sezione === chiave ? 'white' : '#64748b',
        border: `1px solid ${sezione === chiave ? BLU : '#e2e8f0'}`,
        whiteSpace: 'nowrap',
      }}
    >
      {etichetta}
    </button>
  );

  return (
    <div style={{ padding: '14px clamp(10px, 3vw, 28px)', maxWidth: 1280, margin: '0 auto' }}>
      <div style={{ display: 'flex', gap: 8, marginBottom: 14 }}>
        {tab('cassa', `💵 Cassa ${anno}`)}
        {tab('banca', `🏦 Banca ${anno}`)}
        {tab('provvisori', `⚠️ Provvisori (${provvisori.length})`)}
      </div>

      {loading && (
        <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>⏳ Caricamento…</div>
      )}

      {!loading && sezione === 'provvisori' && (
        <Provvisori provvisori={provvisori} attese={attese} onRicarica={carica} />
      )}

      {!loading && sezione !== 'provvisori' && (
        <>
          {/* 4 numeri, nessuna card doppia */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 10 }}>
            <Card
              titolo="Riporto 01/01" valore={datiAttivi.saldo_precedente} colore="#6b7280"
              onEdit={() => modificaRiporto(sezione)} testId={`modifica-riporto-${sezione}`}
            />
            <Card titolo={`Entrate (Dare) ${anno}`} valore={datiAttivi.totale_entrate} colore={VERDE} />
            <Card titolo={`Uscite (Avere) ${anno}`} valore={datiAttivi.totale_uscite} colore={ROSSO} />
            <Card titolo="Saldo" valore={saldoFinale} colore={saldoFinale >= 0 ? BLU : ROSSO} />
          </div>

          {/* mese */}
          <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', margin: '12px 0 0' }}>
            <button
              onClick={() => setHs('mese', '')}
              style={{
                padding: '7px 12px', borderRadius: 7, border: 'none', cursor: 'pointer', fontSize: 12.5,
                background: mese === null ? BLU : '#f1f5f9', color: mese === null ? 'white' : '#374151',
                fontWeight: mese === null ? 700 : 400,
              }}
            >
              Tutti
            </button>
            {MESI.map((m, i) => (
              <button
                key={m}
                onClick={() => setHs('mese', String(i))}
                style={{
                  padding: '7px 10px', borderRadius: 7, border: 'none', cursor: 'pointer', fontSize: 12.5,
                  background: mese === i ? BLU : '#f1f5f9', color: mese === i ? 'white' : '#374151',
                  fontWeight: mese === i ? 700 : 400,
                }}
              >
                {m}
              </button>
            ))}
          </div>

          <Registro
            tipo={sezione}
            dati={datiAttivi}
            mese={mese}
            onRicarica={carica}
            onModificaRiporto={() => modificaRiporto(sezione)}
          />
        </>
      )}

      {riportoModal && (
        <div
          onClick={() => setRiportoModal(null)}
          style={{
            position: 'fixed', inset: 0, background: 'rgba(15,39,68,0.55)', zIndex: 1000,
            display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 14,
          }}
        >
          <div onClick={e => e.stopPropagation()} style={{ background: 'white', borderRadius: 14, padding: 18, width: '100%', maxWidth: 400 }}>
            <h3 style={{ margin: '0 0 6px', fontSize: 15, color: BLU }}>
              🏁 Saldo iniziale {riportoModal.tipo === 'cassa' ? 'Cassa' : 'Banca'} al 01/01/{anno}
            </h3>
            <div style={{ fontSize: 12.5, color: '#64748b', marginBottom: 10 }}>
              È il riporto dell'anno precedente: il saldo che avevi in {riportoModal.tipo} a fine {anno - 1}.
              Tutti i saldi progressivi ripartono da qui.
            </div>
            <input
              placeholder="es. 12.500,00" inputMode="decimal" value={riportoInput} autoFocus
              onChange={e => setRiportoInput(e.target.value)}
              style={{ width: '100%', padding: '11px 12px', border: '1px solid #d1d5db', borderRadius: 8, fontSize: 16, boxSizing: 'border-box', marginBottom: 8 }}
            />
            {riportoErr && <div style={{ color: ROSSO, fontSize: 13, marginBottom: 8 }}>{riportoErr}</div>}
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button onClick={() => setRiportoModal(null)} style={{ padding: '9px 14px', borderRadius: 8, border: '1px solid #d1d5db', background: 'white', cursor: 'pointer' }}>
                Annulla
              </button>
              <button
                onClick={salvaRiporto} disabled={riportoSaving}
                style={{ padding: '9px 18px', borderRadius: 8, border: 'none', background: BLU, color: 'white', fontWeight: 700, cursor: 'pointer', opacity: riportoSaving ? 0.6 : 1 }}
              >
                {riportoSaving ? '⏳…' : '💾 Salva'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
