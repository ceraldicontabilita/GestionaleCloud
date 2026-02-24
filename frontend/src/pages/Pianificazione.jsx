import React, { useState, useEffect } from "react";
import api from "../api";
import { PageLayout, PageSection, PageLoading, PageEmpty } from '../components/PageLayout';
import { Calendar, Plus, RefreshCw, X } from 'lucide-react';

export default function Pianificazione() {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [err, setErr] = useState("");
  const [newEvent, setNewEvent] = useState({
    title: "",
    date: new Date().toISOString().split("T")[0],
    time: "09:00",
    type: "meeting",
    notes: ""
  });

  useEffect(() => {
    loadEvents();
  }, []);

  async function loadEvents() {
    try {
      setLoading(true);
      const r = await api.get("/api/pianificazione/events");
      setEvents(Array.isArray(r.data) ? r.data : r.data?.items || []);
    } catch (e) {
      console.error("Error loading events:", e);
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateEvent(e) {
    e.preventDefault();
    setErr("");
    try {
      await api.post("/api/pianificazione/events", {
        title: newEvent.title,
        scheduled_date: `${newEvent.date}T${newEvent.time}:00`,
        event_type: newEvent.type,
        notes: newEvent.notes,
        status: "scheduled"
      });
      setShowForm(false);
      setNewEvent({ title: "", date: new Date().toISOString().split("T")[0], time: "09:00", type: "meeting", notes: "" });
      loadEvents();
    } catch (e) {
      setErr("Errore: " + (e.response?.data?.detail || e.message));
    }
  }

  function getEventColor(type) {
    const colors = {
      meeting: "#dbeafe",
      deadline: "#fef2f2",
      reminder: "#fef3c7",
      task: "#dcfce7"
    };
    return colors[type] || "#f1f5f9";
  }

  function getEventIcon(type) {
    const icons = { meeting: "🤝", deadline: "⏰", reminder: "🔔", task: "✅" };
    return icons[type] || "📌";
  }

  const inputStyle = {
    padding: '10px 14px',
    borderRadius: 8,
    border: '1px solid #e2e8f0',
    fontSize: 14,
    minWidth: 150
  };

  const selectStyle = {
    padding: '10px 14px',
    borderRadius: 8,
    border: '1px solid #e2e8f0',
    fontSize: 14,
    background: 'white',
    cursor: 'pointer',
    minWidth: 130
  };

  return (
    <PageLayout
      title="Pianificazione"
      icon={<Calendar size={28} />}
      subtitle="Gestisci eventi, scadenze, riunioni e promemoria"
      actions={
        <div style={{ display: 'flex', gap: 10 }}>
          <button 
            onClick={() => setShowForm(!showForm)}
            data-testid="btn-nuovo-evento"
            style={{
              padding: '10px 16px',
              background: 'linear-gradient(135deg, #1535a8, #1535a8)',
              color: 'white',
              border: 'none',
              borderRadius: 8,
              cursor: 'pointer',
              fontWeight: 600,
              fontSize: 14,
              display: 'flex',
              alignItems: 'center',
              gap: 6
            }}
          >
            <Plus size={16} /> Nuovo Evento
          </button>
          <button 
            onClick={loadEvents}
            style={{
              padding: '10px 16px',
              background: '#f1f5f9',
              color: '#475569',
              border: '1px solid #e2e8f0',
              borderRadius: 8,
              cursor: 'pointer',
              fontWeight: 500,
              fontSize: 14,
              display: 'flex',
              alignItems: 'center',
              gap: 6
            }}
          >
            <RefreshCw size={16} /> Aggiorna
          </button>
        </div>
      }
    >
      {err && (
        <div style={{ 
          color: '#dc2626', 
          fontSize: 13, 
          padding: 12, 
          background: '#fef2f2', 
          borderRadius: 8,
          marginBottom: 16,
          border: '1px solid #fecaca'
        }}>
          {err}
        </div>
      )}

      {/* Form Nuovo Evento */}
      {showForm && (
        <PageSection title="Nuovo Evento" icon="✨" style={{ marginBottom: 20 }}>
          <button 
            onClick={() => setShowForm(false)} 
            style={{ 
              position: 'absolute', 
              top: 16, 
              right: 16, 
              background: 'none', 
              border: 'none', 
              cursor: 'pointer',
              padding: 4
            }}
          >
            <X size={20} color="#64748b" />
          </button>
          
          <form onSubmit={handleCreateEvent}>
            <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap', marginBottom: 16 }}>
              <input
                style={{ ...inputStyle, flex: 1, minWidth: 200 }}
                placeholder="Titolo evento"
                value={newEvent.title}
                onChange={(e) => setNewEvent({ ...newEvent, title: e.target.value })}
                required
                data-testid="input-titolo"
              />
              <input
                style={inputStyle}
                type="date"
                value={newEvent.date}
                onChange={(e) => setNewEvent({ ...newEvent, date: e.target.value })}
                required
              />
              <input
                style={{ ...inputStyle, width: 100 }}
                type="time"
                value={newEvent.time}
                onChange={(e) => setNewEvent({ ...newEvent, time: e.target.value })}
              />
              <select
                style={selectStyle}
                value={newEvent.type}
                onChange={(e) => setNewEvent({ ...newEvent, type: e.target.value })}
              >
                <option value="meeting">🤝 Riunione</option>
                <option value="deadline">⏰ Scadenza</option>
                <option value="reminder">🔔 Promemoria</option>
                <option value="task">✅ Attività</option>
              </select>
            </div>
            <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
              <input
                style={{ ...inputStyle, flex: 1 }}
                placeholder="Note (opzionale)"
                value={newEvent.notes}
                onChange={(e) => setNewEvent({ ...newEvent, notes: e.target.value })}
              />
              <button 
                type="submit" 
                data-testid="btn-salva"
                style={{
                  padding: '10px 20px',
                  background: '#16a34a',
                  color: 'white',
                  border: 'none',
                  borderRadius: 8,
                  cursor: 'pointer',
                  fontWeight: 600,
                  fontSize: 14
                }}
              >
                💾 Salva
              </button>
              <button 
                type="button" 
                onClick={() => setShowForm(false)}
                style={{
                  padding: '10px 20px',
                  background: '#f1f5f9',
                  color: '#475569',
                  border: '1px solid #e2e8f0',
                  borderRadius: 8,
                  cursor: 'pointer',
                  fontWeight: 500,
                  fontSize: 14
                }}
              >
                Annulla
              </button>
            </div>
          </form>
        </PageSection>
      )}

      {/* Lista Eventi */}
      <PageSection title={`Eventi Pianificati (${events.length})`} icon="📋">
        {loading ? (
          <PageLoading message="Caricamento eventi..." />
        ) : events.length === 0 ? (
          <PageEmpty 
            icon="📭" 
            message="Nessun evento pianificato" 
          />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {events.map((ev, i) => (
              <div 
                key={ev.id || i} 
                style={{
                  background: getEventColor(ev.event_type),
                  padding: 16,
                  borderRadius: 10,
                  border: '1px solid rgba(0,0,0,0.05)'
                }}
              >
                <div style={{ fontWeight: 600, fontSize: 15, color: '#1e293b', marginBottom: 8 }}>
                  {getEventIcon(ev.event_type)} {ev.title}
                </div>
                <div style={{ fontSize: 13, color: '#64748b', display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
                  <span>📅 {new Date(ev.scheduled_date).toLocaleString("it-IT")}</span>
                  <span>🏷️ {ev.event_type}</span>
                  <span style={{ 
                    padding: '2px 10px', 
                    borderRadius: 6, 
                    background: ev.status === 'completed' ? '#dcfce7' : '#e0e7ff',
                    color: ev.status === 'completed' ? '#166534' : '#3730a3',
                    fontWeight: 600,
                    fontSize: 12
                  }}>
                    {ev.status}
                  </span>
                </div>
                {ev.notes && (
                  <div style={{ fontSize: 13, color: '#64748b', marginTop: 10, fontStyle: 'italic' }}>
                    💬 {ev.notes}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </PageSection>
    </PageLayout>
  );
}
