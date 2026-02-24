"""
OpenAPI.com Imprese Integration
Servizio per recuperare dati anagrafici aziendali (fornitori) da OpenAPI.it
"""
import httpx
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# URL Base API
OPENAPI_BASE_URL = "https://imprese.openapi.it"
OPENAPI_SANDBOX_URL = "https://test.imprese.openapi.it"


class OpenAPIImprese:
    """Client per API OpenAPI.com Imprese"""
    
    def __init__(self, token: str, sandbox: bool = False):
        self.token = token
        self.base_url = OPENAPI_SANDBOX_URL if sandbox else OPENAPI_BASE_URL
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        }
    
    async def get_base_info(self, piva_or_cf: str) -> Dict[str, Any]:
        """
        Recupera informazioni base di un'azienda.
        
        Args:
            piva_or_cf: Partita IVA o Codice Fiscale
            
        Returns:
            Dict con dati azienda (denominazione, indirizzo, pec, etc.)
        """
        url = f"{self.base_url}/base/{piva_or_cf}"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(url, headers=self.headers)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        return {"success": True, "data": data.get("data", {})}
                    return {"success": False, "error": data.get("message", "Errore API")}
                    
                elif response.status_code == 204:
                    return {"success": False, "error": "Azienda non trovata"}
                    
                elif response.status_code == 402:
                    return {"success": False, "error": "Credito insufficiente"}
                    
                elif response.status_code == 404:
                    return {"success": False, "error": "Partita IVA non trovata"}
                    
                else:
                    return {"success": False, "error": f"Errore HTTP {response.status_code}"}
                    
            except Exception as e:
                logger.error(f"Errore chiamata OpenAPI base: {e}")
                return {"success": False, "error": str(e)}
    
    async def get_advance_info(self, piva_or_cf: str) -> Dict[str, Any]:
        """
        Recupera informazioni avanzate (include PEC, codice ATECO, bilanci).
        
        Args:
            piva_or_cf: Partita IVA o Codice Fiscale
            
        Returns:
            Dict con dati completi azienda
        """
        url = f"{self.base_url}/advance/{piva_or_cf}"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(url, headers=self.headers)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        return {"success": True, "data": data.get("data", {})}
                    return {"success": False, "error": data.get("message", "Errore API")}
                    
                elif response.status_code == 204:
                    return {"success": False, "error": "Azienda non trovata"}
                    
                elif response.status_code == 402:
                    return {"success": False, "error": "Credito insufficiente"}
                    
                else:
                    return {"success": False, "error": f"Errore HTTP {response.status_code}"}
                    
            except Exception as e:
                logger.error(f"Errore chiamata OpenAPI advance: {e}")
                return {"success": False, "error": str(e)}
    
    async def get_pec(self, piva_or_cf: str) -> Dict[str, Any]:
        """Recupera solo la PEC di un'azienda."""
        url = f"{self.base_url}/pec/{piva_or_cf}"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(url, headers=self.headers)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        return {"success": True, "pec": data.get("data", {}).get("pec")}
                    return {"success": False, "error": data.get("message")}
                    
                return {"success": False, "error": f"Errore HTTP {response.status_code}"}
                    
            except Exception as e:
                return {"success": False, "error": str(e)}
    
    async def get_codice_sdi(self, piva_or_cf: str) -> Dict[str, Any]:
        """Recupera il Codice Destinatario SDI."""
        url = f"{self.base_url}/codice_destinatario/{piva_or_cf}"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(url, headers=self.headers)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        return {"success": True, "codice_sdi": data.get("data", {}).get("codice_destinatario")}
                    return {"success": False, "error": data.get("message")}
                    
                return {"success": False, "error": f"Errore HTTP {response.status_code}"}
                    
            except Exception as e:
                return {"success": False, "error": str(e)}
    
    async def search_by_name(self, query: str) -> Dict[str, Any]:
        """
        Cerca aziende per nome (autocomplete).
        
        Args:
            query: Nome o parte del nome (usa * come wildcard)
            
        Returns:
            Lista di aziende trovate
        """
        # Aggiungi wildcard se non presente
        if not query.startswith("*") and not query.endswith("*"):
            query = f"*{query}*"
            
        url = f"{self.base_url}/autocomplete/{query}"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(url, headers=self.headers)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        return {"success": True, "results": data.get("data", [])}
                    return {"success": False, "error": data.get("message")}
                    
                return {"success": False, "error": f"Errore HTTP {response.status_code}"}
                    
            except Exception as e:
                return {"success": False, "error": str(e)}


def map_openapi_to_fornitore(openapi_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Mappa i dati OpenAPI al formato fornitore interno.
    
    Args:
        openapi_data: Dati da OpenAPI /advance o /base
        
    Returns:
        Dict con campi mappati per il fornitore
    """
    dettaglio = openapi_data.get("dettaglio", {})
    
    fornitore_update = {
        # Dati anagrafici
        "ragione_sociale": openapi_data.get("denominazione"),
        "partita_iva": openapi_data.get("piva"),
        "codice_fiscale": openapi_data.get("cf"),
        
        # Indirizzo
        "indirizzo": openapi_data.get("indirizzo"),
        "cap": openapi_data.get("cap"),
        "citta": openapi_data.get("comune"),
        "provincia": openapi_data.get("provincia"),
        
        # Contatti
        "pec": dettaglio.get("pec"),
        
        # Fatturazione elettronica
        "codice_sdi": openapi_data.get("codice_destinatario"),
        
        # Info aziendali
        "codice_ateco": dettaglio.get("codice_ateco"),
        "descrizione_ateco": dettaglio.get("descrizione_ateco"),
        "rea": dettaglio.get("rea"),
        "cciaa": dettaglio.get("cciaa"),
        "stato_attivita": openapi_data.get("stato_attivita"),
        "data_iscrizione": openapi_data.get("data_iscrizione"),
        
        # Coordinate GPS
        "gps": openapi_data.get("gps", {}).get("coordinates"),
        
        # Metadata
        "openapi_last_update": datetime.now(timezone.utc).isoformat(),
        "openapi_id": openapi_data.get("id")
    }
    
    # Rimuovi campi None
    return {k: v for k, v in fornitore_update.items() if v is not None}
