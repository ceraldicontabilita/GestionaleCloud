import React, { useEffect, useState, useCallback } from 'react';
import api from '../api';

/**
 * Hook per gestire le notifiche browser per scadenze imminenti
 */
export function useScadenzeNotifiche() {
  const [permission, setPermission] = useState('default');
  const [scadenzeUrgenti, setScadenzeUrgenti] = useState([]);

  // Richiedi permesso notifiche
  const requestPermission = useCallback(async () => {
    if (!('Notification' in window)) {
      console.warn('Browser non supporta notifiche');
      return false;
    }

    const result = await Notification.requestPermission();
    setPermission(result);
    return result === 'granted';
  }, []);

  // Invia notifica
  const sendNotification = useCallback(
    (title, body, options = {}) => {
      if (permission !== 'granted') return;

      const notification = new Notification(title, {
        body,
        icon: '/favicon.ico',
        badge: '/favicon.ico',
        tag: options.tag || 'scadenza',
        requireInteraction: options.urgent || false,
        ...options,
      });

      notification.onclick = () => {
        window.focus();
        if (options.url) {
          const isInternalRoute = options.url.startsWith('/') && !options.url.startsWith('/api/');
          if (isInternalRoute) {
            window.history.pushState({}, '', options.url);
            window.dispatchEvent(new PopStateEvent('popstate'));
          } else {
            window.location.href = options.url;
          }
        }
        notification.close();
      };

      return notification;
    },
    [permission]
  );

  // Controlla scadenze
  const checkScadenze = useCallback(async () => {
    try {
      const res = await api.get('/api/scadenze/prossime?giorni=3');
      const scadenze = res.data?.scadenze || res.data || [];

      const urgenti = scadenze.filter(s => {
        const dataScadenza = new Date(s.data_scadenza);
        const oggi = new Date();
        const diffGiorni = Math.ceil((dataScadenza - oggi) / (1000 * 60 * 60 * 24));
        return diffGiorni <= 3 && diffGiorni >= 0;
      });

      setScadenzeUrgenti(urgenti);

      // Notifica per scadenze urgenti
      if (urgenti.length > 0 && permission === 'granted') {
        const scadenzaOggi = urgenti.filter(s => {
          const d = new Date(s.data_scadenza);
          const oggi = new Date();
          return d.toDateString() === oggi.toDateString();
        });

        if (scadenzaOggi.length > 0) {
          sendNotification(
            '⚠️ Scadenze OGGI!',
            `Hai ${scadenzaOggi.length} scadenz${scadenzaOggi.length > 1 ? 'e' : 'a'} in scadenza oggi`,
            { urgent: true, tag: 'scadenza-oggi', url: '/scadenze' }
          );
        } else if (urgenti.length > 0) {
          sendNotification(
            '📅 Scadenze imminenti',
            `${urgenti.length} scadenz${urgenti.length > 1 ? 'e' : 'a'} nei prossimi 3 giorni`,
            { tag: 'scadenza-prossima', url: '/scadenze' }
          );
        }
      }

      return urgenti;
    } catch (e) {
      console.error('Errore check scadenze:', e);
      return [];
    }
  }, [permission, sendNotification]);

  // Setup iniziale
  useEffect(() => {
    if ('Notification' in window) {
      setPermission(Notification.permission);
    }
  }, []);

  // Check only on mount (no periodic refresh)
  useEffect(() => {
    checkScadenze();
  }, [checkScadenze]);

  return {
    permission,
    requestPermission,
    sendNotification,
    scadenzeUrgenti,
    checkScadenze,
    isSupported: 'Notification' in window,
  };
}

/**
 * Componente UI per gestire notifiche
 */
export function NotificheScadenze({ showBanner = true }) {
  const { permission, requestPermission, scadenzeUrgenti, isSupported } = useScadenzeNotifiche();
  const [dismissed, setDismissed] = useState(() => {
    // Controlla se l'utente ha già chiuso il banner
    return localStorage.getItem('notifiche_banner_dismissed') === 'true';
  });

  const handleDismiss = () => {
    setDismissed(true);
    localStorage.setItem('notifiche_banner_dismissed', 'true');
  };

  if (!isSupported || dismissed) return null;

  // Non mostrare se permesso già concesso o negato
  if (permission !== 'default') return null;

  // Banner per richiedere permesso - meno invasivo, in basso a destra
  if (showBanner) {
    return (
      <div
        style={{
          position: 'fixed',
          bottom: 20,
          right: 20,
          maxWidth: 360,
          background: '#1d4ed8',
          color: 'white',
          padding: '14px 18px',
          borderRadius: 12,
          boxShadow: '0 4px 20px rgba(0,0,0,0.2)',
          zIndex: 9999,
          fontSize: 13,
        }}
      >
        <div style={{ marginBottom: 10, fontWeight: 500 }}>🔔 Attiva le notifiche</div>
        <div style={{ marginBottom: 12, fontSize: 12, opacity: 0.9 }}>
          Ricevi avvisi per scadenze imminenti
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            onClick={requestPermission}
            style={{
              padding: '8px 16px',
              background: 'white',
              color: '#3b82f6',
              border: 'none',
              borderRadius: 6,
              fontWeight: 600,
              cursor: 'pointer',
              fontSize: 12,
            }}
          >
            Attiva
          </button>
          <button
            onClick={handleDismiss}
            style={{
              padding: '8px 16px',
              background: 'rgba(255,255,255,0.2)',
              color: 'white',
              border: 'none',
              borderRadius: 6,
              cursor: 'pointer',
              fontSize: 12,
            }}
          >
            Non ora
          </button>
        </div>
      </div>
    );
  }

  return null;
}

export default NotificheScadenze;
