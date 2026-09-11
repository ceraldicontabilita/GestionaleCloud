"""Riferimenti `/api/...` usati dal frontend, risolvendo le costanti prefisso.

Usato da `genera_mappa.py` e `genera_classificazione_endpoint.py` (colonna
FE). Risolve costanti locali, concatenazioni semplici, template e baseURL axios.
Gli slot dinamici `${...}` vengono preservati interi per permettere ai chiamanti
di normalizzarli come parametri senza produrre falsi endpoint troncati.
I file di test non vengono censiti come chiamanti reali dell'applicazione.
"""
from __future__ import annotations

import os
import re
from typing import Dict, Set

_CONST = re.compile(r"const\s+([A-Z][A-Z0-9_]*)\s*=\s*([\"'`][^;\n]*[\"'`])\s*;")
_CONCAT = re.compile(r"[\"'`]\s*\+\s*[\"'`]")
_TEMPLATE_VAR = re.compile(r"\$\{([A-Z][A-Z0-9_]*)\}")
_BASEURL = re.compile(r"baseURL:\s*([^,}\n]+)")
_API_CALL = re.compile(r"\bapi\.(?:get|post|put|delete|patch|request)\(\s*([\"'`])(/[^\"'`]*)\1")
_API_REF = re.compile(r"/api/(?:[A-Za-z0-9_.\-/]+|\$\{[^}\n]+\})+")
_TEST_FILE = re.compile(r"(?:^|\.)(?:test|spec)\.(?:js|jsx|ts|tsx)$", re.IGNORECASE)


def _resolve(value: str, consts: Dict[str, str], depth: int = 0) -> str:
    value = _CONCAT.sub("", value.strip()).strip("`\"' ")
    if depth > 5:
        return value
    return _TEMPLATE_VAR.sub(
        lambda m: _resolve(consts.get(m.group(1), m.group(0)), consts, depth + 1)
        if m.group(1) in consts
        else m.group(0),
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


def _is_runtime_source(name: str, folder: str) -> bool:
    if not name.endswith((".js", ".jsx", ".ts", ".tsx")):
        return False
    if _TEST_FILE.search(name):
        return False
    parts = {part.lower() for part in os.path.normpath(folder).split(os.sep)}
    if "__tests__" in parts or "tests" in parts:
        return False
    return True


def frontend_api_refs(root: str = "frontend/src") -> Set[str]:
    refs: Set[str] = set()
    for folder, _dirs, files in os.walk(root):
        for name in files:
            if not _is_runtime_source(name, folder):
                continue
            with open(os.path.join(folder, name), encoding="utf-8", errors="ignore") as handle:
                refs |= file_api_refs(handle.read())
    return refs
