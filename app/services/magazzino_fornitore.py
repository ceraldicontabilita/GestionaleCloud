"""Nel magazzino / fuori dal magazzino: la decisione sul fornitore, in un posto solo.

Prima la stessa domanda aveva tre risposte che non si parlavano:

- l'anagrafica ERP (`fornitori.esclude_magazzino`), che la pagina Fornitori
  mostrava ma che il ponte fatture -> Lotti **non leggeva mai**;
- un campo legacy `inventory_enabled` (0 righe su 198) che, assente,
  faceva risultare **escluso** ogni fornitore che non avesse il flag: 197 su
  198 apparivano «Escluso magazzino» senza che nessuno l'avesse deciso;
- le decisioni di Lotti (`fornitori.escluso` e `fornitori_decisioni`), per
  nome, che sono quelle che davvero fermano l'import (88 fornitori su 180).

Ora la scelta **canonica** e' `fornitori.esclude_magazzino` dell'anagrafica
ERP, per P.IVA, con motivo, data, chi e storico. Lotti ne riceve una
**proiezione** (`imposta_esclusione`: la usano il gestionale e gli endpoint di Lotti) e il ponte legge
per prima l'anagrafica. Dove l'anagrafica non ha mai deciso, vale la decisione
gia' presa in Lotti (`origine = "lotti"`); se non ha deciso nessuno il
fornitore e' incluso e la scheda lo dice («non deciso»). `inventory_enabled`
non si legge piu' (migrazione: nessun documento lo aveva).

Escludere o includere non cancella niente: le fatture restano contabili
(IVA, giornale, pagamenti), i lotti e gli articoli gia' creati restano dove
sono; cambia solo se le fatture NUOVE entrano in Lotti. Includere accoda le
fatture ancora da prendere, con lo stesso import idempotente di sempre.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Chip della scheda (le mani sporche: si sceglie, non si scrive). L'ultimo e'
# sempre l'eccezione «Altro (scrivi tu)».
MOTIVI_ESCLUSIONE: Tuple[Tuple[str, str], ...] = (
    ("servizi_utenze", "Servizi, utenze o noleggi (niente merce)"),
    ("non_alimentare", "Merce non alimentare"),
    ("consumo_diretto", "Consumo diretto, non passa dal magazzino"),
    ("occasionale", "Acquisto occasionale"),
    ("altro", "Altro (scrivi tu)"),
)
MOTIVI_INCLUSIONE: Tuple[Tuple[str, str], ...] = (
    ("merce_alimentare", "Vende merce alimentare o bevande"),
    ("tracciabilita", "Serve la tracciabilita' dei lotti"),
    ("escluso_per_errore", "Era escluso per errore"),
    ("altro", "Altro (scrivi tu)"),
)
# Motivi scritti dal sistema, non scelti dal titolare.
MOTIVO_DA_LOTTI = "decisione_in_lotti"
MOTIVO_ALLINEAMENTO = "allineamento_da_lotti"
MOTIVO_MODIFICA_SCHEDA = "modifica_scheda"

_ETICHETTE = {**dict(MOTIVI_ESCLUSIONE), **dict(MOTIVI_INCLUSIONE),
              MOTIVO_DA_LOTTI: "Scelta fatta dentro Lotti",
              MOTIVO_ALLINEAMENTO: "Allineato alla decisione gia' presa in Lotti",
              MOTIVO_MODIFICA_SCHEDA: "Modifica dalla scheda fornitore"}


def normalizza_piva(valore: Any) -> str:
    """P.IVA senza spazi, maiuscola, senza prefisso IT: la stessa chiave ovunque."""
    testo = re.sub(r"\s+", "", str(valore or "")).upper()
    if testo.startswith("IT") and len(testo) > 2:
        testo = testo[2:]
    return testo


def chiave_nome(valore: Any) -> str:
    """Nome confrontabile: minuscolo, senza virgolette, spazi collassati, senza punto finale."""
    n = str(valore or "").strip().strip('"').strip("'").strip().lower()
    return re.sub(r"\s+", " ", n).rstrip(".")


def _piva_di(fornitore: Dict[str, Any]) -> str:
    for campo in ("partita_iva", "piva", "vat_number", "vat"):
        v = normalizza_piva(fornitore.get(campo))
        if v:
            return v
    return ""


def _nome_di(fornitore: Dict[str, Any]) -> str:
    return str(
        fornitore.get("ragione_sociale") or fornitore.get("denominazione")
        or fornitore.get("nome") or fornitore.get("name") or ""
    ).strip()


def etichetta_motivo(motivo: str, testo: str = "") -> str:
    if motivo == "altro":
        return (testo or "").strip() or _ETICHETTE["altro"]
    return _ETICHETTE.get(motivo, motivo)


def valida_motivo(escludi: bool, motivo: str, testo: str = "") -> Tuple[str, str]:
    """Il motivo deve essere uno dei chip; «altro» richiede il testo."""
    motivo = str(motivo or "").strip()
    ammessi = {m for m, _ in (MOTIVI_ESCLUSIONE if escludi else MOTIVI_INCLUSIONE)}
    if motivo not in ammessi:
        raise ValueError("Motivo non valido: scegli una delle opzioni proposte")
    testo = str(testo or "").strip()[:200]
    if motivo == "altro" and not testo:
        raise ValueError("Con «Altro» scrivi il motivo")
    return motivo, testo


class DecisioniMagazzino:
    """Le decisioni lette una volta sola, per rispondere per ogni fornitore o fattura."""

    def __init__(self) -> None:
        self.erp_per_piva: Dict[str, bool] = {}
        self.erp_per_nome: Dict[str, bool] = {}
        self.lotti_per_nome: Dict[str, Tuple[bool, str]] = {}
        self.lotti_per_piva: Dict[str, bool] = {}

    def carica_erp(self, fornitori: Iterable[Dict[str, Any]]) -> "DecisioniMagazzino":
        for f in fornitori:
            valore = f.get("esclude_magazzino")
            if not isinstance(valore, bool):
                continue  # non deciso: nessuna risposta inventata
            piva = _piva_di(f)
            if piva:
                self.erp_per_piva[piva] = valore
            nome = chiave_nome(_nome_di(f))
            if nome:
                self.erp_per_nome.setdefault(nome, valore)
        return self

    def carica_lotti(self, fornitori: Iterable[Dict[str, Any]]) -> "DecisioniMagazzino":
        for f in fornitori:
            if not isinstance(f.get("escluso"), bool):
                continue
            piva = _piva_di(f)
            nome = chiave_nome(f.get("nome") or _nome_di(f))
            if nome:
                self.lotti_per_nome[nome] = (f["escluso"], piva)
            if piva:
                self.lotti_per_piva[piva] = f["escluso"]
        return self

    def stato(self, piva: Any = "", nome: Any = "") -> Tuple[Optional[bool], str]:
        """(escluso, origine): origine e' `erp`, `lotti` o `non_deciso`.

        Prima l'anagrafica ERP per P.IVA, poi la stessa per nome, poi Lotti per
        P.IVA e per nome. Un nome uguale con P.IVA diversa non eredita mai: due
        aziende omonime restano due decisioni."""
        p, n = normalizza_piva(piva), chiave_nome(nome)
        if p and p in self.erp_per_piva:
            return self.erp_per_piva[p], "erp"
        if not p and n in self.erp_per_nome:
            return self.erp_per_nome[n], "erp"
        if p and p in self.lotti_per_piva:
            return self.lotti_per_piva[p], "lotti"
        if n in self.lotti_per_nome:
            escluso_lotti, piva_lotti = self.lotti_per_nome[n]
            # stesso nome ma P.IVA diversa = un'altra azienda: non eredita
            if not p or not piva_lotti or piva_lotti == p:
                return escluso_lotti, "lotti"
        return None, "non_deciso"

    def escluso(self, piva: Any = "", nome: Any = "") -> bool:
        return bool(self.stato(piva, nome)[0])


async def carica_decisioni(db=None, db_lotti=None) -> DecisioniMagazzino:
    """Legge anagrafica ERP e decisioni di Lotti (una lettura leggera ciascuna).

    Lotti installato da solo (senza l'ERP nello stesso processo) resta con le sole
    sue decisioni: si dice nel log, non si finge un'anagrafica."""
    from app.database import Collections

    decisioni = DecisioniMagazzino()
    try:
        if db is None:
            from app.database import Database

            db = Database.get_db()
        fornitori = await db[Collections.SUPPLIERS].find(
            {}, {"_id": 0, "partita_iva": 1, "piva": 1, "vat_number": 1, "vat": 1,
                 "ragione_sociale": 1, "denominazione": 1, "nome": 1, "name": 1,
                 "esclude_magazzino": 1},
        ).to_list(5000)
        decisioni.carica_erp(fornitori)
    except Exception as exc:  # noqa: BLE001 - senza ERP valgono le decisioni di Lotti
        logger.warning("[magazzino_fornitore] anagrafica ERP non letta: %s: %s",
                       type(exc).__name__, exc)
    try:
        if db_lotti is None:
            from app.lotti.db import database as db_lotti

        righe = await db_lotti.fornitori.find(
            {}, {"_id": 0, "nome": 1, "piva": 1, "escluso": 1}).to_list(5000)
        decisioni.carica_lotti(righe)
    except Exception as exc:  # noqa: BLE001 - senza Lotti resta l'anagrafica, ma si dice
        logger.warning("[magazzino_fornitore] decisioni di Lotti non lette: %s: %s",
                       type(exc).__name__, exc)
    return decisioni


def vista_scheda(fornitore: Dict[str, Any], decisioni: DecisioniMagazzino) -> Dict[str, Any]:
    """Campi da mostrare sulla scheda: stato effettivo, origine, motivo, chi e quando."""
    escluso, origine = decisioni.stato(_piva_di(fornitore), _nome_di(fornitore))
    motivo = fornitore.get("magazzino_motivo") or ""
    return {
        "esclude_magazzino": bool(escluso),
        "magazzino_origine": origine,
        "magazzino_motivo": motivo,
        "magazzino_motivo_testo": (
            etichetta_motivo(motivo, fornitore.get("magazzino_motivo_testo") or "") if motivo else ""),
        "magazzino_deciso_il": fornitore.get("magazzino_deciso_il") or "",
        "magazzino_deciso_da": fornitore.get("magazzino_deciso_da") or "",
    }


def _varianti_piva(piva: str) -> List[str]:
    base = normalizza_piva(piva)
    return [base, f"IT{base}"] if base else []


async def _fatture_erp_fornitore(db, piva: str) -> List[Dict[str, Any]]:
    from app.database import Collections
    from app.services.fattura_attiva import FILTRO_FATTURA_ATTIVA

    varianti = _varianti_piva(piva)
    if not varianti:
        return []
    return await db[Collections.INVOICES].find(
        {"$and": [FILTRO_FATTURA_ATTIVA, {"$or": [
            {"supplier_vat": {"$in": varianti}},
            {"cedente_piva": {"$in": varianti}},
            {"fornitore_partita_iva": {"$in": varianti}},
        ]}]},
        {"_id": 0, "id": 1, "invoice_date": 1},
    ).to_list(20000)


async def anteprima(db, fornitore: Dict[str, Any], escludi: bool) -> Dict[str, Any]:
    """Cosa succede se lo escludi / lo includi, coi numeri veri, senza scrivere."""
    from app.lotti.db import database as db_lotti
    from app.lotti.routers.gestionale_fatture import fatture_da_prendere_fornitore

    piva, nome = _piva_di(fornitore), _nome_di(fornitore)
    fatture = await _fatture_erp_fornitore(db, piva)
    decisioni = await carica_decisioni(db)
    escluso_ora, origine = decisioni.stato(piva, nome)

    varianti = _varianti_piva(piva)
    per_nome = ({"fornitore": {"$regex": f"^{re.escape(nome)}$", "$options": "i"}}
                if nome else None)
    condizioni = ([{"piva": {"$in": varianti}}] if varianti else []) + (
        [per_nome] if per_nome else [])
    fatture_lotti = (await db_lotti.fatture.count_documents({"$or": condizioni})
                     if condizioni else 0)
    lotti_creati = lotti_disponibili = 0
    if per_nome:
        righe = await db_lotti.lotti_fornitori.find(
            per_nome, {"_id": 0, "esaurito": 1, "quantita_disponibile": 1}).to_list(50000)
        lotti_creati = len(righe)
        lotti_disponibili = sum(
            1 for r in righe
            if not r.get("esaurito") and float(r.get("quantita_disponibile") or 0) > 0)
    da_prendere = await fatture_da_prendere_fornitore(piva, nome)
    inventario = 0
    if piva:
        inventario = await db["warehouse_inventory"].count_documents(
            {"$or": [{"supplier_piva": {"$in": varianti}}, {"fornitore_piva": {"$in": varianti}}]})

    if escludi:
        effetto = [
            f"Le {len(fatture)} fatture restano contabili: IVA, giornale e pagamenti non cambiano.",
            "Le nuove fatture non entrano piu' in Lotti.",
        ]
        if fatture_lotti or lotti_creati:
            effetto.append(
                f"{fatture_lotti} fatture gia' in Lotti e {lotti_creati} lotti "
                f"({lotti_disponibili} con giacenza) restano dove sono: non si cancella niente.")
        if inventario:
            effetto.append(f"{inventario} righe di inventario del gestionale restano.")
    else:
        effetto = ["Le fatture nuove di questo fornitore tornano a entrare in Lotti."]
        if da_prendere:
            effetto.append(
                f"{len(da_prendere)} fatture ancora da prendere entrano in Lotti subito "
                "(quelle gia' presenti non si duplicano).")
        else:
            effetto.append("Non ci sono fatture in attesa: niente da importare adesso.")
    return {
        "escludi": escludi,
        "gia_cosi": (escluso_ora is not None and bool(escluso_ora) == escludi),
        "stato_attuale": {"esclude_magazzino": bool(escluso_ora), "origine": origine},
        "fatture_contabili": len(fatture),
        "fatture_in_lotti": fatture_lotti,
        "lotti_creati": lotti_creati,
        "lotti_con_giacenza": lotti_disponibili,
        "righe_inventario_erp": inventario,
        "fatture_da_prendere": len(da_prendere),
        "effetto": effetto,
        "motivi": [{"id": m, "etichetta": e}
                   for m, e in (MOTIVI_ESCLUSIONE if escludi else MOTIVI_INCLUSIONE)],
    }


async def _svuota_cache_lista() -> None:
    """La lista fornitori e' in cache: dopo una scelta (anche quella fatta in Lotti) si rilegge."""
    try:
        from app.middleware.performance import cache
        from app.routers.suppliers_module.common import SUPPLIERS_CACHE_KEY

        await cache.clear_pattern(SUPPLIERS_CACHE_KEY)
    except Exception as exc:  # noqa: BLE001 - al peggio la lista si aggiorna alla scadenza
        logger.warning("[magazzino_fornitore] cache fornitori non svuotata: %s: %s",
                       type(exc).__name__, exc)


def _voce_storico(escluso: bool, motivo: str, testo: str, da: str, origine: str,
                  ora: str, effetto: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    voce = {"escluso": escluso, "motivo": motivo,
            "motivo_testo": etichetta_motivo(motivo, testo),
            "il": ora, "da": da, "origine": origine}
    if effetto:
        voce["effetto"] = effetto
    return voce


def _filtro_id(fornitore: Dict[str, Any]) -> Dict[str, Any]:
    """Filtro per id del documento: mai per P.IVA, mai su piu' righe."""
    valore = fornitore.get("id")
    if valore is None:
        raise ValueError("Fornitore senza id: impossibile aggiornarlo per id")
    return {"id": valore}


async def applica(db, fornitore: Dict[str, Any], escludi: bool, motivo: str,
                  motivo_testo: str = "", utente: str = "", origine: str = "erp"
                  ) -> Dict[str, Any]:
    """Scrive la decisione (anagrafica, storico, proiezione su Lotti) e, se includi,
    accoda le fatture ancora da prendere. Non cancella niente."""
    from app.database import Collections

    if motivo not in (MOTIVO_DA_LOTTI, MOTIVO_ALLINEAMENTO, MOTIVO_MODIFICA_SCHEDA):
        motivo, motivo_testo = valida_motivo(escludi, motivo, motivo_testo)
    ora = datetime.now(timezone.utc).isoformat()
    piva, nome = _piva_di(fornitore), _nome_di(fornitore)

    da_prendere: List[str] = []
    if not escludi:
        from app.lotti.routers.gestionale_fatture import fatture_da_prendere_fornitore

        da_prendere = await fatture_da_prendere_fornitore(piva, nome)
    effetto = {"fatture_da_prendere": len(da_prendere)} if not escludi else {}

    await db[Collections.SUPPLIERS].update_one(
        _filtro_id(fornitore),
        {"$set": {
            "esclude_magazzino": escludi,
            "magazzino_motivo": motivo,
            "magazzino_motivo_testo": motivo_testo,
            "magazzino_deciso_il": ora,
            "magazzino_deciso_da": utente,
            "updated_at": ora,
        }, "$push": {"storico_magazzino": _voce_storico(
            escludi, motivo, motivo_testo, utente, origine, ora, effetto)}},
    )

    proiezione = {"scritta": False}
    if origine != "lotti":  # se la scelta arriva da Lotti, Lotti l'ha gia' scritta
        try:
            from app.lotti.routers.fornitori import imposta_esclusione, _CACHE_FORNITORI

            await imposta_esclusione(nome, escludi, piva)
            _CACHE_FORNITORI["dati"] = None
            proiezione = {"scritta": True}
        except Exception as exc:  # noqa: BLE001
            logger.warning("[magazzino_fornitore] proiezione su Lotti non scritta per %s: %s: %s",
                           nome, type(exc).__name__, exc)
            proiezione = {"scritta": False, "errore": type(exc).__name__}

    accodate = 0
    if da_prendere:
        from app.services.handlers.fattura_handlers import accoda_alimentazione_lotti

        accodate = accoda_alimentazione_lotti(da_prendere)

    await _svuota_cache_lista()
    return {"esclude_magazzino": escludi, "fatture_accodate_a_lotti": accodate,
            "proiezione_lotti": proiezione, "deciso_il": ora}


async def registra_decisione_da_lotti(nome: str, piva: str, escluso: bool) -> Optional[Dict[str, Any]]:
    """Una scelta fatta dentro Lotti arriva nell'anagrafica ERP, se il fornitore c'e'
    (P.IVA, altrimenti nome univoco). Lotti l'ha gia' scritta: qui solo il canonico."""
    from app.database import Database, Collections

    db = Database.get_db()
    trovato = await trova_fornitore(db, piva, nome)
    if trovato is None:
        return None
    if trovato.get("esclude_magazzino") is escluso:
        return None
    return await applica(db, trovato, escluso, MOTIVO_DA_LOTTI, "", "Lotti", origine="lotti")


async def trova_fornitore(db, piva: str, nome: str) -> Optional[Dict[str, Any]]:
    """Il fornitore ERP per P.IVA; senza P.IVA, per nome solo se univoco."""
    from app.database import Collections

    varianti = _varianti_piva(piva)
    if varianti:
        righe = await db[Collections.SUPPLIERS].find(
            {"$or": [{"partita_iva": {"$in": varianti}}, {"piva": {"$in": varianti}},
                     {"vat_number": {"$in": varianti}}]}, {"_id": 0}).to_list(5)
        if len(righe) == 1:
            return righe[0]
        if righe:
            return None  # due anagrafiche con la stessa P.IVA: non si sceglie a caso
    chiave = chiave_nome(nome)
    if not chiave:
        return None
    tutte = await db[Collections.SUPPLIERS].find({}, {"_id": 0}).to_list(5000)
    uguali = [f for f in tutte if chiave_nome(_nome_di(f)) == chiave
              and not (piva and _piva_di(f) and _piva_di(f) != normalizza_piva(piva))]
    return uguali[0] if len(uguali) == 1 else None


async def allinea_da_lotti(db, dry_run: bool = True) -> Dict[str, Any]:
    """Migrazione dichiarata: dove l'anagrafica non ha mai deciso e Lotti si',
    la decisione di Lotti diventa quella canonica. Per id, mai per filtro.
    Non tocca chi ha gia' una scelta ERP e non decide nulla per gli omonimi."""
    from app.database import Collections

    decisioni = DecisioniMagazzino()
    fornitori = await db[Collections.SUPPLIERS].find({}, {"_id": 0}).to_list(5000)
    try:
        from app.lotti.db import database as db_lotti

        decisioni.carica_lotti(await db_lotti.fornitori.find(
            {}, {"_id": 0, "nome": 1, "piva": 1, "escluso": 1}).to_list(5000))
    except Exception as exc:  # noqa: BLE001
        return {"dry_run": dry_run, "errore": f"Lotti non leggibile: {type(exc).__name__}",
                "da_allineare": 0, "dettaglio": []}
    esito: Dict[str, Any] = {
        "dry_run": dry_run, "fornitori": len(fornitori), "gia_decisi_in_erp": 0,
        "senza_decisione_lotti": 0, "da_allineare": 0, "allineati": 0,
        "esclusi": 0, "inclusi": 0, "dettaglio": [],
    }
    ora = datetime.now(timezone.utc).isoformat()
    for f in fornitori:
        if isinstance(f.get("esclude_magazzino"), bool):
            esito["gia_decisi_in_erp"] += 1
            continue
        escluso, origine = decisioni.stato(_piva_di(f), _nome_di(f))
        if escluso is None:
            esito["senza_decisione_lotti"] += 1
            continue
        esito["da_allineare"] += 1
        esito["esclusi" if escluso else "inclusi"] += 1
        if len(esito["dettaglio"]) < 50:
            esito["dettaglio"].append({"fornitore": _nome_di(f), "partita_iva": _piva_di(f),
                                       "esclude_magazzino": escluso})
        if dry_run or f.get("id") is None:
            continue
        await db[Collections.SUPPLIERS].update_one(
            _filtro_id(f),
            {"$set": {"esclude_magazzino": escluso, "magazzino_motivo": MOTIVO_ALLINEAMENTO,
                      "magazzino_motivo_testo": "", "magazzino_deciso_il": ora,
                      "magazzino_deciso_da": "allineamento"},
             "$push": {"storico_magazzino": _voce_storico(
                 escluso, MOTIVO_ALLINEAMENTO, "", "allineamento", "allineamento", ora)}},
        )
        esito["allineati"] += 1
    return esito
