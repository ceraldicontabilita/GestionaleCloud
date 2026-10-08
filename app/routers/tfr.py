"""Proiezione ERP del TFR canonico HR, senza una seconda anagrafica o motore."""
from fastapi import APIRouter

from app.hr.routers.tfr import (
    RIVALUTAZIONE_FISSA, TFR_DIVISORE,
    _estrai_acconto_da_cedolino, get_situazione_tfr, get_riepilogo_tfr_aziendale,
)

__all__ = [
    "router", "RIVALUTAZIONE_FISSA", "TFR_DIVISORE",
    "_estrai_acconto_da_cedolino", "get_situazione_tfr", "get_riepilogo_tfr_aziendale",
]

router = APIRouter()
router.add_api_route("/situazione/{dipendente_id}", get_situazione_tfr, methods=["GET"])
router.add_api_route("/riepilogo-aziendale", get_riepilogo_tfr_aziendale, methods=["GET"])
