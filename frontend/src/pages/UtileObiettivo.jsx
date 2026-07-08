import React, { useState, useEffect } from 'react';
import { toast } from 'sonner';
import api from '../api';
import { formatEuro, COLORS, BORDER_RADIUS, FONT } from '../lib/utils';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { PageLayout, PageSection, PageGrid, PageLoading } from '../components/PageLayout';
import { Button, Badge, StatCard, Input } from '../components/ds';
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
        per_centro_costo: {},
      });
      setSettings({
        target_utile: data.target?.utile_target_annuo || 0,
        margine_atteso: data.target?.margine_medio_atteso || 0.15,
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
        margine_medio_atteso: settings.margine_atteso,
      });
      loadStatus();
    } catch (err) {
      toast.error('Errore salvataggio: ' + (err.response?.data?.detail || err.message));
    } finally {
      setSaving(false);
    }
  }

  const percentualeRaggiungimento = status?.percentuale_raggiungimento || 0;
  const isOnTrack = percentualeRaggiungimento >= 80;
  const isAtRisk = percentualeRaggiungimento >= 50 && percentualeRaggiungimento < 80;
  const progressColor = isOnTrack ? COLORS.success : isAtRisk ? COLORS.warning : COLORS.danger;
  const progressVariant = isOnTrack ? 'success' : isAtRisk ? 'warning' : 'danger';

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
                <label
                  style={{
                    display: 'block',
                    fontSize: 13,
                    fontWeight: 500,
                    color: COLORS.gray[700],
                    marginBottom: 6,
                  }}
                >
                  Target Utile Annuale (€)
                </label>
                <Input
                  type="number"
                  value={settings.target_utile}
                  onChange={e =>
                    setSettings(s => ({ ...s, target_utile: parseFloat(e.target.value) || 0 }))
                  }
                  style={{ padding: 12, fontSize: 16, fontWeight: 600 }}
                  data-testid="input-target-utile"
                />
              </div>
              <div>
                <label
                  style={{
                    display: 'block',
                    fontSize: 13,
                    fontWeight: 500,
                    color: COLORS.gray[700],
                    marginBottom: 6,
                  }}
                >
                  Margine Atteso (%)
                </label>
                <Input
                  type="number"
                  value={(settings.margine_atteso * 100).toFixed(0)}
                  onChange={e =>
                    setSettings(s => ({
                      ...s,
                      margine_atteso: (parseFloat(e.target.value) || 0) / 100,
                    }))
                  }
                  style={{ padding: 12, fontSize: 16, fontWeight: 600 }}
                  data-testid="input-margine"
                />
              </div>
              <div style={{ display: 'flex', alignItems: 'flex-end' }}>
                <Button
                  variant="primary"
                  size="lg"
                  onClick={saveTarget}
                  disabled={saving}
                  data-testid="save-target-btn"
                  iconLeft={<Save size={16} />}
                  style={{ minHeight: 40 }}
                >
                  {saving ? 'Salvataggio...' : 'Salva Target'}
                </Button>
              </div>
            </PageGrid>
          </PageSection>

          {/* Status Card */}
          {status && (
            <>
              {/* Barra Progresso Principale */}
              <PageSection title="Raggiungimento Obiettivo" style={{ marginTop: 24 }}>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    flexWrap: 'wrap',
                    gap: 12,
                    marginBottom: 24,
                  }}
                >
                  <div>
                    <div style={{ fontSize: 14, color: COLORS.textMuted, marginBottom: 4 }}>
                      Percentuale
                    </div>
                    <div style={{ fontSize: 48, fontWeight: 700, color: progressColor, fontFamily: FONT.mono }}>
                      {percentualeRaggiungimento.toFixed(1)}%
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: 14, color: COLORS.textMuted, marginBottom: 4 }}>Target</div>
                    <div style={{ fontSize: 32, fontWeight: 700, color: COLORS.gray[800], fontFamily: FONT.mono }}>
                      {formatEuro(status.target_utile || 0)}
                    </div>
                  </div>
                </div>

                {/* Progress Bar */}
                <div
                  style={{
                    background: COLORS.bg,
                    borderRadius: BORDER_RADIUS.md,
                    height: 24,
                    overflow: 'hidden',
                    marginBottom: 16,
                  }}
                >
                  <div
                    style={{
                      width: `${Math.min(percentualeRaggiungimento, 100)}%`,
                      height: '100%',
                      background: progressColor,
                      borderRadius: BORDER_RADIUS.md,
                      transition: 'width 0.5s ease',
                    }}
                  />
                </div>

                {/* Status Badge */}
                <div style={{ display: 'flex', justifyContent: 'center' }}>
                  <Badge
                    variant={progressVariant}
                    style={{
                      padding: '8px 20px',
                      borderRadius: BORDER_RADIUS.md,
                      fontSize: 14,
                      textTransform: 'none',
                      letterSpacing: 'normal',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                    }}
                  >
                    {isOnTrack ? (
                      <TrendingUp size={18} />
                    ) : isAtRisk ? (
                      <BarChart3 size={18} />
                    ) : (
                      <TrendingDown size={18} />
                    )}
                    {isOnTrack
                      ? 'In linea con obiettivo'
                      : isAtRisk
                        ? 'Attenzione richiesta'
                        : 'Sotto obiettivo'}
                  </Badge>
                </div>
              </PageSection>

              {/* Metriche Dettagliate */}
              <div style={{ marginTop: 24 }}>
                <PageGrid cols={4} gap={16}>
                  <StatCard
                    label="Ricavi Totali"
                    value={formatEuro(status.ricavi_totali || 0)}
                    icon={<TrendingUp size={18} />}
                    accent="success"
                  />
                  <StatCard
                    label="Costi Totali"
                    value={formatEuro(status.costi_totali || 0)}
                    icon={<TrendingDown size={18} />}
                    accent="danger"
                  />
                  <StatCard
                    label="Utile Attuale"
                    value={formatEuro(status.utile_attuale || 0)}
                    icon={<Target size={18} />}
                    accent={(status.utile_attuale || 0) >= 0 ? 'success' : 'danger'}
                  />
                  <StatCard
                    label="Gap da Colmare"
                    value={formatEuro(status.gap_da_colmare || 0)}
                    icon={<BarChart3 size={18} />}
                    accent={(status.gap_da_colmare || 0) > 0 ? 'warning' : 'success'}
                  />
                </PageGrid>
              </div>

              {/* Distribuzione per CDC */}
              {status.per_centro_costo && Object.keys(status.per_centro_costo).length > 0 && (
                <PageSection title="Distribuzione per Centro di Costo" style={{ marginTop: 24 }}>
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
                      gap: 12,
                    }}
                  >
                    {Object.entries(status.per_centro_costo).map(([cdc, data]) => (
                      <StatCard
                        key={cdc}
                        label={cdc}
                        value={formatEuro(data.totale || 0)}
                        subtext={`${data.count || 0} fatture`}
                        accent="none"
                      />
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
