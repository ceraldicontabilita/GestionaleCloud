from pathlib import Path

from app.routers.prima_nota_module import router as prima_nota_router
from app.routers.scadenze import router as scadenze_router


ROOT = Path(__file__).resolve().parents[1]


def test_endpoint_importazione_ec_in_prima_nota_non_esiste_piu():
    paths = {route.path for route in prima_nota_router.routes}
    assert "/importa-da-ec" not in paths


def test_pagina_movimenti_banca_e_consultiva():
    source = (ROOT / "frontend/src/pages/VerificaMovimentiBanca.jsx").read_text(encoding="utf-8")
    assert "Importa in Prima Nota" not in source
    assert "importa-da-ec" not in source
    assert "sola lettura" in source.lower()


def test_scadenze_non_espone_calcolo_iva_trimestrale():
    assert not any(route.path == "/iva/{anno}" for route in scadenze_router.routes)
    source = (ROOT / "frontend/src/pages/Scadenze.jsx").read_text(encoding="utf-8")
    assert "Trimestrale" not in source
