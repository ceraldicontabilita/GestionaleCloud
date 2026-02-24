"""
OpenAPI.com Automotive Integration
Servizio per recuperare dati veicoli da targa tramite OpenAPI Automotive
"""
import httpx
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

AUTOMOTIVE_API_URL = "https://automotive.openapi.com"
AUTOMOTIVE_SANDBOX_URL = "https://test.automotive.openapi.com"


class OpenAPIAutomotive:
    """Client per API OpenAPI.com Automotive"""
    
    def __init__(self, token: str, sandbox: bool = False):
        self.token = token
        self.base_url = AUTOMOTIVE_SANDBOX_URL if sandbox else AUTOMOTIVE_API_URL
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        }
    
    async def get_car_info(self, targa: str, country: str = "IT") -> Dict[str, Any]:
        """
        Recupera informazioni su un'auto dalla targa.
        
        Args:
            targa: Targa del veicolo (es: GE911SC)
            country: Paese (IT, UK, FR, DE, ES, PT)
            
        Returns:
            Dict con dati veicolo
        """
        # Normalizza targa
        targa = targa.upper().replace(" ", "").replace("-", "")
        
        url = f"{self.base_url}/{country}-car/{targa}"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(url, headers=self.headers)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        return {"success": True, "data": data.get("data", {})}
                    return {"success": False, "error": data.get("message", "Errore API")}
                    
                elif response.status_code == 402:
                    return {"success": False, "error": "Credito insufficiente"}
                elif response.status_code == 404:
                    return {"success": False, "error": "Targa non trovata"}
                elif response.status_code == 406:
                    return {"success": False, "error": "Formato targa non valido"}
                else:
                    return {"success": False, "error": f"Errore HTTP {response.status_code}"}
                    
            except Exception as e:
                logger.error(f"Errore chiamata Automotive API: {e}")
                return {"success": False, "error": str(e)}
    
    async def get_bike_info(self, targa: str, country: str = "IT") -> Dict[str, Any]:
        """Recupera informazioni su una moto dalla targa."""
        targa = targa.upper().replace(" ", "").replace("-", "")
        url = f"{self.base_url}/{country}-bike/{targa}"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(url, headers=self.headers)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        return {"success": True, "data": data.get("data", {})}
                    return {"success": False, "error": data.get("message")}
                return {"success": False, "error": f"Errore HTTP {response.status_code}"}
                    
            except Exception as e:
                return {"success": False, "error": str(e)}
    
    async def get_insurance_info(self, targa: str, country: str = "IT") -> Dict[str, Any]:
        """Recupera informazioni sull'assicurazione del veicolo."""
        targa = targa.upper().replace(" ", "").replace("-", "")
        url = f"{self.base_url}/{country}-insurance/{targa}"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(url, headers=self.headers)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        return {"success": True, "data": data.get("data", {})}
                    return {"success": False, "error": data.get("message")}
                return {"success": False, "error": f"Errore HTTP {response.status_code}"}
                    
            except Exception as e:
                return {"success": False, "error": str(e)}


def map_automotive_to_veicolo(auto_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Mappa i dati Automotive API al formato veicolo interno.
    
    Args:
        auto_data: Dati da Automotive API /IT-car
        
    Returns:
        Dict con campi mappati per il veicolo
    """
    veicolo_update = {
        # Targa
        "targa": auto_data.get("LicensePlate"),
        
        # Dati veicolo
        "marca": auto_data.get("CarMake"),
        "modello": auto_data.get("CarModel"),
        "descrizione": auto_data.get("Description"),
        "versione": auto_data.get("Version"),
        
        # Anno e immatricolazione
        "anno_immatricolazione": auto_data.get("RegistrationYear"),
        
        # Motore
        "cilindrata": auto_data.get("EngineSize"),
        "alimentazione": auto_data.get("FuelType"),
        "potenza_cv": auto_data.get("PowerCV"),
        "potenza_kw": auto_data.get("PowerKW"),
        "potenza_fiscale": auto_data.get("PowerFiscal"),
        
        # Carrozzeria
        "numero_porte": auto_data.get("NumberOfDoors"),
        "tipo_carrozzeria": auto_data.get("BodyStyle"),
        
        # Identificativi
        "vin": auto_data.get("Vin"),
        "ktype": auto_data.get("KType"),
        
        # Metadata
        "openapi_automotive_timestamp": auto_data.get("TimeStamp"),
        "openapi_last_update": datetime.now(timezone.utc).isoformat()
    }
    
    # Rimuovi campi None o vuoti
    return {k: v for k, v in veicolo_update.items() if v is not None and v != ""}
