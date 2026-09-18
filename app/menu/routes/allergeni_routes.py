"""Allergeni: alert dei prodotti senza dichiarazione, associazione dalla
ricetta di Lotti gia' collegata.

18/09/2026: 108 dei 325 prodotti del Menu non avevano allergeni dichiarati.
Un abbinamento automatico per somiglianza di nome tra i prodotti del Menu e le
719 ricette di Lotti e' stato provato e scartato: le due app sono state scritte
in momenti diversi, senza un id in comune, e un confronto per testo produce
accoppiamenti sbagliati (es. "Aspritz", "Campari Spritz", "Hugo Spritz" finiti
tutti sulla stessa ricetta generica "Spritz"; il te' "Caramel" abbinato a
ricette di caramelle; il liquore "Diplomatico" abbinato al dolce "Diplomatico
Napoletano" solo perche' si chiamano uguale). Scrivere un allergene sbagliato
su un'etichetta e' peggio che non scriverne nessuno.

L'unica associazione automatica sicura e' per id (``lotti_ref``), dopo che una
persona ha scelto la ricetta giusta una volta in ``/associa``: da quel momento
il prodotto resta agganciato a quella ricetta e ``/risincronizza`` ne riallinea
gli allergeni ogni volta che servisse (es. dopo una correzione fatta su
Lotti), senza dover rifare la scelta.

Le credenziali per leggere le ricette di Lotti (``LOTTI_SUPABASE_URL``,
``LOTTI_SUPABASE_ANON_KEY``, ``LOTTI_DB_SECRET``) sono le stesse gia'
configurate su Render per il backend di Lotti: GestionaleCloud e' un solo
servizio Render, un solo processo, le variabili d'ambiente sono condivise.
Nessun nuovo segreto da aggiungere.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import os
import httpx

from app.menu.routes.qrcode_routes import verify_token
from app.menu.supabase_client import supabase

router = APIRouter(prefix="/api/admin/allergeni", tags=["Allergeni"])

# Stessa corrispondenza di menu.menu_allergens: id canonico (quello salvato in
# menu_products.allergens) <- nome italiano (quello scritto nelle ricette di
# Lotti). Le 14 categorie del regolamento UE 1169/2011 sono stabili; se
# cambiassero andrebbe aggiornata anche la tabella menu.menu_allergens.
_NOME_IT_A_ID = {
    "glutine": "gluten", "latte": "milk", "uova": "eggs",
    "frutta a guscio": "nuts", "pesce": "fish", "soia": "soy",
    "solfiti": "sulphites", "crostacei": "crustaceans", "molluschi": "molluscs",
    "sedano": "celery", "senape": "mustard", "sesamo": "sesame",
    "lupini": "lupin", "arachidi": "peanuts",
}


def _traduci_allergeni(nomi_it) -> list:
    tradotti = []
    for nome in nomi_it or []:
        id_canonico = _NOME_IT_A_ID.get(str(nome).strip().lower())
        if id_canonico and id_canonico not in tradotti:
            tradotti.append(id_canonico)
    return sorted(tradotti)


class _ClienteRicetteLotti:
    """Legge le ricette di Lotti in sola lettura tramite l'RPC gia' usata dal
    backend di Lotti stesso (``lotti_list_docs``): stesso meccanismo di
    autorizzazione, nessuna scrittura, nessuna tabella nuova."""

    def __init__(self):
        self.url = os.environ.get("LOTTI_SUPABASE_URL", "").rstrip("/")
        self.api_key = os.environ.get("LOTTI_SUPABASE_ANON_KEY", "")
        self.secret = os.environ.get("LOTTI_DB_SECRET", "")

    @property
    def configurato(self) -> bool:
        return bool(self.url and self.api_key and self.secret)

    async def ricette(self) -> list:
        if not self.configurato:
            return []
        async with httpx.AsyncClient(
            base_url=f"{self.url}/rest/v1",
            headers={
                "apikey": self.api_key,
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(30.0, connect=10.0),
        ) as client:
            offset, righe = 0, []
            while True:
                r = await client.post("/rpc/lotti_list_docs", json={
                    "p_secret": self.secret, "p_collection": "ricette",
                    "p_offset": offset, "p_limit": 500,
                })
                r.raise_for_status()
                pagina = r.json() or {}
                items = pagina.get("items") or []
                righe.extend(items)
                offset += len(items)
                if not items or offset >= int(pagina.get("total") or 0):
                    break
        risultato = []
        for row in righe:
            dato = row.get("data") or {}
            risultato.append({
                "doc_id": row.get("doc_id"),
                "nome": dato.get("nome") or "",
                "allergeni": _traduci_allergeni(dato.get("allergeni")),
                "verificato": bool(dato.get("allergeni_verificato")),
            })
        return risultato


_cliente_lotti = _ClienteRicetteLotti()


@router.get("/mancanti")
async def prodotti_senza_allergeni(_username: str = Depends(verify_token)):
    """Prodotti senza allergeni dichiarati, con evidenza se manca anche il
    collegamento a una ricetta di Lotti."""
    res = (
        supabase.table("menu_products")
        .select("id,name_it,description_it,allergens,lotti_ref,visible")
        .execute()
    )
    tutti = res.data or []
    mancanti = [
        {
            "id": p["id"],
            "name_it": p["name_it"],
            "description_it": p.get("description_it"),
            "lotti_ref": p.get("lotti_ref"),
            "visible": p.get("visible", True),
        }
        for p in tutti
        if not (p.get("allergens") or [])
    ]
    return {
        "totale_prodotti": len(tutti),
        "senza_allergeni": len(mancanti),
        "senza_ricetta_collegata": len([m for m in mancanti if not m["lotti_ref"]]),
        "prodotti": sorted(mancanti, key=lambda p: (p["name_it"] or "").lower()),
    }


@router.get("/ricette-lotti")
async def ricette_lotti(_username: str = Depends(verify_token)):
    """Elenco delle ricette di Lotti, per la scelta manuale da abbinare a un
    prodotto del Menu. Sola lettura: non scrive nulla su Lotti."""
    if not _cliente_lotti.configurato:
        raise HTTPException(
            status_code=503,
            detail=(
                "Collegamento a Lotti non configurato: mancano "
                "LOTTI_SUPABASE_URL / LOTTI_SUPABASE_ANON_KEY / LOTTI_DB_SECRET"
            ),
        )
    return {"ricette": await _cliente_lotti.ricette()}


class AssociaRicetta(BaseModel):
    product_id: int
    ricetta_doc_id: str


@router.post("/associa")
async def associa_ricetta(payload: AssociaRicetta, username: str = Depends(verify_token)):
    """Collega un prodotto a una ricetta di Lotti scelta da una persona e
    copia subito i suoi allergeni tradotti nel formato del Menu. Da qui in
    poi ``/risincronizza`` puo' riallinearli automaticamente, senza rifare la
    scelta ogni volta."""
    ricette = await _cliente_lotti.ricette()
    ricetta = next((r for r in ricette if r["doc_id"] == payload.ricetta_doc_id), None)
    if not ricetta:
        raise HTTPException(status_code=404, detail="Ricetta non trovata")

    res = (
        supabase.table("menu_products")
        .update({"lotti_ref": ricetta["doc_id"], "allergens": ricetta["allergeni"]})
        .eq("id", payload.product_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Prodotto non trovato")
    return {
        "success": True,
        "prodotto": res.data[0],
        "ricetta_nome": ricetta["nome"],
        "ricetta_verificata": ricetta["verificato"],
    }


@router.post("/risincronizza")
async def risincronizza(_username: str = Depends(verify_token)):
    """Per ogni prodotto gia' collegato a una ricetta, riallinea gli allergeni
    a quelli attuali della ricetta (es. dopo una correzione fatta su Lotti)."""
    ricette = {r["doc_id"]: r for r in await _cliente_lotti.ricette()}
    res = (
        supabase.table("menu_products")
        .select("id,name_it,allergens,lotti_ref")
        .execute()
    )
    aggiornati = []
    for prodotto in res.data or []:
        ref = prodotto.get("lotti_ref")
        if not ref or ref not in ricette:
            continue
        nuovi = ricette[ref]["allergeni"]
        if sorted(nuovi) != sorted(prodotto.get("allergens") or []):
            supabase.table("menu_products").update({"allergens": nuovi}).eq("id", prodotto["id"]).execute()
            aggiornati.append({"id": prodotto["id"], "name_it": prodotto["name_it"], "allergens": nuovi})
    return {"aggiornati": aggiornati, "totale_aggiornati": len(aggiornati)}
