"""Motore unico di categorizzazione dei movimenti bancari da descrizione.

Prima del 19/09/2026 esistevano DUE funzioni con lo stesso nome
(`categorizza_movimento_bancario`), nessuna delle due collegata al vero
percorso di import (`app/routers/bank/estratto_conto.py`): una qui con il
commento "DA INTEGRARE", l'altra in `app/schemas/accounting_rules.py` con un
piano dei conti (4.3.01, 2.1.01, ...) diverso da quello ufficiale CEE
(`app/services/piano_conti_ufficiale.py`). Risultato: al 18/09/2026, 1.764 dei
1.920 movimenti bancari 2026 (92%) non avevano categoria.

Questo e' l'UNICO motore rimasto. Regole:

- Ritorna un valore SOLO dalla tassonomia operativa gia' in produzione
  (`CATEGORIE_BANCA` in `app/routers/prima_nota_module/common.py`), mai una
  tassonomia parallela: la riga scritta qui deve restare compatibile con
  `mappa_categoria_ec()` e con `entra_in_prima_nota()`.
- Categorizza SOLO quando il pattern e' una parola chiave/sigla non ambigua
  nella descrizione. Non associa mai per solo importo (CLAUDE.md, "Identita',
  prove e attese"): un bonifico che assomiglia a una fattura aperta per
  importo resta senza categoria, non diventa "Fatture" per quello.
- Non tocca gli Stipendi: quelli hanno gia' un motore proprio, piu' rigoroso
  di un controllo per parola chiave (`app/services/stipendi_bonifici.py`,
  nome completo + importo esatto + periodo + candidato univoco). Riprodurre
  qui un secondo riconoscimento stipendi via "ADD.TOT"/"VS.DISP" sarebbe
  esattamente il doppione che questo file elimina.
- Non tocca Versamento/Prelevamento Banca, PayPal e "UTENZ*" generico: sono
  gia' riconosciuti dalla causale in `mappa_categoria_ec()` indipendentemente
  dal campo `categoria` salvato, quindi ripeterli qui non aggiungerebbe
  copertura.
- In caso di piu' pattern non ambigui in conflitto sulla stessa descrizione,
  il movimento resta "ambiguo" (categoria None): non si sceglie a caso.

Il riconoscimento del codice tributo F24 riusa i cataloghi ufficiali in
`app/schemas/accounting_rules.py` (F24_ERARIO_CODES, F24_INPS_CODES): stesso
registro versionato usato dal parser dei modelli F24, non un secondo elenco.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ============================================================================
# RICONOSCIMENTO
# ============================================================================

# F24: la sigla "F24" (o le varianti sotto) in causale bancaria non ha altro
# significato possibile. Il codice tributo, se presente, arricchisce il
# dettaglio ma non e' condizione: anche "ADDEBITO F24 IVA E RITENUTE" senza
# codice esplicito e' inequivocabilmente un F24.
_F24_KEYWORDS = (
    "F24", "F 24", "MOD.F24", "MOD F24", "DELEGA F24",
    "I24 AGENZIA ENTRATE", "PAGAMENTO F24", "VERSAMENTO F24",
)

# Spese/competenze bancarie: rientrano fra le "categorie bancarie senza
# documento" (CATEGORIE_SENZA_DOCUMENTO) — la banca stessa e' la prova, non
# esiste una fattura a cui agganciarle. Parole intere o sigle specifiche:
# mai "BOLLO" da solo (si confonderebbe col bollo auto/verbali). "COMM.SU" /
# "COMM.SDD" / "SPESE E COMM" e "IMP.BOLLO" sono le abbreviazioni reali della
# banca (BPM), trovate leggendo le causali vere del 2026: senza queste sigle
# il motore riconosceva solo 150 dei 1.764 movimenti 2026 senza categoria,
# con queste 344 (verificato il 19/09/2026 sul progetto Supabase di
# produzione, sola lettura prima di scrivere).
_COMMISSIONI_KEYWORDS = (
    "COMMISSIONI", "COMMISSIONE", "COMM.SU", "COMM.SDD", "SPESE E COMM",
    "SPESE BANCARIE", "SPESE TENUTA CONTO",
    "CANONE CONTO", "CANONE MENSILE C/C", "CANONE TRIMESTRALE C/C",
    "IMPOSTA DI BOLLO", "IMPOSTA BOLLO", "IMP.BOLLO", "I.BOLLO", "BOLLO C/C",
    "INTERESSI PASSIVI", "INT.PASSIVI", "INTERESSI DEBITORI", "INT.DEB",
    "COMPETENZE TRIMESTRALI", "COMPETENZE BANCARIE",
)

# Utenze: marchi/fornitori di energia, gas, telefonia, acqua non ambigui.
# "UTENZ*" generico e "PAG. UTENZE" sono gia' riconosciuti da
# `mappa_categoria_ec()` a prescindere da questo modulo.
_UTENZE_KEYWORDS = (
    "ENEL", "ENI GAS", "ENI SPA", "A2A", "EDISON", "SORGENIA", "HERA SPA",
    "ACEA", "IREN", "TELECOM ITALIA", "TIM", "TIM SPA", "VODAFONE",
    "WINDTRE", "WIND TRE", "FASTWEB", "ACQUEDOTTO",
)

# Fatture fornitore: solo un riferimento testuale esplicito a una fattura, mai
# il generico "BONIFICO" (lo userebbe qualsiasi bonifico in uscita). Include
# anche assicurazioni e canoni di locazione, che in azienda viaggiano sempre
# con fattura periodica del fornitore/assicuratore — stessa convenzione gia'
# in uso in `_CATEGORIE_EC_PREFISSI` (estratto_conto.py) per la tassonomia
# bancaria: "Assicurazione" e "Altre passivita' - Leasing" -> "Fatture".
_FATTURE_KEYWORDS = (
    "SALDO FATTURA", "SALDO FT", "PAGAM.FATT", "PAGAMENTO FATTURA",
    "PAGAMENTO FORNITORE", "ADD. FATT", "ADD.FATT",
    "ASSICURAZ", "POLIZZA", "PREMIO ASSICURATIVO",
    "CANONE LOCAZIONE", "AFFITTO", "LOCAZIONE UFFICIO", "LOCAZIONE NEGOZIO",
)

_PATTERN_BUCKETS: Dict[str, tuple] = {
    "F24": _F24_KEYWORDS,
    "Commissioni bancarie": _COMMISSIONI_KEYWORDS,
    "Utenze": _UTENZE_KEYWORDS,
    "Fatture": _FATTURE_KEYWORDS,
}

# Codici tributo: stesso registro del parser F24 (nessun secondo elenco).
from app.schemas.accounting_rules import F24_ERARIO_CODES, F24_INPS_CODES  # noqa: E402

_RE_CODICE_ERARIO = re.compile(r"\b([2-6]\d{3})\b")
_RE_CODICE_INPS = re.compile(r"\b(DM\d{2})\b")


def _kw_presente(desc: str, kw: str) -> bool:
    """Cerca la parola chiave rispettando i confini di parola: una sigla
    corta come "IREN" o "ACEA" non deve accendersi dentro "IRENE" o
    "PANACEA SRL" (audit 19/09/2026, verificato: non ancora accaduto sui
    dati reali, ma un rischio latente con un semplice `kw in desc`)."""
    return re.search(r"\b" + re.escape(kw.strip()) + r"\b", desc) is not None


@dataclass(frozen=True)
class EsitoCategorizzazione:
    """Esito del riconoscimento per un singolo movimento."""

    categoria: Optional[str]        # uno dei valori di CATEGORIE_BANCA, o None
    motivo: str                     # spiegazione breve, per audit/report
    codice_tributo: Optional[str] = None
    ambiguo: bool = False


def _codice_tributo(descrizione_upper: str) -> Optional[str]:
    """Codice tributo F24, se riconosciuto nel registro ufficiale."""
    match_erario = _RE_CODICE_ERARIO.search(descrizione_upper)
    if match_erario and match_erario.group(1) in F24_ERARIO_CODES:
        return match_erario.group(1)
    match_inps = _RE_CODICE_INPS.search(descrizione_upper)
    if match_inps and match_inps.group(1) in F24_INPS_CODES:
        return match_inps.group(1)
    return None


def categorizza_movimento_bancario(
    descrizione: Optional[str], importo: float = 0.0,
) -> EsitoCategorizzazione:
    """Riconosce la categoria di un movimento bancario dalla sola descrizione.

    Non associa mai per importo: `importo` resta nella firma solo perche' i
    chiamanti gia' lo passano (compatibilita' con l'uso storico) ma non entra
    in nessuna condizione di riconoscimento.
    """
    desc = (descrizione or "").upper()
    if not desc.strip():
        return EsitoCategorizzazione(None, "descrizione assente")

    trovati = [
        nome for nome, keywords in _PATTERN_BUCKETS.items()
        if any(_kw_presente(desc, kw) for kw in keywords)
    ]

    if len(trovati) > 1:
        return EsitoCategorizzazione(
            None, f"ambiguo: corrisponde a piu' categorie ({', '.join(sorted(trovati))})",
            ambiguo=True,
        )
    if not trovati:
        return EsitoCategorizzazione(None, "nessun pattern non ambiguo riconosciuto")

    categoria = trovati[0]
    if categoria == "F24":
        codice = _codice_tributo(desc)
        motivo = (
            f"parola chiave F24 + codice tributo {codice}" if codice
            else "parola chiave F24 in descrizione"
        )
        return EsitoCategorizzazione("F24", motivo, codice_tributo=codice)

    kw_match = next(kw for kw in _PATTERN_BUCKETS[categoria] if _kw_presente(desc, kw))
    return EsitoCategorizzazione(categoria, f"parola chiave '{kw_match.strip()}'")


# ============================================================================
# BACKFILL — movimenti gia' importati senza categoria
# ============================================================================

_STATO_KEY = "backfill_categorie_banca"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _movimenti_senza_categoria(db, anno: Optional[int]) -> List[Dict[str, Any]]:
    query: Dict[str, Any] = {
        "$or": [
            {"categoria": None}, {"categoria": ""},
            {"categoria": {"$exists": False}},
        ],
    }
    if anno:
        query["data"] = {"$regex": f"^{anno}"}
    return await db["estratto_conto_movimenti"].find(
        query,
        {"_id": 0, "id": 1, "descrizione_originale": 1, "descrizione": 1,
         "importo": 1, "data": 1, "tipo": 1},
    ).to_list(20000)


async def backfill_categorie_banca(
    db, *, anno: Optional[int] = 2026, dry_run: bool = False,
    on_progress=None,
) -> Dict[str, Any]:
    """Valorizza `categoria` sui movimenti gia' importati, SOLO dove il
    riconoscimento e' certo. Non tocca i movimenti che hanno gia' una
    categoria (dal CSV bancario o da una riconciliazione precedente).

    Ordine:
    1. Motore stipendi esistente (`associa_bonifici_stipendi`): nome
       completo + importo esatto + periodo, non un controllo per parola
       chiave — resta l'unico sistema per gli Stipendi.
    2. Questo motore per parola chiave (F24, Commissioni bancarie, Utenze,
       Fatture) sui movimenti ancora senza categoria dopo il passo 1.

    Con `dry_run=True` non scrive nulla: il passo 1 viene saltato (il motore
    stipendi non ha una modalita' di sola simulazione) e il report copre solo
    il passo 2, dichiarandolo nel risultato.
    """
    stipendi_esito: Optional[Dict[str, Any]] = None
    if not dry_run:
        try:
            from app.services.stipendi_bonifici import associa_bonifici_stipendi
            stipendi_esito = await associa_bonifici_stipendi(db, anno=anno)
        except Exception as exc:  # noqa: BLE001 - non deve bloccare il resto
            logger.exception("Motore stipendi non completato durante il backfill categorie")
            stipendi_esito = {"errore": str(exc)}

    movimenti = await _movimenti_senza_categoria(db, anno)
    totale = len(movimenti)

    per_categoria: Dict[str, List[str]] = {}
    dettaglio_f24: Dict[str, str] = {}
    non_riconosciuti = 0
    ambigui = 0
    campioni_non_riconosciuti: List[Dict[str, Any]] = []

    for indice, mov in enumerate(movimenti, start=1):
        descrizione = mov.get("descrizione_originale") or mov.get("descrizione") or ""
        esito = categorizza_movimento_bancario(descrizione, mov.get("importo") or 0)
        if esito.categoria:
            per_categoria.setdefault(esito.categoria, []).append(mov["id"])
            if esito.codice_tributo:
                dettaglio_f24[mov["id"]] = esito.codice_tributo
        else:
            if esito.ambiguo:
                ambigui += 1
            else:
                non_riconosciuti += 1
            if len(campioni_non_riconosciuti) < 20:
                campioni_non_riconosciuti.append({
                    "id": mov.get("id"),
                    "data": mov.get("data"),
                    "importo": mov.get("importo"),
                    "descrizione": descrizione[:120],
                    "motivo": esito.motivo,
                })
        if on_progress and indice % 200 == 0:
            await on_progress(indice, totale)

    aggiornati = 0
    if not dry_run:
        now_iso = _now()
        for categoria, ids in per_categoria.items():
            if not ids:
                continue
            await db["estratto_conto_movimenti"].update_many(
                {"id": {"$in": ids}},
                {"$set": {
                    "categoria": categoria,
                    "categoria_auto": True,
                    "categoria_auto_motivo": "parola chiave non ambigua (backfill 19/09/2026)",
                    "categoria_auto_at": now_iso,
                }},
            )
            aggiornati += len(ids)
        for mov_id, codice in dettaglio_f24.items():
            await db["estratto_conto_movimenti"].update_one(
                {"id": mov_id}, {"$set": {"categoria_codice_tributo": codice}},
            )

    return {
        "success": True,
        "dry_run": dry_run,
        "anno": anno,
        "stipendi": stipendi_esito,
        "movimenti_esaminati": totale,
        "per_categoria": {cat: len(ids) for cat, ids in per_categoria.items()},
        "aggiornati": aggiornati,
        "non_riconosciuti": non_riconosciuti,
        "ambigui": ambigui,
        "non_categorizzati_totale": non_riconosciuti + ambigui,
        "campioni_non_categorizzati": campioni_non_riconosciuti,
    }


async def stato_backfill_categorie_banca(db) -> Dict[str, Any]:
    stato = await db["sistema_stato"].find_one({"chiave": _STATO_KEY}, {"_id": 0}) or {}
    stato.pop("chiave", None)
    return stato


async def _salva_stato_backfill(db, **campi: Any) -> None:
    campi["aggiornato_at"] = _now()
    await db["sistema_stato"].update_one(
        {"chiave": _STATO_KEY}, {"$set": campi}, upsert=True,
    )


_backfill_in_corso = False


def backfill_in_corso() -> bool:
    return _backfill_in_corso


async def _backfill_in_background(db, anno: Optional[int]) -> None:
    global _backfill_in_corso
    _backfill_in_corso = True
    await _salva_stato_backfill(db, stato="in_corso", avviato_at=_now(), risultato=None, errore=None)

    async def progresso(fatti: int, totale: int) -> None:
        await _salva_stato_backfill(db, avanzamento={"fatti": fatti, "totale": totale})

    try:
        risultato = await backfill_categorie_banca(db, anno=anno, dry_run=False, on_progress=progresso)
        await _salva_stato_backfill(
            db, stato="completato", terminato_at=_now(),
            risultato={k: v for k, v in risultato.items() if k != "success"},
        )
    except Exception as exc:  # noqa: BLE001 - lo stato deve restare leggibile
        logger.exception("Backfill categorie banca interrotto")
        await _salva_stato_backfill(db, stato="errore", errore=str(exc), terminato_at=_now())
    finally:
        _backfill_in_corso = False


def avvia_backfill_in_background(db, anno: Optional[int] = 2026) -> bool:
    """Come `registrazione_contabile.avvia_pregresso_in_background`: risponde
    subito, lo stato si segue con `stato_backfill_categorie_banca`."""
    import asyncio
    if _backfill_in_corso:
        return False
    asyncio.create_task(_backfill_in_background(db, anno))
    return True
