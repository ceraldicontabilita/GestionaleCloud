import React, { useState, useEffect } from 'react';
import { toast } from 'sonner';
import api from '../api';
import { formatEuro, COLORS, BORDER_RADIUS, FONT } from '../lib/utils';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { PageLayout, PageSection, PageGrid, PageLoading } from '../components/PageLayout';
import { Button, Badge, StatCard, Input } from '../components/ds';
import { Target, TrendingUp, TrendingDown, Save, Calculator, BarChart3 } from 'lucide-react';

export const DATO_NON_DISPONIBILE = 'Dato non disponibile';

/** Importo in euro, oppure «Dato non disponibile» se il backend non lo sa. */
export function euroODato(valore) {
  return valore == null ? DATO_NON_DISPONIBILE : formatEuro(valore);
}

/**
 * Stato della pagina dalla risposta del backend. Nessun ripiego numerico:
 * senza target configurato il target e' null (prima il backend inventava
 * 50.000 € e la pagina un margine del 15%), senza costo del personale
 * costi e utile sono null.
 */
export function statoDaRisposta(data) {
  const target = data?.target || {};
  const reale = data?.reale || {};
  const analisi = data?.analisi || {};
  return {
    configurato: Boolean(target.configurato),
    target_utile: target.utile_target_annuo ?? null,
    margine_atteso: target.margine_medio_atteso ?? null,
    ricavi_totali: reale.ricavi_totali ?? null,
    costi_totali: reale.costi_totali ?? null,
    utile_attuale: reale.utile_corrente ?? null,
    personale_motivo: reale.personale_motivo ?? null,
    percentuale_raggiungimento: analisi.percentuale_target_annuo ?? null,
    gap_da_colmare: analisi.gap_target_annuo ?? null,
    surplus_target: analisi.surplus_target_annuo ?? null,
    per_centro_costo: {},
  };
}

export default function UtileObiettivo() {
  const { anno } = useAnnoGlobale();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [settings, setSettings] = useState({ target_utile: '', margine_atteso: null });
  const [status, setStatus] = useState(null);

  useEffect(() => {
    loadStatus();
  }, [anno]);

  async function loadStatus() {
    setLoading(true);
    try {
      const res = await api.get(`/api/centri-costo/utile-obiettivo?anno=${anno}`);
      const nuovo = statoDaRisposta(res.data);
      setStatus(nuovo);
      setSettings({
        target_utile: nuovo.target_utile ?? '',
        margine_atteso: nuovo.margine_atteso,
      });
    } catch (err) {
      console.error('Errore caricamento status:', err);
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }

  async function saveTarget() {
    const target = parseFloat(settings.target_utile);
    if (!Number.isFinite(target)) {
      toast.error('Indica il target di utile annuale prima di salvare');
      return;
    }
    setSaving(true);
    try {
      await api.post('/api/centri-costo/utile-obiettivo', {
        anno,
        utile_target_annuo: target,
        margine_medio_atteso: settings.margine_atteso,
      });
      loadStatus();
    } catch (err) {
      toast.error('Errore salvataggio: ' + (err.response?.data?.detail || err.message));
    } finally {
      setSaving(false);
    }
  }

  const percentualeRaggiungimento = status?.percentuale_raggiungimento ?? null;
  const confrontabile = status?.configurato && percentualeRaggiungimento != null;
  const isOnTrack = confrontabile && status?.gap_da_colmare === 0 && status?.target_utile > 0;
  const isAtRisk = confrontabile && !isOnTrack && percentualeRaggiungimento >= 50;
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
                  placeholder="Da impostare"
                  onChange={e => setSettings(s => ({ ...s, target_utile: e.target.value }))}
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
                  value={settings.margine_atteso == null ? '' : (settings.margine_atteso * 100).toFixed(0)}
                  placeholder="Da impostare"
                  onChange={e =>
                    setSettings(s => ({
                      ...s,
                      margine_atteso:
                        e.target.value === '' ? null : (parseFloat(e.target.value) || 0) / 100,
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
              {!confrontabile && (
                <PageSection title="Raggiungimento Obiettivo" style={{ marginTop: 24 }}>
                  <div data-testid="utile-obiettivo-non-confrontabile" style={{ color: COLORS.textMuted, fontSize: 14 }}>
                    {!status.configurato
                      ? 'Nessun target impostato per quest\'anno: indica il target di utile per confrontarlo con il risultato.'
                      : `${DATO_NON_DISPONIBILE}: utile non calcolabile${
                          status.personale_motivo ? ` (${status.personale_motivo})` : ''
                        }.`}
                  </div>
                </PageSection>
              )}
              {/* Barra Progresso Principale */}
              {confrontabile && (
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
                      {euroODato(status.target_utile)}
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
                      width: `${Math.max(0, Math.min(percentualeRaggiungimento, 100))}%`,
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
                      ? `Obiettivo raggiunto${status.surplus_target > 0 ? ` · Superato di ${formatEuro(status.surplus_target)}` : ''}`
                      : isAtRisk
                        ? 'Attenzione richiesta'
                        : 'Sotto obiettivo'}
                  </Badge>
                </div>
              </PageSection>
              )}

              {/* Metriche Dettagliate */}
              <div style={{ marginTop: 24 }}>
                <PageGrid cols={4} gap={16}>
                  <StatCard
                    label="Ricavi Totali"
                    value={euroODato(status.ricavi_totali)}
                    icon={<TrendingUp size={18} />}
                    accent="success"
                  />
                  <StatCard
                    label="Costi Totali"
                    value={euroODato(status.costi_totali)}
                    subtext="Fatture nette e lordo buste paga, senza contributi datoriali"
                    icon={<TrendingDown size={18} />}
                    accent="danger"
                  />
                  <StatCard
                    label="Utile Attuale"
                    value={euroODato(status.utile_attuale)}
                    icon={<Target size={18} />}
                    accent={status.utile_attuale == null ? 'none' : status.utile_attuale >= 0 ? 'success' : 'danger'}
                  />
                  <StatCard
                    label={
                      status.gap_da_colmare == null
                        ? 'Gap da Colmare'
                        : status.gap_da_colmare > 0 ? 'Gap da Colmare' : 'Target Superato'
                    }
                    value={euroODato(status.gap_da_colmare)}
                    icon={<BarChart3 size={18} />}
                    subtext={
                      status.gap_da_colmare != null && status.gap_da_colmare === 0
                        ? euroODato(status.surplus_target)
                        : undefined
                    }
                    accent={
                      status.gap_da_colmare == null ? 'none' : status.gap_da_colmare > 0 ? 'warning' : 'success'
                    }
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
