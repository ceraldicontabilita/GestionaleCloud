import React, { useState, useEffect } from 'react';
import api from '../api';
import { formatEuro } from '../lib/utils';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { PageLayout, PageSection, PageGrid, PageLoading } from '../components/PageLayout';
import { Target, TrendingUp, TrendingDown, Save, Calculator, BarChart3 } from 'lucide-react';

export default function UtileObiettivo() {
  const { anno } = useAnnoGlobale();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [settings, setSettings] = useState({ target_utile: 0, margine_atteso: 0.15 });
  const [status, setStatus] = useState(null);

  useEffect(() => {
    loadStatus();
  }, [anno]);

  async function loadStatus() {
    setLoading(true);
    try {
      const res = await api.get(`/api/centri-costo/utile-obiettivo?anno=${anno}`);
      const data = res.data;
      
      setStatus({
        target_utile: data.target?.utile_target_annuo || 0,
        margine_atteso: data.target?.margine_medio_atteso || 0.15,
        ricavi_totali: data.reale?.ricavi_totali || 0,
        costi_totali: data.reale?.costi_totali || 0,
        utile_attuale: data.reale?.utile_corrente || 0,
        percentuale_raggiungimento: Math.max(0, data.analisi?.percentuale_raggiungimento || 0),
        gap_da_colmare: Math.abs(data.analisi?.scostamento_ad_oggi || 0),
        per_centro_costo: {}
      });
      setSettings({
        target_utile: data.target?.utile_target_annuo || 0,
        margine_atteso: data.target?.margine_medio_atteso || 0.15
      });
    } catch (err) {
      console.error('Errore caricamento status:', err);
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }

  async function saveTarget() {
    setSaving(true);
    try {
      await api.post('/api/centri-costo/utile-obiettivo', {
        anno,
        utile_target_annuo: settings.target_utile,
        margine_medio_atteso: settings.margine_atteso
      });
      loadStatus();
    } catch (err) {
      alert('Errore salvataggio: ' + (err.response?.data?.detail || err.message));
    } finally {
      setSaving(false);
    }
  }

  const percentualeRaggiungimento = status?.percentuale_raggiungimento || 0;
  const isOnTrack = percentualeRaggiungimento >= 80;
  const isAtRisk = percentualeRaggiungimento >= 50 && percentualeRaggiungimento < 80;
  const progressColor = isOnTrack ? '#16a34a' : (isAtRisk ? '#ca8a04' : '#dc2626');

  const MetricCard = ({ label, value, icon: Icon, color, bgColor }) => (
    <div style={{ 
      background: bgColor, 
      padding: 20, 
      borderRadius: 12,
      border: `1px solid ${color}22`
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <Icon size={20} color={color} />
        <span style={{ fontSize: 13, color: '#6080a0', fontWeight: 500 }}>{label}</span>
      </div>
      <div style={{ fontSize: 24, fontWeight: 700, color }}>{value}</div>
    </div>
  );

  return (
    <PageLayout
      title={`Utile Obiettivo ${anno}`}
      icon={<Target size={28} />}
      subtitle="Monitoraggio in tempo reale del raggiungimento degli obiettivi di profitto"
    >
      {loading ? (
        <PageLoading message="Caricamento dati obiettivo..." />
      ) : (
        <>
          {/* Impostazioni Target */}
          <PageSection title="Impostazioni Target" icon={<Calculator size={18} />}>
            <PageGrid cols={3} gap={20}>
              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 500, color: '#374151', marginBottom: 6 }}>
                  Target Utile Annuale (€)
                </label>
                <input
                  type="number"
                  value={settings.target_utile}
                  onChange={(e) => setSettings(s => ({ ...s, target_utile: parseFloat(e.target.value) || 0 }))}
                  style={{
                    width: '100%',
                    padding: 12,
                    border: '1px solid #dce8f4',
                    borderRadius: 8,
                    fontSize: 16,
                    fontWeight: 600
                  }}
                  data-testid="input-target-utile"
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 500, color: '#374151', marginBottom: 6 }}>
                  Margine Atteso (%)
                </label>
                <input
                  type="number"
                  value={(settings.margine_atteso * 100).toFixed(0)}
                  onChange={(e) => setSettings(s => ({ ...s, margine_atteso: (parseFloat(e.target.value) || 0) / 100 }))}
                  style={{
                    width: '100%',
                    padding: 12,
                    border: '1px solid #dce8f4',
                    borderRadius: 8,
                    fontSize: 16,
                    fontWeight: 600
                  }}
                  data-testid="input-margine"
                />
              </div>
              <div style={{ display: 'flex', alignItems: 'flex-end' }}>
                <button
                  onClick={saveTarget}
                  disabled={saving}
                  data-testid="save-target-btn"
                  style={{
                    padding: '12px 24px',
                    background: 'linear-gradient(135deg, #1535a8 0%, #2050e8 100%)',
                    color: 'white',
                    border: 'none',
                    borderRadius: 8,
                    cursor: saving ? 'not-allowed' : 'pointer',
                    fontSize: 14,
                    fontWeight: 600,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    opacity: saving ? 0.7 : 1
                  }}
                >
                  <Save size={16} />
                  {saving ? 'Salvataggio...' : 'Salva Target'}
                </button>
              </div>
            </PageGrid>
          </PageSection>

          {/* Status Card */}
          {status && (
            <>
              {/* Barra Progresso Principale */}
              <PageSection title="Raggiungimento Obiettivo" style={{ marginTop: 24 }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
                  <div>
                    <div style={{ fontSize: 14, color: '#6080a0', marginBottom: 4 }}>Percentuale</div>
                    <div style={{ fontSize: 48, fontWeight: 700, color: progressColor }}>
                      {percentualeRaggiungimento.toFixed(1)}%
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: 14, color: '#6080a0', marginBottom: 4 }}>Target</div>
                    <div style={{ fontSize: 32, fontWeight: 700, color: '#1f2937' }}>
                      {formatEuro(status.target_utile || 0)}
                    </div>
                  </div>
                </div>
                
                {/* Progress Bar */}
                <div style={{ background: '#f3f4f6', borderRadius: 12, height: 24, overflow: 'hidden', marginBottom: 16 }}>
                  <div
                    style={{
                      width: `${Math.min(percentualeRaggiungimento, 100)}%`,
                      height: '100%',
                      background: `linear-gradient(90deg, ${progressColor}, ${progressColor}dd)`,
                      borderRadius: 12,
                      transition: 'width 0.5s ease'
                    }}
                  />
                </div>

                {/* Status Badge */}
                <div style={{ display: 'flex', justifyContent: 'center' }}>
                  <span style={{
                    background: isOnTrack ? '#dcfce7' : (isAtRisk ? '#fef3c7' : '#fef2f2'),
                    color: progressColor,
                    padding: '8px 20px',
                    borderRadius: 20,
                    fontSize: 14,
                    fontWeight: 600,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8
                  }}>
                    {isOnTrack ? <TrendingUp size={18} /> : (isAtRisk ? <BarChart3 size={18} /> : <TrendingDown size={18} />)}
                    {isOnTrack ? 'In linea con obiettivo' : (isAtRisk ? 'Attenzione richiesta' : 'Sotto obiettivo')}
                  </span>
                </div>
              </PageSection>

              {/* Metriche Dettagliate */}
              <div style={{ marginTop: 24 }}>
                <PageGrid cols={4} gap={16}>
                  <MetricCard
                    label="Ricavi Totali"
                    value={formatEuro(status.ricavi_totali || 0)}
                    icon={TrendingUp}
                    color="#16a34a"
                    bgColor="#f0fdf4"
                  />
                  <MetricCard
                    label="Costi Totali"
                    value={formatEuro(status.costi_totali || 0)}
                    icon={TrendingDown}
                    color="#dc2626"
                    bgColor="#fef2f2"
                  />
                  <MetricCard
                    label="Utile Attuale"
                    value={formatEuro(status.utile_attuale || 0)}
                    icon={Target}
                    color={(status.utile_attuale || 0) >= 0 ? '#16a34a' : '#dc2626'}
                    bgColor={(status.utile_attuale || 0) >= 0 ? '#f0fdf4' : '#fef2f2'}
                  />
                  <MetricCard
                    label="Gap da Colmare"
                    value={formatEuro(status.gap_da_colmare || 0)}
                    icon={BarChart3}
                    color={(status.gap_da_colmare || 0) > 0 ? '#ca8a04' : '#16a34a'}
                    bgColor={(status.gap_da_colmare || 0) > 0 ? '#fefce8' : '#f0fdf4'}
                  />
                </PageGrid>
              </div>

              {/* Distribuzione per CDC */}
              {status.per_centro_costo && Object.keys(status.per_centro_costo).length > 0 && (
                <PageSection title="Distribuzione per Centro di Costo" style={{ marginTop: 24 }}>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 12 }}>
                    {Object.entries(status.per_centro_costo).map(([cdc, data]) => (
                      <div key={cdc} style={{ 
                        background: '#f8fafc', 
                        padding: 16, 
                        borderRadius: 8,
                        border: '1px solid #e2e8f0'
                      }}>
                        <div style={{ fontSize: 11, color: '#64748b', fontWeight: 600 }}>{cdc}</div>
                        <div style={{ fontSize: 18, fontWeight: 700, color: '#1e293b' }}>
                          {formatEuro(data.totale || 0)}
                        </div>
                        <div style={{ fontSize: 12, color: '#6080a0' }}>
                          {data.count || 0} fatture
                        </div>
                      </div>
                    ))}
                  </div>
                </PageSection>
              )}
            </>
          )}
        </>
      )}
    </PageLayout>
  );
}
