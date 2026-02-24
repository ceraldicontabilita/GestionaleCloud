import React, { useState, useEffect } from 'react';
import api from '../api';
import { formatEuro, formatDateIT, STYLES, COLORS, button, badge } from '../lib/utils';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { PageLayout } from '../components/PageLayout';

export default function MagazzinoDoppiaVerita() {
  const { anno } = useAnnoGlobale();
  const [prodotti, setProdotti] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [soloDifferenze, setSoloDifferenze] = useState(false);
  const [soloScorteBasse, setSoloScorteBasse] = useState(false);
  const [stats, setStats] = useState({});
  const [selectedProdotto, setSelectedProdotto] = useState(null);
  const [fornitoriEsclusi, setFornitoriEsclusi] = useState(null);
  const [puliziaInCorso, setPuliziaInCorso] = useState(false);

  useEffect(() => {
    loadProdotti();
  }, [search, soloDifferenze, soloScorteBasse, anno]);

  async function loadProdotti() {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (search) params.append('search', search);
      if (soloDifferenze) params.append('solo_differenze', 'true');
      if (soloScorteBasse) params.append('solo_scorte_basse', 'true');
      params.append('anno', anno.toString());
      params.append('limit', '500');
      
      const res = await api.get(`/api/magazzino-dv/prodotti?${params.toString()}`);
      setProdotti(res.data.prodotti || []);
      setStats(res.data.statistiche || {});
    } catch (err) {
      console.error('Errore caricamento magazzino:', err);
    } finally {
      setLoading(false);
    }
  }

  async function loadDettaglioProdotto(prodottoId) {
    try {
      const res = await api.get(`/api/magazzino-dv/prodotti/${prodottoId}`);
      setSelectedProdotto(res.data);
    } catch (err) {
      console.error('Errore caricamento dettaglio:', err);
    }
  }

  // Carica info sui fornitori esclusi
  async function loadFornitoriEsclusi() {
    try {
      const res = await api.get('/api/magazzino-dv/fornitori-esclusi');
      setFornitoriEsclusi(res.data);
    } catch (err) {
      console.error('Errore caricamento fornitori esclusi:', err);
    }
  }

  // Anteprima pulizia magazzino
  async function anteprimaPulizia() {
    setPuliziaInCorso(true);
    try {
      const res = await api.post('/api/magazzino-dv/pulizia-fornitori-esclusi?dry_run=true');
      setFornitoriEsclusi(res.data);
    } catch (err) {
      console.error('Errore anteprima pulizia:', err);
      alert('Errore durante l\'anteprima: ' + (err.response?.data?.detail || err.message));
    } finally {
      setPuliziaInCorso(false);
    }
  }

  // Esegui pulizia effettiva
  async function eseguiPulizia() {
    setPuliziaInCorso(true);
    try {
      const res = await api.post('/api/magazzino-dv/pulizia-fornitori-esclusi?dry_run=false');
      alert(`Pulizia completata! Rimossi ${res.data.totale_prodotti_rimossi} prodotti.`);
      setFornitoriEsclusi(null);
      loadProdotti(); // Ricarica lista prodotti
    } catch (err) {
      console.error('Errore pulizia:', err);
      alert('Errore durante la pulizia: ' + (err.response?.data?.detail || err.message));
    } finally {
      setPuliziaInCorso(false);
    }
  }

  return (
    <PageLayout title="Magazzino Doppia Verità" subtitle="Confronto giacenze teoriche vs reali - Tracciamento differenze inventariali">
    <div style={{ maxWidth: '1400px', margin: '0 auto' }}>
      {/* Header */}
      <div style={{ marginBottom: '24px' }}>
        <h1 style={{ fontSize: '28px', fontWeight: 700, color: '#1f2937', margin: '0 0 8px 0', display: 'flex', alignItems: 'center', gap: '12px' }}>
          📦 Magazzino Doppia Verità
        </h1>
        <p style={{ color: '#6080a0', margin: 0 }}>
          Confronto giacenze teoriche vs reali - Tracciamento differenze inventariali
        </p>
      </div>

      {/* Statistiche */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '16px', marginBottom: '24px' }}>
        <div style={{ background: '#f8fafc', padding: '20px', borderRadius: '12px', border: '1px solid #e2e8f0' }}>
          <div style={{ fontSize: '12px', color: '#64748b', fontWeight: 600 }}>PRODOTTI TOTALI</div>
          <div style={{ fontSize: '28px', fontWeight: 700, color: '#1e293b' }}>{stats.totale_prodotti || 0}</div>
        </div>
        <div style={{ background: '#eff6ff', padding: '20px', borderRadius: '12px', border: '1px solid #93c5fd' }}>
          <div style={{ fontSize: '12px', color: '#1535a8', fontWeight: 600 }}>VALORE TEORICO</div>
          <div style={{ fontSize: '24px', fontWeight: 700, color: '#1535a8' }}>{formatEuro(stats.valore_teorico || 0)}</div>
        </div>
        <div style={{ background: '#f0fdf4', padding: '20px', borderRadius: '12px', border: '1px solid #86efac' }}>
          <div style={{ fontSize: '12px', color: '#16a34a', fontWeight: 600 }}>VALORE REALE</div>
          <div style={{ fontSize: '24px', fontWeight: 700, color: '#15803d' }}>{formatEuro(stats.valore_reale || 0)}</div>
        </div>
        <div style={{ 
          background: (stats.differenza_valore || 0) > 0 ? '#fef2f2' : '#f0fdf4', 
          padding: '20px', 
          borderRadius: '12px', 
          border: `1px solid ${(stats.differenza_valore || 0) > 0 ? '#fecaca' : '#86efac'}` 
        }}>
          <div style={{ fontSize: '12px', color: (stats.differenza_valore || 0) > 0 ? '#dc2626' : '#16a34a', fontWeight: 600 }}>DIFFERENZA</div>
          <div style={{ fontSize: '24px', fontWeight: 700, color: (stats.differenza_valore || 0) > 0 ? '#b91c1c' : '#15803d' }}>
            {formatEuro(stats.differenza_valore || 0)}
          </div>
        </div>
      </div>

      {/* Alert */}
      <div style={{ display: 'flex', gap: '16px', marginBottom: '24px', flexWrap: 'wrap' }}>
        {(stats.prodotti_con_differenze || 0) > 0 && (
          <div style={{ 
            background: '#fef2f2', 
            padding: '12px 16px', 
            borderRadius: '8px', 
            display: 'flex', 
            alignItems: 'center', 
            gap: '8px',
            border: '1px solid #fecaca'
          }}>
            <span style={{ fontSize: 18 }}>⚠️</span>
            <span style={{ color: '#b91c1c', fontWeight: 500 }}>
              {stats.prodotti_con_differenze} prodotti con differenze inventariali
            </span>
          </div>
        )}
        {(stats.prodotti_scorte_basse || 0) > 0 && (
          <div style={{ 
            background: '#fefce8', 
            padding: '12px 16px', 
            borderRadius: '8px', 
            display: 'flex', 
            alignItems: 'center', 
            gap: '8px',
            border: '1px solid #fde047'
          }}>
            <span style={{ fontSize: 18 }}>⚠️</span>
            <span style={{ color: '#a16207', fontWeight: 500 }}>
              {stats.prodotti_scorte_basse} prodotti con scorte basse
            </span>
          </div>
        )}
      </div>

      {/* Filtri - Responsive */}
      <div style={{ display: 'flex', gap: '12px', marginBottom: '24px', flexWrap: 'wrap', alignItems: 'center' }}>
        <div style={{ position: 'relative', flex: 1, minWidth: '150px', maxWidth: '300px' }}>
          <span style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', fontSize: 16 }}>🔍</span>
          <input
            type="text"
            placeholder="Cerca prodotto..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{
              width: '100%',
              padding: '10px 10px 10px 36px',
              border: '1px solid #dce8f4',
              borderRadius: '8px',
              fontSize: '14px'
            }}
            data-testid="search-prodotti"
          />
        </div>
        <label style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer', fontSize: '13px' }}>
          <input
            type="checkbox"
            checked={soloDifferenze}
            onChange={(e) => setSoloDifferenze(e.target.checked)}
          />
          <span style={{ color: '#374151' }}>Differenze</span>
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer', fontSize: '13px' }}>
          <input
            type="checkbox"
            checked={soloScorteBasse}
            onChange={(e) => setSoloScorteBasse(e.target.checked)}
          />
          <span style={{ color: '#374151' }}>Scorte basse</span>
        </label>
        <button
          onClick={loadProdotti}
          style={{
            padding: '8px 14px',
            background: '#f3f4f6',
            border: '1px solid #dce8f4',
            borderRadius: '8px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            fontSize: '13px'
          }}
        >
          🔄 Aggiorna
        </button>
        <button
          onClick={anteprimaPulizia}
          disabled={puliziaInCorso}
          style={{
            padding: '8px 14px',
            background: '#fef2f2',
            border: '1px solid #fecaca',
            borderRadius: '8px',
            cursor: puliziaInCorso ? 'not-allowed' : 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            fontSize: '13px',
            color: '#dc2626'
          }}
          data-testid="btn-pulizia-magazzino"
        >
          🗑️ Pulizia
        </button>
      </div>

      {/* Pannello Pulizia Fornitori Esclusi */}
      {fornitoriEsclusi && (
        <div style={{ 
          marginBottom: '24px', 
          padding: '20px', 
          background: '#fef2f2', 
          borderRadius: '12px', 
          border: '1px solid #fecaca' 
        }}>
          <h3 style={{ margin: '0 0 12px 0', fontSize: '16px', fontWeight: 600, color: '#dc2626', display: 'flex', alignItems: 'center', gap: '8px' }}>
            🗑️ Pulizia Prodotti da Fornitori Esclusi
          </h3>
          
          {fornitoriEsclusi.fornitori_esclusi === 0 ? (
            <p style={{ color: '#6080a0', margin: 0 }}>
              Nessun fornitore con flag "Esclude Magazzino" attivo. 
              Per escludere un fornitore, vai nella pagina <strong>Fornitori</strong> e attiva il checkbox "Esclude dal Magazzino".
            </p>
          ) : (
            <>
              <p style={{ color: '#374151', margin: '0 0 16px 0' }}>
                <strong>{fornitoriEsclusi.fornitori_esclusi}</strong> fornitori esclusi dal magazzino. 
                <strong style={{ color: '#dc2626' }}> {fornitoriEsclusi.totale_prodotti || 0}</strong> prodotti verranno rimossi.
              </p>
              
              {fornitoriEsclusi.fornitori_dettaglio?.length > 0 && (
                <div style={{ marginBottom: '16px' }}>
                  <div style={{ fontSize: '13px', fontWeight: 600, color: '#374151', marginBottom: '8px' }}>Fornitori coinvolti:</div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                    {fornitoriEsclusi.fornitori_dettaglio.map((f, i) => (
                      <span key={i} style={{
                        padding: '4px 12px',
                        background: '#fee2e2',
                        borderRadius: '6px',
                        fontSize: '13px',
                        color: '#b91c1c'
                      }}>
                        {f.nome}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              
              {fornitoriEsclusi.anteprima_prodotti?.length > 0 && (
                <div style={{ marginBottom: '16px' }}>
                  <div style={{ fontSize: '13px', fontWeight: 600, color: '#374151', marginBottom: '8px' }}>
                    Anteprima prodotti da rimuovere (primi 50):
                  </div>
                  <div style={{ 
                    maxHeight: '150px', 
                    overflowY: 'auto', 
                    background: 'white', 
                    borderRadius: '8px', 
                    padding: '12px',
                    border: '1px solid #fecaca'
                  }}>
                    {fornitoriEsclusi.anteprima_prodotti.map((p, i) => (
                      <div key={i} style={{ 
                        padding: '4px 0', 
                        borderBottom: i < fornitoriEsclusi.anteprima_prodotti.length - 1 ? '1px solid #f3f4f6' : 'none',
                        fontSize: '13px',
                        color: '#374151'
                      }}>
                        <strong>{p.nome}</strong> - {p.fornitore} (giac: {p.giacenza})
                      </div>
                    ))}
                  </div>
                </div>
              )}
              
              <div style={{ display: 'flex', gap: '12px' }}>
                <button
                  onClick={eseguiPulizia}
                  disabled={puliziaInCorso || (fornitoriEsclusi.totale_prodotti || 0) === 0}
                  style={{
                    padding: '10px 20px',
                    background: '#dc2626',
                    border: 'none',
                    borderRadius: '8px',
                    color: 'white',
                    cursor: puliziaInCorso || (fornitoriEsclusi.totale_prodotti || 0) === 0 ? 'not-allowed' : 'pointer',
                    fontWeight: 600,
                    opacity: puliziaInCorso || (fornitoriEsclusi.totale_prodotti || 0) === 0 ? 0.5 : 1
                  }}
                  data-testid="btn-conferma-pulizia"
                >
                  {puliziaInCorso ? 'Pulizia in corso...' : 'Conferma Rimozione'}
                </button>
                <button
                  onClick={() => setFornitoriEsclusi(null)}
                  style={{
                    padding: '10px 20px',
                    background: 'white',
                    border: '1px solid #dce8f4',
                    borderRadius: '8px',
                    cursor: 'pointer'
                  }}
                >
                  Annulla
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {/* Tabella/Cards Prodotti */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: '40px', color: '#6080a0' }}>Caricamento...</div>
      ) : (
        <>
          {/* MOBILE CARDS VIEW */}
          <style>{`
            @media (min-width: 768px) {
              .mobile-cards-magazzino { display: none !important; }
              .desktop-table-magazzino { display: block !important; }
            }
            @media (max-width: 767px) {
              .mobile-cards-magazzino { display: block !important; }
              .desktop-table-magazzino { display: none !important; }
            }
          `}</style>
          
          <div className="mobile-cards-magazzino" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {prodotti.length === 0 ? (
              <div style={{ padding: '40px', textAlign: 'center', color: '#6080a0', background: 'white', borderRadius: 12 }}>
                Nessun prodotto trovato
              </div>
            ) : (
              prodotti.map((p, i) => {
                const diff = (p.giacenza_teorica || 0) - (p.giacenza_reale || 0);
                const hasDiff = diff !== 0;
                const scortaBassa = (p.giacenza_teorica || 0) <= (p.scorta_minima || 0);
                
                return (
                  <div 
                    key={p.id || i}
                    onClick={() => loadDettaglioProdotto(p.id)}
                    style={{
                      background: hasDiff ? '#fef2f2' : (scortaBassa ? '#fefce8' : 'white'),
                      borderRadius: 12,
                      padding: 14,
                      border: '1px solid #dce8f4',
                      cursor: 'pointer'
                    }}
                  >
                    {/* Row 1: Nome + Stato */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontWeight: 600, color: '#1f2937', fontSize: 14, marginBottom: 2 }}>
                          {p.nome}
                        </div>
                        <div style={{ fontSize: 12, color: '#6080a0' }}>
                          {p.categoria || 'N/D'} • {p.fornitore || 'Fornitore n/d'}
                        </div>
                      </div>
                      {hasDiff ? (
                        <span style={{ background: '#fecaca', color: '#b91c1c', padding: '4px 8px', borderRadius: 6, fontSize: 10, fontWeight: 600 }}>
                          DIFF
                        </span>
                      ) : scortaBassa ? (
                        <span style={{ background: '#fde047', color: '#a16207', padding: '4px 8px', borderRadius: 6, fontSize: 10, fontWeight: 600 }}>
                          BASSO
                        </span>
                      ) : (
                        <span style={{ background: '#dcfce7', color: '#16a34a', padding: '4px 8px', borderRadius: 6, fontSize: 10, fontWeight: 600 }}>
                          OK
                        </span>
                      )}
                    </div>
                    
                    {/* Row 2: Giacenze */}
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
                      <div style={{ textAlign: 'center', padding: '8px 4px', background: 'rgba(37, 99, 235, 0.1)', borderRadius: 6 }}>
                        <div style={{ fontSize: 11, color: '#6080a0', marginBottom: 2 }}>Teorica</div>
                        <div style={{ fontWeight: 600, color: '#1535a8', fontSize: 14 }}>
                          {(p.giacenza_teorica || 0).toFixed(1)}
                        </div>
                      </div>
                      <div style={{ textAlign: 'center', padding: '8px 4px', background: 'rgba(22, 163, 74, 0.1)', borderRadius: 6 }}>
                        <div style={{ fontSize: 11, color: '#6080a0', marginBottom: 2 }}>Reale</div>
                        <div style={{ fontWeight: 600, color: '#16a34a', fontSize: 14 }}>
                          {(p.giacenza_reale || 0).toFixed(1)}
                        </div>
                      </div>
                      <div style={{ textAlign: 'center', padding: '8px 4px', background: diff !== 0 ? 'rgba(220, 38, 38, 0.1)' : 'rgba(107, 114, 128, 0.1)', borderRadius: 6 }}>
                        <div style={{ fontSize: 11, color: '#6080a0', marginBottom: 2 }}>Diff.</div>
                        <div style={{ fontWeight: 600, color: diff > 0 ? '#dc2626' : (diff < 0 ? '#16a34a' : '#6080a0'), fontSize: 14 }}>
                          {diff > 0 ? '+' : ''}{diff.toFixed(1)}
                        </div>
                      </div>
                    </div>
                    
                    {/* Row 3: Costo */}
                    <div style={{ marginTop: 8, fontSize: 12, color: '#6080a0', display: 'flex', justifyContent: 'space-between' }}>
                      <span>Costo medio: <strong style={{ color: '#374151' }}>{formatEuro(p.costo_medio || 0)}</strong></span>
                      <span>{p.unita || 'pz'}</span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
          
          {/* DESKTOP TABLE VIEW */}
          <div className="desktop-table-magazzino" style={{ background: 'white', borderRadius: '12px', border: '1px solid #dce8f4', overflow: 'hidden' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ background: '#f8fafc' }}>
                  <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 600, fontSize: '13px', color: '#374151' }}>Prodotto</th>
                  <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 600, fontSize: '13px', color: '#374151' }}>Categoria</th>
                  <th style={{ padding: '12px 16px', textAlign: 'right', fontWeight: 600, fontSize: '13px', color: '#374151' }}>Giac. Teorica</th>
                  <th style={{ padding: '12px 16px', textAlign: 'right', fontWeight: 600, fontSize: '13px', color: '#374151' }}>Giac. Reale</th>
                  <th style={{ padding: '12px 16px', textAlign: 'right', fontWeight: 600, fontSize: '13px', color: '#374151' }}>Differenza</th>
                  <th style={{ padding: '12px 16px', textAlign: 'right', fontWeight: 600, fontSize: '13px', color: '#374151' }}>Costo Medio</th>
                  <th style={{ padding: '12px 16px', textAlign: 'center', fontWeight: 600, fontSize: '13px', color: '#374151' }}>Stato</th>
                </tr>
              </thead>
              <tbody>
                {prodotti.map((p, i) => {
                  const diff = (p.giacenza_teorica || 0) - (p.giacenza_reale || 0);
                  const hasDiff = diff !== 0;
                  const scortaBassa = (p.giacenza_teorica || 0) <= (p.scorta_minima || 0);
                  
                  return (
                    <tr 
                      key={p.id || i} 
                      style={{ 
                        borderBottom: '1px solid #f3f4f6',
                        background: hasDiff ? '#fef2f2' : (scortaBassa ? '#fefce8' : 'white'),
                        cursor: 'pointer'
                      }}
                      onClick={() => loadDettaglioProdotto(p.id)}
                    >
                      <td style={{ padding: '12px 16px', fontSize: '14px', fontWeight: 500, color: '#1f2937' }}>
                        {p.nome}
                      </td>
                      <td style={{ padding: '12px 16px', fontSize: '13px', color: '#6080a0' }}>
                        {p.categoria || '-'}
                      </td>
                      <td style={{ padding: '12px 16px', textAlign: 'right', fontSize: '14px', color: '#1535a8', fontWeight: 600 }}>
                        {(p.giacenza_teorica || 0).toFixed(2)} {p.unita || ''}
                      </td>
                      <td style={{ padding: '12px 16px', textAlign: 'right', fontSize: '14px', color: '#16a34a', fontWeight: 600 }}>
                        {(p.giacenza_reale || 0).toFixed(2)} {p.unita || ''}
                      </td>
                      <td style={{ 
                        padding: '12px 16px', 
                        textAlign: 'right', 
                        fontSize: '14px', 
                        fontWeight: 600,
                        color: diff > 0 ? '#dc2626' : (diff < 0 ? '#16a34a' : '#6080a0')
                      }}>
                        {diff > 0 ? '+' : ''}{diff.toFixed(2)}
                      </td>
                      <td style={{ padding: '12px 16px', textAlign: 'right', fontSize: '14px', color: '#374151' }}>
                        {formatEuro(p.costo_medio || 0)}
                      </td>
                      <td style={{ padding: '12px 16px', textAlign: 'center' }}>
                        {hasDiff ? (
                          <span style={{ background: '#fecaca', color: '#b91c1c', padding: '4px 8px', borderRadius: '6px', fontSize: '11px', fontWeight: 600 }}>
                            DIFF
                          </span>
                        ) : scortaBassa ? (
                          <span style={{ background: '#fde047', color: '#a16207', padding: '4px 8px', borderRadius: '6px', fontSize: '11px', fontWeight: 600 }}>
                            BASSO
                          </span>
                        ) : (
                          <span style={{ background: '#dcfce7', color: '#16a34a', padding: '4px 8px', borderRadius: '6px', fontSize: '11px', fontWeight: 600 }}>
                            OK
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            
            {prodotti.length === 0 && (
              <div style={{ padding: '40px', textAlign: 'center', color: '#6080a0' }}>
                Nessun prodotto trovato
              </div>
            )}
          </div>
        </>
      )}

      {/* Modal Dettaglio */}
      {selectedProdotto && (
        <ProdottoDetailModal 
          prodotto={selectedProdotto} 
          onClose={() => setSelectedProdotto(null)} 
        />
      )}
    </div>
    </PageLayout>
  );
}

function ProdottoDetailModal({ prodotto, onClose }) {
  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      background: 'rgba(0,0,0,0.5)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 9999,
      padding: '20px'
    }} onClick={onClose}>
      <div 
        style={{
          background: 'white',
          borderRadius: '16px',
          width: '100%',
          maxWidth: '500px',
          maxHeight: '80vh',
          overflow: 'auto'
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ padding: '24px', borderBottom: '1px solid #dce8f4' }}>
          <h2 style={{ fontSize: '20px', fontWeight: 700, color: '#1f2937', margin: 0 }}>
            {prodotto.nome}
          </h2>
          <p style={{ color: '#6080a0', margin: '4px 0 0 0' }}>
            {prodotto.categoria} - {prodotto.fornitore || 'Fornitore n/d'}
          </p>
        </div>
        
        <div style={{ padding: '24px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '24px' }}>
            <div style={{ background: '#eff6ff', padding: '16px', borderRadius: '8px' }}>
              <div style={{ fontSize: '12px', color: '#1535a8', fontWeight: 600 }}>Giacenza Teorica</div>
              <div style={{ fontSize: '24px', fontWeight: 700, color: '#1535a8' }}>
                {(prodotto.giacenza_teorica || 0).toFixed(2)} {prodotto.unita}
              </div>
            </div>
            <div style={{ background: '#f0fdf4', padding: '16px', borderRadius: '8px' }}>
              <div style={{ fontSize: '12px', color: '#16a34a', fontWeight: 600 }}>Giacenza Reale</div>
              <div style={{ fontSize: '24px', fontWeight: 700, color: '#15803d' }}>
                {(prodotto.giacenza_reale || 0).toFixed(2)} {prodotto.unita}
              </div>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '12px' }}>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '11px', color: '#6080a0' }}>Costo Medio</div>
              <div style={{ fontSize: '16px', fontWeight: 600, color: '#1f2937' }}>{formatEuro(prodotto.costo_medio || 0)}</div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '11px', color: '#6080a0' }}>Scorta Minima</div>
              <div style={{ fontSize: '16px', fontWeight: 600, color: '#1f2937' }}>{prodotto.scorta_minima || 0}</div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '11px', color: '#6080a0' }}>Ultimo Aggiorn.</div>
              <div style={{ fontSize: '14px', fontWeight: 500, color: '#6080a0' }}>
                {prodotto.updated_at ? formatDateIT(prodotto.updated_at) : '-'}
              </div>
            </div>
          </div>
        </div>

        <div style={{ padding: '16px 24px', borderTop: '1px solid #dce8f4', display: 'flex', justifyContent: 'flex-end' }}>
          <button
            onClick={onClose}
            style={{
              padding: '10px 20px',
              background: '#f3f4f6',
              border: 'none',
              borderRadius: '8px',
              cursor: 'pointer',
              fontSize: '14px',
              fontWeight: 500
            }}
          >
            Chiudi
          </button>
        </div>
      </div>
    </div>
  );
}
