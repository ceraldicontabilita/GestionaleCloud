/**
 * useWebSocketNotifications — Connessione WebSocket real-time per notifiche push.
 * Sostituisce il vecchio stub. Gestisce riconnessione con backoff esponenziale.
 */
import { useEffect, useRef } from 'react';
import { queryClient } from '../lib/queryClient';

const MAX_RETRIES = 8;

// Mapping event_type → chiavi React Query da invalidare
const QUERY_INVALIDATIONS = {
  email_sync: [['fatture-ricevute'], ['operazioni-da-confermare']],
  verbali_scan: [['verbali'], ['verbali-riconciliazione']],
  f24_scadenze: [['f24'], ['scadenze']],
};

function getWebSocketUrl() {
  // Usa il protocollo e host correnti (funziona sia in dev che in produzione)
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/api/ws/notifications`;
}

export function useWebSocketNotifications() {
  const wsRef = useRef(null);
  const retriesRef = useRef(0);
  const pingTimerRef = useRef(null);
  const reconnectTimerRef = useRef(null);

  useEffect(() => {
    function cleanup() {
      clearInterval(pingTimerRef.current);
      clearTimeout(reconnectTimerRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null; // evita riconnessione su chiusura volontaria
        wsRef.current.close();
        wsRef.current = null;
      }
    }

    function connect() {
      if (retriesRef.current >= MAX_RETRIES) {
        console.warn('[WS] Massimo numero di tentativi raggiunto. WebSocket non connesso.');
        return;
      }

      const url = getWebSocketUrl();
      let ws;
      try {
        ws = new WebSocket(url);
      } catch (e) {
        console.error('[WS] Impossibile creare WebSocket:', e);
        return;
      }
      wsRef.current = ws;

      ws.onopen = () => {
        retriesRef.current = 0;
        console.info('[WS] Connesso a', url);
        // Ping ogni 20 secondi (proxy Kubernetes timeout: 30s — dobbiamo pingare prima)
        pingTimerRef.current = setInterval(() => {
          if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify({ command: 'ping' }));
          }
        }, 20000);
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);

          if (msg.type === 'data_change') {
            // 1. Emette CustomEvent globale → pagine useState possono ascoltarlo
            window.dispatchEvent(new CustomEvent('data-refresh', { detail: msg }));

            // 2. Invalida cache React Query per le query registrate
            const keys = QUERY_INVALIDATIONS[msg.event] || [];
            keys.forEach((key) => queryClient.invalidateQueries({ queryKey: key }));

            console.info(`[WS] data_change ricevuto: ${msg.event}`, msg.data);
          }
        } catch (e) {
          // messaggio non JSON (es. heartbeat text) — ignorato
        }
      };

      ws.onerror = () => {
        // onclose verrà chiamato dopo onerror, gestirà la riconnessione
      };

      ws.onclose = () => {
        clearInterval(pingTimerRef.current);
        retriesRef.current++;
        if (retriesRef.current < MAX_RETRIES) {
          const delay = Math.min(1000 * Math.pow(2, retriesRef.current), 30000);
          console.info(`[WS] Riconnessione tra ${delay}ms (tentativo ${retriesRef.current}/${MAX_RETRIES})...`);
          reconnectTimerRef.current = setTimeout(connect, delay);
        }
      };
    }

    connect();
    return cleanup;
  }, []);
}

// Dashboard WebSocket mantenuto come stub (non critico)
export function useWebSocketDashboard(anno, enabled = false) {
  return {
    kpiData: null,
    isConnected: false,
    lastUpdate: null,
    connectionError: null,
    requestRefresh: () => {},
    sendPing: () => {},
  };
}
