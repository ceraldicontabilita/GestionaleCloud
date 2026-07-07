import React, { useState, useEffect } from 'react';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { formatEuro, useIsMobile, RG, pagePad, formatDateIT } from '../lib/utils';
import { PageLayout, PageSection, PageLoading } from '../components/PageLayout';
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

const MONO = 'ui-monospace, SFMono-Regular, Menlo, monospace';

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

      alert(
        `Riconciliazione completata!\n\n${response.data.data.riconciliazioni_automatiche} rate riconciliate automaticamente\n${response.data.data.riconciliazioni_manuali_richieste} richiedono riconciliazione manuale`
      );
    } catch (error) {
      console.error('Errore riconciliazione:', error);
      alert('Errore durante la riconciliazione');
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
            borderLeft: '4px solid #0f2744',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <Landmark size={28} style={{ color: '#0f2744' }} />
            <h1 style={{ fontSize: 24, fontWeight: 700, color: '#1e293b' }}>Gestione Mutui</h1>
          </div>
          <button
            onClick={riconciliaAutomatico}
            disabled={riconciliaLoading}
            data-testid="riconcilia-mutui-btn"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '10px 20px',
              minHeight: 40,
              fontSize: 13,
              background: riconciliaLoading ? '#9ca3af' : '#0f2744',
              color: 'white',
              border: 'none',
              borderRadius: 6,
              cursor: riconciliaLoading ? 'not-allowed' : 'pointer',
              fontWeight: 500,
              transition: 'all 0.2s',
            }}
          >
            <RefreshCw size={18} className={riconciliaLoading ? 'animate-spin' : ''} />
            {riconciliaLoading ? 'Riconciliazione...' : 'Riconcilia Automaticamente'}
          </button>
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
            <div
              data-testid="stat-importo-totale"
              style={{
                background: 'white',
                padding: 20,
                borderRadius: 8,
                border: '1px solid #e2e8f0',
                borderLeft: '4px solid #0f2744',
                color: '#1e293b',
              }}
            >
              <div style={{ fontSize: 11, color: '#64748b', fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 }}>
                Importo Totale Accordato
              </div>
              <div style={{ fontSize: 22, fontWeight: 700, color: '#0f2744', fontFamily: MONO }}>
                {formatEuro(stats.importo_totale_accordato)}
              </div>
              <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>
                {stats.numero_mutui} mutui attivi
              </div>
            </div>

            <div
              data-testid="stat-pagato"
              style={{
                background: 'white',
                padding: 20,
                borderRadius: 8,
                border: '1px solid #e2e8f0',
                borderLeft: '4px solid #0f2744',
                color: '#1e293b',
              }}
            >
              <div style={{ fontSize: 11, color: '#64748b', fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 }}>Già Pagato</div>
              <div style={{ fontSize: 22, fontWeight: 700, color: '#16a34a', fontFamily: MONO }}>
                {formatEuro(stats.totale_pagato || stats.totale_pagato_capitale)}
              </div>
              <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>
                {stats.rate_pagate} rate pagate
              </div>
            </div>

            <div
              data-testid="stat-residuo"
              style={{
                background: 'white',
                padding: 20,
                borderRadius: 8,
                border: '1px solid #e2e8f0',
                borderLeft: '4px solid #0f2744',
                color: '#1e293b',
              }}
            >
              <div style={{ fontSize: 11, color: '#64748b', fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 }}>Debito Residuo</div>
              <div style={{ fontSize: 22, fontWeight: 700, color: '#b45309', fontFamily: MONO }}>
                {formatEuro(stats.debito_residuo_totale)}
              </div>
              <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>
                {stats.rate_da_pagare} rate da pagare
              </div>
            </div>

            <div
              data-testid="stat-completamento"
              style={{
                background: 'white',
                padding: 20,
                borderRadius: 8,
                border: '1px solid #e2e8f0',
                borderLeft: '4px solid #0f2744',
                color: '#1e293b',
              }}
            >
              <div style={{ fontSize: 11, color: '#64748b', fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 }}>Completamento</div>
              <div style={{ fontSize: 22, fontWeight: 700, color: '#0f2744', fontFamily: MONO }}>
                {stats.percentuale_completamento?.toFixed(1) || 0}%
              </div>
              <div
                style={{
                  width: '100%',
                  height: 6,
                  background: '#e2e8f0',
                  borderRadius: 3,
                  marginTop: 8,
                  overflow: 'hidden',
                }}
              >
                <div
                  style={{
                    width: `${stats.percentuale_completamento || 0}%`,
                    height: '100%',
                    background: '#0f2744',
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
              background: '#fef3c7',
              border: '1px solid #fbbf24',
              borderRadius: 8,
              padding: 16,
              marginBottom: 24,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
              <AlertTriangle size={20} style={{ color: '#d97706' }} />
              <span style={{ fontWeight: 600, color: '#92400e' }}>
                Prossime Scadenze (30 giorni)
              </span>
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
              {stats.prossime_scadenze.map((scad, idx) => (
                <div
                  key={idx}
                  style={{
                    background: 'white',
                    padding: '10px 14px',
                    borderRadius: 8,
                    border: '1px solid #fcd34d',
                    fontSize: 13,
                  }}
                >
                  <div style={{ fontWeight: 600, color: '#1f2937' }}>{scad.nome}</div>
                  <div style={{ color: '#6b7280' }}>
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
            <div
              key={mutuo.mutuo_id}
              data-testid={`mutuo-card-${mutuo.mutuo_id}`}
              style={{
                background: 'white',
                borderRadius: 8,
                border: '1px solid #e2e8f0',
                overflow: 'hidden',
                boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
              }}
            >
              {/* Header Mutuo */}
              <div
                onClick={() => toggleExpanded(mutuo.mutuo_id)}
                style={{
                  padding: 20,
                  cursor: 'pointer',
                  background: expandedMutuo === mutuo.mutuo_id ? '#f9fafb' : 'white',
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
                      style={{ fontSize: 18, fontWeight: 600, color: '#1f2937', marginBottom: 4 }}
                    >
                      {mutuo.nome}
                    </h3>
                    <div style={{ fontSize: 14, color: '#6b7280' }}>
                      {mutuo.tipo_finanziamento} | Delibera: {mutuo.numero_delibera}
                    </div>
                    <div style={{ fontSize: 13, color: '#9ca3af', marginTop: 2 }}>
                      {mutuo.banca}
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: 13, color: '#6b7280' }}>Importo accordato</div>
                    <div style={{ fontSize: 22, fontWeight: 700, color: '#0f2744', fontFamily: MONO }}>
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
                    borderTop: '1px solid #e5e7eb',
                  }}
                >
                  <div>
                    <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 2 }}>
                      Totale pagato
                    </div>
                    <div style={{ fontSize: 16, fontWeight: 600, color: '#16a34a', fontFamily: MONO }}>
                      {formatEuro(mutuo.totale_pagato)}
                    </div>
                    <div style={{ fontSize: 11, color: '#9ca3af' }}>
                      {mutuo.rate_pagate} / {mutuo.totale_rate} rate
                    </div>
                  </div>
                  <div>
                    <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 2 }}>
                      Debito residuo
                    </div>
                    <div style={{ fontSize: 16, fontWeight: 600, color: '#b45309', fontFamily: MONO }}>
                      {formatEuro(mutuo.debito_residuo_totale)}
                    </div>
                  </div>
                  <div>
                    <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 2 }}>
                      Riconciliazione
                    </div>
                    <div style={{ fontSize: 16, fontWeight: 600, color: '#3b82f6' }}>
                      {mutuo.percentuale_riconciliazione?.toFixed(1) || 0}%
                    </div>
                    <div style={{ fontSize: 11, color: '#9ca3af' }}>
                      {mutuo.rate_riconciliate || 0} / {mutuo.rate_pagate} riconciliate
                    </div>
                  </div>
                  <div
                    style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end' }}
                  >
                    {expandedMutuo === mutuo.mutuo_id ? (
                      <ChevronUp size={24} style={{ color: '#6b7280' }} />
                    ) : (
                      <ChevronDown size={24} style={{ color: '#6b7280' }} />
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
                      background: '#fef3c7',
                      borderRadius: 8,
                    }}
                  >
                    <Calendar size={16} style={{ color: '#d97706' }} />
                    <span style={{ fontSize: 13, color: '#92400e', fontWeight: 500 }}>
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
                    background: '#f9fafb',
                    borderTop: '1px solid #e5e7eb',
                  }}
                >
                  <h4 style={{ fontSize: 14, fontWeight: 600, color: '#374151', marginBottom: 12 }}>
                    Piano di Ammortamento ({mutuo.rate?.length || 0} rate)
                  </h4>
                  <div
                    style={{
                      maxHeight: 400,
                      overflowY: 'auto',
                      background: 'white',
                      borderRadius: 8,
                      border: '1px solid #e2e8f0',
                      overflowX: 'auto',
                    }}
                  >
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                      <thead>
                        <tr style={{ background: '#f8fafc' }}>
                          {[
                            ['N°', 'left'],
                            ['Scadenza', 'left'],
                            ['Capitale', 'right'],
                            ['Interessi', 'right'],
                            ['Totale', 'right'],
                            ['Stato', 'center'],
                            ['Riconciliata', 'center'],
                          ].map(([label, align]) => (
                            <th
                              key={label}
                              style={{
                                padding: '10px 12px',
                                textAlign: align,
                                fontWeight: 600,
                                fontSize: 11,
                                textTransform: 'uppercase',
                                letterSpacing: 0.5,
                                color: '#64748b',
                              }}
                            >
                              {label}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {mutuo.rate?.map((rata, idx) => (
                          <tr
                            key={idx}
                            style={{
                              borderBottom: '1px solid #f1f5f9',
                              background:
                                rata.stato === 'Pagata'
                                  ? '#f0fdf4'
                                  : rata.stato === 'Scaduta'
                                    ? '#fef2f2'
                                    : 'white',
                            }}
                          >
                            <td style={{ padding: '10px 12px', fontWeight: 500 }}>
                              {rata.numero_rata}
                            </td>
                            <td style={{ padding: '10px 12px' }}>{formatDateIT(rata.data_scadenza)}</td>
                            <td style={{ padding: '10px 12px', textAlign: 'right', fontFamily: MONO }}>
                              {formatEuro(rata.quota_capitale)}
                            </td>
                            <td
                              style={{
                                padding: '10px 12px',
                                textAlign: 'right',
                                color: '#64748b',
                                fontFamily: MONO,
                              }}
                            >
                              {formatEuro(rata.quota_interessi)}
                            </td>
                            <td
                              style={{
                                padding: '10px 12px',
                                textAlign: 'right',
                                fontWeight: 600,
                                fontFamily: MONO,
                              }}
                            >
                              {formatEuro(rata.importo_totale)}
                            </td>
                            <td style={{ padding: '10px 12px', textAlign: 'center' }}>
                              {rata.stato === 'Pagata' && (
                                <span
                                  style={{
                                    display: 'inline-flex',
                                    alignItems: 'center',
                                    gap: 4,
                                    padding: '2px 8px',
                                    background: '#dcfce7',
                                    color: '#166534',
                                    borderRadius: 8,
                                    fontSize: 11,
                                    fontWeight: 500,
                                  }}
                                >
                                  <CheckCircle2 size={12} /> Pagata
                                </span>
                              )}
                              {rata.stato === 'Da pagare' && (
                                <span
                                  style={{
                                    display: 'inline-flex',
                                    alignItems: 'center',
                                    gap: 4,
                                    padding: '2px 8px',
                                    background: '#e5e7eb',
                                    color: '#374151',
                                    borderRadius: 8,
                                    fontSize: 11,
                                    fontWeight: 500,
                                  }}
                                >
                                  <Clock size={12} /> Da pagare
                                </span>
                              )}
                              {rata.stato === 'Scaduta' && (
                                <span
                                  style={{
                                    display: 'inline-flex',
                                    alignItems: 'center',
                                    gap: 4,
                                    padding: '2px 8px',
                                    background: '#fee2e2',
                                    color: '#991b1b',
                                    borderRadius: 8,
                                    fontSize: 11,
                                    fontWeight: 500,
                                  }}
                                >
                                  <AlertTriangle size={12} /> Scaduta
                                </span>
                              )}
                            </td>
                            <td style={{ padding: '10px 12px', textAlign: 'center' }}>
                              {rata.riconciliata ? (
                                <CheckCircle2 size={18} style={{ color: '#16a34a' }} />
                              ) : rata.stato === 'Pagata' ? (
                                <Clock size={18} style={{ color: '#d97706' }} />
                              ) : (
                                <span style={{ color: '#d1d5db' }}>-</span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
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
                        background: '#f0fdf4',
                        borderRadius: 8,
                        border: '1px solid #bbf7d0',
                      }}
                    >
                      <div style={{ fontSize: 12, color: '#166534', marginBottom: 4 }}>
                        Capitale Pagato
                      </div>
                      <div style={{ fontSize: 18, fontWeight: 700, color: '#15803d', fontFamily: MONO }}>
                        {formatEuro(mutuo.totale_pagato_capitale)}
                      </div>
                    </div>
                    <div
                      style={{
                        padding: 12,
                        background: '#fef3c7',
                        borderRadius: 8,
                        border: '1px solid #fcd34d',
                      }}
                    >
                      <div style={{ fontSize: 12, color: '#92400e', marginBottom: 4 }}>
                        Interessi Pagati
                      </div>
                      <div style={{ fontSize: 18, fontWeight: 700, color: '#d97706', fontFamily: MONO }}>
                        {formatEuro(mutuo.totale_pagato_interessi)}
                      </div>
                    </div>
                    <div
                      style={{
                        padding: 12,
                        background: 'white',
                        borderRadius: 8,
                        border: '1px solid #e2e8f0',
                        borderLeft: '4px solid #0f2744',
                      }}
                    >
                      <div style={{ fontSize: 12, color: '#64748b', marginBottom: 4 }}>
                        Totale Versato
                      </div>
                      <div style={{ fontSize: 18, fontWeight: 700, color: '#0f2744', fontFamily: MONO }}>
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
              background: '#f8fafc',
              borderRadius: 8,
            }}
          >
            <Landmark size={48} style={{ color: '#d1d5db', marginBottom: 16 }} />
            <div style={{ fontSize: 18, fontWeight: 500, color: '#6b7280' }}>
              Nessun mutuo trovato
            </div>
            <div style={{ fontSize: 14, color: '#9ca3af', marginTop: 4 }}>
              I mutui verranno visualizzati qui una volta importati
            </div>
          </div>
        )}
      </PageSection>
    </PageLayout>
  );
}
