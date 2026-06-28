import React, { useState, useEffect } from 'react';
import api from '../api';
import { toast } from 'sonner';

/**
 * Modal inserimento massivo giustificativi/presenze.
 * Props:
 *  - open: bool
 *  - onClose: () => void
 *  - dipendenti: [{id, nome, cognome}] (lista completa selezionabile)
 *  - preselected_ids: [str] (opzionale, pre-selezionati)
 *  - onSaved: () => void (refresh callback)
 */
export default function BatchGiustificativoModal({
  open,
  onClose,
  dipendenti = [],
  preselected_ids = [],
  onSaved,
}) {
  const [selectedEmpIds, setSelectedEmpIds] = useState(preselected_ids);
  const [dataInizio, setDataInizio] = useState('');
  const [dataFine, setDataFine] = useState('');
  const [stato, setStato] = useState('FE');
  const [ore, setOre] = useState(8);
  const [protocollo, setProtocollo] = useState('');
  const [note, setNote] = useState('');
  const [tipologie, setTipologie] = useState([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setSelectedEmpIds(preselected_ids.length ? preselected_ids : []);
    api
      .get('/api/attendance/tipologie-giustificativi')
      .then(r => setTipologie(r.data?.tipologie || []))
      .catch(() => setTipologie([]));
  }, [open, preselected_ids]);

  const tipo = tipologie.find(t => t.codice === stato);
  const protocolloObbligatorio = tipo?.protocollo_obbligatorio;

  const giorniRange = () => {
    if (!dataInizio) return [];
    const start = new Date(dataInizio);
    const end = dataFine ? new Date(dataFine) : start;
    const out = [];
    const d = new Date(start);
    while (d <= end) {
      out.push(d.toISOString().slice(0, 10));
      d.setDate(d.getDate() + 1);
    }
    return out;
  };

  const giorni = giorniRange();

  const handleSave = async () => {
    if (selectedEmpIds.length === 0) {
      toast.error('Seleziona almeno un dipendente');
      return;
    }
    if (giorni.length === 0) {
      toast.error('Seleziona un range date valido');
      return;
    }
    if (protocolloObbligatorio && !protocollo.trim()) {
      toast.error(`Protocollo obbligatorio per ${tipo.nome}`);
      return;
    }
    setSaving(true);
    try {
      const body = {
        employee_ids: selectedEmpIds,
        giorni,
        stato,
        ore: parseFloat(ore) || 8.0,
        protocollo: protocollo.trim() || null,
        note: note.trim() || null,
      };
      const res = await api.post('/api/attendance/batch-insert', body);
      toast.success(`✓ ${res.data.message}`);
      onSaved?.();
      onClose();
    } catch (e) {
      toast.error('Errore: ' + (e.response?.data?.detail || e.message));
    } finally {
      setSaving(false);
    }
  };

  if (!open) return null;

  const categorieColor = {
    ferie: '#1d4ed8',
    permessi: '#4338ca',
    malattia: '#92400e',
    infortunio: '#dc2626',
    congedi: '#15803d',
    riposi: '#0891b2',
    assenze: '#dc2626',
    presenza: '#16a34a',
  };

  return (
    <div
      data-testid="batch-giustificativo-modal"
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.5)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
        padding: 20,
      }}
      onClick={onClose}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: 'white',
          borderRadius: 16,
          maxWidth: 720,
          width: '100%',
          maxHeight: '90vh',
          overflow: 'auto',
          padding: 28,
        }}
      >
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: 20,
          }}
        >
          <h2 style={{ margin: 0, fontSize: 18, color: '#0f2744' }}>
            📝 Inserimento massivo giustificativi
          </h2>
          <button
            data-testid="close-modal-btn"
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              fontSize: 22,
              cursor: 'pointer',
              color: '#64748b',
            }}
          >
            ✕
          </button>
        </div>

        {/* Step 1: Dipendenti */}
        <div style={{ marginBottom: 16 }}>
          <label
            style={{
              fontSize: 13,
              fontWeight: 600,
              color: '#334155',
              display: 'block',
              marginBottom: 6,
            }}
          >
            1️⃣ Dipendenti ({selectedEmpIds.length} selezionati)
          </label>
          <div
            style={{
              maxHeight: 140,
              overflow: 'auto',
              border: '1px solid #e2e8f0',
              borderRadius: 8,
              padding: 8,
            }}
          >
            <label
              style={{
                display: 'block',
                fontSize: 12,
                fontWeight: 700,
                color: '#0070ba',
                marginBottom: 4,
                cursor: 'pointer',
              }}
            >
              <input
                type="checkbox"
                data-testid="select-all-emp"
                checked={selectedEmpIds.length === dipendenti.length && dipendenti.length > 0}
                onChange={e => setSelectedEmpIds(e.target.checked ? dipendenti.map(d => d.id) : [])}
              />{' '}
              Seleziona tutti ({dipendenti.length})
            </label>
            {dipendenti.map(d => (
              <label
                key={d.id}
                data-testid={`emp-${d.id}`}
                style={{ display: 'block', fontSize: 13, padding: '3px 0', cursor: 'pointer' }}
              >
                <input
                  type="checkbox"
                  checked={selectedEmpIds.includes(d.id)}
                  onChange={e =>
                    setSelectedEmpIds(prev =>
                      e.target.checked ? [...prev, d.id] : prev.filter(id => id !== d.id)
                    )
                  }
                />{' '}
                {d.cognome} {d.nome}
              </label>
            ))}
          </div>
        </div>

        {/* Step 2: Range date */}
        <div style={{ marginBottom: 16 }}>
          <label
            style={{
              fontSize: 13,
              fontWeight: 600,
              color: '#334155',
              display: 'block',
              marginBottom: 6,
            }}
          >
            2️⃣ Periodo ({giorni.length} giorni)
          </label>
          <div style={{ display: 'flex', gap: 12 }}>
            <input
              type="date"
              data-testid="data-inizio"
              value={dataInizio}
              onChange={e => setDataInizio(e.target.value)}
              style={{ flex: 1, padding: '8px 10px', border: '1px solid #d1d5db', borderRadius: 6 }}
            />
            <input
              type="date"
              data-testid="data-fine"
              value={dataFine}
              onChange={e => setDataFine(e.target.value)}
              min={dataInizio}
              style={{ flex: 1, padding: '8px 10px', border: '1px solid #d1d5db', borderRadius: 6 }}
            />
          </div>
        </div>

        {/* Step 3: Tipologia */}
        <div style={{ marginBottom: 16 }}>
          <label
            style={{
              fontSize: 13,
              fontWeight: 600,
              color: '#334155',
              display: 'block',
              marginBottom: 6,
            }}
          >
            3️⃣ Tipologia giustificativo
          </label>
          <select
            data-testid="select-tipologia"
            value={stato}
            onChange={e => {
              setStato(e.target.value);
              const t = tipologie.find(x => x.codice === e.target.value);
              if (t?.ore_default) setOre(t.ore_default);
            }}
            style={{
              width: '100%',
              padding: '10px',
              border: '1px solid #d1d5db',
              borderRadius: 6,
              fontSize: 14,
            }}
          >
            {tipologie.map(t => (
              <option key={t.codice} value={t.codice}>
                {t.protocollo_obbligatorio ? '🔴 ' : ''}
                {t.codice} — {t.nome}
                {t.normativa ? ` (${t.normativa})` : ''}
              </option>
            ))}
          </select>
          {tipo && (
            <div
              style={{
                marginTop: 6,
                padding: 8,
                background: '#f8fafc',
                borderRadius: 6,
                fontSize: 12,
                color: '#475569',
                borderLeft: `3px solid ${categorieColor[tipo.categoria] || '#64748b'}`,
              }}
            >
              <strong>Categoria:</strong> {tipo.categoria} · <strong>Default ore:</strong>{' '}
              {tipo.ore_default}h
              {tipo.normativa && (
                <>
                  <br />
                  <strong>Normativa:</strong> {tipo.normativa}
                </>
              )}
              {tipo.note && (
                <>
                  <br />
                  <strong>Note:</strong> {tipo.note}
                </>
              )}
            </div>
          )}
        </div>

        {/* Step 4: Ore + Protocollo */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 12, marginBottom: 16 }}>
          <div>
            <label
              style={{
                fontSize: 13,
                fontWeight: 600,
                color: '#334155',
                display: 'block',
                marginBottom: 6,
              }}
            >
              Ore/giorno
            </label>
            <input
              type="number"
              data-testid="ore-giorno"
              step="0.5"
              min="0"
              max="12"
              value={ore}
              onChange={e => setOre(e.target.value)}
              style={{
                width: '100%',
                padding: '8px 10px',
                border: '1px solid #d1d5db',
                borderRadius: 6,
              }}
            />
          </div>
          <div>
            <label
              style={{
                fontSize: 13,
                fontWeight: 600,
                color: '#334155',
                display: 'block',
                marginBottom: 6,
              }}
            >
              Protocollo {protocolloObbligatorio && <span style={{ color: '#dc2626' }}>*</span>}
            </label>
            <input
              type="text"
              data-testid="protocollo-input"
              value={protocollo}
              onChange={e => setProtocollo(e.target.value)}
              placeholder={
                protocolloObbligatorio ? 'N° INPS/Certificato (obbligatorio)' : 'Opzionale'
              }
              style={{
                width: '100%',
                padding: '8px 10px',
                border: `1px solid ${protocolloObbligatorio ? '#dc2626' : '#d1d5db'}`,
                borderRadius: 6,
              }}
            />
          </div>
        </div>

        {/* Note */}
        <div style={{ marginBottom: 16 }}>
          <label
            style={{
              fontSize: 13,
              fontWeight: 600,
              color: '#334155',
              display: 'block',
              marginBottom: 6,
            }}
          >
            Note
          </label>
          <textarea
            data-testid="note-input"
            value={note}
            onChange={e => setNote(e.target.value)}
            rows={2}
            style={{
              width: '100%',
              padding: '8px 10px',
              border: '1px solid #d1d5db',
              borderRadius: 6,
              resize: 'vertical',
              fontFamily: 'inherit',
            }}
          />
        </div>

        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
          <button
            data-testid="cancel-btn"
            onClick={onClose}
            disabled={saving}
            style={{
              padding: '10px 18px',
              background: '#f1f5f9',
              color: '#334155',
              border: 'none',
              borderRadius: 8,
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Annulla
          </button>
          <button
            data-testid="save-batch-btn"
            onClick={handleSave}
            disabled={saving || selectedEmpIds.length === 0 || giorni.length === 0}
            style={{
              padding: '10px 22px',
              background:
                saving || selectedEmpIds.length === 0 || giorni.length === 0
                  ? '#94a3b8'
                  : '#0f2744',
              color: 'white',
              border: 'none',
              borderRadius: 8,
              fontWeight: 700,
              cursor: saving ? 'not-allowed' : 'pointer',
            }}
          >
            {saving
              ? '⏳ Salvataggio...'
              : `💾 Applica a ${selectedEmpIds.length} dip × ${giorni.length} gg`}
          </button>
        </div>
      </div>
    </div>
  );
}
