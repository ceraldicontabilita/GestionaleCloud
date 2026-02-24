"""
OpenClaw/MoltBot Integration Router for Ceraldi ERP
Provides AI assistant functionality via Moltbot gateway
"""
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Request, Response
from fastapi.responses import HTMLResponse
from starlette.websockets import WebSocketState
from pydantic import BaseModel
from typing import Optional
import os
import logging
import json
import secrets
import asyncio
import httpx
import websockets
from websockets.exceptions import ConnectionClosed
from datetime import datetime, timezone

from app.database import Database
from app.services.gateway_config import write_gateway_env, clear_gateway_env
from app.services.supervisor_client import SupervisorClient
from app.services.whatsapp_monitor import get_whatsapp_status, fix_registered_flag

logger = logging.getLogger(__name__)

router = APIRouter()

# Moltbot Gateway Configuration
MOLTBOT_PORT = 18789
CONFIG_DIR = os.path.expanduser("~/.clawdbot")
CONFIG_FILE = os.path.join(CONFIG_DIR, "clawdbot.json")
WORKSPACE_DIR = os.path.expanduser("~/clawd")

# Global state for gateway
gateway_state = {
    "token": None,
    "provider": None,
    "started_at": None,
    "owner_user_id": None
}


def get_token_from_config():
    """Read token from clawdbot config file"""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
            return config.get("gateway", {}).get("auth", {}).get("token")
    except:
        pass
    return gateway_state.get("token")


# ============== Pydantic Models ==============

class OpenClawStartRequest(BaseModel):
    provider: str = "emergent"
    apiKey: Optional[str] = None


class OpenClawStartResponse(BaseModel):
    ok: bool
    controlUrl: str
    token: str
    message: str


class OpenClawStatusResponse(BaseModel):
    running: bool
    pid: Optional[int] = None
    provider: Optional[str] = None
    started_at: Optional[str] = None
    controlUrl: Optional[str] = None


# ============== Helper Functions ==============

def get_clawdbot_command():
    """Get the path to clawdbot executable"""
    NODE_DIR = "/root/nodejs"
    CLAWDBOT_DIR = "/root/.clawdbot-bin"
    CLAWDBOT_WRAPPER = "/root/run_clawdbot.sh"
    
    if os.path.exists(CLAWDBOT_WRAPPER):
        return CLAWDBOT_WRAPPER
    if os.path.exists(f"{CLAWDBOT_DIR}/clawdbot"):
        return f"{CLAWDBOT_DIR}/clawdbot"
    if os.path.exists(f"{NODE_DIR}/bin/clawdbot"):
        return f"{NODE_DIR}/bin/clawdbot"
    import shutil
    return shutil.which("clawdbot")


def generate_token():
    return secrets.token_hex(32)


def create_moltbot_config(token: str = None, api_key: str = None, provider: str = "emergent"):
    """Create/update clawdbot configuration"""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(WORKSPACE_DIR, exist_ok=True)
    
    existing_config = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                existing_config = json.load(f)
        except:
            pass
    
    existing_token = existing_config.get("gateway", {}).get("auth", {}).get("token")
    final_token = existing_token or token or generate_token()
    
    gateway_config = {
        "mode": "local",
        "port": MOLTBOT_PORT,
        "bind": "lan",
        "auth": {"mode": "token", "token": final_token},
        "controlUi": {"enabled": True, "allowInsecureAuth": True}
    }
    
    existing_config["gateway"] = gateway_config
    
    if "models" not in existing_config:
        existing_config["models"] = {"mode": "merge", "providers": {}}
    
    if "agents" not in existing_config:
        existing_config["agents"] = {"defaults": {"workspace": WORKSPACE_DIR}}
    
    # Configure Emergent provider
    if provider == "emergent":
        emergent_key = api_key or os.environ.get('EMERGENT_API_KEY', '')
        emergent_base_url = os.environ.get('EMERGENT_BASE_URL', 'https://integrations.emergentagent.com/llm')
        
        existing_config["models"]["providers"]["emergent-claude"] = {
            "baseUrl": emergent_base_url,
            "apiKey": emergent_key,
            "api": "anthropic-messages",
            "authHeader": True,
            "models": [{
                "id": "claude-sonnet-4-5",
                "name": "Claude Sonnet 4.5",
                "input": ["text"],
                "contextWindow": 200000,
                "maxTokens": 64000
            }]
        }
        
        existing_config["agents"]["defaults"]["model"] = {
            "primary": "emergent-claude/claude-sonnet-4-5"
        }
    
    with open(CONFIG_FILE, "w") as f:
        json.dump(existing_config, f, indent=2)
    
    return final_token


async def start_gateway_process(api_key: str, provider: str):
    """Start the Moltbot gateway"""
    global gateway_state
    
    if SupervisorClient.status():
        token = None
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
            token = config.get("gateway", {}).get("auth", {}).get("token")
        except:
            pass
        
        if not token:
            token = generate_token()
            create_moltbot_config(token=token, api_key=api_key, provider=provider)
        
        gateway_state["token"] = token
        gateway_state["provider"] = provider
        gateway_state["started_at"] = datetime.now(timezone.utc).isoformat()
        return token
    
    clawdbot_cmd = get_clawdbot_command()
    if not clawdbot_cmd:
        raise HTTPException(status_code=500, detail="OpenClaw (clawdbot) non installato")
    
    token = create_moltbot_config(api_key=api_key, provider=provider)
    write_gateway_env(token=token, api_key=api_key, provider=provider)
    
    if not SupervisorClient.start():
        raise HTTPException(status_code=500, detail="Impossibile avviare il gateway")
    
    gateway_state["token"] = token
    gateway_state["provider"] = provider
    gateway_state["started_at"] = datetime.now(timezone.utc).isoformat()
    
    # Wait for gateway to be ready
    async with httpx.AsyncClient() as client:
        for _ in range(30):
            try:
                response = await client.get(f"http://127.0.0.1:{MOLTBOT_PORT}/", timeout=2.0)
                if response.status_code == 200:
                    return token
            except:
                pass
            await asyncio.sleep(1)
    
    raise HTTPException(status_code=500, detail="Gateway non pronto")


# ============== API Endpoints ==============

@router.get("/openclaw/status", response_model=OpenClawStatusResponse)
async def get_openclaw_status():
    """Get OpenClaw gateway status"""
    running = SupervisorClient.status()
    
    # Also check if port is alive
    if not running:
        try:
            async with httpx.AsyncClient() as probe:
                r = await probe.get(f"http://127.0.0.1:{MOLTBOT_PORT}/", timeout=2.0)
                running = r.status_code == 200
        except:
            pass
    
    if running:
        return OpenClawStatusResponse(
            running=True,
            pid=SupervisorClient.get_pid(),
            provider=gateway_state.get("provider", "emergent"),
            started_at=gateway_state.get("started_at"),
            controlUrl="/api/openclaw/ui/"
        )
    return OpenClawStatusResponse(running=False)


@router.post("/openclaw/start", response_model=OpenClawStartResponse)
async def start_openclaw(request: OpenClawStartRequest):
    """Start OpenClaw gateway"""
    if request.provider not in ["emergent", "anthropic", "openai"]:
        raise HTTPException(status_code=400, detail="Provider non valido")
    
    try:
        token = await start_gateway_process(request.apiKey, request.provider)
        return OpenClawStartResponse(
            ok=True,
            controlUrl="/api/openclaw/ui/",
            token=token,
            message="OpenClaw avviato con successo"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore avvio OpenClaw: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/openclaw/stop")
async def stop_openclaw():
    """Stop OpenClaw gateway"""
    global gateway_state
    
    if not SupervisorClient.status():
        return {"ok": True, "message": "OpenClaw non era in esecuzione"}
    
    SupervisorClient.stop()
    clear_gateway_env()
    
    gateway_state = {"token": None, "provider": None, "started_at": None, "owner_user_id": None}
    return {"ok": True, "message": "OpenClaw fermato"}


# ============== Quick Actions for Clawdbot ==============

@router.get("/openclaw/quick-actions")
async def get_quick_actions():
    """
    Restituisce le azioni rapide disponibili per Clawdbot.
    Queste azioni possono essere eseguite tramite comandi vocali o pulsanti.
    """
    return {
        "actions": [
            {
                "id": "riconcilia_mutui",
                "label": "Riconcilia Mutui",
                "description": "Riconcilia automaticamente le rate dei mutui con i movimenti bancari",
                "endpoint": "/api/mutui/riconcilia",
                "method": "POST",
                "icon": "🏦"
            },
            {
                "id": "riconcilia_pos",
                "label": "Verifica POS/Corrispettivi",
                "description": "Verifica la coerenza tra incassi POS e corrispettivi elettronici",
                "endpoint": "/api/pos-corrispettivi/verifica-coerenza?anno=2025",
                "method": "GET",
                "icon": "💳"
            },
            {
                "id": "dashboard_mutui",
                "label": "Statistiche Mutui",
                "description": "Visualizza statistiche aggregate sui mutui",
                "endpoint": "/api/mutui/statistiche/dashboard",
                "method": "GET",
                "icon": "📊"
            },
            {
                "id": "prossime_scadenze",
                "label": "Prossime Scadenze",
                "description": "Mostra le prossime scadenze nei prossimi 30 giorni",
                "endpoint": "/api/scadenze/prossime?giorni=30",
                "method": "GET",
                "icon": "📅"
            }
        ]
    }


@router.post("/openclaw/execute-action/{action_id}")
async def execute_quick_action(action_id: str):
    """
    Esegue un'azione rapida specifica.
    Utilizzato da Clawdbot per eseguire comandi predefiniti.
    """
    db = Database.get_db()
    
    if action_id == "riconcilia_mutui":
        # Chiama la riconciliazione mutui
        from app.routers.mutui import riconcilia_mutui_con_estratto_conto
        result = await riconcilia_mutui_con_estratto_conto(tolleranza_giorni=10)
        return {
            "action": action_id,
            "success": True,
            "result": result
        }
    
    elif action_id == "dashboard_mutui":
        # Statistiche mutui
        pipeline = [
            {
                "$group": {
                    "_id": None,
                    "numero_mutui": {"$sum": 1},
                    "importo_totale": {"$sum": "$importo_accordato"},
                    "totale_pagato": {"$sum": "$totale_pagato"},
                    "debito_residuo": {"$sum": "$debito_residuo_totale"}
                }
            }
        ]
        result = await db.mutui.aggregate(pipeline).to_list(length=1)
        stats = result[0] if result else {}
        stats.pop("_id", None)
        return {
            "action": action_id,
            "success": True,
            "result": {
                "messaggio": f"Hai {stats.get('numero_mutui', 0)} mutui attivi per un totale di €{stats.get('importo_totale', 0):,.2f}. "
                            f"Hai già pagato €{stats.get('totale_pagato', 0):,.2f} e il debito residuo è €{stats.get('debito_residuo', 0):,.2f}.",
                "dati": stats
            }
        }
    
    elif action_id == "prossime_scadenze":
        # Prossime scadenze
        from datetime import timedelta
        oggi = datetime.now()
        fra_30_giorni = oggi + timedelta(days=30)
        
        scadenze = await db.scadenze.find({
            "data_scadenza": {
                "$gte": oggi.strftime("%Y-%m-%d"),
                "$lte": fra_30_giorni.strftime("%Y-%m-%d")
            },
            "completata": {"$ne": True}
        }, {"_id": 0, "titolo": 1, "data_scadenza": 1, "importo": 1, "tipo": 1}).sort("data_scadenza", 1).to_list(length=10)
        
        return {
            "action": action_id,
            "success": True,
            "result": {
                "messaggio": f"Hai {len(scadenze)} scadenze nei prossimi 30 giorni.",
                "scadenze": scadenze
            }
        }
    
    else:
        raise HTTPException(status_code=404, detail=f"Azione '{action_id}' non trovata")


@router.get("/openclaw/whatsapp/status")
async def get_whatsapp_status_endpoint():
    """Get WhatsApp connection status"""
    return get_whatsapp_status()


# ============== Proxy Endpoints ==============

@router.api_route("/openclaw/ui/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def proxy_openclaw_ui(request: Request, path: str = ""):
    """Proxy to OpenClaw Control UI"""
    # Check if gateway is running via supervisor OR if port is active
    is_running = SupervisorClient.status()
    if not is_running:
        # Also try to check if port is alive (might have been started externally)
        try:
            async with httpx.AsyncClient() as probe:
                r = await probe.get(f"http://127.0.0.1:{MOLTBOT_PORT}/", timeout=2.0)
                is_running = r.status_code == 200
        except:
            pass
    
    if not is_running:
        return HTMLResponse(
            content="<html><body><h1>OpenClaw non attivo</h1><p>Avvia OpenClaw dalla pagina Admin.</p></body></html>",
            status_code=503
        )
    
    target_url = f"http://127.0.0.1:{MOLTBOT_PORT}/{path}"
    if request.query_params:
        target_url += f"?{request.query_params}"
    
    async with httpx.AsyncClient() as client:
        try:
            headers = dict(request.headers)
            headers.pop("host", None)
            headers.pop("content-length", None)
            
            response = await client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=await request.body(),
                timeout=30.0
            )
            
            exclude_headers = {"content-encoding", "content-length", "transfer-encoding", "connection"}
            response_headers = {k: v for k, v in response.headers.items() if k.lower() not in exclude_headers}
            
            content = response.content
            content_type = response.headers.get("content-type", "")
            
            # Inject WebSocket override for HTML
            if "text/html" in content_type:
                token = get_token_from_config() or ""
                # Fix base path and WebSocket URL
                ws_override = f'''
<script>
// Override base path for Clawdbot UI
window.__CLAWDBOT_CONTROL_UI_BASE_PATH__ = "/api/openclaw/ui";
window.__MOLTBOT_PROXY_TOKEN__ = "{token}";

// WebSocket proxy override - intercept ALL WebSocket connections
(function() {{
    const origWS = window.WebSocket;
    window.WebSocket = function(url, protocols) {{
        // Redirect any connection to our proxy
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const proxyUrl = wsProtocol + '//' + window.location.host + '/api/openclaw/ws';
        console.log('[OpenClaw Proxy] Original URL:', url, '-> Proxy URL:', proxyUrl);
        const ws = new origWS(proxyUrl, protocols);
        return ws;
    }};
    window.WebSocket.prototype = origWS.prototype;
    window.WebSocket.CONNECTING = origWS.CONNECTING;
    window.WebSocket.OPEN = origWS.OPEN;
    window.WebSocket.CLOSING = origWS.CLOSING;
    window.WebSocket.CLOSED = origWS.CLOSED;
}})();
</script>
'''
                content_str = content.decode('utf-8', errors='ignore')
                # Remove old base path script and inject new one
                content_str = content_str.replace(
                    'window.__CLAWDBOT_CONTROL_UI_BASE_PATH__=""',
                    'window.__CLAWDBOT_CONTROL_UI_BASE_PATH__="/api/openclaw/ui"'
                )
                if '</head>' in content_str:
                    content_str = content_str.replace('</head>', ws_override + '</head>')
                content = content_str.encode('utf-8')
            
            return Response(content=content, status_code=response.status_code, headers=response_headers)
        except Exception as e:
            logger.error(f"Proxy error: {e}")
            raise HTTPException(status_code=502, detail="Errore connessione OpenClaw")


@router.get("/openclaw/ui")
async def proxy_openclaw_ui_root():
    """Redirect to OpenClaw UI with token"""
    token = get_token_from_config()
    if token:
        return Response(status_code=307, headers={"Location": f"/api/openclaw/ui/?token={token}"})
    return Response(status_code=307, headers={"Location": "/api/openclaw/ui/"})


@router.websocket("/openclaw/ws")
async def websocket_proxy(websocket: WebSocket):
    """WebSocket proxy for OpenClaw - transparent proxy without auth handling"""
    await websocket.accept()
    
    # Check if gateway is running via supervisor or direct port check
    is_running = SupervisorClient.status()
    if not is_running:
        try:
            async with httpx.AsyncClient() as probe:
                r = await probe.get(f"http://127.0.0.1:{MOLTBOT_PORT}/", timeout=2.0)
                is_running = r.status_code == 200
        except:
            pass
    
    if not is_running:
        await websocket.close(code=1013, reason="OpenClaw non attivo")
        return
    
    ws_url = f"ws://127.0.0.1:{MOLTBOT_PORT}/"
    
    logger.info(f"WebSocket proxy connecting to {ws_url} (no auth - allowInsecureAuth mode)")
    
    try:
        # Connect without auth headers - let the UI handle auth via allowInsecureAuth
        async with websockets.connect(ws_url, ping_interval=20) as moltbot_ws:
            
            async def client_to_moltbot():
                try:
                    while True:
                        data = await websocket.receive()
                        if data["type"] == "websocket.receive":
                            if "text" in data:
                                await moltbot_ws.send(data["text"])
                            elif "bytes" in data:
                                await moltbot_ws.send(data["bytes"])
                        elif data["type"] == "websocket.disconnect":
                            break
                except WebSocketDisconnect:
                    pass
            
            async def moltbot_to_client():
                try:
                    async for message in moltbot_ws:
                        if websocket.client_state == WebSocketState.CONNECTED:
                            if isinstance(message, str):
                                await websocket.send_text(message)
                            else:
                                await websocket.send_bytes(message)
                except ConnectionClosed:
                    pass
            
            done, pending = await asyncio.wait(
                [asyncio.create_task(client_to_moltbot()), asyncio.create_task(moltbot_to_client())],
                return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close()
