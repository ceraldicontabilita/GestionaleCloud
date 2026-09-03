from fastapi import APIRouter, HTTPException
from typing import List, Optional

from app.menu.supabase_client import supabase
from app.menu.models.menu_models import (
    Category, CategoryCreate, CategoryUpdate,
    Subcategory, SubcategoryCreate, SubcategoryUpdate,
    Product, ProductCreate, ProductUpdate,
    Allergen, MenuResponse
)

router = APIRouter(prefix="/api/menu", tags=["Menu"])


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


def prod_out(row: dict) -> dict:
    return {
        "id": row["id"], "category_id": row["category_id"], "subcategory_id": row["subcategory_id"],
        "name": row["name"], "nameIT": row["name_it"], "price": row["price"],
        "description": row.get("description"), "descriptionIT": row.get("description_it"),
        "allergens": row.get("allergens") or [], "image": row.get("image"),
    }


def prod_in(data: dict) -> dict:
    out = {
        "name": data["name"], "name_it": data["nameIT"], "price": data["price"],
        "description": data.get("description"), "description_it": data.get("descriptionIT"),
        "allergens": data.get("allergens") if data.get("allergens") is not None else [],
        "image": data.get("image"),
    }
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


def _fetch_all():
    categories = [cat_out(r) for r in supabase.table("menu_categories").select("*").order("id").execute().data]
    subcategories = [subcat_out(r) for r in supabase.table("menu_subcategories").select("*").order("id").execute().data]
    products = [prod_out(r) for r in supabase.table("menu_products").select("*").order("id").execute().data]
    return categories, subcategories, products


def _build_hierarchy(categories, subcategories, products):
    for subcategory in subcategories:
        subcategory['items'] = [p for p in products if p.get('subcategory_id') == subcategory.get('id')]
    for category in categories:
        category['subcategories'] = [s for s in subcategories if s.get('category_id') == category.get('id')]
    return categories


# ================== PUBLIC ENDPOINTS ==================

@router.get("/", response_model=MenuResponse)
async def get_full_menu():
    """Get the complete menu with categories, subcategories, and products"""
    try:
        categories, subcategories, products = _fetch_all()
        categories = _build_hierarchy(categories, subcategories, products)
        allergens = [allergen_out(r) for r in supabase.table("menu_allergens").select("*").order("id").execute().data]

        return {
            "categories": categories,
            "allergens": allergens
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/categories", response_model=List[Category])
async def get_categories():
    """Get all categories with their subcategories and products"""
    try:
        categories, subcategories, products = _fetch_all()
        return _build_hierarchy(categories, subcategories, products)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/categories/{category_id}")
async def get_category(category_id: int):
    """Get a specific category with its subcategories and products"""
    res = supabase.table("menu_categories").select("*").eq("id", category_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Category not found")
    category = cat_out(res.data[0])

    subcategories = [subcat_out(r) for r in supabase.table("menu_subcategories").select("*").eq("category_id", category_id).order("id").execute().data]
    products = [prod_out(r) for r in supabase.table("menu_products").select("*").eq("category_id", category_id).order("id").execute().data]

    for subcategory in subcategories:
        subcategory['items'] = [p for p in products if p.get('subcategory_id') == subcategory.get('id')]

    category['subcategories'] = subcategories
    return category


@router.get("/subcategories/{subcategory_id}")
async def get_subcategory(subcategory_id: int):
    """Get a specific subcategory with its products"""
    res = supabase.table("menu_subcategories").select("*").eq("id", subcategory_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Subcategory not found")
    subcategory = subcat_out(res.data[0])

    products = [prod_out(r) for r in supabase.table("menu_products").select("*").eq("subcategory_id", subcategory_id).order("id").execute().data]

    subcategory['items'] = products
    return subcategory


@router.get("/products/{product_id}")
async def get_product(product_id: int):
    """Get a specific product"""
    res = supabase.table("menu_products").select("*").eq("id", product_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Product not found")
    return prod_out(res.data[0])


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
    products = [prod_out(r) for r in res.data]
    return {"results": products, "count": len(products)}


# ================== ADMIN ENDPOINTS (Protected) ==================
# Import JWT verification
from app.menu.routes.qrcode_routes import verify_token
from fastapi import Depends


# --- Categories CRUD ---
@router.post("/admin/categories")
async def create_category(category: CategoryCreate, username: str = Depends(verify_token)):
    """Create a new category"""
    last = supabase.table("menu_categories").select("id").order("id", desc=True).limit(1).execute()
    new_id = (last.data[0]['id'] + 1) if last.data else 1

    row = cat_in(category.model_dump())
    row['id'] = new_id

    supabase.table("menu_categories").insert(row).execute()
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

    last = supabase.table("menu_subcategories").select("id").order("id", desc=True).limit(1).execute()
    new_id = (last.data[0]['id'] + 1) if last.data else 10

    row = subcat_in(subcategory.model_dump())
    row['id'] = new_id

    supabase.table("menu_subcategories").insert(row).execute()
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

    last = supabase.table("menu_products").select("id").order("id", desc=True).limit(1).execute()
    new_id = (last.data[0]['id'] + 1) if last.data else 100

    row = prod_in(product.model_dump())
    row['id'] = new_id

    supabase.table("menu_products").insert(row).execute()
    return {"success": True, "id": new_id, "message": "Product created"}


@router.put("/admin/products/{product_id}")
async def update_product(product_id: int, product: ProductUpdate, username: str = Depends(verify_token)):
    """Update a product"""
    data = {k: v for k, v in product.model_dump().items() if v is not None}
    if not data:
        raise HTTPException(status_code=400, detail="No data to update")

    update_data = {}
    field_map = {"name": "name", "nameIT": "name_it", "price": "price", "description": "description",
                 "descriptionIT": "description_it", "allergens": "allergens", "image": "image"}
    for api_field, db_field in field_map.items():
        if api_field in data:
            update_data[db_field] = data[api_field]

    result = supabase.table("menu_products").update(update_data).eq("id", product_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Product not found")

    return {"success": True, "message": "Product updated"}


@router.delete("/admin/products/{product_id}")
async def delete_product(product_id: int, username: str = Depends(verify_token)):
    """Delete a product"""
    result = supabase.table("menu_products").delete().eq("id", product_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Product not found")

    return {"success": True, "message": "Product deleted"}


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
