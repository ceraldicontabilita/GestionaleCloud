"""P0.9 — registra_pagamento è idempotente: due submit identici producono la
stessa chiave e non devono creare due movimenti Prima Nota."""
from app.routers.multi_pagamento import chiave_idempotenza_pagamento


def test_stessi_dati_stessa_chiave():
    k1 = chiave_idempotenza_pagamento("F1", 500.0, "2026-04-11", "contanti")
    k2 = chiave_idempotenza_pagamento("F1", 500.00, "2026-04-11", "contanti")
    assert k1 == k2
    assert k1.startswith("pag_")


def test_dati_diversi_chiavi_diverse():
    base = chiave_idempotenza_pagamento("F1", 500.0, "2026-04-11", "contanti")
    assert chiave_idempotenza_pagamento("F1", 500.0, "2026-04-11", "bonifico") != base
    assert chiave_idempotenza_pagamento("F1", 250.0, "2026-04-11", "contanti") != base
    assert chiave_idempotenza_pagamento("F2", 500.0, "2026-04-11", "contanti") != base
    assert chiave_idempotenza_pagamento("F1", 500.0, "2026-04-12", "contanti") != base


def test_chiave_esplicita_del_client_ha_priorita():
    k = chiave_idempotenza_pagamento("F1", 500.0, "2026-04-11", "contanti", esplicita="req-123")
    assert k == "req-123"
