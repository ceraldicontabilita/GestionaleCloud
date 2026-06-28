/**
 * Learning Machine Universale - SEMPLIFICATO
 * Un solo bottone: Impara tutto e mostra i risultati
 */

import React, { useState, useEffect } from 'react';
import api from '../api';
import {
  Brain,
  CheckCircle,
  TrendingUp,
  Users,
  CreditCard,
  Calendar,
  FileText,
} from 'lucide-react';

export default function LearningMachineUniversale() {
  const [status, setStatus] = useState(null);
  const [results, setResults] = useState(null);
  const [training, setTraining] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [statusRes, resultsRes] = await Promise.all([
        api.get('/api/learning-universal/status'),
        api.get('/api/learning-universal/results'),
      ]);
      setStatus(statusRes.data);
      if (resultsRes.data.status !== 'no_results') {
        setResults(resultsRes.data);
      }
    } catch (e) {
      console.error('Errore:', e);
    }
  };

  const startLearning = async () => {
    setTraining(true);
    setError(null);
    try {
      const res = await api.post('/api/learning-universal/train/all');
      if (res.data.status === 'completed') {
        setResults(res.data);
        await loadData();
      } else {
        setError(res.data.error || 'Errore sconosciuto');
      }
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    }
    setTraining(false);
  };

  const getModuleResult = moduleId => results?.modules?.[moduleId] || null;

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto', padding: 24 }}>
      {/* Header Semplice */}
      <div
        style={{
          textAlign: 'center',
          marginBottom: 32,
          padding: '32px 24px',
          background: '#1d4ed8',
          borderRadius: 16,
          color: 'white',
        }}
      >
        <Brain size={48} style={{ marginBottom: 12 }} />
        <h1 style={{ margin: '0 0 8px', fontSize: 28, fontWeight: 700 }}>Learning Machine</h1>
        <p style={{ margin: '0 0 24px', opacity: 0.9, fontSize: 15 }}>
          Analizza automaticamente tutti i dati per migliorare le associazioni e previsioni
        </p>

        {/* UN SOLO BOTTONE */}
        <button
          onClick={startLearning}
          disabled={training}
          style={{
            padding: '16px 40px',
            fontSize: 18,
            fontWeight: 700,
            background: training ? 'rgba(255,255,255,0.3)' : 'white',
            color: training ? 'white' : '#6366f1',
            border: 'none',
            borderRadius: 12,
            cursor: training ? 'wait' : 'pointer',
            display: 'inline-flex',
            alignItems: 'center',
            gap: 12,
            boxShadow: '0 4px 15px rgba(0,0,0,0.2)',
            transition: 'transform 0.2s',
          }}
        >
          {training ? (
            <>
              <div
                style={{
                  width: 24,
                  height: 24,
                  border: '3px solid rgba(99,102,241,0.3)',
                  borderTopColor: '#6366f1',
                  borderRadius: '50%',
                  animation: 'spin 1s linear infinite',
                }}
              />
              Sto imparando...
            </>
          ) : (
            <>
              <Brain size={24} />
              🧠 Impara Tutto
            </>
          )}
        </button>

        {results?.completed_at && (
          <p style={{ margin: '16px 0 0', fontSize: 13, opacity: 0.8 }}>
            Ultimo apprendimento: {new Date(results.completed_at).toLocaleString('it-IT')}
          </p>
        )}
      </div>

      {error && (
        <div
          style={{
            padding: 16,
            background: '#fef2f2',
            border: '1px solid #fca5a5',
            borderRadius: 12,
            color: '#dc2626',
            marginBottom: 24,
            textAlign: 'center',
          }}
        >
          ⚠️ Errore: {error}
        </div>
      )}

      {/* Dati Disponibili */}
      {status && (
        <div
          style={{
            background: 'white',
            borderRadius: 12,
            padding: 20,
            marginBottom: 24,
            border: '1px solid #e2e8f0',
          }}
        >
          <h3 style={{ margin: '0 0 16px', fontSize: 14, color: '#64748b', fontWeight: 600 }}>
            📊 Dati disponibili per l'apprendimento
          </h3>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
            {Object.entries(status.collections || {}).map(([name, count]) => (
              <div
                key={name}
                style={{
                  padding: '8px 16px',
                  background: count > 0 ? '#dcfce7' : '#f1f5f9',
                  borderRadius: 8,
                  fontSize: 13,
                  fontWeight: 500,
                  color: count > 0 ? '#16a34a' : '#94a3b8',
                }}
              >
                {name}: <strong>{count.toLocaleString()}</strong>
              </div>
            ))}
          </div>
          <div style={{ marginTop: 12, fontSize: 13, color: '#64748b' }}>
            Totale: <strong>{status.total_documents?.toLocaleString() || 0}</strong> documenti
          </div>
        </div>
      )}

      {/* RISULTATI - Cosa ha imparato */}
      {results?.modules && (
        <div>
          <h2
            style={{
              margin: '0 0 20px',
              fontSize: 18,
              fontWeight: 700,
              color: '#1e293b',
              display: 'flex',
              alignItems: 'center',
              gap: 8,
            }}
          >
            <CheckCircle size={24} color="#10b981" />
            Cosa ho imparato
          </h2>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
              gap: 16,
            }}
          >
            {/* Fornitori */}
            {getModuleResult('fornitori') && (
              <ResultCard
                icon={<Users size={24} />}
                color="#3b82f6"
                title="Fornitori"
                analyzed={getModuleResult('fornitori').total_analyzed}
                insights={[
                  `${getModuleResult('fornitori').patterns_found} pattern trovati`,
                  ...Object.entries(getModuleResult('fornitori').payment_methods || {})
                    .slice(0, 3)
                    .map(([m, c]) => `${m}: ${c} fornitori`),
                ]}
                benefit="→ Suggerisco metodo pagamento per nuovi fornitori"
              />
            )}

            {/* Stagionalità */}
            {getModuleResult('stagionalita') && (
              <ResultCard
                icon={<Calendar size={24} />}
                color="#f59e0b"
                title="Stagionalità Vendite"
                analyzed={getModuleResult('stagionalita').total_analyzed}
                insights={[
                  `Trend: ${getModuleResult('stagionalita').trend === 'growing' ? '📈 In crescita' : getModuleResult('stagionalita').trend === 'declining' ? '📉 In calo' : '➡️ Stabile'}`,
                  getModuleResult('stagionalita').peak_months?.length > 0
                    ? `Mesi migliori: ${getModuleResult('stagionalita').peak_months.join(', ')}`
                    : 'Analizzando pattern mensili...',
                ]}
                benefit="→ Prevedo gli incassi dei prossimi mesi"
              />
            )}

            {/* Assegni */}
            {getModuleResult('assegni') && (
              <ResultCard
                icon={<FileText size={24} />}
                color="#ef4444"
                title="Assegni"
                analyzed={getModuleResult('assegni').total_analyzed}
                insights={[
                  `${getModuleResult('assegni').associations_found} già associati`,
                  `Tasso successo: ${getModuleResult('assegni').success_rate}%`,
                  getModuleResult('assegni').common_patterns?.length > 0
                    ? `Pattern: ${getModuleResult('assegni')
                        .common_patterns.slice(0, 2)
                        .map(p => p[0])
                        .join(', ')}`
                    : '',
                ].filter(Boolean)}
                benefit="→ Associo automaticamente assegni a fatture"
              />
            )}

            {/* Pagamenti */}
            {getModuleResult('pagamenti') && (
              <ResultCard
                icon={<CreditCard size={24} />}
                color="#10b981"
                title="Tempi Pagamento"
                analyzed={getModuleResult('pagamenti').total_analyzed}
                insights={[
                  getModuleResult('pagamenti').avg_payment_days > 0
                    ? `Media: ${getModuleResult('pagamenti').avg_payment_days} giorni`
                    : 'Raccolgo dati sui pagamenti...',
                  `${getModuleResult('pagamenti').patterns_found} fornitori analizzati`,
                ]}
                benefit="→ Prevedo quando arriveranno i pagamenti"
              />
            )}

            {/* Movimenti */}
            {getModuleResult('movimenti') && (
              <ResultCard
                icon={<TrendingUp size={24} />}
                color="#8b5cf6"
                title="Movimenti Bancari"
                analyzed={getModuleResult('movimenti').total_analyzed}
                insights={[
                  `${getModuleResult('movimenti').categories_found} categorie trovate`,
                  Object.keys(getModuleResult('movimenti').keywords || {}).length > 0
                    ? `${Object.keys(getModuleResult('movimenti').keywords).length} parole chiave`
                    : 'Raccolgo dati movimenti...',
                ]}
                benefit="→ Categorizzo automaticamente i movimenti"
              />
            )}
          </div>
        </div>
      )}

      {/* Se non ci sono risultati */}
      {!results?.modules && !training && (
        <div
          style={{
            textAlign: 'center',
            padding: 60,
            background: '#f8fafc',
            borderRadius: 16,
            color: '#64748b',
          }}
        >
          <Brain size={64} style={{ opacity: 0.3, marginBottom: 16 }} />
          <p style={{ fontSize: 16, margin: 0 }}>
            Clicca <strong>"🧠 Impara Tutto"</strong> per iniziare l'analisi
          </p>
          <p style={{ fontSize: 14, margin: '8px 0 0', opacity: 0.7 }}>
            Il sistema analizzerà tutti i tuoi dati e imparerà i pattern
          </p>
        </div>
      )}

      <style>{`
        @keyframes spin {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}

// Componente Card Risultato
function ResultCard({ icon, color, title, analyzed, insights, benefit }) {
  return (
    <div
      style={{
        background: 'white',
        borderRadius: 12,
        padding: 20,
        border: '1px solid #e2e8f0',
        borderLeft: `4px solid ${color}`,
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          marginBottom: 12,
        }}
      >
        <div style={{ color }}>{icon}</div>
        <div>
          <h4 style={{ margin: 0, fontSize: 15, fontWeight: 600, color: '#1e293b' }}>{title}</h4>
          <span style={{ fontSize: 12, color: '#64748b' }}>
            {analyzed.toLocaleString()} analizzati
          </span>
        </div>
      </div>

      <ul
        style={{
          margin: '0 0 12px',
          padding: '0 0 0 16px',
          fontSize: 13,
          color: '#475569',
        }}
      >
        {insights.map((insight, i) => (
          <li key={i} style={{ marginBottom: 4 }}>
            {insight}
          </li>
        ))}
      </ul>

      <div
        style={{
          padding: '8px 12px',
          background: `${color}15`,
          borderRadius: 6,
          fontSize: 12,
          fontWeight: 500,
          color: color,
        }}
      >
        {benefit}
      </div>
    </div>
  );
}
