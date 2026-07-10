import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import {
  formatEuro,
  formatDateIT,
  formatDateGGMM,
  COLORS,
  SHADOWS,
  BORDER_RADIUS,
  useIsMobile,
} from '../lib/utils';
import { useHashState } from '../hooks/useHashState';
import { CopyLinkButton } from '../components/CopyLinkButton';
import ModalFattura from '../components/ModalFattura';
import {
  Button,
  Badge,
  StatCard,
  Card,
  Input,
  Select,
  Table,
  TableWrap,
  Th,
  Td,
} from '../components/ds';

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

  // Debounce sulla ricerca: senza, ogni tasto premuto faceva partire una
  // chiamata API (fetch da 500 fatture a battuta). La fetch usa il valore
  // ritardato di 400ms; Invio e bottone "Cerca" restano immediati.
  const [debouncedSearch, setDebouncedSearch] = useState(search);
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 400);
    return () => clearTimeout(t);
  }, [search]);

  // Dati
  const [fatture, setFatture] = useState([]);
  const [fornitori, setFornitori] = useState([]);
  const [statistiche, setStatistiche] = useState(null);
  const [loading, setLoading] = useState(true);

  // Deep-link a una specifica fattura (es. dal modale PayPal):
  // /fatture?invoice_id=<id> — dopo il caricamento scrolla alla riga,
  // la evidenzia per 4 secondi, poi torna normale.
  const [searchParams, setSearchParams] = useSearchParams();
  const invoiceIdFromUrl = searchParams.get('invoice_id') || searchParams.get('id') || '';
  const [highlightedId, setHighlightedId] = useState('');
  const [invoiceNotFoundWarning, setInvoiceNotFoundWarning] = useState(null);
  const [fatturaView, setFatturaView] = useState(null);
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
      if (debouncedSearch) params.append('search', debouncedSearch);
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
  }, [anno, mese, fornitore, stato, debouncedSearch]);

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
        <Badge variant="success" style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
          {icon} {label}
        </Badge>
      );
    }
    if (fattura.stato === 'anomala') {
      return <Badge variant="danger">Anomala</Badge>;
    }
    return <Badge variant="warning">Da pagare</Badge>;
  };

  // ==================== RENDER ====================

  return (
    <div
      style={{ maxWidth: 1600, margin: '0 auto', position: 'relative', padding: '16px 0' }}
      data-testid="archivio-fatture-ricevute"
    >
      {/* Warning deep-link: la fattura richiesta non e nella lista corrente */}
      {invoiceNotFoundWarning && (
        <div style={{
          marginBottom: 16, padding: 14, borderRadius: BORDER_RADIUS.lg,
          background: COLORS.warningLight, border: `1px solid ${COLORS.warning}`,
          display: 'flex', alignItems: 'flex-start', gap: 12,
        }}>
          <div style={{ fontSize: 20 }}>🔍 ⚠️</div>
          <div style={{ flex: 1, fontSize: 13, color: COLORS.warning, lineHeight: 1.5 }}>
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
                <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 10 }}>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() => setFatturaView({ id: invoiceNotFoundWarning.id, numero: invoiceNotFoundWarning.numero_fattura || invoiceNotFoundWarning.fornitore })}
                  >
                    Vedi la fattura adesso
                  </Button>
                  <span style={{ fontSize: 12, color: COLORS.warning, alignSelf: 'center' }}>
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
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setInvoiceNotFoundWarning(null);
              const p = new URLSearchParams(searchParams);
              p.delete('invoice_id');
              p.delete('id');
              setSearchParams(p, { replace: true });
            }}
            style={{ fontSize: 18, color: COLORS.warning, padding: 0 }}
          >
            ✓
          </Button>
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
          <StatCard label="Fatture Totali" value={statistiche.totale_fatture} accent="primary" />
          <StatCard
            label="Importo Totale"
            value={formatCurrency(statistiche.totale_importo)}
            accent="success"
          />
          <StatCard label="Fornitori" value={statistiche.fornitori_unici} accent="info" />
          <StatCard
            label="Anomale"
            value={statistiche.fatture_anomale}
            accent={statistiche.fatture_anomale > 0 ? 'danger' : 'success'}
          />
        </div>
      )}

      {/* Filtri */}
      <Card style={{ marginBottom: 20 }}>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <div>
            <label style={{ fontSize: 11, color: COLORS.textMuted, display: 'block', marginBottom: 4 }}>
              Anno
            </label>
            <div
              style={{
                padding: '9px 12px',
                borderRadius: BORDER_RADIUS.sm,
                border: `1px solid ${COLORS.border}`,
                minWidth: 80,
                background: COLORS.gray[100],
                color: COLORS.textMuted,
                fontWeight: 600,
                fontSize: 13,
                boxSizing: 'border-box',
              }}
            >
              {anno} <span style={{ fontSize: 9, opacity: 0.7 }}>(globale)</span>
            </div>
          </div>
          <div>
            <label style={{ fontSize: 11, color: COLORS.textMuted, display: 'block', marginBottom: 4 }}>
              Mese
            </label>
            <Select
              value={mese}
              onChange={e => setHs('mese', e.target.value)}
              style={{ minWidth: 110, fontSize: 13 }}
            >
              {MESI.map(m => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <label style={{ fontSize: 11, color: COLORS.textMuted, display: 'block', marginBottom: 4 }}>
              Fornitore
            </label>
            <Select
              value={fornitore}
              onChange={e => setHs('fornitore', e.target.value)}
              style={{ minWidth: 180, fontSize: 13 }}
            >
              <option value="">Tutti i fornitori</option>
              {fornitori.map(f => (
                <option key={f.partita_iva} value={f.partita_iva}>
                  {f.ragione_sociale} ({f.partita_iva})
                </option>
              ))}
            </Select>
          </div>
          <div>
            <label style={{ fontSize: 11, color: COLORS.textMuted, display: 'block', marginBottom: 4 }}>
              Stato
            </label>
            <Select
              value={stato}
              onChange={e => setHs('stato', e.target.value)}
              style={{ minWidth: 100, fontSize: 13 }}
            >
              <option value="">Tutti</option>
              <option value="importata">Importate</option>
              <option value="anomala">Anomale</option>
              <option value="pagata">Pagate</option>
              <option value="senza_metodo">🔍 ⚠️ Senza metodo pagamento</option>
            </Select>
          </div>
          <div style={{ flex: 1, minWidth: 180 }}>
            <label style={{ fontSize: 11, color: COLORS.textMuted, display: 'block', marginBottom: 4 }}>
              Ricerca
            </label>
            <Input
              type="text"
              placeholder="Numero fattura, fornitore..."
              value={search}
              onChange={e => setHs('search', e.target.value)}
              onKeyDown={e => e.key === 'Enter' && setDebouncedSearch(search)}
              style={{ fontSize: 13 }}
            />
          </div>
          <div style={{ alignSelf: 'flex-end', display: 'flex', gap: 8 }}>
            <Button
              variant="primary"
              size="sm"
              onClick={() => {
                setDebouncedSearch(search);
                fetchFatture();
              }}
              style={{ fontSize: 13 }}
            >
              Cerca
            </Button>
            <CopyLinkButton />
          </div>
        </div>
      </Card>

      {/* Tabella Fatture */}
      <Card>
        {loading ? (
          <div style={{ padding: 40, textAlign: 'center', color: COLORS.textMuted }}>
            ⏳ Caricamento...
          </div>
        ) : fatture.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: COLORS.textMuted }}>
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
                    <Badge variant="success" style={{ fontSize: 11 }}>
                      🔗 RICONC.
                    </Badge>
                  )}
                  <Button
                    variant="info"
                    size="sm"
                    onClick={() => setFatturaView({ id: f.id, numero: f.numero_fattura || f.numero || f.fornitore })}
                  >
                    Vedi
                  </Button>
                  {!isPaid && (isFornitoreBanca || isFornitoreCassa) && (
                    <Badge
                      variant={isFornitoreCassa ? 'success' : 'info'}
                      title="Metodo del fornitore — la registrazione avviene in Prima Nota"
                      style={{ fontSize: 12 }}
                    >
                      {isFornitoreCassa ? '💵 Cassa' : '🏦 Banca'}
                    </Badge>
                  )}
                  {/* Se la fattura e pagata: mostra SOLO il bottone col check del metodo effettivo */}
                  {isPaid && metodoPagEffettivo === 'cassa' && (
                    <Badge variant="success" style={{ fontSize: 12 }}>
                      💵 🔗 Cassa
                    </Badge>
                  )}
                  {isPaid && metodoPagEffettivo === 'banca' && (
                    <Badge variant="info" style={{ fontSize: 12 }}>
                      🏦 🔗 Banca
                    </Badge>
                  )}
                </div>
              );

              return (
                <div
                  key={f.id || `fattura-${idx}`}
                  ref={f.id === highlightedId ? highlightedRowRef : null}
                  style={{
                    background: f.id === highlightedId ? COLORS.warningLight : COLORS.card,
                    borderRadius: BORDER_RADIUS.lg,
                    padding: '10px 12px',
                    boxShadow: f.id === highlightedId
                      ? `0 0 0 3px ${COLORS.accent}, 0 8px 25px rgba(184,134,11,0.25)`
                      : SHADOWS.sm,
                    border: f.id === highlightedId ? `1px solid ${COLORS.accent}` : `1px solid ${COLORS.border}`,
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
                      {/* Su mobile niente P.IVA: è nel "Vedi", qui ruba solo
                          una riga per card (richiesta utente 10-07-2026) */}
                      <div
                        style={{
                          fontWeight: 700,
                          color: COLORS.primary,
                          fontSize: 14,
                          wordBreak: 'break-word',
                          overflowWrap: 'anywhere',
                        }}
                      >
                        {f.supplier_name || f.fornitore_ragione_sociale || '—'}
                      </div>
                    </div>
                    <div
                      style={{
                        fontWeight: 700,
                        fontSize: 15,
                        color: COLORS.primary,
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
                      color: COLORS.textMuted,
                      marginBottom: 8,
                      flexWrap: 'wrap',
                      minWidth: 0,
                    }}
                  >
                    {/* Data compatta (gg/mm): l'anno è nel selettore globale
                        e la data non deve pesare più di imponibile e IVA */}
                    <span style={{ minWidth: 0, whiteSpace: 'nowrap' }}>
                      {formatDateGGMM(f.invoice_date || f.data_documento)}
                    </span>
                    <span
                      style={{
                        minWidth: 0,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        maxWidth: '40%',
                      }}
                      title={f.invoice_number || f.numero_documento || ''}
                    >
                      #{f.invoice_number || f.numero_documento || '—'}
                    </span>
                    <span style={{ whiteSpace: 'nowrap' }}>
                      Imp. {formatCurrency(f.imponibile)}
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
          <TableWrap>
            <Table>
              <thead>
                <tr>
                  <Th>Data</Th>
                  <Th>Numero</Th>
                  <Th>Fornitore</Th>
                  <Th align="right">Imponibile</Th>
                  <Th align="right">IVA</Th>
                  <Th align="right">Totale</Th>
                  <Th align="center" style={{ minWidth: 220 }}>
                    Azioni
                  </Th>
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
                          ? COLORS.warningLight
                          : idx % 2 === 0 ? COLORS.card : COLORS.bgAlt,
                        boxShadow: f.id === highlightedId
                          ? `0 0 0 3px ${COLORS.accent} inset, 0 4px 12px rgba(184,134,11,0.2)`
                          : SHADOWS.sm,
                        transition: 'background 300ms, box-shadow 300ms',
                      }}
                    >
                      <Td>{formatDateIT(f.invoice_date || f.data_documento)}</Td>
                      <Td style={{ fontWeight: 600, color: COLORS.primary }}>
                        {f.invoice_number || f.numero_documento}
                      </Td>
                      <Td>
                        <div style={{ fontWeight: 500, fontSize: 13, color: COLORS.gray[700] }}>
                          {f.supplier_name || f.fornitore_ragione_sociale}
                        </div>
                        <div style={{ fontSize: 11, color: COLORS.textSubtle, marginTop: 2 }}>
                          {f.supplier_vat || f.fornitore_partita_iva}
                        </div>
                      </Td>
                      <Td align="right" mono>
                        {formatCurrency(f.imponibile)}
                      </Td>
                      <Td align="right" mono style={{ color: COLORS.textMuted }}>
                        {formatCurrency(f.iva)}
                      </Td>
                      <Td align="right" mono style={{ fontWeight: 700, color: COLORS.primary }}>
                        {formatCurrency(f.total_amount || f.importo_totale)}
                      </Td>
                      <Td align="center">
                        <div
                          style={{
                            display: 'flex',
                            gap: 8,
                            justifyContent: 'center',
                            alignItems: 'center',
                            flexWrap: 'wrap',
                          }}
                        >
                          <Button
                            variant="info"
                            size="sm"
                            onClick={() => setFatturaView({ id: f.id, numero: f.numero_fattura || f.numero || f.fornitore })}
                          >
                            Vedi
                          </Button>
                          {isPaid ? (
                            <Badge
                              variant={metodoPagEffettivo === 'cassa' ? 'success' : 'info'}
                              title={isRiconciliata ? 'Riconciliata con estratto conto' : 'Pagata'}
                            >
                              {metodoPagEffettivo === 'cassa'
                                ? 'Cassa'
                                : 'Banca'}
                              {isRiconciliata ? ' � EC' : ''}
                            </Badge>
                          ) : fornBanca || fornCassa ? (
                            <Badge
                              variant={fornCassa ? 'success' : 'info'}
                              title="Metodo del fornitore — la registrazione avviene in Prima Nota"
                            >
                              {fornCassa ? '💵 Cassa' : '🏦 Banca'}
                            </Badge>
                          ) : (
                            <span
                              title="Fornitore senza metodo di pagamento — impostalo in Fornitori; la registrazione si fa in Prima Nota"
                              style={{ color: COLORS.textSubtle, fontSize: 12 }}
                            >
                              —
                            </span>
                          )}
                        </div>
                      </Td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
          </TableWrap>
        )}
      </Card>
      {fatturaView && (
        <ModalFattura
          fatturaId={fatturaView.id}
          numero={fatturaView.numero}
          onClose={() => setFatturaView(null)}
        />
      )}
    </div>
  );
}
