"""Allergeni del Menu: alert dei prodotti senza dichiarazione ed esclusioni
di chi una dichiarazione non deve averla.

Gli allergeni sono un obbligo di legge (Regolamento UE 1169/2011, D.Lgs.
231/2017): questa pagina serve a non lasciarne scoperto nessuno. Ma l'elenco
"senza allergeni dichiarati" contiene anche whisky, distillati e bibite in
bottiglia, che allergeni da dichiarare non ne hanno: finche' restano li' il
numero non scende mai e l'alert diventa rumore.

19/09/2026 (richiesta del titolare): si esclude un prodotto - o un'intera
categoria/sottocategoria - dalla verifica. L'esclusione dice "non richiede la
dichiarazione allergeni", NON "nascondilo dal menu": e' un dato di
conformita', quindi si conserva, si vede e si puo' revocare.

Perche' le esclusioni stanno in una tabella a parte
(``menu.menu_allergeni_esclusioni``) e non in una colonna di
``menu_products``: la sync Qromo (``app/menu/qromo_sync.py``) cancella e
reinserisce tutte le righe con ``origine IS NULL``, e le righe reinserite
portano solo le colonne di ``trasforma_catalogo``. Un flag dentro
``menu_products`` sparirebbe alla prima sincronizzazione - e' gia' cosi' che
si perdono gli allergeni scritti a mano su un prodotto Qromo. Gli id Qromo
sono invece stabili tra un sync e l'altro, quindi un'esclusione chiavata su
quell'id sopravvive.

"Collega a una ricetta" non vive piu' qui: la strada ricetta -> prodotto del
Menu e' quella del ponte ``app/lotti/servizi/menu_bridge.py``, che pubblica la
ricetta nel Menu con gli allergeni gia' calcolati dagli ingredienti. Averne
una seconda, manuale e dal lato sbagliato, era un doppione.
"""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.menu.routes.qrcode_routes import verify_token
from app.menu.supabase_client import supabase

router = APIRouter(prefix="/api/admin/allergeni", tags=["Allergeni"])

TABELLA_ESCLUSIONI = "menu_allergeni_esclusioni"

Tipo = Literal["prodotto", "categoria", "sottocategoria"]

# tipo di esclusione -> tabella dell'entita' esclusa
_TABELLA_PER_TIPO = {
    "prodotto": "menu_products",
    "categoria": "menu_categories",
    "sottocategoria": "menu_subcategories",
}


def _leggi_esclusioni() -> list:
    res = (
        supabase.table(TABELLA_ESCLUSIONI)
        .select("tipo,riferimento_id,motivo,creato_il,creato_da")
        .execute()
    )
    return res.data or []


def _insiemi_esclusi(esclusioni: list) -> dict:
    """Gli id esclusi raggruppati per tipo, pronti per il confronto."""
    per_tipo = {"prodotto": set(), "categoria": set(), "sottocategoria": set()}
    for e in esclusioni:
        tipo = e.get("tipo")
        if tipo in per_tipo and e.get("riferimento_id") is not None:
            per_tipo[tipo].add(e["riferimento_id"])
    return per_tipo


def _prodotto_escluso(prodotto: dict, esclusi: dict) -> bool:
    return (
        prodotto.get("id") in esclusi["prodotto"]
        or prodotto.get("category_id") in esclusi["categoria"]
        or prodotto.get("subcategory_id") in esclusi["sottocategoria"]
    )


def _nomi(tabella: str) -> dict:
    res = supabase.table(tabella).select("id,name_it").execute()
    return {r["id"]: r.get("name_it") for r in (res.data or [])}


@router.get("/mancanti")
async def prodotti_senza_allergeni(_username: str = Depends(verify_token)):
    """Prodotti che devono dichiarare gli allergeni e non lo fanno.

    Restituisce anche categoria e sottocategoria di ogni prodotto, cosi' la
    pagina puo' raggrupparli ed escludere un reparto intero in un colpo solo,
    e il conteggio di quelli tenuti fuori da un'esclusione."""
    res = (
        supabase.table("menu_products")
        .select("id,name_it,description_it,allergens,category_id,subcategory_id,visible")
        .execute()
    )
    tutti = res.data or []
    esclusi = _insiemi_esclusi(_leggi_esclusioni())

    senza_allergeni = [p for p in tutti if not (p.get("allergens") or [])]
    da_dichiarare = [p for p in senza_allergeni if not _prodotto_escluso(p, esclusi)]

    nomi_categorie = _nomi("menu_categories")
    nomi_sottocategorie = _nomi("menu_subcategories")

    prodotti = [
        {
            "id": p["id"],
            "name_it": p["name_it"],
            "description_it": p.get("description_it"),
            "category_id": p.get("category_id"),
            "categoria_nome": nomi_categorie.get(p.get("category_id")),
            "subcategory_id": p.get("subcategory_id"),
            "sottocategoria_nome": nomi_sottocategorie.get(p.get("subcategory_id")),
            "visible": p.get("visible", True),
        }
        for p in da_dichiarare
    ]
    return {
        "totale_prodotti": len(tutti),
        "senza_allergeni": len(prodotti),
        "esclusi": len(senza_allergeni) - len(prodotti),
        "prodotti": sorted(prodotti, key=lambda p: (p["name_it"] or "").lower()),
    }


@router.get("/esclusioni")
async def elenco_esclusioni(_username: str = Depends(verify_token)):
    """Le esclusioni attive, con il nome dell'entita' esclusa: devono restare
    visibili e revocabili, non essere una scelta invisibile."""
    esclusioni = _leggi_esclusioni()
    nomi = {
        "prodotto": _nomi("menu_products"),
        "categoria": _nomi("menu_categories"),
        "sottocategoria": _nomi("menu_subcategories"),
    }
    voci = [
        {**e, "nome": nomi.get(e.get("tipo"), {}).get(e.get("riferimento_id"))}
        for e in esclusioni
    ]
    voci.sort(key=lambda v: (v.get("tipo") or "", (v.get("nome") or "").lower()))
    return {"esclusioni": voci, "totale": len(voci)}


class NuovaEsclusione(BaseModel):
    tipo: Tipo
    riferimento_id: int
    motivo: Optional[str] = Field(default=None, max_length=500)


@router.post("/esclusioni")
async def crea_esclusione(payload: NuovaEsclusione, username: str = Depends(verify_token)):
    """Segna che un prodotto (o un'intera categoria/sottocategoria) non
    richiede la dichiarazione allergeni. Il motivo e' facoltativo."""
    tabella = _TABELLA_PER_TIPO[payload.tipo]
    esiste = supabase.table(tabella).select("id,name_it").eq("id", payload.riferimento_id).execute()
    if not esiste.data:
        raise HTTPException(status_code=404, detail=f"{payload.tipo.capitalize()} non trovato")

    motivo = (payload.motivo or "").strip() or None
    riga = {
        "tipo": payload.tipo,
        "riferimento_id": payload.riferimento_id,
        "motivo": motivo,
        "creato_da": username,
    }

    gia_escluso = (
        supabase.table(TABELLA_ESCLUSIONI)
        .select("tipo,riferimento_id")
        .eq("tipo", payload.tipo)
        .eq("riferimento_id", payload.riferimento_id)
        .execute()
    )
    if gia_escluso.data:
        (
            supabase.table(TABELLA_ESCLUSIONI)
            .update({"motivo": motivo, "creato_da": username})
            .eq("tipo", payload.tipo)
            .eq("riferimento_id", payload.riferimento_id)
            .execute()
        )
        esito = "aggiornata"
    else:
        supabase.table(TABELLA_ESCLUSIONI).insert(riga).execute()
        esito = "creata"

    return {
        "success": True,
        "esito": esito,
        "esclusione": {**riga, "nome": esiste.data[0].get("name_it")},
    }


@router.delete("/esclusioni/{tipo}/{riferimento_id}")
async def revoca_esclusione(tipo: Tipo, riferimento_id: int, _username: str = Depends(verify_token)):
    """Ripristino: il prodotto (o il reparto) torna nell'elenco di chi deve
    dichiarare gli allergeni."""
    res = (
        supabase.table(TABELLA_ESCLUSIONI)
        .delete()
        .eq("tipo", tipo)
        .eq("riferimento_id", riferimento_id)
        .execute()
    )
    if not (res.data or []):
        raise HTTPException(status_code=404, detail="Esclusione non trovata")
    return {"success": True, "tipo": tipo, "riferimento_id": riferimento_id}
