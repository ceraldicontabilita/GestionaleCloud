from fastapi import APIRouter, HTTPException
from typing import List, Optional
from decimal import Decimal, InvalidOperation

from app.menu.supabase_client import inserisci_con_id_del_database, supabase
from app.menu.models.menu_models import (
    Category, CategoryCreate, CategoryUpdate,
    SubcategoryCreate, SubcategoryUpdate,
    ProductCreate, ProductUpdate, ProductVisibility,
    Allergen, MenuResponse
)

router = APIRouter(prefix="/api/menu", tags=["Menu"])


def _crea_riga(tabella: str, row: dict) -> int:
    """Crea una riga in ``menu_*`` lasciando l'``id`` al database (CLAUDE.md §5).

    Stesso percorso del ponte Lotti (``inserisci_con_id_del_database``): un solo
    modo di assegnare gli id, cosi' admin del Menu e Lotti non si contendono lo
    stesso numero. L'identity e' quella della migrazione
    ``20261007051337_menu_id_dal_database``; un rifiuto del database risale."""
    return inserisci_con_id_del_database(supabase, tabella, row)


# ================== Mappatura colonne DB (snake_case) <-> API (camelCase) ==================

def cat_out(row: dict) -> dict:
    return {"id": row["id"], "name": row["name"], "nameIT": row["name_it"], "image": row.get("image")}


def cat_in(data: dict) -> dict:
    return {"name": data["name"], "name_it": data["nameIT"], "image": data.get("image")}


def subcat_out(row: dict) -> dict:
    return {
        "id": row["id"], "category_id": row["category_id"],
        "name": row["name"], "nameIT": row["name_it"], "image": row.get("image"),
    }


def subcat_in(data: dict) -> dict:
    out = {"name": data["name"], "name_it": data["nameIT"], "image": data.get("image")}
    if "category_id" in data and data["category_id"] is not None:
        out["category_id"] = data["category_id"]
    return out


def _visibile(row: dict) -> bool:
    """Righe senza la chiave (vecchi dati/fixture) = visibili."""
    return row.get("visible") is not False


def prezzo_centesimi(prezzo) -> int | None:
    """Un prezzo pubblico e' finito, positivo e dichiarato al centesimo."""
    try:
        valore = Decimal(str(prezzo).replace("€", "").strip().replace(",", "."))
        if not valore.is_finite() or valore <= 0:
            return None
        centesimi = valore * 100
        if centesimi != centesimi.to_integral_value():
            return None
        return int(centesimi)
    except (InvalidOperation, ValueError, TypeError):
        return None


def _pubblicabile(row: dict) -> bool:
    return _visibile(row) and prezzo_centesimi(row.get("price")) is not None


def prod_out(row: dict) -> dict:
    return {
        "id": row["id"], "category_id": row["category_id"], "subcategory_id": row["subcategory_id"],
        "name": row["name"], "nameIT": row["name_it"], "price": row["price"],
        "description": row.get("description"), "descriptionIT": row.get("description_it"),
        "allergens": row.get("allergens") or [], "image": row.get("image"),
        # visible/origine: prodotti creati da Lotti (origine "lotti") nascono con
        # visible = scelta del titolare in Lotti ("menu_pubblico").
        "visible": _visibile(row), "pubblicabile": _pubblicabile(row), "origine": row.get("origine"),
        "lotti_ref": row.get("lotti_ref"),
        # prezzo AL BANCO (price e' quello al tavolo): None = non deciso
        "prezzo_banco": float(row["prezzo_banco"]) if row.get("prezzo_banco") is not None else None,
        # ID prodotto unico (PRD-000123): lo stesso in Menu, B&B e Lotti; lo assegna il database
        "codice_prodotto": row.get("codice_prodotto"),
        # scheda vendita (la scrive il ponte Lotti): canali, disponibilita', aggiunte e rimozioni
        "vendita_sala": row.get("vendita_sala") is not False,
        "vendita_delivery": row.get("vendita_delivery") is not False,
        "disponibile": row.get("disponibile") is not False,
        "aggiunte": row.get("aggiunte") or [],
        "rimozioni": row.get("rimozioni") or [],
        "menu_bb": row.get("menu_bb") is not False,
    }


def prezzo_banco_valido(valore) -> Optional[float]:
    """Prezzo al banco in euro: >0 e finito; 0 o assente = nessun prezzo. Negativi, nan e inf sono 400."""
    if valore is None:
        return None
    try:
        v = float(valore)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Prezzo al banco non valido")
    if v != v or v in (float("inf"), float("-inf")) or v < 0:
        raise HTTPException(status_code=400, detail="Prezzo al banco non valido")
    return round(v, 2) if v > 0 else None


def prod_in(data: dict) -> dict:
    out = {
        "name": data["name"], "name_it": data["nameIT"], "price": data["price"],
        "description": data.get("description"), "description_it": data.get("descriptionIT"),
        "allergens": data.get("allergens") if data.get("allergens") is not None else [],
        "image": data.get("image"),
        "visible": data.get("visible") is not False,
    }
    banco = prezzo_banco_valido(data.get("prezzo_banco"))
    if banco:
        out["prezzo_banco"] = banco
    if "category_id" in data and data["category_id"] is not None:
        out["category_id"] = data["category_id"]
    if "subcategory_id" in data and data["subcategory_id"] is not None:
        out["subcategory_id"] = data["subcategory_id"]
    return out


def allergen_out(row: dict) -> dict:
    return {
        "id": row["id"], "name": row["name"], "nameIT": row["name_it"], "icon": row.get("icon"),
        "descriptionIT": row.get("description_it"), "descriptionEN": row.get("description_en"),
    }


def _prodotti_pubblici(rows) -> list:
    """Il menu pubblico esclude righe nascoste o senza un prezzo valido."""
    return [prod_out(r) for r in rows if _pubblicabile(r)]


async def _fetch_all(*, catalogo_carta=False, catalogo_bb=False):
    categories = [cat_out(r) for r in supabase.table("menu_categories").select("*").order("id").execute().data]
    subcategories = [subcat_out(r) for r in supabase.table("menu_subcategories").select("*").order("id").execute().data]
    righe = supabase.table("menu_products").select("*").order("id").execute().data
    if catalogo_bb:
        # La spunta arriva dal ponte Lotti: Menu non rilegge le ricette.
        products = [prod_out(r) for r in righe if r.get("menu_bb") is not False and (
            r.get("origine") == "lotti" or _pubblicabile(r)
        )]
    else:
        products = [prod_out(r) for r in righe if _pubblicabile(r) or (
            catalogo_carta and r.get("origine") == "lotti" and _visibile(r)
        )]
    return categories, subcategories, products


def _sottocategorie_con_prodotti(subcategories, products) -> list:
    """Sottocategorie con almeno un prodotto visibile, gia' con i loro items."""
    piene = []
    for subcategory in subcategories:
        subcategory['items'] = [p for p in products if p.get('subcategory_id') == subcategory.get('id')]
        if subcategory['items']:
            piene.append(subcategory)
    return piene


def _build_hierarchy(categories, subcategories, products):
    """Gerarchia per i clienti: **niente categorie e sottocategorie vuote**.

    La home del Menu disegna ogni categoria come un riquadro con la sua
    immagine e il conteggio dei prodotti: una categoria senza prodotti
    visibili diventa un riquadro con immagine rotta (le categorie create da
    Lotti nascono con ``image = None``) e la scritta «0 prodotti». Succede
    appena il titolare prepara una categoria in anticipo, e succedeva in massa
    quando il ponte Lotti creava «Produzione Ceraldi» con le sue sezioni di
    reparto anche per ricette non pubbliche.

    Il filtro sta **in lettura** e non in scrittura perche' e' l'unico punto
    che copre anche le categorie gia' vuote oggi in produzione (comprese
    quelle create a mano nell'admin) e perche' ``menu_products.subcategory_id`` e'
    NOT NULL: una riga di Lotti la sua sottocategoria deve comunque averla,
    anche quando resta nascosta. Una categoria con prodotti in una sola delle
    sue sottocategorie resta visibile: si tolgono solo le sezioni vuote."""
    piene = _sottocategorie_con_prodotti(subcategories, products)
    for category in categories:
        category['subcategories'] = [s for s in piene if s.get('category_id') == category.get('id')]
    return [c for c in categories if c['subcategories']]


# ================== PUBLIC ENDPOINTS ==================

@router.get("/", response_model=MenuResponse)
async def get_full_menu():
    """Get the complete menu with categories, subcategories, and products"""
    try:
        categories, subcategories, products = await _fetch_all()
        categories = _build_hierarchy(categories, subcategories, products)
        allergens = [allergen_out(r) for r in supabase.table("menu_allergens").select("*").order("id").execute().data]

        return {
            "categories": categories,
            "allergens": allergens
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# Dati del titolare per l'informativa privacy del menu clienti. Una sola fonte:
# l'anagrafica azienda che si modifica in Lotti > Impostazioni
# (`app/lotti/azienda.py`). Solo i campi che un'informativa deve mostrare.
CAMPI_TITOLARE = ("ragione_sociale", "indirizzo", "partita_iva", "email", "telefono")


@router.get("/titolare")
async def titolare_del_trattamento():
    from app.lotti.azienda import get_azienda

    azienda = await get_azienda()
    return {campo: (azienda.get(campo) or "") for campo in CAMPI_TITOLARE}


@router.get("/categories", response_model=List[Category])
async def get_categories():
    """Get all categories with their subcategories and products"""
    try:
        categories, subcategories, products = await _fetch_all()
        return _build_hierarchy(categories, subcategories, products)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/categories/{category_id}")
async def get_category(category_id: int):
    """Get a specific category with its subcategories and products"""
    res = supabase.table("menu_categories").select("*").eq("id", category_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Category not found")
    category = cat_out(res.data[0])

    subcategories = [subcat_out(r) for r in supabase.table("menu_subcategories").select("*").eq("category_id", category_id).order("id").execute().data]
    products = _prodotti_pubblici(supabase.table("menu_products").select("*").eq("category_id", category_id).order("id").execute().data)

    # Come nel menu completo: le sezioni senza prodotti visibili non si mostrano.
    category['subcategories'] = _sottocategorie_con_prodotti(subcategories, products)
    return category


@router.get("/subcategories/{subcategory_id}")
async def get_subcategory(subcategory_id: int):
    """Get a specific subcategory with its products"""
    res = supabase.table("menu_subcategories").select("*").eq("id", subcategory_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Subcategory not found")
    subcategory = subcat_out(res.data[0])

    products = _prodotti_pubblici(supabase.table("menu_products").select("*").eq("subcategory_id", subcategory_id).order("id").execute().data)

    subcategory['items'] = products
    return subcategory


@router.get("/products/{product_id}")
async def get_product(product_id: int):
    """Get a specific product"""
    res = supabase.table("menu_products").select("*").eq("id", product_id).limit(1).execute()
    righe = res.data
    if not righe or not _pubblicabile(righe[0]):
        raise HTTPException(status_code=404, detail="Product not found")
    return prod_out(righe[0])


@router.get("/allergens", response_model=List[Allergen])
async def get_allergens():
    """Get all allergens"""
    rows = supabase.table("menu_allergens").select("*").order("id").execute().data
    return [allergen_out(r) for r in rows]


@router.get("/search")
async def search_products(q: str, limit: int = 20):
    """Search products by name"""
    if not q or len(q) < 2:
        raise HTTPException(status_code=400, detail="Query must be at least 2 characters")

    # Ricerca case-insensitive su name e name_it
    res = (
        supabase.table("menu_products")
        .select("*")
        .or_(f"name.ilike.%{q}%,name_it.ilike.%{q}%")
        .limit(limit)
        .execute()
    )
    products = _prodotti_pubblici(res.data)
    return {"results": products, "count": len(products)}


# ================== ADMIN ENDPOINTS (Protected) ==================
# Import JWT verification
from app.menu.routes.qrcode_routes import verify_token
from fastapi import Depends


# --- Categories CRUD ---
@router.post("/admin/categories")
async def create_category(category: CategoryCreate, username: str = Depends(verify_token)):
    """Create a new category"""
    new_id = _crea_riga("menu_categories", cat_in(category.model_dump()))
    return {"success": True, "id": new_id, "message": "Category created"}


@router.put("/admin/categories/{category_id}")
async def update_category(category_id: int, category: CategoryUpdate, username: str = Depends(verify_token)):
    """Update a category"""
    data = {k: v for k, v in category.model_dump().items() if v is not None}
    if not data:
        raise HTTPException(status_code=400, detail="No data to update")

    update_data = {}
    if "name" in data:
        update_data["name"] = data["name"]
    if "nameIT" in data:
        update_data["name_it"] = data["nameIT"]
    if "image" in data:
        update_data["image"] = data["image"]

    result = supabase.table("menu_categories").update(update_data).eq("id", category_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Category not found")

    return {"success": True, "message": "Category updated"}


@router.delete("/admin/categories/{category_id}")
async def delete_category(category_id: int, username: str = Depends(verify_token)):
    """Delete a category and all its subcategories and products"""
    # I prodotti e le sottocategorie vengono cancellati in automatico (ON DELETE CASCADE)
    result = supabase.table("menu_categories").delete().eq("id", category_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Category not found")

    return {"success": True, "message": "Category and all related data deleted"}


# --- Subcategories CRUD ---
@router.post("/admin/subcategories")
async def create_subcategory(subcategory: SubcategoryCreate, username: str = Depends(verify_token)):
    """Create a new subcategory"""
    category = supabase.table("menu_categories").select("id").eq("id", subcategory.category_id).limit(1).execute()
    if not category.data:
        raise HTTPException(status_code=404, detail="Category not found")

    new_id = _crea_riga("menu_subcategories", subcat_in(subcategory.model_dump()))
    return {"success": True, "id": new_id, "message": "Subcategory created"}


@router.put("/admin/subcategories/{subcategory_id}")
async def update_subcategory(subcategory_id: int, subcategory: SubcategoryUpdate, username: str = Depends(verify_token)):
    """Update a subcategory"""
    data = {k: v for k, v in subcategory.model_dump().items() if v is not None}
    if not data:
        raise HTTPException(status_code=400, detail="No data to update")

    update_data = {}
    if "name" in data:
        update_data["name"] = data["name"]
    if "nameIT" in data:
        update_data["name_it"] = data["nameIT"]
    if "image" in data:
        update_data["image"] = data["image"]

    result = supabase.table("menu_subcategories").update(update_data).eq("id", subcategory_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Subcategory not found")

    return {"success": True, "message": "Subcategory updated"}


@router.delete("/admin/subcategories/{subcategory_id}")
async def delete_subcategory(subcategory_id: int, username: str = Depends(verify_token)):
    """Delete a subcategory and all its products"""
    # I prodotti vengono cancellati in automatico (ON DELETE CASCADE)
    result = supabase.table("menu_subcategories").delete().eq("id", subcategory_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Subcategory not found")

    return {"success": True, "message": "Subcategory and all products deleted"}


# --- Products CRUD ---
@router.post("/admin/products")
async def create_product(product: ProductCreate, username: str = Depends(verify_token)):
    """Create a new product"""
    subcategory = supabase.table("menu_subcategories").select("id").eq("id", product.subcategory_id).limit(1).execute()
    if not subcategory.data:
        raise HTTPException(status_code=404, detail="Subcategory not found")

    new_id = _crea_riga("menu_products", prod_in(product.model_dump()))
    return {"success": True, "id": new_id, "message": "Product created"}


ORIGINE_LOTTI = "lotti"

MESSAGGIO_RIGA_DI_LOTTI = (
    "Questo prodotto e' della ricetta di Lotti e si modifica solo in Lotti "
    "(Ricette): nome, descrizione, prezzo al tavolo, allergeni, foto, "
    "categoria e «inserisci in menu». Una modifica fatta qui verrebbe "
    "sovrascritta al primo salvataggio della ricetta o alla prossima "
    "ripubblicazione in massa."
)


async def _verifica_prodotto_modificabile(product_id: int):
    """Lo stesso proprietario vale per modifica e cancellazione."""
    esistente = supabase.table("menu_products").select("id,origine").eq("id", product_id).limit(1).execute()
    if not esistente.data:
        raise HTTPException(status_code=404, detail="Product not found")
    if (esistente.data[0].get("origine") or "") == ORIGINE_LOTTI:
        raise HTTPException(status_code=409, detail=MESSAGGIO_RIGA_DI_LOTTI)


@router.put("/admin/products/{product_id}")
async def update_product(product_id: int, product: ProductUpdate, username: str = Depends(verify_token)):
    """Modifica i prodotti del Menu; quelli delle ricette si gestiscono in Lotti."""
    await _verifica_prodotto_modificabile(product_id)
    data = {k: v for k, v in product.model_dump().items() if v is not None}
    if not data:
        raise HTTPException(status_code=400, detail="No data to update")

    update_data = {}
    field_map = {"name": "name", "nameIT": "name_it", "price": "price", "description": "description",
                 "descriptionIT": "description_it", "allergens": "allergens", "image": "image",
                 "visible": "visible"}
    for api_field, db_field in field_map.items():
        if api_field in data:
            update_data[db_field] = data[api_field]
    if "prezzo_banco" in data:
        # 0 toglie il prezzo al banco; un valore non valido e' un errore, mai un ripiego
        update_data["prezzo_banco"] = prezzo_banco_valido(data["prezzo_banco"]) or None

    result = supabase.table("menu_products").update(update_data).eq("id", product_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Product not found")

    return {"success": True, "message": "Product updated"}


@router.delete("/admin/products/{product_id}")
async def delete_product(product_id: int, username: str = Depends(verify_token)):
    """Delete a product"""
    await _verifica_prodotto_modificabile(product_id)
    result = supabase.table("menu_products").delete().eq("id", product_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Product not found")

    return {"success": True, "message": "Product deleted"}


@router.put("/admin/products/{product_id}/visibilita")
async def imposta_visibilita_prodotto(product_id: int, body: ProductVisibility, username: str = Depends(verify_token)):
    """X reversibile: nessun DELETE. Le ricette restano possedute da Lotti."""
    righe = supabase.table("menu_products").select("id,origine,lotti_ref").eq("id", product_id).limit(1).execute().data or []
    if not righe:
        raise HTTPException(404, "Prodotto non trovato")
    riga = righe[0]
    if riga.get("origine") == ORIGINE_LOTTI:
        riferimento = str(riga.get("lotti_ref") or "")
        if not riferimento.startswith("ricetta:") or not riferimento[8:]:
            raise HTTPException(409, "Riferimento alla ricetta non valido: verifica in Lotti")
        from app.lotti.routers.ricette import aggiorna_campo_ricetta
        # verify_token accetta esclusivamente la sessione amministratore derivata dall'ERP.
        esito = await aggiorna_campo_ricetta(riferimento[8:], {"menu_pubblico": body.visible}, {"ruolo": "amministratore"})
        return {"success": True, "visible": body.visible, "menu_sync": esito["menu_sync"]}
    await update_product(product_id, ProductUpdate(visible=body.visible), username)
    return {"success": True, "visible": body.visible}


# --- Bulk operations ---
@router.get("/admin/products/all")
async def get_all_products_flat(username: str = Depends(verify_token)):
    """Get all products in a flat list for admin management"""
    products = [prod_out(r) for r in supabase.table("menu_products").select("*").order("id").execute().data]

    categories = {r['id']: r['name_it'] for r in supabase.table("menu_categories").select("id,name_it").execute().data}
    subcategories = {r['id']: r['name_it'] for r in supabase.table("menu_subcategories").select("id,name_it").execute().data}

    for product in products:
        product['categoryName'] = categories.get(product.get('category_id'), 'N/A')
        product['subcategoryName'] = subcategories.get(product.get('subcategory_id'), 'N/A')

    return {"products": products, "total": len(products)}
