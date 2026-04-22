import React, { useState, useEffect } from 'react';
import api from '../api';
import { formatEuro } from '../lib/utils';
import { useAnnoGlobale } from '../contexts/AnnoContext';
import { PageLayout, PageSection, PageGrid, PageLoading } from '../components/PageLayout';
import { Building2, TrendingUp, Percent, RefreshCw } from 'lucide-react';

const TIPO_COLORS = {
  operativo: { bg: '#dcfce7', color: '#16a34a', label: 'Operativo' },
  supporto: { bg: '#dbeafe', color: '#2563eb', label: 'Supporto' },
  struttura: { bg: '#fef3c7', color: '#d97706', label: 'Struttura' },
};

export default function CentriCosto() {
  const { anno } = useAnnoGlobale();
  const [centri, setCentri] = useState([]);
  const [loading, setLoading] = useState(true);
  const [assigning, setAssigning] = useState(false);
  const [stats, setStats] = useState({ totale: 0, operativi: 0, supporto: 0, struttura: 0 });

  useEffect(() => {
    loadCentri();
  }, []);

  async function loadCentri() {
    setLoading(true);
    try {
      const res = await api.get('/api/centri-costo');
      const data = res.data || [];
      setCentri(data);

      const operativi = data.filter(c => c.tipo === 'operativo');
      const supporto = data.filter(c => c.tipo === 'supporto');
      const struttura = data.filter(c => c.tipo === 'struttura');

      setStats({
        totale: data.reduce((sum, c) => sum + (c.fatture_totale || 0), 0),
        operativi: operativi.reduce((sum, c) => sum + (c.fatture_totale || 0), 0),
        supporto: supporto.reduce((sum, c) => sum + (c.fatture_totale || 0), 0),
        struttura: struttura.reduce((sum, c) => sum + (c.fatture_totale || 0), 0),
      });
    } catch (err) {
      console.error('Errore caricamento centri di costo:', err);
    } finally {
      setLoading(false);
    }
  }

  async function assegnaCDCFatture() {
    setAssigning(true);
    try {
      const res = await api.post(`/api/centri-costo/assegna-cdc-fatture?anno=${anno}`);
      alert(`Assegnati ${res.data.fatture_aggiornate} centri di costo`);
      loadCentri();
    } catch (err) {
      alert('Errore: ' + (err.response?.data?.detail || err.message));
    } finally {
      setAssigning(false);
    }
  }

  const grouped = {
    operativo: centri.filter(c => c.tipo === 'operativo'),
    supporto: centri.filter(c => c.tipo === 'supporto'),
    struttura: centri.filter(c => c.tipo === 'struttura'),
  };

  const KPICard = ({ label, value, color, bgColor, borderColor }) => (
    <div
      style={{
        background: bgColor,
        padding: 20,
        borderRadius: 12,
        border: `1px solid ${borderColor}`,
      }}
    >
      <div style={{ fontSize: 12, color: color, fontWeight: 600, textTransform: 'uppercase' }}>
        {label}
      </div>
      <div style={{ fontSize: 26, fontWeight: 700, color: color, marginTop: 4 }}>
        {formatEuro(value)}
      </div>
    </div>
  );

  return (
    <PageLayout
      title="Centri di Costo"
      icon={<Building2 size={28} />}
      subtitle="Contabilità analitica - Distribuzione costi per centro di responsabilità"
      actions={
        <button
          onClick={assegnaCDCFatture}
          disabled={assigning}
          data-testid="assign-cdc-btn"
          style={{
            padding: '10px 20px',
            background: 'linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%)',
            color: 'white',
            border: 'none',
            borderRadius: 8,
            cursor: assigning ? 'not-allowed' : 'pointer',
            fontSize: 14,
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            opacity: assigning ? 0.7 : 1,
          }}
        >
          <RefreshCw size={16} style={assigning ? { animation: 'spin 1s linear infinite' } : {}} />
          {assigning ? 'Assegnazione...' : `Assegna CDC Fatture ${anno}`}
        </button>
      }
    >
      {/* KPI Cards */}
      <PageGrid cols={4} gap={16}>
        <KPICard
          label="Centri Operativi"
          value={stats.operativi}
          color="#15803d"
          bgColor="#f0fdf4"
          borderColor="#86efac"
        />
        <KPICard
          label="Centri Supporto"
          value={stats.supporto}
          color="#1d4ed8"
          bgColor="#eff6ff"
          borderColor="#93c5fd"
        />
        <KPICard
          label="Costi Struttura"
          value={stats.struttura}
          color="#a16207"
          bgColor="#fefce8"
          borderColor="#fde047"
        />
        <KPICard
          label="Totale Costi"
          value={stats.totale}
          color="#334155"
          bgColor="#f8fafc"
          borderColor="#e2e8f0"
        />
      </PageGrid>

      {loading ? (
        <PageLoading message="Caricamento centri di costo..." />
      ) : (
        <>
          {/* Centri Operativi */}
          <PageSection
            title="Centri Operativi (generano ricavi)"
            icon={<TrendingUp size={20} color="#16a34a" />}
            style={{ marginTop: 24 }}
          >
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                gap: 16,
              }}
            >
              {grouped.operativo.map(centro => (
                <CDCCard key={centro.codice} centro={centro} />
              ))}
            </div>
          </PageSection>

          {/* Centri Supporto */}
          <PageSection
            title="Centri di Supporto (costi da ribaltare)"
            icon={<Percent size={20} color="#2563eb" />}
            style={{ marginTop: 24 }}
          >
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                gap: 16,
              }}
            >
              {grouped.supporto.map(centro => (
                <CDCCard key={centro.codice} centro={centro} />
              ))}
            </div>
          </PageSection>

          {/* Costi Struttura */}
          <PageSection
            title="Costi Generali / Struttura"
            icon={<Building2 size={20} color="#d97706" />}
            style={{ marginTop: 24 }}
          >
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                gap: 16,
              }}
            >
              {grouped.struttura.map(centro => (
                <CDCCard key={centro.codice} centro={centro} />
              ))}
            </div>
          </PageSection>
        </>
      )}

      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </PageLayout>
  );
}

function CDCCard({ centro }) {
  const tipo = TIPO_COLORS[centro.tipo] || TIPO_COLORS.operativo;

  return (
    <div
      style={{
        background: 'white',
        borderRadius: 12,
        border: `2px solid ${tipo.bg}`,
        overflow: 'hidden',
        transition: 'all 0.2s',
      }}
    >
      <div style={{ padding: '4px 0', background: tipo.bg }} />
      <div style={{ padding: 16 }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginBottom: 12,
          }}
        >
          <span
            style={{
              background: tipo.bg,
              color: tipo.color,
              padding: '4px 10px',
              borderRadius: 6,
              fontSize: 11,
              fontWeight: 600,
            }}
          >
            {centro.codice}
          </span>
          <span style={{ fontSize: 12, color: '#9ca3af' }}>{tipo.label}</span>
        </div>

        <h3 style={{ fontSize: 16, fontWeight: 600, color: '#1f2937', margin: '0 0 8px 0' }}>
          {centro.nome}
        </h3>

        <p style={{ fontSize: 13, color: '#6b7280', margin: '0 0 16px 0' }}>{centro.descrizione}</p>

        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            paddingTop: 12,
            borderTop: '1px solid #f3f4f6',
          }}
        >
          <div>
            <div style={{ fontSize: 11, color: '#9ca3af' }}>Fatture</div>
            <div style={{ fontSize: 16, fontWeight: 600, color: '#1f2937' }}>
              {centro.fatture_count || 0}
            </div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: 11, color: '#9ca3af' }}>Totale Costi</div>
            <div style={{ fontSize: 16, fontWeight: 700, color: tipo.color }}>
              {formatEuro(centro.fatture_totale || 0)}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
