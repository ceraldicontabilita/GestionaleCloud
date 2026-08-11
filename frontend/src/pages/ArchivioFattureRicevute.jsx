import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import api from '../api';
import { toast } from 'sonner';
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
import AssociaAssegnoFattura from '../components/AssociaAssegnoFattura';
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
import { ChevronLeft, ChevronRight, Eye, FileText } from 'lucide-react';

const PER_PAGINA = 50;

const NOMI_TIPO_DOCUMENTO = {
  TD01: 'Fattura',
  TD04: 'Nota di credito',
  TD05: 'Nota di debito',
  TD24: 'Fattura differita',
  TD25: 'Fattura differita',
  TD26: 'Cessione beni ammortizzabili',
};

const tipoDocumento = fattura => {
  const codice = String(fattura.tipo_documento || fattura.document_type || 'TD01').toUpperCase();
  return { codice, nome: fattura.tipo_documento_desc || NOMI_TIPO_DOCUMENTO[codice] || codice };
};

const statoAllocazione = fattura => String(
  fattura.payment_allocation_status || (fattura.allocation_conflict_reason ? 'conflicting' : '') || ''
).toLowerCase();

export const descriviPagamento = fattura => {
  if (statoAllocazione(fattura) === 'conflicting') {
    return {
      variant: 'danger',
      label: 'Conflitto da verificare',
      title: fattura.allocation_conflict_reason || 'Le allocazioni superano il totale del documento.',
      verified: false,
    };
  }

  const prove = Array.isArray(fattura.payment_evidence) ? fattura.payment_evidence : [];
  const provaConfermata = prove.find(prova =>
    prova && (prova.status === 'confirmed' || prova.bank_movement_id)
  );
  const provaDocumentata = prove.find(prova => prova && prova.status === 'documented');
  const prova = provaConfermata || provaDocumentata;

  if (prova) {
    const riferimento = String(prova.reference || '').trim();
    const data = String(prova.date || '').slice(0, 10);
    if (prova.type === 'assegno') {
      return {
        variant: provaConfermata ? 'success' : 'warning',
        label: `Assegno${riferimento ? ` n. ${riferimento}` : ''}`,
        title: provaConfermata
          ? `Assegno collegato e riscontrato${data ? ` il ${formatDateIT(data)}` : ''}.`
          : 'Assegno collegato, ancora in attesa del riscontro bancario.',
        verified: !!provaConfermata,
      };
    }
    if (prova.type === 'bonifico_pdf') {
      return {
        variant: provaConfermata ? 'success' : 'warning',
        label: `Bonifico${riferimento ? ` · ${riferimento}` : ''}`,
        title: provaConfermata
          ? 'Documento di bonifico collegato al movimento bancario.'
          : 'Documento di bonifico presente, ma movimento bancario non ancora riscontrato.',
        verified: !!provaConfermata,
      };
    }
    return {
      variant: provaConfermata ? 'success' : 'warning',
      label: provaConfermata ? 'Banca · riscontro EC' : 'Prova da riscontrare',
      title: riferimento || 'Prova di pagamento collegata alla fattura.',
      verified: !!provaConfermata,
    };
  }

  if (fattura.prima_nota_cassa_id) {
    return {
      variant: 'success',
      label: 'Cassa · Prima Nota',
      title: 'Registrazione di cassa collegata alla fattura.',
      verified: true,
    };
  }
  if (fattura.prima_nota_banca_id && fattura.riconciliato === true) {
    return {
      variant: 'success',
      label: 'Banca · riscontro EC',
      title: 'Registrazione bancaria riconciliata con estratto conto.',
      verified: true,
    };
  }
  if (fattura.prima_nota_banca_id) {
    return {
      variant: 'warning',
      label: 'Banca · da riscontrare',
      title: 'Registrazione presente in Prima Nota, non ancora riscontrata con un movimento bancario.',
      verified: false,
    };
  }

  const dichiarataPagata = fattura.pagato || fattura.status === 'paid'
    || fattura.stato_pagamento === 'pagata';
  if (dichiarataPagata) {
    return {
      variant: 'warning',
      label: 'Pagamento da verificare',
      title: 'Lo stato storico indica pagata, ma non espone una prova collegata.',
      verified: false,
    };
  }

  const metodoFornitore = String(fattura.fornitore_metodo_pagamento || '').toLowerCase();
  if (metodoFornitore.includes('contant') || metodoFornitore === 'cassa' || metodoFornitore.includes('cash')) {
    return {
      variant: 'neutral',
      label: 'Previsto: Cassa',
      title: 'Metodo previsto in anagrafica; non prova che la fattura sia stata pagata.',
      verified: false,
    };
  }
  if (['bonifico', 'banca', 'bank', 'sepa', 'rid', 'sdd', 'addebito'].some(x => metodoFornitore.includes(x))) {
    return {
      variant: 'neutral',
      label: 'Previsto: Banca',
      title: 'Metodo previsto in anagrafica; non prova che la fattura sia stata pagata.',
      verified: false,
    };
  }
  return {
    variant: 'neutral',
    label: 'Non documentato',
    title: 'Nessuna prova di pagamento collegata.',
    verified: false,
  };
};

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
  const [ricercaFornitore, setRicercaFornitore] = useState('');
  const [statistiche, setStatistiche] = useState(null);
  const [loading, setLoading] = useState(true);
  const [pagina, setPagina] = useState(1);

  // Selezione multipla per export (richiesta utente 16/07/2026: "permettimi
  // di selezionare le fatture e di poterle scaricare in pdf ed excel").
  const [selezionate, setSelezionate] = useState(() => new Set());
  const [exportInCorso, setExportInCorso] = useState(null); // 'pdf' | 'excel' | null

  const toggleSelezione = id => {
    setSelezionate(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelezionaTutte = () => {
    setSelezionate(prev =>
      prev.size === fatture.length ? new Set() : new Set(fatture.map(f => f.id))
    );
  };

  const scaricaSelezione = async formato => {
    if (selezionate.size === 0) return;
    setExportInCorso(formato);
    try {
      const res = await api.post(
        '/api/fatture-ricevute/export-selezione',
        { ids: [...selezionate], formato },
        { responseType: 'blob' }
      );
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = formato === 'pdf' ? 'fatture_selezionate.pdf' : 'fatture_selezionate.xlsx';
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.error('Errore export: ' + (e.response?.data?.detail || e.message));
    } finally {
      setExportInCorso(null);
    }
  };

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

    const indiceFound = fatture.findIndex(f => f.id === invoiceIdFromUrl);
    const found = indiceFound >= 0 ? fatture[indiceFound] : null;

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
    setPagina(Math.floor(indiceFound / PER_PAGINA) + 1);
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
      params.append('limit', '6000');

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
      setPagina(1);
      setSelezionate(new Set()); // nuova lista → selezione azzerata
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

  const dopoAssociazioneAssegno = async data => {
    toast.success(data?.message || 'Assegno collegato alla fattura.');
    await Promise.all([fetchFatture(), fetchStatistiche()]);
  };

  // ==================== EFFECTS ====================

  useEffect(() => {
    fetchFatture();
    fetchStatistiche();
  }, [fetchFatture, anno]);

  useEffect(() => {
    fetchFornitori();
  }, []);

  const totalePagine = Math.max(1, Math.ceil(fatture.length / PER_PAGINA));
  const fattureVisibili = useMemo(
    () => fatture.slice((pagina - 1) * PER_PAGINA, pagina * PER_PAGINA),
    [fatture, pagina]
  );
  const fornitoriFiltrati = useMemo(() => {
    const query = ricercaFornitore.trim().toLowerCase();
    if (!query) return fornitori;
    return fornitori.filter(f =>
      `${f.ragione_sociale || ''} ${f.partita_iva || ''}`.toLowerCase().includes(query)
    );
  }, [fornitori, ricercaFornitore]);

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
                    onClick={() => setFatturaView({ id: invoiceNotFoundWarning.id, numero: invoiceNotFoundWarning.numero })}
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
            gridTemplateColumns: isMobile ? 'repeat(2, minmax(0, 1fr))' : 'repeat(4, minmax(120px, 1fr))',
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

      {/* Filtri — su mobile griglia 2 colonne compatta (prima ogni campo
          occupava una riga intera e la card mangiava tutto lo schermo) */}
      <Card style={{ marginBottom: isMobile ? 12 : 20, ...(isMobile ? { padding: 12 } : {}) }}>
        <div
          style={
            isMobile
              ? { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }
              : { display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }
          }
        >
          <div>
            <label style={{ fontSize: 11, color: COLORS.textMuted, display: 'block', marginBottom: 2 }}>
              Anno
            </label>
            <div
              style={{
                padding: isMobile ? '8px 10px' : '9px 12px',
                borderRadius: BORDER_RADIUS.sm,
                border: `1px solid ${COLORS.border}`,
                minWidth: isMobile ? 0 : 80,
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
            <label htmlFor="filtro-mese-fatture" style={{ fontSize: 11, color: COLORS.textMuted, display: 'block', marginBottom: 2 }}>
              Mese
            </label>
            <Select
              id="filtro-mese-fatture"
              value={mese}
              onChange={e => setHs('mese', e.target.value)}
              style={{ minWidth: isMobile ? 0 : 110, width: isMobile ? '100%' : undefined, fontSize: 13 }}
            >
              {MESI.map(m => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <label htmlFor="filtro-fornitore-fatture" style={{ fontSize: 11, color: COLORS.textMuted, display: 'block', marginBottom: 2 }}>
              Fornitore
            </label>
            <Input
              aria-label="Filtra elenco fornitori"
              placeholder={`Filtra ${fornitori.length} fornitori...`}
              value={ricercaFornitore}
              onChange={e => setRicercaFornitore(e.target.value)}
              style={{ width: '100%', marginBottom: 6, fontSize: 12 }}
            />
            <Select
              id="filtro-fornitore-fatture"
              value={fornitore}
              onChange={e => setHs('fornitore', e.target.value)}
              style={{ minWidth: isMobile ? 0 : 180, width: isMobile ? '100%' : undefined, fontSize: 13 }}
            >
              <option value="">Tutti i fornitori</option>
              {fornitoriFiltrati.map(f => (
                <option key={f.partita_iva} value={f.partita_iva}>
                  {f.ragione_sociale} ({f.partita_iva})
                </option>
              ))}
            </Select>
          </div>
          <div>
            <label htmlFor="filtro-stato-fatture" style={{ fontSize: 11, color: COLORS.textMuted, display: 'block', marginBottom: 2 }}>
              Stato
            </label>
            <Select
              id="filtro-stato-fatture"
              value={stato}
              onChange={e => setHs('stato', e.target.value)}
              style={{ minWidth: isMobile ? 0 : 100, width: isMobile ? '100%' : undefined, fontSize: 13 }}
            >
              <option value="">Tutti</option>
              <option value="importata">Importate</option>
              <option value="anomala">Anomale</option>
              <option value="pagata">Pagate</option>
              <option value="senza_metodo">🔍 ⚠️ Senza metodo pagamento</option>
            </Select>
          </div>
          <div style={isMobile ? { gridColumn: '1 / -1' } : { flex: 1, minWidth: 180 }}>
            <label htmlFor="ricerca-fatture" style={{ fontSize: 11, color: COLORS.textMuted, display: 'block', marginBottom: 2 }}>
              Ricerca
            </label>
            <div style={{ display: 'flex', gap: 8 }}>
              <Input
                id="ricerca-fatture"
                type="text"
                placeholder="Numero fattura, fornitore..."
                value={search}
                onChange={e => setHs('search', e.target.value)}
                onKeyDown={e => e.key === 'Enter' && setDebouncedSearch(search)}
                style={{ fontSize: 13, flex: 1 }}
              />
              <Button
                variant="primary"
                size="sm"
                onClick={() => {
                  setDebouncedSearch(search);
                  fetchFatture();
                }}
                style={{ fontSize: 13, flexShrink: 0 }}
              >
                Cerca
              </Button>
              {!isMobile && <CopyLinkButton />}
            </div>
          </div>
        </div>
      </Card>

      {/* Barra selezione: appare quando almeno una fattura è spuntata */}
      {selezionate.size > 0 && (
        <div
          data-testid="barra-selezione-fatture"
          style={{
            position: 'sticky', top: 8, zIndex: 20,
            display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
            background: '#0f2744', color: 'white',
            borderRadius: BORDER_RADIUS.lg, padding: '10px 14px',
            marginBottom: 12, boxShadow: SHADOWS.md,
          }}
        >
          <strong style={{ fontSize: 13 }}>
            {selezionate.size} {selezionate.size === 1 ? 'fattura selezionata' : 'fatture selezionate'}
          </strong>
          <Button
            variant="secondary"
            size="sm"
            disabled={!!exportInCorso}
            onClick={() => scaricaSelezione('pdf')}
            data-testid="scarica-selezione-pdf"
          >
            {exportInCorso === 'pdf' ? '⏳ PDF...' : '📄 Scarica PDF'}
          </Button>
          <Button
            variant="secondary"
            size="sm"
            disabled={!!exportInCorso}
            onClick={() => scaricaSelezione('excel')}
            data-testid="scarica-selezione-excel"
          >
            {exportInCorso === 'excel' ? '⏳ Excel...' : '📊 Scarica Excel'}
          </Button>
          <button
            onClick={() => setSelezionate(new Set())}
            style={{
              marginLeft: 'auto', background: 'transparent', border: 'none',
              color: 'white', cursor: 'pointer', fontSize: 13, fontWeight: 600,
            }}
            title="Deseleziona tutto"
          >
            ✕ Deseleziona
          </button>
        </div>
      )}

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
            <label
              style={{
                display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5,
                color: COLORS.textMuted, fontWeight: 600, padding: '2px 2px 0',
              }}
            >
              <input
                type="checkbox"
                checked={fatture.length > 0 && selezionate.size === fatture.length}
                onChange={toggleSelezionaTutte}
                style={{ width: 18, height: 18, accentColor: '#0f2744' }}
                data-testid="seleziona-tutte-fatture"
              />
              Seleziona tutte ({fatture.length})
            </label>
            {fattureVisibili.map((f, idx) => {
              const isPaid = f.pagato || f.status === 'paid' || f.stato_pagamento === 'pagata';
              const tipoDoc = tipoDocumento(f);
              const isCreditNote = ['TD04', 'TD08'].includes(tipoDoc.codice);
              const allocationConflict = statoAllocazione(f) === 'conflicting';
              const isRiconciliata = f.riconciliato === true;
              const pagamento = descriviPagamento(f);

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
                    onClick={() => setFatturaView({ id: f.id, numero: f.invoice_number || f.numero_documento || f.numero_fattura })}
                    style={{ minHeight: 40, display: 'inline-flex', alignItems: 'center', gap: 7 }}
                  >
                    <Eye size={17} aria-hidden="true" /> Vedi
                  </Button>
                  {!isPaid && !isRiconciliata && !isCreditNote && !allocationConflict && (
                    <AssociaAssegnoFattura
                      fattura={f}
                      onSuccess={dopoAssociazioneAssegno}
                    />
                  )}
                  <Badge variant={pagamento.variant} style={{ fontSize: 11 }} title={pagamento.title}>
                    {pagamento.label}
                  </Badge>
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
                    <input
                      type="checkbox"
                      checked={selezionate.has(f.id)}
                      onChange={() => toggleSelezione(f.id)}
                      style={{ width: 20, height: 20, marginTop: 1, flexShrink: 0, accentColor: '#0f2744' }}
                      data-testid={`seleziona-fattura-${f.id}`}
                    />
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
                    <span title={tipoDoc.nome} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, whiteSpace: 'nowrap', color: COLORS.info, fontWeight: 650 }}>
                      <FileText size={14} aria-hidden="true" /> {tipoDoc.codice}
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
                  <Th align="center" style={{ width: 36 }}>
                    <input
                      type="checkbox"
                      checked={fatture.length > 0 && selezionate.size === fatture.length}
                      onChange={toggleSelezionaTutte}
                      style={{ width: 16, height: 16, accentColor: '#0f2744', cursor: 'pointer' }}
                      title="Seleziona tutte"
                      data-testid="seleziona-tutte-fatture"
                    />
                  </Th>
                  <Th>Data</Th>
                  <Th>Numero</Th>
                  <Th>Tipo</Th>
                  <Th>Fornitore</Th>
                  <Th align="right">Imponibile</Th>
                  <Th align="right">IVA</Th>
                  <Th align="right">Totale</Th>
                  <Th align="left" style={{ minWidth: 190 }}>
                    Pagamento / prova
                  </Th>
                  <Th align="center" style={{ minWidth: 190 }}>
                    Azioni
                  </Th>
                </tr>
              </thead>
              <tbody>
                {fattureVisibili.map((f, idx) => {
                  const isPaid = f.pagato || f.status === 'paid' || f.stato_pagamento === 'pagata';
                  const tipoDoc = tipoDocumento(f);
                  const isCreditNote = ['TD04', 'TD08'].includes(tipoDoc.codice);
                  const allocationConflict = statoAllocazione(f) === 'conflicting';
                  const isRiconciliata = f.riconciliato === true;
                  const pagamento = descriviPagamento(f);
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
                      <Td align="center">
                        <input
                          type="checkbox"
                          checked={selezionate.has(f.id)}
                          onChange={() => toggleSelezione(f.id)}
                          style={{ width: 16, height: 16, accentColor: '#0f2744', cursor: 'pointer' }}
                          data-testid={`seleziona-fattura-${f.id}`}
                        />
                      </Td>
                      <Td>{formatDateIT(f.invoice_date || f.data_documento)}</Td>
                      <Td style={{ fontWeight: 600, color: COLORS.primary }}>
                        {f.invoice_number || f.numero_documento}
                      </Td>
                      <Td>
                        <span title={tipoDoc.nome} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, minHeight: 30, padding: '4px 8px', borderRadius: 7, background: COLORS.infoLight, color: COLORS.info, fontSize: 11, fontWeight: 700, whiteSpace: 'nowrap' }}>
                          <FileText size={15} aria-hidden="true" /> {tipoDoc.codice}
                        </span>
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
                      <Td>
                        <Badge variant={pagamento.variant} title={pagamento.title}>
                          {pagamento.label}
                        </Badge>
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
                            onClick={() => setFatturaView({ id: f.id, numero: f.invoice_number || f.numero_documento || f.numero_fattura })}
                            style={{ minHeight: 40, display: 'inline-flex', alignItems: 'center', gap: 7 }}
                          >
                            <Eye size={17} aria-hidden="true" /> Vedi
                          </Button>
                          {!isPaid && !isRiconciliata && !isCreditNote && !allocationConflict && (
                            <AssociaAssegnoFattura
                              fattura={f}
                              onSuccess={dopoAssociazioneAssegno}
                            />
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
      {fatture.length > PER_PAGINA && (
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 12, marginTop: 16, padding: 12, background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: BORDER_RADIUS.md }}>
          <Button
            variant="secondary"
            onClick={() => setPagina(p => Math.max(1, p - 1))}
            disabled={pagina === 1}
            aria-label="Pagina precedente"
            style={{ width: 44, height: 44, padding: 0, justifyContent: 'center' }}
          >
            <ChevronLeft size={21} />
          </Button>
          <div style={{ minWidth: 150, textAlign: 'center', fontSize: 13, color: COLORS.gray[700] }}>
            <strong>Pagina {pagina} di {totalePagine}</strong>
            <div style={{ fontSize: 11, color: COLORS.textMuted, marginTop: 2 }}>
              {fatture.length} fatture totali
            </div>
          </div>
          <Button
            variant="secondary"
            onClick={() => setPagina(p => Math.min(totalePagine, p + 1))}
            disabled={pagina === totalePagine}
            aria-label="Pagina successiva"
            style={{ width: 44, height: 44, padding: 0, justifyContent: 'center' }}
          >
            <ChevronRight size={21} />
          </Button>
        </div>
      )}
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
