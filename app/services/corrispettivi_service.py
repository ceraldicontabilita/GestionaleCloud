"""CSV «Corrispettivi» del portale Agenzia delle Entrate: dato PROVVISORIO.

Qui vive solo l'import del CSV (`importa_csv_ade`). La vecchia classe
`CorrispettiviService` (process_xml, create_manual, somma delle chiusure dello
stesso giorno in una riga) non aveva nessun chiamante in produzione ed e' stata
tolta il 02/10/2026: l'unico motore che scrive una chiusura RT e'
`app.routers.invoices.corrispettivi_helpers.ingest_corrispettivo_parsed`.
"""

from typing import Dict, Any, List
from datetime import datetime, timezone
import logging
import uuid

logger = logging.getLogger(__name__)


# ── CSV «Corrispettivi» del portale Agenzia delle Entrate: dato PROVVISORIO ──────────

#: Lo stesso ciclo del corrispettivo manuale serale: ``provvisorio`` finche' non arriva
#: l'XML del registratore, che lo promuove a ``definitivo_xml`` (matricola + data) e
#: sovrascrive importi e quote. Il CSV non ha la divisione contanti/POS ne' il non
#: riscosso: niente Prima Nota, niente giornale, niente evento finche' non c'e' l'XML.
STATO_PROVVISORIO = "provvisorio"
STATO_DEFINITIVO_XML = "definitivo_xml"
SORGENTE_CSV_ADE = "csv_ade"


def _cents_csv(valore: str) -> int:
    """«000000002518,15» -> 251815. Solo Decimal, mai float."""
    from decimal import Decimal

    pulito = (valore or "").strip().strip("'\"").replace(".", "").replace(",", ".")
    return int((Decimal(pulito) * 100).to_integral_value())


def leggi_csv_ade(testo: str) -> Dict[str, Any]:
    """Righe del CSV AdE per intestazione di posizione fissa; gli errori si elencano, non si saltano.

    Colonne (portale «Corrispettivi»): Id invio; Matricola; Data rilevazione; Data trasmissione;
    **Ammontare delle vendite** = imponibile (verificato sulle chiusure XML di settembre 2026:
    coincide al centesimo con ``totale_imponibile``); Imponibile al 10% (puo' differire: aliquote
    miste); **Imposta** = IVA; periodo di inattivita' da/a.
    """
    import csv
    import io
    import re

    righe: List[Dict[str, Any]] = []
    errori: List[str] = []
    lettore = csv.reader(io.StringIO(testo.lstrip("﻿")), delimiter=";")
    for numero, parti in enumerate(lettore, start=1):
        if not parti or not "".join(parti).strip():
            continue
        if numero == 1 and ("Id invio" in parti[0] or "Matricola" in "".join(parti)):
            continue
        if len(parti) < 7:
            errori.append(f"Riga {numero}: attese almeno 7 colonne, trovate {len(parti)}")
            continue
        try:
            quando = re.match(r"(\d{2})/(\d{2})/(\d{4})", parti[2].strip())
            if not quando:
                raise ValueError(f"data non valida: {parti[2]!r}")
            righe.append({
                "id_invio": parti[0].strip().strip("'\""),
                "matricola": parti[1].strip().strip("'\""),
                "data": f"{quando.group(3)}-{quando.group(2)}-{quando.group(1)}",
                "data_rilevazione": parti[2].strip(), "data_trasmissione": parti[3].strip(),
                "ammontare_cents": _cents_csv(parti[4]), "imponibile_colonna_cents": _cents_csv(parti[5]),
                "imposta_cents": _cents_csv(parti[6]),
                "inattivita_da": parti[7].strip() if len(parti) > 7 else "",
                "inattivita_a": parti[8].strip() if len(parti) > 8 else "",
            })
        except (ValueError, ArithmeticError) as exc:
            errori.append(f"Riga {numero}: {type(exc).__name__}: {exc}")
    return {"righe": righe, "errori": errori}


async def importa_csv_ade(db, testo: str, filename: str = "", *, dry_run: bool = False) -> Dict[str, Any]:
    """Registra come PROVVISORIE le giornate del CSV che l'XML non ha ancora coperto.

    - Giornata gia' ``definitivo_xml``: non si tocca; si confronta l'imponibile (somma del giorno).
    - Giornata gia' provvisoria manuale: non si tocca (conflitto dichiarato).
    - Altrimenti una riga ``provvisorio`` per ogni invio (``id_invio``): il secondo import dello
      stesso file non crea niente (``nuovi=0``).
    ``dry_run`` non scrive. Nessun evento, nessuna Prima Nota, nessuna scrittura contabile.
    """
    letto = leggi_csv_ade(testo)
    esito: Dict[str, Any] = {
        "dry_run": dry_run, "righe_lette": len(letto["righe"]), "nuovi": 0, "aggiornati": 0, "invariati": 0,
        "gia_definitivi": 0, "fuori_anno": 0, "anno_attivo": None,
        "conflitti": [], "discordanze_con_xml": [], "chiusure_dichiarate": 0,
        "errori": list(letto["errori"]), "giornate_provvisorie": [],
    }
    per_giorno: Dict[str, List[Dict[str, Any]]] = {}
    for riga in letto["righe"]:
        per_giorno.setdefault(riga["data"], []).append(riga)

    # Nel gestionale entra solo l'anno attivo (decisione del titolare, 20/09/2026):
    # il CSV del portale puo' coprire piu' anni, ma una giornata di un altro anno
    # non diventa un corrispettivo (come per l'XML); l'originale resta dov'e'.
    from app.services.config_import import get_anno_importazione_attivo

    anno_attivo = await get_anno_importazione_attivo(db)
    esito["anno_attivo"] = anno_attivo

    now = datetime.now(timezone.utc).isoformat()
    for giorno in sorted(per_giorno):
        righe = per_giorno[giorno]
        if int(giorno[:4]) != anno_attivo:
            esito["fuori_anno"] += len(righe)
            continue
        presenti = await db["corrispettivi"].find(
            {"data": giorno, "entity_status": {"$ne": "deleted"},
             "status": {"$nin": ["deleted", "archived", "archiviata"]}}, {"_id": 0},
        ).to_list(50)
        definitivi = [d for d in presenti if d.get("stato") == STATO_DEFINITIVO_XML]
        if definitivi:
            esito["gia_definitivi"] += len(righe)
            xml_cents = sum(int(round(float(d.get("totale_imponibile") or 0) * 100)) for d in definitivi)
            csv_cents = sum(r["ammontare_cents"] for r in righe)
            if xml_cents != csv_cents:
                esito["discordanze_con_xml"].append({
                    "data": giorno, "imponibile_xml_cents": xml_cents, "imponibile_csv_cents": csv_cents})
            continue
        altri = [d for d in presenti if d.get("source") != SORGENTE_CSV_ADE]
        if altri:
            esito["conflitti"].append({"data": giorno, "motivo": "esiste gia' una riga non XML per questa giornata",
                                       "source": altri[0].get("source"), "stato": altri[0].get("stato")})
            continue
        gia_csv = {d.get("id_invio"): d for d in presenti}
        for r in righe:
            imponibile = r["ammontare_cents"]
            totale = imponibile + r["imposta_cents"]
            nuovi_campi = {
                "totale": totale / 100, "totale_cents": totale,
                "totale_imponibile": imponibile / 100, "totale_imponibile_cents": imponibile,
                "totale_iva": r["imposta_cents"] / 100, "totale_iva_cents": r["imposta_cents"],
                "csv_ade": {"id_invio": r["id_invio"], "ammontare_cents": r["ammontare_cents"],
                            "imponibile_colonna_cents": r["imponibile_colonna_cents"],
                            "imposta_cents": r["imposta_cents"], "data_trasmissione": r["data_trasmissione"],
                            "filename": filename},
            }
            precedente = gia_csv.get(r["id_invio"])
            if precedente:
                # Lo stesso contenuto con un altro nome di file («corrispettivi (1).csv»)
                # non e' una variazione: il nome non conta nel confronto.
                def _senza_nome(campo, valore):
                    return ({k: x for k, x in valore.items() if k != "filename"}
                            if campo == "csv_ade" and isinstance(valore, dict) else valore)

                if all(_senza_nome(k, precedente.get(k)) == _senza_nome(k, v)
                       for k, v in nuovi_campi.items()):
                    esito["invariati"] += 1
                    continue
                esito["aggiornati"] += 1
                if not dry_run:
                    await db["corrispettivi"].update_one(
                        {"id": precedente["id"]}, {"$set": {**nuovi_campi, "updated_at": now}})
                continue
            esito["nuovi"] += 1
            esito["giornate_provvisorie"].append({"data": giorno, "imponibile_cents": imponibile, "iva_cents": r["imposta_cents"]})
            if dry_run:
                continue
            await db["corrispettivi"].insert_one({
                "id": str(uuid.uuid4()), "data": giorno, "anno": int(giorno[:4]), "mese": int(giorno[5:7]),
                "id_invio": r["id_invio"], "matricola_rt": r["matricola"],
                **nuovi_campi,
                # Ignoti finche' non arriva l'XML: mai per differenza.
                "pagato_contanti": None, "pagato_elettronico": None, "totale_derivato": True,
                "stato": STATO_PROVVISORIO, "source": SORGENTE_CSV_ADE, "status": "imported",
                "data_import_xml": None, "totale_xml": None,
                "created_at": now, "updated_at": now,
            })

    # Periodi di inattivita' dichiarati dal RT: non sono corrispettivi mancanti.
    for r in letto["righe"]:
        if r["inattivita_da"] and not dry_run:
            try:
                from app.services.chiusure_attivita import registra_chiusura

                await registra_chiusura(
                    db, r["inattivita_da"][:10], (r["inattivita_a"] or r["inattivita_da"])[:10],
                    "inattivita", "ade_inattivita", riferimento=r["id_invio"],
                    note=f"dichiarata dal RT {r['matricola']} con l'invio {r['id_invio']}")
                esito["chiusure_dichiarate"] += 1
            except Exception as exc:  # noqa: BLE001
                esito["errori"].append(f"Inattivita' {r['id_invio']}: {type(exc).__name__}: {exc}")
    return esito
