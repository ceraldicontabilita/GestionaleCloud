"""Il metodo di pagamento di ogni fornitore, e la copia che sopravvive.

E' il dato che decide se una fattura finisce in Prima Nota Cassa o Banca.
Senza, la fattura resta `sospesa` e fuori dai saldi: al 20/09/2026 erano
**1.405 fatture su 1.457**, per 188 fornitori nessuno dei quali aveva un
metodo.

Quei metodi erano stati impostati e non si sono ritrovati: non in `fornitori`,
non nell'audit, non nelle proposte di aggiornamento, e nemmeno nell'archivio
legacy, che un campo metodo non ce l'ha proprio. Non c'e' un punto da cui
recuperarli.

Per questo il dato ha due case:
- l'anagrafica `fornitori`, che e' quella che il gestionale legge;
- `app/data/metodi_pagamento_fornitori.json`, che sta in git e sopravvive a
  qualunque cosa succeda al database.

E ogni scrittura lascia una riga in `metodi_pagamento_storico`: chi, quando,
da cosa a cosa. Un dato che sparisce senza traccia e' quello che e' successo
la prima volta.
"""
import json
import logging
import pathlib
import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

FILE_RIFERIMENTO = pathlib.Path(__file__).resolve().parents[1] / "data" / "metodi_pagamento_fornitori.json"

# Gli unici tre valori che il motore di instradamento sa leggere
# (`app/engines/prima_nota_engine.py`). «misto» significa: resta in
# Provvisoria, decide una persona.
METODI_AMMESSI = ("cassa", "banca", "misto")

COLLEZIONE_STORICO = "metodi_pagamento_storico"


def normalizza_nome(nome: str) -> str:
    senza_accenti = unicodedata.normalize("NFKD", str(nome or ""))
    senza_accenti = "".join(c for c in senza_accenti if not unicodedata.combining(c))
    return " ".join(senza_accenti.lower().replace('"', " ").split())


def chiave(fornitore: Dict[str, Any]) -> str:
    """P.IVA quando c'e', altrimenti il nome normalizzato.

    La regola e' quella dell'anagrafica: P.IVA → CF → nome. Su 188 fornitori
    solo 111 hanno una P.IVA, quindi il ripiego sul nome non e' un caso raro
    ed e' l'unica cosa che tiene insieme i restanti 77.
    """
    for campo in ("partita_iva", "piva", "codice_fiscale"):
        valore = str(fornitore.get(campo) or "").strip()
        if valore:
            return valore
    nome = fornitore.get("ragione_sociale") or fornitore.get("nome") or fornitore.get("name") or ""
    return normalizza_nome(nome)


def metodo_valido(metodo: str) -> bool:
    return str(metodo or "").strip().lower() in METODI_AMMESSI


def leggi_file() -> Dict[str, Any]:
    """Il file di riferimento versionato. Assente o rotto → struttura vuota."""
    try:
        return json.loads(FILE_RIFERIMENTO.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.warning("File dei metodi non trovato: %s", FILE_RIFERIMENTO)
    except json.JSONDecodeError as exc:
        logger.error("File dei metodi illeggibile (%s): %s", type(exc).__name__, exc)
    return {"fornitori": []}


async def esporta(db) -> Dict[str, Any]:
    """I metodi come sono adesso nell'anagrafica, nel formato del file."""
    fornitori = await db["fornitori"].find({}, {"_id": 0}).to_list(5000)
    righe = [
        {
            "nome": f.get("ragione_sociale") or f.get("nome") or "",
            "partita_iva": str(f.get("partita_iva") or ""),
            "metodo_pagamento": str(f.get("metodo_pagamento") or "").strip().lower(),
        }
        for f in fornitori
    ]
    righe.sort(key=lambda r: r["nome"].lower())
    modello = leggi_file()
    return {
        **{k: v for k, v in modello.items() if k.startswith("_") or k == "metodi_ammessi"},
        "aggiornato_il": datetime.now(timezone.utc).date().isoformat(),
        "fornitori": righe,
    }


async def mancanti(db) -> List[Dict[str, Any]]:
    """Chi non ha ancora un metodo: l'elenco da compilare.

    Ordinato per numero di fatture: il fornitore da cui arrivano piu' documenti
    e' quello che sblocca piu' righe di Prima Nota.
    """
    from app.constants.metodi_pagamento import metodo_non_configurato

    fornitori = await db["fornitori"].find({}, {"_id": 0}).to_list(5000)
    conteggio: Dict[str, int] = {}
    for f in await db["invoices"].find({}, {"_id": 0, "fornitore_id": 1}).to_list(20000):
        fid = f.get("fornitore_id")
        if fid:
            conteggio[fid] = conteggio.get(fid, 0) + 1

    senza = [
        {
            "id": f.get("id", ""),
            "nome": f.get("ragione_sociale") or f.get("nome") or "",
            "partita_iva": str(f.get("partita_iva") or ""),
            "iban": str(f.get("iban") or ""),
            "chiave": chiave(f),
            "fatture": conteggio.get(f.get("id", ""), 0),
        }
        for f in fornitori
        if metodo_non_configurato(f.get("metodo_pagamento"))
    ]
    senza.sort(key=lambda r: (-r["fatture"], r["nome"].lower()))
    return senza


async def importa(db, dati: Optional[Dict[str, Any]] = None, *, dry_run: bool = True,
                  attore: str = "importazione") -> Dict[str, Any]:
    """Applica i metodi del file (o di `dati`) all'anagrafica.

    `dry_run` per difetto: un comando che scrive sull'anagrafica di 188
    fornitori non parte per sbaglio. Le righe senza metodo si saltano — un
    metodo vuoto non cancella quello gia' impostato — e un metodo fuori dai
    tre ammessi si rifiuta invece di finire in archivio come parola libera.
    """
    documento = dati if dati is not None else leggi_file()
    righe = documento.get("fornitori") or []

    fornitori = await db["fornitori"].find({}, {"_id": 0}).to_list(5000)
    per_chiave = {chiave(f): f for f in fornitori}
    per_nome = {normalizza_nome(f.get("ragione_sociale") or f.get("nome") or ""): f
                for f in fornitori}

    applicati, saltati, non_trovati, rifiutati = [], 0, [], []
    for riga in righe:
        metodo = str(riga.get("metodo_pagamento") or "").strip().lower()
        if not metodo:
            saltati += 1
            continue
        if not metodo_valido(metodo):
            rifiutati.append({"nome": riga.get("nome", ""), "metodo": metodo})
            continue

        fornitore = per_chiave.get(chiave(riga)) or per_nome.get(normalizza_nome(riga.get("nome", "")))
        if not fornitore:
            non_trovati.append(riga.get("nome", ""))
            continue

        precedente = str(fornitore.get("metodo_pagamento") or "")
        if precedente.strip().lower() == metodo:
            saltati += 1
            continue

        applicati.append({"nome": riga.get("nome", ""), "da": precedente, "a": metodo})
        if not dry_run:
            adesso = datetime.now(timezone.utc).isoformat()
            await db["fornitori"].update_one(
                {"id": fornitore["id"]},
                {"$set": {"metodo_pagamento": metodo, "metodo_pagamento_updated_at": adesso}},
            )
            await db[COLLEZIONE_STORICO].insert_one({
                "id": f"{fornitore['id']}:{adesso}",
                "fornitore_id": fornitore["id"],
                "fornitore_nome": riga.get("nome", ""),
                "chiave": chiave(fornitore),
                "da": precedente,
                "a": metodo,
                "attore": attore,
                "timestamp": adesso,
            })

    return {
        "dry_run": dry_run,
        "applicati": len(applicati),
        "dettaglio": applicati[:200],
        "saltati_senza_metodo_o_gia_uguale": saltati,
        "metodi_rifiutati": rifiutati,
        "fornitori_non_trovati": non_trovati,
    }
