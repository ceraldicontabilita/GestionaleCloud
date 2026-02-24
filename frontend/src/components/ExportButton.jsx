import React from 'react';
import { Download } from 'lucide-react';

export const ExportButton = ({ onClick, disabled = false, label = "Esporta" }) => {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        padding: '8px 16px',
        background: disabled ? '#e2e8f0' : '#22c55e',
        color: disabled ? '#94a3b8' : 'white',
        border: 'none',
        borderRadius: '8px',
        cursor: disabled ? 'not-allowed' : 'pointer',
        display: 'flex',
        alignItems: 'center',
        gap: '6px',
        fontSize: '14px',
        fontWeight: '500',
        transition: 'all 0.2s'
      }}
      onMouseEnter={(e) => {
        if (!disabled) {
          e.target.style.background = '#16a34a';
        }
      }}
      onMouseLeave={(e) => {
        if (!disabled) {
          e.target.style.background = '#22c55e';
        }
      }}
    >
      <Download size={16} />
      {label}
    </button>
  );
};

export default ExportButton;
