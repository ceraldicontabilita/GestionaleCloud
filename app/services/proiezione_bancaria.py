"""Proiezione semantica delle prove bancarie in Prima Nota Banca.

L'estratto conto e' prova immutabile. Quando la causale identifica in modo
univoco la natura dell'operazione (finanziamento socio, retribuzione/TFR o
addebito PayPal), questa prova viene proiettata nel registro contabile tramite
il writer unico. Non viene mai usata la sola uguaglianza dell'importo.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

from app.database import Collections
from app.routers.bonifici_module.classification import (
    classifica_destinazione_dipendente,
)
from app.services.finanziamenti_soci import classifica_finanziamento_ec
from app.services.scritture_contabili import scrivi_movimento_se_assente
from app.services.bank_reconciliation_rules import classify_bank_movement
from app.services.conti_pos import CONTO_BPM as CONTO_BANCA_PREDEFINITO

logger = logging.getLogger(__name__)


logger = logging.getLogger(__name__)

SOURCE = "proiezione_semantica_ec"
CATEGORIA_CONTENZIOSO = "Spese legali e contenzioso"
_PAYPAL = re.compile(r"\bPAYPAL\b", re.IGNORECASE)
_ADDEBITO_DIRETTO = re.compile(
    r"\b(?:SDD|ADDEBITO\s+DIRETTO|49RJ2252ASLM4)\b", re.IGNORECASE
)


def _testo(doc: Dict[str, Any]) -> str:
    return " ".join(
        str(doc.get(campo) or "")
        for campo in (
            "descrizione_originale", "descrizione", "causale",
            "beneficiario", "ordinante",
        )
        if doc.get(campo)
    ).strip()


def _id_ec(doc: Dict[str, Any]) -> str:
    return str(
        doc.get("id")
        or doc.get("movement_id")
        or doc.get("transaction_id")
        or doc.get("_id")
        or ""
    )


def _data_iso(doc: Dict[str, Any]) -> str:
    valore = str(
        doc.get("data_contabile")
        or doc.get("data")
        or doc.get("date")
        or doc.get("data_valuta")
        or ""
    ).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", valore[:10]):
        return valore[:10]
    match = re.search(r"\b(\d{2})[/-](\d{2})[/-](\d{4})\b", valore)
    if match:
        return f"{match.group(3)}-{match.group(2)}-{match.group(1)}"
    return ""


def _verso(doc: Dict[str, Any]) -> Optional[str]:
    valore = str(doc.get("tipo") or doc.get("type") or "").strip().lower()
    if valore in {"entrata", "credito", "credit", "dare"}:
        return "entrata"
    if valore in {"uscita", "debito", "debit", "avere"}:
        return "uscita"
    try:
        return "entrata" if float(doc.get("importo") or 0) > 0 else "uscita"
    except (TypeError, ValueError):
        return None


def _importo(doc: Dict[str, Any]) -> float:
    try:
        return round(abs(float(doc.get("importo") or doc.get("amount") or 0)), 2)
    except (TypeError, ValueError):
        return 0.0


def _classifica_paypal(doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    testo = _testo(doc)
    if _verso(doc) != "uscita" or not (_PAYPAL.search(testo) and _ADDEBITO_DIRETTO.search(testo)):
        return None
    return {
        "tipo": "uscita",
        "categoria": "Pagamento PayPal",
        "tipo_classificazione_contabile": "paypal_sdd",
        "gestore_pagamento": "paypal",
    }


# «RIMBORSO FINANZ. - MUTUO N.1788 4851906 RATA 24/09/2026» (export e banca
# diretta), «MUTUO N.1788 4851906 RATA 24/06/2026» (vecchio archivio): il numero
# del mutuo e la rata sono l'identita', non l'importo.
_RATA_MUTUO = re.compile(
    r"\bMUTUO\s+N\.?\s*(\d{3,5}[\s/]+[\d/]{5,})\s+RATA\s+(\d{2}/\d{2}/\d{4})",
    re.IGNORECASE,
)


def _classifica_rata_mutuo(doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """La rata addebitata dalla banca sul mutuo che la causale nomina.

    Esce davvero dal conto, quindi entra in Banca sul conto dei mutui
    (``mapping_piano_conti``: «rata mutuo» -> 31.03.05). Quanto sia capitale e
    quanto interessi lo dice il piano d'ammortamento della banca: finche' non
    c'e', la ripartizione resta dichiarata da verificare, mai stimata.
    """
    if _verso(doc) != "uscita":
        return None
    trovato = _RATA_MUTUO.search(_testo(doc))
    if not trovato:
        return None
    return {
        "tipo": "uscita",
        "categoria": "Rata mutuo",
        "tipo_classificazione_contabile": "rata_mutuo",
        "numero_mutuo": re.sub(r"[\s/]+", " ", trovato.group(1)).strip(),
        "rata_scadenza": trovato.group(2),
        "ripartizione_capitale_interessi": "da_verificare",
    }


# Addebito spese di una disposizione: stessa causale del bonifico, col nome
# del beneficiario dentro («- ADD.SPE», «COMM.SU BONIFICI»).
SPESE_DISPOSIZIONE_RE = re.compile(r"ADD\.?\s*SPE\b|COMM\.?\s*SU\s*BONIFIC", re.IGNORECASE)


def _classifica_dipendente(
    doc: Dict[str, Any], dipendenti: Iterable[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if _verso(doc) != "uscita":
        return None
    risultato = classifica_destinazione_dipendente(doc, dipendenti)
    if not (risultato.get("destinazione_dipendente") and risultato.get("identita_univoca")):
        return None
    tipo = risultato.get("tipo_retribuzione") or "stipendio"
    return {
        "tipo": "uscita",
        "categoria": "TFR" if tipo == "tfr" else "Stipendi",
        "tipo_classificazione_contabile": tipo,
        "dipendente_id": risultato.get("dipendente_id"),
        "dipendente_nome": risultato.get("dipendente_nome_rilevato"),
        "dipendente_codice_fiscale": risultato.get("dipendente_codice_fiscale"),
        "motivo_classificazione": risultato.get("motivo_destinazione"),
    }


def classifica_movimento_ec(
    doc: Dict[str, Any], dipendenti: Iterable[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Classifica solo identita' esplicite; nessun match per importo."""
    fascicolo = doc.get("fascicolo_giudiziario")
    if fascicolo and _verso(doc) == "uscita":
        # Spese di lite: l'uscita cita la sentenza o il titolare l'ha messa nel
        # fascicolo (``atti_giudiziari.collega_pagamenti``). Nessuna fattura.
        return {
            "tipo": "uscita",
            "categoria": CATEGORIA_CONTENZIOSO,
            "tipo_classificazione_contabile": "spese_contenzioso",
            "fascicolo_giudiziario": fascicolo,
        }
    finanziamento = classifica_finanziamento_ec(doc)
    if finanziamento:
        return {
            "tipo": finanziamento["tipo_banca"],
            "categoria": "Finanziamento soci",
            "tipo_classificazione_contabile": f"finanziamento_socio_{finanziamento['tipo']}",
            "socio_id": finanziamento["socio_id"],
            "socio_nome": finanziamento["socio_nome"],
            "tipo_finanziamento": finanziamento["tipo"],
        }
    causale = classify_bank_movement(doc)
    if (
        causale
        and causale.get("tipo") == "commissione_bancaria"
        and _verso(doc) == "uscita"
    ):
        # Commissioni e competenze sono costi bancari deterministici che non
        # richiedono una fattura esterna. Possono quindi entrare nel registro
        # con la riga EC come prova esatta; POS, SDD, F24 e versamenti restano
        # invece solo classificati finche' manca il collegamento reciproco.
        return {
            "tipo": "uscita",
            "categoria": "Commissioni bancarie",
            "tipo_classificazione_contabile": (
                f"commissione_bancaria:{causale['rule_id']}"
            ),
            "regola_bancaria": causale["rule_id"],
            "regola_versione": causale["rule_version"],
            "campi_estratti": causale.get("campi_estratti") or {},
        }
    if SPESE_DISPOSIZIONE_RE.search(_testo(doc)) and _verso(doc) == "uscita":
        # «COMM.SU BONIFICI - VS.DISP. … FAVORE <dipendente> - ADD.SPE»: la
        # commissione del bonifico porta il nome del beneficiario, ma e' un
        # costo della banca, non uno stipendio.
        return {
            "tipo": "uscita",
            "categoria": "Commissioni bancarie",
            "tipo_classificazione_contabile": "commissione_bancaria:spese_disposizione",
        }
    mutuo = _classifica_rata_mutuo(doc)
    if mutuo:
        return mutuo
    dipendente = _classifica_dipendente(doc, dipendenti)
    if dipendente:
        return dipendente
    return _classifica_paypal(doc)


def _cifre_mutuo(numero: Any) -> str:
    """L'identita' del mutuo nelle sue tre forme: «1788 4851906» in causale,
    delibera «904851906» sul piano, «1788/0004851906» sulla quietanza."""
    ultime = re.findall(r"\d+", str(numero or ""))
    return ultime[-1].lstrip("0")[-7:] if ultime else ""


def _data_gma(valore: Any) -> str:
    testo = str(valore or "")[:10]
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", testo):
        anno, mese, giorno = testo.split("-")
        return f"{giorno}/{mese}/{anno}"
    return testo


async def _carica_quote_mutui(db) -> list:
    """Righe (numero, scadenza gg/mm/aaaa, importo, capitale, interessi, fonte).

    La quietanza della banca vince sul piano (prova il pagamento di quella
    rata); il piano copre le rate senza quietanza. Nessuna quota si stima.
    """
    righe: list = []
    try:
        quietanze = await db["mutui_quietanze"].find(
            {}, {"_id": 0, "numero_finanziamento": 1, "data_scadenza": 1, "importo_totale": 1,
                 "quota_capitale": 1, "quota_interessi": 1, "numero_rata": 1, "sha256": 1},
        ).to_list(None)
        piani = await db["mutui_piani_documentali"].find(
            {}, {"_id": 0, "id": 1, "numero_delibera": 1, "rate": 1, "sha256": 1},
        ).to_list(None)
    except Exception as exc:  # noqa: BLE001 - senza piano la rata resta da verificare
        logger.warning("Piani/quietanze mutui non leggibili (%s): quote da verificare", type(exc).__name__)
        return righe
    for q in quietanze:
        righe.append((_cifre_mutuo(q.get("numero_finanziamento")), _data_gma(q.get("data_scadenza")),
                      q.get("importo_totale"), q.get("quota_capitale"), q.get("quota_interessi"),
                      q.get("numero_rata"), "quietanza"))
    for piano in piani:
        for rata in piano.get("rate") or []:
            righe.append((_cifre_mutuo(piano.get("numero_delibera")), _data_gma(rata.get("data_scadenza")),
                          rata.get("importo_totale"), rata.get("quota_capitale"), rata.get("quota_interessi"),
                          rata.get("numero_rata"), "piano_ammortamento"))
    return righe


def _quote_rata(classificazione: Dict[str, Any], importo: float, quote: list) -> Dict[str, Any]:
    """Capitale e interessi della rata: stesso mutuo, stessa scadenza, stesso
    importo al centesimo. Se non torna, la ripartizione resta da verificare."""
    numero = _cifre_mutuo(classificazione.get("numero_mutuo"))
    scadenza = classificazione.get("rata_scadenza")
    for fonte in ("quietanza", "piano_ammortamento"):
        for num, scad, totale, capitale, interessi, numero_rata, origine in quote:
            if origine != fonte or num != numero or scad != scadenza:
                continue
            try:
                if abs(float(totale) - importo) > 0.005:
                    continue
                capitale, interessi = round(float(capitale), 2), round(float(interessi), 2)
            except (TypeError, ValueError):
                continue
            if abs(capitale + interessi - importo) > 0.01:
                continue
            return {
                "quota_capitale": capitale,
                "quota_interessi": interessi,
                "numero_rata": numero_rata,
                "ripartizione_capitale_interessi": origine,
                # Capitale: debito verso la banca; interessi: costo (75.03.05).
                "ripartizione_conti": [
                    {"conto": "31.03.05", "importo": capitale},
                    {"conto": "75.03.05", "importo": interessi},
                ],
            }
    return {}


# Riferimento della disposizione BPM («RIF. MB0B10283131/…», «MBVT96918868»):
# e' lo stesso in ogni copia dell'estratto conto.
_RIF_DISPOSIZIONE = re.compile(r"\b(MB[A-Z0-9]{2}\d{8})")


def _chiave_operazione(data: str, importo: float, classificazione: Dict[str, Any],
                       conto: Optional[str] = None, testo: str = "") -> tuple:
    """Conto, giorno, importo, verso, categoria e chi: la stessa operazione in ogni copia.

    Per uno stipendio «chi» e' il riferimento della disposizione quando c'e':
    una copia dell'estratto conto portava il dipendente vero, l'altra quello
    provvisorio ricavato dai salari (``salario:nome|cognome``), e lo stesso
    bonifico finiva in due gruppi con due righe in Banca (17 stipendi,
    14.000,00 EUR contati due volte).
    """
    chi = str(classificazione.get("dipendente_id") or classificazione.get("socio_id")
              or classificazione.get("numero_mutuo") or classificazione.get("gestore_pagamento")
              or classificazione.get("fascicolo_giudiziario") or "")
    if classificazione.get("dipendente_id"):
        rif = _RIF_DISPOSIZIONE.search(testo or str(classificazione.get("descrizione") or ""))
        if rif:
            chi = f"rif:{rif.group(1)}"
    return (
        conto or CONTO_BANCA_PREDEFINITO,
        data, int(round(importo * 100)), classificazione.get("tipo"), classificazione.get("categoria"),
        chi,
    )


def _documento(movimento_ec: Dict[str, Any], classificazione: Dict[str, Any],
               data: str, importo: float, ec_id: str,
               conto_contabile: str = None) -> Dict[str, Any]:
    return {
        **({"conto_contabile": conto_contabile} if conto_contabile else {}),
        "data": data,
        "anno": int(data[:4]),
        "mese": int(data[5:7]),
        "tipo": classificazione["tipo"],
        "importo": importo,
        "categoria": classificazione["categoria"],
        "descrizione": _testo(movimento_ec),
        "source": SOURCE,
        "natura": "movimento_bancario_reale",
        "estratto_conto_id": ec_id,
        "movimento_estratto_conto_id": ec_id,
        "movimento_bancario_id": ec_id,
        "classificazione_automatica": True,
        "tipo_classificazione_contabile": classificazione["tipo_classificazione_contabile"],
        "classificato_at": datetime.now(timezone.utc).isoformat(),
        **{k: v for k, v in classificazione.items() if k not in {"tipo", "categoria"} and v},
    }


_CAMPI_CLASSIFICAZIONE = (
    "dipendente_id", "dipendente_nome", "dipendente_codice_fiscale", "motivo_classificazione",
    "socio_id", "socio_nome", "tipo_finanziamento", "numero_mutuo", "rata_scadenza",
    "ripartizione_capitale_interessi", "gestore_pagamento", "regola_bancaria",
    "regola_versione", "campi_estratti", "fascicolo_giudiziario",
)


_CATEGORIE_RETRIBUTIVE = {"Stipendi", "TFR"}


async def _riclassifica_riga_propria(db, prima_nota_id: str, documento: Dict[str, Any],
                                     stats: Dict[str, Any]) -> None:
    """Una riga «Stipendi»/«TFR» scritta da questo motore diventa rimborso
    (o apporto) soci quando la causale, letta meglio, lo dichiara: cambia
    categoria e contropartita con lo stesso id, nessuna seconda uscita. Una
    riga scritta da altri (import, a mano) non si tocca."""
    from app.services.mapping_piano_conti import completa_conti_prima_nota

    # Solo il caso in cui la causale e' una prova piu' forte del nome: un
    # rimborso/apporto soci scritto come stipendio. Il resto non si ritocca
    # (fra un giro e l'altro la stessa riga puo' leggersi TFR o stipendio).
    if not str(documento.get("tipo_classificazione_contabile") or "").startswith(
        ("finanziamento_socio_", "commissione_bancaria:")
    ):
        return
    riga = await db["prima_nota_banca"].find_one({"id": prima_nota_id}, {"_id": 0})
    if not riga or riga.get("source") != SOURCE:
        return
    if riga.get("categoria") not in _CATEGORIE_RETRIBUTIVE:
        return
    campi = {
        "categoria": documento["categoria"],
        "tipo": documento["tipo"],
        "tipo_classificazione_contabile": documento["tipo_classificazione_contabile"],
        "descrizione": documento["descrizione"],
        "classificato_at": documento["classificato_at"],
        "riclassificata_da": riga.get("categoria"),
    }
    for campo in _CAMPI_CLASSIFICAZIONE:
        campi[campo] = documento.get(campo)
    base = {k: v for k, v in {**riga, **campi}.items()
            if k not in ("conto_contropartita", "conto_contropartita_nome",
                         "contropartita_da_classificare")}
    campi.update({"conto_contropartita": None, "conto_contropartita_nome": None,
                  "contropartita_da_classificare": None})
    campi.update(completa_conti_prima_nota("banca", base))
    await db["prima_nota_banca"].update_one({"id": prima_nota_id}, {"$set": campi})
    stats["riclassificate"] = stats.get("riclassificate", 0) + 1
    logger.warning("Riga Prima Nota %s riclassificata: %s -> %s",
                   prima_nota_id, riga.get("categoria"), documento["categoria"])


async def proietta_movimenti_bancari_semantici(
    db, *, anno: Optional[int] = None, movimento_ids=None,
    collezione: str = Collections.BANK_STATEMENTS,
    conto_contabile: str = CONTO_BANCA_PREDEFINITO,
) -> Dict[str, Any]:
    """Scrive in Banca le sole prove con classificazione univoca e auditabile.

    ``collezione`` e ``conto_contabile`` servono alla carta SumUp: stessi
    criteri del conto BPM, righe di Prima Nota sul suo conto (19.01.05). Il
    conto fa parte dell'identita' dell'operazione: un pagamento uguale sulla
    carta e sul BPM sono due operazioni, mai una copia dell'altra.
    """
    dipendenti = await db[Collections.EMPLOYEES].find(
        {}, {
            "_id": 0, "id": 1, "nome": 1, "cognome": 1,
            "nome_completo": 1, "codice_fiscale": 1, "cf": 1, "iban": 1,
        },
    ).to_list(5000)

    query: Dict[str, Any] = {}
    if movimento_ids:
        ids = [str(item) for item in movimento_ids if item]
        query = {"$or": [
            {"id": {"$in": ids}},
            {"movement_id": {"$in": ids}},
            {"transaction_id": {"$in": ids}},
        ]}

    stats = {
        "esaminati": 0, "proiettati": 0, "gia_presenti": 0,
        "finanziamenti_soci": 0, "stipendi": 0, "tfr": 0,
        "paypal_sdd": 0, "non_classificati": 0,
        "causali_deterministiche": 0,
        "commissioni_bancarie": 0,
    }
    stats["doppioni_tolti"] = 0
    stats["rate_mutuo"] = 0
    candidati: list = []
    cursore = db[collezione].find(query)
    async for movimento_ec in cursore:
        if str(movimento_ec.get("status") or "") in {"deleted", "archived"}:
            continue
        data = _data_iso(movimento_ec)
        if anno and not data.startswith(f"{anno}-"):
            continue
        stats["esaminati"] += 1
        ec_id = _id_ec(movimento_ec)
        importo = _importo(movimento_ec)
        causale_classification = classify_bank_movement(movimento_ec)
        if causale_classification and ec_id and movimento_ec.get("classificazione_rule_id") != causale_classification["rule_id"]:
            source_query = (
                {"_id": movimento_ec["_id"]}
                if movimento_ec.get("_id") is not None
                else {"id": ec_id}
            )
            await db[collezione].update_one(
                source_query,
                {"$set": {
                    "decisione_classificazione": "automatica",
                    "classificazione_rule_id": causale_classification["rule_id"],
                    "classificazione_rule_version": causale_classification["rule_version"],
                    "classificazione_evidenze": causale_classification["evidenze"],
                    "classificazione_campi_estratti": causale_classification["campi_estratti"],
                    "classificazione_tipo": causale_classification["tipo"],
                    "classificazione_categoria": causale_classification["categoria"],
                    "classificato_at": datetime.now(timezone.utc).isoformat(),
                }},
            )
        if causale_classification and ec_id:
            stats["causali_deterministiche"] += 1
        # Il confronto dei nomi e' calcolo puro: un thread per movimento lascia respirare il loop (regola 16).
        classificazione = await asyncio.to_thread(classifica_movimento_ec, movimento_ec, dipendenti)
        if not classificazione or not ec_id or not data or importo <= 0:
            stats["non_classificati"] += 1
            continue
        candidati.append((movimento_ec, classificazione, data, importo, ec_id))

    if any(voce[1].get("tipo_classificazione_contabile") == "rata_mutuo" for voce in candidati):
        quote = await _carica_quote_mutui(db)
        for voce in candidati:
            if voce[1].get("tipo_classificazione_contabile") == "rata_mutuo":
                trovate = _quote_rata(voce[1], voce[3], quote)
                if trovate:
                    voce[1].update(trovate)

    # La stessa operazione arriva da piu' export (vecchio archivio, CSV,
    # banca diretta): una riga in Banca per operazione, non per copia. Fino al
    # 26/09/2026 ogni copia scriveva la sua: 23 stipendi contati due volte,
    # 27.076,00 EUR di uscite in piu'. Il numero vero e' il massimo per fonte
    # (``versamenti_contanti._quante_operazioni``); le righe in piu' scritte da
    # questo motore si tolgono per id, solo nel giro completo.
    from app.services.versamenti_contanti import _fonte_ec, _quante_operazioni

    gruppi: Dict[tuple, list] = {}
    for voce in candidati:
        gruppi.setdefault(
            _chiave_operazione(voce[2], voce[3], voce[1], conto_contabile, _testo(voce[0])), [],
        ).append(voce)

    # Una riga gia' agganciata a una copia del gruppo e' quell'operazione,
    # qualunque sia la sua chiave: uno stipendio scritto col dipendente
    # provvisorio ``salario:nome|cognome`` (anagrafica ricavata dai salari)
    # finiva in un altro gruppo, e la copia gemella scriveva una seconda riga.
    gruppo_per_ec: Dict[str, tuple] = {
        voce[4]: chiave for chiave, voci in gruppi.items() for voce in voci
    }

    esistenti: Dict[tuple, list] = {}
    if gruppi:
        # Anche le righe scritte da altri canali (import dell'estratto conto,
        # registrazioni a mano) sono gia' l'operazione: contano, non si toccano.
        # Anche per estratto conto: una riga scritta con la categoria sbagliata
        # (una commissione registrata come stipendio) e' ancora quell'operazione.
        righe = await db["prima_nota_banca"].find(
            {"$or": [{"categoria": {"$in": sorted({chiave[4] for chiave in gruppi})}},
                     {"estratto_conto_id": {"$in": sorted(gruppo_per_ec)}}],
             "status": {"$nin": ["deleted", "archived"]}},
            {"_id": 0, "id": 1, "data": 1, "importo": 1, "tipo": 1, "categoria": 1,
             "conto_contabile": 1,
             "dipendente_id": 1, "socio_id": 1, "numero_mutuo": 1, "gestore_pagamento": 1,
             "fascicolo_giudiziario": 1, "descrizione": 1,
             "estratto_conto_id": 1, "source": 1, "ripartizione_capitale_interessi": 1},
        ).to_list(None)
        for riga in righe:
            chiave = gruppo_per_ec.get(str(riga.get("estratto_conto_id") or "")) or _chiave_operazione(
                str(riga.get("data") or "")[:10], _importo(riga),
                {"tipo": riga.get("tipo"), "categoria": riga.get("categoria"), **riga},
                riga.get("conto_contabile"),
            )
            esistenti.setdefault(chiave, []).append(riga)

    adesso = datetime.now(timezone.utc).isoformat()
    for chiave, voci in gruppi.items():
        n = _quante_operazioni([voce[0] for voce in voci])
        ec_del_gruppo = {voce[4] for voce in voci}
        tenute = sorted(
            esistenti.get(chiave, []),
            key=lambda r: (r.get("source") == SOURCE,
                           r.get("estratto_conto_id") not in ec_del_gruppo,
                           # resta la riga col dipendente vero, non quello provvisorio
                           str(r.get("dipendente_id") or "").startswith("salario:"),
                           str(r.get("id") or "")),
        )
        if movimento_ids is None:
            for extra in tenute[n:]:
                if extra.get("source") != SOURCE:
                    continue
                await db["prima_nota_banca"].update_one({"id": extra["id"]}, {"$set": {
                    "status": "deleted", "deleted_at": adesso,
                    "deleted_reason": "doppione_stessa_operazione_bancaria",
                    "deleted_by": SOURCE,
                }})
                stats["doppioni_tolti"] += 1
            tenute = tenute[:n] + [r for r in tenute[n:] if r.get("source") != SOURCE]
        per_ec = {r.get("estratto_conto_id"): r for r in tenute if r.get("estratto_conto_id")}
        libere = [r for r in tenute if r.get("estratto_conto_id") not in ec_del_gruppo]
        voci = sorted(voci, key=lambda v: (v[4] not in per_ec, _fonte_ec(v[0]) == "enable_banking", v[4]))
        for indice, (movimento_ec, classificazione, data, importo, ec_id) in enumerate(voci):
            riga = per_ec.get(ec_id)
            gia_esistente = riga is not None
            if riga is not None and riga.get("categoria") != classificazione["categoria"]:
                # La stessa riga, letta meglio: cambia categoria con lo stesso id.
                await _riclassifica_riga_propria(db, riga["id"], _documento(
                    movimento_ec, classificazione, data, importo, ec_id,
                    conto_contabile if conto_contabile != CONTO_BANCA_PREDEFINITO else None,
                ), stats)
            if riga is None and libere:
                riga = libere.pop(0)
                gia_esistente = True
            if riga is None and len(tenute) >= n and tenute:
                # Una copia in piu' della stessa operazione: si aggancia, non scrive.
                riga = tenute[indice % len(tenute)]
                gia_esistente = True
            if riga is None:
                prima_nota_id, gia_esistente = await scrivi_movimento_se_assente(
                    db, "banca",
                    {"$or": [
                        {"estratto_conto_id": ec_id},
                        {"movimento_estratto_conto_id": ec_id},
                        {"movimento_bancario_id": ec_id},
                        {"movimento_banca_id": ec_id},
                    ]},
                    _documento(
                        movimento_ec, classificazione, data, importo, ec_id,
                        conto_contabile if conto_contabile != CONTO_BANCA_PREDEFINITO else None,
                    ),
                )
                if gia_esistente:
                    await _riclassifica_riga_propria(
                        db, prima_nota_id, _documento(
                            movimento_ec, classificazione, data, importo, ec_id,
                            conto_contabile if conto_contabile != CONTO_BANCA_PREDEFINITO else None,
                        ), stats,
                    )
                riga = {"id": prima_nota_id, "estratto_conto_id": ec_id}
                tenute.append(riga)
            prima_nota_id = riga["id"]
            tipo_classificazione = classificazione["tipo_classificazione_contabile"]
            if (
                gia_esistente and riga.get("source") == SOURCE
                and classificazione.get("quota_capitale") is not None
                and riga.get("ripartizione_capitale_interessi") != classificazione["ripartizione_capitale_interessi"]
            ):
                # La rata gia' in Banca prende le quote quando arriva il piano.
                await db["prima_nota_banca"].update_one({"id": prima_nota_id}, {"$set": {
                    k: classificazione[k] for k in (
                        "quota_capitale", "quota_interessi", "numero_rata",
                        "ripartizione_capitale_interessi", "ripartizione_conti",
                    )
                }})
                riga["ripartizione_capitale_interessi"] = classificazione["ripartizione_capitale_interessi"]
            if movimento_ec.get("prima_nota_banca_id") != prima_nota_id or not movimento_ec.get("classificato_contabilmente"):
                query_sorgente = (
                    {"_id": movimento_ec["_id"]}
                    if movimento_ec.get("_id") is not None
                    else {"id": ec_id}
                )
                await db[collezione].update_one(
                    query_sorgente,
                    {"$set": {
                        "classificato_contabilmente": True,
                        "tipo_classificazione_contabile": tipo_classificazione,
                        "prima_nota_banca_id": prima_nota_id,
                        "proiezione_contabile_at": adesso,
                        **{k: v for k, v in classificazione.items() if k in {
                            "socio_id", "socio_nome", "dipendente_id", "dipendente_nome",
                            "gestore_pagamento",
                        } and v},
                    }},
                )
            if gia_esistente:
                stats["gia_presenti"] += 1
            else:
                stats["proiettati"] += 1
            if tipo_classificazione.startswith("finanziamento_socio_"):
                stats["finanziamenti_soci"] += 1
            elif tipo_classificazione.startswith("commissione_bancaria:"):
                stats["commissioni_bancarie"] += 1
            elif tipo_classificazione == "rata_mutuo":
                stats["rate_mutuo"] += 1
            elif tipo_classificazione == "spese_contenzioso":
                stats["spese_contenzioso"] = stats.get("spese_contenzioso", 0) + 1
            elif tipo_classificazione in {"stipendio", "tfr", "paypal_sdd"}:
                chiave_statistica = {
                    "stipendio": "stipendi",
                    "tfr": "tfr",
                    "paypal_sdd": "paypal_sdd",
                }[tipo_classificazione]
                stats[chiave_statistica] += 1
    return stats
