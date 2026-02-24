"""
OpenAPI.com Company Integration
Servizio per recuperare dati anagrafici aziendali (fornitori) da OpenAPI Company API
"""
import httpx
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# URL Base API - NOTA: è .com non .it
COMPANY_API_URL = "https://company.openapi.com"
COMPANY_SANDBOX_URL = "https://test.company.openapi.com"


class OpenAPICompany:
    """Client per API OpenAPI.com Company (nuova versione)"""
    
    def __init__(self, token: str, sandbox: bool = False):
        self.token = token
        self.base_url = COMPANY_SANDBOX_URL if sandbox else COMPANY_API_URL
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        }
    
    async def get_start_info(self, piva_or_cf: str) -> Dict[str, Any]:
        """
        Recupera informazioni base di un'azienda italiana.
        Endpoint: /IT-start/{vatCode_taxCode_or_id}
        """
        url = f"{self.base_url}/IT-start/{piva_or_cf}"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(url, headers=self.headers)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        # L'API restituisce una lista, prendiamo il primo elemento
                        items = data.get("data", [])
                        if items and isinstance(items, list):
                            return {"success": True, "data": items[0]}
                        return {"success": True, "data": items}
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
                logger.error(f"Errore chiamata OpenAPI IT-start: {e}")
                return {"success": False, "error": str(e)}
    
    async def get_advanced_info(self, piva_or_cf: str) -> Dict[str, Any]:
        """
        Recupera informazioni avanzate (include ATECO, bilanci, dipendenti).
        Endpoint: /IT-advanced/{vatCode_taxCode_or_id}
        """
        url = f"{self.base_url}/IT-advanced/{piva_or_cf}"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(url, headers=self.headers)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        items = data.get("data", [])
                        if items and isinstance(items, list):
                            return {"success": True, "data": items[0]}
                        return {"success": True, "data": items}
                    return {"success": False, "error": data.get("message", "Errore API")}
                else:
                    return {"success": False, "error": f"Errore HTTP {response.status_code}"}
                    
            except Exception as e:
                logger.error(f"Errore chiamata OpenAPI IT-advanced: {e}")
                return {"success": False, "error": str(e)}
    
    async def get_pec(self, piva_or_cf: str) -> Dict[str, Any]:
        """Recupera la PEC di un'azienda."""
        url = f"{self.base_url}/IT-pec/{piva_or_cf}"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(url, headers=self.headers)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        items = data.get("data", [])
                        if items and isinstance(items, list) and items:
                            return {"success": True, "pec": items[0].get("pec")}
                        return {"success": True, "pec": None}
                    return {"success": False, "error": data.get("message")}
                return {"success": False, "error": f"Errore HTTP {response.status_code}"}
                    
            except Exception as e:
                return {"success": False, "error": str(e)}
    
    async def get_sdi_code(self, piva_or_cf: str) -> Dict[str, Any]:
        """Recupera il Codice Destinatario SDI."""
        url = f"{self.base_url}/IT-sdicode/{piva_or_cf}"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(url, headers=self.headers)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        items = data.get("data", [])
                        if items and isinstance(items, list) and items:
                            return {"success": True, "codice_sdi": items[0].get("sdiCode")}
                        return {"success": True, "codice_sdi": None}
                    return {"success": False, "error": data.get("message")}
                return {"success": False, "error": f"Errore HTTP {response.status_code}"}
                    
            except Exception as e:
                return {"success": False, "error": str(e)}
    
    async def search_company(self, company_name: str = None, provincia: str = None, 
                             limit: int = 10) -> Dict[str, Any]:
        """
        Cerca aziende per nome o altri criteri.
        Endpoint: /IT-search
        """
        url = f"{self.base_url}/IT-search"
        params = {"limit": limit}
        
        if company_name:
            params["companyName"] = f"*{company_name}*"
        if provincia:
            params["province"] = provincia
            
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(url, headers=self.headers, params=params)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        return {"success": True, "results": data.get("data", [])}
                    return {"success": False, "error": data.get("message")}
                return {"success": False, "error": f"Errore HTTP {response.status_code}"}
                    
            except Exception as e:
                return {"success": False, "error": str(e)}
    
    async def get_full_info(self, piva_or_cf: str) -> Dict[str, Any]:
        """
        Recupera TUTTI i dati disponibili (antiriciclaggio, stakeholder, bilanci completi).
        Endpoint: /IT-full/{vatCode_or_taxCode}
        NOTA: Questo endpoint è più costoso
        """
        url = f"{self.base_url}/IT-full/{piva_or_cf}"
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.get(url, headers=self.headers)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        return {"success": True, "data": data.get("data", {})}
                    return {"success": False, "error": data.get("message", "Errore API")}
                else:
                    return {"success": False, "error": f"Errore HTTP {response.status_code}"}
                    
            except Exception as e:
                logger.error(f"Errore chiamata OpenAPI IT-full: {e}")
                return {"success": False, "error": str(e)}


def map_company_to_fornitore(company_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Mappa i dati Company API al formato fornitore interno.
    
    Args:
        company_data: Dati da Company API /IT-start o /IT-advanced
        
    Returns:
        Dict con campi mappati per il fornitore
    """
    address = company_data.get("address", {})
    registered = address.get("registeredOffice", {})
    
    fornitore_update = {
        # Dati anagrafici
        "ragione_sociale": company_data.get("companyName"),
        "partita_iva": company_data.get("vatCode"),
        "codice_fiscale": company_data.get("taxCode"),
        
        # Indirizzo
        "indirizzo": registered.get("streetName"),
        "cap": registered.get("zipCode"),
        "citta": registered.get("town"),
        "provincia": registered.get("province"),
        
        # Fatturazione elettronica
        "codice_sdi": company_data.get("sdiCode"),
        
        # Info aziendali
        "stato_attivita": company_data.get("activityStatus"),
        "data_iscrizione": company_data.get("registrationDate"),
        
        # Coordinate GPS
        "gps": registered.get("gps"),
        
        # ID OpenAPI
        "openapi_id": company_data.get("id"),
        
        # Metadata
        "openapi_last_update": datetime.now(timezone.utc).isoformat()
    }
    
    # Aggiungi dati avanzati se presenti
    ateco = company_data.get("atecoClassification", {})
    if ateco:
        fornitore_update["codice_ateco"] = ateco.get("ateco", {}).get("code")
        fornitore_update["descrizione_ateco"] = ateco.get("ateco", {}).get("description")
    
    ecofin = company_data.get("ecofin", {})
    if ecofin:
        fornitore_update["fatturato"] = ecofin.get("turnover")
        fornitore_update["capitale_sociale"] = ecofin.get("shareCapital")
    
    employees = company_data.get("employees", {})
    if employees:
        fornitore_update["numero_dipendenti"] = employees.get("employee")
    
    # Rimuovi campi None
    return {k: v for k, v in fornitore_update.items() if v is not None}
