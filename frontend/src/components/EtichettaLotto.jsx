import React, { useState, useEffect, useCallback } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import api from '../api';

/**
 * EtichettaLotto - Componente per stampa etichette 80mm
 * Ottimizzato per stampanti termiche
 * 
 * @media print rules per layout 80mm
 */

// Stili per la stampa 80mm
const printStyles = `
@media print {
  @page {
    size: 80mm auto;
    margin: 0;
  }
  body * {
    visibility: hidden;
  }
  .etichetta-print-area, .etichetta-print-area * {
    visibility: visible;
  }
  .etichetta-print-area {
    position: absolute;
    left: 0;
    top: 0;
    width: 80mm !important;
  }
  .no-print {
    display: none !important;
  }
}
`;

const styles = {
  // Container principale (non stampato)
  container: {
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
  },
  
  // Header del modal/componente
  header: {
    padding: '20px',
    borderBottom: '1px solid #e2e8f0',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center'
  },
  headerTitle: {
    margin: 0,
    fontSize: '18px',
    fontWeight: '600',
    color: '#1e293b',
    display: 'flex',
    alignItems: 'center',
    gap: '8px'
  },
  
  // Preview container
  previewContainer: {
    padding: '20px',
    background: '#f8fafc',
    display: 'flex',
    justifyContent: 'center',
    alignItems: 'center'
  },
  
  // Etichetta 80mm
  etichetta: {
    width: '80mm',
    minHeight: '50mm',
    background: 'white',
    border: '1px solid #e2e8f0',
    borderRadius: '4px',
    padding: '3mm',
    boxSizing: 'border-box',
    fontFamily: 'Arial, sans-serif',
    fontSize: '10px',
    lineHeight: '1.3'
  },
  
  // Header etichetta
  etichettaHeader: {
    borderBottom: '1px solid #000',
    paddingBottom: '2mm',
    marginBottom: '2mm'
  },
  nomeProdotto: {
    fontSize: '14px',
    fontWeight: 'bold',
    margin: '0 0 1mm 0',
    textTransform: 'uppercase',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap'
  },
  fornitore: {
    fontSize: '9px',
    color: '#333',
    margin: 0
  },
  
  // Body etichetta con 2 colonne
  etichettaBody: {
    display: 'flex',
    gap: '2mm'
  },
  infoColumn: {
    flex: 1
  },
  qrColumn: {
    width: '20mm',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center'
  },
  
  // Righe info
  infoRow: {
    marginBottom: '1.5mm'
  },
  label: {
    fontSize: '8px',
    color: '#666',
    textTransform: 'uppercase',
    margin: 0
  },
  value: {
    fontSize: '11px',
    fontWeight: 'bold',
    margin: 0,
    color: '#000'
  },
  valueSmall: {
    fontSize: '9px',
    margin: 0,
    color: '#333'
  },
  
  // Scadenza evidenziata
  scadenzaBox: {
    background: '#000',
    color: '#fff',
    padding: '1.5mm 2mm',
    marginTop: '2mm',
    textAlign: 'center'
  },
  scadenzaLabel: {
    fontSize: '8px',
    margin: 0,
    opacity: 0.8
  },
  scadenzaValue: {
    fontSize: '14px',
    fontWeight: 'bold',
    margin: 0
  },
  
  // Allergeni evidenziati
  allergeniBox: {
    marginTop: '2mm',
    padding: '2mm',
    background: '#fef3c7',
    border: '1px solid #f59e0b',
    borderRadius: '2mm'
  },
  allergeniLabel: {
    fontSize: '8px',
    fontWeight: 'bold',
    color: '#92400e',
    margin: '0 0 1mm 0',
    textTransform: 'uppercase'
  },
  allergeniList: {
    fontSize: '9px',
    fontWeight: 'bold',
    color: '#dc2626',
    margin: 0,
    lineHeight: 1.4
  },
  
  // Footer etichetta
  etichettaFooter: {
    marginTop: '2mm',
    paddingTop: '1mm',
    borderTop: '1px dashed #ccc',
    fontSize: '7px',
    color: '#666',
    display: 'flex',
    justifyContent: 'space-between'
  },
  
  // Bottoni azioni
  actionsBar: {
    padding: '16px 20px',
    borderTop: '1px solid #e2e8f0',
    display: 'flex',
    gap: '12px',
    justifyContent: 'flex-end',
    background: '#f8fafc'
  },
  button: (variant = 'default') => ({
    padding: '10px 20px',
    borderRadius: '8px',
    border: 'none',
    cursor: 'pointer',
    fontWeight: '500',
    fontSize: '14px',
    display: 'inline-flex',
    alignItems: 'center',
    gap: '8px',
    transition: 'all 0.2s',
    ...(variant === 'primary' ? {
      background: '#1535a8',
      color: 'white'
    } : variant === 'success' ? {
      background: '#10b981',
      color: 'white'
    } : {
      background: 'white',
      color: '#475569',
      border: '1px solid #e2e8f0'
    })
  }),
  
  // Lista lotti per stampa multipla
  lottiList: {
    padding: '20px',
    maxHeight: '300px',
    overflowY: 'auto'
  },
  lottoItem: (selected) => ({
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    padding: '12px',
    borderRadius: '8px',
    marginBottom: '8px',
    cursor: 'pointer',
    border: selected ? '2px solid #1535a8' : '1px solid #e2e8f0',
    background: selected ? '#eff6ff' : 'white'
  }),
  checkbox: {
    width: '18px',
    height: '18px',
    cursor: 'pointer'
  },
  lottoInfo: {
    flex: 1
  },
  lottoNome: {
    fontSize: '14px',
    fontWeight: '500',
    margin: '0 0 4px 0'
  },
  lottoDettagli: {
    fontSize: '12px',
    color: '#64748b',
    margin: 0
  },
  
  // Loading
  loading: {
    textAlign: 'center',
    padding: '40px',
    color: '#64748b'
  },
  
  // Messaggio
  message: {
    padding: '16px 20px',
    background: '#f0fdf4',
    borderBottom: '1px solid #bbf7d0',
    color: '#166534',
    fontSize: '14px'
  }
};

// Componente Etichetta Singola (per preview e stampa)
export function Etichetta({ dati, baseUrl = '' }) {
  const formatDate = (dateStr) => {
    if (!dateStr) return 'N/D';
    try {
      const parts = dateStr.split('-');
      if (parts.length === 3) {
        return `${parts[2]}/${parts[1]}/${parts[0]}`;
      }
    } catch (e) {
      // Date parsing error, return original
    }
    return dateStr;
  };

  // Formatta allergeni per visualizzazione
  const allergeniText = dati.allergeni?.length > 0 
    ? dati.allergeni.map(a => a.toUpperCase()).join(', ')
    : null;

  return (
    <div style={styles.etichetta} className="etichetta-print-area">
      {/* Header */}
      <div style={styles.etichettaHeader}>
        <p style={styles.nomeProdotto}>{dati.nome_prodotto || 'PRODOTTO'}</p>
        <p style={styles.fornitore}>{dati.fornitore || ''}</p>
      </div>
      
      {/* Body */}
      <div style={styles.etichettaBody}>
        {/* Colonna Info */}
        <div style={styles.infoColumn}>
          <div style={styles.infoRow}>
            <p style={styles.label}>Lotto Interno</p>
            <p style={styles.value}>{dati.lotto_interno || 'N/D'}</p>
          </div>
          
          <div style={styles.infoRow}>
            <p style={styles.label}>Lotto Fornitore</p>
            <p style={styles.value}>{dati.lotto_fornitore || 'N/D'}</p>
          </div>
          
          <div style={styles.infoRow}>
            <p style={styles.label}>N. Fattura</p>
            <p style={styles.valueSmall}>{dati.fattura_numero || 'N/D'}</p>
          </div>
          
          {/* Box Scadenza */}
          <div style={styles.scadenzaBox}>
            <p style={styles.scadenzaLabel}>SCADENZA</p>
            <p style={styles.scadenzaValue}>{formatDate(dati.data_scadenza)}</p>
          </div>
          
          {/* Box Allergeni - EVIDENZIATO */}
          {allergeniText && (
            <div style={styles.allergeniBox}>
              <p style={styles.allergeniLabel}>⚠️ CONTIENE:</p>
              <p style={styles.allergeniList}>{allergeniText}</p>
            </div>
          )}
        </div>
        
        {/* Colonna QR */}
        <div style={styles.qrColumn}>
          <QRCodeSVG 
            value={`${baseUrl}${dati.qr_data || ''}`}
            size={70}
            level="M"
          />
          <span style={{ fontSize: '6px', marginTop: '1mm', color: '#666' }}>
            Scansiona per dettagli
          </span>
        </div>
      </div>
      
      {/* Footer */}
      <div style={styles.etichettaFooter}>
        <span>Qtà: {dati.quantita || 'N/D'}</span>
        <span>Data: {formatDate(dati.fattura_data)}</span>
      </div>
    </div>
  );
}

// Componente principale per stampa etichette
export default function EtichettaLotto({ 
  lottoId = null, 
  fatturaId = null, 
  onClose = null,
  baseUrl = window.location.origin
}) {
  const [loading, setLoading] = useState(true);
  const [lotti, setLotti] = useState([]);
  const [selectedLotti, setSelectedLotti] = useState([]);
  const [currentPreview, setCurrentPreview] = useState(null);
  const [message, setMessage] = useState(null);

  const loadLotti = useCallback(async () => {
    setLoading(true);
    try {
      if (lottoId) {
        // Singolo lotto
        const res = await api.get(`/api/ciclo-passivo/etichetta/${lottoId}`);
        setLotti([res.data.lotto]);
        setCurrentPreview(res.data.etichetta);
        setSelectedLotti([lottoId]);
      } else if (fatturaId) {
        // Tutti i lotti di una fattura
        const res = await api.get(`/api/ciclo-passivo/lotti/fattura/${fatturaId}`);
        setLotti(res.data.lotti || []);
        if (res.data.lotti?.length > 0) {
          setSelectedLotti(res.data.lotti.map(l => l.id));
          // Preview primo lotto
          const previewRes = await api.get(`/api/ciclo-passivo/etichetta/${res.data.lotti[0].id}`);
          setCurrentPreview(previewRes.data.etichetta);
        }
      }
    } catch (e) {
      console.error('Errore caricamento lotti:', e);
    } finally {
      setLoading(false);
    }
  }, [lottoId, fatturaId]);

  useEffect(() => {
    loadLotti();
  }, [loadLotti]);

  // Inietta stili stampa
  useEffect(() => {
    const styleEl = document.createElement('style');
    styleEl.textContent = printStyles;
    document.head.appendChild(styleEl);
    return () => document.head.removeChild(styleEl);
  }, []);

  const toggleLotto = async (id) => {
    if (selectedLotti.includes(id)) {
      setSelectedLotti(selectedLotti.filter(l => l !== id));
    } else {
      setSelectedLotti([...selectedLotti, id]);
      // Aggiorna preview
      try {
        const res = await api.get(`/api/ciclo-passivo/etichetta/${id}`);
        setCurrentPreview(res.data.etichetta);
      } catch (e) {
        console.error('Errore preview:', e);
      }
    }
  };

  const selectAll = () => {
    setSelectedLotti(lotti.map(l => l.id));
  };

  const deselectAll = () => {
    setSelectedLotti([]);
  };

  const handlePrint = async () => {
    // Segna etichette come stampate
    for (const id of selectedLotti) {
      try {
        await api.post(`/api/ciclo-passivo/lotto/${id}/segna-etichetta-stampata`);
      } catch (e) {
        console.error(`Errore segnando lotto ${id} come stampato:`, e);
      }
    }
    
    setMessage(`${selectedLotti.length} etichette segnate come stampate`);
    setTimeout(() => setMessage(null), 3000);
    
    // Apri dialog stampa
    window.print();
  };

  if (loading) {
    return <div style={styles.loading}>⏳ Caricamento lotti...</div>;
  }

  return (
    <div style={styles.container} data-testid="etichetta-lotto-component">
      {/* Header */}
      <div style={styles.header} className="no-print">
        <h3 style={styles.headerTitle}>
          <span>🏷️</span> Stampa Etichette 80mm
        </h3>
        {onClose && (
          <button style={styles.button()} onClick={onClose}>✕ Chiudi</button>
        )}
      </div>

      {/* Messaggio */}
      {message && (
        <div style={styles.message} className="no-print">
          ✅ {message}
        </div>
      )}

      {/* Lista lotti selezionabili (se multipli) */}
      {lotti.length > 1 && (
        <div style={styles.lottiList} className="no-print">
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px' }}>
            <span style={{ fontWeight: '500' }}>Seleziona lotti da stampare:</span>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button style={{ ...styles.button(), padding: '6px 12px', fontSize: '12px' }} onClick={selectAll}>
                Tutti
              </button>
              <button style={{ ...styles.button(), padding: '6px 12px', fontSize: '12px' }} onClick={deselectAll}>
                Nessuno
              </button>
            </div>
          </div>
          
          {lotti.map((lotto) => (
            <div 
              key={lotto.id}
              style={styles.lottoItem(selectedLotti.includes(lotto.id))}
              onClick={() => toggleLotto(lotto.id)}
              data-testid={`lotto-item-${lotto.id}`}
            >
              <input 
                type="checkbox"
                checked={selectedLotti.includes(lotto.id)}
                onChange={() => {}}
                style={styles.checkbox}
              />
              <div style={styles.lottoInfo}>
                <p style={styles.lottoNome}>{lotto.prodotto}</p>
                <p style={styles.lottoDettagli}>
                  Lotto: {lotto.lotto_interno || 'N/D'} | Scad: {lotto.data_scadenza || 'N/D'}
                  {lotto.etichetta_stampata && ' | ✅ Già stampata'}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Preview Etichetta */}
      {currentPreview && (
        <div style={styles.previewContainer}>
          <Etichetta dati={currentPreview} baseUrl={baseUrl} />
        </div>
      )}

      {/* Azioni */}
      <div style={styles.actionsBar} className="no-print">
        <button 
          style={styles.button()}
          onClick={onClose}
        >
          Annulla
        </button>
        <button 
          style={styles.button('primary')}
          onClick={handlePrint}
          disabled={selectedLotti.length === 0}
          data-testid="btn-stampa"
        >
          🖨️ Stampa {selectedLotti.length} Etichett{selectedLotti.length === 1 ? 'a' : 'e'}
        </button>
      </div>
    </div>
  );
}

// Componente per stampare tutte le etichette di una fattura
export function StampaEtichetteFattura({ fatturaId, onClose }) {
  return <EtichettaLotto fatturaId={fatturaId} onClose={onClose} />;
}

// Componente per stampare singola etichetta
export function StampaEtichettaSingola({ lottoId, onClose }) {
  return <EtichettaLotto lottoId={lottoId} onClose={onClose} />;
}
