"""Fatture ERP del prodotto: sola lettura, identità fornitore/articolo esplicita."""
from app.database import Database
from app.document_repository import metadata_projection
from app.routers.fatture_module.crud import _piva_senza_prefisso
from app.routers.lotti_integration import _attiva, _invoice_date, _year


def _codice(value):
    # Gli zeri iniziali possono distinguere articoli: niente fuzzy matching.
    return str(value or "").strip().upper()


async def fatture_acquisto(ricetta: dict, anno: int) -> dict:
    partita_iva = _piva_senza_prefisso(ricetta.get("fornitore_partita_iva"))
    codice = _codice(ricetta.get("codice_articolo_fornitore"))
    result = {"anno": anno, "fatture": [], "collegamento_configurato": bool(partita_iva and codice)}
    if not result["collegamento_configurato"]:
        result["messaggio"] = "Indica P.IVA del fornitore in fattura e codice articolo nella scheda."
        return result
    db = Database.get_db()
    documents = await db["invoices"].find({}, metadata_projection("invoices")).to_list(None)
    for doc in documents:
        if not doc.get("id") or not _attiva(doc) or _year(_invoice_date(doc)) != anno:
            continue
        supplier_vat = doc.get("supplier_vat") or doc.get("fornitore_partita_iva") or doc.get("cedente_piva")
        if _piva_senza_prefisso(supplier_vat) != partita_iva:
            continue
        righe = []
        for row in (doc.get("linee") or doc.get("righe") or doc.get("prodotti") or []):
            if not isinstance(row, dict):
                continue
            codici = row.get("codici_articolo") or []
            valori = {_codice(c.get("valore")) for c in codici if isinstance(c, dict)}
            valori.update(_codice(row.get(k)) for k in ("codice_articolo", "codice"))
            if codice not in valori:
                continue
            righe.append({k: row.get(k) for k in (
                "numero_linea", "descrizione", "quantita", "unita_misura", "prezzo_unitario", "prezzo_totale",
            )})
        if righe:
            result["fatture"].append({
                "id": doc["id"], "data": _invoice_date(doc),
                "numero": doc.get("invoice_number") or doc.get("numero_fattura"),
                "fornitore": doc.get("supplier_name") or doc.get("fornitore_ragione_sociale"),
                "tipo_documento": doc.get("tipo_documento"), "righe": righe,
            })
    result["fatture"].sort(key=lambda f: f["data"], reverse=True)
    return result
