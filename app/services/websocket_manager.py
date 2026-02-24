"""
WebSocket Manager per notifiche real-time.
Gestisce connessioni WebSocket per aggiornamenti live della dashboard.
"""
from fastapi import WebSocket
from typing import Dict, List, Set
import asyncio
from datetime import datetime, timezone
from app.utils.logger import get_logger

logger = get_logger(__name__)


class ConnectionManager:
    """
    Gestisce le connessioni WebSocket attive e la distribuzione dei messaggi.
    """
    
    def __init__(self):
        # Connessioni attive per canale
        self.active_connections: Dict[str, List[WebSocket]] = {}
        # Set di tutti i websocket connessi
        self.all_connections: Set[WebSocket] = set()
        # Lock per thread safety
        self._lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket, channel: str = "dashboard"):
        """Accetta una nuova connessione WebSocket."""
        await websocket.accept()
        
        async with self._lock:
            if channel not in self.active_connections:
                self.active_connections[channel] = []
            self.active_connections[channel].append(websocket)
            self.all_connections.add(websocket)
        
        logger.info(f"WebSocket connesso al canale '{channel}'. Totale connessioni: {len(self.all_connections)}")
        
        # Invia messaggio di benvenuto
        await self.send_personal_message({
            "type": "connection",
            "status": "connected",
            "channel": channel,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }, websocket)
    
    async def disconnect(self, websocket: WebSocket, channel: str = "dashboard"):
        """Rimuove una connessione WebSocket."""
        async with self._lock:
            if channel in self.active_connections:
                if websocket in self.active_connections[channel]:
                    self.active_connections[channel].remove(websocket)
            if websocket in self.all_connections:
                self.all_connections.discard(websocket)
        
        logger.info(f"WebSocket disconnesso dal canale '{channel}'. Totale connessioni: {len(self.all_connections)}")
    
    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """Invia un messaggio a una singola connessione."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Errore invio messaggio WebSocket: {e}")
    
    async def broadcast_to_channel(self, message: dict, channel: str = "dashboard"):
        """Invia un messaggio a tutte le connessioni di un canale."""
        if channel not in self.active_connections:
            return
        
        disconnected = []
        for connection in self.active_connections[channel]:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Errore broadcast WebSocket: {e}")
                disconnected.append(connection)
        
        # Rimuovi connessioni non più attive
        for conn in disconnected:
            await self.disconnect(conn, channel)
    
    async def broadcast_all(self, message: dict):
        """Invia un messaggio a TUTTE le connessioni attive."""
        disconnected = []
        for connection in self.all_connections.copy():
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)
        
        # Rimuovi connessioni non più attive
        for conn in disconnected:
            # Trova il canale e disconnetti
            for channel in self.active_connections:
                if conn in self.active_connections[channel]:
                    await self.disconnect(conn, channel)
                    break
    
    def get_connection_count(self, channel: str = None) -> int:
        """Restituisce il numero di connessioni attive."""
        if channel:
            return len(self.active_connections.get(channel, []))
        return len(self.all_connections)


# Istanza globale del manager
ws_manager = ConnectionManager()


async def notify_data_change(event_type: str, data: dict = None, channel: str = "dashboard"):
    """
    Notifica un cambiamento dati a tutti i client connessi.
    
    Args:
        event_type: Tipo di evento (es. 'fattura_creata', 'movimento_aggiunto', 'scadenza_completata')
        data: Dati associati all'evento
        channel: Canale su cui inviare la notifica
    """
    message = {
        "type": "data_change",
        "event": event_type,
        "data": data or {},
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    await ws_manager.broadcast_to_channel(message, channel)
    logger.debug(f"Notifica '{event_type}' inviata a {ws_manager.get_connection_count(channel)} client")


async def notify_kpi_update(kpi_data: dict, channel: str = "dashboard"):
    """
    Invia un aggiornamento KPI alla dashboard.
    
    Args:
        kpi_data: Dati KPI aggiornati
        channel: Canale su cui inviare
    """
    message = {
        "type": "kpi_update",
        "data": kpi_data,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    await ws_manager.broadcast_to_channel(message, channel)


async def notify_alert(alert_type: str, message_text: str, severity: str = "info", channel: str = "dashboard"):
    """
    Invia una notifica di alert.
    
    Args:
        alert_type: Tipo di alert (es. 'scadenza', 'pagamento', 'errore')
        message_text: Testo del messaggio
        severity: Gravità (info, warning, error, success)
        channel: Canale su cui inviare
    """
    message = {
        "type": "alert",
        "alert_type": alert_type,
        "message": message_text,
        "severity": severity,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    await ws_manager.broadcast_to_channel(message, channel)
