"""Riferimenti `/api/...` usati dal frontend, risolvendo le costanti prefisso.

Usato da `genera_mappa.py` e `genera_classificazione_endpoint.py` (colonna
FE). Prima veniva cercato solo il testo letterale `/api/...`: un modulo che
compone gli URL da una costante (`const HR_API = "/api" + "/hr"`,
``const API = `${HR_API}/dipendenti-cloud` ``, ``hrApi.get(`${API}/dipendenti`)``)
o da un client axios con `baseURL` (`api.get("/portale/buste")`) risultava
"mai usato dal frontend" pur essendo la parte piu' chiamata dell'app.

La risoluzione e' statica e per singolo file: costanti MAIUSCOLE dichiarate
nel file, concatenazioni di stringhe letterali, template `${COSTANTE}` e il
`baseURL` di un client axios dichiarato nel file. Restituisce stringhe grezze
(con eventuali `${...}` non risolti): la normalizzazione a `:x` resta ai
chiamanti, come prima.
"""
from __future__ import annotations

import os
import re
from typing import Dict, Set

_CONST = re.compile(r"const\s+([A-Z][A-Z0-9_]*)\s*=\s*([\"'`][^;\n]*[\"'`])\s*;")
_CONCAT = re.compile(r"[\"'`]\s*\+\s*[\"'`]")
_TEMPLATE_VAR = re.compile(r"\$\{([A-Z][A-Z0-9_]*)\}")
_BASEURL = re.compile(r"baseURL:\s*([^,}\n]+)")
_API_CALL = re.compile(r"\b(?:api|hrApi)\.(?:get|post|put|delete|patch|request)\(\s*([\"'`])(/[^\"'`]*)\1")
_API_REF = re.compile(r"/api/[a-zA-Z0-9_\-/${}.]+")


def _resolve(value: str, consts: Dict[str, str], depth: int = 0) -> str:
    value = _CONCAT.sub("", value.strip()).strip("`\"' ")
    if depth > 5:
        return value
    return _TEMPLATE_VAR.sub(
        lambda m: _resolve(consts.get(m.group(1), m.group(0)), consts, depth + 1) if m.group(1) in consts else m.group(0),
        value,
    )


def file_api_refs(text: str) -> Set[str]:
    consts = {name: raw for name, raw in _CONST.findall(text)}
    resolved = {name: _resolve(raw, consts) for name, raw in consts.items()}
    expanded = text
    for name, value in resolved.items():
        if value.startswith("/api/"):
            expanded = expanded.replace("${" + name + "}", value)
    refs = set(_API_REF.findall(expanded))

    base = _BASEURL.search(text)
    if base:
        base_url = _resolve(base.group(1), consts)
        if base_url.startswith("/api/"):
            for _quote, path in _API_CALL.findall(text):
                if not path.startswith("/api/"):
                    refs.add(base_url.rstrip("/") + path)
    return refs


def frontend_api_refs(root: str = "frontend/src") -> Set[str]:
    refs: Set[str] = set()
    for folder, _dirs, files in os.walk(root):
        for name in files:
            if name.endswith((".js", ".jsx", ".ts", ".tsx")):
                with open(os.path.join(folder, name), encoding="utf-8", errors="ignore") as handle:
                    refs |= file_api_refs(handle.read())
    return refs
