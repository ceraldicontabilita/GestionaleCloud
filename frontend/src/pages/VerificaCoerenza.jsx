import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { formatEuro, COLORS, SHADOWS, BORDER_RADIUS, FONT } from '../lib/utils';
import { PageLayout } from '../components/PageLayout';
import { Button, Badge, Card, Tabs, TableWrap, Table, Th, Td } from '../components/ds';

export default function VerificaCoerenza() {
  const { anno } = useAnnoGlobale();
  const [loading, setLoading] = useState(false);
  // URL Tab Support
  const navigate = useNavigate();
  const location = useLocation();

  const getTabFromPath = () => {
    const path = location.pathname;
    const match = path.match(/\/verifica-coerenza\/([\w-]+)/);
    return match ? match[1] : 'riepilogo';
  };

  const [activeTab, setActiveTab] = useState(getTabFromPath());

  const handleTabChange = tabId => {
    setActiveTab(tabId);
    navigate(`/verifica-coerenza/${tabId}`);
  };

  useEffect(() => {
    const tab = getTabFromPath();
    if (tab !== activeTab) setActiveTab(tab);
  }, [location.pathname]);
  const [verificaCompleta, setVerificaCompleta] = useState(null);
  const [confrontoIva, setConfrontoIva] = useState(null);
  // 'bonifici' rimosso: il box 'Bonifici vs Banca' è stato eliminato (sempre a zero, fuorviante)
  const [error, setError] = useState(null);

  useEffect(() => {
    loadAll();
  }, [anno]);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [completa, iva] = await Promise.all([
        api.get(`/api/verifica-coerenza/completa/${anno}`).catch(() => ({ data: null })),
        api
          .get(`/api/verifica-coerenza/confronto-iva-completo/${anno}`)
          .catch(() => ({ data: null })),
      ]);
      setVerificaCompleta(completa.data);
      setConfrontoIva(iva.data);
    } catch (err) {
      console.error('Errore caricamento:', err);
      setError('Errore nel caricamento dei dati');
    } finally {
      setLoading(false);
    }
  }, [anno]);

  const getStatoColor = stato => {
    switch (stato) {
      case 'OK':
        return { bg: COLORS.successLight, text: COLORS.success, border: COLORS.success };
      case 'ATTENZIONE':
        return { bg: COLORS.warningLight, text: COLORS.warning, border: COLORS.warning };
      case 'CRITICO':
        return { bg: COLORS.dangerLight, text: COLORS.danger, border: COLORS.danger };
      default:
        return { bg: COLORS.bg, text: COLORS.gray[600], border: COLORS.border };
    }
  };

  const stato = verificaCompleta?.stato_generale || 'OK';
  const statoColors = getStatoColor(stato);

  const cardStyle = {
    background: COLORS.card,
    borderRadius: BORDER_RADIUS.md,
    boxShadow: SHADOWS.sm,
    border: `1px solid ${COLORS.border}`,
    overflow: 'hidden',
  };

  const cardHeaderStyle = {
    padding: '12px 16px',
    borderBottom: `1px solid ${COLORS.border}`,
    background: COLORS.bgAlt,
  };

  const cardTitleStyle = {
    margin: 0,
    fontSize: 14,
    fontWeight: 600,
    color: COLORS.gray[800],
    display: 'flex',
    alignItems: 'center',
    gap: 8,
  };

  const cardContentStyle = {
    padding: 16,
  };

  return (
    <PageLayout
      title="Verifica Coerenza Dati"
      icon="🔍"
      subtitle={`Controllo automatico - Anno ${anno}`}
      actions={
        <Button
          variant="secondary"
          onClick={loadAll}
          disabled={loading}
          data-testid="btn-ricarica-verifica"
          iconLeft="🔄"
        >
          Ricarica
        </Button>
      }
    >
      {error && (
        <div
          style={{
            padding: 12,
            background: COLORS.dangerLight,
            borderRadius: BORDER_RADIUS.md,
            color: COLORS.danger,
            marginBottom: 16,
            fontSize: 13,
          }}
        >
          {error}
        </div>
      )}

      {loading && (
        <div
          style={{
            padding: 40,
            textAlign: 'center',
            color: COLORS.textMuted,
            fontSize: 14,
          }}
        >
          <div
            style={{
              width: 32,
              height: 32,
              border: `3px solid ${COLORS.border}`,
              borderTop: `3px solid ${COLORS.info}`,
              borderRadius: BORDER_RADIUS.full,
              animation: 'spin 1s linear infinite',
              margin: '0 auto 12px',
            }}
          />
          <style>{`@keyframes spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}`}</style>
          Caricamento verifica coerenza dati...
        </div>
      )}

      {/* Stato Generale Card */}
      {!loading && verificaCompleta && (
        <div
          style={{
            ...cardStyle,
            marginBottom: 16,
            background: statoColors.bg,
            border: `2px solid ${statoColors.border}`,
          }}
        >
          <div style={{ ...cardContentStyle, padding: 16 }}>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                flexWrap: 'wrap',
                gap: 16,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <span style={{ fontSize: 40 }}>
                  {stato === 'OK' ? '✅' : stato === 'ATTENZIONE' ? '⚠️' : '❌'}
                </span>
                <div>
                  <div style={{ fontSize: 20, fontWeight: 'bold', color: statoColors.text }}>
                    Stato: {stato}
                  </div>
                  <div style={{ color: COLORS.textMuted, fontSize: 12 }}>
                    Ultima verifica: {new Date(verificaCompleta.timestamp).toLocaleString('it-IT').replaceAll('/', '-')}
                  </div>
                </div>
              </div>
              <div style={{ display: 'flex', gap: 20, textAlign: 'center' }}>
                <div>
                  <div style={{ fontSize: 24, fontWeight: 'bold', color: COLORS.danger }}>
                    {verificaCompleta.riepilogo?.critical || 0}
                  </div>
                  <div style={{ fontSize: 11, color: COLORS.textMuted }}>Critiche</div>
                </div>
                <div>
                  <div style={{ fontSize: 24, fontWeight: 'bold', color: COLORS.warning }}>
                    {verificaCompleta.riepilogo?.warning || 0}
                  </div>
                  <div style={{ fontSize: 11, color: COLORS.textMuted }}>Avvisi</div>
                </div>
                <div>
                  <div style={{ fontSize: 24, fontWeight: 'bold', color: COLORS.info }}>
                    {verificaCompleta.riepilogo?.info || 0}
                  </div>
                  <div style={{ fontSize: 11, color: COLORS.textMuted }}>Info</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tabs */}
      {!loading && (
        <Tabs
          value={activeTab}
          onChange={handleTabChange}
          items={[
            { key: 'riepilogo', label: '📋 Riepilogo' },
            { key: 'iva', label: '📈 IVA Mensile' },
            { key: 'discrepanze', label: '⚠️ Discrepanze' },
          ]}
          style={{ marginBottom: 16 }}
        />
      )}

      {/* TAB RIEPILOGO */}
      {!loading && activeTab === 'riepilogo' && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
            gap: 16,
          }}
        >
          {/* IVA Annuale */}
          <Card title={`IVA Annuale ${anno}`} icon="🧾">
            {verificaCompleta?.verifiche?.iva_annuale && (
              <div style={{ display: 'grid', gap: 10 }}>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    padding: 10,
                    background: COLORS.dangerLight,
                    borderRadius: BORDER_RADIUS.sm,
                  }}
                >
                  <span style={{ color: COLORS.danger, fontSize: 13 }}>IVA Debito</span>
                  <strong style={{ color: COLORS.danger }}>
                    {formatEuro(verificaCompleta.verifiche.iva_annuale.iva_debito_totale)}
                  </strong>
                </div>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    padding: 10,
                    background: COLORS.successLight,
                    borderRadius: BORDER_RADIUS.sm,
                  }}
                >
                  <span style={{ color: COLORS.success, fontSize: 13 }}>IVA Credito</span>
                  <strong style={{ color: COLORS.success }}>
                    {formatEuro(verificaCompleta.verifiche.iva_annuale.iva_credito_totale)}
                  </strong>
                </div>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    padding: 10,
                    background:
                      verificaCompleta.verifiche.iva_annuale.saldo_iva > 0
                        ? COLORS.warningLight
                        : COLORS.infoLight,
                    borderRadius: BORDER_RADIUS.sm,
                    fontWeight: 'bold',
                  }}
                >
                  <span style={{ fontSize: 13 }}>Saldo IVA</span>
                  <span
                    style={{
                      color:
                        verificaCompleta.verifiche.iva_annuale.saldo_iva > 0
                          ? COLORS.warning
                          : COLORS.info,
                    }}
                  >
                    {verificaCompleta.verifiche.iva_annuale.saldo_iva > 0
                      ? 'Da versare '
                      : 'A credito '}
                    {formatEuro(Math.abs(verificaCompleta.verifiche.iva_annuale.saldo_iva))}
                  </span>
                </div>
              </div>
            )}
          </Card>

          {/* Versamenti */}
          <Card title="Versamenti Cassa vs Banca" icon="💳">
            {verificaCompleta?.verifiche?.versamenti && (
              <div style={{ display: 'grid', gap: 10 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                  <span>Versamenti (Cassa)</span>
                  <strong>
                    {formatEuro(verificaCompleta.verifiche.versamenti.versamenti_manuali)}
                  </strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                  <span>Versamenti (Banca)</span>
                  <strong>
                    {formatEuro(verificaCompleta.verifiche.versamenti.versamenti_banca)}
                  </strong>
                </div>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    padding: 10,
                    background:
                      Math.abs(verificaCompleta.verifiche.versamenti.differenza) < 1
                        ? COLORS.successLight
                        : COLORS.dangerLight,
                    borderRadius: BORDER_RADIUS.sm,
                  }}
                >
                  <span style={{ fontSize: 13 }}>Differenza</span>
                  <strong
                    style={{
                      color:
                        Math.abs(verificaCompleta.verifiche.versamenti.differenza) < 1
                          ? COLORS.success
                          : COLORS.danger,
                    }}
                  >
                    {Math.abs(verificaCompleta.verifiche.versamenti.differenza) < 1
                      ? '✅ OK'
                      : formatEuro(verificaCompleta.verifiche.versamenti.differenza)}
                  </strong>
                </div>
              </div>
            )}
          </Card>

          {/* NOTA: i box 'Prima Nota vs E/C' e 'Bonifici vs Banca' sono stati
              rimossi su richiesta dell'utente perché fuorvianti (sempre a zero
              o con numeri non interpretabili). Il controllo saldi è stato
              sostituito da una tab dedicata che elenca i singoli movimenti
              bancari non presenti in Prima Nota, con azioni di import. */}
        </div>
      )}

      {/* TAB IVA MENSILE */}
      {!loading && activeTab === 'iva' && confrontoIva && (
        <Card title={`Confronto IVA Mensile ${anno}`}>
          <TableWrap>
            <Table>
              <thead>
                <tr>
                  <Th>Mese</Th>
                  <Th align="right">IVA Debito</Th>
                  <Th align="center">N.Corr</Th>
                  <Th align="right">IVA Credito</Th>
                  <Th align="center">N.Fatt</Th>
                  <Th align="right">Saldo</Th>
                  <Th align="center">Stato</Th>
                </tr>
              </thead>
              <tbody>
                {confrontoIva.mensile?.map((m, idx) => (
                  <tr key={idx}>
                    <Td style={{ fontWeight: 'bold' }}>{m.mese_nome}</Td>
                    <Td align="right" mono style={{ color: COLORS.danger }}>
                      {formatEuro(m.iva_debito_corrispettivi)}
                    </Td>
                    <Td align="center" style={{ color: COLORS.textMuted }}>
                      {m.num_corrispettivi}
                    </Td>
                    <Td align="right" mono style={{ color: COLORS.success }}>
                      {formatEuro(m.iva_credito_fatture)}
                    </Td>
                    <Td align="center" style={{ color: COLORS.textMuted }}>
                      {m.num_fatture}
                    </Td>
                    <Td
                      align="right"
                      mono
                      style={{
                        fontWeight: 'bold',
                        color: m.saldo > 0 ? COLORS.danger : COLORS.success,
                      }}
                    >
                      {m.saldo > 0 ? '+' : ''}
                      {formatEuro(m.saldo)}
                    </Td>
                    <Td align="center">
                      {m.da_versare > 0 ? (
                        <Badge variant="warning">Versare {formatEuro(m.da_versare)}</Badge>
                      ) : (
                        <Badge variant="info">Credito {formatEuro(m.a_credito)}</Badge>
                      )}
                    </Td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr style={{ background: COLORS.gray[800], color: COLORS.white, fontWeight: 'bold' }}>
                  <td style={{ padding: '10px 14px' }}>TOTALE {anno}</td>
                  <td style={{ padding: '10px 14px', textAlign: 'right', fontFamily: FONT.mono }}>
                    {formatEuro(confrontoIva.totali?.iva_debito_totale)}
                  </td>
                  <td style={{ padding: '10px 14px' }}></td>
                  <td style={{ padding: '10px 14px', textAlign: 'right', fontFamily: FONT.mono }}>
                    {formatEuro(confrontoIva.totali?.iva_credito_totale)}
                  </td>
                  <td style={{ padding: '10px 14px' }}></td>
                  <td style={{ padding: '10px 14px', textAlign: 'right', fontFamily: FONT.mono }}>
                    {confrontoIva.totali?.saldo_annuale > 0 ? '+' : ''}
                    {formatEuro(confrontoIva.totali?.saldo_annuale)}
                  </td>
                  <td style={{ padding: '10px 14px', textAlign: 'center', fontSize: 10 }}>
                    {confrontoIva.totali?.saldo_annuale > 0 ? 'DA VERSARE' : 'A CREDITO'}
                  </td>
                </tr>
              </tfoot>
            </Table>
          </TableWrap>
        </Card>
      )}

      {/* TAB DISCREPANZE */}
      {!loading &&
        activeTab === 'discrepanze' &&
        (verificaCompleta?.discrepanze?.length > 0 ? (
          <div style={{ ...cardStyle, border: `2px solid ${COLORS.danger}` }}>
            <div style={{ ...cardHeaderStyle, background: COLORS.dangerLight }}>
              <h3 style={{ ...cardTitleStyle, color: COLORS.danger }}>
                ⚠️ Discrepanze Rilevate ({verificaCompleta?.discrepanze?.length})
              </h3>
            </div>
            <div style={cardContentStyle}>
              <div style={{ display: 'grid', gap: 12 }}>
                {verificaCompleta.discrepanze.map((d, idx) => (
                  <div
                    key={idx}
                    style={{
                      padding: 14,
                      background: d.severita === 'critical' ? COLORS.dangerLight : COLORS.warningLight,
                      borderRadius: BORDER_RADIUS.md,
                      border: `1px solid ${d.severita === 'critical' ? COLORS.danger : COLORS.warning}`,
                    }}
                  >
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'flex-start',
                        flexWrap: 'wrap',
                        gap: 12,
                      }}
                    >
                      <div style={{ flex: 1 }}>
                        <div
                          style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}
                        >
                          <Badge variant={d.severita === 'critical' ? 'danger' : 'warning'}>
                            {d.severita.toUpperCase()}
                          </Badge>
                          <strong style={{ color: COLORS.gray[800], fontSize: 13 }}>{d.categoria}</strong>
                          <span style={{ color: COLORS.textMuted, fontSize: 12 }}>
                            • {d.sottocategoria}
                          </span>
                        </div>
                        <p style={{ margin: '6px 0', color: COLORS.gray[600], fontSize: 13 }}>
                          {d.descrizione}
                        </p>
                        {d.periodo && (
                          <span style={{ fontSize: 11, color: COLORS.textSubtle }}>
                            Periodo: {d.periodo}
                          </span>
                        )}
                      </div>
                      <div style={{ textAlign: 'right', minWidth: 100 }}>
                        <div style={{ fontSize: 11, color: COLORS.textMuted }}>Atteso</div>
                        <div style={{ fontWeight: 'bold', color: COLORS.success, fontSize: 14 }}>
                          {formatEuro(d.valore_atteso)}
                        </div>
                        <div style={{ fontSize: 11, color: COLORS.textMuted, marginTop: 4 }}>Trovato</div>
                        <div style={{ fontWeight: 'bold', color: COLORS.danger, fontSize: 14 }}>
                          {formatEuro(d.valore_trovato)}
                        </div>
                        <div
                          style={{
                            marginTop: 6,
                            padding: '3px 8px',
                            background: COLORS.gray[800],
                            color: COLORS.white,
                            borderRadius: BORDER_RADIUS.sm,
                            fontWeight: 'bold',
                            fontSize: 12,
                          }}
                        >
                          Δ {d.differenza > 0 ? '+' : ''}
                          {formatEuro(d.differenza)}
                        </div>
                      </div>
                    </div>
                    {d.suggerimento && (
                      <div
                        style={{
                          marginTop: 10,
                          padding: 10,
                          background: COLORS.card,
                          borderRadius: BORDER_RADIUS.sm,
                          fontSize: 12,
                          color: COLORS.textMuted,
                          borderLeft: `3px solid ${COLORS.info}`,
                        }}
                      >
                        💡 <strong>Suggerimento:</strong> {d.suggerimento}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div style={{ ...cardStyle, background: COLORS.successLight, border: `2px solid ${COLORS.success}` }}>
            <div style={{ ...cardContentStyle, padding: 40, textAlign: 'center' }}>
              <div style={{ fontSize: 56, marginBottom: 12 }}>✅</div>
              <h3 style={{ margin: 0, color: COLORS.success, fontSize: 20 }}>
                Tutti i Dati sono Coerenti!
              </h3>
              <p style={{ margin: '8px 0 0', color: COLORS.success, fontSize: 13 }}>
                Non sono state rilevate discrepanze tra le varie sezioni del gestionale.
              </p>
            </div>
          </div>
        ))}
    </PageLayout>
  );
}
