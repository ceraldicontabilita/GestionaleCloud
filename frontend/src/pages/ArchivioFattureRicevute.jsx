import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import {
  formatEuro,
  formatDateIT,
  STYLES,
  COLORS,
  SHADOWS,
  BORDER_RADIUS,
  button,
  badge,
  useIsMobile,
  RG,
  pagePad,
} from '../lib/utils';
import { useHashState } from '../hooks/useHashState';
import { CopyLinkButton } from '../components/CopyLinkButton';

const MESI = [
  { value: '', label: 'Tutti i mesi' },
  { value: '1', label: 'Gennaio' },
  { value: '2', label: 'Febbraio' },
  { value: '3', label: 'Marzo' },
  { value: '4', label: 'Aprile' },
  { value: '5', label: 'Maggio' },
  { value: '6', label: 'Giugno' },
  { value: '7', label: 'Luglio' },
  { value: '8', label: 'Agosto' },
  { value: '9', label: 'Settembre' },
  { value: '10', label: 'Ottobre' },
  { value: '11', label: 'Novembre' },
  { value: '12', label: 'Dicembre' },
];

// Stili inline — allineati a STYLES.card/button() (design system unificato in lib/utils.js)
const cardStyle = STYLES.card;
const btnPrimary = { ...button('primary'), fontSize: 14 };
const btnSecondary = { ...button('secondary'), fontSize: 14 };
const inputStyle = {
  padding: '10px 12px',
  borderRadius: BORDER_RADIUS.sm,
  border: `1px solid ${COLORS.border}`,
  fontSize: 14,
  boxSizing: 'border-box',
};
const selectStyle = {
  padding: '10px 12px',
  borderRadius: BORDER_RADIUS.sm,
  border: `1px solid ${COLORS.border}`,
  fontSize: 14,
  background: 'white',
};

// Stili aggiuntivi per riconciliazione
const styles = {
  badge: color => ({
    display: 'inline-flex',
    alignItems: 'center',
    padding: '4px 10px',
    borderRadius: 20,
    fontSize: 12,
    fontWeight: 600,
    background: `${color}15`,
    color: color,
  }),
  button: (variant = 'primary') => ({
    padding: '8px 14px',
    borderRadius: 8,
    border: 'none',
    cursor: 'pointer',
    fontWeight: 500,
    fontSize: 13,
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    transition: 'all 0.2s',
    ...(variant === 'primary'
      ? { background: '#3b82f6', color: 'white' }
      : variant === 'success'
        ? { background: '#10b981', color: 'white' }
        : variant === 'danger'
          ? { background: '#ef4444', color: 'white' }
          : { background: '#f1f5f9', color: '#475569', border: '1px solid #e2e8f0' }),
  }),
  uploadZone: {
    border: '2px dashed #cbd5e1',
    borderRadius: 12,
    padding: '40px 20px',
    textAlign: 'center',
    cursor: 'pointer',
    transition: 'all 0.2s',
    background: '#f8fafc',
  },
  uploadZoneActive: {
    borderColor: '#3b82f6',
    background: '#eff6ff',
  },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: 14 },
  th: {
    padding: '12px 16px',
    textAlign: 'left',
    fontWeight: 600,
    color: '#475569',
    borderBottom: '2px solid #e2e8f0',
    background: '#f8fafc',
  },
  td: { padding: '12px 16px', borderBottom: '1px solid #f1f5f9', color: '#334155' },
  emptyState: { textAlign: 'center', padding: '60px 20px', color: '#64748b' },
  splitView: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))',
    gap: 24,
  },
  rowHighlight: { background: '#fef3c7', cursor: 'pointer' },
  rowSelected: { background: '#dbeafe' },
};

export default function ArchivioFatture() {
  const isMobile = useIsMobile();
  const navigate = useNavigate();
  const { anno } = useAnnoGlobale();

  // Deep link: filtri sincronizzati con URL hash
  // es: /archivio-fatture-ricevute#mese=3&stato=da_pagare&search=rossi
  const [hs, setHs, setHsMany] = useHashState({
    mese: '',
    fornitore: '',
    stato: '',
    search: '',
  });
  const mese = hs.mese;
  const fornitore = hs.fornitore;
  const stato = hs.stato;
  const search = hs.search;

  // Dati
  const [fatture, setFatture] = useState([]);
  const [fornitori, setFornitori] = useState([]);
  const [statistiche, setStatistiche] = useState(null);
  const [loading, setLoading] = useState(true);

  // Deep-link a una specifica fattura (es. dal modale PayPal):
  // /fatture?invoice_id=<id> → dopo il caricamento scrolla alla riga,
  // la evidenzia per 4 secondi, poi torna normale.
  const [searchParams, setSearchParams] = useSearchParams();
  const invoiceIdFromUrl = searchParams.get('invoice_id') || searchParams.get('id') || '';
  const [highlightedId, setHighlightedId] = useState('');
  const [invoiceNotFoundWarning, setInvoiceNotFoundWarning] = useState(null);
  const highlightedRowRef = useRef(null);

  useEffect(() => {
    if (!invoiceIdFromUrl || loading) return; // aspetto che il fetch sia finito
    if (fatture.length === 0) return;

    const found = fatture.find(f => f.id === invoiceIdFromUrl);

    if (!found) {
      // La fattura non è nella lista — probabilmente è di un anno diverso
      // da quello attualmente filtrato. Chiedo al backend di che anno è.
      (async () => {
        try {
          const r = await api.get(`/api/fatture-ricevute/fattura/${invoiceIdFromUrl}`);
          const f = r.data;
          const annoFattura = (f.invoice_date || f.data_documento || '').slice(0, 4);
          setInvoiceNotFoundWarning({
            id: invoiceIdFromUrl,
            anno: annoFattura,
            numero: f.invoice_number || f.numero_documento,
            fornitore: f.supplier_name || f.fornitore_ragione_sociale,
          });
        } catch {
          // Anche il lookup diretto fallisce — fattura inesistente o cancellata
          setInvoiceNotFoundWarning({ id: invoiceIdFromUrl, notExist: true });
        }
      })();
      return;
    }

    // Caso normale: trovata, evidenzio
    setInvoiceNotFoundWarning(null);
    setHighlightedId(invoiceIdFromUrl);
    setTimeout(() => {
      highlightedRowRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 100);
    const t = setTimeout(() => {
      setHighlightedId('');
      const p = new URLSearchParams(searchParams);
      p.delete('invoice_id');
      p.delete('id');
      setSearchParams(p, { replace: true });
    }, 4000);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [invoiceIdFromUrl, fatture, loading]);

  // ==================== FETCH FUNCTIONS ====================

  const fetchFatture = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (anno) params.append('anno', anno);
      if (mese) params.append('mese', mese);
      if (fornitore) params.append('fornitore_piva', fornitore);
      // "senza_metodo" è un filtro client-side: fa fetch senza stato e poi filtra
      if (stato && stato !== 'senza_metodo') params.append('stato', stato);
      if (search) params.append('search', search);
      params.append('limit', '500');

      const res = await api.get(`/api/fatture-ricevute/archivio?${params.toString()}`);
      let items = res.data.fatture || res.data.items || [];

      // Filtro client: fatture di fornitori SENZA metodo pagamento configurato
      if (stato === 'senza_metodo') {
        items = items.filter(f => {
          const m = (f.fornitore_metodo_pagamento || '').toLowerCase().trim();
          return !m || m === 'da_configurare' || m === 'misto' || m === 'altro';
        });
      }
      setFatture(items);
    } catch (err) {
      console.error('Errore caricamento fatture:', err);
    }
    setLoading(false);
  }, [anno, mese, fornitore, stato, search]);

  const fetchFornitori = async () => {
    try {
      const res = await api.get('/api/fatture-ricevute/fornitori?con_fatture=true&limit=500');
      setFornitori(res.data.items || []);
    } catch (err) {
      console.error('Errore caricamento fornitori:', err);
    }
  };

  const fetchStatistiche = async () => {
    try {
      const params = anno ? `?anno=${anno}` : '';
      const res = await api.get(`/api/fatture-ricevute/statistiche${params}`);
      setStatistiche(res.data);
    } catch (err) {
      console.error('Errore caricamento statistiche:', err);
    }
  };

  // ==================== EFFECTS ====================

  useEffect(() => {
    fetchFatture();
    fetchStatistiche();
  }, [fetchFatture, anno]);

  useEffect(() => {
    fetchFornitori();
  }, []);

  // ==================== HELPERS ====================

  // Usa formatEuro da utils.js (già importato)
  const formatCurrency = formatEuro;

  // Usa formatDateIT da utils.js
  const formatDate = formatDateIT;

  const getStatoBadge = fattura => {
    if (fattura.pagato) {
      let metodo = fattura.metodo_pagamento || '';
      let icon = '✅';
      let label = 'Pagata';

      if (
        fattura.prima_nota_cassa_id ||
        metodo.toLowerCase().includes('cassa') ||
        metodo.toLowerCase().includes('contanti')
      ) {
        icon = '💵';
        label = 'Cassa';
      } else if (
        fattura.prima_nota_banca_id ||
        metodo.toLowerCase().includes('banca') ||
        metodo.toLowerCase().includes('bonifico')
      ) {
        icon = '🏦';
        label = 'Banca';
      } else if (metodo.toLowerCase().includes('assegno')) {
        icon = '📝';
        label = 'Assegno';
      } else if (metodo.toLowerCase().includes('rid') || metodo.toLowerCase().includes('sdd')) {
        icon = '🔄';
        label = 'RID/SDD';
      }

      return (
        <span
          style={{
            padding: '4px 10px',
            background: '#dcfce7',
            color: '#16a34a',
            borderRadius: 6,
            fontSize: 11,
            fontWeight: '600',
            display: 'inline-flex',
            alignItems: 'center',
            gap: 4,
          }}
        >
          {icon} {label}
        </span>
      );
    }
    if (fattura.stato === 'anomala') {
      return (
        <span
          style={{
            padding: '4px 10px',
            background: '#fee2e2',
            color: '#dc2626',
            borderRadius: 6,
            fontSize: 12,
            fontWeight: '600',
          }}
        >
          Anomala
        </span>
      );
    }
    return (
      <span
        style={{
          padding: '4px 10px',
          background: '#fef3c7',
          color: '#d97706',
          borderRadius: 6,
          fontSize: 12,
          fontWeight: '600',
        }}
      >
        Da pagare
      </span>
    );
  };

  // ==================== RENDER ====================

  return (
    <div
      style={{ maxWidth: 1600, margin: '0 auto', position: 'relative', padding: '16px 0' }}
      data-testid="archivio-fatture-ricevute"
    >
      {/* Warning deep-link: la fattura richiesta non è nella lista corrente */}
      {invoiceNotFoundWarning && (
        <div style={{
          marginBottom: 16, padding: 14, borderRadius: 10,
          background: '#fffbeb', border: '1px solid #fcd34d',
          display: 'flex', alignItems: 'flex-start', gap: 12,
        }}>
          <div style={{ fontSize: 20 }}>⚠️</div>
          <div style={{ flex: 1, fontSize: 13, color: '#78350f', lineHeight: 1.5 }}>
            {invoiceNotFoundWarning.notExist ? (
              <>
                La fattura che cercavi non esiste più o è stata eliminata
                (id: <code>{invoiceNotFoundWarning.id}</code>).
              </>
            ) : (
              <>
                La fattura <strong>{invoiceNotFoundWarning.numero}</strong> di{' '}
                <strong>{invoiceNotFoundWarning.fornitore}</strong>
                {invoiceNotFoundWarning.anno ? (
                  <>
                    {' '}è dell'anno <strong>{invoiceNotFoundWarning.anno}</strong>, ma stai
                    guardando l'anno <strong>{anno}</strong>.
                  </>
                ) : (
                  <> non è nell'anno selezionato (<strong>{anno}</strong>).</>
                )}
                <div style={{ marginTop: 8, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  <a
                    href={`/api/fatture-ricevute/fattura/${invoiceNotFoundWarning.id}/view-assoinvoice`}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      padding: '6px 12px', background: '#1e3a5f', color: 'white',
                      borderRadius: 6, fontSize: 12, fontWeight: 600, textDecoration: 'none',
                    }}
                  >
                    📄 Vedi la fattura adesso
                  </a>
                  <span style={{ fontSize: 12, color: '#92400e', alignSelf: 'center' }}>
                    oppure cambia l'anno globale (in alto a destra)
                    {invoiceNotFoundWarning.anno ? (
                      <> a <strong>{invoiceNotFoundWarning.anno}</strong></>
                    ) : null}{' '}
                    per vederla in elenco.
                  </span>
                </div>
              </>
            )}
          </div>
          <button
            onClick={() => {
              setInvoiceNotFoundWarning(null);
              const p = new URLSearchParams(searchParams);
              p.delete('invoice_id');
              p.delete('id');
              setSearchParams(p, { replace: true });
            }}
            style={{
              background: 'transparent', border: 'none', cursor: 'pointer',
              fontSize: 18, color: '#78350f', padding: 0,
            }}
          >
            ✕
          </button>
        </div>
      )}

      {/* Statistiche */}
      {statistiche && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))',
            gap: 12,
            marginBottom: 20,
          }}
        >
          <div style={{ ...cardStyle, textAlign: 'center', padding: 14 }}>
            <div style={{ fontSize: 22, fontWeight: 'bold', color: '#1e3a5f' }}>
              {statistiche.totale_fatture}
            </div>
            <div style={{ fontSize: 12, color: '#6b7280' }}>Fatture Totali</div>
          </div>
          <div style={{ ...cardStyle, textAlign: 'center', padding: 14 }}>
            <div style={{ fontSize: 18, fontWeight: 'bold', color: '#16a34a' }}>
              {formatCurrency(statistiche.totale_importo)}
            </div>
            <div style={{ fontSize: 12, color: '#6b7280' }}>Importo Totale</div>
          </div>
          <div style={{ ...cardStyle, textAlign: 'center', padding: 14 }}>
            <div style={{ fontSize: 22, fontWeight: 'bold', color: '#2196f3' }}>
              {statistiche.fornitori_unici}
            </div>
            <div style={{ fontSize: 12, color: '#6b7280' }}>Fornitori</div>
          </div>
          <div style={{ ...cardStyle, textAlign: 'center', padding: 14 }}>
            <div
              style={{
                fontSize: 22,
                fontWeight: 'bold',
                color: statistiche.fatture_anomale > 0 ? '#dc2626' : '#16a34a',
              }}
            >
              {statistiche.fatture_anomale}
            </div>
            <div style={{ fontSize: 12, color: '#6b7280' }}>Anomale</div>
          </div>
        </div>
      )}

      {/* Filtri */}
      <div style={{ ...cardStyle, marginBottom: 20 }}>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <div>
            <label style={{ fontSize: 11, color: '#6b7280', display: 'block', marginBottom: 4 }}>
              Anno
            </label>
            <div
              style={{
                ...selectStyle,
                minWidth: 80,
                background: '#f1f5f9',
                color: '#64748b',
                fontWeight: 600,
                fontSize: 13,
              }}
            >
              {anno} <span style={{ fontSize: 9, opacity: 0.7 }}>(globale)</span>
            </div>
          </div>
          <div>
            <label style={{ fontSize: 11, color: '#6b7280', display: 'block', marginBottom: 4 }}>
              Mese
            </label>
            <select
              value={mese}
              onChange={e => setHs('mese', e.target.value)}
              style={{ ...selectStyle, minWidth: 110, fontSize: 13 }}
            >
              {MESI.map(m => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label style={{ fontSize: 11, color: '#6b7280', display: 'block', marginBottom: 4 }}>
              Fornitore
            </label>
            <select
              value={fornitore}
              onChange={e => setHs('fornitore', e.target.value)}
              style={{ ...selectStyle, minWidth: 180, fontSize: 13 }}
            >
              <option value="">Tutti i fornitori</option>
              {fornitori.map(f => (
                <option key={f.partita_iva} value={f.partita_iva}>
                  {f.ragione_sociale} ({f.partita_iva})
                </option>
              ))}
            </select>
          </div>
          <div>
            <label style={{ fontSize: 11, color: '#6b7280', display: 'block', marginBottom: 4 }}>
              Stato
            </label>
            <select
              value={stato}
              onChange={e => setHs('stato', e.target.value)}
              style={{ ...selectStyle, minWidth: 100, fontSize: 13 }}
            >
              <option value="">Tutti</option>
              <option value="importata">Importate</option>
              <option value="anomala">Anomale</option>
              <option value="pagata">Pagate</option>
              <option value="senza_metodo">⚠️ Senza metodo pagamento</option>
            </select>
          </div>
          <div style={{ flex: 1, minWidth: 180 }}>
            <label style={{ fontSize: 11, color: '#6b7280', display: 'block', marginBottom: 4 }}>
              Ricerca
            </label>
            <input
              type="text"
              placeholder="Numero fattura, fornitore..."
              value={search}
              onChange={e => setHs('search', e.target.value)}
              onKeyDown={e => e.key === 'Enter' && fetchFatture()}
              style={{ ...inputStyle, width: '100%', fontSize: 13 }}
            />
          </div>
          <div style={{ alignSelf: 'flex-end', display: 'flex', gap: 8 }}>
            <button onClick={fetchFatture} style={{ ...btnPrimary, fontSize: 13 }}>
              Cerca
            </button>
            <CopyLinkButton />
          </div>
        </div>
      </div>

      {/* Tabella Fatture */}
      <div style={cardStyle}>
        {loading ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>
            ⏳ Caricamento...
          </div>
        ) : fatture.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>
            <div style={{ fontSize: 48, marginBottom: 16 }}>📭</div>
            <p style={{ margin: 0 }}>Nessuna fattura trovata</p>
            <p style={{ margin: '8px 0 0 0', fontSize: 14 }}>
              Vai a Import Unificato per importare fatture
            </p>
          </div>
        ) : isMobile ? (
          // VISTA MOBILE: card per ogni fattura
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {fatture.map((f, idx) => {
              const isPaid = f.pagato || f.status === 'paid' || f.stato_pagamento === 'pagata';
              // Determina metodo EFFETTIVO del pagamento guardando:
              // 1. prima_nota_cassa_id / prima_nota_banca_id (fonte primaria)
              // 2. metodo_pagamento / metodo_pagamento_effettivo (fallback per dati legacy)
              const hasCassaId = !!f.prima_nota_cassa_id;
              const hasBancaId = !!f.prima_nota_banca_id;
              const metodoSalvato = (
                f.metodo_pagamento_effettivo ||
                f.metodo_pagamento ||
                ''
              ).toLowerCase();
              const isCassaByMetodo =
                metodoSalvato.includes('contant') ||
                metodoSalvato === 'cassa' ||
                metodoSalvato.includes('cash');
              const isBancaByMetodo =
                metodoSalvato.includes('bonifico') ||
                metodoSalvato === 'banca' ||
                metodoSalvato.includes('bank') ||
                metodoSalvato.includes('sepa') ||
                metodoSalvato.includes('rid');

              // Priorità: ID prima nota > metodo salvato > null
              const metodoPagEffettivo = hasCassaId
                ? 'cassa'
                : hasBancaId
                  ? 'banca'
                  : isCassaByMetodo
                    ? 'cassa'
                    : isBancaByMetodo
                      ? 'banca'
                      : null;

              // Metodo configurato nel fornitore (per default quando non pagato)
              // NOTA: fallback NON deve usare metodo_pagamento della fattura XML,
              // perché in XML il cedente dichiara il SUO modo di incasso, non
              // come noi paghiamo. Usiamo SOLO il campo dell'anagrafica fornitore.
              const metodoFornitore = (
                f.fornitore_metodo_pagamento || ''
              ).toLowerCase();
              const isFornitoreCassa =
                metodoFornitore.includes('contant') ||
                metodoFornitore === 'cassa' ||
                metodoFornitore.includes('cash');
              const isFornitoreBanca =
                metodoFornitore.includes('bonifico') ||
                metodoFornitore === 'banca' ||
                metodoFornitore.includes('bank') ||
                metodoFornitore.includes('sepa') ||
                metodoFornitore.includes('rid') ||
                metodoFornitore.includes('sdd') ||
                metodoFornitore.includes('addebito');

              // BLOCCO: Se riconciliata, non permettere modifica
              const isRiconciliata = f.riconciliato === true;

              const azioniButtons = (
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                  {isRiconciliata && (
                    <span
                      style={{
                        padding: '5px 8px',
                        background: '#10b981',
                        color: 'white',
                        borderRadius: 6,
                        fontSize: 11,
                        fontWeight: 'bold',
                      }}
                    >
                      ✓ RICONC.
                    </span>
                  )}
                  <a
                    href={`/api/fatture-ricevute/fattura/${f.id}/view-assoinvoice`}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      padding: '7px 11px',
                      background: '#3b82f6',
                      color: 'white',
                      border: 'none',
                      borderRadius: 6,
                      cursor: 'pointer',
                      fontSize: 12,
                      fontWeight: '600',
                      textDecoration: 'none',
                    }}
                  >
                    📄 Vedi
                  </a>
                  {/* Metodo del fornitore in SOLA LETTURA: la registrazione in
                      cassa/banca si fa dalla pagina Prima Nota. */}
                  {!isPaid && (isFornitoreBanca || isFornitoreCassa) && (
                    <span
                      title="Metodo del fornitore — la registrazione avviene in Prima Nota"
                      style={{
                        padding: '7px 11px',
                        background: isFornitoreCassa ? '#f0fdf4' : '#eff6ff',
                        color: isFornitoreCassa ? '#16a34a' : '#2563eb',
                        border: `1px solid ${isFornitoreCassa ? '#bbf7d0' : '#bfdbfe'}`,
                        borderRadius: 6,
                        fontSize: 12,
                        fontWeight: '600',
                      }}
                    >
                      {isFornitoreCassa ? '💵 Cassa' : '🏦 Banca'}
                    </span>
                  )}
                  {/* Se la fattura è pagata: mostra SOLO il bottone col check del metodo effettivo */}
                  {isPaid && metodoPagEffettivo === 'cassa' && (
                    <span
                      style={{
                        padding: '7px 11px',
                        background: '#10b981',
                        color: 'white',
                        borderRadius: 6,
                        fontSize: 12,
                        fontWeight: '600',
                      }}
                    >
                      💵 ✓ Cassa
                    </span>
                  )}
                  {isPaid && metodoPagEffettivo === 'banca' && (
                    <span
                      style={{
                        padding: '7px 11px',
                        background: '#3b82f6',
                        color: 'white',
                        borderRadius: 6,
                        fontSize: 12,
                        fontWeight: '600',
                      }}
                    >
                      🏦 ✓ Banca
                    </span>
                  )}
                </div>
              );

              return (
                <div
                  key={f.id || `fattura-${idx}`}
                  ref={f.id === highlightedId ? highlightedRowRef : null}
                  style={{
                    background: f.id === highlightedId ? '#fef3c7' : 'white',
                    borderRadius: 10,
                    padding: '14px 16px',
                    boxShadow: f.id === highlightedId
                      ? '0 0 0 3px #b8860b, 0 8px 25px rgba(184,134,11,0.25)'
                      : '0 1px 4px rgba(0,0,0,0.08)',
                    border: f.id === highlightedId ? '1px solid #b8860b' : '1px solid #e5e7eb',
                    overflow: 'hidden',
                    minWidth: 0,
                    transition: 'all 300ms ease',
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'flex-start',
                      marginBottom: 8,
                      gap: 8,
                    }}
                  >
                    <div style={{ flex: 1, minWidth: 0, overflow: 'hidden' }}>
                      <div
                        style={{
                          fontWeight: 700,
                          color: '#1e3a5f',
                          fontSize: 14,
                          wordBreak: 'break-word',
                          overflowWrap: 'anywhere',
                        }}
                      >
                        {f.supplier_name || f.fornitore_ragione_sociale || '—'}
                      </div>
                      <div
                        style={{
                          fontSize: 11,
                          color: '#9ca3af',
                          marginTop: 2,
                          wordBreak: 'break-word',
                        }}
                      >
                        {f.supplier_vat || f.fornitore_partita_iva}
                      </div>
                    </div>
                    <div
                      style={{
                        fontWeight: 700,
                        fontSize: 15,
                        color: '#1e3a5f',
                        whiteSpace: 'nowrap',
                        flexShrink: 0,
                      }}
                    >
                      {formatCurrency(f.total_amount || f.importo_totale)}
                    </div>
                  </div>
                  <div
                    style={{
                      display: 'flex',
                      gap: 10,
                      rowGap: 4,
                      fontSize: 12,
                      color: '#64748b',
                      marginBottom: 10,
                      flexWrap: 'wrap',
                      minWidth: 0,
                    }}
                  >
                    <span style={{ minWidth: 0, whiteSpace: 'nowrap' }}>
                      📅 {formatDateIT(f.invoice_date || f.data_documento)}
                    </span>
                    <span
                      style={{
                        minWidth: 0,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        maxWidth: '55%',
                      }}
                      title={f.invoice_number || f.numero_documento || ''}
                    >
                      #{f.invoice_number || f.numero_documento || '—'}
                    </span>
                    <span style={{ whiteSpace: 'nowrap' }}>IVA {formatCurrency(f.iva)}</span>
                  </div>
                  {azioniButtons}
                </div>
              );
            })}
          </div>
        ) : (
          // VISTA DESKTOP: tabella classica
          <div style={{ overflowX: 'auto' }}>
            <table
              style={{
                width: '100%',
                borderCollapse: 'separate',
                borderSpacing: '0 4px',
                fontSize: 13,
              }}
            >
              <thead>
                <tr style={{ background: '#f1f5f9' }}>
                  <th
                    style={{
                      padding: '14px 16px',
                      textAlign: 'left',
                      fontWeight: '600',
                      color: '#1e293b',
                      borderRadius: '8px 0 0 8px',
                    }}
                  >
                    Data
                  </th>
                  <th
                    style={{
                      padding: '14px 16px',
                      textAlign: 'left',
                      fontWeight: '600',
                      color: '#1e293b',
                    }}
                  >
                    Numero
                  </th>
                  <th
                    style={{
                      padding: '14px 16px',
                      textAlign: 'left',
                      fontWeight: '600',
                      color: '#1e293b',
                    }}
                  >
                    Fornitore
                  </th>
                  <th
                    style={{
                      padding: '14px 16px',
                      textAlign: 'right',
                      fontWeight: '600',
                      color: '#1e293b',
                    }}
                  >
                    Imponibile
                  </th>
                  <th
                    style={{
                      padding: '14px 16px',
                      textAlign: 'right',
                      fontWeight: '600',
                      color: '#1e293b',
                    }}
                  >
                    IVA
                  </th>
                  <th
                    style={{
                      padding: '14px 16px',
                      textAlign: 'right',
                      fontWeight: '600',
                      color: '#1e293b',
                    }}
                  >
                    Totale
                  </th>
                  <th
                    style={{
                      padding: '14px 16px',
                      textAlign: 'center',
                      fontWeight: '600',
                      color: '#1e293b',
                      borderRadius: '0 8px 8px 0',
                      minWidth: 220,
                    }}
                  >
                    Azioni
                  </th>
                </tr>
              </thead>
              <tbody>
                {fatture.map((f, idx) => {
                  const isPaid = f.pagato || f.status === 'paid' || f.stato_pagamento === 'pagata';
                  const hasCassaId = !!f.prima_nota_cassa_id;
                  const hasBancaId = !!f.prima_nota_banca_id;
                  const metodoSalvato = (
                    f.metodo_pagamento_effettivo ||
                    f.metodo_pagamento ||
                    ''
                  ).toLowerCase();
                  const isCassaByMetodo =
                    metodoSalvato.includes('contant') ||
                    metodoSalvato === 'cassa' ||
                    metodoSalvato.includes('cash');
                  const isBancaByMetodo =
                    metodoSalvato.includes('bonifico') ||
                    metodoSalvato === 'banca' ||
                    metodoSalvato.includes('bank') ||
                    metodoSalvato.includes('sepa') ||
                    metodoSalvato.includes('rid');
                  const metodoPagEffettivo = hasCassaId
                    ? 'cassa'
                    : hasBancaId
                      ? 'banca'
                      : isCassaByMetodo
                        ? 'cassa'
                        : isBancaByMetodo
                          ? 'banca'
                          : null;
                  // Metodo dichiarato in ANAGRAFICA FORNITORE (non in XML).
                  // Se presente, mostriamo solo il bottone corrispondente per evitare
                  // di registrare un pagamento col metodo sbagliato.
                  const metodoFornitoreDesk = (
                    f.fornitore_metodo_pagamento || ''
                  ).toLowerCase();
                  const fornCassa =
                    metodoFornitoreDesk.includes('contant') ||
                    metodoFornitoreDesk === 'cassa' ||
                    metodoFornitoreDesk.includes('cash');
                  const fornBanca =
                    metodoFornitoreDesk.includes('bonifico') ||
                    metodoFornitoreDesk === 'banca' ||
                    metodoFornitoreDesk.includes('bank') ||
                    metodoFornitoreDesk.includes('sepa') ||
                    metodoFornitoreDesk.includes('rid') ||
                    metodoFornitoreDesk.includes('sdd') ||
                    metodoFornitoreDesk.includes('addebito');
                  const isRiconciliata = f.riconciliato === true;
                  return (
                    <tr
                      key={f.id || `fattura-${idx}`}
                      ref={f.id === highlightedId ? highlightedRowRef : null}
                      style={{
                        background: f.id === highlightedId
                          ? '#fef3c7'
                          : idx % 2 === 0 ? 'white' : '#f8fafc',
                        boxShadow: f.id === highlightedId
                          ? '0 0 0 3px #b8860b inset, 0 4px 12px rgba(184,134,11,0.2)'
                          : '0 1px 3px rgba(0,0,0,0.05)',
                        transition: 'background 300ms, box-shadow 300ms',
                      }}
                    >
                      <td style={{ padding: '14px 16px', borderRadius: '8px 0 0 8px' }}>
                        {formatDateIT(f.invoice_date || f.data_documento)}
                      </td>
                      <td style={{ padding: '14px 16px', fontWeight: '600', color: '#1e3a5f' }}>
                        {f.invoice_number || f.numero_documento}
                      </td>
                      <td style={{ padding: '14px 16px' }}>
                        <div style={{ fontWeight: '500', fontSize: 13, color: '#374151' }}>
                          {f.supplier_name || f.fornitore_ragione_sociale}
                        </div>
                        <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 2 }}>
                          {f.supplier_vat || f.fornitore_partita_iva}
                        </div>
                      </td>
                      <td
                        style={{
                          padding: '14px 16px',
                          textAlign: 'right',
                          fontFamily: 'monospace',
                        }}
                      >
                        {formatCurrency(f.imponibile)}
                      </td>
                      <td
                        style={{
                          padding: '14px 16px',
                          textAlign: 'right',
                          fontFamily: 'monospace',
                          color: '#6b7280',
                        }}
                      >
                        {formatCurrency(f.iva)}
                      </td>
                      <td
                        style={{
                          padding: '14px 16px',
                          textAlign: 'right',
                          fontWeight: 'bold',
                          fontFamily: 'monospace',
                          color: '#1e3a5f',
                        }}
                      >
                        {formatCurrency(f.total_amount || f.importo_totale)}
                      </td>
                      <td
                        style={{
                          padding: '14px 16px',
                          textAlign: 'center',
                          borderRadius: '0 8px 8px 0',
                        }}
                      >
                        <div
                          style={{
                            display: 'flex',
                            gap: 8,
                            justifyContent: 'center',
                            alignItems: 'center',
                            flexWrap: 'wrap',
                          }}
                        >
                          <a
                            href={`/api/fatture-ricevute/fattura/${f.id}/view-assoinvoice`}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{
                              padding: '8px 12px',
                              background: '#3b82f6',
                              color: 'white',
                              border: 'none',
                              borderRadius: 6,
                              cursor: 'pointer',
                              fontSize: 12,
                              fontWeight: '600',
                              textDecoration: 'none',
                            }}
                          >
                            📄 Vedi
                          </a>
                          {/* SOLO stato in sola lettura: la registrazione in
                              cassa/banca si fa dalla pagina Prima Nota. */}
                          {isPaid ? (
                            <span
                              title={isRiconciliata ? 'Riconciliata con estratto conto' : 'Pagata'}
                              style={{
                                padding: '8px 14px',
                                background: metodoPagEffettivo === 'cassa' ? '#10b981' : '#3b82f6',
                                color: 'white',
                                borderRadius: 6,
                                fontSize: 12,
                                fontWeight: '600',
                              }}
                            >
                              {metodoPagEffettivo === 'cassa' ? '💵 ✓ Cassa' : '🏦 ✓ Banca'}
                              {isRiconciliata ? ' · EC' : ''}
                            </span>
                          ) : fornBanca || fornCassa ? (
                            <span
                              title="Metodo del fornitore — la registrazione avviene in Prima Nota"
                              style={{
                                padding: '8px 14px',
                                background: fornCassa ? '#f0fdf4' : '#eff6ff',
                                color: fornCassa ? '#16a34a' : '#2563eb',
                                border: `1px solid ${fornCassa ? '#bbf7d0' : '#bfdbfe'}`,
                                borderRadius: 6,
                                fontSize: 12,
                                fontWeight: '600',
                              }}
                            >
                              {fornCassa ? '💵 Cassa' : '🏦 Banca'}
                            </span>
                          ) : (
                            <span
                              title="Fornitore senza metodo di pagamento — impostalo in Fornitori; la registrazione si fa in Prima Nota"
                              style={{ color: '#9ca3af', fontSize: 12 }}
                            >
                              —
                            </span>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
