import { formatDateIT } from '../lib/utils';
import React, { useState, useEffect, useRef } from 'react';
import { Bell, X, CheckCircle, AlertTriangle, Info, ExternalLink } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import api from '../api';

export default function NotificationBell() {
  const [alerts, setAlerts] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const dropdownRef = useRef(null);
  const navigate = useNavigate();

  const fetchAlerts = async () => {
    try {
      setLoading(true);
      const response = await api.get('/api/alerts/lista?limit=20');
      const data = response.data;
      setAlerts(data.alerts || []);
      setUnreadCount(data.stats?.non_letti || 0);
    } catch (error) {
      console.error('Errore caricamento alert:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAlerts();
    // Rimosso auto-refresh ogni 60 secondi per evitare re-render della pagina
    // Le notifiche si aggiornano solo al caricamento iniziale o cliccando sulla campanella
  }, []);

  useEffect(() => {
    const handleClickOutside = event => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const markAsRead = async alertId => {
    try {
      await api.post(`/api/alerts/${alertId}/segna-letto`);
      fetchAlerts();
    } catch (error) {
      console.error('Errore:', error);
    }
  };

  const resolveAlert = async (alertId, e) => {
    e.stopPropagation();
    try {
      await api.post(`/api/alerts/${alertId}/risolvi`);
      fetchAlerts();
    } catch (error) {
      console.error('Errore:', error);
    }
  };

  const getAlertIcon = tipo => {
    switch (tipo) {
      case 'fornitore_senza_metodo_pagamento':
        return <AlertTriangle size={16} style={{ color: '#f59e0b' }} />;
      case 'scadenza':
        return <Bell size={16} style={{ color: '#ef4444' }} />;
      default:
        return <Info size={16} style={{ color: '#3b82f6' }} />;
    }
  };

  const getPriorityBorder = priorita => {
    switch (priorita) {
      case 'alta':
        return '#ef4444';
      case 'media':
        return '#f59e0b';
      default:
        return '#3b82f6';
    }
  };

  const handleAlertClick = alert => {
    if (alert.link) {
      navigate(alert.link);
      setIsOpen(false);
    }
    if (!alert.letto) {
      markAsRead(alert.id);
    }
  };

  return (
    <div style={{ position: 'relative' }} ref={dropdownRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        style={{
          position: 'relative',
          padding: '8px',
          borderRadius: '8px',
          background: isOpen ? 'rgba(255,255,255,0.2)' : 'rgba(255,255,255,0.1)',
          border: 'none',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          transition: 'background 0.2s',
        }}
        data-testid="notification-bell"
      >
        <Bell size={18} style={{ color: 'white' }} />
        {unreadCount > 0 && (
          <span
            style={{
              position: 'absolute',
              top: '-4px',
              right: '-4px',
              background: '#ef4444',
              color: 'white',
              fontSize: '10px',
              fontWeight: 'bold',
              borderRadius: '50%',
              minWidth: '18px',
              height: '18px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '0 4px',
              boxShadow: '0 2px 4px rgba(0,0,0,0.2)',
            }}
          >
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {isOpen && (
        <div
          style={{
            position: 'absolute',
            right: 0,
            marginTop: '8px',
            width: '340px',
            backgroundColor: 'white',
            borderRadius: '12px',
            boxShadow: '0 10px 40px rgba(0,0,0,0.25)',
            border: '1px solid #e5e7eb',
            zIndex: 99999,
            maxHeight: '70vh',
            overflow: 'hidden',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          {/* Header */}
          <div
            style={{
              padding: '14px 16px',
              borderBottom: '1px solid #e5e7eb',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              background: '#f8fafc',
            }}
          >
            <h3
              style={{
                margin: 0,
                fontWeight: 600,
                fontSize: '14px',
                color: '#1f2937',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
              }}
            >
              <Bell size={16} />
              Notifiche
              {unreadCount > 0 && (
                <span
                  style={{
                    background: '#fee2e2',
                    color: '#dc2626',
                    fontSize: '11px',
                    padding: '2px 8px',
                    borderRadius: '10px',
                    fontWeight: 600,
                  }}
                >
                  {unreadCount} nuove
                </span>
              )}
            </h3>
            <button
              onClick={() => setIsOpen(false)}
              style={{
                padding: '4px',
                background: 'transparent',
                border: 'none',
                cursor: 'pointer',
                borderRadius: '6px',
                display: 'flex',
              }}
            >
              <X size={18} style={{ color: '#6b7280' }} />
            </button>
          </div>

          {/* Alerts List */}
          <div style={{ overflowY: 'auto', flex: 1 }}>
            {loading ? (
              <div style={{ padding: '24px', textAlign: 'center', color: '#6b7280' }}>
                Caricamento...
              </div>
            ) : alerts.length === 0 ? (
              <div style={{ padding: '40px 24px', textAlign: 'center', color: '#9ca3af' }}>
                <Bell size={32} style={{ opacity: 0.3, marginBottom: '8px' }} />
                <p style={{ margin: 0 }}>Nessuna notifica</p>
              </div>
            ) : (
              <div>
                {alerts.map(alert => (
                  <div
                    key={alert.id}
                    onClick={() => handleAlertClick(alert)}
                    style={{
                      padding: '12px 16px',
                      borderBottom: '1px solid #f1f5f9',
                      cursor: 'pointer',
                      borderLeft: `4px solid ${getPriorityBorder(alert.priorita)}`,
                      background: !alert.letto ? '#eff6ff' : 'white',
                      transition: 'background 0.15s',
                    }}
                    onMouseEnter={e => (e.currentTarget.style.background = '#f8fafc')}
                    onMouseLeave={e =>
                      (e.currentTarget.style.background = !alert.letto ? '#eff6ff' : 'white')
                    }
                  >
                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
                      <div style={{ marginTop: '2px' }}>{getAlertIcon(alert.tipo)}</div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <p
                          style={{
                            margin: 0,
                            fontSize: '13px',
                            fontWeight: !alert.letto ? 600 : 400,
                            color: '#1f2937',
                            whiteSpace: 'nowrap',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                          }}
                        >
                          {alert.titolo}
                        </p>
                        <p
                          style={{
                            margin: '4px 0 0',
                            fontSize: '12px',
                            color: '#6b7280',
                            display: '-webkit-box',
                            WebkitLineClamp: 2,
                            WebkitBoxOrient: 'vertical',
                            overflow: 'hidden',
                          }}
                        >
                          {alert.messaggio}
                        </p>
                        <div
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px',
                            marginTop: '6px',
                          }}
                        >
                          <span style={{ fontSize: '11px', color: '#9ca3af' }}>
                            {formatDateIT(alert.created_at)}
                          </span>
                          {alert.link && <ExternalLink size={12} style={{ color: '#9ca3af' }} />}
                          {alert.risolto && (
                            <span
                              style={{
                                fontSize: '11px',
                                color: '#16a34a',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '4px',
                              }}
                            >
                              <CheckCircle size={12} /> Risolto
                            </span>
                          )}
                        </div>
                      </div>
                      {!alert.risolto && (
                        <button
                          onClick={e => resolveAlert(alert.id, e)}
                          style={{
                            padding: '6px',
                            background: 'transparent',
                            border: 'none',
                            cursor: 'pointer',
                            borderRadius: '6px',
                            color: '#16a34a',
                          }}
                          title="Segna come risolto"
                        >
                          <CheckCircle size={16} />
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Footer */}
          {alerts.length > 0 && (
            <div
              style={{
                padding: '10px 16px',
                borderTop: '1px solid #e5e7eb',
                background: '#f8fafc',
              }}
            >
              <button
                onClick={() => {
                  navigate('/admin?tab=alerts');
                  setIsOpen(false);
                }}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: '#2563eb',
                  fontSize: '13px',
                  fontWeight: 500,
                  cursor: 'pointer',
                  padding: 0,
                }}
              >
                Vedi tutte le notifiche →
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
