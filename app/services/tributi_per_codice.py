"""Tributi per codice: che cosa ho pagato, quando, come, e che cosa resta.

Una vista, non un secondo registro: legge il registro unico F24
(``f24_controllo_incrociato.carica_registro``) e le ritenute attese
(``ritenute_acconto``, alimentate dalle fatture con ritenuta), e mette ogni
riga tributo al suo posto, per **codice tributo e periodo di riferimento**
(l'anno di riferimento vince sulla data di pagamento):

* **Inviato dal commercialista** — le righe a debito dei modelli F24 arrivati
  (il modello non prova il pagamento);
* **Pagato con quietanza** — le righe a debito delle quietanze AdE ordinarie;
* **Pagato con ravvedimento** — le righe delle quietanze di ravvedimento: il
  tributo ravveduto (con gli interessi cumulati), la sanzione, gli interessi;
* **A credito / compensato** — le righe a credito usate in compensazione, con
  i tributi che hanno pagato nella stessa delega;
* **Atteso** — le ritenute d'acconto lette dalle fatture, non ancora versate;
* **Resta da pagare** — il dovuto (modello o ritenuta attesa) meno quello che
  quietanze, ravvedimenti e addebiti in banca documentano, mai sotto zero.

Le copie della stessa quietanza sono un pagamento solo
(``pagamenti_da_quietanze``). Nessun importo si stima: una riga che manca
resta vuota. Nessuna scrittura: la pagina legge e basta.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.constants.codici_ravvedimento import CODICI_RAVVEDIMENTO
from app.services import f24_controllo_incrociato as reg

COLL_RITENUTE = "ritenute_acconto"

# Stati di una riga della pagina, con la parola che la pagina scrive.
PAGATO = "PAGATO"
PAGATO_IN_RITARDO = "PAGATO_IN_RITARDO"
RAVVEDUTO = "RAVVEDUTO"
PAGATO_BANCA = "PAGATO_BANCA"
COMPENSATO = "COMPENSATO"
DA_PAGARE = "DA_PAGARE"
SCADUTO = "SCADUTO"
ATTESO = "ATTESO"
CREDITO = "CREDITO"
SANZIONE = "SANZIONE"
INTERESSI = "INTERESSI"
SENZA_PROVA = "SENZA_PROVA"
NON_TORNA = "NON_TORNA"

ETICHETTE = {
    PAGATO: "Pagato (quietanza)",
    PAGATO_IN_RITARDO: "Pagato in ritardo",
    RAVVEDUTO: "Pagato con ravvedimento",
    PAGATO_BANCA: "Pagato in banca, manca la quietanza",
    COMPENSATO: "Pagato in compensazione (F24 a zero)",
    DA_PAGARE: "Da pagare",
    SCADUTO: "Scaduto, non pagato",
    ATTESO: "Atteso, manca l'F24",
    CREDITO: "A credito, compensato",
    SANZIONE: "Sanzione pagata",
    INTERESSI: "Interessi pagati",
    SENZA_PROVA: "Da verificare",
    NON_TORNA: "Non torna con le fatture",
}

# Sanzioni e interessi da ravvedimento (fonte unica: constants/codici_ravvedimento).
_CODICI_INTERESSI = {c for c in CODICI_RAVVEDIMENTO if c.startswith("19") or c.startswith("15")}
_CODICI_SANZIONE = set(CODICI_RAVVEDIMENTO) - _CODICI_INTERESSI

Chiave = Tuple[str, str, Optional[int], Optional[int]]


def natura_codice(codice: str, descrizione: str = "") -> str:
    """tributo, sanzione o interessi: dal codice, poi dalla descrizione."""
    c = str(codice or "").upper()
    testo = str(descrizione or "").upper()
    if c in _CODICI_SANZIONE or "SANZION" in testo:
        return "sanzione"
    if c in _CODICI_INTERESSI or "INTERESS" in testo:
        return "interessi"
    return "tributo"


def descrizione_codice(codice: str, sezione: str, descrizione_riga: str = "") -> str:
    """Le descrizioni vengono dal catalogo unico; la riga solo se il catalogo tace."""
    from app.services.codici_tributo_f24 import CODICI_TRIBUTO_F24, get_descrizione_causale_inps

    c = str(codice or "").upper()
    if sezione in ("sezione_inps", "sezione_inail"):
        testo = get_descrizione_causale_inps(c)
        if not testo.startswith("Causale INPS"):
            return testo
    elif c in CODICI_TRIBUTO_F24:
        return str(CODICI_TRIBUTO_F24[c].get("descrizione") or c)
    riga = str(descrizione_riga or "").strip()
    if riga and not riga.lower().startswith(("tributo ", "codice ")):
        return riga
    return f"Codice {c}" if sezione not in ("sezione_inps", "sezione_inail") else f"Causale INPS {c}"


_SEZIONI = {
    "sezione_erario": "Erario",
    "sezione_inps": "INPS",
    "sezione_regioni": "Regioni",
    "sezione_tributi_locali": "Tributi locali",
    "sezione_inail": "INAIL",
}


def _periodo_testo(anno: Optional[int], mese: Optional[int]) -> str:
    if anno and mese:
        return f"{mese:02d}/{anno}"
    return str(anno) if anno else "senza periodo"


def _nuova_voce(chiave: Chiave, descrizione_riga: str) -> Dict[str, Any]:
    sezione, codice, anno, mese = chiave
    return {
        "chiave": f"{sezione}|{codice}|{anno or ''}|{mese or ''}",
        "codice": codice,
        "sezione": sezione,
        "sezione_label": _SEZIONI.get(sezione, sezione),
        "descrizione": descrizione_codice(codice, sezione, descrizione_riga),
        "natura": natura_codice(codice, descrizione_riga),
        "anno": anno,
        "mese": mese,
        "periodo": _periodo_testo(anno, mese),
        "inviato_cents": 0,
        "quietanza_cents": 0,
        "ravvedimento_cents": 0,
        "banca_cents": 0,
        "compensazione_cents": 0,
        "credito_cents": 0,
        "atteso_cents": 0,
        "scadenza": None,
        "ultimo_pagamento": None,
        "documenti": [],
    }


def _chiave_riga(r: Dict[str, Any]) -> Chiave:
    return (str(r.get("sezione") or ""), str(r.get("codice") or ""), r.get("anno"), r.get("mese"))


def _voce(voci: Dict[Chiave, Dict[str, Any]], r: Dict[str, Any]) -> Dict[str, Any]:
    chiave = _chiave_riga(r)
    if chiave not in voci:
        voci[chiave] = _nuova_voce(chiave, r.get("descrizione") or "")
    return voci[chiave]


def _min_data(a: Optional[str], b: Optional[str]) -> Optional[str]:
    return min(x for x in (a, b) if x) if (a or b) else None


def _max_data(a: Optional[str], b: Optional[str]) -> Optional[str]:
    return max(x for x in (a, b) if x) if (a or b) else None


def _righe_debito_testo(righe: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {"codice": r.get("codice"), "periodo": _periodo_testo(r.get("anno"), r.get("mese")),
         "importo_cents": int(r.get("importo_debito_cents") or 0)}
        for r in righe if int(r.get("importo_debito_cents") or 0) > 0
    ]


def _aggiungi_pagamenti(voci: Dict[Chiave, Dict[str, Any]], pagamenti: List[Dict[str, Any]]) -> None:
    for p in pagamenti:
        righe = p.get("_righe") or []
        # Periodi ravveduti: dove nella stessa delega c'e' una sanzione o un
        # interesse da ravvedimento. Solo quelle righe sono «ravvedimento»;
        # le altre righe della stessa delega restano pagamenti ordinari.
        periodi_ravveduti = {
            (r.get("anno"), r.get("mese")) for r in righe
            if str(r.get("codice") or "").upper() in CODICI_RAVVEDIMENTO
        }
        anni_ravveduti = {a for a, _m in periodi_ravveduti}
        credito_delega = sum(int(r.get("importo_credito_cents") or 0) for r in righe)
        debiti = _righe_debito_testo(righe)
        crediti = [
            {"codice": r.get("codice"), "periodo": _periodo_testo(r.get("anno"), r.get("mese")),
             "importo_cents": int(r.get("importo_credito_cents") or 0)}
            for r in righe if int(r.get("importo_credito_cents") or 0) > 0
        ]
        prima = (p.get("quietanze") or [{}])[0]
        # F24 a saldo zero: i debiti sono pagati per intero dai crediti della
        # stessa delega. E' un pagamento vero, senza addebito in banca.
        tutta_compensata = bool(p.get("compensazione_totale"))
        for r in righe:
            voce = _voce(voci, r)
            debito = int(r.get("importo_debito_cents") or 0)
            credito = int(r.get("importo_credito_cents") or 0)
            codice = str(r.get("codice") or "").upper()
            ravveduta = (
                codice in CODICI_RAVVEDIMENTO
                or (r.get("anno"), r.get("mese")) in periodi_ravveduti
                or (r.get("mese") is None and r.get("anno") in anni_ravveduti)
            )
            if credito and not debito:
                tipo_doc = "credito"
            elif ravveduta and debito:
                tipo_doc = "ravvedimento"
            elif tutta_compensata:
                tipo_doc = "compensazione"
            else:
                tipo_doc = "quietanza"
            documento = {
                "tipo": tipo_doc,
                "origini": p.get("origini") or [],
                "in_compensazione": tutta_compensata,
                "data": p.get("data"),
                "protocollo": p.get("protocollo"),
                "quietanza_id": prima.get("id"),
                "pdf_url": prima.get("pdf_url"),
                "copie": len(p.get("quietanze") or []),
                "importo_cents": debito,
                "credito_cents": credito,
                "saldo_delega_cents": p.get("importo_cents"),
                "credito_delega_cents": credito_delega,
                "ravvedimento_di": p.get("ravvedimento_di") or [],
                "tipo_versamento": p.get("tipo_versamento"),
            }
            if credito:
                documento["compensato_con"] = debiti
            if debito and credito_delega:
                documento["crediti_usati"] = crediti
            if debito:
                if ravveduta:
                    voce["ravvedimento_cents"] += debito
                elif tutta_compensata:
                    voce["compensazione_cents"] += debito
                else:
                    voce["quietanza_cents"] += debito
                voce["ultimo_pagamento"] = _max_data(voce["ultimo_pagamento"], p.get("data"))
            voce["credito_cents"] += credito
            voce["documenti"].append(documento)


def _aggiungi_modelli(
    voci: Dict[Chiave, Dict[str, Any]], registro: Dict[str, Any], quietanze_con_righe: set,
) -> None:
    for f24 in registro["f24"]:
        # Il modello di ravvedimento (etichettato, o con sanzioni e interessi nelle sue righe) non e' del
        # commercialista: la sua data e' quella del versamento, non una scadenza, e il suo tributo comprende
        # gli interessi cumulati. Contarlo qui nascondeva il ritardo (Scadenzario «puntuale» il giorno stesso
        # del versamento) e dava un dovuto maggiorato (interessi «insufficienti»): lo racconta la sua quietanza.
        if reg.e_modello_di_ravvedimento(f24):
            continue
        fid = str(f24.get("id") or "")
        prove = reg.prove_modello(f24, registro)
        esito, motivo = reg._esito_da_prove(prove)
        ids_quietanze = {str(q.get("quietanza_id")) for q in prove["quietanze"] if q.get("quietanza_id")}
        documentato_da_righe = bool(ids_quietanze & quietanze_con_righe)
        ravvedimento = f24.get("ravvedimento") or {}
        for r in reg.righe_modello(f24):
            voce = _voce(voci, r)
            debito = int(r.get("importo_debito_cents") or 0)
            credito = int(r.get("importo_credito_cents") or 0)
            voce["inviato_cents"] += debito
            voce["scadenza"] = _min_data(voce["scadenza"], prove["data_versamento"])
            # Pagato senza una quietanza leggibile riga per riga: lo prova la
            # banca (o una quietanza senza righe), e conta come pagato.
            if not documentato_da_righe and (
                esito == reg.ESITO_PAGATO_SENZA_QUIETANZA
                or (esito == reg.ESITO_COPERTO and prove["quietanza_presente"])
            ):
                voce["banca_cents"] += debito
                voce["credito_cents"] += credito
                voce["ultimo_pagamento"] = _max_data(
                    voce["ultimo_pagamento"],
                    next((a.get("data") for a in prove["addebiti_banca"] if a.get("data")), None)
                    or next((q.get("data") for q in prove["quietanze"] if q.get("data")), None),
                )
            voce["documenti"].append({
                "tipo": "commercialista",
                "f24_id": fid,
                "file": f24.get("file_name") or f24.get("filename"),
                "data": prove["data_versamento"],
                "importo_cents": debito,
                "credito_cents": credito,
                "esito": esito,
                "motivo": motivo,
                "pdf_url": reg.PDF_F24_URL.format(f24_id=fid),
                "ravveduto": ravvedimento.get("stato") == "RAVVEDUTO",
                "addebiti_banca": [
                    {"data": a.get("data"), "importo": a.get("importo"), "link": a.get("link"),
                     "agganciato": a.get("agganciato")}
                    for a in prove["addebiti_banca"]
                ],
            })


def _aggiungi_ritenute(voci: Dict[Chiave, Dict[str, Any]], ritenute: List[Dict[str, Any]]) -> None:
    for rit in ritenute:
        # Il periodo del 1040 e' il mese del pagamento al professionista
        # (decisione del 02/10/2026): una parcella non ancora pagata non ha
        # periodo e resta fuori dal registro, mai nel mese della fattura.
        periodo = str(rit.get("periodo_ritenuta") or "")[:7]
        if len(periodo) != 7:
            continue
        anno, mese = int(periodo[:4]), int(periodo[5:7])
        voce = _voce(voci, {"sezione": "sezione_erario", "codice": "1040", "anno": anno, "mese": mese,
                            "descrizione": ""})
        importo = int(rit.get("importo_cents") or 0)
        versata = rit.get("stato_obbligazione") == "VERSATA"
        voce["atteso_cents"] += importo
        scadenza = rit.get("scadenza_legale") or rit.get("scadenza")
        voce["scadenza"] = _min_data(voce["scadenza"], scadenza)
        voce["documenti"].append({
            "tipo": "ritenuta",
            "ritenuta_id": rit.get("id"),
            "fattura_id": rit.get("fattura_id"),
            "numero_fattura": rit.get("numero_fattura"),
            "fornitore": rit.get("fornitore"),
            "data": rit.get("data_fattura"),
            "importo_cents": importo,
            "scadenza": scadenza,
            "versata": versata,
            "stato": rit.get("stato"),
            "data_pagamento": rit.get("data_pagamento"),
            "quietanza_protocollo": rit.get("quietanza_protocollo"),
            "quietanza_pdf_url": rit.get("quietanza_pdf_url"),
            "f24_id": rit.get("f24_id"),
            "avviso": rit.get("avviso_versamento_testo"),
            "link": f"/fatture?invoice_id={rit.get('fattura_id')}" if rit.get("fattura_id") else None,
        })


def _chiudi_voce(voce: Dict[str, Any], oggi: str) -> Dict[str, Any]:
    pagato = (voce["quietanza_cents"] + voce["ravvedimento_cents"] + voce["banca_cents"]
              + voce["compensazione_cents"])
    dovuto = max(voce["inviato_cents"], voce["atteso_cents"])
    voce["pagato_cents"] = pagato
    voce["dovuto_cents"] = dovuto
    voce["residuo_cents"] = max(0, dovuto - pagato)
    # Ritenuta: la somma delle fatture e l'importo versato devono coincidere al
    # centesimo. Se no, «pagato» sarebbe un'affermazione senza prova.
    voce["scarto_cents"] = 0
    voce["fatture_da_associare"] = False
    if voce["codice"] == "1040" and voce["sezione"] == "sezione_erario":
        if voce["atteso_cents"] and pagato and pagato != voce["atteso_cents"]:
            voce["scarto_cents"] = pagato - voce["atteso_cents"]
            # Ravvedimento: gli interessi legali si cumulano al tributo (280,00 → 280,31), non e' uno scarto.
            if voce["ravvedimento_cents"] and voce["scadenza"] and voce["ultimo_pagamento"]:
                from app.services.scadenzario_tributi import eccedenza_da_interessi

                if eccedenza_da_interessi(voce["atteso_cents"], pagato, voce["scadenza"], voce["ultimo_pagamento"]):
                    voce["interessi_cumulati_cents"] = voce["scarto_cents"]
                    voce["scarto_cents"] = 0
        elif pagato and not voce["atteso_cents"]:
            voce["fatture_da_associare"] = True
    scadenza = voce["scadenza"]
    ritardo = bool(scadenza and voce["ultimo_pagamento"] and voce["ultimo_pagamento"] > scadenza)
    voce["in_ritardo"] = ritardo
    # Stesso importo pagato da due deleghe diverse (protocolli diversi): e'
    # lo stesso segnale di F24_TRIBUTO_VERSATO_DUE_VOLTE, qui sulla riga.
    protocolli_per_importo: Dict[int, set] = defaultdict(set)
    for d in voce["documenti"]:
        if d["tipo"] in ("quietanza", "ravvedimento", "compensazione") and d.get("importo_cents"):
            protocolli_per_importo[int(d["importo_cents"])].add(d.get("protocollo") or d.get("quietanza_id"))
    voce["versato_due_volte_cents"] = sum(
        importo * (len(protocolli) - 1) for importo, protocolli in protocolli_per_importo.items()
        if len(protocolli) > 1
    )
    if voce["scarto_cents"]:
        stato = NON_TORNA
    elif voce["residuo_cents"] > 0:
        if not voce["inviato_cents"] and voce["atteso_cents"] and not pagato:
            stato = SCADUTO if scadenza and scadenza < oggi else ATTESO
        else:
            stato = SCADUTO if scadenza and scadenza < oggi else DA_PAGARE
    elif voce["natura"] == "sanzione" and pagato:
        stato = SANZIONE
    elif voce["natura"] == "interessi" and pagato:
        stato = INTERESSI
    elif voce["ravvedimento_cents"]:
        stato = RAVVEDUTO
    elif voce["quietanza_cents"]:
        stato = PAGATO_IN_RITARDO if ritardo else PAGATO
    elif voce["compensazione_cents"]:
        stato = COMPENSATO
    elif voce["banca_cents"]:
        stato = PAGATO_BANCA
    elif voce["credito_cents"]:
        stato = CREDITO
    else:
        stato = SENZA_PROVA
    voce["stato"] = stato
    voce["stato_label"] = ETICHETTE[stato]
    voce["documenti"].sort(key=lambda d: str(d.get("data") or ""), reverse=True)
    return voce


def _ordine(voce: Dict[str, Any]) -> Tuple:
    codice = voce["codice"]
    # I codici numerici in ordine di numero, le causali INPS dopo.
    return (0 if codice.isdigit() else 1, codice.zfill(6), -(voce["anno"] or 0), -(voce["mese"] or 0))


def costruisci(
    registro: Dict[str, Any], ritenute: List[Dict[str, Any]], *, oggi: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Tutte le voci codice+periodo, in ordine di codice tributo."""
    oggi = oggi or date.today().isoformat()
    voci: Dict[Chiave, Dict[str, Any]] = {}
    quietanze_con_righe = [q for q in registro["quietanze"] if q.get("righe")]
    pagamenti = reg.pagamenti_da_quietanze(quietanze_con_righe)
    _aggiungi_pagamenti(voci, pagamenti)
    _aggiungi_modelli(voci, registro, {str(q.get("id")) for q in quietanze_con_righe if q.get("id")})
    _aggiungi_ritenute(voci, ritenute)
    return sorted((_chiudi_voce(v, oggi) for v in voci.values()), key=_ordine)


def riepilogo(voci: List[Dict[str, Any]], *, anno: Optional[int] = None, stato: Optional[str] = None,
              sezione: Optional[str] = None, cerca: Optional[str] = None) -> Dict[str, Any]:
    scelte = [
        v for v in voci
        if (not anno or v["anno"] == anno)
        and (not sezione or v["sezione"] == sezione)
        and (not stato or v["stato"] == stato
             or (stato == "APERTO" and v["residuo_cents"] > 0))
        and (not cerca or str(cerca).strip().lower() in
             f"{v['codice']} {v['descrizione']} {v['periodo']}".lower())
    ]
    somma = lambda campo: sum(int(v[campo] or 0) for v in scelte)  # noqa: E731
    anni = sorted({v["anno"] for v in voci if v["anno"]}, reverse=True)
    per_codice: Dict[str, int] = defaultdict(int)
    for v in scelte:
        per_codice[v["codice"]] += 1
    return {
        "voci": scelte,
        "totali": {
            "inviato_cents": somma("inviato_cents"),
            "quietanza_cents": somma("quietanza_cents"),
            "ravvedimento_cents": somma("ravvedimento_cents"),
            "banca_cents": somma("banca_cents"),
            "compensazione_cents": somma("compensazione_cents"),
            "credito_cents": somma("credito_cents"),
            "atteso_cents": somma("atteso_cents"),
            "residuo_cents": somma("residuo_cents"),
            "voci": len(scelte),
            "codici": len(per_codice),
            "aperte": sum(1 for v in scelte if v["residuo_cents"] > 0),
        },
        "facets": {
            "anni": anni,
            "stati": [{"id": k, "label": ETICHETTE[k]} for k in ETICHETTE],
            "sezioni": [{"id": k, "label": l} for k, l in _SEZIONI.items()],
        },
    }


async def carica_voci(db) -> Dict[str, Any]:
    """Le voci di tutti gli anni, con i conteggi delle fonti (una lettura sola)."""
    registro = await reg.carica_registro(db)
    ritenute = await db[COLL_RITENUTE].find({}, {"_id": 0}).to_list(5000)
    return {
        "voci": costruisci(registro, ritenute),
        "conteggi": {
            **registro["conteggi"],
            "ritenute_attese": len(ritenute),
            "quietanze_senza_righe": sum(1 for q in registro["quietanze"] if not q.get("righe")),
        },
    }


async def vista_tributi(db, **filtri: Any) -> Dict[str, Any]:
    dati = await carica_voci(db)
    return {**riepilogo(dati["voci"], **filtri), "conteggi": dati["conteggi"]}
