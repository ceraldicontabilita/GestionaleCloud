import React, { useState, useEffect, useCallback } from 'react';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import {
  formatEuro,
  formatDateIT,
  STYLES,
  COLORS,
  button,
  badge,
  useIsMobile,
  RG,
  pagePad,
} from '../lib/utils';
import { Package, Search, Plus, Trash2, Save, X, Check, Calculator, Archive } from 'lucide-react';
import { PageLayout } from '../components/PageLayout';

export default function Inventario() {
  const isMobile = useIsMobile();
  const { anno } = useAnnoGlobale();
  const [inventari, setInventari] = useState([]);
  const [loading, setLoading] = useState(true);

  // Creazione inventario
  const [showCreazione, setShowCreazione] = useState(false);
  const [importoTarget, setImportoTarget] = useState('');
  const [annoInventario, setAnnoInventario] = useState(anno);
  const [prodottiInventario, setProdottiInventario] = useState([]);
  const [totaleCorrente, setTotaleCorrente] = useState(0);

  // Ricerca prodotti
  const [searchProdotto, setSearchProdotto] = useState('');
  const [risultatiRicerca, setRisultatiRicerca] = useState([]);
  const [loadingRicerca, setLoadingRicerca] = useState(false);

  // Salvataggio
  const [saving, setSaving] = useState(false);

  const loadInventari = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/api/inventario');
      setInventari(res.data.inventari || []);
    } catch (e) {
      console.error('Errore caricamento inventari:', e);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    loadInventari();
  }, [loadInventari]);

  useEffect(() => {
    // Calcola totale corrente
    const tot = prodottiInventario.reduce((sum, p) => sum + p.quantita * p.prezzo_unitario, 0);
    setTotaleCorrente(tot);
  }, [prodottiInventario]);

  async function searchProdotti(query) {
    if (!query || query.length < 2) {
      setRisultatiRicerca([]);
      return;
    }
    setLoadingRicerca(true);
    try {
      const res = await api.get(
        `/api/dizionario-prodotti/prodotti/search-per-ingrediente?ingrediente=${encodeURIComponent(query)}`
      );
      setRisultatiRicerca(res.data.prodotti || []);
    } catch (e) {
      console.error('Errore ricerca:', e);
    }
    setLoadingRicerca(false);
  }

  function aggiungiProdotto(prodotto) {
    // Verifica se già presente
    if (prodottiInventario.find(p => p.prodotto_id === prodotto.id)) {
      alert('Prodotto già presente in lista');
      return;
    }

    setProdottiInventario([
      ...prodottiInventario,
      {
        prodotto_id: prodotto.id,
        descrizione: prodotto.descrizione,
        fornitore: prodotto.fornitore_nome,
        prezzo_unitario: prodotto.prezzo_per_kg || prodotto.ultimo_prezzo_unitario || 0,
        quantita: 1,
        unita: 'kg',
      },
    ]);
    setSearchProdotto('');
    setRisultatiRicerca([]);
  }

  function updateProdottoQta(index, quantita) {
    setProdottiInventario(
      prodottiInventario.map((p, i) =>
        i === index ? { ...p, quantita: parseFloat(quantita) || 0 } : p
      )
    );
  }

  function updateProdottoPrezzo(index, prezzo) {
    setProdottiInventario(
      prodottiInventario.map((p, i) =>
        i === index ? { ...p, prezzo_unitario: parseFloat(prezzo) || 0 } : p
      )
    );
  }

  function removeProdotto(index) {
    setProdottiInventario(prodottiInventario.filter((_, i) => i !== index));
  }

  async function salvaInventario() {
    if (prodottiInventario.length === 0) {
      alert('Aggiungi almeno un prodotto');
      return;
    }

    setSaving(true);
    try {
      await api.post('/api/inventario', {
        anno: annoInventario,
        importo_target: parseFloat(importoTarget) || 0,
        importo_totale: totaleCorrente,
        prodotti: prodottiInventario,
        data_creazione: new Date().toISOString(),
      });

      alert('Inventario salvato con successo!');
      setShowCreazione(false);
      setProdottiInventario([]);
      setImportoTarget('');
      loadInventari();
    } catch (e) {
      alert('Errore salvataggio: ' + (e.response?.data?.detail || e.message));
    }
    setSaving(false);
  }

  function nuovoInventario() {
    setShowCreazione(true);
    setProdottiInventario([]);
    setImportoTarget('');
    setAnnoInventario(anno);
  }

  const differenza = parseFloat(importoTarget) - totaleCorrente;
  const percentualeRaggiunta = importoTarget
    ? (totaleCorrente / parseFloat(importoTarget)) * 100
    : 0;

  return (
    <PageLayout
      title="Inventario"
      icon="📦"
      subtitle="Crea e gestisci inventari annuali con importo target"
      actions={
        <button
          onClick={nuovoInventario}
          style={{
            padding: '12px 24px',
            background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
            color: 'white',
            border: 'none',
            borderRadius: '10px',
            cursor: 'pointer',
            fontSize: '14px',
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
          }}
        >
          <Plus size={18} />
          Nuovo Inventario
        </button>
      }
    >
      {/* Lista Inventari Esistenti */}
      {!showCreazione && (
        <div>
          {loading ? (
            <div style={{ textAlign: 'center', padding: '40px', color: '#6b7280' }}>
              Caricamento...
            </div>
          ) : inventari.length === 0 ? (
            <div
              style={{
                textAlign: 'center',
                padding: '60px',
                background: '#f8fafc',
                borderRadius: '16px',
              }}
            >
              <Archive size={64} style={{ color: '#cbd5e1', marginBottom: '16px' }} />
              <h3 style={{ color: '#64748b', margin: '0 0 8px 0' }}>Nessun inventario</h3>
              <p style={{ color: '#94a3b8', margin: 0 }}>
                Clicca su &quot;Nuovo Inventario&quot; per crearne uno
              </p>
            </div>
          ) : (
            <div style={{ display: 'grid', gap: '16px' }}>
              {inventari.map((inv, idx) => (
                <div
                  key={idx}
                  style={{
                    background: 'white',
                    borderRadius: '12px',
                    border: '1px solid #e2e8f0',
                    padding: '20px',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                  }}
                >
                  <div>
                    <div style={{ fontSize: '18px', fontWeight: 600, color: '#1e293b' }}>
                      Inventario {inv.anno}
                    </div>
                    <div style={{ fontSize: '13px', color: '#64748b', marginTop: '4px' }}>
                      {inv.prodotti?.length || 0} prodotti • Creato il{' '}
                      {formatDateIT(inv.data_creazione)}
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: '24px', fontWeight: 700, color: '#10b981' }}>
                      {formatEuro(inv.importo_totale || 0)}
                    </div>
                    {inv.importo_target > 0 && (
                      <div style={{ fontSize: '12px', color: '#64748b' }}>
                        Target: {formatEuro(inv.importo_target)}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Creazione Nuovo Inventario */}
      {showCreazione && (
        <div
          style={{
            background: 'white',
            borderRadius: '16px',
            border: '1px solid #e2e8f0',
            overflow: 'hidden',
          }}
        >
          {/* Header Creazione */}
          <div
            style={{
              padding: '20px 24px',
              background: 'linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%)',
              color: 'white',
            }}
          >
            <h2 style={{ margin: 0, fontSize: '20px', fontWeight: 600 }}>Nuovo Inventario</h2>
            <p style={{ margin: '8px 0 0 0', opacity: 0.9, fontSize: '14px' }}>
              Inserisci i prodotti fino a raggiungere l importo target
            </p>
          </div>

          {/* Parametri */}
          <div
            style={{
              padding: '20px 24px',
              borderBottom: '1px solid #e5e7eb',
              display: 'flex',
              gap: '20px',
              flexWrap: 'wrap',
            }}
          >
            <div>
              <label
                style={{
                  display: 'block',
                  fontSize: '12px',
                  fontWeight: 600,
                  color: '#64748b',
                  marginBottom: '6px',
                }}
              >
                ANNO INVENTARIO
              </label>
              <select
                value={annoInventario}
                onChange={e => setAnnoInventario(parseInt(e.target.value))}
                style={{
                  padding: '10px 14px',
                  border: '1px solid #e5e7eb',
                  borderRadius: '8px',
                  fontSize: '14px',
                  minWidth: '120px',
                }}
              >
                {[...Array(8)].map((_, i) => {
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
                style={{
                  display: 'block',
                  fontSize: '12px',
                  fontWeight: 600,
                  color: '#64748b',
                  marginBottom: '6px',
                }}
              >
                IMPORTO TARGET (€ netto IVA)
              </label>
              <input
                type="number"
                value={importoTarget}
                onChange={e => setImportoTarget(e.target.value)}
                placeholder="Es: 7250"
                style={{
                  padding: '10px 14px',
                  border: '1px solid #e5e7eb',
                  borderRadius: '8px',
                  fontSize: '14px',
                  width: '150px',
                }}
              />
            </div>

            {/* Progress Bar */}
            {importoTarget > 0 && (
              <div style={{ flex: 1, minWidth: '300px' }}>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    fontSize: '12px',
                    color: '#64748b',
                    marginBottom: '6px',
                  }}
                >
                  <span>
                    Progresso: {formatEuro(totaleCorrente)} /{' '}
                    {formatEuro(parseFloat(importoTarget))}
                  </span>
                  <span style={{ color: percentualeRaggiunta >= 100 ? '#10b981' : '#f59e0b' }}>
                    {percentualeRaggiunta.toFixed(1)}%
                  </span>
                </div>
                <div
                  style={{
                    height: '8px',
                    background: '#e5e7eb',
                    borderRadius: '4px',
                    overflow: 'hidden',
                  }}
                >
                  <div
                    style={{
                      height: '100%',
                      width: `${Math.min(percentualeRaggiunta, 100)}%`,
                      background:
                        percentualeRaggiunta >= 100
                          ? '#10b981'
                          : 'linear-gradient(90deg, #3b82f6, #8b5cf6)',
                      transition: 'width 0.3s',
                    }}
                  />
                </div>
                {importoTarget > 0 && (
                  <div
                    style={{
                      fontSize: '12px',
                      marginTop: '4px',
                      color: differenza > 0 ? '#f59e0b' : '#10b981',
                    }}
                  >
                    {differenza > 0
                      ? `Mancano ${formatEuro(differenza)}`
                      : `Superato di ${formatEuro(Math.abs(differenza))}`}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Ricerca Prodotti */}
          <div style={{ padding: '20px 24px', borderBottom: '1px solid #e5e7eb' }}>
            <label
              style={{
                display: 'block',
                fontSize: '12px',
                fontWeight: 600,
                color: '#64748b',
                marginBottom: '8px',
              }}
            >
              AGGIUNGI PRODOTTO DAL DIZIONARIO
            </label>
            <div style={{ position: 'relative' }}>
              <Search
                size={18}
                style={{
                  position: 'absolute',
                  left: '12px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  color: '#9ca3af',
                }}
              />
              <input
                type="text"
                value={searchProdotto}
                onChange={e => {
                  setSearchProdotto(e.target.value);
                  searchProdotti(e.target.value);
                }}
                placeholder="Cerca prodotto (es: farina, zucchero, burro...)"
                style={{
                  width: '100%',
                  padding: '12px 12px 12px 42px',
                  border: '1px solid #e5e7eb',
                  borderRadius: '8px',
                  fontSize: '14px',
                }}
              />

              {/* Risultati ricerca */}
              {risultatiRicerca.length > 0 && (
                <div
                  style={{
                    position: 'absolute',
                    top: '100%',
                    left: 0,
                    right: 0,
                    background: 'white',
                    border: '1px solid #e5e7eb',
                    borderRadius: '8px',
                    boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
                    maxHeight: '300px',
                    overflow: 'auto',
                    zIndex: 100,
                  }}
                >
                  {risultatiRicerca.map((prod, idx) => (
                    <div
                      key={idx}
                      onClick={() => aggiungiProdotto(prod)}
                      style={{
                        padding: '12px 16px',
                        cursor: 'pointer',
                        borderBottom: '1px solid #f1f5f9',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                      }}
                      onMouseEnter={e => (e.currentTarget.style.background = '#f0f9ff')}
                      onMouseLeave={e => (e.currentTarget.style.background = 'white')}
                    >
                      <div>
                        <div style={{ fontWeight: 500, color: '#1e293b', fontSize: '13px' }}>
                          {prod.descrizione}
                        </div>
                        <div style={{ fontSize: '11px', color: '#64748b' }}>
                          {prod.fornitore_nome}
                        </div>
                      </div>
                      <div
                        style={{
                          padding: '4px 10px',
                          background: prod.prezzo_per_kg ? '#dcfce7' : '#fef3c7',
                          borderRadius: '6px',
                          fontSize: '12px',
                          fontWeight: 600,
                          color: prod.prezzo_per_kg ? '#15803d' : '#92400e',
                        }}
                      >
                        {prod.prezzo_per_kg ? `${formatEuro(prod.prezzo_per_kg)}/kg` : 'Prezzo N/D'}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Lista Prodotti Aggiunti */}
          <div style={{ padding: '20px 24px' }}>
            <div
              style={{ fontSize: '12px', fontWeight: 600, color: '#64748b', marginBottom: '12px' }}
            >
              PRODOTTI IN INVENTARIO ({prodottiInventario.length})
            </div>

            {prodottiInventario.length === 0 ? (
              <div
                style={{
                  textAlign: 'center',
                  padding: '40px',
                  background: '#f8fafc',
                  borderRadius: '12px',
                  color: '#64748b',
                }}
              >
                Nessun prodotto aggiunto. Usa la ricerca sopra per aggiungere prodotti.
              </div>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ background: '#f8fafc' }}>
                    <th
                      style={{
                        padding: '10px 12px',
                        textAlign: 'left',
                        fontSize: '11px',
                        fontWeight: 600,
                        color: '#64748b',
                      }}
                    >
                      PRODOTTO
                    </th>
                    <th
                      style={{
                        padding: '10px 12px',
                        textAlign: 'center',
                        fontSize: '11px',
                        fontWeight: 600,
                        color: '#64748b',
                        width: '100px',
                      }}
                    >
                      QTÀ
                    </th>
                    <th
                      style={{
                        padding: '10px 12px',
                        textAlign: 'center',
                        fontSize: '11px',
                        fontWeight: 600,
                        color: '#64748b',
                        width: '120px',
                      }}
                    >
                      €/KG
                    </th>
                    <th
                      style={{
                        padding: '10px 12px',
                        textAlign: 'right',
                        fontSize: '11px',
                        fontWeight: 600,
                        color: '#64748b',
                        width: '120px',
                      }}
                    >
                      TOTALE
                    </th>
                    <th style={{ padding: '10px 12px', textAlign: 'center', width: '50px' }}></th>
                  </tr>
                </thead>
                <tbody>
                  {prodottiInventario.map((prod, idx) => (
                    <tr key={idx} style={{ borderBottom: '1px solid #f1f5f9' }}>
                      <td style={{ padding: '12px' }}>
                        <div style={{ fontWeight: 500, color: '#1e293b', fontSize: '13px' }}>
                          {prod.descrizione}
                        </div>
                        <div style={{ fontSize: '11px', color: '#64748b' }}>{prod.fornitore}</div>
                      </td>
                      <td style={{ padding: '12px', textAlign: 'center' }}>
                        <input
                          type="number"
                          value={prod.quantita}
                          onChange={e => updateProdottoQta(idx, e.target.value)}
                          style={{
                            width: '70px',
                            padding: '6px',
                            border: '1px solid #e5e7eb',
                            borderRadius: '6px',
                            textAlign: 'center',
                          }}
                          step="0.1"
                        />
                      </td>
                      <td style={{ padding: '12px', textAlign: 'center' }}>
                        <input
                          type="number"
                          value={prod.prezzo_unitario}
                          onChange={e => updateProdottoPrezzo(idx, e.target.value)}
                          style={{
                            width: '90px',
                            padding: '6px',
                            border: '1px solid #e5e7eb',
                            borderRadius: '6px',
                            textAlign: 'center',
                          }}
                          step="0.01"
                        />
                      </td>
                      <td
                        style={{
                          padding: '12px',
                          textAlign: 'right',
                          fontWeight: 600,
                          color: '#1e293b',
                        }}
                      >
                        {formatEuro(prod.quantita * prod.prezzo_unitario)}
                      </td>
                      <td style={{ padding: '12px', textAlign: 'center' }}>
                        <button
                          onClick={() => removeProdotto(idx)}
                          style={{
                            padding: '6px',
                            background: '#fef2f2',
                            border: 'none',
                            borderRadius: '6px',
                            cursor: 'pointer',
                            color: '#dc2626',
                          }}
                        >
                          <Trash2 size={14} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr style={{ background: '#f0fdf4' }}>
                    <td
                      colSpan={3}
                      style={{
                        padding: '14px 12px',
                        fontWeight: 600,
                        color: '#15803d',
                        textAlign: 'right',
                      }}
                    >
                      TOTALE INVENTARIO:
                    </td>
                    <td
                      style={{
                        padding: '14px 12px',
                        fontWeight: 700,
                        fontSize: '18px',
                        color: '#15803d',
                        textAlign: 'right',
                      }}
                    >
                      {formatEuro(totaleCorrente)}
                    </td>
                    <td></td>
                  </tr>
                </tfoot>
              </table>
            )}
          </div>

          {/* Footer Actions */}
          <div
            style={{
              padding: '16px 24px',
              borderTop: '1px solid #e5e7eb',
              display: 'flex',
              gap: '12px',
              justifyContent: 'flex-end',
              background: '#f8fafc',
            }}
          >
            <button
              onClick={() => setShowCreazione(false)}
              style={{
                padding: '10px 20px',
                background: '#f3f4f6',
                border: 'none',
                borderRadius: '8px',
                cursor: 'pointer',
                fontSize: '14px',
              }}
            >
              Annulla
            </button>
            <button
              onClick={salvaInventario}
              disabled={saving || prodottiInventario.length === 0}
              style={{
                padding: '10px 24px',
                background: saving ? '#9ca3af' : '#10b981',
                color: 'white',
                border: 'none',
                borderRadius: '8px',
                cursor: saving ? 'not-allowed' : 'pointer',
                fontSize: '14px',
                fontWeight: 600,
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
              }}
            >
              <Save size={16} />
              {saving ? 'Salvataggio...' : `Salda Inventario ${annoInventario}`}
            </button>
          </div>
        </div>
      )}
    </PageLayout>
  );
}
