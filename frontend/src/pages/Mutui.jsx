import React, { useState, useEffect } from 'react';
import { toast } from 'sonner';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { formatEuro, useIsMobile, RG, pagePad, formatDateIT, COLORS, SHADOWS, BORDER_RADIUS, FONT } from '../lib/utils';
import { PageLayout, PageSection, PageLoading } from '../components/PageLayout';
import { Button, Badge, TableWrap, Table, Th, Td } from '../components/ds';
import {
  Landmark,
  TrendingUp,
  TrendingDown,
  Calendar,
  CheckCircle2,
  Clock,
  AlertTriangle,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  Percent,
  Banknote,
  FileText,
} from 'lucide-react';

const MONO = FONT.mono;

export default function Mutui() {
  const isMobile = useIsMobile();
  const { anno } = useAnnoGlobale();
  const [mutui, setMutui] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [expandedMutuo, setExpandedMutuo] = useState(null);
  const [riconciliaLoading, setRiconciliaLoading] = useState(false);
  const [lastRiconciliazione, setLastRiconciliazione] = useState(null);

  useEffect(() => {
    loadData();
  }, [anno]);

  const loadData = async () => {
    try {
      setLoading(true);
      const [mutuiRes, statsRes] = await Promise.all([
        api.get('/api/mutui/'),
        api.get('/api/mutui/statistiche/dashboard'),
      ]);

      setMutui(mutuiRes.data.data || []);
      setStats(statsRes.data.data || null);
    } catch (error) {
      console.error('Errore caricamento mutui:', error);
    } finally {
      setLoading(false);
    }
  };

  const riconciliaAutomatico = async () => {
    try {
      setRiconciliaLoading(true);
      const response = await api.post('/api/mutui/riconcilia', {
        tolleranza_importo: 1.0,
        tolleranza_giorni: 7,
      });

      setLastRiconciliazione(response.data.data);
      loadData(); // Ricarica dati

      toast.success(
        `Riconciliazione completata! ${response.data.data.riconciliazioni_automatiche} rate riconciliate automaticamente, ${response.data.data.riconciliazioni_manuali_richieste} richiedono riconciliazione manuale`
      );
    } catch (error) {
      console.error('Errore riconciliazione:', error);
      toast.error('Errore durante la riconciliazione');
    } finally {
      setRiconciliaLoading(false);
    }
  };

  const toggleExpanded = mutuoId => {
    setExpandedMutuo(expandedMutuo === mutuoId ? null : mutuoId);
  };

  if (loading) return <PageLoading />;

  return (
    <PageLayout>
      <PageSection>
        {/* Header */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: 12,
            marginBottom: 24,
            paddingLeft: 12,
            borderLeft: `4px solid ${COLORS.primary}`,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <Landmark size={28} style={{ color: COLORS.primary }} />
            <h1 style={{ fontSize: 24, fontWeight: 700, color: COLORS.gray[800] }}>Gestione Mutui</h1>
          </div>
          <Button
            variant="primary"
            size="lg"
            onClick={riconciliaAutomatico}
            disabled={riconciliaLoading}
            data-testid="riconcilia-mutui-btn"
            iconLeft={<RefreshCw size={18} className={riconciliaLoading ? 'animate-spin' : ''} />}
          >
            {riconciliaLoading ? 'Riconciliazione...' : 'Riconcilia Automaticamente'}
          </Button>
        </div>

        {/* Statistiche Cards */}
        {stats && (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
              gap: 16,
              marginBottom: 24,
            }}
          >
            {/* NOTA: StatCard del design system non inoltra data-testid al nodo radice,
                quindi qui si mantiene markup nativo con stile tokenizzato per preservare i testid. */}
            <div
              data-testid="stat-importo-totale"
              style={{
                background: COLORS.card,
                padding: 20,
                borderRadius: BORDER_RADIUS.md,
                border: `1px solid ${COLORS.border}`,
                borderLeft: `4px solid ${COLORS.primary}`,
                color: COLORS.gray[800],
              }}
            >
              <div style={{ fontSize: 11, color: COLORS.textMuted, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 }}>
                Importo Totale Accordato
              </div>
              <div style={{ fontSize: 22, fontWeight: 700, color: COLORS.primary, fontFamily: MONO }}>
                {formatEuro(stats.importo_totale_accordato)}
              </div>
              <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 4 }}>
                {stats.numero_mutui} mutui attivi
              </div>
            </div>

            <div
              data-testid="stat-pagato"
              style={{
                background: COLORS.card,
                padding: 20,
                borderRadius: BORDER_RADIUS.md,
                border: `1px solid ${COLORS.border}`,
                borderLeft: `4px solid ${COLORS.primary}`,
                color: COLORS.gray[800],
              }}
            >
              <div style={{ fontSize: 11, color: COLORS.textMuted, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 }}>Già Pagato</div>
              <div style={{ fontSize: 22, fontWeight: 700, color: COLORS.success, fontFamily: MONO }}>
                {formatEuro(stats.totale_pagato || stats.totale_pagato_capitale)}
              </div>
              <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 4 }}>
                {stats.rate_pagate} rate pagate
              </div>
            </div>

            <div
              data-testid="stat-residuo"
              style={{
                background: COLORS.card,
                padding: 20,
                borderRadius: BORDER_RADIUS.md,
                border: `1px solid ${COLORS.border}`,
                borderLeft: `4px solid ${COLORS.primary}`,
                color: COLORS.gray[800],
              }}
            >
              <div style={{ fontSize: 11, color: COLORS.textMuted, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 }}>Debito Residuo</div>
              <div style={{ fontSize: 22, fontWeight: 700, color: COLORS.warning, fontFamily: MONO }}>
                {formatEuro(stats.debito_residuo_totale)}
              </div>
              <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 4 }}>
                {stats.rate_da_pagare} rate da pagare
              </div>
            </div>

            <div
              data-testid="stat-completamento"
              style={{
                background: COLORS.card,
                padding: 20,
                borderRadius: BORDER_RADIUS.md,
                border: `1px solid ${COLORS.border}`,
                borderLeft: `4px solid ${COLORS.primary}`,
                color: COLORS.gray[800],
              }}
            >
              <div style={{ fontSize: 11, color: COLORS.textMuted, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 }}>Completamento</div>
              <div style={{ fontSize: 22, fontWeight: 700, color: COLORS.primary, fontFamily: MONO }}>
                {stats.percentuale_completamento?.toFixed(1) || 0}%
              </div>
              <div
                style={{
                  width: '100%',
                  height: 6,
                  background: COLORS.border,
                  borderRadius: 3,
                  marginTop: 8,
                  overflow: 'hidden',
                }}
              >
                <div
                  style={{
                    width: `${stats.percentuale_completamento || 0}%`,
                    height: '100%',
                    background: COLORS.primary,
                    borderRadius: 3,
                  }}
                />
              </div>
            </div>
          </div>
        )}

        {/* Prossime Scadenze */}
        {stats?.prossime_scadenze?.length > 0 && (
          <div
            style={{
              background: COLORS.warningLight,
              border: `1px solid ${COLORS.warning}`,
              borderRadius: BORDER_RADIUS.md,
              padding: 16,
              marginBottom: 24,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
              <AlertTriangle size={20} style={{ color: COLORS.warning }} />
              <span style={{ fontWeight: 600, color: COLORS.warning }}>
                Prossime Scadenze (30 giorni)
              </span>
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
              {stats.prossime_scadenze.map((scad, idx) => (
                <div
                  key={idx}
                  style={{
                    background: COLORS.card,
                    padding: '10px 14px',
                    borderRadius: BORDER_RADIUS.md,
                    border: `1px solid ${COLORS.warning}`,
                    fontSize: 13,
                  }}
                >
                  <div style={{ fontWeight: 600, color: COLORS.text }}>{scad.nome}</div>
                  <div style={{ color: COLORS.textMuted }}>
                    Rata {scad.numero_rata} - {formatDateIT(scad.data_scadenza)} -{' '}
                    {formatEuro(scad.importo_totale)}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Lista Mutui */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {mutui.map(mutuo => (
            // NOTA: il Card del design system non ha uno slot per header cliccabile custom
            // né inoltra data-testid al nodo radice; si mantiene markup nativo tokenizzato.
            <div
              key={mutuo.mutuo_id}
              data-testid={`mutuo-card-${mutuo.mutuo_id}`}
              style={{
                background: COLORS.card,
                borderRadius: BORDER_RADIUS.md,
                border: `1px solid ${COLORS.border}`,
                overflow: 'hidden',
                boxShadow: SHADOWS.sm,
              }}
            >
              {/* Header Mutuo */}
              <div
                onClick={() => toggleExpanded(mutuo.mutuo_id)}
                style={{
                  padding: 20,
                  cursor: 'pointer',
                  background: expandedMutuo === mutuo.mutuo_id ? COLORS.bgAlt : COLORS.card,
                  transition: 'background 0.2s',
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'flex-start',
                    flexWrap: 'wrap',
                    gap: 8,
                  }}
                >
                  <div>
                    <h3
                      style={{ fontSize: 18, fontWeight: 600, color: COLORS.text, marginBottom: 4 }}
                    >
                      {mutuo.nome}
                    </h3>
                    <div style={{ fontSize: 14, color: COLORS.textMuted }}>
                      {mutuo.tipo_finanziamento} | Delibera: {mutuo.numero_delibera}
                    </div>
                    <div style={{ fontSize: 13, color: COLORS.textSubtle, marginTop: 2 }}>
                      {mutuo.banca}
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: 13, color: COLORS.textMuted }}>Importo accordato</div>
                    <div style={{ fontSize: 22, fontWeight: 700, color: COLORS.primary, fontFamily: MONO }}>
                      {formatEuro(mutuo.importo_accordato)}
                    </div>
                  </div>
                </div>

                {/* Stats Row */}
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
                    gap: 16,
                    marginTop: 16,
                    paddingTop: 16,
                    borderTop: `1px solid ${COLORS.border}`,
                  }}
                >
                  <div>
                    <div style={{ fontSize: 12, color: COLORS.textMuted, marginBottom: 2 }}>
                      Totale pagato
                    </div>
                    <div style={{ fontSize: 16, fontWeight: 600, color: COLORS.success, fontFamily: MONO }}>
                      {formatEuro(mutuo.totale_pagato)}
                    </div>
                    <div style={{ fontSize: 11, color: COLORS.textSubtle }}>
                      {mutuo.rate_pagate} / {mutuo.totale_rate} rate
                    </div>
                  </div>
                  <div>
                    <div style={{ fontSize: 12, color: COLORS.textMuted, marginBottom: 2 }}>
                      Debito residuo
                    </div>
                    <div style={{ fontSize: 16, fontWeight: 600, color: COLORS.warning, fontFamily: MONO }}>
                      {formatEuro(mutuo.debito_residuo_totale)}
                    </div>
                  </div>
                  <div>
                    <div style={{ fontSize: 12, color: COLORS.textMuted, marginBottom: 2 }}>
                      Riconciliazione
                    </div>
                    <div style={{ fontSize: 16, fontWeight: 600, color: COLORS.info }}>
                      {mutuo.percentuale_riconciliazione?.toFixed(1) || 0}%
                    </div>
                    <div style={{ fontSize: 11, color: COLORS.textSubtle }}>
                      {mutuo.rate_riconciliate || 0} / {mutuo.rate_pagate} riconciliate
                    </div>
                  </div>
                  <div
                    style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end' }}
                  >
                    {expandedMutuo === mutuo.mutuo_id ? (
                      <ChevronUp size={24} style={{ color: COLORS.textMuted }} />
                    ) : (
                      <ChevronDown size={24} style={{ color: COLORS.textMuted }} />
                    )}
                  </div>
                </div>

                {/* Prossima Scadenza Alert */}
                {mutuo.prossima_data_scadenza && (
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      marginTop: 12,
                      padding: '10px 12px',
                      background: COLORS.warningLight,
                      borderRadius: BORDER_RADIUS.md,
                    }}
                  >
                    <Calendar size={16} style={{ color: COLORS.warning }} />
                    <span style={{ fontSize: 13, color: COLORS.warning, fontWeight: 500 }}>
                      Prossima scadenza: {mutuo.prossima_data_scadenza} -{' '}
                      {formatEuro(mutuo.prossimo_importo)}
                    </span>
                  </div>
                )}
              </div>

              {/* Rate Dettaglio (Expanded) */}
              {expandedMutuo === mutuo.mutuo_id && (
                <div
                  style={{
                    padding: 20,
                    background: COLORS.bgAlt,
                    borderTop: `1px solid ${COLORS.border}`,
                  }}
                >
                  <h4 style={{ fontSize: 14, fontWeight: 600, color: COLORS.gray[700], marginBottom: 12 }}>
                    Piano di Ammortamento ({mutuo.rate?.length || 0} rate)
                  </h4>
                  <div
                    style={{
                      maxHeight: 400,
                      overflowY: 'auto',
                      borderRadius: BORDER_RADIUS.md,
                    }}
                  >
                    <TableWrap>
                      <Table>
                        <thead>
                          <tr>
                            <Th align="left">N°</Th>
                            <Th align="left">Scadenza</Th>
                            <Th align="right">Capitale</Th>
                            <Th align="right">Interessi</Th>
                            <Th align="right">Totale</Th>
                            <Th align="center">Stato</Th>
                            <Th align="center">Riconciliata</Th>
                          </tr>
                        </thead>
                        <tbody>
                          {mutuo.rate?.map((rata, idx) => (
                            <tr
                              key={idx}
                              style={{
                                background:
                                  rata.stato === 'Pagata'
                                    ? COLORS.successLight
                                    : rata.stato === 'Scaduta'
                                      ? COLORS.dangerLight
                                      : COLORS.card,
                              }}
                            >
                              <Td style={{ fontWeight: 500 }}>{rata.numero_rata}</Td>
                              <Td>{formatDateIT(rata.data_scadenza)}</Td>
                              <Td align="right" mono>
                                {formatEuro(rata.quota_capitale)}
                              </Td>
                              <Td align="right" mono style={{ color: COLORS.textMuted }}>
                                {formatEuro(rata.quota_interessi)}
                              </Td>
                              <Td align="right" mono style={{ fontWeight: 600 }}>
                                {formatEuro(rata.importo_totale)}
                              </Td>
                              <Td align="center">
                                {rata.stato === 'Pagata' && (
                                  <Badge variant="success" style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                                    <CheckCircle2 size={12} /> Pagata
                                  </Badge>
                                )}
                                {rata.stato === 'Da pagare' && (
                                  <Badge variant="neutral" style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                                    <Clock size={12} /> Da pagare
                                  </Badge>
                                )}
                                {rata.stato === 'Scaduta' && (
                                  <Badge variant="danger" style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                                    <AlertTriangle size={12} /> Scaduta
                                  </Badge>
                                )}
                              </Td>
                              <Td align="center">
                                {rata.riconciliata ? (
                                  <CheckCircle2 size={18} style={{ color: COLORS.success }} />
                                ) : rata.stato === 'Pagata' ? (
                                  <Clock size={18} style={{ color: COLORS.warning }} />
                                ) : (
                                  <span style={{ color: COLORS.gray[300] }}>-</span>
                                )}
                              </Td>
                            </tr>
                          ))}
                        </tbody>
                      </Table>
                    </TableWrap>
                  </div>

                  {/* Riepilogo Importi */}
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
                      gap: 16,
                      marginTop: 16,
                    }}
                  >
                    <div
                      style={{
                        padding: 12,
                        background: COLORS.successLight,
                        borderRadius: BORDER_RADIUS.md,
                        border: `1px solid ${COLORS.success}`,
                      }}
                    >
                      <div style={{ fontSize: 12, color: COLORS.success, marginBottom: 4 }}>
                        Capitale Pagato
                      </div>
                      <div style={{ fontSize: 18, fontWeight: 700, color: COLORS.success, fontFamily: MONO }}>
                        {formatEuro(mutuo.totale_pagato_capitale)}
                      </div>
                    </div>
                    <div
                      style={{
                        padding: 12,
                        background: COLORS.warningLight,
                        borderRadius: BORDER_RADIUS.md,
                        border: `1px solid ${COLORS.warning}`,
                      }}
                    >
                      <div style={{ fontSize: 12, color: COLORS.warning, marginBottom: 4 }}>
                        Interessi Pagati
                      </div>
                      <div style={{ fontSize: 18, fontWeight: 700, color: COLORS.warning, fontFamily: MONO }}>
                        {formatEuro(mutuo.totale_pagato_interessi)}
                      </div>
                    </div>
                    <div
                      style={{
                        padding: 12,
                        background: COLORS.card,
                        borderRadius: BORDER_RADIUS.md,
                        border: `1px solid ${COLORS.border}`,
                        borderLeft: `4px solid ${COLORS.primary}`,
                      }}
                    >
                      <div style={{ fontSize: 12, color: COLORS.textMuted, marginBottom: 4 }}>
                        Totale Versato
                      </div>
                      <div style={{ fontSize: 18, fontWeight: 700, color: COLORS.primary, fontFamily: MONO }}>
                        {formatEuro(mutuo.totale_pagato)}
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>

        {mutui.length === 0 && (
          <div
            style={{
              textAlign: 'center',
              padding: 60,
              background: COLORS.bgAlt,
              borderRadius: BORDER_RADIUS.md,
            }}
          >
            <Landmark size={48} style={{ color: COLORS.gray[300], marginBottom: 16 }} />
            <div style={{ fontSize: 18, fontWeight: 500, color: COLORS.textMuted }}>
              Nessun mutuo trovato
            </div>
            <div style={{ fontSize: 14, color: COLORS.textSubtle, marginTop: 4 }}>
              I mutui verranno visualizzati qui una volta importati
            </div>
          </div>
        )}
      </PageSection>
    </PageLayout>
  );
}
