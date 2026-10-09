"""Identità documentale e rapporti distinti nello stesso mese, senza importi dedotti."""
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
import hashlib
import re


CAMPI_RAPPORTO = ("rapporto_id", "rapporto_lavoro", "impronta_contenuto")


def rapporto_da_coordinate(words):
    """Legge solo le celle sotto etichette esplicite della testata Zucchetti."""
    labels = {"CODICEDIPENDENTE": "codice_dipendente", "DATAASSUNZIONE": "data_assunzione",
              "DATACESSAZIONE": "data_cessazione"}
    labels = {k.replace("S", ""): v for k, v in labels.items()}
    rapporto = {}
    for label in words:
        name = re.sub(r"\s+", "", str(label[4]).upper().replace("S", ""))
        campo = labels.get(name)
        if not campo:
            continue
        candidates = [w for w in words if label[1] + 5 < w[1] < label[3] + 16
                      and label[0] - 3 <= w[0] <= label[0] + 12]
        for w in sorted(candidates, key=lambda v: v[1]):
            value = str(w[4])
            if campo == "codice_dipendente" and re.fullmatch(r"\d{1,10}", value):
                rapporto[campo] = value
                break
            if campo != "codice_dipendente" and re.fullmatch(r"\d{2}[-/]\d{2}[-/]\d{4}", value):
                try:
                    rapporto[campo] = datetime.strptime(value.replace("/", "-"), "%d-%m-%Y").date().isoformat()
                    break
                except ValueError:
                    pass
    # La descrizione è solo un'etichetta; non decide l'identità del rapporto.
    header = " ".join(str(w[4]) for w in words if w[1] < 0.35 * max((v[3] for v in words), default=0))
    if re.search(r"Tir\./Stag\.", header, re.I):
        rapporto["descrizione"] = "Tirocinio"
    elif "Appr." in header:
        rapporto["descrizione"] = "Apprendistato"
    identity = ":".join(str(rapporto.get(k) or "") for k in ("codice_dipendente", "data_assunzione"))
    return {"rapporto_id": identity, "rapporto_lavoro": rapporto} if identity.strip(":") else {}


def impronta_testo(text):
    """Stessa pagina estratta da un fascicolo o caricata da sola = stessa prova."""
    normalized = re.sub(r"\s+", " ", text).strip()
    return hashlib.sha256(normalized.encode()).hexdigest() if normalized else None


def stessa_busta(a, b):
    """Copia certa o stessa versione documentata; mai soltanto stesso mese/netto."""
    if a.get("rapporto_id") and b.get("rapporto_id") and a["rapporto_id"] != b["rapporto_id"]:
        return False
    for field in ("impronta_contenuto", "cedolino_dedup_key", "gestionale_cedolino_id"):
        if a.get(field) and a[field] == b.get(field):
            return True
    # Fonte originale e pagine identiche, anche per i documenti storici.
    return bool(a.get("source_file_hash") and a["source_file_hash"] == b.get("source_file_hash")
                and a.get("source_page_start") is not None
                and a.get("source_page_end") is not None
                and all(a.get(k) == b.get(k) for k in ("source_page_start", "source_page_end")))


def mese_registro(c):
    return {"tredicesima": 13, "quattordicesima": 14}.get(
        str(c.get("tipo_cedolino") or "").lower(), int(c.get("mese") or 0))


def raggruppa_cedolini(cedolini):
    """Vista mensile; conserva ogni originale, esclude copie certe e sostituiti."""
    gruppi = defaultdict(list)
    for c in cedolini:
        if c.get("entity_status") == "deleted" or c.get("status") in ("deleted", "archived", "archiviata", "sostituito"):
            continue
        key = (c.get("dipendente_id") or c.get("codice_fiscale") or "__unico__", int(c.get("anno") or 0), mese_registro(c))
        if not key[0] or not key[1] or not key[2]:
            continue
        if not any(stessa_busta(c, old) or (c.get("id") and c["id"] == old.get("id")) for old in gruppi[key]):
            gruppi[key].append(c)
    result = {}
    for key, docs in gruppi.items():
        if len(docs) == 1:
            result[key] = docs[0]
            continue
        docs.sort(key=lambda c: ((c.get("rapporto_lavoro") or {}).get("data_assunzione") or "", str(c.get("id") or "")))
        total = dict(docs[0])
        total["cedolini_componenti"] = docs
        # Nessuna decisione automatica fra revisioni ancora da verificare.
        conflitto = any(c.get("varianti_da_decidere") for c in docs)
        for field in ("netto", "netto_mese", "lordo", "totale_trattenute", "giorni_lavorati", "ore_lavorate"):
            values = [c.get(field, c.get("netto") if field == "netto_mese" else None) for c in docs]
            total[field] = None if conflitto or any(v is None for v in values) else float(sum((Decimal(str(v)) for v in values), Decimal(0)))
        total["varianti_da_decidere"] = conflitto
        # Non ereditare da una singola busta valori usati al posto del totale.
        total.pop("netto_stampato", None)
        total.pop("netto_busta", None)
        result[key] = total
    return result
