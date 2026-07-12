import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { useIsMobile } from '../../lib/utils';

/**
 * HubTabs — barra degli hub (Fatture, Prima Nota, Riconciliazione,
 * Contabilità, Admin, Dashboard, …).
 *
 * Comportamento voluto dall'utente (12/07/2026): entrando in una pagina
 * specifica NON si deve vedere la fila dei tab di tutte le altre pagine, ma
 * solo un pulsante «← Indietro» (torna alla pagina precedente). A destra
 * resta un menù a tendina compatto «Vai a sezione» — necessario perché
 * alcune sezioni (es. le 13 di Contabilità, Corrispettivi dentro Fatture,
 * Archivio bonifici) esistono SOLO dentro il loro hub: senza quel menù
 * diventerebbero irraggiungibili. Il menù è nascosto finché non lo apri:
 * niente barra di tab, solo «Indietro» + un selettore discreto.
 *
 * API invariata: tabs [{ id, label, Icon }], activeId, onSelect(tab).
 */
export function HubTabs({ tabs = [], activeId, onSelect = () => {}, testIdPrefix = 'tab', style = {} }) {
  const isMobile = useIsMobile();
  const navigate = useNavigate();

  // Il select mostra la sezione corrente solo se è tra le opzioni (alcune
  // pagine canoniche, es. F24, non sono un tab dell'hub: in quel caso niente
  // valore selezionato, ma il pulsante Indietro c'è sempre).
  const valoreSelect = tabs.some(t => t.id === activeId) ? activeId : '';

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '8px 12px',
        background: 'white',
        borderBottom: '1px solid #e2e8f0',
        borderRadius: '8px 8px 0 0',
        marginBottom: 16,
        ...style,
      }}
    >
      <button
        type="button"
        onClick={() => navigate(-1)}
        data-testid={`${testIdPrefix}-indietro`}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 6,
          padding: isMobile ? '8px 12px' : '9px 14px',
          minHeight: 40,
          borderRadius: 6,
          border: '1px solid #0f2744',
          background: '#0f2744',
          color: '#fff',
          fontWeight: 700,
          fontSize: isMobile ? 12.5 : 13,
          cursor: 'pointer',
          whiteSpace: 'nowrap',
        }}
      >
        <ArrowLeft size={16} />
        Indietro
      </button>

      {tabs.length > 1 && (
        <select
          value={valoreSelect}
          onChange={e => {
            const tab = tabs.find(t => t.id === e.target.value);
            if (tab) onSelect(tab);
          }}
          data-testid={`${testIdPrefix}-select`}
          aria-label="Vai a sezione"
          style={{
            marginLeft: 'auto',
            minHeight: 40,
            maxWidth: isMobile ? '58%' : 260,
            padding: '8px 10px',
            borderRadius: 6,
            border: '1px solid #e2e8f0',
            background: '#fff',
            color: '#0f2744',
            fontWeight: 600,
            fontSize: isMobile ? 12.5 : 13,
            cursor: 'pointer',
          }}
        >
          {valoreSelect === '' && (
            <option value="" disabled>
              Vai a sezione…
            </option>
          )}
          {tabs.map(t => (
            <option key={t.id} value={t.id}>
              {t.label}
            </option>
          ))}
        </select>
      )}
    </div>
  );
}

export default HubTabs;
