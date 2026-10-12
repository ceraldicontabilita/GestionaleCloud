"""Preferiti acquisti: proiezione delle fatture, senza copie né modifiche al magazzino."""
import hashlib
import re
from decimal import Decimal, InvalidOperation

from app.database import Database
from app.document_repository import metadata_projection
from app.routers.lotti_integration import _attiva


def nome_fornitore(f):
    nome = f.get("supplier_name") or f.get("cedente_denominazione") or f.get("fornitore") or ""
    return str(nome.get("ragione_sociale") or nome.get("denominazione") or "") if isinstance(nome, dict) else str(nome)


def chiave_nome(nome):
    nome = str(nome or "").lower().split("sog. all")[0]
    nome = re.sub(r"\b(s\.?r\.?l\.?s?|s\.?p\.?a\.?|unipersonale)\b\.?", "", nome)
    return re.sub(r"[^a-z0-9]", "", nome)


def piva(f):
    return re.sub(r"^IT", "", re.sub(r"\W", "", str(f.get("supplier_vat") or f.get("cedente_piva") or f.get("fornitore_partita_iva") or "").upper()))


ALIASES = {
    "mepa": ["ME.PA. ALIMENTARI S.R.L.", "MEPA Alimentari"],
    "saima": ["SAIMA S.p.A."],
    "acquaviva": ["Dolciaria Acquaviva S.p.A.", "Vandemoortele Italia", "Vandemoortele Europe NV (Sede Secondaria Italia)"],
    "vandemoortele": ["Vandemoortele Italia", "Vandemoortele Europe NV (Sede Secondaria Italia)"],
    "alpha": ["PROGETTO ALPHA S.R.L.S"],
    "alfa": ["PROGETTO ALPHA S.R.L.S"],
    "tremarie": ["Tre Marie", "Sammontana Italia", "Sammontana"],
    "tre marie": ["Tre Marie", "Sammontana Italia", "Sammontana"],
    "sammontana": ["Sammontana Italia", "Sammontana"],
    "pasticcere": ["Il Pasticcere"],
    "bindi": ["Bindi", "Bindi Dessert"],
}


async def fatture_catalogo(db_lotti, fonte):
    fonti = await db_lotti.fonti_catalogo_esterne.find({}, {"_id": 0}).to_list(None)
    nomi, pive = set(), set()
    for key in str(fonte).split("|"):
        key = key.strip().lower()
        registro = next((f for f in fonti if f.get("fornitore_key") == key), {})
        if registro.get("partita_iva"):
            pive.add(piva({"supplier_vat": registro["partita_iva"]}))
        else:
            nomi.update(chiave_nome(n) for n in ALIASES.get(key, [registro.get("nome") or key]))
    try:
        erp = Database.get_db()
    except RuntimeError:
        # Installazione Lotti autonoma/test: la sua fonte resta la fattura importata.
        fatture = await db_lotti.fatture.find({}, {"_id": 0}).to_list(None)
    else:
        # Metadati con righe XML, mai il payload PDF/XML per ogni battuta di ricerca.
        fatture = await erp["invoices"].find({}, metadata_projection("invoices")).to_list(None)
    return [f for f in fatture if _attiva(f)
            and str(f.get("tipo_documento") or f.get("document_type") or "").upper() not in {"TD04", "TD08"}
            and (piva(f) in pive or chiave_nome(nome_fornitore(f)) in nomi)]


def numero(valore):
    try:
        n = Decimal(str(valore).replace(",", "."))
        return n if n.is_finite() else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def articoli_acquistati(fatture):
    from app.lotti.routers.utils import _norm, _norm_codice_articolo, parse_data_flessibile
    from datetime import date

    articoli = {}
    for f in fatture:
        data = f.get("invoice_date") or f.get("data_documento") or f.get("data_fattura") or ""
        data_ord = parse_data_flessibile(str(data)) or date.min
        for r in f.get("linee") or f.get("righe") or f.get("prodotti") or f.get("lines") or []:
            nome = str(r.get("descrizione") or r.get("description") or "").strip()
            quantita = numero(r.get("quantita") or r.get("quantity"))
            prezzo = numero(r.get("prezzo_unitario") or r.get("unit_price") or r.get("prezzo") or 0)
            if not nome or prezzo is None or prezzo < 0 or (quantita is not None and quantita <= 0):
                continue
            if re.search(r"\b(trasporto|spese|sconto|abbuono|bollo|contributo conai)\b", nome, re.I):
                continue
            totale = numero(r.get("prezzo_totale") or r.get("line_total"))
            informativa = nome.casefold() == "riga ausiliaria contenente informazioni tecniche e aggiuntive del documento" or any(
                str(d.get("tipo_dato") or "").casefold() == "aswtriga"
                and "#ID#" in str(d.get("riferimento_testo") or "").upper()
                for d in r.get("altri_dati_gestionali") or [] if isinstance(d, dict)
            )
            if informativa and prezzo == 0 and totale in (None, 0):
                # Metadati del documento XML, non un articolo gratuito/omaggio.
                continue
            if quantita and totale is not None:
                if totale < 0:
                    continue
                prezzo = totale / quantita
            codici = [str(r.get("codice_articolo") or "").strip()]
            codici += [str(c.get("valore") or c.get("value") or "").strip() for c in r.get("codici_articolo") or [] if isinstance(c, dict)]
            codici = [c for c in codici if c]
            identita = f"{piva(f) or chiave_nome(nome_fornitore(f))}|{_norm_codice_articolo(codici[0]) if codici else _norm(nome)}"
            precedente = articoli.get(identita)
            if precedente and precedente["_data"] > data_ord:
                continue
            articoli[identita] = {"id": "acquisto_" + hashlib.sha256(identita.encode()).hexdigest()[:24],
                "nome": nome, "codice_articolo": codici[0] if codici else "", "codici_alias": codici,
                "prezzo": float(prezzo), "quantita": float(quantita or 0), "data": str(data), "_data": data_ord,
                "unita_confezione": r.get("unita_misura") or r.get("unit") or "pz",
                "fattura_id": str(f.get("id") or ""), "fornitore_nome": nome_fornitore(f)}
    return list(articoli.values())


def collega_preferiti(articoli, catalogo, fonte):
    """Codice o nome esatto e univoco; le righe non agganciate restano quelle originali."""
    from app.lotti.routers.utils import _norm, _norm_codice_articolo
    risultato = {}
    codici, nomi = {}, {}
    for p in catalogo:
        for c in [p.get(k) for k in ("codice_articolo", "codice", "codice_aqv_2025", "codice_aqv_2026")] + (p.get("codici_alias") or []):
            if _norm_codice_articolo(c):
                codici.setdefault(_norm_codice_articolo(c), []).append(p)
        for n in [p.get("nome"), p.get("nome_completo")] + (p.get("alias_fattura") or []):
            if n:
                nomi.setdefault(_norm(n), []).append(p)
    for a in sorted(articoli, key=lambda a: a["_data"]):
        candidati = []
        for codice in a["codici_alias"]:
            candidati += codici.get(_norm_codice_articolo(codice), [])
        if not candidati:
            candidati = nomi.get(_norm(a["nome"]), [])
        unici = {str(p.get("id") or p.get("codice_articolo") or p.get("nome")): p for p in candidati}
        p = dict(next(iter(unici.values()))) if len(unici) == 1 else {}
        p.setdefault("id", a["id"])
        p.setdefault("nome", a["nome"])
        p.setdefault("codice_articolo", a["codice_articolo"])
        p.setdefault("unita_confezione", a["unita_confezione"])
        p.update({"fonte": fonte, "fornitore": fonte, "gia_acquistato": True, "preferito_acquisti": True,
                  "prezzo_fattura": a["prezzo"], "prezzo_fattura_data": a["data"],
                  "quantita_ultima_fattura": a["quantita"], "fattura_id": a["fattura_id"],
                  "da_fattura_senza_catalogo": not bool(unici) or len(unici) != 1})
        risultato[p["id"]] = p
    return sorted(risultato.values(), key=lambda p: p["nome"].casefold())
