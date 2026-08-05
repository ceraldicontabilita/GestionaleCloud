import React, { useState, useEffect, useMemo } from 'react';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { formatEuro, formatDateIT, COLORS, BORDER_RADIUS, FONT } from '../lib/utils';
import { PageLayout, PageLoading } from '../components/PageLayout';
import { Button, Badge, StatCard, Input, Select, TableWrap, Table, Th, Td } from '../components/ds';
import {
  FileText,
  Download,
  Search,
  ChevronDown,
  ChevronRight,
  CheckCircle,
  AlertTriangle,
  RefreshCw,
  Printer,
} from 'lucide-react';

const TIPO_COLORS = {
  attivo: { variant: 'success', label: 'Attivo' },
  passivo: { variant: 'danger', label: 'Passivo' },
  ricavo: { variant: 'info', label: 'Ricavo' },
  costo: { variant: 'warning', label: 'Costo' },
};

const GRUPPI_CONTI = {
  '01': 'Attività',
  '02': 'Passività',
  '03': 'Patrimonio Netto',
  '04': 'Ricavi',
  '05': 'Costi',
};

export default function BilancioVerifica() {
  const { anno } = useAnnoGlobale();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [bvError, setBvError] = useState(false);
  const [dettaglio, setDettaglio] = useState(false);
  const [search, setSearch] = useState('');
  const [filtroTipo, setFiltroTipo] = useState('tutti');
  const [soloMovimentati, setSoloMovimentati] = useState(true);
  const [expandedConti, setExpandedConti] = useState(new Set());
  const [showSaldi, setShowSaldi] = useState(true); // mostra saldo dare/avere separati

  useEffect(() => {
    loadData();
  }, [anno, dettaglio]);

  const loadData = async () => {
    setLoading(true);
    try {
      const res = await api.get(
        `/api/contabilita-gestionale/bilancio-verifica?anno=${anno}&dettaglio=${dettaglio}`
      );
      setData(res.data);
      setBvError(false);
    } catch (err) {
      // Errore del servizio ≠ "nessun dato": distinguili nell'interfaccia.
      setBvError(true);
    } finally {
      setLoading(false);
    }
  };

  const contiFiltered = useMemo(() => {
    if (!data?.conti) return [];
    return data.conti.filter(c => {
      if (filtroTipo !== 'tutti' && c.tipo !== filtroTipo) return false;
      if (search) {
        const s = search.toLowerCase();
        if (!c.codice.toLowerCase().includes(s) && !c.nome.toLowerCase().includes(s)) return false;
      }
      return true;
    });
  }, [data, filtroTipo, search]);

  // Raggruppa per prefisso codice (01.xx, 02.xx, etc.)
  const contiRaggruppati = useMemo(() => {
    const gruppi = {};
    for (const c of contiFiltered) {
      const prefix = c.codice.substring(0, 2);
      if (!gruppi[prefix]) {
        gruppi[prefix] = {
          codice: prefix,
          nome: GRUPPI_CONTI[prefix] || `Gruppo ${prefix}`,
          conti: [],
          totale_dare: 0,
          totale_avere: 0,
        };
      }
      gruppi[prefix].conti.push(c);
      gruppi[prefix].totale_dare += c.dare;
      gruppi[prefix].totale_avere += c.avere;
    }
    return Object.values(gruppi).sort((a, b) => a.codice.localeCompare(b.codice));
  }, [contiFiltered]);

  const toggleExpand = codice => {
    setExpandedConti(prev => {
      const next = new Set(prev);
      next.has(codice) ? next.delete(codice) : next.add(codice);
      return next;
    });
  };

  const expandAll = () => setExpandedConti(new Set(contiRaggruppati.map(g => g.codice)));
  const collapseAll = () => setExpandedConti(new Set());

  const handleExportCSV = () => {
    if (!data?.conti) return;
    const rows = [
      ['Codice', 'Conto', 'Tipo', 'Dare', 'Avere', 'Saldo Dare', 'Saldo Avere'].join(';'),
    ];
    for (const c of data.conti) {
      rows.push(
        [
          c.codice,
          `"${c.nome}"`,
          c.tipo,
          c.dare.toFixed(2),
          c.avere.toFixed(2),
          c.saldo_dare.toFixed(2),
          c.saldo_avere.toFixed(2),
        ].join(';')
      );
    }
    rows.push(
      [
        '',
        'TOTALI',
        '',
        data.totali.dare.toFixed(2),
        data.totali.avere.toFixed(2),
        data.totali.saldo_dare.toFixed(2),
        data.totali.saldo_avere.toFixed(2),
      ].join(';')
    );
    const blob = new Blob(['﻿' + rows.join('\n')], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `bilancio-verifica-${anno}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handlePrint = () => {
    window.print();
  };

  const SummaryCards = () => {
    if (!data) return null;
    const { totali, quadratura, riepilogo } = data;
    return (
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
          gap: 16,
        }}
      >
        <StatCard
          accent="primary"
          label="TOTALE DARE"
          value={<span style={{ fontFamily: FONT.mono }}>{formatEuro(totali.dare)}</span>}
        />
        <StatCard
          accent="primary"
          label="TOTALE AVERE"
          value={<span style={{ fontFamily: FONT.mono }}>{formatEuro(totali.avere)}</span>}
        />
        <StatCard
          accent="primary"
          label="SALDO DARE"
          value={<span style={{ fontFamily: FONT.mono }}>{formatEuro(totali.saldo_dare)}</span>}
        />
        <StatCard
          accent="primary"
          label="SALDO AVERE"
          value={<span style={{ fontFamily: FONT.mono }}>{formatEuro(totali.saldo_avere)}</span>}
        />
        <StatCard
          accent={quadratura ? 'success' : 'danger'}
          label="QUADRATURA"
          value={
            <span
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                fontSize: 20,
                color: quadratura ? COLORS.success : COLORS.danger,
              }}
            >
              {quadratura ? <CheckCircle size={20} /> : <AlertTriangle size={20} />}
              {quadratura ? 'OK' : formatEuro(totali.sbilancio)}
            </span>
          }
          subtext={
            <>
              {riepilogo.n_conti} conti • {riepilogo.n_conti_attivo}A {riepilogo.n_conti_passivo}P{' '}
              {riepilogo.n_conti_ricavo}R {riepilogo.n_conti_costo}C
            </>
          }
        />
      </div>
    );
  };

  return (
    <PageLayout
      title="Bilancio di Verifica"
      icon={<FileText size={28} />}
      subtitle={`Saldi dare/avere di tutti i conti – Anno ${anno}`}
      actions={
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <Button
            variant="secondary"
            onClick={loadData}
            disabled={loading}
            iconLeft={<RefreshCw size={14} />}
          >
            Aggiorna
          </Button>
          <Button
            variant="primary"
            onClick={handleExportCSV}
            disabled={!data}
            iconLeft={<Download size={14} />}
          >
            CSV
          </Button>
          <Button variant="secondary" onClick={handlePrint} iconLeft={<Printer size={14} />}>
            Stampa
          </Button>
        </div>
      }
    >
      {loading ? (
        <PageLoading message="Generazione bilancio di verifica..." />
      ) : data ? (
        <>
          <SummaryCards />

          <div
            role="status"
            style={{
              marginTop: 16,
              padding: '12px 14px',
              borderRadius: BORDER_RADIUS.md,
              border: `1px solid ${data.completezza_registro?.completo ? COLORS.success : COLORS.warning}`,
              background: data.completezza_registro?.completo ? COLORS.successLight : COLORS.warningLight,
              color: COLORS.text,
              fontSize: 13,
              lineHeight: 1.5,
            }}
          >
            <strong>Fonte: libro giornale definitivo.</strong>{' '}
            {data.completezza_registro?.scritture_registrate || 0} scritture registrate.
            {!data.completezza_registro?.completo && (
              <>
                {' '}Il risultato quadra, ma non è ancora completo: restano{' '}
                <strong>{data.completezza_registro?.documenti_da_registrare || 0}</strong> documenti
                ({data.completezza_registro?.fatture_da_registrare || 0} fatture e{' '}
                {data.completezza_registro?.corrispettivi_da_registrare || 0} corrispettivi).
              </>
            )}
          </div>

          {/* Filtri */}
          <div
            style={{
              display: 'flex',
              gap: 12,
              alignItems: 'center',
              margin: '20px 0',
              flexWrap: 'wrap',
            }}
          >
            <div style={{ flex: 1, minWidth: 200 }}>
              <Input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Cerca per codice o nome conto..."
                iconLeft={<Search size={16} />}
              />
            </div>
            <Select value={filtroTipo} onChange={e => setFiltroTipo(e.target.value)}>
              <option value="tutti">Tutti i tipi</option>
              <option value="attivo">Attivo</option>
              <option value="passivo">Passivo</option>
              <option value="ricavo">Ricavi</option>
              <option value="costo">Costi</option>
            </Select>
            <label
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                fontSize: 13,
                cursor: 'pointer',
              }}
            >
              <input
                type="checkbox"
                checked={dettaglio}
                onChange={e => setDettaglio(e.target.checked)}
              />
              Dettaglio movimenti
            </label>
            <label
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                fontSize: 13,
                cursor: 'pointer',
              }}
            >
              <input
                type="checkbox"
                checked={showSaldi}
                onChange={e => setShowSaldi(e.target.checked)}
              />
              Colonne Saldo
            </label>
            <Button variant="secondary" size="sm" onClick={expandAll}>
              Espandi tutti
            </Button>
            <Button variant="secondary" size="sm" onClick={collapseAll}>
              Comprimi tutti
            </Button>
          </div>

          {/* Tabella principale */}
          <TableWrap>
            <Table>
              <thead>
                <tr>
                  <Th style={{ width: 100 }}>Codice</Th>
                  <Th>Conto</Th>
                  <Th align="center" style={{ width: 80 }}>
                    Tipo
                  </Th>
                  <Th align="right" style={{ width: 130 }}>
                    Dare
                  </Th>
                  <Th align="right" style={{ width: 130 }}>
                    Avere
                  </Th>
                  {showSaldi && (
                    <>
                      <Th align="right" style={{ width: 130, background: COLORS.bg }}>
                        Saldo Dare
                      </Th>
                      <Th align="right" style={{ width: 130, background: COLORS.bg }}>
                        Saldo Avere
                      </Th>
                    </>
                  )}
                  <Th align="center" style={{ width: 50 }}>
                    Mov.
                  </Th>
                </tr>
              </thead>
              <tbody>
                {contiRaggruppati.map(gruppo => {
                  const isExpanded = expandedConti.has(gruppo.codice);
                  const saldoGruppo = gruppo.totale_dare - gruppo.totale_avere;
                  return (
                    <React.Fragment key={gruppo.codice}>
                      {/* Riga gruppo */}
                      <tr
                        onClick={() => toggleExpand(gruppo.codice)}
                        style={{
                          background: COLORS.bg,
                          cursor: 'pointer',
                          borderTop: `2px solid ${COLORS.borderDark}`,
                        }}
                      >
                        <Td style={{ fontWeight: 700, fontSize: 13 }}>
                          <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                            {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                            {gruppo.codice}
                          </span>
                        </Td>
                        <Td style={{ fontWeight: 700, fontSize: 13 }}>
                          {gruppo.nome} ({gruppo.conti.length} conti)
                        </Td>
                        <Td></Td>
                        <Td align="right" mono style={{ fontWeight: 600, color: COLORS.success }}>
                          {formatEuro(gruppo.totale_dare)}
                        </Td>
                        <Td align="right" mono style={{ fontWeight: 600, color: COLORS.danger }}>
                          {formatEuro(gruppo.totale_avere)}
                        </Td>
                        {showSaldi && (
                          <>
                            <Td
                              align="right"
                              mono
                              style={{ fontWeight: 600, color: COLORS.success, background: COLORS.bgAlt }}
                            >
                              {saldoGruppo > 0 ? formatEuro(saldoGruppo) : '-'}
                            </Td>
                            <Td
                              align="right"
                              mono
                              style={{ fontWeight: 600, color: COLORS.danger, background: COLORS.bgAlt }}
                            >
                              {saldoGruppo < 0 ? formatEuro(Math.abs(saldoGruppo)) : '-'}
                            </Td>
                          </>
                        )}
                        <Td align="center" style={{ color: COLORS.textMuted, fontSize: 12 }}>
                          {gruppo.conti.reduce((s, c) => s + c.n_movimenti, 0)}
                        </Td>
                      </tr>

                      {/* Righe conti (se espanso) */}
                      {isExpanded &&
                        gruppo.conti.map((conto, idx) => {
                          const tc = TIPO_COLORS[conto.tipo] || {
                            variant: 'neutral',
                            label: conto.tipo,
                          };
                          return (
                            <React.Fragment key={conto.codice}>
                              <tr
                                style={{
                                  background: idx % 2 === 0 ? COLORS.card : COLORS.gray[50],
                                  borderBottom: `1px solid ${COLORS.gray[100]}`,
                                }}
                              >
                                <Td
                                  mono
                                  style={{
                                    padding: '8px 8px 8px 28px',
                                    fontSize: 13,
                                    color: COLORS.gray[600],
                                  }}
                                >
                                  {conto.codice}
                                </Td>
                                <Td style={{ color: COLORS.text }}>{conto.nome}</Td>
                                <Td align="center">
                                  <Badge variant={tc.variant}>{tc.label}</Badge>
                                </Td>
                                <Td
                                  align="right"
                                  mono
                                  style={{
                                    fontWeight: 500,
                                    color: conto.dare > 0 ? COLORS.success : COLORS.gray[300],
                                  }}
                                >
                                  {formatEuro(conto.dare)}
                                </Td>
                                <Td
                                  align="right"
                                  mono
                                  style={{
                                    fontWeight: 500,
                                    color: conto.avere > 0 ? COLORS.danger : COLORS.gray[300],
                                  }}
                                >
                                  {formatEuro(conto.avere)}
                                </Td>
                                {showSaldi && (
                                  <>
                                    <Td
                                      align="right"
                                      mono
                                      style={{
                                        fontWeight: 600,
                                        color: COLORS.success,
                                        background: COLORS.bgAlt,
                                      }}
                                    >
                                      {conto.saldo_dare > 0 ? formatEuro(conto.saldo_dare) : '-'}
                                    </Td>
                                    <Td
                                      align="right"
                                      mono
                                      style={{
                                        fontWeight: 600,
                                        color: COLORS.danger,
                                        background: COLORS.bgAlt,
                                      }}
                                    >
                                      {conto.saldo_avere > 0 ? formatEuro(conto.saldo_avere) : '-'}
                                    </Td>
                                  </>
                                )}
                                <Td align="center" style={{ fontSize: 12, color: COLORS.textMuted }}>
                                  {conto.n_movimenti}
                                </Td>
                              </tr>
                              {/* Dettaglio movimenti */}
                              {dettaglio && conto.movimenti?.length > 0 && (
                                <tr>
                                  <td
                                    colSpan={showSaldi ? 8 : 6}
                                    style={{ padding: '0 0 0 48px', background: COLORS.bgAlt }}
                                  >
                                    <Table style={{ fontSize: 12 }}>
                                      <thead>
                                        <tr>
                                          <Th style={{ padding: '4px 8px' }}>Data</Th>
                                          <Th style={{ padding: '4px 8px' }}>Descrizione</Th>
                                          <Th align="right" style={{ padding: '4px 8px' }}>
                                            Dare
                                          </Th>
                                          <Th align="right" style={{ padding: '4px 8px' }}>
                                            Avere
                                          </Th>
                                        </tr>
                                      </thead>
                                      <tbody>
                                        {conto.movimenti.map((m, mi) => (
                                          <tr key={mi} style={{ borderBottom: `1px solid ${COLORS.gray[100]}` }}>
                                            <Td style={{ padding: '3px 8px', color: COLORS.textMuted }}>
                                              {formatDateIT(m.data)}
                                            </Td>
                                            <Td style={{ padding: '3px 8px', color: COLORS.gray[700] }}>
                                              {m.descrizione}
                                            </Td>
                                            <Td
                                              align="right"
                                              mono
                                              style={{ padding: '3px 8px', color: COLORS.success }}
                                            >
                                              {m.dare > 0 ? formatEuro(m.dare) : ''}
                                            </Td>
                                            <Td
                                              align="right"
                                              mono
                                              style={{ padding: '3px 8px', color: COLORS.danger }}
                                            >
                                              {m.avere > 0 ? formatEuro(m.avere) : ''}
                                            </Td>
                                          </tr>
                                        ))}
                                      </tbody>
                                    </Table>
                                  </td>
                                </tr>
                              )}
                            </React.Fragment>
                          );
                        })}
                    </React.Fragment>
                  );
                })}
              </tbody>
              {/* Totali */}
              <tfoot>
                <tr
                  style={{ background: COLORS.primary, color: COLORS.card, fontWeight: 700, fontSize: 14 }}
                >
                  <td colSpan={2} style={{ padding: '14px 8px' }}>
                    TOTALE GENERALE
                  </td>
                  <td></td>
                  <td style={{ padding: '14px 8px', textAlign: 'right', fontFamily: FONT.mono }}>
                    {formatEuro(data.totali.dare)}
                  </td>
                  <td style={{ padding: '14px 8px', textAlign: 'right', fontFamily: FONT.mono }}>
                    {formatEuro(data.totali.avere)}
                  </td>
                  {showSaldi && (
                    <>
                      <td
                        style={{
                          padding: '14px 8px',
                          textAlign: 'right',
                          fontFamily: FONT.mono,
                          background: COLORS.primaryLight,
                        }}
                      >
                        {formatEuro(data.totali.saldo_dare)}
                      </td>
                      <td
                        style={{
                          padding: '14px 8px',
                          textAlign: 'right',
                          fontFamily: FONT.mono,
                          background: COLORS.primaryLight,
                        }}
                      >
                        {formatEuro(data.totali.saldo_avere)}
                      </td>
                    </>
                  )}
                  <td style={{ padding: '14px 8px', textAlign: 'center' }}>
                    {data.conti.reduce((s, c) => s + c.n_movimenti, 0)}
                  </td>
                </tr>
                <tr style={{ background: data.quadratura ? COLORS.successLight : COLORS.dangerLight }}>
                  <td
                    colSpan={showSaldi ? 8 : 6}
                    style={{
                      padding: '10px 8px',
                      textAlign: 'center',
                      fontWeight: 600,
                      fontSize: 14,
                      color: data.quadratura ? COLORS.success : COLORS.danger,
                    }}
                  >
                    {data.quadratura
                      ? '✓ Il bilancio di verifica quadra — Totale Dare = Totale Avere'
                      : `✗ SBILANCIO: ${formatEuro(data.totali.sbilancio)} — Verificare le registrazioni`}
                  </td>
                </tr>
              </tfoot>
            </Table>
          </TableWrap>

          {/* Note */}
          <div
            style={{
              marginTop: 24,
              padding: 16,
              background: COLORS.bgAlt,
              borderRadius: BORDER_RADIUS.md,
              border: `1px solid ${COLORS.border}`,
            }}
          >
            <p style={{ margin: 0, fontSize: 12, color: COLORS.textMuted }}>
              <strong>Fonti dati:</strong> Fatture ricevute, Corrispettivi, Prima Nota (Cassa +
              Banca + Salari), Cespiti/Ammortamenti. Generato il{' '}
              {data.data_generazione
                ? new Date(data.data_generazione).toLocaleString('it-IT')
                : '-'}
              .
            </p>
          </div>
        </>
      ) : bvError ? (
        <div style={{ textAlign: 'center', padding: 60, color: '#b91c1c' }}>
          <FileText size={48} style={{ margin: '0 auto 16px', opacity: 0.3 }} />
          <p>Errore nel caricamento del bilancio di verifica {anno}. Riprova con «Aggiorna».</p>
        </div>
      ) : (
        <div style={{ textAlign: 'center', padding: 60, color: COLORS.textMuted }}>
          <FileText size={48} style={{ margin: '0 auto 16px', opacity: 0.3 }} />
          <p>Nessun dato disponibile per l'anno {anno}</p>
        </div>
      )}
    </PageLayout>
  );
}
