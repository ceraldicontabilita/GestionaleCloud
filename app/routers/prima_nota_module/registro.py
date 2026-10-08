"""Registro di Prima Nota a pagine: ordine, saldo progressivo e filtri.

La pagina Prima Nota chiedeva 10.000 righe per mostrarne 200: ordine a video,
saldo progressivo riga per riga e ricerca si facevano nel browser su tutto
l'anno. Qui la stessa regola si applica sul server, una volta sola, e al
browser arriva solo la pagina richiesta (``skip``/``limit``) con il saldo di
ogni riga gia' calcolato sull'anno intero: i numeri non dipendono da quante
righe sono state caricate.

Regole (le stesse che stavano in ``PrimaNota.jsx``):

- ordine a video: giorni dal piu' recente; dentro la giornata prima il
  corrispettivo, poi le altre entrate, poi l'uscita POS, poi fatture e altre
  uscite, per ultimo il versamento; a parita', ``created_at`` crescente;
- saldo progressivo: si parte dal riporto in fondo al registro e si sale riga
  per riga, sempre su tutto l'elenco dell'anno, mai sulla selezione filtrata;
- in Banca non entrano nel saldo le righe che ``ESCLUSIONI_SALDO_REALE``
  esclude dal saldo reale (credito POS, costo del gestore, attese, righe
  dichiarate senza estratto): restano visibili in elenco;
- i filtri di consultazione (mese, categoria, entrate/uscite, testo, numero,
  data e fornitore della fattura) scelgono le righe da mostrare e non toccano
  saldo, entrate e uscite della testata.
"""
from __future__ import annotations

import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List

from .common import CATEGORIE_ESCLUSE, SOURCES_CREDITO_POS, SOURCES_ESCLUSE

# Valore della tendina «Movimenti storici importati»: categorie che sono un
# anno a quattro cifre, lasciate dai vecchi import.
CATEGORIA_STORICA = "__movimenti_storici__"
_ANNO_QUATTRO_CIFRE = re.compile(r"^\d{4}$")

# Stessa regola del saldo reale (ESCLUSIONI_SALDO_REALE in common.py).
_NATURE_FUORI_SALDO_BANCA = {"credito_pos", "costo"}
_SOURCES_FUORI_SALDO_BANCA = set(SOURCES_ESCLUSE) | set(SOURCES_CREDITO_POS)
_CATEGORIE_FUORI_SALDO = set(CATEGORIE_ESCLUSE)

_CENTESIMO = Decimal("0.01")


def e_categoria_storica(categoria: Any) -> bool:
    return bool(_ANNO_QUATTRO_CIFRE.match(str(categoria or "").strip()))


def conta_nel_saldo(movimento: Dict[str, Any], conto: str) -> bool:
    """Vero se la riga entra nel saldo progressivo del conto."""
    if conto != "banca":
        return True
    return not (
        movimento.get("natura") in _NATURE_FUORI_SALDO_BANCA
        or movimento.get("source") in _SOURCES_FUORI_SALDO_BANCA
        or movimento.get("categoria") in _CATEGORIE_FUORI_SALDO
        or movimento.get("in_attesa_estratto_ufficiale") is True
    )


def _importo(movimento: Dict[str, Any]) -> Decimal:
    valore = movimento.get("importo")
    if valore in (None, ""):
        return Decimal("0")
    try:
        return abs(Decimal(str(valore)))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _con_segno(movimento: Dict[str, Any]) -> Decimal:
    importo = _importo(movimento)
    return importo if movimento.get("tipo") == "entrata" else -importo


def _rango(movimento: Dict[str, Any]) -> int:
    if movimento.get("tipo") == "entrata":
        return 0 if movimento.get("categoria") == "Corrispettivi" else 1
    categoria = movimento.get("categoria")
    if categoria in ("POS Verso Banca", "Corrispettivi POS"):
        return 2
    if categoria == "Versamento Banca":
        return 4
    return 3


def ordina_come_a_video(movimenti: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Ordine del registro a video (sort stabile a tre passate)."""
    lista = sorted(movimenti, key=lambda m: str(m.get("created_at") or ""))
    lista.sort(key=_rango)
    lista.sort(key=lambda m: str(m.get("data") or ""), reverse=True)
    return lista


def numero_fattura(movimento: Dict[str, Any]) -> str:
    return str(
        movimento.get("numero_fattura") or movimento.get("fattura_numero")
        or movimento.get("invoice_number") or ""
    )


def nome_fornitore(movimento: Dict[str, Any]) -> str:
    esplicito = (
        movimento.get("fornitore") or movimento.get("ragione_sociale")
        or movimento.get("supplier_name") or movimento.get("cedente_denominazione")
    )
    if esplicito:
        return str(esplicito)
    numero = numero_fattura(movimento)
    testo = f"{movimento.get('categoria') or ''} {movimento.get('descrizione') or ''}"
    sembra_fattura = (
        movimento.get("fattura_id") or numero
        or re.search(r"fattur|nota credito", testo, re.IGNORECASE)
    )
    if not sembra_fattura:
        return ""
    # Righe storiche: "Pagamento fattura N. - Ragione sociale".
    descrizione = str(movimento.get("descrizione") or "")
    separatore = descrizione.find(" - ")
    return descrizione[separatore + 3:].strip() if separatore >= 0 else ""


def data_documento(movimento: Dict[str, Any]) -> str:
    return str(
        movimento.get("data_fattura") or movimento.get("fattura_data")
        or movimento.get("invoice_date") or movimento.get("data") or ""
    )


def _testo(valore: Any) -> str:
    """Il valore come lo scriveva il browser (``String(x)``), in minuscolo."""
    if valore is None:
        return ""
    if isinstance(valore, bool):
        return "true" if valore else "false"
    if isinstance(valore, float) and valore.is_integer():
        return str(int(valore))
    return str(valore).strip().lower()


def filtri_attivi(filtri: Dict[str, Any]) -> bool:
    return any(v not in (None, "") for v in filtri.values())


def filtri_fattura_attivi(filtri: Dict[str, Any]) -> bool:
    """I filtri che leggono numero, data e fornitore dalla fattura collegata."""
    return any(filtri.get(k) for k in ("numero_fattura", "fornitore", "data_fattura"))


def filtra(movimenti: List[Dict[str, Any]], filtri: Dict[str, Any]) -> List[Dict[str, Any]]:
    mese = filtri.get("mese")
    categoria = filtri.get("categoria") or ""
    tipo = filtri.get("tipo") or ""
    numero = _testo(filtri.get("numero_fattura"))
    fornitore = _testo(filtri.get("fornitore"))
    data = str(filtri.get("data_fattura") or "").strip()
    generico = _testo(filtri.get("cerca"))

    def passa(m: Dict[str, Any]) -> bool:
        if mese:
            try:
                if int(str(m.get("data") or "")[5:7]) != int(mese):
                    return False
            except ValueError:
                return False
        if categoria == CATEGORIA_STORICA:
            if not e_categoria_storica(m.get("categoria")):
                return False
        elif categoria and m.get("categoria") != categoria:
            return False
        if tipo and m.get("tipo") != tipo:
            return False
        if numero and numero not in _testo(numero_fattura(m)):
            return False
        if fornitore and fornitore not in _testo(nome_fornitore(m)):
            return False
        if data and data_documento(m) != data:
            return False
        if generico:
            campi = (
                m.get("descrizione"),
                m.get("numero_assegno") or m.get("assegno_numero"),
                m.get("importo"),
                m.get("id"),
                m.get("estratto_conto_id"),
                m.get("movimento_estratto_conto_id"),
            )
            if not any(generico in _testo(c) for c in campi):
                return False
        return True

    return [m for m in movimenti if passa(m)]


def categorie_usate(movimenti: List[Dict[str, Any]]) -> List[str]:
    categorie = {m.get("categoria") for m in movimenti if m.get("categoria")}
    storiche = any(e_categoria_storica(c) for c in categorie)
    correnti = sorted(c for c in categorie if not e_categoria_storica(c))
    return correnti + [CATEGORIA_STORICA] if storiche else correnti


def impagina_registro(
    movimenti: List[Dict[str, Any]], *, riporto: Any, conto: str,
    filtri: Dict[str, Any], skip: int, limit: int,
) -> Dict[str, Any]:
    """Ordina tutto l'elenco, calcola il saldo di ogni riga e ne rende una pagina.

    Ogni riga della pagina porta ``saldo_progressivo`` (sull'elenco intero) e
    ``netto_giorno`` (entrate − uscite della sua giornata fra le righe che
    passano i filtri e contano nel saldo) con ``operazioni_giorno``: numeri che il browser non puo'
    piu' calcolare, perche' non ha tutte le righe.
    """
    ordinati = ordina_come_a_video(movimenti)
    saldo = Decimal(str(riporto or 0))
    saldi: Dict[int, Decimal] = {}
    for m in reversed(ordinati):
        if conta_nel_saldo(m, conto):
            saldo += _con_segno(m)
        saldi[id(m)] = saldo

    scelti = filtra(ordinati, filtri) if filtri_attivi(filtri) else ordinati
    netti: Dict[str, Decimal] = defaultdict(Decimal)
    operazioni: Dict[str, int] = defaultdict(int)
    for m in scelti:
        operazioni[str(m.get("data") or "")] += 1
        if conta_nel_saldo(m, conto):
            netti[str(m.get("data") or "")] += _con_segno(m)

    pagina = []
    for m in scelti[skip:skip + limit]:
        riga = dict(m)
        riga["saldo_progressivo"] = float(saldi[id(m)].quantize(_CENTESIMO))
        riga["netto_giorno"] = float(netti[str(m.get("data") or "")].quantize(_CENTESIMO))
        riga["operazioni_giorno"] = operazioni[str(m.get("data") or "")]
        riga["conta_nel_saldo"] = conta_nel_saldo(m, conto)
        pagina.append(riga)
    return {
        "movimenti": pagina,
        "totale": len(scelti),
        "skip": skip,
        "limit": limit,
        "categorie": categorie_usate(movimenti),
    }
