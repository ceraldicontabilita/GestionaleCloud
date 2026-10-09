"""Nessun endpoint del Menu risponde «success» senza salvare.

PUT /api/admin/products/{id} e POST /api/admin/associate-image rispondevano
successo senza toccare il database; GET /api/admin/products era pubblico e
vuoto. Nessuna pagina li chiamava: sono stati tolti.
"""
from fastapi.routing import APIRoute

from app.menu.routes.admin_routes import router


def test_endpoint_finti_rimossi():
    percorsi = {(r.path, m) for r in router.routes if isinstance(r, APIRoute) for m in r.methods}
    assert ("/api/admin/products", "GET") not in percorsi
    assert ("/api/admin/products/{product_id}", "PUT") not in percorsi
    assert ("/api/admin/associate-image", "POST") not in percorsi
    assert ("/api/admin/upload-image", "POST") in percorsi
