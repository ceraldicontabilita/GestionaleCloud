"""
WebSocket Router per Dashboard Real-time.
Fornisce endpoint WebSocket per aggiornamenti live.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from jose import jwt, JWTError
from app.services.websocket_manager import ws_manager
from app.database import Database, Collections
from app.config import settings
from app.utils.logger import get_logger
import asyncio
from datetime import datetime, timezone

logger = get_logger(__name__)
router = APIRouter()


async def _autentica_websocket(websocket: WebSocket) -> bool:
    """Verifica il JWT prima di accettare la connessione.

    AuthenticationMiddleware (app/middleware/authentication.py) NON
    intercetta mai lo scope "websocket": BaseHTTPMiddleware di Starlette
    salta il dispatch per qualunque scope diverso da "http" (bypassa
    dispatch()), quindi il controllo lì scritto per i websocket non
    veniva mai eseguito — questi due endpoint erano di fatto pubblici
    (bug #25 audit memoria/endpoints/README.md). Il token arriva dal
    cookie di sessione (stesso meccanismo dell'HTTP, il browser lo manda
    in automatico sull'handshake) o da ?token= per client non-browser.
    """
    token = websocket.query_params.get("token") or websocket.cookies.get("access_token")
    if not token:
        await websocket.close(code=4401, reason="Authentication required")
        return False
    try:
        jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        await websocket.close(code=4401, reason="Invalid or expired token")
        return False
    return True


async def calculate_live_kpi(db, anno: int) -> dict:
    """
    Calcola i KPI in tempo reale per la dashboard.
    """
    try:
        # Fatturato da corrispettivi
        corrispettivi_cursor = db[Collections.CORRISPETTIVI].find({
            "data": {"$regex": f"^{anno}"}
        })
        corrispettivi = await corrispettivi_cursor.to_list(length=None)
        fatturato_corr = sum(float(c.get("totale", 0) or 0) for c in corrispettivi)
        
        # Entrate/Uscite dalla Prima Nota
        entrate_totali = 0
        uscite_totali = 0
        
        for collection_name in ["prima_nota_cassa", "prima_nota_banca", "prima_nota_salari"]:
            try:
                cursor = db[collection_name].find({
                    "data": {"$regex": f"^{anno}"}
                })
                movimenti = await cursor.to_list(length=None)
                for m in movimenti:
                    importo = float(m.get("importo", 0) or 0)
                    if m.get("tipo") == "entrata":
                        entrate_totali += importo
                    else:
                        uscite_totali += abs(importo)
            except Exception:
                pass
        
        # Conteggi
        num_fatture = await db[Collections.INVOICES].count_documents({})
        num_dipendenti = await db[Collections.EMPLOYEES].count_documents({})
        num_f24 = await db["f24_unificato"].count_documents({"pagato": {"$ne": True}})
        
        # Scadenze prossime (entro 7 giorni)
        from datetime import timedelta
        oggi = datetime.now(timezone.utc)
        tra_7_giorni = oggi + timedelta(days=7)
        
        scadenze_urgenti = await db["scadenziario_fornitori"].count_documents({
            "data_scadenza": {
                "$gte": oggi.strftime("%Y-%m-%d"),
                "$lte": tra_7_giorni.strftime("%Y-%m-%d")
            },
            "pagato": {"$ne": True}
        })
        
        return {
            "fatturato": fatturato_corr,
            "entrate": entrate_totali,
            "uscite": uscite_totali,
            "cashFlow": entrate_totali - uscite_totali,
            "numFatture": num_fatture,
            "numDipendenti": num_dipendenti,
            "numF24": num_f24,
            "scadenzeUrgenti": scadenze_urgenti,
            "lastUpdate": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Errore calcolo KPI live: {e}")
        return {}


@router.websocket("/ws/dashboard")
async def websocket_dashboard(
    websocket: WebSocket,
    anno: int = Query(default=2026)
):
    """
    WebSocket endpoint per la dashboard real-time.
    
    Invia aggiornamenti KPI ogni 30 secondi e notifiche immediate per eventi.
    """
    if not await _autentica_websocket(websocket):
        return
    await ws_manager.connect(websocket, "dashboard")
    
    try:
        db = Database.get_db()
        
        # Invia KPI iniziali
        kpi = await calculate_live_kpi(db, anno)
        await ws_manager.send_personal_message({
            "type": "kpi_update",
            "data": kpi,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }, websocket)
        
        # Loop per gestione messaggi - nessun aggiornamento automatico periodico
        while True:
            try:
                # Attendi messaggio dal client (solo su richiesta esplicita)
                message = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=300.0  # Timeout lungo - non inviare aggiornamenti automatici
                )
                
                # Gestisci comandi dal client
                if message.get("command") == "refresh":
                    anno_richiesto = message.get("anno", anno)
                    kpi = await calculate_live_kpi(db, anno_richiesto)
                    await ws_manager.send_personal_message({
                        "type": "kpi_update",
                        "data": kpi,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }, websocket)
                
                elif message.get("command") == "ping":
                    await ws_manager.send_personal_message({
                        "type": "pong",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }, websocket)
                    
            except asyncio.TimeoutError:
                # Timeout keepalive - invia solo pong, NON aggiornamenti KPI automatici
                try:
                    await ws_manager.send_personal_message({
                        "type": "pong",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }, websocket)
                except Exception:
                    break
                
    except WebSocketDisconnect:
        logger.info("WebSocket dashboard disconnesso")
    except Exception as e:
        logger.error(f"Errore WebSocket dashboard: {e}")
    finally:
        await ws_manager.disconnect(websocket, "dashboard")


@router.websocket("/ws/notifications")
async def websocket_notifications(websocket: WebSocket):
    """
    WebSocket endpoint per notifiche generali.
    
    Riceve notifiche push per eventi come:
    - Nuove fatture
    - Scadenze imminenti
    - Movimenti bancari
    """
    if not await _autentica_websocket(websocket):
        return
    await ws_manager.connect(websocket, "notifications")
    
    try:
        while True:
            try:
                # Mantieni la connessione attiva
                message = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=25.0
                )
                
                if message.get("command") == "ping":
                    await ws_manager.send_personal_message({
                        "type": "pong",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }, websocket)
                    
            except asyncio.TimeoutError:
                # Heartbeat
                await ws_manager.send_personal_message({
                    "type": "heartbeat",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }, websocket)
                
    except WebSocketDisconnect:
        logger.info("WebSocket notifications disconnesso")
    except Exception as e:
        logger.error(f"Errore WebSocket notifications: {e}")
    finally:
        await ws_manager.disconnect(websocket, "notifications")


# GET /realtime/status: smontato (audit 14/07/2026, piano residuo op.7) —
# zero chiamanti verificati. Il websocket reale (/ws/notifications, sopra)
# resta attivo, usato da frontend/src/hooks/useWebSocket.js.
