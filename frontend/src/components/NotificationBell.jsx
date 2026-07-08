import { COLORS, SHADOWS, BORDER_RADIUS, formatDateIT } from '../lib/utils';
import React, { useState, useEffect, useRef } from 'react';
import { Bell, X, CheckCircle, AlertTriangle, Info, ExternalLink } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import api from '../api';
import { Button, Badge } from './ds';

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
        return <AlertTriangle size={16} style={{ color: COLORS.warning }} />;
      case 'scadenza':
        return <Bell size={16} style={{ color: COLORS.danger }} />;
      default:
        return <Info size={16} style={{ color: COLORS.info }} />;
    }
  };

  const getPriorityBorder = priorita => {
    switch (priorita) {
      case 'alta':
        return COLORS.danger;
      case 'media':
        return COLORS.warning;
      default:
        return COLORS.info;
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
      <Button
        onClick={() => setIsOpen(!isOpen)}
        variant="ghost"
        size="sm"
        data-testid="notification-bell"
        style={{
          position: 'relative',
          background: isOpen ? 'rgba(255,255,255,0.2)' : 'rgba(255,255,255,0.1)',
        }}
      >
        <Bell size={18} style={{ color: 'white' }} />
        {unreadCount > 0 && (
          <span
            style={{
              position: 'absolute',
              top: '-4px',
              right: '-4px',
              background: COLORS.danger,
              color: 'white',
              fontSize: '10px',
              fontWeight: 'bold',
              borderRadius: BORDER_RADIUS.full,
              minWidth: '18px',
              height: '18px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '0 4px',
              boxShadow: SHADOWS.sm,
            }}
          >
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </Button>

      {isOpen && (
        <div
          style={{
            position: 'absolute',
            right: 0,
            marginTop: '8px',
            width: '340px',
            backgroundColor: COLORS.card,
            borderRadius: BORDER_RADIUS.xl,
            boxShadow: SHADOWS.modal,
            border: `1px solid ${COLORS.border}`,
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
              borderBottom: `1px solid ${COLORS.border}`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              background: COLORS.bgAlt,
            }}
          >
            <h3
              style={{
                margin: 0,
                fontWeight: 600,
                fontSize: '14px',
                color: COLORS.text,
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
              }}
            >
              <Bell size={16} />
              Notifiche
              {unreadCount > 0 && <Badge variant="danger">{unreadCount} nuove</Badge>}
            </h3>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIsOpen(false)}
              style={{ padding: '4px' }}
            >
              <X size={18} style={{ color: COLORS.textMuted }} />
            </Button>
          </div>

          {/* Alerts List */}
          <div style={{ overflowY: 'auto', flex: 1 }}>
            {loading ? (
              <div style={{ padding: '24px', textAlign: 'center', color: COLORS.textMuted }}>
                Caricamento...
              </div>
            ) : alerts.length === 0 ? (
              <div style={{ padding: '40px 24px', textAlign: 'center', color: COLORS.textSubtle }}>
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
                      borderBottom: `1px solid ${COLORS.gray[100]}`,
                      cursor: 'pointer',
                      borderLeft: `4px solid ${getPriorityBorder(alert.priorita)}`,
                      background: !alert.letto ? COLORS.infoLight : COLORS.card,
                      transition: 'background 0.15s',
                    }}
                    onMouseEnter={e => (e.currentTarget.style.background = COLORS.bgAlt)}
                    onMouseLeave={e =>
                      (e.currentTarget.style.background = !alert.letto
                        ? COLORS.infoLight
                        : COLORS.card)
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
                            color: COLORS.text,
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
                            color: COLORS.textMuted,
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
                          <span style={{ fontSize: '11px', color: COLORS.textSubtle }}>
                            {formatDateIT(alert.created_at)}
                          </span>
                          {alert.link && (
                            <ExternalLink size={12} style={{ color: COLORS.textSubtle }} />
                          )}
                          {alert.risolto && (
                            <span
                              style={{
                                fontSize: '11px',
                                color: COLORS.success,
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
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={e => resolveAlert(alert.id, e)}
                          title="Segna come risolto"
                          style={{ padding: '6px', color: COLORS.success }}
                        >
                          <CheckCircle size={16} />
                        </Button>
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
                borderTop: `1px solid ${COLORS.border}`,
                background: COLORS.bgAlt,
              }}
            >
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  navigate('/admin?tab=alerts');
                  setIsOpen(false);
                }}
                style={{ color: COLORS.info, padding: 0 }}
              >
                Vedi tutte le notifiche →
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
