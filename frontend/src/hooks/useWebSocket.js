/**
 * WebSocket disabilitato — il gestionale carica i dati via API REST.
 * Hook stub che rispetta la stessa interfaccia per non rompere i consumer.
 */

export function useWebSocketDashboard(anno, enabled = false) {
  return {
    kpiData: null,
    isConnected: false,
    lastUpdate: null,
    connectionError: null,
    requestRefresh: () => {},
    sendPing: () => {}
  };
}

export function useWebSocketNotifications(enabled = false) {
  return {
    notifications: [],
    isConnected: false,
    clearNotifications: () => {}
  };
}
