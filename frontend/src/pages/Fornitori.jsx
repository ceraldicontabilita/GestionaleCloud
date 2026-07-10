import React, { useState, useEffect, useCallback, useRef } from 'react';
import ReactDOM from 'react-dom';
import { useNavigate, Link } from 'react-router-dom';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import Portal from '../components/Portal';
import { PageLayout } from '../components/PageLayout';
import {
  formatEuro,
  formatDateIT,
  STYLES,
  COLORS,
  SHADOWS,
  BORDER_RADIUS,
  FONT,
  button,
  badge,
  useIsMobile,
  RG,
  pagePad,
} from '../lib/utils';
import { useHashState } from '../hooks/useHashState';
import { CopyLinkButton } from '../components/CopyLinkButton';
import {
  Button,
  Badge,
  StatCard,
  TableWrap,
  Table,
  Th,
  Td,
  ListaAdattiva,
  RowActions,
  RowActionButton,
} from '../components/ds';
import {
  Search,
  Edit2,
  Trash2,
  Plus,
  FileText,
  Building2,
  Phone,
  CreditCard,
  AlertCircle,
  Check,
  Users,
  X,
  TrendingUp,
  RefreshCw,
} from 'lucide-react';

// Hook per debounce
function useDebounce(value, delay) {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    return () => {
      clearTimeout(handler);
    };
  }, [value, delay]);

  return debouncedValue;
}

// Dizionario Metodi di Pagamento — SOLO 3: cassa, banca, misto.
// Coerente con la mappa già usata dal backend per instradare le fatture in
// Prima Nota (app/routers/suppliers_module/common.py::PAYMENT_METHODS):
// contanti->cassa, {assegno,bonifico,rid,carta}->banca, misto->provvisorio.
// "certo" è stato rimosso: il sistema non saprebbe dove imputare
// automaticamente il pagamento in quel caso, quindi non è un canale valido.
const METODI_PAGAMENTO = {
  cassa: { label: 'Cassa', bg: COLORS.successLight, color: COLORS.success },
  banca: { label: 'Banca', bg: COLORS.infoLight, color: COLORS.info },
  misto: { label: 'Misto', bg: COLORS.gray[200], color: COLORS.primary },
};

// Valori legacy ancora presenti sui fornitori già salvati prima della
// semplificazione a 3 metodi — tradotti in sola lettura per continuare a
// mostrare/filtrare correttamente i dati esistenti senza una migrazione.
// DEVE restare allineata alla regola unica del backend
// (app/engines/prima_nota_engine.py): ogni strumento che transita dal
// conto corrente -> banca; contanti/contrassegno -> cassa.
const METODO_LEGACY_A_CANONICO = {
  contanti: 'cassa',
  contante: 'cassa',
  cash: 'cassa',
  contrassegno: 'cassa',
  assegno: 'banca',
  bonifico: 'banca',
  'bonifico bancario': 'banca',
  bancario: 'banca',
  bancomat: 'banca',
  rid: 'banca',
  riba: 'banca',
  sepa: 'banca',
  sdd: 'banca',
  mav: 'banca',
  rav: 'banca',
  carta: 'banca',
  'carta di credito': 'banca',
  paypal: 'banca',
  stripe: 'banca',
  domiciliazione: 'banca',
};

// Canale (cassa/banca/misto) da un valore grezzo, anche legacy.
const canaleCanonico = raw => {
  const key = (raw || '').toLowerCase().trim();
  return METODO_LEGACY_A_CANONICO[key] || key;
};

// Metodo canonico (cassa/banca/misto) di un fornitore, a partire dal valore
// grezzo salvato (anche legacy).
const metodoCanonico = supplier => canaleCanonico(supplier?.metodo_pagamento);

const getMetodo = key => METODI_PAGAMENTO[key] || METODI_PAGAMENTO.banca;

const emptySupplier = {
  ragione_sociale: '',
  partita_iva: '',
  codice_fiscale: '',
  indirizzo: '',
  cap: '',
  comune: '',
  provincia: '',
  nazione: 'IT',
  telefono: '',
  email: '',
  pec: '',
  iban: '',
  iban_lista: [], // Lista di IBAN aggiuntivi estratti dalle fatture
  metodo_pagamento: 'banca',
  giorni_pagamento: 30,
  esclude_magazzino: false,
  note: '',
};

// Modale Fornitore
function SupplierModal({ isOpen, onClose, supplier, onSave, saving }) {
  const isMobile = useIsMobile();
  const [form, setForm] = useState(emptySupplier);
  const [loadingOpenAPI, setLoadingOpenAPI] = useState(false);
  const [openAPIError, setOpenAPIError] = useState(null);
  const [loadingXML, setLoadingXML] = useState(false);
  const [xmlMsg, setXmlMsg] = useState(null);
  const isNew = !supplier?.id;

  useEffect(() => {
    if (isOpen && supplier) {
      setForm({
        ...emptySupplier,
        ...supplier,
        ragione_sociale: supplier.ragione_sociale || supplier.nome || supplier.denominazione || '',
        partita_iva: supplier.partita_iva || supplier.piva || '',
      });
    } else if (isOpen) {
      setForm(emptySupplier);
    }
    setOpenAPIError(null);
    setXmlMsg(null);
  }, [isOpen, supplier]);

  const handleChange = (field, value) => {
    setForm(prev => ({ ...prev, [field]: value }));
  };

  // Carica dati da OpenAPI.it
  const handleLoadFromOpenAPI = async () => {
    const piva = form.partita_iva?.replace(/\s/g, '');
    if (!piva || piva.length !== 11) {
      setOpenAPIError('Inserisci una Partita IVA valida (11 cifre)');
      return;
    }

    setLoadingOpenAPI(true);
    setOpenAPIError(null);

    try {
      const res = await api.get(`/api/openapi-imprese/info/${piva}`);
      if (res.data.success) {
        const mapped = res.data.campi_mappati;
        // Aggiorna form con dati OpenAPI
        setForm(prev => ({
          ...prev,
          ragione_sociale: mapped.ragione_sociale || prev.ragione_sociale,
          codice_fiscale: mapped.codice_fiscale || prev.codice_fiscale,
          indirizzo: mapped.indirizzo || prev.indirizzo,
          cap: mapped.cap || prev.cap,
          comune: mapped.citta || prev.comune,
          provincia: mapped.provincia || prev.provincia,
          pec: mapped.pec || prev.pec,
          codice_sdi: mapped.codice_sdi || prev.codice_sdi,
        }));
      }
    } catch (err) {
      setOpenAPIError(err.response?.data?.detail || 'Errore nel recupero dati');
    } finally {
      setLoadingOpenAPI(false);
    }
  };

  // Popola dati mancanti dagli XML delle fatture
  const handlePopolaDaXml = async () => {
    const fId = supplier?.id || form.partita_iva;
    if (!fId) return;
    setLoadingXML(true);
    setXmlMsg(null);
    try {
      const res = await api.post(`/api/schede-tecniche/popola-fornitore/${fId}`);
      const d = res.data;
      if (d.success && d.dati_estratti) {
        const dati = d.dati_estratti;
        setForm(prev => ({
          ...prev,
          telefono: dati.telefono || prev.telefono,
          email: dati.email || prev.email,
          indirizzo: dati.indirizzo || prev.indirizzo,
          cap: dati.cap || prev.cap,
          comune: dati.comune || prev.comune,
          provincia: dati.provincia || prev.provincia,
          ragione_sociale: dati.ragione_sociale || prev.ragione_sociale,
        }));
        setXmlMsg(
          `Estratti da ${d.xml_letti} fatture: ${(d.campi_aggiornati ?? []).join(', ') || 'nessun campo nuovo'}`
        );
      } else {
        setXmlMsg(d.message || 'Nessun dato trovato negli XML');
      }
    } catch (err) {
      setXmlMsg('Errore nel leggere le fatture XML del fornitore');
    } finally {
      setLoadingXML(false);
    }
  };

  const handleSubmit = () => {
    if (!form.ragione_sociale) {
      alert('Inserisci la ragione sociale');
      return;
    }
    onSave(form);
  };

  if (!isOpen) return null;

  return (
    <Portal>
      <div
        style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(0,0,0,0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 99999,
          padding: '20px',
        }}
        onClick={onClose}
      >
        <div
          style={{
            backgroundColor: COLORS.card,
            borderRadius: BORDER_RADIUS.lg,
            width: '100%',
            maxWidth: '600px',
            maxHeight: '85vh',
            overflow: 'hidden',
            boxShadow: SHADOWS.modal,
          }}
          onClick={e => e.stopPropagation()}
        >
          {/* Header */}
          <div
            style={{
              background: COLORS.primary,
              padding: '20px 24px',
              color: 'white',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <h2 style={{ margin: 0, fontSize: '20px', fontWeight: 600 }}>
                  {isNew ? 'Nuovo Fornitore' : 'Modifica Anagrafica'}
                </h2>
                <p style={{ margin: '4px 0 0', opacity: 0.9, fontSize: '14px' }}>
                  {isNew ? 'Inserisci i dati del fornitore' : form.ragione_sociale}
                </p>
              </div>
              <Button
                variant="ghost"
                onClick={onClose}
                aria-label="Chiudi"
                style={{
                  background: 'rgba(255,255,255,0.2)',
                  minWidth: '40px',
                  minHeight: '40px',
                  padding: 0,
                  color: 'white',
                }}
              >
                <X size={20} />
              </Button>
            </div>
          </div>

          {/* Form */}
          <div style={{ padding: '24px', overflowY: 'auto', maxHeight: 'calc(85vh - 140px)' }}>
            <div style={{ display: 'grid', gap: '16px' }}>
              {/* Alert dati mancanti */}
              {!isNew && (!form.email || !form.telefono) && (
                <div
                  style={{
                    padding: '12px 16px',
                    background: COLORS.warningLight,
                    border: `1px solid ${COLORS.warning}`,
                    borderRadius: BORDER_RADIUS.lg,
                    display: 'flex',
                    alignItems: 'flex-start',
                    justifyContent: 'space-between',
                    gap: '12px',
                  }}
                >
                  <div style={{ display: 'flex', gap: '10px', alignItems: 'flex-start', flex: 1 }}>
                    <AlertCircle
                      size={18}
                      color={COLORS.warning}
                      style={{ flexShrink: 0, marginTop: 2 }}
                    />
                    <div>
                      <div
                        style={{
                          fontSize: '13px',
                          fontWeight: 600,
                          color: COLORS.warning,
                          marginBottom: '2px',
                        }}
                      >
                        Dati mancanti:{' '}
                        {[!form.email && 'Email', !form.telefono && 'Telefono']
                          .filter(Boolean)
                          .join(', ')}
                      </div>
                      <div style={{ fontSize: '12px', color: COLORS.warning }}>
                        Compilare manualmente o usa "Cerca in fatture" per leggere dagli XML
                      </div>
                    </div>
                  </div>
                  <Button
                    type="button"
                    variant="warning"
                    size="sm"
                    onClick={handlePopolaDaXml}
                    disabled={loadingXML}
                    style={{ flexShrink: 0, whiteSpace: 'nowrap' }}
                  >
                    {loadingXML ? 'Ricerca...' : 'Cerca in fatture'}
                  </Button>
                </div>
              )}

              {/* Messaggio esito lettura XML */}
              {xmlMsg && (
                <div
                  style={{
                    padding: '10px 14px',
                    background: COLORS.successLight,
                    border: `1px solid ${COLORS.success}`,
                    borderRadius: BORDER_RADIUS.md,
                    fontSize: '12px',
                    color: COLORS.success,
                  }}
                >
                  {xmlMsg}
                </div>
              )}
              <div>
                <label
                  style={{
                    display: 'block',
                    fontSize: '13px',
                    fontWeight: 500,
                    color: COLORS.gray[700],
                    marginBottom: '6px',
                  }}
                >
                  Ragione Sociale *
                </label>
                <input
                  type="text"
                  value={form.ragione_sociale || ''}
                  onChange={e => handleChange('ragione_sociale', e.target.value)}
                  style={{
                    width: '100%',
                    padding: '10px 14px',
                    border: `1px solid ${COLORS.border}`,
                    borderRadius: BORDER_RADIUS.md,
                    fontSize: '14px',
                    boxSizing: 'border-box',
                  }}
                  placeholder="Nome azienda"
                />
              </div>

              {/* P.IVA e CF */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr',
                  gap: '12px',
                }}
              >
                <div>
                  <label
                    style={{
                      display: 'block',
                      fontSize: '13px',
                      fontWeight: 500,
                      color: COLORS.gray[700],
                      marginBottom: '6px',
                    }}
                  >
                    Partita IVA
                  </label>
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <input
                      type="text"
                      value={form.partita_iva || ''}
                      onChange={e => handleChange('partita_iva', e.target.value)}
                      style={{
                        flex: 1,
                        padding: '10px 14px',
                        border: `1px solid ${COLORS.border}`,
                        borderRadius: BORDER_RADIUS.md,
                        fontSize: '14px',
                        fontFamily: 'monospace',
                        boxSizing: 'border-box',
                      }}
                      placeholder="01234567890"
                    />
                    <Button
                      type="button"
                      variant="primary"
                      size="sm"
                      onClick={handleLoadFromOpenAPI}
                      disabled={loadingOpenAPI || !form.partita_iva}
                      title="Carica dati da Camera di Commercio"
                      style={{ whiteSpace: 'nowrap' }}
                      data-testid="btn-load-openapi"
                    >
                      <RefreshCw size={14} className={loadingOpenAPI ? 'animate-spin' : ''} />
                      {loadingOpenAPI ? '...' : 'Auto'}
                    </Button>
                  </div>
                  {openAPIError && (
                    <p style={{ margin: '4px 0 0', fontSize: '12px', color: COLORS.danger }}>
                      {openAPIError}
                    </p>
                  )}
                </div>
                <div>
                  <label
                    style={{
                      display: 'block',
                      fontSize: '13px',
                      fontWeight: 500,
                      color: COLORS.gray[700],
                      marginBottom: '6px',
                    }}
                  >
                    Codice Fiscale
                  </label>
                  <input
                    type="text"
                    value={form.codice_fiscale || ''}
                    onChange={e => handleChange('codice_fiscale', e.target.value.toUpperCase())}
                    style={{
                      width: '100%',
                      padding: '10px 14px',
                      border: `1px solid ${COLORS.border}`,
                      borderRadius: BORDER_RADIUS.md,
                      fontSize: '14px',
                      fontFamily: 'monospace',
                      boxSizing: 'border-box',
                    }}
                  />
                </div>
              </div>

              {/* Indirizzo */}
              <div>
                <label
                  style={{
                    display: 'block',
                    fontSize: '13px',
                    fontWeight: 500,
                    color: COLORS.gray[700],
                    marginBottom: '6px',
                  }}
                >
                  Indirizzo
                </label>
                <input
                  type="text"
                  value={form.indirizzo || ''}
                  onChange={e => handleChange('indirizzo', e.target.value)}
                  style={{
                    width: '100%',
                    padding: '10px 14px',
                    border: `1px solid ${COLORS.border}`,
                    borderRadius: BORDER_RADIUS.md,
                    fontSize: '14px',
                    boxSizing: 'border-box',
                  }}
                  placeholder="Via, numero civico"
                />
              </div>

              {/* CAP, Comune, Provincia */}
              <div style={{ display: 'grid', gridTemplateColumns: '100px 1fr 80px', gap: '12px' }}>
                <div>
                  <label
                    style={{
                      display: 'block',
                      fontSize: '13px',
                      fontWeight: 500,
                      color: COLORS.gray[700],
                      marginBottom: '6px',
                    }}
                  >
                    CAP
                  </label>
                  <input
                    type="text"
                    value={form.cap || ''}
                    onChange={e => handleChange('cap', e.target.value)}
                    style={{
                      width: '100%',
                      padding: '10px 14px',
                      border: `1px solid ${COLORS.border}`,
                      borderRadius: BORDER_RADIUS.md,
                      fontSize: '14px',
                      boxSizing: 'border-box',
                    }}
                    maxLength={5}
                  />
                </div>
                <div>
                  <label
                    style={{
                      display: 'block',
                      fontSize: '13px',
                      fontWeight: 500,
                      color: COLORS.gray[700],
                      marginBottom: '6px',
                    }}
                  >
                    Comune
                  </label>
                  <input
                    type="text"
                    value={form.comune || ''}
                    onChange={e => handleChange('comune', e.target.value)}
                    style={{
                      width: '100%',
                      padding: '10px 14px',
                      border: `1px solid ${COLORS.border}`,
                      borderRadius: BORDER_RADIUS.md,
                      fontSize: '14px',
                      boxSizing: 'border-box',
                    }}
                  />
                </div>
                <div>
                  <label
                    style={{
                      display: 'block',
                      fontSize: '13px',
                      fontWeight: 500,
                      color: COLORS.gray[700],
                      marginBottom: '6px',
                    }}
                  >
                    Prov
                  </label>
                  <input
                    type="text"
                    value={form.provincia || ''}
                    onChange={e => handleChange('provincia', e.target.value.toUpperCase())}
                    style={{
                      width: '100%',
                      padding: '10px 14px',
                      border: `1px solid ${COLORS.border}`,
                      borderRadius: BORDER_RADIUS.md,
                      fontSize: '14px',
                      boxSizing: 'border-box',
                    }}
                    maxLength={2}
                  />
                </div>
              </div>

              {/* Telefono, Email */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr',
                  gap: '12px',
                }}
              >
                <div>
                  <label
                    style={{
                      display: 'block',
                      fontSize: '13px',
                      fontWeight: 500,
                      color: COLORS.gray[700],
                      marginBottom: '6px',
                    }}
                  >
                    Telefono
                  </label>
                  <input
                    type="tel"
                    value={form.telefono || ''}
                    onChange={e => handleChange('telefono', e.target.value)}
                    style={{
                      width: '100%',
                      padding: '10px 14px',
                      border: `1px solid ${COLORS.border}`,
                      borderRadius: BORDER_RADIUS.md,
                      fontSize: '14px',
                      boxSizing: 'border-box',
                    }}
                  />
                </div>
                <div>
                  <label
                    style={{
                      display: 'block',
                      fontSize: '13px',
                      fontWeight: 500,
                      color: COLORS.gray[700],
                      marginBottom: '6px',
                    }}
                  >
                    Email
                  </label>
                  <input
                    type="email"
                    value={form.email || ''}
                    onChange={e => handleChange('email', e.target.value)}
                    style={{
                      width: '100%',
                      padding: '10px 14px',
                      border: `1px solid ${COLORS.border}`,
                      borderRadius: BORDER_RADIUS.md,
                      fontSize: '14px',
                      boxSizing: 'border-box',
                    }}
                  />
                </div>
              </div>

              {/* Metodo pagamento e giorni */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr',
                  gap: '12px',
                }}
              >
                <div>
                  <label
                    style={{
                      display: 'block',
                      fontSize: '13px',
                      fontWeight: 500,
                      color: COLORS.gray[700],
                      marginBottom: '6px',
                    }}
                  >
                    Metodo Pagamento
                  </label>
                  <select
                    value={canaleCanonico(form.metodo_pagamento) || 'banca'}
                    onChange={e => handleChange('metodo_pagamento', e.target.value)}
                    style={{
                      width: '100%',
                      padding: '10px 14px',
                      border: `1px solid ${COLORS.border}`,
                      borderRadius: BORDER_RADIUS.md,
                      fontSize: '14px',
                      backgroundColor: 'white',
                      boxSizing: 'border-box',
                    }}
                  >
                    {Object.entries(METODI_PAGAMENTO).map(([key, val]) => (
                      <option key={key} value={key}>
                        {val.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label
                    style={{
                      display: 'block',
                      fontSize: '13px',
                      fontWeight: 500,
                      color: COLORS.gray[700],
                      marginBottom: '6px',
                    }}
                  >
                    Giorni Pagamento
                  </label>
                  <input
                    type="number"
                    value={form.giorni_pagamento || 30}
                    onChange={e => handleChange('giorni_pagamento', parseInt(e.target.value) || 30)}
                    style={{
                      width: '100%',
                      padding: '10px 14px',
                      border: `1px solid ${COLORS.border}`,
                      borderRadius: BORDER_RADIUS.md,
                      fontSize: '14px',
                      boxSizing: 'border-box',
                    }}
                    min={0}
                  />
                </div>
              </div>

              {/* IBAN e lista IBAN aggiuntivi */}
              <div>
                <label
                  style={{
                    display: 'block',
                    fontSize: '13px',
                    fontWeight: 500,
                    color: COLORS.gray[700],
                    marginBottom: '6px',
                  }}
                >
                  IBAN Principale
                </label>
                <input
                  type="text"
                  value={form.iban || ''}
                  onChange={e =>
                    handleChange('iban', e.target.value.toUpperCase().replace(/\s/g, ''))
                  }
                  style={{
                    width: '100%',
                    padding: '10px 14px',
                    border: `1px solid ${COLORS.border}`,
                    borderRadius: BORDER_RADIUS.md,
                    fontSize: '14px',
                    fontFamily: 'monospace',
                    boxSizing: 'border-box',
                  }}
                  placeholder="IT60X0542811101000000123456"
                />
                {/* Lista IBAN aggiuntivi */}
                {form.iban_lista && form.iban_lista.length > 0 && (
                  <div
                    style={{
                      marginTop: '8px',
                      padding: '10px',
                      background: COLORS.bgAlt,
                      borderRadius: BORDER_RADIUS.sm,
                    }}
                  >
                    <div style={{ fontSize: '12px', color: COLORS.textMuted, marginBottom: '6px' }}>
                      IBAN aggiuntivi (da fatture):
                    </div>
                    {(form.iban_lista ?? []).map((iban, idx) => (
                      <div
                        key={idx}
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          padding: '4px 8px',
                          background: 'white',
                          borderRadius: BORDER_RADIUS.sm,
                          marginBottom: '4px',
                          fontSize: '12px',
                          fontFamily: 'monospace',
                        }}
                      >
                        <span>{iban}</span>
                        <Button
                          type="button"
                          variant="info"
                          size="sm"
                          onClick={() => handleChange('iban', iban)}
                          style={{ padding: '2px 8px', fontSize: '11px' }}
                        >
                          Usa come principale
                        </Button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Nota: il toggle "Esclude dal Magazzino" è ora un badge cliccabile
                direttamente sulla card del fornitore (accanto al metodo di pagamento).
                Basta cliccare su "📦 In magazzino" / "🚫 Escluso magazzino" per cambiare. */}
            </div>
          </div>

          {/* Footer */}
          <div
            style={{
              padding: '16px 24px',
              borderTop: `1px solid ${COLORS.border}`,
              display: 'flex',
              justifyContent: 'flex-end',
              gap: '12px',
              backgroundColor: COLORS.bgAlt,
            }}
          >
            <Button variant="secondary" onClick={onClose}>
              Annulla
            </Button>
            <Button variant="primary" onClick={handleSubmit} disabled={saving}>
              {saving ? (
                'Salvataggio...'
              ) : (
                <>
                  <Check size={16} /> Salva
                </>
              )}
            </Button>
          </div>
        </div>
      </div>
    </Portal>
  );
}

// Badge metodo pagamento (cassa/banca/misto) cliccabile con menu a comparsa:
// stessa logica della vecchia card fornitore, riusata per riga in ListaAdattiva.
function MetodoBadge({ supplier, onChangeMetodo }) {
  // NIENTE default fittizio: se il metodo non è impostato, la riga lo deve
  // DIRE (prima mostrava "Bonifico" e il filtro "senza metodo" sembrava rotto)
  const metodoKey = supplier.metodo_pagamento ? metodoCanonico(supplier) : '';
  const metodo = metodoKey
    ? getMetodo(metodoKey)
    : { label: '⚠️ Da impostare', color: COLORS.warning };
  const [showMetodoMenu, setShowMetodoMenu] = useState(false);
  const [updating, setUpdating] = useState(false);
  const [menuPosition, setMenuPosition] = useState({ top: 0, left: 0 });
  const buttonRef = React.useRef(null);

  const handleMetodoChange = async newMetodo => {
    if (newMetodo === metodoKey) {
      setShowMetodoMenu(false);
      return;
    }
    setUpdating(true);
    setShowMetodoMenu(false);
    await onChangeMetodo(supplier.id, newMetodo);
    setUpdating(false);
  };

  const openMenu = () => {
    if (buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      const menuHeight = 280; // altezza stimata del menu
      const spaceBelow = window.innerHeight - rect.bottom;

      // Se non c'è spazio sotto, posiziona sopra
      if (spaceBelow < menuHeight) {
        setMenuPosition({
          top: rect.top - menuHeight - 4,
          left: rect.right - 170,
        });
      } else {
        setMenuPosition({
          top: rect.bottom + 4,
          left: rect.right - 170,
        });
      }
    }
    setShowMetodoMenu(true);
  };

  return (
    <>
      {/* Resta un <button> nativo (non <Button>) perché serve un ref DOM
          reale per calcolare la posizione del menu a comparsa. */}
      <button
        ref={buttonRef}
        onClick={openMenu}
        disabled={updating}
        style={{
          padding: '6px 12px',
          borderRadius: BORDER_RADIUS.sm,
          fontSize: '12px',
          fontWeight: 600,
          backgroundColor: metodo.bg,
          color: metodo.color,
          border: `2px solid ${metodo.color}20`,
          cursor: updating ? 'wait' : 'pointer',
          display: 'inline-flex',
          alignItems: 'center',
          gap: '4px',
          transition: 'all 0.2s',
          opacity: updating ? 0.6 : 1,
          fontFamily: FONT.family,
        }}
        title="Clicca per cambiare metodo pagamento"
      >
        <CreditCard size={12} />
        {updating ? '...' : metodo.label}
        <span style={{ marginLeft: '2px', fontSize: '10px' }}>▼</span>
      </button>

      {/* Menu dropdown con Portal - fuori dalla riga */}
      {showMetodoMenu && (
        <Portal>
          {/* Overlay per chiudere */}
          <div
            style={{
              position: 'fixed',
              inset: 0,
              zIndex: 99998,
              background: 'transparent',
            }}
            onClick={() => setShowMetodoMenu(false)}
          />
          {/* Menu */}
          <div
            style={{
              position: 'fixed',
              top: menuPosition.top,
              left: menuPosition.left,
              backgroundColor: 'white',
              borderRadius: BORDER_RADIUS.lg,
              boxShadow: SHADOWS.xl,
              border: `1px solid ${COLORS.border}`,
              overflow: 'hidden',
              zIndex: 99999,
              minWidth: '160px',
            }}
          >
            <div
              style={{
                padding: '8px 12px',
                borderBottom: `1px solid ${COLORS.bg}`,
                fontSize: '11px',
                color: COLORS.textSubtle,
                fontWeight: 600,
              }}
            >
              METODO PAGAMENTO
            </div>
            {Object.entries(METODI_PAGAMENTO).map(([key, val]) => (
              <Button
                key={key}
                variant="ghost"
                onClick={() => handleMetodoChange(key)}
                style={{
                  width: '100%',
                  borderRadius: 0,
                  padding: '7px 12px',
                  backgroundColor: metodoKey === key ? val.bg : 'white',
                  color: val.color,
                  justifyContent: 'flex-start',
                }}
              >
                <span
                  style={{
                    width: '10px',
                    height: '10px',
                    borderRadius: BORDER_RADIUS.full,
                    backgroundColor: val.color,
                  }}
                />
                {val.label}
                {metodoKey === key && <Check size={16} style={{ marginLeft: 'auto' }} />}
              </Button>
            ))}
          </div>
        </Portal>
      )}
    </>
  );
}

// Azioni per riga fornitore in formato compatto da tabella/card: le STESSE
// azioni della vecchia card (fatturato anno e anno-1, cerca P.IVA, schede
// tecniche, estratto fatture, modifica, elimina).
function AzioniFornitore({
  supplier,
  selectedYear,
  isMobile,
  onEdit,
  onDelete,
  onViewInvoices,
  onSearchPiva,
  onShowFatturato,
  onShowSchedeTecniche,
}) {
  const piva = supplier.partita_iva || supplier.piva || null;
  const hasPiva = !!piva;
  const [searching, setSearching] = useState(false);
  const [loadingFatturato, setLoadingFatturato] = useState(false);

  const handleShowFatturato = async anno => {
    setLoadingFatturato(true);
    await onShowFatturato(supplier, anno);
    setLoadingFatturato(false);
  };

  const handleSearchPiva = async () => {
    if (!piva) return;
    setSearching(true);
    await onSearchPiva(supplier);
    setSearching(false);
  };

  return (
    <RowActions
      style={{
        justifyContent: isMobile ? 'flex-end' : 'center',
        flexWrap: 'wrap',
        // Su mobile i bottoni vanno a capo su due righe dentro la card
        maxWidth: isMobile ? 160 : undefined,
      }}
    >
      {hasPiva && (
        <RowActionButton
          variant="info"
          onClick={() => handleShowFatturato(selectedYear)}
          disabled={loadingFatturato}
          title={`Visualizza fatturato ${selectedYear}`}
          data-testid={`btn-fatturato-${supplier.id}`}
          style={{ width: 'auto', padding: '0 6px', gap: 3, fontSize: 11, fontWeight: 600 }}
        >
          <TrendingUp size={13} /> {loadingFatturato ? '...' : selectedYear}
        </RowActionButton>
      )}
      <RowActionButton
        variant="neutral"
        onClick={() => handleShowFatturato(selectedYear - 1)}
        disabled={loadingFatturato}
        title={`Visualizza fatturato ${selectedYear - 1}`}
        style={{ width: 'auto', padding: '0 6px', gap: 3, fontSize: 11, fontWeight: 600 }}
      >
        <TrendingUp size={13} /> {selectedYear - 1}
      </RowActionButton>
      {hasPiva && (
        <RowActionButton
          onClick={handleSearchPiva}
          disabled={searching}
          title="Cerca dati azienda tramite Partita IVA"
          style={{ background: COLORS.warningLight, color: COLORS.warning }}
        >
          <Search size={14} />
        </RowActionButton>
      )}
      <RowActionButton
        variant="primary"
        onClick={() => onShowSchedeTecniche && onShowSchedeTecniche(supplier)}
        title="Visualizza schede tecniche prodotti"
        data-testid={`btn-schede-tecniche-${supplier.id}`}
      >
        📋
      </RowActionButton>
      <RowActionButton
        variant="neutral"
        onClick={() => onViewInvoices(supplier)}
        title="Estratto fatture"
      >
        <FileText size={14} />
      </RowActionButton>
      <RowActionButton
        variant="neutral"
        onClick={() => onEdit(supplier)}
        title="Modifica anagrafica"
      >
        <Edit2 size={14} />
      </RowActionButton>
      <RowActionButton
        variant="danger"
        onClick={() => onDelete(supplier.id)}
        title="Elimina fornitore"
      >
        <Trash2 size={14} />
      </RowActionButton>
    </RowActions>
  );
}

export default function Fornitori() {
  const isMobile = useIsMobile();
  const { anno: selectedYear } = useAnnoGlobale();
  const navigate = useNavigate();
  const [suppliers, setSuppliers] = useState([]);
  const [loading, setLoading] = useState(true);

  // Deep link: search e metodo sincronizzati con URL hash
  // es: /fornitori#search=rossi&metodo=bonifico
  const [hs, setHs] = useHashState({ search: '', metodo: 'tutti' });
  const search = hs.search;
  const setSearch = v => setHs('search', v);
  const filterMetodo = hs.metodo || 'tutti';
  const setFilterMetodo = v => setHs('metodo', v);

  const [filterIncomplete, setFilterIncomplete] = useState(false);
  const [filterSenzaMetodo, setFilterSenzaMetodo] = useState(false);
  // PR #5e850c8: filtri avanzati backend
  const [filterAnzianita, setFilterAnzianita] = useState('tutti'); // tutti | nuovo | storico
  const [giorniNuovo, setGiorniNuovo] = useState(90);
  const [filtroProdotto, setFiltroProdotto] = useState('');
  const debouncedProdotto = useDebounce(filtroProdotto, 500);
  const [totaliFiltrati, setTotaliFiltrati] = useState({
    totale_fornitori: 0,
    attivi: 0,
  });
  const [modalOpen, setModalOpen] = useState(false);
  const [currentSupplier, setCurrentSupplier] = useState(null);
  const [saving, setSaving] = useState(false);

  // === SCHEDE TECNICHE STATE ===
  const [schedeTecnicheModal, setSchedeTecnicheModal] = useState({
    open: false,
    fornitore: null,
    schede: [],
    loading: false,
  });

  // Debounce search per evitare troppe chiamate API
  const debouncedSearch = useDebounce(search, 500);

  // Ref per abort controller
  const abortControllerRef = useRef(null);

  // Carica dati quando il debounced search cambia
  useEffect(() => {
    // Cancella richiesta precedente
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    const controller = new AbortController();
    abortControllerRef.current = controller;

    const fetchData = async () => {
      try {
        setLoading(true);
        const params = new URLSearchParams();
        if (debouncedSearch) params.append('search', debouncedSearch);
        params.append('limit', '1000'); // Carica tutti i fornitori
        // PR #5e850c8: filtri avanzati
        if (filterAnzianita !== 'tutti') params.append('stato_anagrafica', filterAnzianita);
        if (giorniNuovo && giorniNuovo !== 90) params.append('giorni_nuovo', String(giorniNuovo));
        if (debouncedProdotto && debouncedProdotto.trim()) params.append('prodotto', debouncedProdotto.trim());

        const res = await api.get(`/api/suppliers/filtered?${params}`, {
          signal: controller.signal,
        });
        // Endpoint /filtered restituisce {items, count, totali, ...}
        setSuppliers(res.data.items || []);
        setTotaliFiltrati(res.data.totali || {
          totale_fornitori: 0,
          attivi: 0,
        });
      } catch (error) {
        if (error.name !== 'CanceledError' && error.code !== 'ERR_CANCELED') {
          console.error('Error loading suppliers:', error);
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    };

    fetchData();

    return () => {
      controller.abort();
    };
  }, [debouncedSearch, filterAnzianita, giorniNuovo, debouncedProdotto]);

  // Funzione per ricaricare i dati (usata dopo save/delete)
  const reloadData = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (debouncedSearch) params.append('search', debouncedSearch);
      params.append('limit', '1000');
      if (filterAnzianita !== 'tutti') params.append('stato_anagrafica', filterAnzianita);
      if (giorniNuovo && giorniNuovo !== 90) params.append('giorni_nuovo', String(giorniNuovo));
      if (debouncedProdotto && debouncedProdotto.trim()) params.append('prodotto', debouncedProdotto.trim());

      const res = await api.get(`/api/suppliers/filtered?${params}`);
      setSuppliers(res.data.items || []);
      setTotaliFiltrati(res.data.totali || {
        totale_fornitori: 0,
        attivi: 0,
      });
    } catch (error) {
      console.error('Error reloading suppliers:', error);
    } finally {
      setLoading(false);
    }
  }, [debouncedSearch, filterAnzianita, giorniNuovo, debouncedProdotto]);

  const filteredSuppliers = suppliers.filter(s => {
    if (filterMetodo !== 'tutti') {
      // niente default fittizio: senza metodo NON è "banca"
      if (!s.metodo_pagamento) return false;
      if (metodoCanonico(s) !== filterMetodo) return false;
    }
    if (filterIncomplete && (s.partita_iva || s.piva) && s.email) return false;
    if (filterSenzaMetodo) {
      // 'misto' è un metodo scelto esplicitamente (uno dei 4 di METODI_PAGAMENTO),
      // non equivale a "nessun metodo impostato".
      const m = (s.metodo_pagamento || '').toLowerCase().trim();
      const senzaMetodo = !m || m === 'da_configurare' || m === 'altro';
      if (!senzaMetodo) return false;
    }
    return true;
  });

  // Salvataggio completo fornitore
  const handleSave = async formData => {
    setSaving(true);
    try {
      let response;
      if (currentSupplier?.id) {
        // UPDATE nel database
        response = await api.put(`/api/suppliers/${currentSupplier.id}`, formData);
      } else {
        // INSERT nel database
        response = await api.post('/api/suppliers', {
          denominazione: formData.ragione_sociale,
          ...formData,
        });
      }

      // Mostra feedback se sono stati rimossi prodotti dal magazzino
      if (response.data?.prodotti_rimossi_magazzino > 0) {
        alert(
          `✅ Fornitore salvato!\n\n🗑️ ${response.data.prodotti_rimossi_magazzino} prodotti rimossi automaticamente dal magazzino (fornitore escluso).`
        );
      }

      setModalOpen(false);
      setCurrentSupplier(null);
      reloadData(); // Ricarica dati aggiornati
    } catch (error) {
      alert('Errore salvataggio: ' + (error.response?.data?.detail || error.message));
    } finally {
      setSaving(false);
    }
  };

  // Cambio rapido metodo pagamento - salva SUBITO nel database
  const handleChangeMetodo = async (supplierId, newMetodo) => {
    const payload = { metodo_pagamento: newMetodo };
    try {
      await api.put(`/api/suppliers/${supplierId}`, payload);

      // Aggiorna lo stato locale immediatamente
      setSuppliers(prev => prev.map(s => (s.id === supplierId ? { ...s, ...payload } : s)));
    } catch (error) {
      alert('Errore aggiornamento metodo: ' + (error.response?.data?.detail || error.message));
    }
  };

  // Toggle rapido "esclude_magazzino" dalla card (evita apertura modifica)
  const handleToggleEsclude = async (supplierId, nuovoValore) => {
    try {
      await api.put(`/api/suppliers/${supplierId}`, { esclude_magazzino: nuovoValore });
      setSuppliers(prev =>
        prev.map(s => (s.id === supplierId ? { ...s, esclude_magazzino: nuovoValore } : s))
      );
    } catch (error) {
      alert('Errore aggiornamento magazzino: ' + (error.response?.data?.detail || error.message));
    }
  };

  // Eliminazione fornitore dal database
  const handleDelete = async (id, forceDelete = false) => {
    if (!forceDelete) {
      const supplier = suppliers.find(s => s.id === id);
      const nome =
        supplier?.ragione_sociale || supplier?.nome || supplier?.name || 'questo fornitore';
      if (
        !window.confirm(
          `Eliminare definitivamente "${nome}"?\n\nAttenzione: questa operazione non può essere annullata.`
        )
      ) {
        return;
      }
    }
    try {
      const url = forceDelete ? `/api/suppliers/${id}?force=true` : `/api/suppliers/${id}`;
      await api.delete(url);
      reloadData();
    } catch (error) {
      const errorMsg =
        error.response?.data?.detail || error.response?.data?.message || error.message;
      if (error.response?.status === 400 && errorMsg.includes('fatture collegate')) {
        const supplier = suppliers.find(s => s.id === id);
        const nome =
          supplier?.ragione_sociale || supplier?.nome || supplier?.name || 'questo fornitore';
        if (
          window.confirm(
            `"${nome}" ha fatture collegate. Eliminare comunque (eliminazione forzata)?`
          )
        ) {
          handleDelete(id, true);
        }
      } else {
        alert('Errore eliminazione: ' + errorMsg);
      }
    }
  };

  const handleViewInvoices = supplier => {
    // Apre il modale con estratto fatture invece di navigare
    handleViewInvoicesModal(supplier);
  };

  // Ricerca dati azienda tramite Partita IVA
  const handleSearchPiva = async supplier => {
    const piva = supplier.partita_iva || supplier.piva;
    if (!piva) {
      alert('Questo fornitore non ha una Partita IVA');
      return;
    }

    try {
      const res = await api.get(`/api/suppliers/search-piva/${piva}`);
      const data = res.data;

      if (data.found) {
        // Prepara i dati da aggiornare (solo campi vuoti)
        const updates = {};
        if (!supplier.ragione_sociale && data.ragione_sociale) {
          updates.ragione_sociale = data.ragione_sociale;
        }
        if (!supplier.indirizzo && data.indirizzo) {
          updates.indirizzo = data.indirizzo;
        }
        if (!supplier.cap && data.cap) {
          updates.cap = data.cap;
        }
        if (!supplier.comune && data.comune) {
          updates.comune = data.comune;
        }
        if (!supplier.provincia && data.provincia) {
          updates.provincia = data.provincia;
        }

        if (Object.keys(updates).length > 0) {
          // Aggiorna automaticamente
          await api.put(`/api/suppliers/${supplier.id}`, updates);
          reloadData();
        } else {
          alert(
            `Nessun dato nuovo trovato per ${supplier.ragione_sociale || supplier.partita_iva}.\nI dati sono già completi o non disponibili su VIES.`
          );
        }
      } else {
        alert(
          `Partita IVA ${supplier.partita_iva} non trovata nel database VIES.\n\nNota: VIES contiene solo aziende registrate per operazioni intracomunitarie UE.`
        );
      }
    } catch (error) {
      alert('Errore ricerca: ' + (error.response?.data?.detail || error.message));
    }
  };

  // Stato per modale fatturato
  const [fatturatoModal, setFatturatoModal] = useState({ open: false, data: null, loading: false });

  // Stato per modale estratto fatture
  const [estrattoModal, setEstrattoModal] = useState({
    open: false,
    fornitore: null,
    data: null,
    loading: false,
    filtri: {
      anno: selectedYear,
      data_da: '',
      data_a: '',
      importo_min: '',
      importo_max: '',
      tipo: 'tutti',
    },
  });

  // Mostra fatturato fornitore per anno
  const handleShowFatturato = async (supplier, anno) => {
    if (!supplier.partita_iva) {
      alert('Questo fornitore non ha una Partita IVA');
      return;
    }

    setFatturatoModal({ open: true, data: null, loading: true });

    try {
      const res = await api.get(`/api/suppliers/${supplier.id}/fatturato?anno=${anno}`);
      setFatturatoModal({ open: true, data: res.data, loading: false });
    } catch (error) {
      alert('Errore caricamento fatturato: ' + (error.response?.data?.detail || error.message));
      setFatturatoModal({ open: false, data: null, loading: false });
    }
  };

  // Mostra estratto fatture fornitore
  const handleViewInvoicesModal = async supplier => {
    if (!supplier.partita_iva && !supplier.id) {
      alert('Questo fornitore non ha una Partita IVA');
      return;
    }

    setEstrattoModal({
      open: true,
      fornitore: supplier,
      data: null,
      loading: true,
      filtri: {
        anno: selectedYear,
        data_da: '',
        data_a: '',
        importo_min: '',
        importo_max: '',
        tipo: 'tutti',
      },
    });

    try {
      const res = await api.get(
        `/api/suppliers/${supplier.id || supplier.partita_iva}/fatture?anno=${selectedYear}`
      );
      setEstrattoModal(prev => ({ ...prev, data: res.data, loading: false }));
    } catch (error) {
      alert('Errore caricamento fatture: ' + (error.response?.data?.detail || error.message));
      setEstrattoModal(prev => ({ ...prev, open: false, loading: false }));
    }
  };

  // Ricarica estratto con filtri
  const reloadEstratto = async () => {
    if (!estrattoModal.fornitore) return;

    setEstrattoModal(prev => ({ ...prev, loading: true }));

    try {
      const { anno, data_da, data_a, importo_min, importo_max, tipo } = estrattoModal.filtri;
      const params = new URLSearchParams();
      if (anno) params.append('anno', anno);
      if (data_da) params.append('data_da', data_da);
      if (data_a) params.append('data_a', data_a);
      if (importo_min) params.append('importo_min', importo_min);
      if (importo_max) params.append('importo_max', importo_max);
      if (tipo && tipo !== 'tutti') params.append('tipo', tipo);

      const res = await api.get(
        `/api/suppliers/${estrattoModal.fornitore.id || estrattoModal.fornitore.partita_iva}/fatture?${params.toString()}`
      );
      setEstrattoModal(prev => ({ ...prev, data: res.data, loading: false }));
    } catch (error) {
      alert('Errore: ' + (error.response?.data?.detail || error.message));
      setEstrattoModal(prev => ({ ...prev, loading: false }));
    }
  };

  // === SCHEDE TECNICHE FUNCTIONS ===
  const [schedeTecnicheJob, setSchedeTecnicheJob] = useState(null);

  const handleViewSchedeTecniche = async supplier => {
    setSchedeTecnicheModal({ open: true, fornitore: supplier, schede: [], loading: true });
    setSchedeTecnicheJob(null);
    try {
      const res = await api.get(`/api/schede-tecniche/fornitore/${supplier.id}`);
      setSchedeTecnicheModal(prev => ({
        ...prev,
        schede: res.data.schede || [],
        loading: false,
        trovate: res.data.trovate || 0,
        da_cercare: res.data.da_cercare || 0,
      }));
      if (res.data.job) setSchedeTecnicheJob(res.data.job);
    } catch (error) {
      console.error('Errore caricamento schede tecniche:', error);
      setSchedeTecnicheModal(prev => ({ ...prev, loading: false }));
    }
  };

  const handleCercaSchedeTecniche = async () => {
    const supplier = schedeTecnicheModal.fornitore;
    if (!supplier) return;
    try {
      setSchedeTecnicheJob({ stato: 'in_corso', prodotti_trovati: [], schede_trovate: 0 });
      const res = await api.post('/api/schede-tecniche/cerca', { fornitore_id: supplier.id });
      const jobId = res.data.job_id;
      // Polling ogni 3s finché completato
      const poll = setInterval(async () => {
        try {
          const jobRes = await api.get(`/api/schede-tecniche/job/${jobId}`);
          const job = jobRes.data;
          setSchedeTecnicheJob(job);
          if (
            job.stato === 'completato' ||
            job.stato === 'completato_vuoto' ||
            job.stato === 'errore'
          ) {
            clearInterval(poll);
            // Ricarica le schede
            const schedeRes = await api.get(`/api/schede-tecniche/fornitore/${supplier.id}`);
            setSchedeTecnicheModal(prev => ({
              ...prev,
              schede: schedeRes.data.schede || [],
              trovate: schedeRes.data.trovate || 0,
              da_cercare: schedeRes.data.da_cercare || 0,
            }));
          }
        } catch (e) {
          clearInterval(poll);
        }
      }, 3000);
    } catch (err) {
      alert('Errore avvio ricerca: ' + (err.response?.data?.detail || err.message));
    }
  };

  const stats = {
    total: suppliers.length,
    withInvoices: suppliers.filter(s => (s.fatture_count || 0) > 0).length,
    incomplete: suppliers.filter(s => !s.partita_iva || !s.comune).length,
    cash: suppliers.filter(s => canaleCanonico(s.metodo_pagamento) === 'cassa').length,
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        backgroundColor: COLORS.bg,
        padding: isMobile ? '12px 10px' : '16px',
        position: 'relative',
      }}
    >
      <div style={{ maxWidth: '1400px', margin: '0 auto' }}>
        {/* Action Bar - senza cornice blu */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'flex-end',
            alignItems: 'center',
            marginBottom: 16,
            gap: 8,
            flexWrap: 'wrap',
          }}
        >
          <Button
            variant="secondary"
            onClick={reloadData}
            disabled={loading}
            style={{ minHeight: 40 }}
          >
            🔄 {loading ? 'Caricamento...' : 'Aggiorna'}
          </Button>
          <Button
            variant="primary"
            onClick={() => {
              setCurrentSupplier(null);
              setModalOpen(true);
            }}
            style={{ minHeight: 40 }}
          >
            <Plus size={18} /> Nuovo Fornitore
          </Button>
        </div>

        {/* Stats */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
            gap: '12px',
            marginBottom: '16px',
          }}
        >
          <StatCard
            icon={<Users size={18} />}
            label="Totale Fornitori"
            value={stats.total}
            accent="primary"
          />
          <StatCard
            icon={<FileText size={18} />}
            label="Con Fatture"
            value={stats.withInvoices}
            accent="success"
          />
          <StatCard
            icon={<AlertCircle size={18} />}
            label="Dati Incompleti"
            value={stats.incomplete}
            accent="warning"
          />
          <StatCard
            icon={<CreditCard size={18} />}
            label="Pagamento Cassa"
            value={stats.cash}
            accent="primary"
          />
        </div>

        {/* PR #5e850c8: Badge contatori filtri avanzati (navy/gold) */}
        <div
          style={{
            display: 'flex',
            gap: '8px',
            marginBottom: '16px',
            flexWrap: 'wrap',
          }}
          data-testid="filter-badges"
        >
          <Badge
            variant="primary"
            style={{
              padding: '8px 14px',
              background: COLORS.primary,
              color: COLORS.card,
              fontSize: 13,
              textTransform: 'none',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
            }}
            data-testid="badge-totale"
          >
            <span style={{ opacity: 0.85 }}>Totale</span>
            <span style={{ color: COLORS.accent, fontSize: 16 }}>{totaliFiltrati.totale_fornitori}</span>
          </Badge>
          <Badge
            variant="neutral"
            style={{
              padding: '8px 14px',
              background: COLORS.bg,
              color: COLORS.primary,
              fontSize: 13,
              textTransform: 'none',
              border: `1px solid ${COLORS.border}`,
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
            }}
            data-testid="badge-attivi"
          >
            <span>✅ Attivi</span>
            <span style={{ fontSize: 16 }}>{totaliFiltrati.attivi}</span>
          </Badge>
        </div>

        {/* Tabs */}
        {/* Search & Filters */}
        <div
          style={{
            backgroundColor: COLORS.card,
            borderRadius: BORDER_RADIUS.lg,
            padding: '16px',
            marginBottom: '24px',
            boxShadow: SHADOWS.sm,
          }}
        >
          <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', alignItems: 'center' }}>
            {/* Search */}
            <div style={{ flex: 1, minWidth: '250px', position: 'relative' }}>
              <Search
                size={18}
                style={{
                  position: 'absolute',
                  left: '12px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  color: COLORS.textSubtle,
                }}
              />
              <input
                type="text"
                placeholder="Cerca fornitore..."
                value={search}
                onChange={e => setSearch(e.target.value)}
                style={{
                  width: '100%',
                  padding: '10px 12px 10px 40px',
                  border: `1px solid ${COLORS.border}`,
                  borderRadius: BORDER_RADIUS.md,
                  fontSize: '14px',
                  boxSizing: 'border-box',
                }}
              />
            </div>

            {/* Filter Metodo - usa METODI_PAGAMENTO */}
            <select
              value={filterMetodo}
              onChange={e => setFilterMetodo(e.target.value)}
              style={{
                padding: '10px 14px',
                border: `1px solid ${COLORS.border}`,
                borderRadius: BORDER_RADIUS.md,
                fontSize: '14px',
                backgroundColor: 'white',
                minWidth: '140px',
              }}
            >
              <option value="tutti">Tutti i metodi</option>
              {Object.entries(METODI_PAGAMENTO)
                .map(([key, val]) => (
                  <option key={key} value={key}>
                    {val.label}
                  </option>
                ))}
            </select>

            {/* Filter Incomplete */}
            <label
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                padding: '10px 14px',
                border: `1px solid ${COLORS.border}`,
                borderRadius: BORDER_RADIUS.md,
                cursor: 'pointer',
                fontSize: '14px',
                backgroundColor: filterIncomplete ? COLORS.warningLight : 'white',
              }}
            >
              <input
                type="checkbox"
                checked={filterIncomplete}
                onChange={e => setFilterIncomplete(e.target.checked)}
                style={{ width: '16px', height: '16px' }}
              />
              Solo incompleti
            </label>

            {/* Filter Senza Metodo Pagamento — per risalire ai fornitori di fatture non auto-confermate */}
            <label
              title="Mostra solo i fornitori SENZA metodo di pagamento predefinito (le loro fatture non vengono auto-confermate)"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                padding: '10px 14px',
                border: filterSenzaMetodo ? `1px solid ${COLORS.warning}` : `1px solid ${COLORS.border}`,
                borderRadius: BORDER_RADIUS.md,
                cursor: 'pointer',
                fontSize: '14px',
                fontWeight: filterSenzaMetodo ? 700 : 400,
                backgroundColor: filterSenzaMetodo ? COLORS.warningLight : 'white',
                color: filterSenzaMetodo ? COLORS.warning : COLORS.gray[700],
              }}
              data-testid="filter-senza-metodo-pagamento"
            >
              <input
                type="checkbox"
                checked={filterSenzaMetodo}
                onChange={e => setFilterSenzaMetodo(e.target.checked)}
                style={{ width: '16px', height: '16px', accentColor: COLORS.warning }}
              />
              ⚠️ Fatture senza metodo
            </label>

            <CopyLinkButton style={{ flexShrink: 0 }} />
          </div>

          {/* PR #5e850c8: riga filtri avanzati (navy/gold) */}
          <div
            style={{
              display: 'flex',
              gap: '12px',
              flexWrap: 'wrap',
              alignItems: 'center',
              marginTop: '12px',
              paddingTop: '12px',
              borderTop: `1px solid ${COLORS.border}`,
            }}
            data-testid="filtri-avanzati-row"
          >
            {/* Segmented: Anzianità */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ fontSize: 13, color: COLORS.primary, fontWeight: 600 }}>Anzianità:</span>
              {[
                { k: 'tutti', l: 'Tutti' },
                { k: 'nuovo', l: '🆕 Nuovi' },
                { k: 'storico', l: '📜 Storici' },
              ].map(opt => (
                <Button
                  key={opt.k}
                  type="button"
                  variant={filterAnzianita === opt.k ? 'primary' : 'secondary'}
                  size="sm"
                  onClick={() => setFilterAnzianita(opt.k)}
                  data-testid={`filter-anzianita-${opt.k}`}
                  style={{
                    minHeight: 40,
                    ...(filterAnzianita === opt.k ? { color: COLORS.accent } : {}),
                  }}
                >
                  {opt.l}
                </Button>
              ))}
            </div>

            {/* Soglia giorni — visibile solo se Nuovi o Storici selezionato */}
            {(filterAnzianita === 'nuovo' || filterAnzianita === 'storico') && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{ fontSize: 13, color: COLORS.primary, fontWeight: 600 }}>
                  Soglia giorni:
                </span>
                <input
                  type="number"
                  min={1}
                  max={3650}
                  value={giorniNuovo}
                  onChange={e => {
                    const v = parseInt(e.target.value, 10);
                    setGiorniNuovo(Number.isFinite(v) && v > 0 ? v : 90);
                  }}
                  data-testid="filter-giorni-nuovo"
                  style={{
                    padding: '6px 10px',
                    border: `1px solid ${COLORS.border}`,
                    borderRadius: BORDER_RADIUS.sm,
                    fontSize: 13,
                    width: 80,
                  }}
                />
              </div>
            )}

            {/* Ricerca prodotto venduto */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flex: '1 1 220px' }}>
              <span style={{ fontSize: 13, color: COLORS.primary, fontWeight: 600 }}>Prodotto:</span>
              <input
                type="text"
                value={filtroProdotto}
                onChange={e => setFiltroProdotto(e.target.value)}
                placeholder='es. "olio"'
                data-testid="filter-prodotto"
                style={{
                  padding: '6px 10px',
                  border: `1px solid ${COLORS.border}`,
                  borderRadius: BORDER_RADIUS.sm,
                  fontSize: 13,
                  flex: 1,
                  minWidth: 140,
                }}
              />
              {filtroProdotto && (
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() => setFiltroProdotto('')}
                  data-testid="filter-prodotto-clear"
                  style={{ padding: '4px 8px', fontSize: 12 }}
                  title="Pulisci"
                >
                  ✕
                </Button>
              )}
            </div>

            {/* Reset filtri avanzati */}
            {(filterAnzianita !== 'tutti' ||
              giorniNuovo !== 90 ||
              filtroProdotto) && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => {
                  setFilterAnzianita('tutti');
                  setGiorniNuovo(90);
                  setFiltroProdotto('');
                }}
                data-testid="filtri-avanzati-reset"
                style={{ borderColor: COLORS.accent, color: COLORS.accent }}
              >
                Reset filtri avanzati
              </Button>
            )}

            {/* L'auto-conferma delle fatture per metodo fornitore è AUTOMATICA:
                avviene all'import di ogni fattura e col job ogni 30 minuti. */}
          </div>
        </div>

        {/* Results Count */}
        <div style={{ marginBottom: '16px', fontSize: '14px', color: COLORS.textMuted }}>
          {filteredSuppliers.length === suppliers.length
            ? `${suppliers.length} fornitori`
            : `${filteredSuppliers.length} di ${suppliers.length} fornitori`}
        </div>

        {/* Cards Grid */}
        {loading ? (
          <div style={{ textAlign: 'center', padding: '60px' }}>
            <div
              style={{
                width: '40px',
                height: '40px',
                border: `4px solid ${COLORS.border}`,
                borderTopColor: COLORS.primary,
                borderRadius: '50%',
                animation: 'spin 1s linear infinite',
                margin: '0 auto',
              }}
            />
            <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
          </div>
        ) : filteredSuppliers.length === 0 ? (
          <div
            style={{
              backgroundColor: COLORS.card,
              borderRadius: BORDER_RADIUS.lg,
              padding: '60px',
              textAlign: 'center',
              boxShadow: SHADOWS.sm,
            }}
          >
            <Building2 size={48} color={COLORS.border} style={{ marginBottom: '16px' }} />
            <h3 style={{ margin: '0 0 8px', color: COLORS.gray[700] }}>Nessun fornitore trovato</h3>
            <p style={{ color: COLORS.textMuted, margin: 0 }}>
              {suppliers.length === 0
                ? 'Aggiungi il primo fornitore'
                : 'Modifica i filtri di ricerca'}
            </p>
          </div>
        ) : (
          /* Lista unica desktop/mobile (ListaAdattiva, ex griglia di card):
             tabella su monitor, card compatte su telefono */
          <div
            style={{
              backgroundColor: COLORS.card,
              borderRadius: BORDER_RADIUS.lg,
              boxShadow: SHADOWS.sm,
              padding: isMobile ? '10px' : '4px 0',
            }}
          >
            <ListaAdattiva
              testId="lista-fornitori"
              dati={filteredSuppliers}
              pageSize={50}
              chiave={(s, i) => s.id || i}
              colonne={[
                {
                  key: 'ragione_sociale',
                  label: 'Fornitore',
                  ruoloCard: 'titolo',
                  render: s => {
                    const nome =
                      s.ragione_sociale || s.denominazione || s.nome || s.name || 'Senza nome';
                    const incompleto =
                      !(s.partita_iva || s.piva) || !s.comune || !s.email || !s.telefono;
                    return (
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                        {nome}
                        {incompleto && (
                          <span title="Dati incompleti" style={{ display: 'inline-flex' }}>
                            <AlertCircle size={14} color={COLORS.warning} />
                          </span>
                        )}
                      </span>
                    );
                  },
                  tdStyle: { fontWeight: 600, color: COLORS.gray[800], fontSize: 14 },
                },
                {
                  // Vincolo mobile: P.IVA mai nelle card
                  key: 'partita_iva',
                  label: 'P.IVA',
                  mono: true,
                  ruoloCard: 'omesso',
                  render: s => s.partita_iva || s.piva || '-',
                  tdStyle: { fontSize: 13, color: COLORS.textMuted },
                },
                {
                  // Vincolo mobile: IBAN mai nelle card
                  key: 'iban',
                  label: 'IBAN',
                  mono: true,
                  ruoloCard: 'omesso',
                  render: s => s.iban || '-',
                  tdStyle: { fontSize: 12, color: COLORS.textMuted },
                },
                {
                  key: 'email',
                  label: 'Email',
                  ruoloCard: 'omesso',
                  render: s => s.email || '-',
                  tdStyle: { fontSize: 13, color: COLORS.textMuted },
                },
                {
                  key: 'comune',
                  label: 'Località',
                  ruoloCard: 'dettaglio',
                  iconaCard: '📍',
                  render: s =>
                    s.comune ? `${s.comune}${s.provincia ? ` (${s.provincia})` : ''}` : '-',
                  tdStyle: { fontSize: 13, color: COLORS.textMuted },
                },
                {
                  key: 'fatture_count',
                  label: 'Fatture',
                  align: 'center',
                  ruoloCard: 'dettaglio',
                  iconaCard: '🧾',
                  render: s => s.fatture_count || 0,
                },
                {
                  key: 'giorni_pagamento',
                  label: 'Giorni',
                  align: 'center',
                  ruoloCard: 'dettaglio',
                  render: s => s.giorni_pagamento || 30,
                },
                {
                  key: 'metodo_pagamento',
                  label: 'Metodo',
                  align: 'center',
                  ruoloCard: 'dettaglio',
                  render: s => <MetodoBadge supplier={s} onChangeMetodo={handleChangeMetodo} />,
                },
                {
                  key: 'esclude_magazzino',
                  label: 'Magazzino',
                  align: 'center',
                  ruoloCard: 'dettaglio',
                  iconaCard: ' ', // il bottone si spiega da solo: niente prefisso "Magazzino:"
                  render: s => (
                    <Button
                      variant={s.esclude_magazzino ? 'warning' : 'success'}
                      size="sm"
                      onClick={async e => {
                        e.stopPropagation();
                        await handleToggleEsclude(s.id, !s.esclude_magazzino);
                      }}
                      data-testid={`btn-toggle-esclude-magazzino-${s.id}`}
                      title={
                        s.esclude_magazzino
                          ? 'Click: RIMETTI nel magazzino (le fatture popoleranno le giacenze)'
                          : 'Click: ESCLUDI dal magazzino (le fatture NON creano carichi)'
                      }
                      style={{ padding: '4px 10px', fontSize: 11 }}
                    >
                      {s.esclude_magazzino ? '🚫 Escluso magazzino' : '📦 In magazzino'}
                    </Button>
                  ),
                },
                {
                  key: 'azioni',
                  label: 'Azioni',
                  align: 'center',
                  ruoloCard: 'azioni',
                  render: s => (
                    <AzioniFornitore
                      supplier={s}
                      selectedYear={selectedYear}
                      isMobile={isMobile}
                      onEdit={sup => {
                        setCurrentSupplier(sup);
                        setModalOpen(true);
                      }}
                      onDelete={handleDelete}
                      onViewInvoices={handleViewInvoices}
                      onSearchPiva={handleSearchPiva}
                      onShowFatturato={handleShowFatturato}
                      onShowSchedeTecniche={handleViewSchedeTecniche}
                    />
                  ),
                },
              ]}
            />
          </div>
        )}
      </div>

      <SupplierModal
        isOpen={modalOpen}
        onClose={() => {
          setModalOpen(false);
          setCurrentSupplier(null);
        }}
        supplier={currentSupplier}
        onSave={handleSave}
        saving={saving}
      />

      {/* Modale Fatturato */}
      {fatturatoModal.open && (
        <Portal>
          <div
            style={{
              position: 'fixed',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              backgroundColor: 'rgba(0,0,0,0.5)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              zIndex: 99999,
              padding: '20px',
            }}
            onClick={() => setFatturatoModal({ open: false, data: null, loading: false })}
          >
            <div
              style={{
                backgroundColor: COLORS.card,
                borderRadius: BORDER_RADIUS.lg,
                width: '100%',
                maxWidth: '500px',
                overflow: 'hidden',
                boxShadow: SHADOWS.modal,
              }}
              onClick={e => e.stopPropagation()}
            >
              {/* Header */}
              <div
                style={{
                  background: COLORS.primary,
                  padding: '20px 24px',
                  color: 'white',
                }}
              >
                <div
                  style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
                >
                  <div>
                    <h2
                      style={{
                        margin: 0,
                        fontSize: '18px',
                        fontWeight: 600,
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px',
                      }}
                    >
                      <TrendingUp size={20} /> Fatturato {fatturatoModal.data?.anno || selectedYear}
                    </h2>
                    <p style={{ margin: '4px 0 0', opacity: 0.9, fontSize: '14px' }}>
                      {fatturatoModal.data?.fornitore || ''}
                    </p>
                  </div>
                  <Button
                    variant="ghost"
                    onClick={() => setFatturatoModal({ open: false, data: null, loading: false })}
                    style={{
                      background: 'rgba(255,255,255,0.2)',
                      minWidth: '40px',
                      minHeight: '40px',
                      padding: 0,
                      color: 'white',
                    }}
                    data-testid="close-fatturato-modal"
                  >
                    <X size={20} />
                  </Button>
                </div>
              </div>

              {/* Content */}
              <div style={{ padding: '24px' }}>
                {fatturatoModal.loading ? (
                  <div style={{ textAlign: 'center', padding: '40px' }}>
                    <div
                      style={{
                        width: '40px',
                        height: '40px',
                        border: `4px solid ${COLORS.border}`,
                        borderTopColor: COLORS.info,
                        borderRadius: '50%',
                        animation: 'spin 1s linear infinite',
                        margin: '0 auto',
                      }}
                    />
                    <p style={{ marginTop: '16px', color: COLORS.textMuted }}>Caricamento fatturato...</p>
                  </div>
                ) : fatturatoModal.data ? (
                  <div>
                    {/* Totale Principale */}
                    <div
                      style={{
                        background: COLORS.infoLight,
                        borderRadius: BORDER_RADIUS.lg,
                        padding: '20px',
                        marginBottom: '20px',
                        textAlign: 'center',
                      }}
                    >
                      <div style={{ fontSize: '14px', color: COLORS.primary, marginBottom: '4px' }}>
                        TOTALE FATTURATO {(fatturatoModal.data?.anno ?? '')}
                      </div>
                      <div style={{ fontSize: '32px', fontWeight: 700, color: COLORS.primary, fontFamily: FONT.mono }}>
                        {formatEuro(fatturatoModal.data.totale_fatturato || 0)}
                      </div>
                      <div style={{ fontSize: '14px', color: COLORS.primary, marginTop: '8px' }}>
                        {(fatturatoModal.data?.numero_fatture ?? 0)} fatture
                      </div>
                    </div>

                    {/* Stats Grid */}
                    <div
                      style={{
                        display: 'grid',
                        gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr',
                        gap: '12px',
                        marginBottom: '20px',
                      }}
                    >
                      <StatCard
                        label="Pagate"
                        value={(fatturatoModal.data?.fatture_pagate ?? 0) || 0}
                        subtext={formatEuro(fatturatoModal.data.importo_pagato || 0)}
                        accent="success"
                      />
                      <StatCard
                        label="Da Pagare"
                        value={(fatturatoModal.data?.fatture_non_pagate ?? 0) || 0}
                        subtext={formatEuro(fatturatoModal.data.importo_non_pagato || 0)}
                        accent="danger"
                      />
                    </div>

                    {/* Dettaglio Mensile (se disponibile) */}
                    {fatturatoModal.data.dettaglio_mensile &&
                      (fatturatoModal.data?.dettaglio_mensile?.length || 0) > 0 && (
                        <div>
                          <div
                            style={{
                              fontSize: '13px',
                              fontWeight: 600,
                              color: COLORS.gray[700],
                              marginBottom: '8px',
                            }}
                          >
                            Dettaglio Mensile
                          </div>
                          <div style={{ maxHeight: '200px', overflowY: 'auto' }}>
                            {(fatturatoModal.data?.dettaglio_mensile ?? []).map((m, idx) => (
                              <div
                                key={idx}
                                style={{
                                  display: 'flex',
                                  justifyContent: 'space-between',
                                  padding: '8px 12px',
                                  borderBottom: `1px solid ${COLORS.bg}`,
                                  fontSize: '13px',
                                }}
                              >
                                <span style={{ color: COLORS.textMuted }}>{m.mese_nome}</span>
                                <span style={{ fontWeight: 600, color: COLORS.gray[800] }}>
                                  {formatEuro(m.totale || 0)}
                                  <span
                                    style={{ fontWeight: 400, color: COLORS.textSubtle, marginLeft: '8px' }}
                                  >
                                    ({m.numero_fatture} fatt.)
                                  </span>
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                    {(fatturatoModal.data?.numero_fatture ?? 0) === 0 && (
                      <div style={{ textAlign: 'center', color: COLORS.textMuted, padding: '20px' }}>
                        Nessuna fattura registrata per questo anno
                      </div>
                    )}
                  </div>
                ) : null}
              </div>
            </div>
          </div>
        </Portal>
      )}

      {/* MODALE ESTRATTO FATTURE */}
      {estrattoModal.open && (
        <Portal>
          <div
            onClick={() => setEstrattoModal(prev => ({ ...prev, open: false }))}
            style={{
              position: 'fixed',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              backgroundColor: 'rgba(0,0,0,0.5)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              zIndex: 10000,
            }}
          >
            <div
              onClick={e => e.stopPropagation()}
              id="estratto-fatture-content"
              style={{
                backgroundColor: COLORS.card,
                borderRadius: BORDER_RADIUS.lg,
                width: '95%',
                maxWidth: '1200px',
                maxHeight: '90vh',
                overflow: 'hidden',
                boxShadow: SHADOWS.modal,
                display: 'flex',
                flexDirection: 'column',
              }}
            >
              {/* Header */}
              <div
                style={{
                  padding: '20px 24px',
                  borderBottom: `1px solid ${COLORS.border}`,
                  background: COLORS.primary,
                  color: 'white',
                }}
              >
                <div
                  style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
                >
                  <div>
                    <div style={{ fontSize: '20px', fontWeight: 700 }}>📋 Estratto Fatture</div>
                    <div style={{ fontSize: '14px', opacity: 0.9, marginTop: 4 }}>
                      {estrattoModal.fornitore?.ragione_sociale ||
                        estrattoModal.fornitore?.nome ||
                        estrattoModal.fornitore?.denominazione}
                      {' • '}
                      {estrattoModal.fornitore?.partita_iva}
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    onClick={() => setEstrattoModal(prev => ({ ...prev, open: false }))}
                    style={{
                      width: '40px',
                      height: '40px',
                      padding: 0,
                      borderRadius: BORDER_RADIUS.full,
                      background: 'rgba(255,255,255,0.2)',
                      color: 'white',
                      fontSize: '18px',
                    }}
                  >
                    ×
                  </Button>
                </div>
              </div>

              {/* Filtri */}
              <div
                style={{
                  padding: '16px 24px',
                  borderBottom: `1px solid ${COLORS.border}`,
                  background: COLORS.bgAlt,
                  display: 'flex',
                  flexWrap: 'wrap',
                  gap: 12,
                  alignItems: 'flex-end',
                }}
              >
                <div>
                  <label
                    style={{ fontSize: 11, color: COLORS.textMuted, display: 'block', marginBottom: 4 }}
                  >
                    Anno
                  </label>
                  <select
                    value={estrattoModal.filtri.anno || ''}
                    onChange={e =>
                      setEstrattoModal(prev => ({
                        ...prev,
                        filtri: {
                          ...prev.filtri,
                          anno: e.target.value ? parseInt(e.target.value) : null,
                        },
                      }))
                    }
                    style={{
                      padding: '8px 12px',
                      border: `1px solid ${COLORS.border}`,
                      borderRadius: BORDER_RADIUS.sm,
                      fontSize: 13,
                    }}
                  >
                    <option value="">Tutti</option>
                    {[...Array(5)].map((_, i) => {
                      const y = new Date().getFullYear() - i;
                      return (
                        <option key={y} value={y}>
                          {y}
                        </option>
                      );
                    })}
                  </select>
                </div>
                <div>
                  <label
                    style={{ fontSize: 11, color: COLORS.textMuted, display: 'block', marginBottom: 4 }}
                  >
                    Data Da
                  </label>
                  <input
                    type="date"
                    value={estrattoModal.filtri.data_da}
                    onChange={e =>
                      setEstrattoModal(prev => ({
                        ...prev,
                        filtri: { ...prev.filtri, data_da: e.target.value },
                      }))
                    }
                    style={{
                      padding: '8px 12px',
                      border: `1px solid ${COLORS.border}`,
                      borderRadius: BORDER_RADIUS.sm,
                      fontSize: 13,
                    }}
                  />
                </div>
                <div>
                  <label
                    style={{ fontSize: 11, color: COLORS.textMuted, display: 'block', marginBottom: 4 }}
                  >
                    Data A
                  </label>
                  <input
                    type="date"
                    value={estrattoModal.filtri.data_a}
                    onChange={e =>
                      setEstrattoModal(prev => ({
                        ...prev,
                        filtri: { ...prev.filtri, data_a: e.target.value },
                      }))
                    }
                    style={{
                      padding: '8px 12px',
                      border: `1px solid ${COLORS.border}`,
                      borderRadius: BORDER_RADIUS.sm,
                      fontSize: 13,
                    }}
                  />
                </div>
                <div>
                  <label
                    style={{ fontSize: 11, color: COLORS.textMuted, display: 'block', marginBottom: 4 }}
                  >
                    Importo Min
                  </label>
                  <input
                    type="number"
                    placeholder="€"
                    value={estrattoModal.filtri.importo_min}
                    onChange={e =>
                      setEstrattoModal(prev => ({
                        ...prev,
                        filtri: { ...prev.filtri, importo_min: e.target.value },
                      }))
                    }
                    style={{
                      padding: '8px 12px',
                      border: `1px solid ${COLORS.border}`,
                      borderRadius: BORDER_RADIUS.sm,
                      fontSize: 13,
                      width: 100,
                    }}
                  />
                </div>
                <div>
                  <label
                    style={{ fontSize: 11, color: COLORS.textMuted, display: 'block', marginBottom: 4 }}
                  >
                    Importo Max
                  </label>
                  <input
                    type="number"
                    placeholder="€"
                    value={estrattoModal.filtri.importo_max}
                    onChange={e =>
                      setEstrattoModal(prev => ({
                        ...prev,
                        filtri: { ...prev.filtri, importo_max: e.target.value },
                      }))
                    }
                    style={{
                      padding: '8px 12px',
                      border: `1px solid ${COLORS.border}`,
                      borderRadius: BORDER_RADIUS.sm,
                      fontSize: 13,
                      width: 100,
                    }}
                  />
                </div>
                <div>
                  <label
                    style={{ fontSize: 11, color: COLORS.textMuted, display: 'block', marginBottom: 4 }}
                  >
                    Tipo
                  </label>
                  <select
                    value={estrattoModal.filtri.tipo}
                    onChange={e =>
                      setEstrattoModal(prev => ({
                        ...prev,
                        filtri: { ...prev.filtri, tipo: e.target.value },
                      }))
                    }
                    style={{
                      padding: '8px 12px',
                      border: `1px solid ${COLORS.border}`,
                      borderRadius: BORDER_RADIUS.sm,
                      fontSize: 13,
                    }}
                  >
                    <option value="tutti">Tutti</option>
                    <option value="fattura">Solo Fatture</option>
                    <option value="nota_credito">Solo Note Credito</option>
                  </select>
                </div>
                <Button variant="primary" size="sm" onClick={reloadEstratto} disabled={estrattoModal.loading}>
                  🔍 Filtra
                </Button>
              </div>

              {/* Content */}
              <div style={{ flex: 1, overflow: 'auto', padding: '16px 24px' }}>
                {estrattoModal.loading ? (
                  <div style={{ textAlign: 'center', padding: 40 }}>
                    <div
                      className="spinner"
                      style={{ width: 40, height: 40, margin: '0 auto' }}
                    ></div>
                    <p style={{ marginTop: 16, color: COLORS.textMuted }}>Caricamento fatture...</p>
                  </div>
                ) : estrattoModal.data ? (
                  <>
                    {/* Totali */}
                    <div
                      style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
                        gap: 12,
                        marginBottom: 20,
                      }}
                    >
                      <StatCard
                        label="Documenti"
                        value={estrattoModal.data.totali?.numero_documenti || 0}
                        accent="primary"
                      />
                      <StatCard
                        label="Totale"
                        value={formatEuro(estrattoModal.data.totali?.importo_totale || 0)}
                        accent="success"
                      />
                      <StatCard
                        label="Note Credito"
                        value={`- ${formatEuro(estrattoModal.data.totali?.note_credito || 0)}`}
                        accent="danger"
                      />
                      <StatCard
                        label="Netto"
                        value={formatEuro(estrattoModal.data.totali?.netto || 0)}
                        accent="warning"
                      />
                    </div>

                    {/* Tabella Fatture */}
                    <TableWrap>
                      <Table>
                        <thead>
                          <tr>
                            <Th>Data</Th>
                            <Th>Numero</Th>
                            <Th>Tipo</Th>
                            <Th align="right">Imponibile</Th>
                            <Th align="right">IVA</Th>
                            <Th align="right">Totale</Th>
                            <Th align="center">Metodo Pag.</Th>
                            <Th align="center">Stato</Th>
                            <Th align="center">Azioni</Th>
                          </tr>
                        </thead>
                        <tbody>
                          {(estrattoModal.data.estratto || []).map((f, idx) => (
                            <tr
                              key={f.id || idx}
                              style={{
                                borderBottom: `1px solid ${COLORS.border}`,
                                background: f.is_nota_credito
                                  ? COLORS.dangerLight
                                  : idx % 2 === 0
                                    ? 'white'
                                    : COLORS.bgAlt,
                              }}
                            >
                              <Td>{formatDateIT(f.data)}</Td>
                              <Td style={{ fontWeight: 500 }}>{f.numero}</Td>
                              <Td>
                                {f.is_nota_credito ? (
                                  <Badge variant="danger">NC</Badge>
                                ) : (
                                  <Badge variant="info">{f.tipo_documento}</Badge>
                                )}
                              </Td>
                              <Td align="right" mono>
                                {formatEuro(f.imponibile || 0)}
                              </Td>
                              <Td align="right" mono>
                                {formatEuro(f.iva || 0)}
                              </Td>
                              <Td align="right" mono style={{ fontWeight: 600 }}>
                                {f.is_nota_credito ? '-' : ''} {formatEuro(f.importo_totale || 0)}
                              </Td>
                              <Td align="center">
                                <Badge
                                  variant={
                                    f.metodo_pagamento === 'cassa' || f.metodo_pagamento === 'contanti'
                                      ? 'success'
                                      : 'info'
                                  }
                                >
                                  {f.metodo_pagamento || '-'}
                                </Badge>
                              </Td>
                              <Td align="center">
                                {f.riconciliato ? (
                                  <Badge variant="success" style={{ background: COLORS.success, color: 'white' }}>
                                    ✓ RICONCILIATA
                                  </Badge>
                                ) : f.pagato ? (
                                  <Badge variant="success" style={{ background: COLORS.success, color: 'white' }}>
                                    Pagata
                                  </Badge>
                                ) : (
                                  <Badge variant="warning" style={{ background: COLORS.warning, color: 'white' }}>
                                    Da pagare
                                  </Badge>
                                )}
                              </Td>
                              <Td align="center">
                                {!f.pagato && !f.is_nota_credito && (
                                  <div
                                    style={{ display: 'flex', gap: 4, justifyContent: 'center' }}
                                  >
                                    <Button
                                      variant="success"
                                      size="sm"
                                      onClick={async () => {
                                        if (
                                          !window.confirm(
                                            `Confermi pagamento CASSA di ${formatEuro(f.importo_totale)} per fattura ${f.numero}?`
                                          )
                                        )
                                          return;
                                        try {
                                          await api.post('/api/fatture-ricevute/paga-manuale', {
                                            fattura_id: f.id,
                                            metodo: 'cassa',
                                            importo: f.importo_totale,
                                            fornitore:
                                              estrattoModal.fornitore?.ragione_sociale ||
                                              estrattoModal.fornitore?.denominazione ||
                                              '',
                                            numero_fattura: f.numero || '',
                                            data_pagamento: new Date().toISOString().split('T')[0],
                                          });
                                          reloadEstratto();
                                        } catch (e) {
                                          alert(
                                            'Errore: ' + (e.response?.data?.detail || e.message)
                                          );
                                        }
                                      }}
                                      style={{ padding: '3px 8px', fontSize: 10 }}
                                      title="Segna come pagata in contanti"
                                    >
                                      💵 Cassa
                                    </Button>
                                    <Button
                                      variant="info"
                                      size="sm"
                                      onClick={async () => {
                                        if (
                                          !window.confirm(
                                            `Confermi pagamento BANCA di ${formatEuro(f.importo_totale)} per fattura ${f.numero}?`
                                          )
                                        )
                                          return;
                                        try {
                                          await api.post('/api/fatture-ricevute/paga-manuale', {
                                            fattura_id: f.id,
                                            metodo: 'banca',
                                            importo: f.importo_totale,
                                            fornitore:
                                              estrattoModal.fornitore?.ragione_sociale ||
                                              estrattoModal.fornitore?.denominazione ||
                                              '',
                                            numero_fattura: f.numero || '',
                                            data_pagamento: new Date().toISOString().split('T')[0],
                                          });
                                          reloadEstratto();
                                        } catch (e) {
                                          alert(
                                            'Errore: ' + (e.response?.data?.detail || e.message)
                                          );
                                        }
                                      }}
                                      style={{ padding: '3px 8px', fontSize: 10 }}
                                      title="Segna come pagata con bonifico"
                                    >
                                      🏦 Banca
                                    </Button>
                                  </div>
                                )}
                              </Td>
                            </tr>
                          ))}
                          {(!estrattoModal.data.estratto ||
                            estrattoModal.data.estratto.length === 0) && (
                            <tr>
                              <Td
                                colSpan={9}
                                align="center"
                                style={{ padding: 40, color: COLORS.textMuted }}
                              >
                                Nessuna fattura trovata con i filtri selezionati
                              </Td>
                            </tr>
                          )}
                        </tbody>
                      </Table>
                    </TableWrap>
                  </>
                ) : null}
              </div>

              {/* Footer */}
              <div
                style={{
                  padding: '16px 24px',
                  borderTop: `1px solid ${COLORS.border}`,
                  background: COLORS.bgAlt,
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <div style={{ fontSize: 12, color: COLORS.textMuted }}>
                  Metodo pagamento predefinito fornitore:{' '}
                  <strong>
                    {estrattoModal.data?.fornitore?.metodo_pagamento_predefinito || '-'}
                  </strong>
                </div>
                <div style={{ display: 'flex', gap: 12 }}>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => {
                      const modal = document.getElementById('estratto-fatture-content');
                      if (!modal) {
                        window.print();
                        return;
                      }
                      const printWin = window.open('', '_blank');
                      printWin.document.write(`<html><head><title>Estratto Fatture</title><style>
                      body{font-family:Arial,sans-serif;padding:20px}
                      table{width:100%;border-collapse:collapse;font-size:12px}
                      th,td{border:1px solid #ddd;padding:8px;text-align:left}
                      th{background:${COLORS.primary};color:white}
                    </style></head><body>${modal.innerHTML}</body></html>`);
                      printWin.document.close();
                      printWin.print();
                    }}
                  >
                    🖨️ Stampa
                  </Button>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() => setEstrattoModal(prev => ({ ...prev, open: false }))}
                  >
                    Chiudi
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </Portal>
      )}

      {/* MODALE SCHEDE TECNICHE */}
      {schedeTecnicheModal.open && (
        <Portal>
          <div
            style={{
              position: 'fixed',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              background: 'rgba(0,0,0,0.5)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              zIndex: 9999,
            }}
            onClick={() =>
              setSchedeTecnicheModal({ open: false, fornitore: null, schede: [], loading: false })
            }
          >
            <div
              style={{
                background: COLORS.card,
                borderRadius: BORDER_RADIUS.lg,
                width: '90%',
                maxWidth: 800,
                maxHeight: '85vh',
                overflow: 'hidden',
                display: 'flex',
                flexDirection: 'column',
                boxShadow: SHADOWS.modal,
              }}
              onClick={e => e.stopPropagation()}
            >
              {/* Header */}
              <div
                style={{
                  padding: '20px 24px',
                  borderBottom: `1px solid ${COLORS.border}`,
                  background: COLORS.primary,
                  color: 'white',
                }}
              >
                <div
                  style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
                >
                  <div>
                    <h2 style={{ margin: 0, fontSize: 18, fontWeight: 'bold' }}>
                      📋 Schede Tecniche Prodotti
                    </h2>
                    <p style={{ margin: '4px 0 0 0', fontSize: 13, opacity: 0.9 }}>
                      {schedeTecnicheModal.fornitore?.ragione_sociale ||
                        schedeTecnicheModal.fornitore?.nome ||
                        schedeTecnicheModal.fornitore?.name}
                    </p>
                  </div>
                  <Button
                    variant="ghost"
                    onClick={() =>
                      setSchedeTecnicheModal({
                        open: false,
                        fornitore: null,
                        schede: [],
                        loading: false,
                      })
                    }
                    style={{
                      background: 'rgba(255,255,255,0.2)',
                      borderRadius: BORDER_RADIUS.full,
                      width: 40,
                      height: 40,
                      padding: 0,
                      color: 'white',
                      fontSize: 18,
                    }}
                  >
                    ×
                  </Button>
                </div>
              </div>

              {/* Content */}
              <div style={{ flex: 1, overflow: 'auto', padding: 24 }}>
                {schedeTecnicheModal.loading ? (
                  <div style={{ textAlign: 'center', padding: 60, color: COLORS.textMuted }}>
                    <div
                      style={{
                        width: 36,
                        height: 36,
                        border: `3px solid ${COLORS.border}`,
                        borderTop: `3px solid ${COLORS.info}`,
                        borderRadius: '50%',
                        animation: 'spin 1s linear infinite',
                        margin: '0 auto 16px',
                      }}
                    />
                    <style>{`@keyframes spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}`}</style>
                    Caricamento...
                  </div>
                ) : schedeTecnicheJob?.stato === 'in_corso' ? (
                  <div style={{ textAlign: 'center', padding: 40 }}>
                    <div
                      style={{
                        width: 40,
                        height: 40,
                        border: `4px solid ${COLORS.border}`,
                        borderTop: `4px solid ${COLORS.info}`,
                        borderRadius: '50%',
                        animation: 'spin 1s linear infinite',
                        margin: '0 auto 20px',
                      }}
                    />
                    <h3 style={{ color: COLORS.primary, margin: '0 0 8px 0', fontSize: 16 }}>
                      Ricerca in corso...
                    </h3>
                    <p style={{ color: COLORS.textMuted, fontSize: 13 }}>
                      Analisi fatture XML e ricerca PDF sul web
                    </p>
                    {schedeTecnicheJob?.prodotti_trovati?.length > 0 && (
                      <div
                        style={{
                          background: COLORS.infoLight,
                          borderRadius: BORDER_RADIUS.md,
                          padding: 16,
                          marginTop: 16,
                          textAlign: 'left',
                        }}
                      >
                        <p
                          style={{
                            margin: '0 0 8px 0',
                            fontWeight: 600,
                            fontSize: 13,
                            color: COLORS.primary,
                          }}
                        >
                          Prodotti trovati nelle fatture (
                          {schedeTecnicheJob.prodotti_trovati.length}):
                        </p>
                        {schedeTecnicheJob.prodotti_trovati.slice(0, 8).map((p, i) => (
                          <div key={i} style={{ fontSize: 12, color: COLORS.gray[700], padding: '3px 0' }}>
                            • {p}
                          </div>
                        ))}
                        {schedeTecnicheJob.prodotti_trovati.length > 8 && (
                          <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 4 }}>
                            ...e altri {schedeTecnicheJob.prodotti_trovati.length - 8}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ) : schedeTecnicheModal.schede.length === 0 ? (
                  <div style={{ textAlign: 'center', padding: 40 }}>
                    <div style={{ fontSize: 52, marginBottom: 16 }}>📄</div>
                    <h3 style={{ color: COLORS.gray[700], margin: '0 0 8px 0' }}>
                      Nessuna scheda tecnica
                    </h3>
                    <p style={{ color: COLORS.textMuted, margin: '0 0 4px 0' }}>
                      Nessuna scheda tecnica associata a questo fornitore.
                    </p>
                    <p style={{ color: COLORS.textSubtle, fontSize: 13, marginBottom: 24 }}>
                      Il sistema leggerà le fatture XML, identificherà i prodotti e cercherà le
                      schede tecniche ufficiali sul sito del produttore.
                    </p>
                    {schedeTecnicheJob?.stato === 'completato_vuoto' && (
                      <div
                        style={{
                          background: COLORS.warningLight,
                          borderRadius: BORDER_RADIUS.md,
                          padding: 12,
                          marginBottom: 16,
                          fontSize: 13,
                          color: COLORS.warning,
                        }}
                      >
                        Nessun prodotto trovato nelle fatture XML di questo fornitore.
                      </div>
                    )}
                    <Button variant="primary" onClick={handleCercaSchedeTecniche}>
                      Cerca automaticamente
                    </Button>
                  </div>
                ) : (
                  <div>
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        marginBottom: 16,
                      }}
                    >
                      <span style={{ fontSize: 13, color: COLORS.textMuted }}>
                        {schedeTecnicheModal.schede.length} prodotti •{' '}
                        <strong style={{ color: COLORS.success }}>
                          {schedeTecnicheModal.trovate || 0} schede trovate
                        </strong>
                        {(schedeTecnicheModal.da_cercare || 0) > 0 && (
                          <span style={{ color: COLORS.textSubtle }}>
                            {' '}
                            • {schedeTecnicheModal.da_cercare} da cercare
                          </span>
                        )}
                      </span>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={handleCercaSchedeTecniche}
                        style={{ background: COLORS.infoLight, borderColor: COLORS.infoLight }}
                      >
                        Aggiorna ricerca
                      </Button>
                    </div>
                    <div style={{ display: 'grid', gap: 10 }}>
                      {schedeTecnicheModal.schede.map((scheda, idx) => (
                        <div
                          key={scheda.id || idx}
                          style={{
                            background:
                              scheda.stato === 'trovato'
                                ? COLORS.successLight
                                : scheda.stato === 'url_trovato'
                                  ? COLORS.warningLight
                                  : COLORS.bgAlt,
                            borderRadius: BORDER_RADIUS.lg,
                            padding: '14px 16px',
                            border: `1px solid ${scheda.stato === 'trovato' ? COLORS.success : scheda.stato === 'url_trovato' ? COLORS.warning : COLORS.border}`,
                            display: 'flex',
                            alignItems: 'flex-start',
                            gap: 14,
                          }}
                        >
                          <div
                            style={{
                              width: 40,
                              height: 40,
                              borderRadius: BORDER_RADIUS.md,
                              flexShrink: 0,
                              background:
                                scheda.stato === 'trovato'
                                  ? COLORS.successLight
                                  : scheda.stato === 'url_trovato'
                                    ? COLORS.warningLight
                                    : scheda.stato === 'url_suggerito'
                                      ? COLORS.gray[200]
                                      : scheda.stato === 'non_cercato'
                                        ? COLORS.bg
                                        : COLORS.bg,
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              fontSize: 20,
                            }}
                          >
                            {scheda.stato === 'trovato'
                              ? '✅'
                              : scheda.stato === 'url_trovato'
                                ? '🔗'
                                : scheda.stato === 'url_suggerito'
                                  ? '💡'
                                  : scheda.stato === 'non_cercato'
                                    ? '🔍'
                                    : '❌'}
                          </div>
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div
                              style={{
                                fontWeight: 600,
                                fontSize: 14,
                                color: COLORS.primary,
                                marginBottom: 3,
                              }}
                            >
                              {scheda.prodotto_pulito || scheda.prodotto}
                            </div>
                            {scheda.brand && (
                              <div style={{ fontSize: 12, color: COLORS.textMuted, marginBottom: 2 }}>
                                Brand: <strong>{scheda.brand}</strong>
                              </div>
                            )}
                            {scheda.sito_ufficiale && (
                              <div style={{ fontSize: 11, color: COLORS.textMuted, marginBottom: 2 }}>
                                Sito: {scheda.sito_ufficiale}
                              </div>
                            )}
                            <div style={{ fontSize: 11, color: COLORS.textSubtle }}>
                              {scheda.stato === 'trovato' &&
                                `PDF scaricato • ${Math.round((scheda.dimensione_bytes || 0) / 1024)} KB`}
                              {scheda.stato === 'url_trovato' &&
                                'URL trovato (PDF non scaricabile direttamente)'}
                              {scheda.stato === 'url_suggerito' &&
                                'URL suggerito da AI — verifica manuale'}
                              {scheda.stato === 'non_trovato' && 'Scheda non trovata online'}
                              {scheda.stato === 'non_cercato' &&
                                'Non ancora cercato — clicca "Cerca automaticamente"'}
                            </div>
                          </div>
                          {(scheda.stato === 'trovato' ||
                            scheda.stato === 'url_trovato' ||
                            scheda.stato === 'url_suggerito') && (
                            <a
                              href={
                                scheda.stato === 'trovato'
                                  ? `${window.location.origin}/api/schede-tecniche/download/${scheda.id}`
                                  : scheda.url_fonte
                              }
                              target="_blank"
                              rel="noopener noreferrer"
                              style={{
                                padding: '6px 14px',
                                background: scheda.stato === 'trovato' ? COLORS.info : COLORS.primary,
                                color: 'white',
                                borderRadius: BORDER_RADIUS.sm,
                                textDecoration: 'none',
                                fontSize: 12,
                                fontWeight: 500,
                                whiteSpace: 'nowrap',
                              }}
                            >
                              {scheda.stato === 'trovato' ? 'Scarica PDF' : 'Apri link'}
                            </a>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Footer */}
              <div
                style={{
                  padding: '16px 24px',
                  borderTop: `1px solid ${COLORS.border}`,
                  background: COLORS.bgAlt,
                  display: 'flex',
                  justifyContent: 'flex-end',
                }}
              >
                <Button
                  variant="primary"
                  onClick={() =>
                    setSchedeTecnicheModal({
                      open: false,
                      fornitore: null,
                      schede: [],
                      loading: false,
                    })
                  }
                >
                  Chiudi
                </Button>
              </div>
            </div>
          </div>
        </Portal>
      )}
    </div>
  );
}
