import React, { useState, useEffect } from 'react';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { COLORS, FONT, formatEuro } from '../lib/utils';
import { Badge, StatCard, TableWrap, Table, Th, Td } from '../components/ds';
import {
  PageLayout,
  PageSection,
  PageGrid,
  PageLoading,
  PageEmpty,
} from '../components/PageLayout';
import {
  TrendingUp,
  TrendingDown,
  Wallet,
  Building2,
  Users,
  Receipt,
  AlertCircle,
  Info,
} from 'lucide-react';

export default function Finanziaria() {
  const { anno: selectedYear } = useAnnoGlobale();
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');

  useEffect(() => {
    loadSummary();
  }, [selectedYear]);

  async function loadSummary() {
    try {
      setLoading(true);
      setLoadError('');
      const r = await api.get(`/api/finanziaria/summary?anno=${selectedYear}`);
      setSummary(r.data);
    } catch (e) {
      console.error('Error loading financial summary:', e);
      setSummary(null);
      setLoadError(e.response?.data?.detail || e.message || 'Errore di caricamento');
    } finally {
      setLoading(false);
    }
  }

  if (loading) {
    return (
      <PageLayout
        title="Situazione Finanziaria"
        icon="📊"
        subtitle={`Riepilogo finanziario ${selectedYear}`}
      >
        <PageLoading message={`Caricamento dati finanziari per ${selectedYear}...`} />
      </PageLayout>
    );
  }

  if (loadError || !summary) {
    return (
      <PageLayout title="Situazione Finanziaria" icon="📊" subtitle={`Riepilogo finanziario ${selectedYear}`}>
        <div role="alert" style={{ padding: 20, border: `1px solid ${COLORS.danger}`, background: COLORS.dangerLight, borderRadius: 8 }}>
          <strong>Dati finanziari non disponibili.</strong>
          <div style={{ marginTop: 6, fontSize: 13 }}>{loadError || 'Il servizio non ha restituito un riepilogo valido.'}</div>
        </div>
      </PageLayout>
    );
  }

  const hasNoData = summary?.total_income === 0 && summary?.total_expenses === 0;

  return (
    <PageLayout
      title="Situazione Finanziaria"
      icon="📊"
      subtitle={`Riepilogo finanziario e stima IVA documentale - Anno ${selectedYear}`}
      actions={
        <Badge
          variant="info"
          style={{
            fontSize: 13,
            fontWeight: 600,
            padding: '10px 20px',
            textTransform: 'none',
            letterSpacing: 'normal',
          }}
        >
          📅 Anno: {selectedYear}
        </Badge>
      }
    >
      {/* Avviso nessun dato */}
      {hasNoData && (
        <div
          style={{
            background: COLORS.warningLight,
            borderRadius: 8,
            padding: 16,
            marginBottom: 20,
            border: `1px solid ${COLORS.warning}`,
            display: 'flex',
            alignItems: 'center',
            gap: 12,
          }}
        >
          <AlertCircle size={24} color={COLORS.warning} />
          <div>
            <div style={{ fontWeight: 600, color: COLORS.warning }}>
              Nessun movimento registrato per {selectedYear}
            </div>
            <div style={{ fontSize: 13, color: COLORS.warning, marginTop: 4 }}>
              Se hai dati per altri anni, seleziona un anno diverso dalla barra laterale.
            </div>
          </div>
        </div>
      )}

      {/* KPI Principali */}
      <PageGrid cols={3} gap={16}>
        <StatCard
          icon={<TrendingUp size={18} />}
          label="Entrate Totali"
          value={formatEuro(summary?.total_income)}
          subtext={`Cassa: ${formatEuro(summary?.cassa?.entrate)} | Banca: ${formatEuro(summary?.banca?.entrate)}`}
          accent="success"
        />
        <StatCard
          icon={<TrendingDown size={18} />}
          label="Uscite Totali"
          value={formatEuro(summary?.total_expenses)}
          subtext={`Cassa: ${formatEuro(summary?.cassa?.uscite)} | Banca: ${formatEuro(summary?.banca?.uscite)}`}
          accent="danger"
        />
        <StatCard
          icon={<Wallet size={18} />}
          label="Saldo"
          value={formatEuro(summary?.balance)}
          accent={summary?.balance >= 0 ? 'primary' : 'danger'}
        />
      </PageGrid>

      {/* Sezione IVA */}
      <PageSection title="Riepilogo IVA" icon="🧾" style={{ marginTop: 20 }}>
        <p style={{ color: COLORS.textMuted, fontSize: 13, marginBottom: 16 }}>
          Stima IVA da Corrispettivi XML e Fatture XML classificate. La liquidazione verificata,
          l'F24 e l'addebito bancario restano controlli distinti.
        </p>
        <PageGrid cols={3} gap={16}>
          <StatCard
            label="📤 IVA a DEBITO (Corrispettivi)"
            value={formatEuro(summary?.vat_debit)}
            subtext={
              <>
                Da {summary?.corrispettivi?.count || 0} corrispettivi
                <br />
                Totale vendite: {formatEuro(summary?.corrispettivi?.totale)}
              </>
            }
            accent="warning"
          />
          <StatCard
            label="📥 IVA a CREDITO (Fatture)"
            value={formatEuro(summary?.vat_credit)}
            subtext={
              <>
                Da {summary?.fatture?.count || 0} fatture
                <br />
                Totale acquisti: {formatEuro(summary?.fatture?.totale)}
              </>
            }
            accent="success"
          />
          <StatCard
            label="⚖️ Stima saldo IVA"
            value={formatEuro(summary?.vat_balance)}
            subtext={
              <Badge variant={summary?.vat_balance > 0 ? 'danger' : 'success'}>
                {summary?.vat_status || '-'}
              </Badge>
            }
            accent={summary?.vat_balance > 0 ? 'danger' : 'success'}
          />
        </PageGrid>
      </PageSection>

      {/* Dettaglio Prima Nota */}
      <PageSection title="Dettaglio Prima Nota" icon="📒" style={{ marginTop: 20 }}>
        <TableWrap>
          <Table>
            <thead>
              <tr>
                <Th align="left">Conto</Th>
                <Th align="right">Entrate</Th>
                <Th align="right">Uscite</Th>
                <Th align="right">Saldo</Th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <Td>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Wallet size={16} color={COLORS.textMuted} /> Cassa
                  </span>
                </Td>
                <Td align="right" mono style={{ color: COLORS.success, fontWeight: 500 }}>
                  {formatEuro(summary?.cassa?.entrate)}
                </Td>
                <Td align="right" mono style={{ color: COLORS.danger, fontWeight: 500 }}>
                  {formatEuro(summary?.cassa?.uscite)}
                </Td>
                <Td align="right" mono style={{ fontWeight: 600 }}>
                  {formatEuro(summary?.cassa?.saldo)}
                </Td>
              </tr>
              <tr>
                <Td>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Building2 size={16} color={COLORS.textMuted} /> Banca
                  </span>
                </Td>
                <Td align="right" mono style={{ color: COLORS.success, fontWeight: 500 }}>
                  {formatEuro(summary?.banca?.entrate)}
                </Td>
                <Td align="right" mono style={{ color: COLORS.danger, fontWeight: 500 }}>
                  {formatEuro(summary?.banca?.uscite)}
                </Td>
                <Td align="right" mono style={{ fontWeight: 600 }}>
                  {formatEuro(summary?.banca?.saldo)}
                </Td>
              </tr>
              <tr>
                <Td>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Users size={16} color={COLORS.textMuted} /> Salari
                  </span>
                </Td>
                <Td align="right">-</Td>
                <Td align="right" mono style={{ color: COLORS.danger, fontWeight: 500 }}>
                  {formatEuro(summary?.salari?.totale)}
                </Td>
                <Td align="right" mono style={{ fontWeight: 600, color: COLORS.danger }}>
                  -{formatEuro(summary?.salari?.totale)}
                </Td>
              </tr>
            </tbody>
            <tfoot>
              <tr style={{ background: COLORS.bgAlt, fontWeight: 600 }}>
                <Td style={{ fontWeight: 600 }}>TOTALE</Td>
                <Td align="right" mono style={{ fontWeight: 600, color: COLORS.success }}>
                  {formatEuro(summary?.total_income)}
                </Td>
                <Td align="right" mono style={{ fontWeight: 600, color: COLORS.danger }}>
                  {formatEuro(summary?.total_expenses)}
                </Td>
                <Td
                  align="right"
                  mono
                  style={{
                    fontWeight: 600,
                    color: summary?.balance >= 0 ? COLORS.success : COLORS.danger,
                  }}
                >
                  {formatEuro(summary?.balance)}
                </Td>
              </tr>
            </tfoot>
          </Table>
        </TableWrap>
      </PageSection>

      {/* Situazione Debiti/Crediti */}
      <PageSection title="Situazione Debiti/Crediti" icon="📋" style={{ marginTop: 20 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: 12,
              background: COLORS.dangerLight,
              borderRadius: 8,
            }}
          >
            <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Receipt size={16} color={COLORS.danger} />
              Fatture da pagare (debiti vs fornitori)
            </span>
            <span style={{ fontWeight: 700, color: COLORS.danger, fontFamily: FONT.mono }}>
              {formatEuro(summary?.payables)}
            </span>
          </div>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: 12,
              background: COLORS.successLight,
              borderRadius: 8,
            }}
          >
            <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Receipt size={16} color={COLORS.success} />
              Fatture da incassare (crediti vs clienti)
            </span>
            <span style={{ fontWeight: 700, color: COLORS.success, fontFamily: FONT.mono }}>
              {formatEuro(summary?.receivables)}
            </span>
          </div>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: 12,
              background: summary?.vat_balance > 0 ? COLORS.dangerLight : COLORS.successLight,
              borderRadius: 8,
            }}
          >
            <span>🧾 IVA {summary?.vat_balance > 0 ? 'da versare' : 'a credito'}</span>
            <span
              style={{
                fontWeight: 700,
                fontFamily: FONT.mono,
                color: summary?.vat_balance > 0 ? COLORS.danger : COLORS.success,
              }}
            >
              {formatEuro(Math.abs(summary?.vat_balance || 0))}
            </span>
          </div>
        </div>
      </PageSection>

      {/* Info */}
      <PageSection
        title="Come vengono calcolati i dati"
        icon={<Info size={18} />}
        style={{ marginTop: 20 }}
      >
        <ul style={{ paddingLeft: 20, lineHeight: 2, margin: 0, color: COLORS.gray[600], fontSize: 13 }}>
          <li>
            <strong>Entrate/Uscite:</strong> Somma movimenti Prima Nota Cassa + Banca
          </li>
          <li>
            <strong>IVA Debito:</strong> Estratta dai file XML dei Corrispettivi giornalieri
            (vendite)
          </li>
          <li>
            <strong>IVA Credito:</strong> Estratta dai file XML delle Fatture (acquisti fornitori)
          </li>
          <li>
            <strong>Saldo IVA:</strong> IVA Debito - IVA Credito = importo da versare o a credito
          </li>
          <li>
            <strong>Fatture da pagare:</strong> Fatture con stato diverso da "Pagata"
          </li>
        </ul>
      </PageSection>
    </PageLayout>
  );
}
