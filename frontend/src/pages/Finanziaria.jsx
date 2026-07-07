import React, { useState, useEffect } from 'react';
import api from '../api';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { formatEuro } from '../lib/utils';
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

const MONO = 'ui-monospace, SFMono-Regular, Menlo, monospace';

export default function Finanziaria() {
  const { anno: selectedYear } = useAnnoGlobale();
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadSummary();
  }, [selectedYear]);

  async function loadSummary() {
    try {
      setLoading(true);
      const r = await api
        .get(`/api/finanziaria/summary?anno=${selectedYear}`)
        .catch(() => ({ data: null }));
      setSummary(r.data);
    } catch (e) {
      console.error('Error loading financial summary:', e);
    } finally {
      setLoading(false);
    }
  }

  const KPICard = ({ icon: Icon, label, value, subtext, color }) => (
    <div
      style={{
        background: 'white',
        borderRadius: 8,
        padding: 20,
        border: '1px solid #e2e8f0',
        borderLeft: '4px solid #0f2744',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <Icon size={18} color={color || '#64748b'} />
        <span
          style={{
            fontSize: 11,
            color: '#64748b',
            textTransform: 'uppercase',
            letterSpacing: 0.5,
          }}
        >
          {label}
        </span>
      </div>
      <div style={{ fontSize: 24, fontWeight: 700, fontFamily: MONO, color: color || '#0f2744' }}>
        {value}
      </div>
      {subtext && <div style={{ fontSize: 12, color: '#64748b', marginTop: 6 }}>{subtext}</div>}
    </div>
  );

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

  const hasNoData = summary?.total_income === 0 && summary?.total_expenses === 0;

  return (
    <PageLayout
      title="Situazione Finanziaria"
      icon="📊"
      subtitle={`Riepilogo finanziario con IVA da Corrispettivi e Fatture - Anno ${selectedYear}`}
      actions={
        <div
          style={{
            background: '#eff6ff',
            border: '1px solid #bfdbfe',
            padding: '10px 20px',
            borderRadius: 6,
            color: '#1e40af',
            fontWeight: 600,
            fontSize: 13,
          }}
        >
          📅 Anno: {selectedYear}
        </div>
      }
    >
      {/* Avviso nessun dato */}
      {hasNoData && (
        <div
          style={{
            background: '#fffbeb',
            borderRadius: 8,
            padding: 16,
            marginBottom: 20,
            border: '1px solid #fde68a',
            display: 'flex',
            alignItems: 'center',
            gap: 12,
          }}
        >
          <AlertCircle size={24} color="#d97706" />
          <div>
            <div style={{ fontWeight: 600, color: '#92400e' }}>
              Nessun movimento registrato per {selectedYear}
            </div>
            <div style={{ fontSize: 13, color: '#92400e', marginTop: 4 }}>
              Se hai dati per altri anni, seleziona un anno diverso dalla barra laterale.
            </div>
          </div>
        </div>
      )}

      {/* KPI Principali */}
      <PageGrid cols={3} gap={16}>
        <KPICard
          icon={TrendingUp}
          label="Entrate Totali"
          value={formatEuro(summary?.total_income)}
          subtext={`Cassa: ${formatEuro(summary?.cassa?.entrate)} | Banca: ${formatEuro(summary?.banca?.entrate)}`}
          color="#16a34a"
        />
        <KPICard
          icon={TrendingDown}
          label="Uscite Totali"
          value={formatEuro(summary?.total_expenses)}
          subtext={`Cassa: ${formatEuro(summary?.cassa?.uscite)} | Banca: ${formatEuro(summary?.banca?.uscite)}`}
          color="#dc2626"
        />
        <KPICard
          icon={Wallet}
          label="Saldo"
          value={formatEuro(summary?.balance)}
          color={summary?.balance >= 0 ? '#0f2744' : '#dc2626'}
        />
      </PageGrid>

      {/* Sezione IVA */}
      <PageSection title="Riepilogo IVA" icon="🧾" style={{ marginTop: 20 }}>
        <p style={{ color: '#64748b', fontSize: 13, marginBottom: 16 }}>
          IVA estratta automaticamente da Corrispettivi XML (vendite) e Fatture XML (acquisti)
        </p>
        <PageGrid cols={3} gap={16}>
          <div
            style={{
              background: '#fffbeb',
              border: '1px solid #fde68a',
              padding: 16,
              borderRadius: 8,
            }}
          >
            <div style={{ fontSize: 12, fontWeight: 600, color: '#92400e', marginBottom: 4 }}>
              📤 IVA a DEBITO (Corrispettivi)
            </div>
            <div style={{ fontSize: 24, fontWeight: 700, fontFamily: MONO, color: '#d97706' }}>
              {formatEuro(summary?.vat_debit)}
            </div>
            <div style={{ fontSize: 12, color: '#64748b', marginTop: 8 }}>
              Da {summary?.corrispettivi?.count || 0} corrispettivi
              <br />
              Totale vendite: {formatEuro(summary?.corrispettivi?.totale)}
            </div>
          </div>
          <div
            style={{
              background: '#f0fdf4',
              border: '1px solid #bbf7d0',
              padding: 16,
              borderRadius: 8,
            }}
          >
            <div style={{ fontSize: 12, fontWeight: 600, color: '#15803d', marginBottom: 4 }}>
              📥 IVA a CREDITO (Fatture)
            </div>
            <div style={{ fontSize: 24, fontWeight: 700, fontFamily: MONO, color: '#16a34a' }}>
              {formatEuro(summary?.vat_credit)}
            </div>
            <div style={{ fontSize: 12, color: '#64748b', marginTop: 8 }}>
              Da {summary?.fatture?.count || 0} fatture
              <br />
              Totale acquisti: {formatEuro(summary?.fatture?.totale)}
            </div>
          </div>
          <div
            style={{
              background: summary?.vat_balance > 0 ? '#fef2f2' : '#f0fdf4',
              border: `1px solid ${summary?.vat_balance > 0 ? '#fecaca' : '#bbf7d0'}`,
              padding: 16,
              borderRadius: 8,
            }}
          >
            <div style={{ fontSize: 12, fontWeight: 600, color: '#64748b', marginBottom: 4 }}>
              ⚖️ Saldo IVA
            </div>
            <div
              style={{
                fontSize: 24,
                fontWeight: 700,
                fontFamily: MONO,
                color: summary?.vat_balance > 0 ? '#dc2626' : '#16a34a',
              }}
            >
              {formatEuro(summary?.vat_balance)}
            </div>
            <div style={{ marginTop: 8 }}>
              <span
                style={{
                  background: summary?.vat_balance > 0 ? '#dc2626' : '#16a34a',
                  color: 'white',
                  padding: '3px 10px',
                  borderRadius: 6,
                  fontSize: 11,
                  fontWeight: 600,
                }}
              >
                {summary?.vat_status || '-'}
              </span>
            </div>
          </div>
        </PageGrid>
      </PageSection>

      {/* Dettaglio Prima Nota */}
      <PageSection title="Dettaglio Prima Nota" icon="📒" style={{ marginTop: 20 }}>
        <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr
              style={{
                background: '#f8fafc',
                borderBottom: '1px solid #e2e8f0',
                fontSize: 11,
                textTransform: 'uppercase',
                color: '#64748b',
              }}
            >
              <th style={{ padding: 12, textAlign: 'left', fontWeight: 600 }}>Conto</th>
              <th style={{ padding: 12, textAlign: 'right', fontWeight: 600 }}>Entrate</th>
              <th style={{ padding: 12, textAlign: 'right', fontWeight: 600 }}>Uscite</th>
              <th style={{ padding: 12, textAlign: 'right', fontWeight: 600 }}>Saldo</th>
            </tr>
          </thead>
          <tbody>
            <tr style={{ borderBottom: '1px solid #f1f5f9' }}>
              <td style={{ padding: 12 }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Wallet size={16} color="#64748b" /> Cassa
                </span>
              </td>
              <td
                style={{
                  padding: 12,
                  textAlign: 'right',
                  color: '#16a34a',
                  fontWeight: 500,
                  fontFamily: MONO,
                }}
              >
                {formatEuro(summary?.cassa?.entrate)}
              </td>
              <td
                style={{
                  padding: 12,
                  textAlign: 'right',
                  color: '#dc2626',
                  fontWeight: 500,
                  fontFamily: MONO,
                }}
              >
                {formatEuro(summary?.cassa?.uscite)}
              </td>
              <td style={{ padding: 12, textAlign: 'right', fontWeight: 600, fontFamily: MONO }}>
                {formatEuro(summary?.cassa?.saldo)}
              </td>
            </tr>
            <tr style={{ borderBottom: '1px solid #f1f5f9' }}>
              <td style={{ padding: 12 }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Building2 size={16} color="#64748b" /> Banca
                </span>
              </td>
              <td
                style={{
                  padding: 12,
                  textAlign: 'right',
                  color: '#16a34a',
                  fontWeight: 500,
                  fontFamily: MONO,
                }}
              >
                {formatEuro(summary?.banca?.entrate)}
              </td>
              <td
                style={{
                  padding: 12,
                  textAlign: 'right',
                  color: '#dc2626',
                  fontWeight: 500,
                  fontFamily: MONO,
                }}
              >
                {formatEuro(summary?.banca?.uscite)}
              </td>
              <td style={{ padding: 12, textAlign: 'right', fontWeight: 600, fontFamily: MONO }}>
                {formatEuro(summary?.banca?.saldo)}
              </td>
            </tr>
            <tr style={{ borderBottom: '1px solid #f1f5f9' }}>
              <td style={{ padding: 12 }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Users size={16} color="#64748b" /> Salari
                </span>
              </td>
              <td style={{ padding: 12, textAlign: 'right' }}>-</td>
              <td
                style={{
                  padding: 12,
                  textAlign: 'right',
                  color: '#dc2626',
                  fontWeight: 500,
                  fontFamily: MONO,
                }}
              >
                {formatEuro(summary?.salari?.totale)}
              </td>
              <td
                style={{
                  padding: 12,
                  textAlign: 'right',
                  fontWeight: 600,
                  fontFamily: MONO,
                  color: '#dc2626',
                }}
              >
                -{formatEuro(summary?.salari?.totale)}
              </td>
            </tr>
          </tbody>
          <tfoot>
            <tr style={{ background: '#f8fafc', fontWeight: 600 }}>
              <td style={{ padding: 12 }}>TOTALE</td>
              <td style={{ padding: 12, textAlign: 'right', color: '#16a34a', fontFamily: MONO }}>
                {formatEuro(summary?.total_income)}
              </td>
              <td style={{ padding: 12, textAlign: 'right', color: '#dc2626', fontFamily: MONO }}>
                {formatEuro(summary?.total_expenses)}
              </td>
              <td
                style={{
                  padding: 12,
                  textAlign: 'right',
                  fontFamily: MONO,
                  color: summary?.balance >= 0 ? '#16a34a' : '#dc2626',
                }}
              >
                {formatEuro(summary?.balance)}
              </td>
            </tr>
          </tfoot>
        </table>
        </div>
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
              background: '#fef2f2',
              borderRadius: 8,
            }}
          >
            <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Receipt size={16} color="#dc2626" />
              Fatture da pagare (debiti vs fornitori)
            </span>
            <span style={{ fontWeight: 700, color: '#dc2626', fontFamily: MONO }}>
              {formatEuro(summary?.payables)}
            </span>
          </div>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: 12,
              background: '#f0fdf4',
              borderRadius: 8,
            }}
          >
            <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Receipt size={16} color="#16a34a" />
              Fatture da incassare (crediti vs clienti)
            </span>
            <span style={{ fontWeight: 700, color: '#16a34a', fontFamily: MONO }}>
              {formatEuro(summary?.receivables)}
            </span>
          </div>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: 12,
              background: summary?.vat_balance > 0 ? '#fef2f2' : '#f0fdf4',
              borderRadius: 8,
            }}
          >
            <span>🧾 IVA {summary?.vat_balance > 0 ? 'da versare' : 'a credito'}</span>
            <span
              style={{
                fontWeight: 700,
                fontFamily: MONO,
                color: summary?.vat_balance > 0 ? '#dc2626' : '#16a34a',
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
        <ul style={{ paddingLeft: 20, lineHeight: 2, margin: 0, color: '#475569', fontSize: 13 }}>
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
