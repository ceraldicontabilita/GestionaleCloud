"""Proposte di collegamento modello F24 → quietanza per tributo e periodo.

Un modello senza protocollo non si aggancia alla sua quietanza per protocollo, e se e' stato pagato con
ravvedimento nemmeno per importo (sanzioni e interessi cambiano il saldo). Qui si cerca la quietanza
dalle **righe**: stesso codice tributo e stesso periodo di riferimento, importo qualsiasi.

* Sola lettura: `proponi_quietanze` calcola i candidati e la differenza di importo di ogni riga;
* niente si scrive da soli: il collegamento lo conferma il titolare (`conferma_collegamento_quietanza`),
  che sceglie **fra i candidati proposti** (un'altra quietanza e' 409) con un motivo a chip;
* il collegamento non prova la banca: e' lo stesso `patch_quietanza_associata` di sempre
  (`DA_VERIFICARE_BANCA`), l'addebito resta al motore F24 ↔ banca.

Mai per solo importo: senza almeno una riga con lo stesso codice e periodo non c'e' candidato.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.db_collections import COLL_F24
from app.services import f24_controllo_incrociato as reg
from app.services.f24_payment_evidence import patch_quietanza_associata

GIORNI_PRIMA = 10      # una quietanza non precede di molto il modello
GIORNI_DOPO = 540      # un ravvedimento puo' arrivare mesi dopo la scadenza
MAX_CANDIDATI = 5

MOTIVI_COLLEGAMENTO: Dict[str, str] = {
    "ravvedimento_stesso_tributo": "Ravvedimento: stesso tributo e periodo, l'importo cambia per sanzioni e interessi",
    "pagato_in_piu_quietanze": "Pagamento spezzato in più quietanze: questa copre parte delle righe",
    "verificato_cassetto_fiscale": "Verificato sul Cassetto fiscale: la delega pagata è questa",
    "stesse_righe_altra_data": "Sono le stesse righe, pagate in una data diversa dal modello",
    "altro": "Altro (scrivi tu)",
}


class CollegamentoNonAmmesso(Exception):
    """Il collegamento non si applica: `code` e `details` dicono perche'."""

    def __init__(self, code: str, message: str, details: Optional[Dict[str, Any]] = None, stato: int = 409):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.stato = stato


Chiave = Tuple[str, Optional[int], Optional[int]]


def _chiave(riga: Dict[str, Any]) -> Chiave:
    return (riga["codice"], riga.get("anno"), riga.get("mese"))


def _a_debito(righe: List[Dict[str, Any]]) -> Dict[Chiave, int]:
    """Debito per (codice, anno, mese): piu' righe uguali (es. 3847 due volte) si sommano."""
    somme: Dict[Chiave, int] = {}
    for r in righe:
        if (r.get("importo_debito_cents") or 0) > 0:
            somme[_chiave(r)] = somme.get(_chiave(r), 0) + int(r["importo_debito_cents"])
    return somme


def _giorni(da: Optional[str], a: Optional[str]) -> Optional[int]:
    try:
        return (date.fromisoformat(str(a)[:10]) - date.fromisoformat(str(da)[:10])).days
    except (TypeError, ValueError):
        return None


def _riga_vista(chiave: Chiave, modello: int, quietanza: Optional[int]) -> Dict[str, Any]:
    codice, anno, mese = chiave
    return {
        "codice": codice, "periodo": reg._periodo(anno, mese),
        "importo_modello_cents": modello, "importo_quietanza_cents": quietanza,
        "differenza_cents": (quietanza - modello) if quietanza is not None else None,
    }


def proponi_quietanze(f24: Dict[str, Any], registro: Dict[str, Any]) -> Dict[str, Any]:
    """Quietanze che pagano righe del modello per codice e periodo. Sola lettura."""
    fid = str(f24.get("id"))
    righe_modello = _a_debito(reg.righe_modello(f24))
    data_modello = reg.data_versamento_modello(f24)
    gia = {str(q.get("id")) for q in registro["quietanze_per_f24"].get(fid, [])}
    candidati: List[Dict[str, Any]] = []
    if righe_modello:
        for q in registro["quietanze"]:
            qid = str(q.get("id"))
            if not q.get("righe") or qid in gia:
                continue
            giorni = _giorni(data_modello, q.get("data"))
            if giorni is not None and not (-GIORNI_PRIMA <= giorni <= GIORNI_DOPO):
                continue
            righe_q = _a_debito(q["righe"])
            comuni = [k for k in righe_modello if k in righe_q]
            # Una sola riga in comune basta solo se il modello ne ha pochissime: codici come 3847 o 3802
            # ricorrono nello stesso periodo in molte deleghe e un aggancio a una riga sola sarebbe rumore.
            if not comuni or (len(comuni) < 2 and len(righe_modello) > 2):
                continue
            righe_vista = [_riga_vista(k, righe_modello[k], righe_q[k]) for k in sorted(comuni, key=str)]
            mancanti = [_riga_vista(k, righe_modello[k], None) for k in sorted(righe_modello, key=str)
                        if k not in righe_q]
            identiche = all(r["differenza_cents"] == 0 for r in righe_vista)
            altro_modello = [x for x in q.get("f24_ids") or [] if str(x) != fid]
            candidati.append({
                "quietanza_id": q.get("id"), "fonte": q.get("fonte"),
                "filename": q.get("filename"), "data": q.get("data"),
                "protocollo": q.get("protocollo_originale") or q.get("protocollo"),
                "saldo_cents": q.get("importo_cents"),
                "giorni_dal_modello": giorni,
                "pdf_url": reg.url_pdf_quietanza(q),
                "righe_corrispondenti": righe_vista, "righe_non_trovate": mancanti,
                "copertura": f"{len(comuni)}/{len(righe_modello)}",
                "tutte_identiche": identiche and not mancanti,
                "differenza_totale_cents": sum(r["differenza_cents"] for r in righe_vista),
                "collegata_ad_altro_modello": altro_modello,
            })
    candidati.sort(key=lambda c: (
        bool(c["collegata_ad_altro_modello"]), -len(c["righe_corrispondenti"]),
        sum(abs(r["differenza_cents"]) for r in c["righe_corrispondenti"]),
        abs(c["giorni_dal_modello"] if c["giorni_dal_modello"] is not None else 9999),
    ))
    return {
        "f24_id": fid, "data_modello": data_modello, "saldo_modello_cents": reg.saldo_modello_cents(f24),
        "righe_modello": len(righe_modello),
        "livello": "TRIBUTO_E_PERIODO",
        "candidati": candidati[:MAX_CANDIDATI],
        "motivi": dict(MOTIVI_COLLEGAMENTO),
    }


async def proposte_per_modello(db, f24_id: str) -> Dict[str, Any]:
    registro = await reg.carica_registro(db)
    f24 = next((f for f in registro["f24"] if str(f.get("id")) == str(f24_id)), None)
    if f24 is None:
        raise CollegamentoNonAmmesso("MODELLO_NON_TROVATO", "Modello F24 non trovato o non attivo",
                                     {"f24_id": f24_id}, stato=404)
    esito = proponi_quietanze(f24, registro)
    esito["file_name"] = f24.get("file_name") or f24.get("filename")
    esito["gia_collegato"] = bool(registro["quietanze_per_f24"].get(str(f24_id)))
    return esito


async def conferma_collegamento_quietanza(
    db, *, f24_id: str, quietanza_id: str, motivo: str, motivo_testo: Optional[str] = None,
    utente: Optional[str] = None,
) -> Dict[str, Any]:
    """Il titolare collega il modello alla quietanza scelta fra i candidati per codice e periodo."""
    motivo = str(motivo or "").strip()
    if motivo not in MOTIVI_COLLEGAMENTO:
        raise CollegamentoNonAmmesso("MOTIVO_NON_AMMESSO", "Motivo non in elenco",
                                     {"motivi": list(MOTIVI_COLLEGAMENTO)}, stato=422)
    testo_motivo = MOTIVI_COLLEGAMENTO[motivo]
    if motivo == "altro":
        testo_motivo = str(motivo_testo or "").strip()
        if len(testo_motivo) < 3:
            raise CollegamentoNonAmmesso("MOTIVO_TESTO_OBBLIGATORIO", "«Altro» richiede il testo del motivo",
                                         stato=422)
    f24_id, quietanza_id = str(f24_id), str(quietanza_id)
    proposta = await proposte_per_modello(db, f24_id)
    if proposta["gia_collegato"]:
        raise CollegamentoNonAmmesso("MODELLO_GIA_COLLEGATO", "Il modello ha gia' una quietanza collegata",
                                     {"f24_id": f24_id})
    scelto = next((c for c in proposta["candidati"] if str(c["quietanza_id"]) == quietanza_id), None)
    if scelto is None:
        raise CollegamentoNonAmmesso(
            "QUIETANZA_NON_CANDIDATA", "La quietanza non e' fra i candidati proposti per questo modello",
            {"f24_id": f24_id, "quietanza_id": quietanza_id,
             "candidati": [c["quietanza_id"] for c in proposta["candidati"]]})
    if scelto["collegata_ad_altro_modello"]:
        raise CollegamentoNonAmmesso(
            "QUIETANZA_GIA_COLLEGATA", "La quietanza e' gia' collegata a un altro modello",
            {"quietanza_id": quietanza_id, "modelli": scelto["collegata_ad_altro_modello"]})

    ora = datetime.now(timezone.utc).isoformat()
    patch = patch_quietanza_associata(
        quietanza_id=quietanza_id, protocollo=scelto["protocollo"] or "", data_quietanza=scelto["data"])
    patch["collegamento_quietanza_titolare"] = {
        "livello": proposta["livello"], "motivo": motivo, "motivo_testo": testo_motivo,
        "confermato_da": utente, "confermato_il": ora,
        "righe": scelto["righe_corrispondenti"], "righe_non_trovate": scelto["righe_non_trovate"],
        "differenza_totale_cents": scelto["differenza_totale_cents"],
    }
    patch["updated_at"] = ora
    await db[COLL_F24].update_one({"id": f24_id}, {"$set": patch})
    # La quietanza conosce il suo modello: stessa indicizzazione che usa gia' il registro.
    if scelto.get("fonte"):
        await db[scelto["fonte"]].update_one({"id": quietanza_id}, {"$addToSet": {"f24_associati": f24_id}})
    return {"collegato": True, "f24_id": f24_id, "quietanza_id": quietanza_id,
            "protocollo": scelto["protocollo"], "differenza_totale_cents": scelto["differenza_totale_cents"],
            "righe": scelto["righe_corrispondenti"]}
