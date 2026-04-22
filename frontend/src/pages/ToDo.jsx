import React, { useState, useEffect, useCallback } from 'react';
import api from '../api';
import { formatDateIT, STYLES, COLORS, button, badge } from '../lib/utils';
import { PageLayout } from '../components/PageLayout';
import { useAnnoGlobale } from '../contexts/AnnoContext';

/**
 * To-Do App - Gestione Task e Promemoria
 *
 * Funzionalità:
 * - Lista task con checkbox
 * - Priorità (alta/media/bassa) con colori
 * - Scadenze con promemoria visivi
 * - Filtri e ricerca
 * - Collegamento a documenti
 */
export default function ToDo() {
  const [tasks, setTasks] = useState([]);
  const [stats, setStats] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Filtri
  const [filtroStato, setFiltroStato] = useState('da_fare');
  const [filtroPriorita, setFiltroPriorita] = useState('');
  const [filtroCategoria, setFiltroCategoria] = useState('');
  const [cerca, setCerca] = useState('');

  // Form nuovo task
  const [showForm, setShowForm] = useState(false);
  const [nuovoTask, setNuovoTask] = useState({
    titolo: '',
    descrizione: '',
    priorita: 'media',
    scadenza: '',
    categoria: 'generale',
  });
  const [saving, setSaving] = useState(false);

  // Categorie disponibili
  const [categorie, setCategorie] = useState([]);

  const loadTasks = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filtroStato) params.append('stato', filtroStato);
      if (filtroPriorita) params.append('priorita', filtroPriorita);
      if (filtroCategoria) params.append('categoria', filtroCategoria);
      if (cerca) params.append('cerca', cerca);

      const res = await api.get(`/api/todo/lista?${params.toString()}`);
      setTasks(res.data.tasks || []);
      setStats(res.data.stats || {});
      setError('');
    } catch (e) {
      setError('Errore caricamento task');
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [filtroStato, filtroPriorita, filtroCategoria, cerca]);

  const loadCategorie = useCallback(async () => {
    try {
      const res = await api.get('/api/todo/categorie');
      setCategorie(res.data.categorie || []);
    } catch (e) {
      console.error('Errore caricamento categorie:', e);
    }
  }, []);

  useEffect(() => {
    loadTasks();
    loadCategorie();
  }, [loadTasks, loadCategorie]);

  const handleCreaTask = async e => {
    e.preventDefault();
    if (!nuovoTask.titolo.trim()) {
      alert('Inserisci un titolo');
      return;
    }

    setSaving(true);
    try {
      await api.post('/api/todo/crea', nuovoTask);
      setNuovoTask({
        titolo: '',
        descrizione: '',
        priorita: 'media',
        scadenza: '',
        categoria: 'generale',
      });
      setShowForm(false);
      loadTasks();
    } catch (e) {
      alert('Errore creazione task');
    } finally {
      setSaving(false);
    }
  };

  const handleToggleCompletato = async task => {
    try {
      if (task.completato) {
        await api.put(`/api/todo/${task.id}/riapri`);
      } else {
        await api.put(`/api/todo/${task.id}/completa`);
      }
      loadTasks();
    } catch (e) {
      alert('Errore aggiornamento task');
    }
  };

  const handleDeleteTask = async taskId => {
    if (!window.confirm('Eliminare questo task?')) return;

    try {
      await api.delete(`/api/todo/${taskId}`);
      loadTasks();
    } catch (e) {
      alert('Errore eliminazione task');
    }
  };

  // Colori priorità
  const getPriorityColor = priorita => {
    switch (priorita) {
      case 'alta':
        return { bg: '#fef2f2', border: '#ef4444', text: '#dc2626' };
      case 'media':
        return { bg: '#fefce8', border: '#eab308', text: '#ca8a04' };
      case 'bassa':
        return { bg: '#f0fdf4', border: '#22c55e', text: '#16a34a' };
      default:
        return { bg: '#f8fafc', border: '#94a3b8', text: '#64748b' };
    }
  };

  // Verifica scadenza
  const getScadenzaStatus = scadenza => {
    if (!scadenza) return null;

    const oggi = new Date();
    oggi.setHours(0, 0, 0, 0);
    const dataScadenza = new Date(scadenza);
    dataScadenza.setHours(0, 0, 0, 0);

    const diffGiorni = Math.ceil((dataScadenza - oggi) / (1000 * 60 * 60 * 24));

    if (diffGiorni < 0) return { label: 'Scaduto', color: '#ef4444', bg: '#fef2f2' };
    if (diffGiorni === 0) return { label: 'Oggi', color: '#f59e0b', bg: '#fefce8' };
    if (diffGiorni <= 3) return { label: `Tra ${diffGiorni}g`, color: '#f59e0b', bg: '#fefce8' };
    return { label: formatDateIT(scadenza), color: '#64748b', bg: 'transparent' };
  };

  return (
    <PageLayout
      title="To-Do"
      icon="📝"
      subtitle="Gestisci task e promemoria"
      actions={
        <button
          onClick={() => setShowForm(!showForm)}
          style={{
            padding: '12px 24px',
            background: '#4f46e5',
            color: 'white',
            border: 'none',
            borderRadius: 8,
            fontWeight: 'bold',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}
          data-testid="btn-nuovo-task"
        >
          {showForm ? '✕ Chiudi' : '+ Nuovo Task'}
        </button>
      }
    >
      {/* Stats Cards */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
          gap: 16,
          marginBottom: 24,
        }}
      >
        <StatCard label="Da Fare" value={stats.da_fare || 0} color="#3b82f6" />
        <StatCard label="Completati" value={stats.completati || 0} color="#22c55e" />
        <StatCard label="Urgenti" value={stats.urgenti || 0} color="#f59e0b" />
        <StatCard label="Scaduti" value={stats.scaduti || 0} color="#ef4444" />
      </div>

      {/* Form Nuovo Task */}
      {showForm && (
        <div
          style={{
            background: 'white',
            borderRadius: 12,
            padding: 24,
            marginBottom: 24,
            border: '1px solid #e5e7eb',
            boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
          }}
        >
          <h3 style={{ margin: '0 0 16px 0', color: '#1e293b' }}>Nuovo Task</h3>
          <form onSubmit={handleCreaTask}>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                gap: 16,
              }}
            >
              {/* Titolo */}
              <div style={{ gridColumn: 'span 2' }}>
                <label
                  style={{
                    display: 'block',
                    fontSize: 12,
                    fontWeight: 600,
                    color: '#374151',
                    marginBottom: 4,
                  }}
                >
                  Titolo *
                </label>
                <input
                  type="text"
                  value={nuovoTask.titolo}
                  onChange={e => setNuovoTask({ ...nuovoTask, titolo: e.target.value })}
                  placeholder="Cosa devi fare?"
                  style={{
                    width: '100%',
                    padding: '10px 12px',
                    border: '1px solid #d1d5db',
                    borderRadius: 8,
                    fontSize: 14,
                  }}
                  data-testid="input-titolo"
                />
              </div>

              {/* Priorità */}
              <div>
                <label
                  style={{
                    display: 'block',
                    fontSize: 12,
                    fontWeight: 600,
                    color: '#374151',
                    marginBottom: 4,
                  }}
                >
                  Priorità
                </label>
                <select
                  value={nuovoTask.priorita}
                  onChange={e => setNuovoTask({ ...nuovoTask, priorita: e.target.value })}
                  style={{
                    width: '100%',
                    padding: '10px 12px',
                    border: '1px solid #d1d5db',
                    borderRadius: 8,
                    fontSize: 14,
                    background: 'white',
                  }}
                  data-testid="select-priorita"
                >
                  <option value="alta">🔴 Alta</option>
                  <option value="media">🟡 Media</option>
                  <option value="bassa">🟢 Bassa</option>
                </select>
              </div>

              {/* Scadenza */}
              <div>
                <label
                  style={{
                    display: 'block',
                    fontSize: 12,
                    fontWeight: 600,
                    color: '#374151',
                    marginBottom: 4,
                  }}
                >
                  Scadenza
                </label>
                <input
                  type="date"
                  value={nuovoTask.scadenza}
                  onChange={e => setNuovoTask({ ...nuovoTask, scadenza: e.target.value })}
                  style={{
                    width: '100%',
                    padding: '10px 12px',
                    border: '1px solid #d1d5db',
                    borderRadius: 8,
                    fontSize: 14,
                  }}
                  data-testid="input-scadenza"
                />
              </div>

              {/* Categoria */}
              <div>
                <label
                  style={{
                    display: 'block',
                    fontSize: 12,
                    fontWeight: 600,
                    color: '#374151',
                    marginBottom: 4,
                  }}
                >
                  Categoria
                </label>
                <select
                  value={nuovoTask.categoria}
                  onChange={e => setNuovoTask({ ...nuovoTask, categoria: e.target.value })}
                  style={{
                    width: '100%',
                    padding: '10px 12px',
                    border: '1px solid #d1d5db',
                    borderRadius: 8,
                    fontSize: 14,
                    background: 'white',
                  }}
                  data-testid="select-categoria"
                >
                  {categorie.map(cat => (
                    <option key={cat} value={cat}>
                      {cat}
                    </option>
                  ))}
                </select>
              </div>

              {/* Descrizione */}
              <div style={{ gridColumn: 'span 2' }}>
                <label
                  style={{
                    display: 'block',
                    fontSize: 12,
                    fontWeight: 600,
                    color: '#374151',
                    marginBottom: 4,
                  }}
                >
                  Descrizione
                </label>
                <textarea
                  value={nuovoTask.descrizione}
                  onChange={e => setNuovoTask({ ...nuovoTask, descrizione: e.target.value })}
                  placeholder="Dettagli aggiuntivi..."
                  rows={3}
                  style={{
                    width: '100%',
                    padding: '10px 12px',
                    border: '1px solid #d1d5db',
                    borderRadius: 8,
                    fontSize: 14,
                    resize: 'vertical',
                  }}
                  data-testid="input-descrizione"
                />
              </div>
            </div>

            <div style={{ marginTop: 16, display: 'flex', gap: 12 }}>
              <button
                type="submit"
                disabled={saving}
                style={{
                  padding: '10px 24px',
                  background: '#4f46e5',
                  color: 'white',
                  border: 'none',
                  borderRadius: 8,
                  fontWeight: 'bold',
                  cursor: saving ? 'wait' : 'pointer',
                  opacity: saving ? 0.7 : 1,
                }}
                data-testid="btn-salva-task"
              >
                {saving ? '⏳ Salvataggio...' : '✓ Crea Task'}
              </button>
              <button
                type="button"
                onClick={() => setShowForm(false)}
                style={{
                  padding: '10px 24px',
                  background: '#f1f5f9',
                  color: '#64748b',
                  border: 'none',
                  borderRadius: 8,
                  cursor: 'pointer',
                }}
              >
                Annulla
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Filtri */}
      <div
        style={{
          display: 'flex',
          gap: 12,
          marginBottom: 20,
          flexWrap: 'wrap',
          alignItems: 'center',
        }}
      >
        {/* Ricerca */}
        <input
          type="text"
          placeholder="🔍 Cerca task..."
          value={cerca}
          onChange={e => setCerca(e.target.value)}
          style={{
            padding: '8px 12px',
            border: '1px solid #d1d5db',
            borderRadius: 8,
            fontSize: 14,
            width: 200,
          }}
          data-testid="input-cerca"
        />

        {/* Filtro Stato */}
        <select
          value={filtroStato}
          onChange={e => setFiltroStato(e.target.value)}
          style={{
            padding: '8px 12px',
            border: '1px solid #d1d5db',
            borderRadius: 8,
            fontSize: 14,
            background: 'white',
          }}
          data-testid="filtro-stato"
        >
          <option value="">Tutti gli stati</option>
          <option value="da_fare">Da fare</option>
          <option value="completato">Completati</option>
        </select>

        {/* Filtro Priorità */}
        <select
          value={filtroPriorita}
          onChange={e => setFiltroPriorita(e.target.value)}
          style={{
            padding: '8px 12px',
            border: '1px solid #d1d5db',
            borderRadius: 8,
            fontSize: 14,
            background: 'white',
          }}
          data-testid="filtro-priorita"
        >
          <option value="">Tutte le priorità</option>
          <option value="alta">🔴 Alta</option>
          <option value="media">🟡 Media</option>
          <option value="bassa">🟢 Bassa</option>
        </select>

        {/* Filtro Categoria */}
        <select
          value={filtroCategoria}
          onChange={e => setFiltroCategoria(e.target.value)}
          style={{
            padding: '8px 12px',
            border: '1px solid #d1d5db',
            borderRadius: 8,
            fontSize: 14,
            background: 'white',
          }}
          data-testid="filtro-categoria"
        >
          <option value="">Tutte le categorie</option>
          {categorie.map(cat => (
            <option key={cat} value={cat}>
              {cat}
            </option>
          ))}
        </select>

        {/* Contatore */}
        <span style={{ fontSize: 14, color: '#64748b' }}>{tasks.length} task</span>
      </div>

      {/* Error */}
      {error && (
        <div
          style={{
            padding: 16,
            background: '#fef2f2',
            color: '#dc2626',
            borderRadius: 8,
            marginBottom: 16,
          }}
        >
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div style={{ textAlign: 'center', padding: 40, color: '#64748b' }}>⏳ Caricamento...</div>
      )}

      {/* Lista Task */}
      {!loading && tasks.length === 0 && (
        <div
          style={{
            textAlign: 'center',
            padding: 60,
            color: '#64748b',
            background: '#f8fafc',
            borderRadius: 12,
          }}
        >
          <div style={{ fontSize: 48, marginBottom: 16 }}>📋</div>
          <p style={{ margin: 0 }}>Nessun task trovato</p>
          <p style={{ margin: '8px 0 0 0', fontSize: 14 }}>
            Crea il tuo primo task cliccando su "+ Nuovo Task"
          </p>
        </div>
      )}

      {!loading && tasks.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {tasks.map(task => {
            const priorityColors = getPriorityColor(task.priorita);
            const scadenzaStatus = getScadenzaStatus(task.scadenza);

            return (
              <div
                key={task.id}
                style={{
                  background: 'white',
                  borderRadius: 12,
                  padding: 16,
                  border: `1px solid ${task.completato ? '#e5e7eb' : priorityColors.border}`,
                  borderLeft: `4px solid ${task.completato ? '#94a3b8' : priorityColors.border}`,
                  opacity: task.completato ? 0.7 : 1,
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: 12,
                  transition: 'all 0.2s',
                }}
                data-testid={`task-${task.id}`}
              >
                {/* Checkbox */}
                <input
                  type="checkbox"
                  checked={task.completato || false}
                  onChange={() => handleToggleCompletato(task)}
                  style={{
                    width: 20,
                    height: 20,
                    cursor: 'pointer',
                    accentColor: '#4f46e5',
                    marginTop: 2,
                  }}
                  data-testid={`checkbox-${task.id}`}
                />

                {/* Contenuto */}
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <span
                      style={{
                        fontWeight: 600,
                        fontSize: 16,
                        textDecoration: task.completato ? 'line-through' : 'none',
                        color: task.completato ? '#94a3b8' : '#1e293b',
                      }}
                    >
                      {task.titolo}
                    </span>

                    {/* Badge Priorità */}
                    <span
                      style={{
                        padding: '2px 8px',
                        borderRadius: 12,
                        fontSize: 11,
                        fontWeight: 600,
                        background: priorityColors.bg,
                        color: priorityColors.text,
                        textTransform: 'uppercase',
                      }}
                    >
                      {task.priorita}
                    </span>

                    {/* Badge Categoria */}
                    <span
                      style={{
                        padding: '2px 8px',
                        borderRadius: 12,
                        fontSize: 11,
                        background: '#f1f5f9',
                        color: '#64748b',
                      }}
                    >
                      {task.categoria}
                    </span>

                    {/* Badge Scadenza */}
                    {scadenzaStatus && (
                      <span
                        style={{
                          padding: '2px 8px',
                          borderRadius: 12,
                          fontSize: 11,
                          fontWeight: 600,
                          background: scadenzaStatus.bg,
                          color: scadenzaStatus.color,
                        }}
                      >
                        📅 {scadenzaStatus.label}
                      </span>
                    )}
                  </div>

                  {task.descrizione && (
                    <p
                      style={{
                        margin: '8px 0 0 0',
                        fontSize: 14,
                        color: '#64748b',
                        textDecoration: task.completato ? 'line-through' : 'none',
                      }}
                    >
                      {task.descrizione}
                    </p>
                  )}

                  {/* Data completamento */}
                  {task.completato && task.completato_at && (
                    <p style={{ margin: '8px 0 0 0', fontSize: 12, color: '#94a3b8' }}>
                      ✓ Completato il {formatDateIT(task.completato_at)}
                    </p>
                  )}
                </div>

                {/* Azioni */}
                <button
                  onClick={() => handleDeleteTask(task.id)}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    color: '#94a3b8',
                    cursor: 'pointer',
                    padding: 8,
                    borderRadius: 4,
                    fontSize: 16,
                  }}
                  title="Elimina"
                  data-testid={`btn-delete-${task.id}`}
                >
                  🗑️
                </button>
              </div>
            );
          })}
        </div>
      )}
    </PageLayout>
  );
}

// Componente StatCard
function StatCard({ label, value, color }) {
  return (
    <div
      style={{
        background: 'white',
        borderRadius: 12,
        padding: 16,
        border: '1px solid #e5e7eb',
        textAlign: 'center',
      }}
    >
      <div style={{ fontSize: 28, fontWeight: 'bold', color }}>{value}</div>
      <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>{label}</div>
    </div>
  );
}
