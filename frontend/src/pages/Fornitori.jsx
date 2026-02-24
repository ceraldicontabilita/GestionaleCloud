import React, { useState, useEffect, useCallback, useRef } from 'react';
import ReactDOM from 'react-dom';
import { useNavigate, Link } from 'react-router-dom';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import Portal from '../components/Portal';
import { PageLayout } from '../components/PageLayout';
import { formatEuro, formatDateIT, STYLES, COLORS, button, badge } from '../lib/utils';
import { 
  Search, Edit2, Trash2, Plus, FileText, Building2, 
  Phone, Mail, MapPin, CreditCard, AlertCircle, Check,
  Users, X, TrendingUp, Brain, ExternalLink, RefreshCw
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

// Dizionario Metodi di Pagamento - allineato con il backend
const METODI_PAGAMENTO = {
  contanti: { label: 'Contanti', bg: '#dcfce7', color: '#16a34a' },
  bonifico: { label: 'Bonifico', bg: '#dbeafe', color: '#1535a8' },
  assegno: { label: 'Assegno', bg: '#fef3c7', color: '#d97706' },
  misto: { label: 'Misto', bg: '#f3e8ff', color: '#9333ea' },
  carta: { label: 'Carta', bg: '#fce7f3', color: '#db2777' },
  sepa: { label: 'SEPA', bg: '#e0e7ff', color: '#4f46e5' }
};

const getMetodo = (key) => METODI_PAGAMENTO[key] || METODI_PAGAMENTO.bonifico;

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
  iban_lista: [],  // Lista di IBAN aggiuntivi estratti dalle fatture
  metodo_pagamento: 'bonifico',
  giorni_pagamento: 30,
  esclude_magazzino: false,
  note: ''
};

// Modale Fornitore
function SupplierModal({ isOpen, onClose, supplier, onSave, saving }) {
  const [form, setForm] = useState(emptySupplier);
  const [loadingOpenAPI, setLoadingOpenAPI] = useState(false);
  const [openAPIError, setOpenAPIError] = useState(null);
  const isNew = !supplier?.id;
  
  useEffect(() => {
    if (isOpen && supplier) {
      setForm({ ...emptySupplier, ...supplier });
    } else if (isOpen) {
      setForm(emptySupplier);
    }
    setOpenAPIError(null);
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
          codice_sdi: mapped.codice_sdi || prev.codice_sdi
        }));
      }
    } catch (err) {
      setOpenAPIError(err.response?.data?.detail || 'Errore nel recupero dati');
    } finally {
      setLoadingOpenAPI(false);
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
    <div style={{
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
      padding: '20px'
    }}>
      <div style={{
        backgroundColor: 'white',
        borderRadius: '16px',
        width: '100%',
        maxWidth: '600px',
        maxHeight: '85vh',
        overflow: 'hidden',
        boxShadow: '0 20px 50px rgba(0,0,0,0.3)'
      }}>
        {/* Header */}
        <div style={{
          background: 'linear-gradient(135deg, #1535a8 0%, #2050e8 100%)',
          padding: '20px 24px',
          color: 'white'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <h2 style={{ margin: 0, fontSize: '20px', fontWeight: 600 }}>
                {isNew ? 'Nuovo Fornitore' : 'Modifica Anagrafica'}
              </h2>
              <p style={{ margin: '4px 0 0', opacity: 0.9, fontSize: '14px' }}>
                {isNew ? 'Inserisci i dati del fornitore' : form.ragione_sociale}
              </p>
            </div>
            <button onClick={onClose} style={{
              background: 'rgba(255,255,255,0.2)',
              border: 'none',
              borderRadius: '8px',
              padding: '8px',
              cursor: 'pointer',
              color: 'white'
            }}>
              <X size={20} />
            </button>
          </div>
        </div>

        {/* Form */}
        <div style={{ padding: '24px', overflowY: 'auto', maxHeight: 'calc(85vh - 140px)' }}>
          <div style={{ display: 'grid', gap: '16px' }}>
            {/* Ragione Sociale */}
            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 500, color: '#374151', marginBottom: '6px' }}>
                Ragione Sociale *
              </label>
              <input
                type="text"
                value={form.ragione_sociale || ''}
                onChange={(e) => handleChange('ragione_sociale', e.target.value)}
                style={{
                  width: '100%',
                  padding: '10px 14px',
                  border: '1px solid #e5e7eb',
                  borderRadius: '8px',
                  fontSize: '14px',
                  boxSizing: 'border-box'
                }}
                placeholder="Nome azienda"
              />
            </div>

            {/* P.IVA e CF */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 500, color: '#374151', marginBottom: '6px' }}>
                  Partita IVA
                </label>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <input
                    type="text"
                    value={form.partita_iva || ''}
                    onChange={(e) => handleChange('partita_iva', e.target.value)}
                    style={{
                      flex: 1,
                      padding: '10px 14px',
                      border: '1px solid #e5e7eb',
                      borderRadius: '8px',
                      fontSize: '14px',
                      fontFamily: 'monospace',
                      boxSizing: 'border-box'
                    }}
                    placeholder="01234567890"
                  />
                  <button
                    type="button"
                    onClick={handleLoadFromOpenAPI}
                    disabled={loadingOpenAPI || !form.partita_iva}
                    title="Carica dati da Camera di Commercio"
                    style={{
                      padding: '10px 12px',
                      border: 'none',
                      borderRadius: '8px',
                      background: loadingOpenAPI ? '#9ca3af' : 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
                      color: 'white',
                      cursor: loadingOpenAPI || !form.partita_iva ? 'not-allowed' : 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                      fontSize: '12px',
                      fontWeight: 600,
                      whiteSpace: 'nowrap'
                    }}
                    data-testid="btn-load-openapi"
                  >
                    <RefreshCw size={14} className={loadingOpenAPI ? 'animate-spin' : ''} />
                    {loadingOpenAPI ? '...' : 'Auto'}
                  </button>
                </div>
                {openAPIError && (
                  <p style={{ margin: '4px 0 0', fontSize: '12px', color: '#dc2626' }}>
                    {openAPIError}
                  </p>
                )}
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 500, color: '#374151', marginBottom: '6px' }}>
                  Codice Fiscale
                </label>
                <input
                  type="text"
                  value={form.codice_fiscale || ''}
                  onChange={(e) => handleChange('codice_fiscale', e.target.value.toUpperCase())}
                  style={{
                    width: '100%',
                    padding: '10px 14px',
                    border: '1px solid #e5e7eb',
                    borderRadius: '8px',
                    fontSize: '14px',
                    fontFamily: 'monospace',
                    boxSizing: 'border-box'
                  }}
                />
              </div>
            </div>

            {/* Indirizzo */}
            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 500, color: '#374151', marginBottom: '6px' }}>
                Indirizzo
              </label>
              <input
                type="text"
                value={form.indirizzo || ''}
                onChange={(e) => handleChange('indirizzo', e.target.value)}
                style={{
                  width: '100%',
                  padding: '10px 14px',
                  border: '1px solid #e5e7eb',
                  borderRadius: '8px',
                  fontSize: '14px',
                  boxSizing: 'border-box'
                }}
                placeholder="Via, numero civico"
              />
            </div>

            {/* CAP, Comune, Provincia */}
            <div style={{ display: 'grid', gridTemplateColumns: '100px 1fr 80px', gap: '12px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 500, color: '#374151', marginBottom: '6px' }}>CAP</label>
                <input
                  type="text"
                  value={form.cap || ''}
                  onChange={(e) => handleChange('cap', e.target.value)}
                  style={{ width: '100%', padding: '10px 14px', border: '1px solid #e5e7eb', borderRadius: '8px', fontSize: '14px', boxSizing: 'border-box' }}
                  maxLength={5}
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 500, color: '#374151', marginBottom: '6px' }}>Comune</label>
                <input
                  type="text"
                  value={form.comune || ''}
                  onChange={(e) => handleChange('comune', e.target.value)}
                  style={{ width: '100%', padding: '10px 14px', border: '1px solid #e5e7eb', borderRadius: '8px', fontSize: '14px', boxSizing: 'border-box' }}
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 500, color: '#374151', marginBottom: '6px' }}>Prov</label>
                <input
                  type="text"
                  value={form.provincia || ''}
                  onChange={(e) => handleChange('provincia', e.target.value.toUpperCase())}
                  style={{ width: '100%', padding: '10px 14px', border: '1px solid #e5e7eb', borderRadius: '8px', fontSize: '14px', boxSizing: 'border-box' }}
                  maxLength={2}
                />
              </div>
            </div>

            {/* Telefono, Email */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 500, color: '#374151', marginBottom: '6px' }}>Telefono</label>
                <input
                  type="tel"
                  value={form.telefono || ''}
                  onChange={(e) => handleChange('telefono', e.target.value)}
                  style={{ width: '100%', padding: '10px 14px', border: '1px solid #e5e7eb', borderRadius: '8px', fontSize: '14px', boxSizing: 'border-box' }}
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 500, color: '#374151', marginBottom: '6px' }}>Email</label>
                <input
                  type="email"
                  value={form.email || ''}
                  onChange={(e) => handleChange('email', e.target.value)}
                  style={{ width: '100%', padding: '10px 14px', border: '1px solid #e5e7eb', borderRadius: '8px', fontSize: '14px', boxSizing: 'border-box' }}
                />
              </div>
            </div>

            {/* Metodo pagamento e giorni */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 500, color: '#374151', marginBottom: '6px' }}>Metodo Pagamento</label>
                <select
                  value={form.metodo_pagamento || 'bonifico'}
                  onChange={(e) => handleChange('metodo_pagamento', e.target.value)}
                  style={{ width: '100%', padding: '10px 14px', border: '1px solid #e5e7eb', borderRadius: '8px', fontSize: '14px', backgroundColor: 'white', boxSizing: 'border-box' }}
                >
                  {Object.entries(METODI_PAGAMENTO).filter(([k]) => k !== 'banca').map(([key, val]) => (
                    <option key={key} value={key}>{val.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: 500, color: '#374151', marginBottom: '6px' }}>Giorni Pagamento</label>
                <input
                  type="number"
                  value={form.giorni_pagamento || 30}
                  onChange={(e) => handleChange('giorni_pagamento', parseInt(e.target.value) || 30)}
                  style={{ width: '100%', padding: '10px 14px', border: '1px solid #e5e7eb', borderRadius: '8px', fontSize: '14px', boxSizing: 'border-box' }}
                  min={0}
                />
              </div>
            </div>

            {/* IBAN e lista IBAN aggiuntivi */}
            <div>
              <label style={{ display: 'block', fontSize: '13px', fontWeight: 500, color: '#374151', marginBottom: '6px' }}>
                IBAN Principale
              </label>
              <input
                type="text"
                value={form.iban || ''}
                onChange={(e) => handleChange('iban', e.target.value.toUpperCase().replace(/\s/g, ''))}
                style={{
                  width: '100%',
                  padding: '10px 14px',
                  border: '1px solid #e5e7eb',
                  borderRadius: '8px',
                  fontSize: '14px',
                  fontFamily: 'monospace',
                  boxSizing: 'border-box'
                }}
                placeholder="IT60X0542811101000000123456"
              />
              {/* Lista IBAN aggiuntivi */}
              {form.iban_lista && form.iban_lista.length > 0 && (
                <div style={{ marginTop: '8px', padding: '10px', background: '#f8fafc', borderRadius: '6px' }}>
                  <div style={{ fontSize: '12px', color: '#6b7280', marginBottom: '6px' }}>IBAN aggiuntivi (da fatture):</div>
                  {form.iban_lista.map((iban, idx) => (
                    <div key={idx} style={{ 
                      display: 'flex', 
                      justifyContent: 'space-between', 
                      alignItems: 'center',
                      padding: '4px 8px',
                      background: 'white',
                      borderRadius: '4px',
                      marginBottom: '4px',
                      fontSize: '12px',
                      fontFamily: 'monospace'
                    }}>
                      <span>{iban}</span>
                      <button 
                        type="button"
                        onClick={() => handleChange('iban', iban)}
                        style={{ 
                          background: '#e0f2fe', 
                          border: 'none', 
                          borderRadius: '4px', 
                          padding: '2px 8px', 
                          cursor: 'pointer',
                          fontSize: '11px',
                          color: '#0369a1'
                        }}
                      >
                        Usa come principale
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
            
            {/* Esclude Magazzino */}
            <div style={{ 
              padding: '14px', 
              background: form.esclude_magazzino ? '#fef3c7' : '#f8fafc', 
              borderRadius: '10px',
              border: form.esclude_magazzino ? '1px solid #fbbf24' : '1px solid #e2e8f0'
            }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '12px', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={form.esclude_magazzino || false}
                  onChange={(e) => handleChange('esclude_magazzino', e.target.checked)}
                  style={{ width: '18px', height: '18px', accentColor: '#f59e0b' }}
                />
                <div>
                  <div style={{ fontSize: '14px', fontWeight: 600, color: '#374151' }}>
                    Esclude dal Magazzino
                  </div>
                  <div style={{ fontSize: '12px', color: '#6b7280', marginTop: '2px' }}>
                    I prodotti di questo fornitore NON verranno caricati in magazzino (es. manutenzione, servizi, ferramenta)
                  </div>
                </div>
              </label>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div style={{
          padding: '16px 24px',
          borderTop: '1px solid #e5e7eb',
          display: 'flex',
          justifyContent: 'flex-end',
          gap: '12px',
          backgroundColor: '#f9fafb'
        }}>
          <button onClick={onClose} style={{
            padding: '10px 20px',
            border: '1px solid #e5e7eb',
            borderRadius: '8px',
            backgroundColor: 'white',
            cursor: 'pointer',
            fontSize: '14px',
            fontWeight: 500
          }}>
            Annulla
          </button>
          <button onClick={handleSubmit} disabled={saving} style={{
            padding: '10px 20px',
            border: 'none',
            borderRadius: '8px',
            background: 'linear-gradient(135deg, #1535a8 0%, #2050e8 100%)',
            color: 'white',
            cursor: saving ? 'not-allowed' : 'pointer',
            fontSize: '14px',
            fontWeight: 500,
            opacity: saving ? 0.7 : 1,
            display: 'flex',
            alignItems: 'center',
            gap: '8px'
          }}>
            {saving ? 'Salvataggio...' : <><Check size={16} /> Salva</>}
          </button>
        </div>
      </div>
    </div>
    </Portal>
  );
}

// Stat Card
function StatCard({ icon: Icon, label, value, color, bgColor }) {
  return (
    <div style={{
      backgroundColor: 'white',
      borderRadius: '12px',
      padding: '20px',
      display: 'flex',
      alignItems: 'center',
      gap: '16px',
      boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
      border: '1px solid #f0f0f0'
    }}>
      <div style={{
        width: '48px',
        height: '48px',
        borderRadius: '12px',
        backgroundColor: bgColor,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center'
      }}>
        <Icon size={24} color={color} />
      </div>
      <div>
        <div style={{ fontSize: '28px', fontWeight: 700, color: color }}>{value}</div>
        <div style={{ fontSize: '13px', color: '#6b7280' }}>{label}</div>
      </div>
    </div>
  );
}

// Supplier Card con cambio rapido metodo
function SupplierCard({ supplier, onEdit, onDelete, onViewInvoices, onChangeMetodo, onSearchPiva, onShowFatturato, onShowSchedeTecniche, selectedYear }) {
  const nome = supplier.ragione_sociale || supplier.denominazione || 'Senza nome';
  const hasIncomplete = !supplier.partita_iva || !supplier.email;
  const hasPiva = !!supplier.partita_iva;
  const metodoKey = supplier.metodo_pagamento || 'bonifico';
  const metodo = getMetodo(metodoKey);
  const [showMetodoMenu, setShowMetodoMenu] = useState(false);
  const [updating, setUpdating] = useState(false);
  const [searching, setSearching] = useState(false);
  const [loadingFatturato, setLoadingFatturato] = useState(false);
  const [menuPosition, setMenuPosition] = useState({ top: 0, left: 0 });
  const buttonRef = React.useRef(null);
  
  const handleShowFatturato = async () => {
    if (!supplier.partita_iva) {
      alert('Questo fornitore non ha una Partita IVA');
      return;
    }
    setLoadingFatturato(true);
    await onShowFatturato(supplier, selectedYear);
    setLoadingFatturato(false);
  };

  const handleMetodoChange = async (newMetodo) => {
    if (newMetodo === metodoKey) {
      setShowMetodoMenu(false);
      return;
    }
    setUpdating(true);
    setShowMetodoMenu(false);
    await onChangeMetodo(supplier.id, newMetodo);
    setUpdating(false);
  };

  const handleSearchPiva = async () => {
    if (!supplier.partita_iva) return;
    setSearching(true);
    await onSearchPiva(supplier);
    setSearching(false);
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
          left: rect.right - 170
        });
      } else {
        setMenuPosition({
          top: rect.bottom + 4,
          left: rect.right - 170
        });
      }
    }
    setShowMetodoMenu(true);
  };

  return (
    <div style={{
      backgroundColor: 'white',
      borderRadius: '12px',
      border: '1px solid #e5e7eb',
      overflow: 'hidden',
      transition: 'all 0.2s',
      position: 'relative'
    }}
    onMouseEnter={(e) => { e.currentTarget.style.boxShadow = '0 8px 25px rgba(0,0,0,0.1)'; e.currentTarget.style.transform = 'translateY(-2px)'; }}
    onMouseLeave={(e) => { e.currentTarget.style.boxShadow = 'none'; e.currentTarget.style.transform = 'translateY(0)'; }}
    >
      {/* Barra colore in alto */}
      <div style={{ 
        height: '4px', 
        background: hasIncomplete 
          ? 'linear-gradient(90deg, #f59e0b, #fbbf24)' 
          : 'linear-gradient(90deg, #1535a8, #2050e8)'
      }} />
      
      <div style={{ padding: '16px' }}>
        {/* Nome e Badge */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flex: 1, minWidth: 0 }}>
            <div style={{
              width: '44px',
              height: '44px',
              borderRadius: '10px',
              background: 'linear-gradient(135deg, #1535a8 0%, #2050e8 100%)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'white',
              fontWeight: 600,
              fontSize: '18px',
              flexShrink: 0
            }}>
              {nome[0].toUpperCase()}
            </div>
            <div style={{ minWidth: 0 }}>
              <div style={{ 
                fontWeight: 600, 
                color: '#1f2937', 
                fontSize: '15px',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis'
              }}>
                {nome}
              </div>
              {supplier.partita_iva && (
                <div style={{ fontSize: '12px', color: '#6b7280', fontFamily: 'monospace' }}>
                  P.IVA {supplier.partita_iva}
                </div>
              )}
            </div>
          </div>
          {hasIncomplete && (
            <div style={{ 
              backgroundColor: '#fef3c7', 
              borderRadius: '50%', 
              padding: '6px',
              flexShrink: 0
            }} title="Dati incompleti">
              <AlertCircle size={14} color="#d97706" />
            </div>
          )}
        </div>

        {/* Info */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '16px' }}>
          {supplier.comune && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', color: '#6b7280' }}>
              <MapPin size={14} />
              <span>{supplier.comune}{supplier.provincia && ` (${supplier.provincia})`}</span>
            </div>
          )}
          {supplier.email && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', color: '#6b7280' }}>
              <Mail size={14} />
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{supplier.email}</span>
            </div>
          )}
        </div>

        {/* Stats e Metodo Pagamento */}
        <div style={{ 
          display: 'flex', 
          alignItems: 'center', 
          justifyContent: 'space-between',
          paddingTop: '12px',
          borderTop: '1px solid #f3f4f6'
        }}>
          <div style={{ display: 'flex', gap: '20px' }}>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '18px', fontWeight: 700, color: '#1f2937' }}>{supplier.fatture_count || 0}</div>
              <div style={{ fontSize: '11px', color: '#9ca3af' }}>Fatture</div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '18px', fontWeight: 700, color: '#1f2937' }}>{supplier.giorni_pagamento || 30}</div>
              <div style={{ fontSize: '11px', color: '#9ca3af' }}>Giorni</div>
            </div>
          </div>
          
          {/* Badge Metodo - Cliccabile per cambio rapido */}
          <div style={{ position: 'relative' }}>
            <button
              ref={buttonRef}
              onClick={openMenu}
              disabled={updating}
              style={{
                padding: '6px 12px',
                borderRadius: '8px',
                fontSize: '12px',
                fontWeight: 600,
                backgroundColor: metodo.bg,
                color: metodo.color,
                border: `2px solid ${metodo.color}20`,
                cursor: updating ? 'wait' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                transition: 'all 0.2s',
                opacity: updating ? 0.6 : 1
              }}
              title="Clicca per cambiare metodo pagamento"
            >
              <CreditCard size={12} />
              {updating ? '...' : metodo.label}
              <span style={{ marginLeft: '2px', fontSize: '10px' }}>▼</span>
            </button>
          </div>
        </div>
      </div>

      {/* Actions */}
      <div style={{ 
        display: 'flex', 
        borderTop: '1px solid #f3f4f6',
        backgroundColor: '#f9fafb',
        flexWrap: 'wrap'
      }}>
        {/* Pulsante Fatturato Anno */}
        {hasPiva && (
          <button onClick={handleShowFatturato} disabled={loadingFatturato} style={{
            flex: 1,
            padding: '12px',
            border: 'none',
            backgroundColor: loadingFatturato ? '#e0f2fe' : 'transparent',
            cursor: loadingFatturato ? 'wait' : 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '6px',
            fontSize: '13px',
            color: '#0284c7',
            transition: 'all 0.2s',
            minWidth: '70px'
          }}
          onMouseEnter={(e) => { if (!loadingFatturato) { e.currentTarget.style.backgroundColor = '#e0f2fe'; } }}
          onMouseLeave={(e) => { if (!loadingFatturato) { e.currentTarget.style.backgroundColor = 'transparent'; } }}
          title={`Visualizza fatturato ${selectedYear}`}
          data-testid={`btn-fatturato-${supplier.id}`}
          >
            <TrendingUp size={15} /> {loadingFatturato ? '...' : `${selectedYear}`}
          </button>
        )}
        {/* Pulsante Fatturato anno precedente - sempre visibile */}
        {selectedYear !== (selectedYear - 1) && (
          <button onClick={async () => {
            setLoadingFatturato(true);
            await onShowFatturato(supplier, selectedYear - 1);
            setLoadingFatturato(false);
          }} disabled={loadingFatturato} style={{
            flex: 1,
            padding: '12px',
            border: 'none',
            backgroundColor: loadingFatturato ? '#e0f2fe' : 'transparent',
            cursor: loadingFatturato ? 'wait' : 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '6px',
            fontSize: '13px',
            color: '#6b7280',
            transition: 'all 0.2s',
            minWidth: '70px'
          }}
          onMouseEnter={(e) => { if (!loadingFatturato) { e.currentTarget.style.backgroundColor = '#f3f4f6'; } }}
          onMouseLeave={(e) => { if (!loadingFatturato) { e.currentTarget.style.backgroundColor = 'transparent'; } }}
          title={`Visualizza fatturato ${selectedYear - 1}`}
          >
            <TrendingUp size={15} /> {selectedYear - 1}
          </button>
        )}
        {/* Pulsante Cerca P.IVA - sempre visibile se ha P.IVA */}
        {hasPiva && (
          <button onClick={handleSearchPiva} disabled={searching} style={{
            flex: 1,
            padding: '12px',
            border: 'none',
            backgroundColor: searching ? '#fef3c7' : 'transparent',
            cursor: searching ? 'wait' : 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '6px',
            fontSize: '13px',
            color: '#d97706',
            transition: 'all 0.2s'
          }}
          onMouseEnter={(e) => { if (!searching) { e.currentTarget.style.backgroundColor = '#fef3c7'; } }}
          onMouseLeave={(e) => { if (!searching) { e.currentTarget.style.backgroundColor = 'transparent'; } }}
          title="Cerca dati azienda tramite Partita IVA"
          >
            <Search size={15} /> {searching ? 'Ricerca...' : 'Cerca P.IVA'}
          </button>
        )}
        {/* Pulsante Schede Tecniche */}
        <button onClick={() => onShowSchedeTecniche && onShowSchedeTecniche(supplier)} style={{
          flex: 1,
          padding: '12px',
          border: 'none',
          borderLeft: hasPiva ? '1px solid #e5e7eb' : 'none',
          backgroundColor: 'transparent',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '6px',
          fontSize: '13px',
          color: '#8b5cf6',
          transition: 'all 0.2s'
        }}
        onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = '#f3e8ff'; }}
        onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent'; }}
        title="Visualizza schede tecniche prodotti"
        data-testid={`btn-schede-tecniche-${supplier.id}`}
        >
          📋 Schede
        </button>
        <button onClick={() => onViewInvoices(supplier)} style={{
          flex: 1,
          padding: '12px',
          border: 'none',
          borderLeft: hasPiva ? '1px solid #e5e7eb' : 'none',
          backgroundColor: 'transparent',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '6px',
          fontSize: '13px',
          color: '#6b7280',
          transition: 'all 0.2s'
        }}
        onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = '#eef2ff'; e.currentTarget.style.color = '#4f46e5'; }}
        onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent'; e.currentTarget.style.color = '#6b7280'; }}
        >
          <FileText size={15} /> Fatture
        </button>
        <button onClick={() => onEdit(supplier)} style={{
          flex: 1,
          padding: '12px',
          border: 'none',
          borderLeft: '1px solid #e5e7eb',
          backgroundColor: 'transparent',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '6px',
          fontSize: '13px',
          color: '#6b7280',
          transition: 'all 0.2s'
        }}
        onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = '#eef2ff'; e.currentTarget.style.color = '#4f46e5'; }}
        onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent'; e.currentTarget.style.color = '#6b7280'; }}
        >
          <Edit2 size={15} /> Modifica
        </button>
        <button onClick={() => onDelete(supplier.id)} style={{
          padding: '12px 16px',
          border: 'none',
          borderLeft: '1px solid #e5e7eb',
          backgroundColor: 'transparent',
          cursor: 'pointer',
          color: '#9ca3af',
          transition: 'all 0.2s'
        }}
        onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = '#fef2f2'; e.currentTarget.style.color = '#dc2626'; }}
        onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent'; e.currentTarget.style.color = '#9ca3af'; }}
        >
          <Trash2 size={15} />
        </button>
      </div>

      {/* Menu dropdown con Portal - fuori dalla card */}
      {showMetodoMenu && (
        <Portal>
          {/* Overlay per chiudere */}
          <div 
            style={{ 
              position: 'fixed', 
              inset: 0, 
              zIndex: 99998,
              background: 'transparent'
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
              borderRadius: '10px',
              boxShadow: '0 10px 40px rgba(0,0,0,0.25)',
              border: '1px solid #e5e7eb',
              overflow: 'hidden',
              zIndex: 99999,
              minWidth: '160px'
            }}
          >
            <div style={{ padding: '8px 12px', borderBottom: '1px solid #f1f5f9', fontSize: '11px', color: '#9ca3af', fontWeight: 600 }}>
              METODO PAGAMENTO
            </div>
            {Object.entries(METODI_PAGAMENTO).map(([key, val]) => (
              <button
                key={key}
                onClick={() => handleMetodoChange(key)}
                style={{
                  width: '100%',
                  padding: '10px 14px',
                  border: 'none',
                  backgroundColor: metodoKey === key ? val.bg : 'white',
                  color: val.color,
                  fontSize: '13px',
                  fontWeight: 500,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '10px',
                  textAlign: 'left',
                  transition: 'all 0.15s'
                }}
                onMouseEnter={(e) => { if (metodoKey !== key) e.currentTarget.style.backgroundColor = '#f9fafb'; }}
                onMouseLeave={(e) => { if (metodoKey !== key) e.currentTarget.style.backgroundColor = 'white'; }}
              >
                <span style={{
                  width: '10px',
                  height: '10px',
                  borderRadius: '50%',
                  backgroundColor: val.color
                }} />
                {val.label}
                {metodoKey === key && <Check size={16} style={{ marginLeft: 'auto' }} />}
              </button>
            ))}
          </div>
        </Portal>
      )}
    </div>
  );
}

export default function Fornitori() {
  const { anno: selectedYear } = useAnnoGlobale();
  const navigate = useNavigate();
  const [suppliers, setSuppliers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [filterMetodo, setFilterMetodo] = useState('tutti');
  const [filterIncomplete, setFilterIncomplete] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [currentSupplier, setCurrentSupplier] = useState(null);
  const [saving, setSaving] = useState(false);
  
  // === SCHEDE TECNICHE STATE ===
  const [schedeTecnicheModal, setSchedeTecnicheModal] = useState({ open: false, fornitore: null, schede: [], loading: false });
  
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
        params.append('limit', '1000');  // Carica tutti i fornitori
        params.append('use_cache', 'false');  // Forza refresh
        
        const res = await api.get(`/api/suppliers?${params}`, {
          signal: controller.signal
        });
        setSuppliers(res.data);
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
  }, [debouncedSearch]);
  
  // Funzione per ricaricare i dati (usata dopo save/delete)
  const reloadData = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (debouncedSearch) params.append('search', debouncedSearch);
      params.append('limit', '1000');
      params.append('use_cache', 'false');
      
      const res = await api.get(`/api/suppliers?${params}`);
      setSuppliers(res.data);
    } catch (error) {
      console.error('Error reloading suppliers:', error);
    } finally {
      setLoading(false);
    }
  }, [debouncedSearch]);

  const filteredSuppliers = suppliers.filter(s => {
    if (filterMetodo !== 'tutti') {
      const metodo = s.metodo_pagamento || 'bonifico';
      if (metodo !== filterMetodo) return false;
    }
    if (filterIncomplete && s.partita_iva && s.email) return false;
    return true;
  });

  // Salvataggio completo fornitore
  const handleSave = async (formData) => {
    setSaving(true);
    try {
      let response;
      if (currentSupplier?.id) {
        // UPDATE nel database
        response = await api.put(`/api/suppliers/${currentSupplier.id}`, formData);
      } else {
        // INSERT nel database
        response = await api.post('/api/suppliers', { denominazione: formData.ragione_sociale, ...formData });
      }
      
      // Mostra feedback se sono stati rimossi prodotti dal magazzino
      if (response.data?.prodotti_rimossi_magazzino > 0) {
        alert(`✅ Fornitore salvato!\n\n🗑️ ${response.data.prodotti_rimossi_magazzino} prodotti rimossi automaticamente dal magazzino (fornitore escluso).`);
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
    try {
      // UPDATE metodo_pagamento nel database
      await api.put(`/api/suppliers/${supplierId}`, { metodo_pagamento: newMetodo });
      
      // Aggiorna lo stato locale immediatamente
      setSuppliers(prev => prev.map(s => 
        s.id === supplierId ? { ...s, metodo_pagamento: newMetodo } : s
      ));
    } catch (error) {
      alert('Errore aggiornamento metodo: ' + (error.response?.data?.detail || error.message));
    }
  };

  // Eliminazione fornitore dal database
  const handleDelete = async (id, forceDelete = false) => {
    try {
      // DELETE dal database
      const url = forceDelete ? `/api/suppliers/${id}?force=true` : `/api/suppliers/${id}`;
      await api.delete(url);
      reloadData(); // Ricarica dati
    } catch (error) {
      const errorMsg = error.response?.data?.detail || error.response?.data?.message || error.message;
      // Se ci sono fatture collegate, procedi con eliminazione forzata
      if (error.response?.status === 400 && errorMsg.includes('fatture collegate')) {
        handleDelete(id, true); // Riprova con force=true
      } else {
        alert('Errore eliminazione: ' + errorMsg);
      }
    }
  };

  const handleViewInvoices = (supplier) => {
    // Apre il modale con estratto fatture invece di navigare
    handleViewInvoicesModal(supplier);
  };

  // Ricerca dati azienda tramite Partita IVA
  const handleSearchPiva = async (supplier) => {
    if (!supplier.partita_iva) {
      alert('Questo fornitore non ha una Partita IVA');
      return;
    }
    
    try {
      const res = await api.get(`/api/suppliers/search-piva/${supplier.partita_iva}`);
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
          alert(`Nessun dato nuovo trovato per ${supplier.ragione_sociale || supplier.partita_iva}.\nI dati sono già completi o non disponibili su VIES.`);
        }
      } else {
        alert(`Partita IVA ${supplier.partita_iva} non trovata nel database VIES.\n\nNota: VIES contiene solo aziende registrate per operazioni intracomunitarie UE.`);
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
    filtri: { anno: selectedYear, data_da: '', data_a: '', importo_min: '', importo_max: '', tipo: 'tutti' }
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
  const handleViewInvoicesModal = async (supplier) => {
    if (!supplier.partita_iva && !supplier.id) {
      alert('Questo fornitore non ha una Partita IVA');
      return;
    }
    
    setEstrattoModal({ 
      open: true, 
      fornitore: supplier, 
      data: null, 
      loading: true,
      filtri: { anno: selectedYear, data_da: '', data_a: '', importo_min: '', importo_max: '', tipo: 'tutti' }
    });
    
    try {
      const res = await api.get(`/api/suppliers/${supplier.id || supplier.partita_iva}/fatture?anno=${selectedYear}`);
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
      
      const res = await api.get(`/api/suppliers/${estrattoModal.fornitore.id || estrattoModal.fornitore.partita_iva}/fatture?${params.toString()}`);
      setEstrattoModal(prev => ({ ...prev, data: res.data, loading: false }));
    } catch (error) {
      alert('Errore: ' + (error.response?.data?.detail || error.message));
      setEstrattoModal(prev => ({ ...prev, loading: false }));
    }
  };

  // === SCHEDE TECNICHE FUNCTIONS ===
  const handleViewSchedeTecniche = async (supplier) => {
    setSchedeTecnicheModal({ open: true, fornitore: supplier, schede: [], loading: true });
    
    try {
      const res = await api.get(`/api/schede-tecniche/fornitore/${supplier.id}`);
      setSchedeTecnicheModal(prev => ({ ...prev, schede: res.data.schede || [], loading: false }));
    } catch (error) {
      console.error('Errore caricamento schede tecniche:', error);
      setSchedeTecnicheModal(prev => ({ ...prev, loading: false }));
    }
  };

  const stats = {
    total: suppliers.length,
    withInvoices: suppliers.filter(s => (s.fatture_count || 0) > 0).length,
    incomplete: suppliers.filter(s => !s.partita_iva || !s.email).length,
    cash: suppliers.filter(s => s.metodo_pagamento === 'contanti').length,
  };

  return (
    <PageLayout title="Gestione Fornitori" subtitle="Anagrafica e gestione fornitori">
    <div style={{ minHeight: '100vh', backgroundColor: '#f3f4f6', position: 'relative' }}>
      
      <div style={{ maxWidth: '1400px', margin: '0 auto' }}>
        
        {/* Header con Gradiente - Nuovo Design */}
        <div style={{ 
          display: 'flex', 
          justifyContent: 'space-between', 
          alignItems: 'center', 
          marginBottom: 32,
          padding: '32px 40px',
          background: 'linear-gradient(135deg, #2563eb 0%, #1e40af 100%)',
          borderRadius: 0,
          color: 'white',
          flexWrap: 'wrap',
          gap: 16,
          boxShadow: '0 4px 12px rgba(37, 99, 235, 0.15)'
        }}>
          <div>
            <h1 style={{ margin: 0, fontSize: 32, fontWeight: '700', display: 'flex', alignItems: 'center', gap: 16, marginBottom: 8 }}>
              <Building2 size={36} /> Gestione Fornitori
            </h1>
            <p style={{ margin: 0, fontSize: 16, opacity: 0.9, fontWeight: '400' }}>
              Anagrafica completa • Metodi di pagamento
            </p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 24 }}>
            <button 
              onClick={reloadData}
              disabled={loading}
              style={{ 
                padding: '14px 28px',
                background: 'white',
                color: '#2563eb',
                border: 'none',
                borderRadius: 10,
                cursor: loading ? 'wait' : 'pointer',
                fontWeight: '600',
                fontSize: 16,
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
                transition: 'all 0.2s'
              }}
              onMouseEnter={(e) => {
                if (!loading) {
                  e.target.style.transform = 'translateY(-2px)';
                  e.target.style.boxShadow = '0 4px 12px rgba(0,0,0,0.15)';
                }
              }}
              onMouseLeave={(e) => {
                e.target.style.transform = 'translateY(0)';
                e.target.style.boxShadow = '0 2px 8px rgba(0,0,0,0.1)';
              }}
            >
              🔄 {loading ? 'Caricamento...' : 'Aggiorna'}
            </button>
            <button 
              onClick={async () => {
                if (!window.confirm('Vuoi aggiornare tutti i fornitori con i dati della Camera di Commercio?')) return;
                try {
                  const res = await api.get('/api/openapi-imprese/fornitori-da-aggiornare?limit=50');
                  if (res.data.count === 0) {
                    alert('Tutti i fornitori sono già aggiornati!');
                    return;
                  }
                  const partiteIva = (res.data?.fornitori || []).map(f => f.partita_iva).filter(Boolean);
                  if (partiteIva.length === 0) {
                    alert('Nessun fornitore con P.IVA valida da aggiornare');
                    return;
                  }
                  const bulkRes = await api.post('/api/openapi-imprese/aggiorna-bulk', { partite_iva: partiteIva });
                  alert(`Aggiornati: ${bulkRes.data.aggiornati}\nCreati: ${bulkRes.data.creati}\nErrori: ${bulkRes.data.errori}`);
                  reloadData();
                } catch (err) {
                  alert('Errore: ' + (err.response?.data?.detail || err.message));
                }
              }}
              style={{ 
                padding: '14px 28px',
                background: 'white',
                color: '#2563eb',
                border: 'none',
                borderRadius: 10,
                cursor: 'pointer',
                fontWeight: '600',
                fontSize: 16,
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
                transition: 'all 0.2s'
              }}
              onMouseEnter={(e) => {
                e.target.style.transform = 'translateY(-2px)';
                e.target.style.boxShadow = '0 4px 12px rgba(0,0,0,0.15)';
              }}
              onMouseLeave={(e) => {
                e.target.style.transform = 'translateY(0)';
                e.target.style.boxShadow = '0 2px 8px rgba(0,0,0,0.1)';
              }}
            >
              🔄 Aggiorna da OpenAPI
            </button>
            <button 
              onClick={() => setShowModal(true)}
              style={{ 
                padding: '14px 28px',
                background: '#22c55e',
                color: 'white',
                border: 'none',
                borderRadius: 10,
                cursor: 'pointer',
                fontWeight: '600',
                fontSize: 16,
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
                transition: 'all 0.2s'
              }}
              onMouseEnter={(e) => {
                e.target.style.background = '#16a34a';
                e.target.style.transform = 'translateY(-2px)';
                e.target.style.boxShadow = '0 4px 12px rgba(0,0,0,0.15)';
              }}
              onMouseLeave={(e) => {
                e.target.style.background = '#22c55e';
                e.target.style.transform = 'translateY(0)';
                e.target.style.boxShadow = '0 2px 8px rgba(0,0,0,0.1)';
              }}
            >
              <Plus size={20} /> Nuovo Fornitore
            </button>
          </div>
        </div>

        {/* Stats */}
        <div style={{ 
          display: 'grid', 
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', 
          gap: '16px', 
          marginBottom: '24px' 
        }}>
          <StatCard icon={Users} label="Totale Fornitori" value={stats.total} color="#1535a8" bgColor="#eef2ff" />
          <StatCard icon={FileText} label="Con Fatture" value={stats.withInvoices} color="#10b981" bgColor="#d1fae5" />
          <StatCard icon={AlertCircle} label="Dati Incompleti" value={stats.incomplete} color="#f59e0b" bgColor="#fef3c7" />
          <StatCard icon={CreditCard} label="Pagamento Contanti" value={stats.cash} color="#8b5cf6" bgColor="#ede9fe" />
        </div>

        {/* Tabs */}
        <div style={{ 
          display: 'flex', 
          gap: '4px', 
          marginBottom: '24px',
          background: '#f1f5f9',
          padding: '4px',
          borderRadius: '10px',
          width: 'fit-content'
        }} data-testid="fornitori-tabs">
          <button
            style={{
              padding: '10px 20px',
              borderRadius: '8px',
              border: 'none',
              fontWeight: '500',
              fontSize: '14px',
              background: 'white',
              color: '#1e293b',
              boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
              display: 'flex',
              alignItems: 'center',
              gap: '8px'
            }}
            data-testid="tab-anagrafica"
          >
            <Building2 size={16} /> Anagrafica Fornitori
          </button>
          <Link
            to="/learning-machine"
            style={{
              padding: '10px 20px',
              borderRadius: '8px',
              textDecoration: 'none',
              fontWeight: '500',
              fontSize: '14px',
              transition: 'all 0.2s',
              background: 'linear-gradient(135deg, #1535a8 0%, #2050e8 100%)',
              color: 'white',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              boxShadow: '0 2px 4px rgba(30,58,95,0.3)'
            }}
            data-testid="link-learning-machine"
          >
            <Brain size={16} /> Learning Machine <ExternalLink size={14} />
          </Link>
        </div>

        {/* Search & Filters */}
        <div style={{ 
          backgroundColor: 'white', 
          borderRadius: '12px', 
          padding: '16px', 
          marginBottom: '24px',
          boxShadow: '0 1px 3px rgba(0,0,0,0.1)'
        }}>
          <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', alignItems: 'center' }}>
            {/* Search */}
            <div style={{ flex: 1, minWidth: '250px', position: 'relative' }}>
              <Search size={18} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: '#9ca3af' }} />
              <input
                type="text"
                placeholder="Cerca fornitore..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                style={{
                  width: '100%',
                  padding: '10px 12px 10px 40px',
                  border: '1px solid #e5e7eb',
                  borderRadius: '8px',
                  fontSize: '14px',
                  boxSizing: 'border-box'
                }}
              />
            </div>

            {/* Filter Metodo - usa METODI_PAGAMENTO */}
            <select
              value={filterMetodo}
              onChange={(e) => setFilterMetodo(e.target.value)}
              style={{
                padding: '10px 14px',
                border: '1px solid #e5e7eb',
                borderRadius: '8px',
                fontSize: '14px',
                backgroundColor: 'white',
                minWidth: '140px'
              }}
            >
              <option value="tutti">Tutti i metodi</option>
              {Object.entries(METODI_PAGAMENTO).filter(([k]) => k !== 'banca').map(([key, val]) => (
                <option key={key} value={key}>{val.label}</option>
              ))}
            </select>

            {/* Filter Incomplete */}
            <label style={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: '8px', 
              padding: '10px 14px',
              border: '1px solid #e5e7eb',
              borderRadius: '8px',
              cursor: 'pointer',
              fontSize: '14px',
              backgroundColor: filterIncomplete ? '#fef3c7' : 'white'
            }}>
              <input
                type="checkbox"
                checked={filterIncomplete}
                onChange={(e) => setFilterIncomplete(e.target.checked)}
                style={{ width: '16px', height: '16px' }}
              />
              Solo incompleti
            </label>
          </div>
        </div>

        {/* Results Count */}
        <div style={{ marginBottom: '16px', fontSize: '14px', color: '#6b7280' }}>
          {filteredSuppliers.length === suppliers.length 
            ? `${suppliers.length} fornitori`
            : `${filteredSuppliers.length} di ${suppliers.length} fornitori`
          }
        </div>

        {/* Cards Grid */}
        {loading ? (
          <div style={{ textAlign: 'center', padding: '60px' }}>
            <div style={{
              width: '40px',
              height: '40px',
              border: '4px solid #e5e7eb',
              borderTopColor: '#1535a8',
              borderRadius: '50%',
              animation: 'spin 1s linear infinite',
              margin: '0 auto'
            }} />
            <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
          </div>
        ) : filteredSuppliers.length === 0 ? (
          <div style={{ 
            backgroundColor: 'white', 
            borderRadius: '12px', 
            padding: '60px', 
            textAlign: 'center',
            boxShadow: '0 1px 3px rgba(0,0,0,0.1)'
          }}>
            <Building2 size={48} color="#d1d5db" style={{ marginBottom: '16px' }} />
            <h3 style={{ margin: '0 0 8px', color: '#374151' }}>Nessun fornitore trovato</h3>
            <p style={{ color: '#6b7280', margin: 0 }}>
              {suppliers.length === 0 ? 'Aggiungi il primo fornitore' : 'Modifica i filtri di ricerca'}
            </p>
          </div>
        ) : (
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
            gap: '16px'
          }}>
            {filteredSuppliers.map(supplier => (
              <SupplierCard
                key={supplier.id}
                supplier={supplier}
                onEdit={(s) => { setCurrentSupplier(s); setModalOpen(true); }}
                onDelete={handleDelete}
                onViewInvoices={handleViewInvoices}
                onChangeMetodo={handleChangeMetodo}
                onSearchPiva={handleSearchPiva}
                onShowFatturato={handleShowFatturato}
                onShowSchedeTecniche={handleViewSchedeTecniche}
                selectedYear={selectedYear}
              />
            ))}
          </div>
        )}
      </div>

      <SupplierModal
        isOpen={modalOpen}
        onClose={() => { setModalOpen(false); setCurrentSupplier(null); }}
        supplier={currentSupplier}
        onSave={handleSave}
        saving={saving}
      />

      {/* Modale Fatturato */}
      {fatturatoModal.open && (
        <Portal>
          <div style={{
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
            padding: '20px'
          }}>
          <div style={{
            backgroundColor: 'white',
            borderRadius: '16px',
            width: '100%',
            maxWidth: '500px',
            overflow: 'hidden',
            boxShadow: '0 20px 50px rgba(0,0,0,0.3)'
          }}>
            {/* Header */}
            <div style={{
              background: 'linear-gradient(135deg, #0284c7 0%, #0369a1 100%)',
              padding: '20px 24px',
              color: 'white'
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <h2 style={{ margin: 0, fontSize: '18px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <TrendingUp size={20} /> Fatturato {fatturatoModal.data?.anno || selectedYear}
                  </h2>
                  <p style={{ margin: '4px 0 0', opacity: 0.9, fontSize: '14px' }}>
                    {fatturatoModal.data?.fornitore || ''}
                  </p>
                </div>
                <button 
                  onClick={() => setFatturatoModal({ open: false, data: null, loading: false })} 
                  style={{
                    background: 'rgba(255,255,255,0.2)',
                    border: 'none',
                    borderRadius: '8px',
                    padding: '8px',
                    cursor: 'pointer',
                    color: 'white'
                  }}
                  data-testid="close-fatturato-modal"
                >
                  <X size={20} />
                </button>
              </div>
            </div>

            {/* Content */}
            <div style={{ padding: '24px' }}>
              {fatturatoModal.loading ? (
                <div style={{ textAlign: 'center', padding: '40px' }}>
                  <div style={{
                    width: '40px',
                    height: '40px',
                    border: '4px solid #e5e7eb',
                    borderTopColor: '#0284c7',
                    borderRadius: '50%',
                    animation: 'spin 1s linear infinite',
                    margin: '0 auto'
                  }} />
                  <p style={{ marginTop: '16px', color: '#6b7280' }}>Caricamento fatturato...</p>
                </div>
              ) : fatturatoModal.data ? (
                <div>
                  {/* Totale Principale */}
                  <div style={{
                    background: 'linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%)',
                    borderRadius: '12px',
                    padding: '20px',
                    marginBottom: '20px',
                    textAlign: 'center'
                  }}>
                    <div style={{ fontSize: '14px', color: '#0369a1', marginBottom: '4px' }}>TOTALE FATTURATO {fatturatoModal.data.anno}</div>
                    <div style={{ fontSize: '36px', fontWeight: 700, color: '#0c4a6e' }}>
                      {formatEuro(fatturatoModal.data.totale_fatturato || 0)}
                    </div>
                    <div style={{ fontSize: '14px', color: '#0369a1', marginTop: '8px' }}>
                      {fatturatoModal.data.numero_fatture} fatture
                    </div>
                  </div>

                  {/* Stats Grid */}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '20px' }}>
                    <div style={{ background: '#f0fdf4', borderRadius: '8px', padding: '12px', textAlign: 'center' }}>
                      <div style={{ fontSize: '12px', color: '#16a34a' }}>Pagate</div>
                      <div style={{ fontSize: '20px', fontWeight: 700, color: '#15803d' }}>{fatturatoModal.data.fatture_pagate || 0}</div>
                      <div style={{ fontSize: '11px', color: '#6b7280' }}>{formatEuro((fatturatoModal.data.importo_pagato || 0))}</div>
                    </div>
                    <div style={{ background: '#fef2f2', borderRadius: '8px', padding: '12px', textAlign: 'center' }}>
                      <div style={{ fontSize: '12px', color: '#dc2626' }}>Da Pagare</div>
                      <div style={{ fontSize: '20px', fontWeight: 700, color: '#b91c1c' }}>{fatturatoModal.data.fatture_non_pagate || 0}</div>
                      <div style={{ fontSize: '11px', color: '#6b7280' }}>{formatEuro((fatturatoModal.data.importo_non_pagato || 0))}</div>
                    </div>
                  </div>

                  {/* Dettaglio Mensile (se disponibile) */}
                  {fatturatoModal.data.dettaglio_mensile && fatturatoModal.data.dettaglio_mensile.length > 0 && (
                    <div>
                      <div style={{ fontSize: '13px', fontWeight: 600, color: '#374151', marginBottom: '8px' }}>Dettaglio Mensile</div>
                      <div style={{ maxHeight: '200px', overflowY: 'auto' }}>
                        {fatturatoModal.data.dettaglio_mensile.map((m, idx) => (
                          <div key={idx} style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            padding: '8px 12px',
                            borderBottom: '1px solid #f3f4f6',
                            fontSize: '13px'
                          }}>
                            <span style={{ color: '#6b7280' }}>{m.mese_nome}</span>
                            <span style={{ fontWeight: 600, color: '#1f2937' }}>
                              {formatEuro(m.totale || 0)} 
                              <span style={{ fontWeight: 400, color: '#9ca3af', marginLeft: '8px' }}>({m.numero_fatture} fatt.)</span>
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {fatturatoModal.data.numero_fatture === 0 && (
                    <div style={{ textAlign: 'center', color: '#6b7280', padding: '20px' }}>
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
        <div style={{
          position: 'fixed',
          top: 0, left: 0, right: 0, bottom: 0,
          backgroundColor: 'rgba(0,0,0,0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 10000
        }}>
          <div style={{
            backgroundColor: 'white',
            borderRadius: '16px',
            width: '95%',
            maxWidth: '1200px',
            maxHeight: '90vh',
            overflow: 'hidden',
            boxShadow: '0 20px 40px rgba(0,0,0,0.2)',
            display: 'flex',
            flexDirection: 'column'
          }}>
            {/* Header */}
            <div style={{
              padding: '20px 24px',
              borderBottom: '1px solid #e5e7eb',
              background: 'linear-gradient(135deg, #1535a8 0%, #2050e8 100%)',
              color: 'white'
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <div style={{ fontSize: '20px', fontWeight: 700 }}>
                    📋 Estratto Fatture
                  </div>
                  <div style={{ fontSize: '14px', opacity: 0.9, marginTop: 4 }}>
                    {estrattoModal.fornitore?.ragione_sociale || estrattoModal.fornitore?.denominazione}
                    {' • '}{estrattoModal.fornitore?.partita_iva}
                  </div>
                </div>
                <button
                  onClick={() => setEstrattoModal(prev => ({ ...prev, open: false }))}
                  style={{
                    width: '36px', height: '36px',
                    borderRadius: '50%',
                    border: 'none',
                    background: 'rgba(255,255,255,0.2)',
                    color: 'white',
                    cursor: 'pointer',
                    fontSize: '18px'
                  }}
                >×</button>
              </div>
            </div>

            {/* Filtri */}
            <div style={{ 
              padding: '16px 24px', 
              borderBottom: '1px solid #e5e7eb',
              background: '#f8fafc',
              display: 'flex',
              flexWrap: 'wrap',
              gap: 12,
              alignItems: 'flex-end'
            }}>
              <div>
                <label style={{ fontSize: 11, color: '#6b7280', display: 'block', marginBottom: 4 }}>Anno</label>
                <select
                  value={estrattoModal.filtri.anno || ''}
                  onChange={(e) => setEstrattoModal(prev => ({ 
                    ...prev, 
                    filtri: { ...prev.filtri, anno: e.target.value ? parseInt(e.target.value) : null }
                  }))}
                  style={{ padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 13 }}
                >
                  <option value="">Tutti</option>
                  {[...Array(5)].map((_, i) => { const y = new Date().getFullYear() - i; return <option key={y} value={y}>{y}</option>; })}
                </select>
              </div>
              <div>
                <label style={{ fontSize: 11, color: '#6b7280', display: 'block', marginBottom: 4 }}>Data Da</label>
                <input
                  type="date"
                  value={estrattoModal.filtri.data_da}
                  onChange={(e) => setEstrattoModal(prev => ({ 
                    ...prev, 
                    filtri: { ...prev.filtri, data_da: e.target.value }
                  }))}
                  style={{ padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 13 }}
                />
              </div>
              <div>
                <label style={{ fontSize: 11, color: '#6b7280', display: 'block', marginBottom: 4 }}>Data A</label>
                <input
                  type="date"
                  value={estrattoModal.filtri.data_a}
                  onChange={(e) => setEstrattoModal(prev => ({ 
                    ...prev, 
                    filtri: { ...prev.filtri, data_a: e.target.value }
                  }))}
                  style={{ padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 13 }}
                />
              </div>
              <div>
                <label style={{ fontSize: 11, color: '#6b7280', display: 'block', marginBottom: 4 }}>Importo Min</label>
                <input
                  type="number"
                  placeholder="€"
                  value={estrattoModal.filtri.importo_min}
                  onChange={(e) => setEstrattoModal(prev => ({ 
                    ...prev, 
                    filtri: { ...prev.filtri, importo_min: e.target.value }
                  }))}
                  style={{ padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 13, width: 100 }}
                />
              </div>
              <div>
                <label style={{ fontSize: 11, color: '#6b7280', display: 'block', marginBottom: 4 }}>Importo Max</label>
                <input
                  type="number"
                  placeholder="€"
                  value={estrattoModal.filtri.importo_max}
                  onChange={(e) => setEstrattoModal(prev => ({ 
                    ...prev, 
                    filtri: { ...prev.filtri, importo_max: e.target.value }
                  }))}
                  style={{ padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 13, width: 100 }}
                />
              </div>
              <div>
                <label style={{ fontSize: 11, color: '#6b7280', display: 'block', marginBottom: 4 }}>Tipo</label>
                <select
                  value={estrattoModal.filtri.tipo}
                  onChange={(e) => setEstrattoModal(prev => ({ 
                    ...prev, 
                    filtri: { ...prev.filtri, tipo: e.target.value }
                  }))}
                  style={{ padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 13 }}
                >
                  <option value="tutti">Tutti</option>
                  <option value="fattura">Solo Fatture</option>
                  <option value="nota_credito">Solo Note Credito</option>
                </select>
              </div>
              <button
                onClick={reloadEstratto}
                disabled={estrattoModal.loading}
                style={{
                  padding: '8px 16px',
                  background: '#1535a8',
                  color: 'white',
                  border: 'none',
                  borderRadius: 6,
                  cursor: estrattoModal.loading ? 'wait' : 'pointer',
                  fontSize: 13,
                  fontWeight: 600
                }}
              >
                🔍 Filtra
              </button>
            </div>

            {/* Content */}
            <div style={{ flex: 1, overflow: 'auto', padding: '16px 24px' }}>
              {estrattoModal.loading ? (
                <div style={{ textAlign: 'center', padding: 40 }}>
                  <div className="spinner" style={{ width: 40, height: 40, margin: '0 auto' }}></div>
                  <p style={{ marginTop: 16, color: '#6b7280' }}>Caricamento fatture...</p>
                </div>
              ) : estrattoModal.data ? (
                <>
                  {/* Totali */}
                  <div style={{ 
                    display: 'grid', 
                    gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', 
                    gap: 12, 
                    marginBottom: 20 
                  }}>
                    <div style={{ background: '#f0f9ff', padding: 16, borderRadius: 8, textAlign: 'center' }}>
                      <div style={{ fontSize: 11, color: '#0369a1' }}>Documenti</div>
                      <div style={{ fontSize: 24, fontWeight: 700, color: '#0c4a6e' }}>{estrattoModal.data.totali?.numero_documenti || 0}</div>
                    </div>
                    <div style={{ background: '#f0fdf4', padding: 16, borderRadius: 8, textAlign: 'center' }}>
                      <div style={{ fontSize: 11, color: '#16a34a' }}>Totale</div>
                      <div style={{ fontSize: 20, fontWeight: 700, color: '#15803d' }}>{formatEuro((estrattoModal.data.totali?.importo_totale || 0))}</div>
                    </div>
                    <div style={{ background: '#fef2f2', padding: 16, borderRadius: 8, textAlign: 'center' }}>
                      <div style={{ fontSize: 11, color: '#dc2626' }}>Note Credito</div>
                      <div style={{ fontSize: 20, fontWeight: 700, color: '#b91c1c' }}>- {formatEuro((estrattoModal.data.totali?.note_credito || 0))}</div>
                    </div>
                    <div style={{ background: '#fef3c7', padding: 16, borderRadius: 8, textAlign: 'center' }}>
                      <div style={{ fontSize: 11, color: '#92400e' }}>Netto</div>
                      <div style={{ fontSize: 20, fontWeight: 700, color: '#78350f' }}>{formatEuro((estrattoModal.data.totali?.netto || 0))}</div>
                    </div>
                  </div>

                  {/* Tabella Fatture */}
                  <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                      <thead>
                        <tr style={{ background: '#f3f4f6' }}>
                          <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: 600 }}>Data</th>
                          <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: 600 }}>Numero</th>
                          <th style={{ padding: '10px 12px', textAlign: 'left', fontWeight: 600 }}>Tipo</th>
                          <th style={{ padding: '10px 12px', textAlign: 'right', fontWeight: 600 }}>Imponibile</th>
                          <th style={{ padding: '10px 12px', textAlign: 'right', fontWeight: 600 }}>IVA</th>
                          <th style={{ padding: '10px 12px', textAlign: 'right', fontWeight: 600 }}>Totale</th>
                          <th style={{ padding: '10px 12px', textAlign: 'center', fontWeight: 600 }}>Metodo Pag.</th>
                          <th style={{ padding: '10px 12px', textAlign: 'center', fontWeight: 600 }}>Stato</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(estrattoModal.data.estratto || []).map((f, idx) => (
                          <tr key={f.id || idx} style={{ borderBottom: '1px solid #e5e7eb', background: f.is_nota_credito ? '#fef2f2' : (idx % 2 === 0 ? 'white' : '#f9fafb') }}>
                            <td style={{ padding: '10px 12px' }}>{f.data}</td>
                            <td style={{ padding: '10px 12px', fontWeight: 500 }}>{f.numero}</td>
                            <td style={{ padding: '10px 12px' }}>
                              {f.is_nota_credito ? (
                                <span style={{ background: '#fecaca', color: '#991b1b', padding: '2px 8px', borderRadius: 4, fontSize: 11 }}>NC</span>
                              ) : (
                                <span style={{ background: '#dbeafe', color: '#1e40af', padding: '2px 8px', borderRadius: 4, fontSize: 11 }}>{f.tipo_documento}</span>
                              )}
                            </td>
                            <td style={{ padding: '10px 12px', textAlign: 'right' }}>{formatEuro((f.imponibile || 0))}</td>
                            <td style={{ padding: '10px 12px', textAlign: 'right' }}>{formatEuro((f.iva || 0))}</td>
                            <td style={{ padding: '10px 12px', textAlign: 'right', fontWeight: 600 }}>
                              {f.is_nota_credito ? '-' : ''} {formatEuro((f.importo_totale || 0))}
                            </td>
                            <td style={{ padding: '10px 12px', textAlign: 'center' }}>
                              <span style={{ 
                                padding: '2px 8px', 
                                borderRadius: 4, 
                                fontSize: 11,
                                background: f.metodo_pagamento === 'cassa' || f.metodo_pagamento === 'contanti' ? '#dcfce7' : '#dbeafe',
                                color: f.metodo_pagamento === 'cassa' || f.metodo_pagamento === 'contanti' ? '#166534' : '#1e40af'
                              }}>
                                {f.metodo_pagamento || '-'}
                              </span>
                            </td>
                            <td style={{ padding: '10px 12px', textAlign: 'center' }}>
                              {f.riconciliato ? (
                                <span style={{ background: '#10b981', color: 'white', padding: '2px 8px', borderRadius: 12, fontSize: 10, fontWeight: 600 }}>✓ RICONCILIATA</span>
                              ) : f.pagato ? (
                                <span style={{ background: '#22c55e', color: 'white', padding: '2px 8px', borderRadius: 12, fontSize: 10 }}>Pagata</span>
                              ) : (
                                <span style={{ background: '#f59e0b', color: 'white', padding: '2px 8px', borderRadius: 12, fontSize: 10 }}>Da pagare</span>
                              )}
                            </td>
                          </tr>
                        ))}
                        {(!estrattoModal.data.estratto || estrattoModal.data.estratto.length === 0) && (
                          <tr>
                            <td colSpan={8} style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>
                              Nessuna fattura trovata con i filtri selezionati
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </>
              ) : null}
            </div>

            {/* Footer */}
            <div style={{ 
              padding: '16px 24px', 
              borderTop: '1px solid #e5e7eb',
              background: '#f8fafc',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center'
            }}>
              <div style={{ fontSize: 12, color: '#6b7280' }}>
                Metodo pagamento predefinito fornitore: <strong>{estrattoModal.data?.fornitore?.metodo_pagamento_predefinito || '-'}</strong>
              </div>
              <div style={{ display: 'flex', gap: 12 }}>
                <button
                  onClick={() => window.print()}
                  style={{
                    padding: '8px 16px',
                    background: '#f3f4f6',
                    color: '#374151',
                    border: '1px solid #d1d5db',
                    borderRadius: 6,
                    cursor: 'pointer',
                    fontSize: 13
                  }}
                >
                  🖨️ Stampa
                </button>
                <button
                  onClick={() => setEstrattoModal(prev => ({ ...prev, open: false }))}
                  style={{
                    padding: '8px 16px',
                    background: '#1535a8',
                    color: 'white',
                    border: 'none',
                    borderRadius: 6,
                    cursor: 'pointer',
                    fontSize: 13,
                    fontWeight: 600
                  }}
                >
                  Chiudi
                </button>
              </div>
            </div>
          </div>
        </div>
        </Portal>
      )}

      {/* MODALE SCHEDE TECNICHE */}
      {schedeTecnicheModal.open && (
        <Portal>
          <div style={{
            position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
            background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center',
            zIndex: 9999
          }}>
            <div style={{
              background: 'white', borderRadius: 16, width: '90%', maxWidth: 800,
              maxHeight: '85vh', overflow: 'hidden', display: 'flex', flexDirection: 'column',
              boxShadow: '0 25px 50px rgba(0,0,0,0.25)'
            }}>
              {/* Header */}
              <div style={{
                padding: '20px 24px', borderBottom: '1px solid #e5e7eb',
                background: 'linear-gradient(135deg, #1535a8 0%, #2050e8 100%)',
                color: 'white'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <h2 style={{ margin: 0, fontSize: 18, fontWeight: 'bold' }}>
                      📋 Schede Tecniche Prodotti
                    </h2>
                    <p style={{ margin: '4px 0 0 0', fontSize: 13, opacity: 0.9 }}>
                      {schedeTecnicheModal.fornitore?.ragione_sociale || schedeTecnicheModal.fornitore?.name}
                    </p>
                  </div>
                  <button
                    onClick={() => setSchedeTecnicheModal({ open: false, fornitore: null, schede: [], loading: false })}
                    style={{ background: 'rgba(255,255,255,0.2)', border: 'none', borderRadius: '50%', width: 32, height: 32, cursor: 'pointer', color: 'white', fontSize: 18 }}
                  >×</button>
                </div>
              </div>

              {/* Content */}
              <div style={{ flex: 1, overflow: 'auto', padding: 24 }}>
                {schedeTecnicheModal.loading ? (
                  <div style={{ textAlign: 'center', padding: 60, color: '#6b7280' }}>
                    ⏳ Caricamento schede tecniche...
                  </div>
                ) : schedeTecnicheModal.schede.length === 0 ? (
                  <div style={{ textAlign: 'center', padding: 60 }}>
                    <div style={{ fontSize: 48, marginBottom: 16 }}>📄</div>
                    <h3 style={{ color: '#374151', margin: '0 0 8px 0' }}>Nessuna scheda tecnica</h3>
                    <p style={{ color: '#6b7280', margin: 0 }}>
                      Questo fornitore non ha ancora schede tecniche associate.
                    </p>
                    <p style={{ color: '#9ca3af', fontSize: 13, marginTop: 12 }}>
                      Le schede tecniche vengono importate automaticamente dalle email del fornitore.
                    </p>
                  </div>
                ) : (
                  <div style={{ display: 'grid', gap: 12 }}>
                    {schedeTecnicheModal.schede.map((scheda, idx) => (
                      <div key={scheda.id || idx} style={{
                        background: '#f9fafb', borderRadius: 12, padding: 16,
                        border: '1px solid #e5e7eb', display: 'flex', alignItems: 'center', gap: 16
                      }}>
                        <div style={{
                          width: 48, height: 48, borderRadius: 8, background: '#e0e7ff',
                          display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 24
                        }}>
                          📋
                        </div>
                        <div style={{ flex: 1 }}>
                          <h4 style={{ margin: '0 0 4px 0', fontSize: 14, fontWeight: 600, color: '#1535a8' }}>
                            {scheda.nome_prodotto || scheda.nome || 'Scheda Tecnica'}
                          </h4>
                          <p style={{ margin: 0, fontSize: 12, color: '#6b7280' }}>
                            {scheda.codice_articolo && `Cod. ${scheda.codice_articolo} • `}
                            Caricata: {scheda.created_at ? new Date(scheda.created_at).toLocaleDateString('it-IT') : '-'}
                          </p>
                        </div>
                        {scheda.file_url && (
                          <a
                            href={scheda.file_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{
                              padding: '8px 16px', background: '#3b82f6', color: 'white',
                              borderRadius: 6, textDecoration: 'none', fontSize: 13, fontWeight: 500
                            }}
                          >
                            📥 Scarica
                          </a>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Footer */}
              <div style={{
                padding: '16px 24px', borderTop: '1px solid #e5e7eb', background: '#f8fafc',
                display: 'flex', justifyContent: 'flex-end'
              }}>
                <button
                  onClick={() => setSchedeTecnicheModal({ open: false, fornitore: null, schede: [], loading: false })}
                  style={{
                    padding: '10px 20px', background: '#1535a8', color: 'white',
                    border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 600
                  }}
                >
                  Chiudi
                </button>
              </div>
            </div>
          </div>
        </Portal>
      )}
    </div>
    </PageLayout>
  );
}
