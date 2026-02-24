/**
 * Card informativa che descrive una pagina e le sue relazioni.
 * Mostra collegamenti, dipendenze e azioni a cascata.
 */
import React, { useState } from 'react';

// Configurazione delle relazioni tra pagine
export const PAGE_INFO = {
  'prima-nota-cassa': {
    icon: '💵',
    title: 'Prima Nota Cassa',
    description: 'Movimenti di cassa giornalieri',
    collegata: ['Corrispettivi', 'Scadenze', 'Report Commercialista'],
    alimentata: ['Import Corrispettivi', 'Registrazione Manuale'],
    cascade: 'Eliminazione → Aggiorna saldi cassa e report giornalieri',
    collection: 'prima_nota_cassa'
  },
  'prima-nota-banca': {
    icon: '🏦',
    title: 'Prima Nota Banca',
    description: 'Movimenti bancari registrati',
    collegata: ['Estratto Conto', 'Riconciliazione', 'Scadenze Fornitori'],
    alimentata: ['Import Estratto Conto', 'Conferme Riconciliazione', 'Registrazione Manuale'],
    cascade: 'Eliminazione → Richiede ri-riconciliazione movimenti',
    collection: 'prima_nota_banca'
  },
  'prima-nota-salari': {
    icon: '👥',
    title: 'Prima Nota Salari',
    description: 'Movimenti stipendi e contributi',
    collegata: ['Cedolini', 'F24', 'Dipendenti', 'TFR'],
    alimentata: ['Import Cedolini', 'Elaborazione F24'],
    cascade: 'Eliminazione → Disallinea calcolo TFR e contributi',
    collection: 'prima_nota_salari'
  },
  'riconciliazione': {
    icon: '🔄',
    title: 'Riconciliazione Smart',
    description: 'Abbinamento movimenti bancari con fatture/scadenze',
    collegata: ['Estratto Conto', 'Prima Nota Banca', 'Scadenzario Fornitori', 'Fatture Ricevute'],
    alimentata: ['Estratto Conto Movimenti'],
    cascade: 'Conferma → Crea movimento in Prima Nota Banca, aggiorna stato scadenza',
    collection: 'estratto_conto_movimenti'
  },
  'dipendenti': {
    icon: '👤',
    title: 'Gestione Dipendenti',
    description: 'Anagrafica e gestione personale',
    collegata: ['Cedolini', 'Bonifici', 'TFR', 'Contratti', 'Libro Unico'],
    alimentata: ['Import Anagrafica', 'Registrazione Manuale'],
    cascade: 'Eliminazione → Rimuove tutti i dati collegati (cedolini, TFR, contratti)',
    collection: 'employees'
  },
  'cedolini': {
    icon: '📄',
    title: 'Cedolini / Buste Paga',
    description: 'Archivio cedolini e calcolo retribuzioni',
    collegata: ['Dipendenti', 'Prima Nota Salari', 'F24', 'TFR'],
    alimentata: ['Import PDF Cedolini', 'Import Excel'],
    cascade: 'Eliminazione → Ricalcola TFR e totali dipendente',
    collection: 'cedolini'
  },
  'fornitori': {
    icon: '🏭',
    title: 'Anagrafica Fornitori',
    description: 'Elenco fornitori estratti dalle fatture',
    collegata: ['Fatture Ricevute', 'Scadenzario', 'Prima Nota Banca'],
    alimentata: ['Import Fatture XML (automatico)'],
    cascade: 'Dati di sola lettura - derivati dalle fatture',
    collection: 'invoices (aggregato)'
  },
  'fatture-ricevute': {
    icon: '📥',
    title: 'Fatture Ricevute',
    description: 'Archivio fatture passive da XML',
    collegata: ['Fornitori', 'Scadenzario', 'Riconciliazione', 'IVA'],
    alimentata: ['Import XML FatturaPA'],
    cascade: 'Eliminazione → Rimuove scadenza associata, aggiorna anagrafica fornitore',
    collection: 'invoices'
  },
  'corrispettivi': {
    icon: '🧾',
    title: 'Corrispettivi Giornalieri',
    description: 'Incassi giornalieri e scontrini',
    collegata: ['Prima Nota Cassa', 'Dashboard Analytics', 'Report IVA'],
    alimentata: ['Import XML Corrispettivi', 'Registrazione Manuale'],
    cascade: 'Eliminazione → Aggiorna fatturato in Dashboard',
    collection: 'corrispettivi'
  },
  'scadenze': {
    icon: '📅',
    title: 'Scadenzario',
    description: 'Scadenze pagamenti fornitori e F24',
    collegata: ['Fatture Ricevute', 'F24', 'Riconciliazione', 'Prima Nota Banca'],
    alimentata: ['Import Fatture (automatico)', 'Import F24', 'Manuale'],
    cascade: 'Pagamento → Aggiorna stato, crea movimento in Prima Nota',
    collection: 'scadenzario_fornitori'
  },
  'f24': {
    icon: '🏛️',
    title: 'Modelli F24',
    description: 'Tributi e contributi da versare',
    collegata: ['Scadenze', 'Cedolini', 'Prima Nota Salari', 'Dipendenti'],
    alimentata: ['Import PDF F24', 'Calcolo da Cedolini'],
    cascade: 'Pagamento → Aggiorna scadenzario, crea movimento Prima Nota',
    collection: 'f24_models'
  },
  'analytics': {
    icon: '📊',
    title: 'Dashboard Analytics',
    description: 'KPI e statistiche in tempo reale',
    collegata: ['Corrispettivi', 'Prima Nota', 'Fatture', 'Dipendenti'],
    alimentata: ['Aggregazione automatica da tutte le collezioni'],
    cascade: 'Sola lettura - nessun dato modificabile',
    collection: 'multiple (read-only)'
  },
  'import': {
    icon: '📤',
    title: 'Import Unificato',
    description: 'Caricamento documenti con rilevamento automatico',
    collegata: ['Tutte le pagine (in base al tipo file)'],
    alimentata: ['Upload manuale'],
    cascade: 'Import → Popola la collezione corrispondente al tipo file',
    collection: 'routing automatico'
  }
};

export function PageInfoCard({ pageKey, style = {} }) {
  const [expanded, setExpanded] = useState(false);
  const info = PAGE_INFO[pageKey];

  if (!info) return null;

  return (
    <div style={{
      background: 'white',
      borderRadius: 10,
      boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
      border: '1px solid #dce8f4',
      overflow: 'hidden',
      fontSize: 12,
      maxWidth: 320,
      ...style
    }}>
      {/* Header cliccabile */}
      <button
        onClick={() => setExpanded(!expanded)}
        style={{
          width: '100%',
          padding: '10px 14px',
          background: expanded ? '#f8fafc' : 'white',
          border: 'none',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          textAlign: 'left'
        }}
      >
        <span style={{ fontSize: 18 }}>{info.icon}</span>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 600, color: '#1e293b', fontSize: 13 }}>{info.title}</div>
          <div style={{ color: '#64748b', fontSize: 11 }}>{info.description}</div>
        </div>
        <span style={{ 
          color: '#94a3b8', 
          fontSize: 10,
          transform: expanded ? 'rotate(180deg)' : 'none',
          transition: 'transform 0.2s'
        }}>
          ▼
        </span>
      </button>

      {/* Contenuto espanso */}
      {expanded && (
        <div style={{ padding: '0 14px 14px', borderTop: '1px solid #f1f5f9' }}>
          {/* Collegata a */}
          <div style={{ marginTop: 12 }}>
            <div style={{ color: '#64748b', fontSize: 10, fontWeight: 600, marginBottom: 4 }}>
              🔗 COLLEGATA A
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
              {info.collegata.map((item, idx) => (
                <span key={idx} style={{
                  padding: '2px 8px',
                  background: '#dbeafe',
                  color: '#1535a8',
                  borderRadius: 4,
                  fontSize: 10
                }}>
                  {item}
                </span>
              ))}
            </div>
          </div>

          {/* Alimentata da */}
          <div style={{ marginTop: 10 }}>
            <div style={{ color: '#64748b', fontSize: 10, fontWeight: 600, marginBottom: 4 }}>
              📥 ALIMENTATA DA
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
              {info.alimentata.map((item, idx) => (
                <span key={idx} style={{
                  padding: '2px 8px',
                  background: '#d1fae5',
                  color: '#047857',
                  borderRadius: 4,
                  fontSize: 10
                }}>
                  {item}
                </span>
              ))}
            </div>
          </div>

          {/* Azioni a cascata */}
          <div style={{ marginTop: 10 }}>
            <div style={{ color: '#64748b', fontSize: 10, fontWeight: 600, marginBottom: 4 }}>
              ⚡ AZIONI A CASCATA
            </div>
            <div style={{
              padding: '6px 10px',
              background: '#fef3c7',
              color: '#92400e',
              borderRadius: 4,
              fontSize: 10,
              lineHeight: 1.4
            }}>
              {info.cascade}
            </div>
          </div>

          {/* Collezione DB */}
          <div style={{ 
            marginTop: 10, 
            paddingTop: 8, 
            borderTop: '1px dashed #dce8f4',
            fontSize: 10,
            color: '#94a3b8'
          }}>
            📦 Collezione: <code style={{ background: '#f1f5f9', padding: '1px 4px', borderRadius: 2 }}>{info.collection}</code>
          </div>
        </div>
      )}
    </div>
  );
}

export default PageInfoCard;
