"""Incroci fiscali del minisito: LIPE ↔ F24, IRAP ↔ 3800, IVA annuale ↔ 6099, 54-bis.

Un motore solo, in sola lettura, che rifà quello che il pacchetto del
titolare (`tests/fiscale/golden_minisito/manifest_final.json`) calcolava a
mano: per ogni mese con una LIPE canonica quanto era dovuto e quanto risulta
versato con i codici 6001–6012; per ogni anno d'imposta il saldo IRAP del
rigo IR26 contro il codice 3800 e il saldo IVA del rigo VX1 contro il 6099;
per ogni comunicazione di irregolarità (art. 54-bis) se i suoi codici sono
stati versati. Gli alert li scrive solo `applica_alert`, tramite
`alert_engine.genera_alert` (idempotente): un alert la cui condizione non
vale più al giro successivo viene chiuso col motivo.

Le regole, nell'ordine in cui contano:

* **la LIPE comanda**: entra solo un periodo con `quadratura_ok` e non
  sostituito da una ritrasmissione; a credito il dovuto è zero. Un periodo
  senza VP14 letto non è «zero», è «non determinabile»: nessun alert;
* **un versamento si conta una volta**: le quietanze prima (una per
  protocollo e saldo), i modelli del commercialista solo quando nessuna
  quietanza con righe li copre (stesso protocollo, aggancio esplicito o
  stessa data e saldo, com'è già in `prove_modello`). Fuori i modelli
  annullati, stornati o in quarantena e ogni documento il cui saldo non
  quadra (`validazione.saldo_quadrato` falso): finiscono in `guardia`;
* **l'anno sta sulla riga** del tributo, mai sul documento: un F24 IVA di
  gennaio 2025 pagato a marzo resta di gennaio 2025; il mese dell'IVA
  mensile è nel codice (6001 = gennaio);
* **soglia 1,00 €**: sotto è OK. Sopra: MANCANTE (niente versato), PARZIALE
  o ECCEDENTE (versato oltre il dovuto: ravvedimento, o un periodo imputato
  male). Solo MANCANTE e PARZIALE aprono un alert;
* **gli indizi non sono alert**: `POSSIBILE_ERRORE_PERIODO_IMPUTAZIONE` e
  `POSSIBILE_COMPENSAZIONE_6099` (±3,00 €, `indizi_riga_mancante`) dicono
  dove guardare prima di dire «non pagato» e restano in `hints`.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from app.constants.canale_documento import (
    STATO_ALERT_APERTO, STATO_ALERT_IGNORATO, STATO_LIPE_SOSTITUITA,
)
from app.constants.codici_ravvedimento import CODICI_RAVVEDIMENTO
from app.db_collections import COLL_FISCAL_DOCUMENTS, COLL_FISCAL_PAGES
from app.services import f24_controllo_incrociato as reg
from app.services import lipe_deposito
from app.services.alert_engine import COLL_ALERTS

logger = logging.getLogger(__name__)

__all__ = [
    "COLL_LIPE",
    "SOGLIA_CENTS",
    "STATO_OK", "STATO_MANCANTE", "STATO_PARZIALE", "STATO_ECCEDENTE", "STATO_NON_DETERMINABILE",
    "ALERT_IVA_MENSILE", "ALERT_IRAP", "ALERT_IVA_ANNUALE", "ALERT_54BIS", "CODICI_ALERT",
    "confronta_importi",
    "versamenti_dal_registro",
    "incroci",
    "applica_alert",
    "esegui_incroci",
]

COLL_LIPE = lipe_deposito.COLL_LIPE

#: Sotto 1,00 € dovuto e versato sono lo stesso numero (soglia del cruscotto
#: fiscale del titolare, PIANO §7-bis F).
SOGLIA_CENTS = 100
#: Giorni dalla notifica per pagare una comunicazione 54-bis con la sanzione
#: ridotta a un terzo (art. 2, c. 2, D.Lgs. 462/1997).
GIORNI_PAGAMENTO_54BIS = 30
#: Finestra entro cui un versamento di pari importo dopo l'elaborazione vale
#: come candidato (60 giorni del pagamento ridotto piu' margine di notifica).
GIORNI_FINESTRA_CANDIDATI = 120

STATO_OK = "OK"
STATO_MANCANTE = "MANCANTE"
STATO_PARZIALE = "PARZIALE"
STATO_ECCEDENTE = "ECCEDENTE"
STATO_NON_DETERMINABILE = "NON_DETERMINABILE"
STATI_DA_SEGNALARE = (STATO_MANCANTE, STATO_PARZIALE)

CODICE_IRAP_SALDO = "3800"
CODICE_IVA_ANNUALE = "6099"
#: Stati di un modello F24 che non e' (piu') un versamento.
STATI_F24_ESCLUSI = ("annullato", "stornato", "eliminato")
TIPI_54BIS = ("COMUNICAZIONE_IRREGOLARITA", "AVVISO_BONARIO")

ALERT_IVA_MENSILE = "IVA_PAGAMENTO_MANCANTE_O_PARZIALE"
ALERT_IRAP = "IRAP_SALDO_MANCANTE_O_PARZIALE"
ALERT_IVA_ANNUALE = "IVA_ANNUALE_SALDO_DA_VERIFICARE"
ALERT_54BIS = "COMUNICAZIONE_54BIS_NON_PAGATA"
CODICI_ALERT = (ALERT_IVA_MENSILE, ALERT_IRAP, ALERT_IVA_ANNUALE, ALERT_54BIS)

MESI = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", "Luglio",
        "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]


# ── aritmetica ───────────────────────────────────────────────────────────────

def _cents(valore: Any) -> Optional[int]:
    """Centesimi, dove uno zero e' un importo letto (`reg.centesimi` lo
    confonde con l'assenza: `0.0 == False`)."""
    if valore is None or valore == "":
        return None
    if isinstance(valore, bool):
        return None
    if isinstance(valore, (int, float, Decimal)) and valore == 0:
        return 0
    return reg.centesimi(valore)


def _euro(cents: Optional[int]) -> Optional[float]:
    return reg.euro(cents)


def _euro_it(cents: int) -> str:
    return f"{Decimal(cents) / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def confronta_importi(dovuto_cents: Optional[int], versato_cents: int) -> Dict[str, Any]:
    """Stato del confronto dovuto ↔ versato con la soglia di 1,00 €. Funzione pura."""
    if dovuto_cents is None:
        return {"stato": STATO_NON_DETERMINABILE, "differenza_cents": None, "mancante_cents": None}
    differenza = versato_cents - dovuto_cents
    if abs(differenza) <= SOGLIA_CENTS:
        stato = STATO_OK
    elif differenza > 0:
        stato = STATO_ECCEDENTE
    elif versato_cents == 0:
        stato = STATO_MANCANTE
    else:
        stato = STATO_PARZIALE
    return {
        "stato": stato,
        "differenza_cents": differenza,
        "mancante_cents": max(dovuto_cents - versato_cents, 0) if stato in STATI_DA_SEGNALARE else 0,
    }


def _mese_da_codice_iva(codice: str) -> Optional[int]:
    if len(codice) != 4 or not codice.startswith("60") or not codice[2:].isdigit():
        return None
    mese = int(codice[2:])
    return mese if 1 <= mese <= 12 else None


# ── versamenti: quietanze prima, modelli solo se scoperti ────────────────────

def _validato(doc: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    validazione = doc.get("validazione") or {}
    if validazione.get("saldo_quadrato") is False:
        return False, "saldo della delega non quadrato (validazione.saldo_quadrato falso)"
    return True, None


def versamenti_dal_registro(registro: Dict[str, Any]) -> Dict[str, Any]:
    """Un versamento per documento: le quietanze (una per protocollo e saldo),
    poi i modelli che nessuna quietanza con righe copre. Ogni riga tributo
    e' gia' normalizzata (`righe_modello`: codice, anno, mese, centesimi)."""
    versamenti: List[Dict[str, Any]] = []
    esclusi: List[Dict[str, Any]] = []
    visti: Set[Tuple[Any, ...]] = set()
    quietanze_con_righe: Dict[str, Dict[str, Any]] = {}
    protocolli_coperti: Set[str] = set()

    for q in registro["quietanze"]:
        if str(q.get("status") or "") in STATI_F24_ESCLUSI:
            esclusi.append({"id": q.get("id"), "filename": q.get("filename"), "fonte": q.get("fonte"),
                            "motivo": f"quietanza con status {q.get('status')}"})
            continue
        ok, motivo = _validato(q)
        if not ok:
            esclusi.append({"id": q.get("id"), "filename": q.get("filename"), "fonte": q.get("fonte"),
                            "motivo": motivo})
            continue
        righe = q.get("righe") or []
        # Una delega su piu' pagine ha lo stesso protocollo e, tutta in
        # compensazione, lo stesso saldo zero su ogni pagina: la copia e' solo
        # chi ripete anche le righe.
        chiave = (
            q.get("protocollo") or f"id:{q.get('id')}", q.get("importo_cents"),
            tuple(sorted((r["codice"], r["periodo_riferimento"], r["importo_debito_cents"], r["importo_credito_cents"])
                         for r in righe)),
        )
        if chiave in visti:
            esclusi.append({"id": q.get("id"), "filename": q.get("filename"), "fonte": q.get("fonte"),
                            "motivo": "stesso protocollo, stesso saldo e stesse righe di una quietanza gia' contata"})
            continue
        visti.add(chiave)
        if not righe:
            # Le quietanze in fiscal_documents portano data e saldo, non le
            # righe: si contano fra le fonti, non diventano righe inventate.
            continue
        if q.get("protocollo"):
            protocolli_coperti.add(q["protocollo"])
        quietanze_con_righe[str(q.get("id"))] = q
        versamenti.append({
            "fonte": q.get("fonte"), "id": q.get("id"), "filename": q.get("filename"),
            "protocollo": q.get("protocollo_originale"), "data_versamento": q.get("data"),
            "saldo_cents": q.get("importo_cents"), "righe": righe, "quietanza": True,
            "ravvedimento": any(r["codice"] in CODICI_RAVVEDIMENTO for r in righe),
            "documento": q.get("documento"),
        })

    for f24 in registro["f24"]:
        fid = str(f24.get("id"))
        nome = f24.get("file_name") or f24.get("filename")
        if str(f24.get("status") or "") in STATI_F24_ESCLUSI:
            esclusi.append({"id": fid, "filename": nome, "fonte": "f24_unificato",
                            "motivo": f"modello con status {f24.get('status')}"})
            continue
        ok, motivo = _validato(f24)
        if not ok:
            esclusi.append({"id": fid, "filename": nome, "fonte": "f24_unificato", "motivo": motivo})
            continue
        prove = reg.prove_modello(f24, registro)
        copre = [
            q["quietanza_id"] for q in prove["quietanze"]
            if str(q.get("quietanza_id")) in quietanze_con_righe
        ]
        if not copre and reg.protocolli_modello(f24) & protocolli_coperti:
            copre = sorted(reg.protocolli_modello(f24) & protocolli_coperti)
        if copre:
            esclusi.append({"id": fid, "filename": nome, "fonte": "f24_unificato",
                            "motivo": f"coperto dalla quietanza {copre[0]}: le righe si contano da lei"})
            continue
        righe = reg.righe_modello(f24)
        versamenti.append({
            "fonte": "f24_unificato", "id": fid, "filename": nome,
            "protocollo": next(iter(sorted(reg.protocolli_modello(f24))), None),
            "data_versamento": prove["data_versamento"], "saldo_cents": prove["saldo_modello_cents"],
            "righe": righe, "quietanza": False,
            "ravvedimento": any(r["codice"] in CODICI_RAVVEDIMENTO for r in righe),
            "documento": f24,
        })

    return {"versamenti": versamenti, "esclusi": esclusi}


def _righe_codice(versamenti: Iterable[Dict[str, Any]], codice: str, anno: int,
                  mese: Optional[int] = None) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """(versamento, riga) per codice e anno della riga; il mese solo se chiesto."""
    trovate = []
    for v in versamenti:
        for r in v["righe"]:
            if r["codice"] != codice or r["anno"] != anno:
                continue
            if mese is not None and r["mese"] is not None and r["mese"] != mese:
                continue
            trovate.append((v, r))
    return trovate


def _vista_versamento(v: Dict[str, Any], r: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "fonte": v["fonte"], "id": v["id"], "filename": v["filename"], "protocollo": v["protocollo"],
        "data_versamento": v["data_versamento"], "quietanza": v["quietanza"],
        "codice_tributo": r["codice"], "periodo": r["periodo_riferimento"],
        "importo": _euro(r["importo_debito_cents"]), "importo_credito": _euro(r["importo_credito_cents"]),
        "ravvedimento": v["ravvedimento"],
    }


def _somma_debito(coppie: Iterable[Tuple[Dict[str, Any], Dict[str, Any]]]) -> int:
    return sum(int(r["importo_debito_cents"] or 0) for _v, r in coppie)


# ── LIPE ─────────────────────────────────────────────────────────────────────

def _anno_mese(periodo: str) -> Optional[Tuple[int, int]]:
    try:
        anno, mese = str(periodo).split("-")[:2]
        anno_i, mese_i = int(anno), int(mese)
    except (TypeError, ValueError):
        return None
    return (anno_i, mese_i) if 1 <= mese_i <= 12 else None


async def _lipe_canoniche(db, anni: Optional[Set[int]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    canoniche: List[Dict[str, Any]] = []
    escluse: List[Dict[str, Any]] = []
    async for riga in db[COLL_LIPE].find({}, {"_id": 0}):
        am = _anno_mese(riga.get("periodo"))
        if not am:
            escluse.append({"periodo": riga.get("periodo"), "nome_file": riga.get("nome_file"),
                            "motivo": "periodo non riconoscibile"})
            continue
        if anni and am[0] not in anni:
            continue
        if riga.get("stato") == STATO_LIPE_SOSTITUITA:
            escluse.append({"periodo": riga["periodo"], "nome_file": riga.get("nome_file"),
                            "motivo": "sostituita da una ritrasmissione con protocollo piu' alto"})
            continue
        if riga.get("quadratura_ok") is not True:
            escluse.append({"periodo": riga["periodo"], "nome_file": riga.get("nome_file"),
                            "motivo": "l'aritmetica del quadro VP non torna (quadratura_ok non vero)"})
            continue
        canoniche.append(riga)
    canoniche.sort(key=lambda r: r["periodo"])
    return canoniche, escluse


def _dovuto_lipe(riga: Dict[str, Any]) -> Tuple[Optional[int], Optional[str]]:
    """VP14 a debito → dovuto; a credito → 0; non letto → None (mai zero per finta)."""
    valore = riga.get("iva_da_versare_o_credito")
    segno = riga.get("iva_da_versare_o_credito_segno")
    if valore is None:
        return None, "VP14 non letto nella LIPE"
    cents = _cents(valore)
    if cents is None:
        return None, f"VP14 illeggibile: {valore!r}"
    if segno == "credito":
        return 0, "LIPE a credito: nessun versamento dovuto"
    if cents == 0:
        return 0, "VP14 a zero"
    if segno != "debito":
        return None, "VP14 senza segno: non si sa se e' un debito o un credito"
    return cents, None


def _confronto_mese(riga: Dict[str, Any], versamenti: List[Dict[str, Any]],
                    registro_indizi: Dict[str, Any]) -> Dict[str, Any]:
    anno, mese = _anno_mese(riga["periodo"])
    codice = f"60{mese:02d}"
    dovuto_cents, nota = _dovuto_lipe(riga)
    coppie = _righe_codice(versamenti, codice, anno, mese)
    versato_cents = _somma_debito(coppie)
    esito = confronta_importi(dovuto_cents, versato_cents)
    hints: List[Dict[str, Any]] = []
    if esito["stato"] in STATI_DA_SEGNALARE and esito["mancante_cents"]:
        hints = reg.indizi_riga_mancante(
            codice, {"anno": anno, "mese": mese}, esito["mancante_cents"], registro_indizi,
        )
    return {
        "anno": anno, "mese": mese, "mese_nome": MESI[mese - 1], "periodo": riga["periodo"],
        "codice_tributo": codice,
        "lipe_id": riga.get("id") or riga["periodo"],
        "lipe_source": riga.get("nome_file"), "lipe_protocollo": riga.get("protocollo"),
        "segno_lipe": riga.get("iva_da_versare_o_credito_segno"),
        "dovuto_da_lipe": _euro(dovuto_cents), "versato_f24": _euro(versato_cents),
        "differenza": _euro(esito["differenza_cents"]), "mancante": _euro(esito["mancante_cents"]),
        "stato": esito["stato"], "nota": nota,
        "f24_versamenti": [_vista_versamento(v, r) for v, r in coppie],
        "f24_sources": sorted({v["filename"] for v, _r in coppie if v.get("filename")}),
        "ravvedimento_rilevato": any(v["ravvedimento"] for v, _r in coppie),
        "hints": hints,
    }


# ── dichiarazioni: IRAP e IVA annuale ────────────────────────────────────────

def _campo_quadro(doc: Dict[str, Any], nome: str) -> Tuple[Optional[int], Optional[str]]:
    """Il rigo letto per posizione: casella vuota = il modello non stampa gli
    zeri, quindi 0; rigo non trovato o ambiguo = non determinabile."""
    campo = ((doc.get("quadri") or {}).get("campi") or {}).get(nome) or {}
    valore = campo.get("valore")
    if valore is not None:
        try:
            return int((Decimal(str(valore)) * 100).quantize(Decimal("1"))), None
        except (InvalidOperation, ValueError):
            return None, f"{nome} illeggibile: {valore!r}"
    motivo = campo.get("motivo") or "rigo_non_trovato"
    if motivo == "casella_vuota":
        return 0, f"{nome} casella vuota: il modello non stampa gli zeri"
    return None, f"{nome} {motivo}"


def _scegli_per_anno(docs: Iterable[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    """Una dichiarazione per anno d'imposta: vince l'identificativo piu' alto
    (una ritrasmissione ne ha uno nuovo); le altre restano citate."""
    per_anno: Dict[int, List[Dict[str, Any]]] = {}
    for d in docs:
        anno = (d.get("quadri") or {}).get("anno_imposta")
        if isinstance(anno, int):
            per_anno.setdefault(anno, []).append(d)
    scelte: Dict[int, Dict[str, Any]] = {}
    for anno, elenco in per_anno.items():
        elenco.sort(key=lambda d: str((d.get("quadri") or {}).get("identificativo") or ""))
        scelto = dict(elenco[-1])
        scelto["_altre_dichiarazioni"] = [d.get("filename") for d in elenco[:-1]]
        scelte[anno] = scelto
    return scelte


def _riscontro_annuale(doc: Dict[str, Any], anno: int, rigo: str, codice: str,
                       versamenti: List[Dict[str, Any]]) -> Dict[str, Any]:
    dovuto_cents, nota = _campo_quadro(doc, rigo)
    coppie = _righe_codice(versamenti, codice, anno)
    versato_cents = _somma_debito(coppie)
    esito = confronta_importi(dovuto_cents, versato_cents)
    return {
        "anno_imposta": anno, "document_id": doc.get("id"), "dich_source": doc.get("filename"),
        "identificativo": (doc.get("quadri") or {}).get("identificativo"),
        "altre_dichiarazioni": doc.get("_altre_dichiarazioni") or [],
        "rigo": rigo, "codice_tributo": codice,
        "importo_dichiarato": _euro(dovuto_cents), "importo_versato": _euro(versato_cents),
        "differenza": _euro(esito["differenza_cents"]), "mancante": _euro(esito["mancante_cents"]),
        "stato": esito["stato"], "nota": nota,
        "f24_versamenti": [_vista_versamento(v, r) for v, r in coppie],
        "f24_sources": sorted({v["filename"] for v, _r in coppie if v.get("filename")}),
        "crediti_compensati": _euro(sum(int(r["importo_credito_cents"] or 0) for _v, r in coppie)),
    }


# ── comunicazioni 54-bis ─────────────────────────────────────────────────────

def _comunicazione_54bis(doc: Dict[str, Any], versamenti: List[Dict[str, Any]],
                         oggi: date) -> Dict[str, Any]:
    dati = doc.get("comunicazione_54bis") or {}
    periodi = [p for p in (dati.get("periodi") or []) if isinstance(p, dict)]
    codici = sorted({
        str(p.get(k)) for p in periodi
        for k in ("codice_tributo_da_versare", "codice_tributo_sanzioni", "codice_tributo_interessi")
        if p.get(k)
    })
    anno_imposta = dati.get("anno_imposta")
    anno_modello = dati.get("anno_modello")
    if isinstance(anno_imposta, int):
        anni = {anno_imposta}
    elif isinstance(anno_modello, int):
        # Il modello dell'anno N dichiara il periodo N-1; sul versamento
        # puo' comparire l'uno o l'altro.
        anni = {anno_modello - 1, anno_modello}
    else:
        anni = set()
    totale_cents = _cents(dati.get("importo_totale"))
    somma_periodi = sum(_cents(p.get("totale")) or 0 for p in periodi)
    nota = None
    if totale_cents is None:
        totale_cents = somma_periodi if periodi else None
    elif periodi and abs(totale_cents - somma_periodi) > SOGLIA_CENTS:
        nota = (f"il totale della comunicazione ({_euro_it(totale_cents)} €) non e' la somma dei periodi "
                f"({_euro_it(somma_periodi)} €)")
    coppie = [(v, r) for anno in sorted(anni) for c in codici for v, r in _righe_codice(versamenti, c, anno)]
    versato_cents = _somma_debito(coppie)
    esito = confronta_importi(totale_cents, versato_cents)
    stato = {STATO_OK: "PAGATA", STATO_ECCEDENTE: "PAGATA", STATO_MANCANTE: "NON_PAGATA",
             STATO_PARZIALE: "PARZIALE", STATO_NON_DETERMINABILE: "DA_VERIFICARE"}[esito["stato"]]
    # Senza riga con i codici della comunicazione, un versamento dello stesso
    # importo al centesimo dopo l'elaborazione e' un candidato (importo e
    # data, nessun identificativo: proposta probabile, §17A.25), mai una prova.
    candidati = []
    data_el = reg._data_iso(dati.get("data_elaborazione"))
    if stato == "NON_PAGATA" and totale_cents and data_el:
        # Solo con la data di elaborazione: la finestra e' quella del pagamento
        # con sanzione ridotta (60 giorni, piu' il margine delle rate).
        limite = (date.fromisoformat(data_el) + timedelta(days=GIORNI_FINESTRA_CANDIDATI)).isoformat()
        for v in versamenti:
            if v.get("saldo_cents") != totale_cents or not v.get("data_versamento"):
                continue
            giorno = str(v["data_versamento"])[:10]
            if giorno < data_el or giorno > limite:
                continue
            candidati.append({
                "fonte": v["fonte"], "id": v["id"], "filename": v["filename"], "protocollo": v["protocollo"],
                "data_versamento": v["data_versamento"], "importo": _euro(v["saldo_cents"]),
                "codici_tributo": sorted({r["codice"] for r in v["righe"]}),
            })
        if candidati:
            stato = "DA_VERIFICARE"
            nota = ((nota + "; ") if nota else "") + (
                f"nessuna riga con i codici {', '.join(codici)}, ma {len(candidati)} versamento/i di pari importo "
                f"({_euro_it(totale_cents)} €) dopo l'elaborazione: da verificare, i codici tributo letti sulla "
                "quietanza non coincidono"
            )
    # Il totale della comunicazione comanda (gli interessi maturano dopo i
    # periodi stampati): la differenza resta scritta in `nota`.
    data_notifica = reg._data_iso(dati.get("data_notifica") or doc.get("data_notifica"))
    scadenza = None
    if data_notifica:
        scadenza = (date.fromisoformat(data_notifica) + timedelta(days=GIORNI_PAGAMENTO_54BIS)).isoformat()
    return {
        "document_id": doc.get("id"), "filename": doc.get("filename"),
        "document_type": doc.get("document_type"),
        "numero_comunicazione": dati.get("numero_comunicazione"),
        "tipo_modello": dati.get("tipo_modello"), "anno_modello": anno_modello, "anno_imposta": anno_imposta,
        "anno": anno_imposta if isinstance(anno_imposta, int) else anno_modello,
        "codici_cercati": codici, "anni_cercati": sorted(anni),
        "importo_totale": _euro(totale_cents), "importo_versato": _euro(versato_cents),
        "mancante": _euro(esito["mancante_cents"]), "stato": stato, "pagata": stato == "PAGATA",
        "nota": nota, "periodi": periodi,
        "codice_atto": dati.get("codice_atto"), "data_elaborazione": dati.get("data_elaborazione"),
        "candidati_per_importo": candidati,
        "data_notifica": data_notifica, "scadenza": scadenza,
        "scadenza_motivo": None if scadenza else "data di notifica non nota: il termine di 30 giorni non si calcola",
        "giorni_oltre_scadenza": (
            (oggi - date.fromisoformat(scadenza)).days if scadenza and stato != "PAGATA" else None
        ),
        "f24_versamenti": [_vista_versamento(v, r) for v, r in coppie],
    }


# ── file rotti ───────────────────────────────────────────────────────────────

async def _file_rotti(db) -> List[Dict[str, Any]]:
    rotti: Dict[str, Dict[str, Any]] = {}
    async for d in db[COLL_FISCAL_DOCUMENTS].find(
        {"review_status": "TO_VERIFY"}, {"_id": 0, "id": 1, "filename": 1, "document_type": 1},
    ):
        rotti[str(d.get("id"))] = {"document_id": d.get("id"), "filename": d.get("filename"),
                                   "document_type": d.get("document_type"),
                                   "motivi": ["classificazione da verificare (review_status TO_VERIFY)"]}
    async for p in db[COLL_FISCAL_PAGES].find(
        {"requires_ocr": True}, {"_id": 0, "document_id": 1, "page_number": 1},
    ):
        did = str(p.get("document_id"))
        voce = rotti.setdefault(did, {"document_id": p.get("document_id"), "filename": None,
                                      "document_type": None, "motivi": []})
        voce["motivi"].append(f"pagina {p.get('page_number')} senza testo: serve OCR")
    return sorted(rotti.values(), key=lambda v: str(v.get("filename") or v.get("document_id")))


# ── il motore ────────────────────────────────────────────────────────────────

def _alert_previsti(esito: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Gli alert che i risultati giustificano: uno per entita', col dettaglio.
    Gli indizi (hints) non ci sono mai."""
    previsti: List[Dict[str, Any]] = []
    for r in esito["confronti_iva_mensile"]:
        if r["stato"] not in STATI_DA_SEGNALARE:
            continue
        previsti.append({
            "codice": ALERT_IVA_MENSILE, "entita_collection": COLL_LIPE, "entita_id": str(r["lipe_id"]),
            "dettaglio": (
                f"Manca (o e' parziale) il versamento IVA di {r['mese_nome']} {r['anno']}: dovuti "
                f"{_euro_it(_cents(r['dovuto_da_lipe']))} € da LIPE ({r['lipe_source']}), versati con il codice "
                f"{r['codice_tributo']} {_euro_it(_cents(r['versato_f24']))} € -> mancano "
                f"{_euro_it(_cents(r['mancante']))} € (piu' l'eventuale ravvedimento se versato in ritardo)"
            ),
            "extra": {"anno": r["anno"], "mese": r["mese"], "stato": r["stato"],
                      "importo_dovuto": r["dovuto_da_lipe"], "importo_versato": r["versato_f24"],
                      "importo_mancante": r["mancante"], "lipe_source": r["lipe_source"],
                      "f24_sources": r["f24_sources"], "hints": [h["tipo"] for h in r["hints"]]},
        })
    for r in esito["irap_riscontro"]:
        if r["stato"] not in STATI_DA_SEGNALARE:
            continue
        previsti.append({
            "codice": ALERT_IRAP, "entita_collection": COLL_FISCAL_DOCUMENTS, "entita_id": str(r["document_id"]),
            "dettaglio": (
                f"Manca (o e' parziale) il saldo IRAP {r['anno_imposta']}: dichiarati "
                f"{_euro_it(_cents(r['importo_dichiarato']))} € (quadro IR, rigo IR26, {r['dich_source']}), "
                f"versati con il codice 3800 {_euro_it(_cents(r['importo_versato']))} € -> mancano "
                f"{_euro_it(_cents(r['mancante']))} € (piu' l'eventuale ravvedimento)"
            ),
            "extra": {"anno": r["anno_imposta"], "stato": r["stato"], "importo_dovuto": r["importo_dichiarato"],
                      "importo_versato": r["importo_versato"], "importo_mancante": r["mancante"],
                      "dich_source": r["dich_source"], "f24_sources": r["f24_sources"]},
        })
    for r in esito["iva_annuale_riscontro"]:
        if r["stato"] not in STATI_DA_SEGNALARE:
            continue
        previsti.append({
            "codice": ALERT_IVA_ANNUALE, "entita_collection": COLL_FISCAL_DOCUMENTS,
            "entita_id": str(r["document_id"]),
            "dettaglio": (
                f"Saldo IVA annuale {r['anno_imposta']} da verificare: il rigo VX1 dichiara "
                f"{_euro_it(_cents(r['importo_dichiarato']))} € ({r['dich_source']}), versati con il codice 6099 "
                f"{_euro_it(_cents(r['importo_versato']))} € -> mancano {_euro_it(_cents(r['mancante']))} €"
            ),
            "extra": {"anno": r["anno_imposta"], "stato": r["stato"], "importo_dovuto": r["importo_dichiarato"],
                      "importo_versato": r["importo_versato"], "importo_mancante": r["mancante"],
                      "dich_source": r["dich_source"], "f24_sources": r["f24_sources"]},
        })
    for r in esito["comunicazioni_54bis"]:
        if r["stato"] not in ("NON_PAGATA", "PARZIALE"):
            continue
        scadenza = f", scaduta il {reg.data_italiana(r['scadenza'])}" if r.get("scadenza") else ""
        previsti.append({
            "codice": ALERT_54BIS, "entita_collection": COLL_FISCAL_DOCUMENTS, "entita_id": str(r["document_id"]),
            "dettaglio": (
                f"Comunicazione di irregolarita' 54-bis n. {r['numero_comunicazione']} "
                f"(modello {r['tipo_modello']} {r['anno_modello']}, {r['filename']}) non risulta pagata: dovuti "
                f"{_euro_it(_cents(r['importo_totale']))} € (codici {', '.join(r['codici_cercati'])}), versati "
                f"{_euro_it(_cents(r['importo_versato']))} €{scadenza}. Oltre i termini la sanzione ridotta decade."
            ),
            "extra": {"anno": r["anno"], "stato": r["stato"], "importo_dovuto": r["importo_totale"],
                      "importo_versato": r["importo_versato"], "importo_mancante": r["mancante"],
                      "numero_comunicazione": r["numero_comunicazione"], "codici": r["codici_cercati"],
                      "scadenza": r["scadenza"]},
        })
    return previsti


async def incroci(db, *, anni: Optional[Iterable[int]] = None, oggi: Optional[date] = None) -> Dict[str, Any]:
    """Il quadro completo degli incroci, in sola lettura. Con `anni` restringe
    LIPE e dichiarazioni agli anni chiesti; le fonti F24 si leggono una volta."""
    oggi = oggi or datetime.now(timezone.utc).date()
    anni_scelti: Optional[Set[int]] = {int(a) for a in anni} if anni else None

    lipe, lipe_escluse = await _lipe_canoniche(db, anni_scelti)
    registro = await reg.carica_registro(db)
    fonti = versamenti_dal_registro(registro)
    versamenti = fonti["versamenti"]
    # Gli indizi guardano modelli e quietanze con righe insieme (i modelli da
    # soli: nel minisito i versamenti sono quasi tutti quietanze).
    registro_indizi = {
        **registro,
        "f24": registro["f24"] + [v["documento"] for v in versamenti if v["quietanza"] and v.get("documento")],
    }

    mensili = [_confronto_mese(riga, versamenti, registro_indizi) for riga in lipe]

    dichiarazioni = await db[COLL_FISCAL_DOCUMENTS].find(
        {"quadri.tipo_letto": {"$in": ["DICHIARAZIONE_IRAP", "DICHIARAZIONE_IVA"]}},
        {"_id": 0, "pdf_data": 0},
    ).to_list(2000)
    dichiarazioni = [d for d in dichiarazioni if d.get("entity_status") != "deleted"]
    irap = _scegli_per_anno(d for d in dichiarazioni if d["quadri"].get("tipo_letto") == "DICHIARAZIONE_IRAP")
    iva = _scegli_per_anno(d for d in dichiarazioni if d["quadri"].get("tipo_letto") == "DICHIARAZIONE_IVA")
    irap_riscontro = [
        _riscontro_annuale(doc, anno, "ir26_importo_a_debito", CODICE_IRAP_SALDO, versamenti)
        for anno, doc in sorted(irap.items()) if not anni_scelti or anno in anni_scelti
    ]
    iva_annuale = [
        _riscontro_annuale(doc, anno, "vx1_da_versare", CODICE_IVA_ANNUALE, versamenti)
        for anno, doc in sorted(iva.items()) if not anni_scelti or anno in anni_scelti
    ]

    comunicazioni = await db[COLL_FISCAL_DOCUMENTS].find(
        {"document_type": {"$in": list(TIPI_54BIS)}}, {"_id": 0, "pdf_data": 0},
    ).to_list(2000)
    comunicazioni_54bis: List[Dict[str, Any]] = []
    senza_righe: List[Dict[str, Any]] = []
    for doc in comunicazioni:
        if doc.get("entity_status") == "deleted":
            continue
        if not (doc.get("comunicazione_54bis") or {}).get("periodi"):
            senza_righe.append({"document_id": doc.get("id"), "filename": doc.get("filename"),
                                "document_type": doc.get("document_type"),
                                "motivo": "nessuna riga strutturata (codici e importi della comunicazione non letti)"})
            continue
        voce = _comunicazione_54bis(doc, versamenti, oggi)
        if anni_scelti and isinstance(voce["anno"], int) and voce["anno"] not in anni_scelti:
            continue
        comunicazioni_54bis.append(voce)

    conteggi_mensili: Dict[str, int] = {}
    for r in mensili:
        conteggi_mensili[r["stato"]] = conteggi_mensili.get(r["stato"], 0) + 1

    esito = {
        "generato_at": datetime.now(timezone.utc).isoformat(),
        "anni": sorted(anni_scelti) if anni_scelti else sorted({r["anno"] for r in mensili}),
        "soglia_euro": _euro(SOGLIA_CENTS),
        "soglia_indizi_euro": _euro(reg.TOLLERANZA_INDIZIO_CENTS),
        "confronti_iva_mensile": mensili,
        "conteggi_mensili": conteggi_mensili,
        "irap_riscontro": irap_riscontro,
        "iva_annuale_riscontro": iva_annuale,
        "comunicazioni_54bis": comunicazioni_54bis,
        "comunicazioni_senza_righe_strutturate": senza_righe,
        "guardia": {"lipe_escluse": lipe_escluse, "f24_esclusi": fonti["esclusi"]},
        "file_rotti": await _file_rotti(db),
        "fonti": {
            **registro["conteggi"],
            "lipe_periodi_canonici": len(lipe), "lipe_periodi_esclusi": len(lipe_escluse),
            "versamenti_contati": len(versamenti),
            "versamenti_da_quietanza": sum(1 for v in versamenti if v["quietanza"]),
            "versamenti_da_modello": sum(1 for v in versamenti if not v["quietanza"]),
            "dichiarazioni_irap": len(irap), "dichiarazioni_iva": len(iva),
            "comunicazioni_54bis": len(comunicazioni_54bis),
        },
        "sola_lettura": True,
    }
    esito["alert_previsti"] = _alert_previsti(esito)
    return esito


# ── alert ────────────────────────────────────────────────────────────────────

async def applica_alert(db, esito: Dict[str, Any], *, anni_completi: bool = True) -> Dict[str, Any]:
    """Apre gli alert previsti e chiude quelli la cui condizione non vale piu'.

    Un alert ignorato dal titolare non rinasce. Con `anni_completi` falso
    (giro su alcuni anni soltanto) non si chiude niente fuori da quegli anni:
    non visto non vuol dire risolto.
    """
    from app.services.alert_engine import genera_alert, risolvi_alert_per_id

    previsti = {(a["codice"], a["entita_id"]): a for a in esito.get("alert_previsti") or []}
    creati = chiusi = invariati = 0
    for codice in CODICI_ALERT:
        esistenti = await db[COLL_ALERTS].find(
            {"codice": codice, "stato": {"$in": [STATO_ALERT_APERTO, STATO_ALERT_IGNORATO]}},
            {"_id": 0, "id": 1, "entita_id": 1, "stato": 1, "extra": 1},
        ).to_list(None)
        per_entita = {str(a.get("entita_id")): a for a in esistenti}
        for (cod, entita_id), spec in previsti.items():
            if cod != codice:
                continue
            gia = per_entita.get(entita_id)
            if gia:
                invariati += 1
                continue
            nuovo = await genera_alert(codice, entita_id, spec["entita_collection"], spec["dettaglio"], db,
                                       extra=spec["extra"])
            creati += int(bool(nuovo))
        for entita_id, a in per_entita.items():
            if (codice, entita_id) in previsti or a.get("stato") != STATO_ALERT_APERTO:
                continue
            anno_alert = (a.get("extra") or {}).get("anno")
            if not anni_completi and anno_alert not in set(esito.get("anni") or []):
                continue
            if await risolvi_alert_per_id(
                a["id"], db, "incroci fiscali: al ricalcolo la condizione non vale piu' (versato entro la soglia, "
                "fonte sostituita o esclusa dalla guardia)", resolved_by="incroci_fiscali",
            ):
                chiusi += 1
    return {"creati": creati, "chiusi": chiusi, "invariati": invariati}


async def esegui_incroci(db, *, anni: Optional[Iterable[int]] = None) -> Dict[str, Any]:
    """Il giro del mattino: incroci piu' alert. Restituisce il riepilogo."""
    esito = await incroci(db, anni=anni)
    alert = await applica_alert(db, esito, anni_completi=anni is None)
    return {
        "anni": esito["anni"],
        "conteggi_mensili": esito["conteggi_mensili"],
        "irap": {r["anno_imposta"]: r["stato"] for r in esito["irap_riscontro"]},
        "iva_annuale": {r["anno_imposta"]: r["stato"] for r in esito["iva_annuale_riscontro"]},
        "comunicazioni_54bis": {r["numero_comunicazione"]: r["stato"] for r in esito["comunicazioni_54bis"]},
        "guardia": {k: len(v) for k, v in esito["guardia"].items()},
        "file_rotti": len(esito["file_rotti"]),
        "alert": alert,
    }
