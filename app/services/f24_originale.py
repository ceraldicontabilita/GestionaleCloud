"""Originale di un modello o di una quietanza F24: lo stesso lettore dei cedolini.

Era una copia di ``cedolino_originale`` (stessa logica, un messaggio diverso):
un lettore solo (DRV-04). Il parametro ``tipo`` resta per compatibilita' dei
chiamanti e non cambia il comportamento.
"""
from __future__ import annotations

from typing import Any, Dict

from app.services.cedolino_originale import carica_originale as _carica

__all__ = ["carica_originale"]


async def carica_originale(doc: Dict[str, Any], *, tipo: str = "f24") -> bytes:
    return await _carica(doc)
