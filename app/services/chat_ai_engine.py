"""
Motore AI della Chat Intelligente — agent loop con strumenti tipizzati.

Architettura (da app/knowledge/chat_kb.json, "implementazione_chat_intelligente"):
- il modello AI NON ha accesso diretto a MongoDB: interroga i dati solo
  tramite gli strumenti definiti qui, con parametri validati, proiezioni
  di campo limitate e tetti sul numero di risultati;
- ogni chiamata a uno strumento viene registrata in chat_tool_calls;
- la risposta finale e' STRUTTURATA (conclusione, stato, affidabilita'
  certo/probabile/dubbio, fonti, dati mancanti, azioni proposte) e viene
  prodotta obbligatoriamente tramite lo strumento `componi_risposta`;
- la chat propone ma NON esegue mai azioni con effetti contabili/fiscali:
  qui esistono SOLO strumenti di lettura.

Configurazione (variabili d'ambiente):
  ANTHROPIC_API_KEY  obbligatoria (senza, il motore non e' configurato e
                     la chat ricade sul motore a parole chiave esistente)
  ANTHROPIC_MODEL    opzionale, default "claude-sonnet-5"
"""
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

KB_PATH = Path(__file__).resolve().parent.parent / "knowledge" / "chat_kb.json"

MAX_ITERAZIONI_TOOL = 10
MAX_RISULTATI_DEFAULT = 25
MAX_RISULTATI_TETTO = 100
STORICO_MESSAGGI_CONTESTO = 10


def is_configured() -> bool:
    """True se la chiave Anthropic e' configurata nell'ambiente."""
    return bool(os.getenv("ANTHROPIC_API_KEY", "").strip())


def _model_name() -> str:
    return os.getenv("ANTHROPIC_MODEL", "").strip() or "claude-sonnet-5"


# ============================================================================
# BASE DI CONOSCENZA — caricamento e selezione dei domini pertinenti
# ============================================================================

_kb_cache: Optional[Dict[str, Any]] = None


def _load_kb() -> Dict[str, Any]:
    global _kb_cache
    if _kb_cache is None:
        try:
            _kb_cache = json.loads(KB_PATH.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("Impossibile caricare la knowledge base della chat")
            _kb_cache = {}
    return _kb_cache


# Parole chiave -> dominio della KB da includere nel contesto.
_DOMINI_KEYWORDS = {
    "f24": ["f24", "tribut", "quietanz", "codice 6", "codice 1", "inps", "iva vers", "erario"],
    "cedolini_dipendenti": ["cedolin", "dipendent", "stipend", "busta", "tfr", "ferie",
                             "permess", "netto", "lordo", "indennit", "irpef", "contribut",
                             "tredicesima", "quattordicesima", "matricola"],
    "verbali_veicoli_trattenute": ["verbal", "multa", "targa", "trattenut", "conducente", "driver"],
    "noleggio": ["auto", "veicolo", "targa", "noleggio", "bmw", "mazda", "stelvio", "alfa",
                  "x1", "x3", "cx-60", "verbale", "multa", "driver", "canone", "trattenuta"],
    "fatture_fornitori": ["fattur", "fornitor", "pagament", "scadenz"],
    "corrispettivi_pos": ["corrispettiv", "pos", "incass", "contant", "accredit", "scontrin"],
    "riconciliazione_bancaria": ["riconcili", "estratto conto", "movimento banc", "banca"],
    "prima_nota": ["prima nota", "saldo", "cassa", "provvisor"],
    "iva": ["iva"],
    "veicoli_noleggio": ["veicol", "noleggi", "auto", "canone"],
    "documenti_import": ["document", "import", "parser", "errore", "email"],
    "controllo_gestionale": ["riepilog", "attenzione", "anomal", "andament", "confront", "controllo"],
}


def _domini_pertinenti(domanda: str) -> List[str]:
    d = domanda.lower()
    trovati = [dom for dom, kws in _DOMINI_KEYWORDS.items() if any(k in d for k in kws)]
    # controllo_gestionale come rete di sicurezza per domande generiche
    return trovati or ["controllo_gestionale", "prima_nota", "fatture_fornitori"]


def _system_prompt(domanda: str) -> str:
    kb = _load_kb()
    oggi = datetime.now().strftime("%Y-%m-%d")

    parti = [
        "Sei la Chat Intelligente del gestionale Ceraldi ERP (Ceraldi Caffe / "
        "Ceraldi Group SRL, bar/caffetteria, Napoli). Ragioni come un consulente "
        "amministrativo, non come un motore di ricerca. Rispondi SEMPRE in italiano.",
        f"Data di oggi: {oggi}.",
    ]

    principi = kb.get("meta", {}).get("principi_chat", [])
    if principi:
        parti.append("PRINCIPI:\n- " + "\n- ".join(principi))

    regola = kb.get("regola_decisionale_globale", {})
    if regola:
        parti.append("REGOLA DECISIONALE (certo/probabile/dubbio):\n" +
                     json.dumps(regola, ensure_ascii=False, indent=1))

    vietate = kb.get("azioni_vietate_alla_chat", [])
    if vietate:
        parti.append("AZIONI VIETATE (mai eseguirle, mai fingere di averle fatte):\n- " +
                     "\n- ".join(vietate))

    conv = kb.get("regole_conversazionali", {})
    if conv:
        parti.append("REGOLE CONVERSAZIONALI:\n" +
                     json.dumps(conv, ensure_ascii=False, indent=1))

    # Solo i domini pertinenti alla domanda (contesto mirato, non tutta la KB)
    domini = kb.get("domini", {})
    for nome in _domini_pertinenti(domanda):
        if nome in domini:
            sezione = dict(domini[nome])
            # le liste di domande d'esempio sono lunghe: bastano le prime
            if isinstance(sezione.get("domande"), list):
                sezione["domande"] = sezione["domande"][:8]
            parti.append(f"DOMINIO {nome}:\n" + json.dumps(sezione, ensure_ascii=False, indent=1))

    parti.append(
        "COME LAVORI:\n"
        "1. Usa gli strumenti per recuperare i DATI REALI: non inventare mai numeri.\n"
        "2. Se i dati non bastano, dichiara cosa manca — mai forzare una conclusione.\n"
        "3. Quando hai finito, chiama SEMPRE lo strumento `componi_risposta` con la "
        "risposta strutturata: e' l'unico modo di rispondere all'utente.\n"
        "4. Gli importi sono in euro. Le date in formato YYYY-MM-DD."
    )
    return "\n\n".join(parti)


# ============================================================================
# STRUMENTI DATI — definizioni tipizzate + esecutori con proiezioni limitate
# ============================================================================

def _limite(args: Dict[str, Any]) -> int:
    try:
        n = int(args.get("limite", MAX_RISULTATI_DEFAULT))
    except (ValueError, TypeError):
        n = MAX_RISULTATI_DEFAULT
    return max(1, min(n, MAX_RISULTATI_TETTO))


def _range_data(args: Dict[str, Any], campo: str) -> Dict[str, Any]:
    q: Dict[str, Any] = {}
    da, a = args.get("data_da"), args.get("data_a")
    if da or a:
        q[campo] = {}
        if da:
            q[campo]["$gte"] = str(da)[:10]
        if a:
            q[campo]["$lte"] = str(a)[:10] + "~"  # include l'intera giornata
    return q


async def _tool_cerca_fatture(db, args):
    q: Dict[str, Any] = {}
    if args.get("anno"):
        q["invoice_date"] = {"$regex": f"^{int(args['anno'])}"}
    q.update(_range_data(args, "invoice_date") if not args.get("anno") else {})
    if args.get("fornitore"):
        t = str(args["fornitore"])[:60]
        q["$or"] = [
            {"supplier_name": {"$regex": t, "$options": "i"}},
            {"cedente_denominazione": {"$regex": t, "$options": "i"}},
            {"supplier_vat": t},
        ]
    if args.get("solo_non_pagate"):
        q["pagato"] = {"$ne": True}
        q["stato_pagamento"] = {"$nin": ["pagata", "paid"]}
    proj = {"_id": 0, "id": 1, "invoice_number": 1, "invoice_date": 1, "supplier_name": 1,
            "supplier_vat": 1, "total_amount": 1, "pagato": 1, "stato_pagamento": 1,
            "metodo_pagamento": 1, "prima_nota_tipo": 1, "riconciliato": 1,
            "data_pagamento": 1, "dicitura_pagamento_agente": 1}
    return await db["invoices"].find(q, proj).sort("invoice_date", -1).to_list(_limite(args))


async def _tool_cerca_fornitori(db, args):
    q: Dict[str, Any] = {}
    if args.get("testo"):
        t = str(args["testo"])[:60]
        q["$or"] = [
            {"ragione_sociale": {"$regex": t, "$options": "i"}},
            {"denominazione": {"$regex": t, "$options": "i"}},
            {"partita_iva": t},
        ]
    proj = {"_id": 0, "id": 1, "ragione_sociale": 1, "denominazione": 1, "partita_iva": 1,
            "metodo_pagamento": 1, "iban": 1, "attivo": 1, "fatture_count": 1}
    return await db["fornitori"].find(q, proj).to_list(_limite(args))


async def _tool_cerca_f24(db, args):
    q: Dict[str, Any] = {}
    if args.get("anno"):
        q["$or"] = [{"anno": int(args["anno"])},
                    {"data_scadenza": {"$regex": f"^{int(args['anno'])}"}}]
    proj = {"_id": 0, "id": 1, "data_scadenza": 1, "saldo_finale": 1, "importo_totale": 1,
            "pagato": 1, "stato": 1, "quietanza_id": 1, "tributi": 1, "anno": 1, "mese": 1,
            "contribuente": 1, "codice_fiscale": 1}
    docs = await db["f24_unificato"].find(q, proj).sort("data_scadenza", -1).to_list(_limite(args))
    # limita i tributi per non gonfiare il contesto
    for d in docs:
        if isinstance(d.get("tributi"), list) and len(d["tributi"]) > 20:
            d["tributi"] = d["tributi"][:20] + [{"nota": "...troncato"}]
    return docs


async def _tool_cerca_quietanze(db, args):
    q: Dict[str, Any] = {}
    if args.get("anno"):
        q["data_versamento"] = {"$regex": f"^{int(args['anno'])}"}
    proj = {"_id": 0, "id": 1, "data_versamento": 1, "saldo_delega": 1,
            "protocollo_telematico": 1, "f24_id": 1, "codice_fiscale": 1}
    # Collezione canonica delle quietanze F24 (fix 13/07/2026: prima leggeva
    # db["quietanze"] inesistente → tool sempre vuoto).
    return await db["quietanze_f24"].find(q, proj).sort("data_versamento", -1).to_list(_limite(args))


async def _tool_cerca_movimenti_bancari(db, args):
    q: Dict[str, Any] = dict(_range_data(args, "data"))
    if args.get("testo"):
        q["descrizione"] = {"$regex": str(args["testo"])[:60], "$options": "i"}
    if args.get("importo") is not None:
        try:
            imp = float(args["importo"])
            q["$or"] = [{"importo": {"$gte": imp - 0.01, "$lte": imp + 0.01}},
                        {"importo": {"$gte": -imp - 0.01, "$lte": -imp + 0.01}}]
        except (ValueError, TypeError):
            pass
    if args.get("solo_non_riconciliati"):
        q["riconciliato"] = {"$ne": True}
    proj = {"_id": 0, "id": 1, "data": 1, "data_contabile": 1, "importo": 1, "tipo": 1,
            "descrizione": 1, "riconciliato": 1, "fattura_id": 1}
    return await db["estratto_conto_movimenti"].find(q, proj).sort("data", -1).to_list(_limite(args))


async def _tool_cerca_cedolini(db, args):
    q: Dict[str, Any] = {}
    if args.get("anno"):
        q["anno"] = int(args["anno"])
    if args.get("mese"):
        q["mese"] = int(args["mese"])
    if args.get("dipendente"):
        t = str(args["dipendente"])[:60]
        q["$or"] = [
            {"nome_dipendente": {"$regex": t, "$options": "i"}},
            {"dipendente_nome": {"$regex": t, "$options": "i"}},
            {"codice_fiscale": t.upper()},
        ]
    proj = {"_id": 0, "id": 1, "dipendente_id": 1, "nome_dipendente": 1, "dipendente_nome": 1,
            "codice_fiscale": 1, "mese": 1, "anno": 1, "netto": 1, "lordo": 1,
            "totale_competenze": 1, "totale_trattenute": 1, "tfr_quota_mese": 1,
            "tfr_progressivo": 1, "ferie_maturate": 1, "ferie_godute": 1, "ferie_residue": 1,
            "voci": 1, "stato_pagamento": 1}
    docs = await db["cedolini"].find(q, proj).sort([("anno", -1), ("mese", -1)]).to_list(_limite(args))
    for d in docs:
        if isinstance(d.get("voci"), list) and len(d["voci"]) > 30:
            d["voci"] = d["voci"][:30] + [{"nota": "...troncato"}]
    return docs


async def _tool_cerca_dipendenti(db, args):
    q: Dict[str, Any] = {"merged_into": {"$exists": False}}
    if args.get("testo"):
        t = str(args["testo"])[:60]
        q["$or"] = [
            {"nome": {"$regex": t, "$options": "i"}},
            {"cognome": {"$regex": t, "$options": "i"}},
            {"nome_completo": {"$regex": t, "$options": "i"}},
            {"codice_fiscale": t.upper()},
        ]
    proj = {"_id": 0, "id": 1, "nome": 1, "cognome": 1, "nome_completo": 1, "codice_fiscale": 1,
            "matricola": 1, "mansione": 1, "data_assunzione": 1, "data_cessazione": 1,
            "tfr_maturato": 1, "in_carico": 1}
    return await db["dipendenti"].find(q, proj).to_list(_limite(args))


async def _tool_cerca_verbali(db, args):
    q: Dict[str, Any] = {}
    if args.get("targa"):
        q["targa"] = {"$regex": str(args["targa"])[:10], "$options": "i"}
    if args.get("numero_verbale"):
        q["numero_verbale"] = {"$regex": str(args["numero_verbale"])[:30], "$options": "i"}
    if args.get("stato"):
        q["stato"] = str(args["stato"])[:40]
    proj = {"_id": 0, "id": 1, "numero_verbale": 1, "targa": 1, "importo": 1, "data_verbale": 1,
            "data_infrazione": 1, "stato": 1, "dipendente_id": 1, "conducente": 1,
            "pagato_da_societa": 1, "trattenuta_stato": 1}
    return await db["verbali_noleggio"].find(q, proj).sort("data_verbale", -1).to_list(_limite(args))


# Tetto piu' basso per i tool del noleggio: la flotta e' piccola, 30 bastano.
MAX_RISULTATI_NOLEGGIO = 30


async def _tool_cerca_veicoli_noleggio(db, args):
    q: Dict[str, Any] = {}
    if args.get("targa"):
        q["targa"] = {"$regex": str(args["targa"])[:10], "$options": "i"}
    if args.get("stato_contratto"):
        q["stato_contratto"] = str(args["stato_contratto"])[:40]
    if args.get("driver"):
        t = str(args["driver"])[:60]
        # driver corrente O presente nello storico assegnazioni
        q["$or"] = [
            {"driver": {"$regex": t, "$options": "i"}},
            {"assegnazioni.driver": {"$regex": t, "$options": "i"}},
        ]
    # `assegnazioni` incluso apposta: e' lo storico [{driver, dal, al}] che
    # permette di rispondere a "chi aveva la targa X in data Y".
    proj = {"_id": 0, "targa": 1, "marca": 1, "modello": 1, "driver": 1, "driver_id": 1,
            "fornitore_noleggio": 1, "stato_contratto": 1, "canone_mensile": 1,
            "canone_previsto": 1, "data_inizio": 1, "data_fine": 1, "assegnazioni": 1,
            "note": 1}
    limite = min(_limite(args), MAX_RISULTATI_NOLEGGIO)
    return await db["veicoli_noleggio"].find(q, proj).sort("targa", 1).to_list(limite)


async def _tool_cerca_verbali_noleggio(db, args):
    """Unisce verbali da posta (verbali_noleggio) e da fatture noleggiatori
    (verbali_noleggio_completi), deduplicati per numero_verbale — stessa
    logica di _get_verbali_completi_per_targa in app/routers/noleggio.py."""
    limite = min(_limite(args), MAX_RISULTATI_NOLEGGIO)

    q_posta: Dict[str, Any] = {}
    q_fatture: Dict[str, Any] = {}
    if args.get("targa"):
        t = str(args["targa"])[:10]
        q_posta["targa"] = {"$regex": t, "$options": "i"}
        q_fatture["targa"] = {"$regex": t, "$options": "i"}
    if args.get("numero_verbale"):
        n = str(args["numero_verbale"])[:30]
        q_posta["numero_verbale"] = {"$regex": n, "$options": "i"}
        q_fatture["numero_verbale"] = {"$regex": n, "$options": "i"}
    if args.get("stato"):
        q_posta["stato"] = str(args["stato"])[:40]
        q_fatture["stato_pagamento"] = str(args["stato"])[:40]
    if args.get("anno"):
        anno = int(args["anno"])
        q_posta["$or"] = [{"data_verbale": {"$regex": f"^{anno}"}},
                          {"created_at": {"$regex": f"^{anno}"}}]
        q_fatture["anno"] = anno

    # MAI i PDF nel contesto del modello: restano lato server.
    proj_no_pdf = {"_id": 0, "pdf_data": 0, "pdf_allegati": 0, "quietanza_pdf": 0}
    per_numero: Dict[str, Dict[str, Any]] = {}

    posta = await db["verbali_noleggio"].find(q_posta, proj_no_pdf) \
        .sort("data_verbale", -1).to_list(limite * 3)
    for v in posta:
        numero = v.get("numero_verbale") or v.get("numero_verbale_old")
        if not numero:
            continue
        per_numero[numero] = {
            "numero_verbale": numero,
            "targa": v.get("targa"),
            "data_verbale": v.get("data_verbale") or (v.get("created_at") or "")[:10],
            "importo": float(v.get("importo") or 0),
            "stato": v.get("stato"),
            "pagato": v.get("stato") == "pagato",
            "conducente": v.get("conducente"),
            "dipendente_id": v.get("dipendente_id"),
            "trattenuta_stato": v.get("trattenuta_stato"),
            "fattura_id": v.get("fattura_id"),
            "fattura_numero": v.get("fattura_numero"),
            "ha_ricevuta": bool(v.get("pdf_ricevuta_path") or v.get("quietanza_ricevuta")),
            "fonte": "posta",
        }

    completi = await db["verbali_noleggio_completi"].find(q_fatture, proj_no_pdf) \
        .sort("data_verbale", -1).to_list(limite * 3)
    for v in completi:
        numero = v.get("numero_verbale")
        if not numero:
            continue
        esistente = per_numero.get(numero, {})
        stato_pagamento = v.get("stato_pagamento")
        per_numero[numero] = {
            **esistente,
            "numero_verbale": numero,
            "targa": esistente.get("targa") or v.get("targa"),
            "data_verbale": esistente.get("data_verbale") or v.get("data_verbale") or v.get("data"),
            "importo": esistente.get("importo") or float(v.get("importo") or 0),
            "stato": esistente.get("stato") or stato_pagamento,
            "pagato": esistente.get("pagato", False) or stato_pagamento == "pagato",
            "fattura_id": esistente.get("fattura_id") or v.get("fattura_id"),
            "fattura_numero": esistente.get("fattura_numero") or v.get("numero_fattura"),
            "ha_ricevuta": esistente.get("ha_ricevuta", False),
            "fonte": "posta+fattura" if esistente else "fattura",
        }

    ordinati = sorted(per_numero.values(),
                      key=lambda x: x.get("data_verbale") or "", reverse=True)
    return ordinati[:limite]


async def _tool_cerca_corrispettivi(db, args):
    q: Dict[str, Any] = dict(_range_data(args, "data"))
    proj = {"_id": 0, "id": 1, "data": 1, "totale": 1, "totale_manuale": 1, "totale_xml": 1,
            "pagato_contanti": 1, "pagato_pos": 1, "pagato_elettronico": 1, "stato": 1,
            "data_prevista_accredito": 1, "stato_accredito": 1}
    return await db["corrispettivi"].find(q, proj).sort("data", -1).to_list(_limite(args))


async def _tool_cerca_movimenti_prima_nota(db, args):
    registro = "prima_nota_banca" if str(args.get("registro", "cassa")).lower() == "banca" else "prima_nota_cassa"
    q: Dict[str, Any] = dict(_range_data(args, "data"))
    q["status"] = {"$nin": ["deleted", "archived"]}
    if args.get("testo"):
        q["descrizione"] = {"$regex": str(args["testo"])[:60], "$options": "i"}
    proj = {"_id": 0, "id": 1, "data": 1, "tipo": 1, "importo": 1, "descrizione": 1,
            "categoria": 1, "fattura_id": 1, "corrispettivo_id": 1, "source": 1, "created_at": 1}
    return await db[registro].find(q, proj).sort("data", -1).to_list(_limite(args))


async def _tool_cerca_alert(db, args):
    q: Dict[str, Any] = {}
    if args.get("solo_aperti", True):
        q["$or"] = [{"stato": "aperto"}, {"risolto": False}]
    proj = {"_id": 0, "id": 1, "codice": 1, "tipo": 1, "titolo": 1, "messaggio": 1,
            "descrizione": 1, "severita": 1, "stato": 1, "modulo": 1, "created_at": 1}
    return await db["alerts"].find(q, proj).sort("created_at", -1).to_list(_limite(args))


async def _tool_cerca_documenti(db, args):
    q: Dict[str, Any] = {}
    if args.get("testo"):
        q["filename"] = {"$regex": re.escape(str(args["testo"])[:60]), "$options": "i"}
    if args.get("categoria"):
        q["category"] = str(args["categoria"])[:40]
    if args.get("solo_errori"):
        q["status"] = "errore"
    # MAI raw_content_b64: il contenuto originale resta lato server.
    proj = {"_id": 0, "id": 1, "filename": 1, "category": 1, "status": 1, "source": 1,
            "created_at": 1, "file_size": 1}
    # Collezione canonica hub documenti (fix 13/07/2026: prima leggeva
    # db["documenti_scaricati"] inesistente → tool sempre vuoto).
    return await db["documents_inbox"].find(q, proj).sort("created_at", -1).to_list(_limite(args))


async def _tool_spiega_f24(db, args):
    """Analisi tracciabile di un F24 col motore tributi (specifica
    memoria/SPECIFICA_F24_CEDOLINI_IRES_IRAP_CHAT.md): classificazione per
    natura/ente/deducibilità, scadenza naturale, ritardo, tipo versamento;
    con mese+anno valuta anche l'associazione ai cedolini (§15)."""
    from app.engines import tributi_engine as te
    f24_id = str(args.get("f24_id") or "").strip()
    if not f24_id:
        return {"errore": "indicare f24_id"}
    doc = None
    for coll in ("f24_commercialista", "f24_unificato"):
        doc = await db[coll].find_one({"id": f24_id}, {"_id": 0, "pdf_data": 0})
        if doc:
            break
    if not doc:
        return {"errore": f"F24 {f24_id} non trovato"}
    out = te.classifica_f24(doc)
    out["file"] = doc.get("file_name") or doc.get("filename")
    if args.get("mese") and args.get("anno"):
        out["associazione_cedolini"] = te.valuta_associazione_cedolini(
            doc, int(args["mese"]), int(args["anno"])
        )
    return out


async def _tool_doppi_pagamenti_f24(db, args):
    """Scansione POSSIBILE DOPPIO PAGAMENTO (coppie DM10↔RC01 entrambe
    pagate per lo stesso debito, §23 della specifica)."""
    from app.routers.f24_analisi import scan_doppi_pagamenti
    return await scan_doppi_pagamenti()


async def _tool_spiega_iva_fattura(db, args):
    """Spiegazione TRACCIABILE dell'attribuzione IVA di una fattura di acquisto
    (SPECIFICA_IVA.md §20): quando è stata ricevuta, a quale periodo IVA è
    attribuita per competenza e con quale regola, se e in quale liquidazione è
    stata effettivamente utilizzata — così si vede perché NON viene conteggiata
    due volte."""
    from app.engines import iva_fatture, iva_engine
    fid = str(args.get("fattura_id") or "").strip()
    if not fid:
        return {"errore": "indicare fattura_id"}
    inv = await db["invoices"].find_one(
        {"id": fid}, {"_id": 0, "pdf_data": 0, "xml_content": 0, "xml_base64": 0}
    )
    if not inv:
        return {"errore": f"Fattura {fid} non trovata"}

    campi = iva_fatture.campi_iva_da_fattura(inv)
    data_ric = campi.get("data_ricezione") or inv.get("data_ricezione")
    periodo_attr = inv.get("periodo_iva_attribuito") or campi.get("periodo_iva_attribuito")
    regola = inv.get("regola_iva_applicata") or campi.get("regola_iva_applicata")
    utilizzata = bool(inv.get("iva_utilizzata"))
    periodo_uso = inv.get("periodo_iva_utilizzato")
    liq_id = inv.get("liquidazione_id")

    liq_stato = None
    if liq_id:
        liq_doc = await db["liquidazioni_iva"].find_one(
            {"id": liq_id}, {"_id": 0, "stato": 1, "periodo": 1}
        )
        if liq_doc:
            liq_stato = liq_doc.get("stato")
            periodo_uso = periodo_uso or liq_doc.get("periodo")

    regole_testo = {
        iva_engine.STESSO_MESE: "operazione e ricezione nello stesso mese",
        iva_engine.ENTRO_15_MESE_SUCCESSIVO: "ricevuta e registrata entro il 15 del mese successivo (stesso anno)",
        iva_engine.RICEVUTA_DOPO_IL_15: "ricevuta dopo il 15 del mese successivo",
        iva_engine.OPERAZIONE_ANNO_PRECEDENTE: "operazione dell'anno precedente: mai retroattribuita a dicembre",
        "CORREZIONE_MANUALE": "periodo corretto manualmente dall'amministratore",
    }
    narrazione = []
    if data_ric:
        narrazione.append(f"Ricevuta il {data_ric}.")
    if periodo_attr:
        motivo = regole_testo.get(regola, regola or "")
        narrazione.append(
            f"IVA attribuita per competenza al periodo {periodo_attr}"
            + (f" ({motivo})." if motivo else ".")
        )
    if utilizzata:
        narrazione.append(
            f"IVA già utilizzata nella liquidazione di {periodo_uso or 'un periodo precedente'}"
            + (f" ({liq_stato})" if liq_stato else "")
            + ": non viene conteggiata di nuovo."
        )
    else:
        narrazione.append("IVA non ancora utilizzata in alcuna liquidazione: disponibile per il calcolo o la verifica annuale.")

    return {
        "fattura_id": fid,
        "fornitore": inv.get("supplier_name"),
        "numero": inv.get("invoice_number"),
        "data_documento": inv.get("data_documento") or inv.get("invoice_date"),
        "data_ricezione": data_ric,
        "periodo_iva_attribuito": periodo_attr,
        "regola_applicata": regola,
        "iva_detraibile": campi.get("iva_detraibile") or inv.get("iva"),
        "iva_utilizzata": utilizzata,
        "periodo_iva_utilizzato": periodo_uso,
        "liquidazione_id": liq_id,
        "liquidazione_stato": liq_stato,
        "spiegazione": " ".join(narrazione),
    }


_TOOL_EXECUTORS = {
    "cerca_fatture": _tool_cerca_fatture,
    "spiega_f24": _tool_spiega_f24,
    "spiega_iva_fattura": _tool_spiega_iva_fattura,
    "doppi_pagamenti_f24": _tool_doppi_pagamenti_f24,
    "cerca_fornitori": _tool_cerca_fornitori,
    "cerca_f24": _tool_cerca_f24,
    "cerca_quietanze": _tool_cerca_quietanze,
    "cerca_movimenti_bancari": _tool_cerca_movimenti_bancari,
    "cerca_cedolini": _tool_cerca_cedolini,
    "cerca_dipendenti": _tool_cerca_dipendenti,
    "cerca_verbali": _tool_cerca_verbali,
    "cerca_veicoli_noleggio": _tool_cerca_veicoli_noleggio,
    "cerca_verbali_noleggio": _tool_cerca_verbali_noleggio,
    "cerca_corrispettivi": _tool_cerca_corrispettivi,
    "cerca_movimenti_prima_nota": _tool_cerca_movimenti_prima_nota,
    "cerca_alert": _tool_cerca_alert,
    "cerca_documenti": _tool_cerca_documenti,
}

def _documenti_citati_da_tool(tool_name: str, risultato: Any) -> List[Dict[str, Any]]:
    """Trasforma i risultati di un tool di ricerca in 'documenti citati' con
    link di download e pagina di riferimento, così la chat può offrire
    'Scarica' e 'Vai a'. Solo i tipi con un documento scaricabile per solo id."""
    if not isinstance(risultato, list):
        return []
    out: List[Dict[str, Any]] = []
    for r in risultato[:5]:
        if not isinstance(r, dict):
            continue
        rid = r.get("id")
        if not rid:
            continue
        if tool_name == "cerca_cedolini":
            nome = r.get("nome_dipendente") or r.get("dipendente_nome") or "dipendente"
            per = "/".join(str(r.get(k)) for k in ("mese", "anno") if r.get(k))
            out.append({"tipo": "cedolino", "id": rid,
                        "etichetta": f"Cedolino {nome} {per}".strip(),
                        "download_url": f"/api/cedolini/{rid}/pdf",
                        "page_url": "/riconciliazione/stipendi"})
        elif tool_name == "cerca_fatture":
            num = r.get("invoice_number") or ""
            forn = r.get("supplier_name") or ""
            out.append({"tipo": "fattura", "id": rid,
                        "etichetta": f"Fattura {num} {forn}".strip(),
                        "download_url": f"/api/fatture-ricevute/fattura/{rid}/view-assoinvoice",
                        "page_url": "/fatture"})
        elif tool_name == "cerca_f24":
            out.append({"tipo": "f24", "id": rid,
                        "etichetta": f"F24 {r.get('data_versamento') or ''}".strip(),
                        "download_url": f"/api/f24-public/pdf/{rid}",
                        "page_url": "/riconciliazione/f24"})
        elif tool_name == "cerca_documenti":
            out.append({"tipo": "documento", "id": rid,
                        "etichetta": r.get("filename") or "Documento",
                        "download_url": f"/api/documenti/documento/{rid}/download",
                        "page_url": "/documenti"})
    return out


_S = {"type": "string"}
_I = {"type": "integer"}
_B = {"type": "boolean"}
_N = {"type": "number"}
_LIM = {"limite": {**_I, "description": f"max risultati (default {MAX_RISULTATI_DEFAULT}, tetto {MAX_RISULTATI_TETTO})"}}

TOOLS_SCHEMA: List[Dict[str, Any]] = [
    {"name": "cerca_fatture",
     "description": "Cerca fatture fornitori (numero, data, fornitore, importo, stato pagamento, metodo).",
     "input_schema": {"type": "object", "properties": {
         "anno": _I, "data_da": _S, "data_a": _S, "fornitore": {**_S, "description": "nome o P.IVA"},
         "solo_non_pagate": _B, **_LIM}}},
    {"name": "cerca_fornitori",
     "description": "Cerca fornitori in anagrafica (ragione sociale, P.IVA, metodo pagamento).",
     "input_schema": {"type": "object", "properties": {"testo": _S, **_LIM}}},
    {"name": "cerca_f24",
     "description": "Cerca F24 con i loro tributi, stato pagamento e quietanza collegata.",
     "input_schema": {"type": "object", "properties": {"anno": _I, **_LIM}}},
    {"name": "cerca_quietanze",
     "description": "Cerca quietanze F24 (protocollo, data versamento, saldo delega, F24 collegato).",
     "input_schema": {"type": "object", "properties": {"anno": _I, **_LIM}}},
    {"name": "spiega_f24",
     "description": "Spiega un F24 in modo TRACCIABILE: classifica ogni riga per natura "
                    "(costo/ritenuta/credito/sanzione/regolarizzazione/pagamento), ente e "
                    "deducibilità; calcola scadenza naturale, giorni di ritardo, stato e tipo "
                    "versamento (ordinario/ravvedimento/RC01). Con mese+anno valuta anche se è "
                    "associabile ai cedolini di quel periodo, con motivazione. Il saldo F24 non "
                    "è mai automaticamente un costo: usa questo strumento per spiegare perché.",
     "input_schema": {"type": "object", "properties": {
         "f24_id": {**_S, "description": "id del modello F24"},
         "mese": {**_I, "description": "mese dei cedolini per la verifica di associazione"},
         "anno": {**_I, "description": "anno dei cedolini"}},
      "required": ["f24_id"]}},
    {"name": "spiega_iva_fattura",
     "description": "Spiega in modo TRACCIABILE l'IVA di una fattura di acquisto (SPECIFICA_IVA): "
                    "quando è stata ricevuta, a quale periodo IVA è attribuita per competenza e con "
                    "quale regola (stesso mese / entro il 15 / dopo il 15 / cambio anno), se e in quale "
                    "liquidazione è già stata utilizzata — così spieghi perché una fattura ricevuta in un "
                    "mese può competere al mese precedente e non essere conteggiata due volte.",
     "input_schema": {"type": "object", "properties": {
         "fattura_id": {**_S, "description": "id della fattura di acquisto"}},
      "required": ["fattura_id"]}},
    {"name": "doppi_pagamenti_f24",
     "description": "Cerca possibili DOPPI PAGAMENTI: coppie F24 ordinario (DM10) e F24 di "
                    "regolarizzazione (RC01) dello stesso periodo entrambe pagate, con quota "
                    "capitale potenzialmente versata due volte e quota sanzioni/interessi.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "cerca_movimenti_bancari",
     "description": "Cerca movimenti dell'estratto conto bancario per data, testo o importo.",
     "input_schema": {"type": "object", "properties": {
         "data_da": _S, "data_a": _S, "testo": _S, "importo": _N,
         "solo_non_riconciliati": _B, **_LIM}}},
    {"name": "cerca_cedolini",
     "description": "Cerca cedolini/buste paga per dipendente (nome o CF), mese e anno.",
     "input_schema": {"type": "object", "properties": {
         "dipendente": _S, "anno": _I, "mese": _I, **_LIM}}},
    {"name": "cerca_dipendenti",
     "description": "Cerca dipendenti in anagrafica (nome, cognome, codice fiscale, matricola).",
     "input_schema": {"type": "object", "properties": {"testo": _S, **_LIM}}},
    {"name": "cerca_verbali",
     "description": "Cerca verbali/multe (numero, targa, stato, trattenuta).",
     "input_schema": {"type": "object", "properties": {
         "targa": _S, "numero_verbale": _S, "stato": _S, **_LIM}}},
    {"name": "cerca_veicoli_noleggio",
     "description": "Cerca i veicoli a noleggio della flotta: targa, marca/modello, driver corrente, "
                    "fornitore, canone mensile, stato contratto e storico assegnazioni [{driver, dal, al}] "
                    "(usalo per 'chi aveva la targa X in data Y').",
     "input_schema": {"type": "object", "properties": {
         "targa": _S,
         "stato_contratto": {**_S, "description": "es. attivo | cessato"},
         "driver": {**_S, "description": "nome del driver, corrente o nello storico"},
         "limite": {**_I, "description": f"max risultati (tetto {MAX_RISULTATI_NOLEGGIO})"}}}},
    {"name": "cerca_verbali_noleggio",
     "description": "Cerca i verbali/multe dei veicoli a noleggio unendo i due canali (posta e fatture "
                    "noleggiatori), deduplicati per numero verbale: stato pagamento, conducente, "
                    "trattenuta, fattura collegata.",
     "input_schema": {"type": "object", "properties": {
         "targa": _S, "numero_verbale": _S,
         "stato": {**_S, "description": "es. pagato | da_pagare"}, "anno": _I,
         "limite": {**_I, "description": f"max risultati (tetto {MAX_RISULTATI_NOLEGGIO})"}}}},
    {"name": "cerca_corrispettivi",
     "description": "Cerca corrispettivi giornalieri (totale, contanti, POS, stato accredito POS).",
     "input_schema": {"type": "object", "properties": {"data_da": _S, "data_a": _S, **_LIM}}},
    {"name": "cerca_movimenti_prima_nota",
     "description": "Cerca movimenti in Prima Nota Cassa o Banca per periodo o testo.",
     "input_schema": {"type": "object", "properties": {
         "registro": {**_S, "description": "cassa | banca"},
         "data_da": _S, "data_a": _S, "testo": _S, **_LIM}}},
    {"name": "cerca_alert",
     "description": "Cerca avvisi/alert del sistema (aperti per default).",
     "input_schema": {"type": "object", "properties": {"solo_aperti": _B, **_LIM}}},
    {"name": "cerca_documenti",
     "description": "Cerca documenti importati (nome file, categoria, stato di lavorazione).",
     "input_schema": {"type": "object", "properties": {
         "testo": _S, "categoria": _S, "solo_errori": _B, **_LIM}}},
    {"name": "componi_risposta",
     "description": "OBBLIGATORIO come ultima azione: componi la risposta strutturata per l'utente.",
     "input_schema": {"type": "object", "properties": {
         "risposta_testuale": {**_S, "description": "risposta chiara e diretta in italiano"},
         "stato": {**_S, "description": "stato amministrativo/contabile sintetico"},
         "livello_affidabilita": {**_S, "enum": ["certo", "probabile", "dubbio"]},
         "documenti_consultati": {"type": "array", "items": _S,
                                   "description": "fonti interne usate (es. '12 fatture 2026', 'cedolino 05/2026 Rossi')"},
         "dati_mancanti": {"type": "array", "items": _S},
         "anomalie": {"type": "array", "items": _S},
         "azioni_proposte": {"type": "array", "items": _S},
         "richiede_conferma_utente": _B,
     }, "required": ["risposta_testuale", "livello_affidabilita"]}},
]


async def _log_tool_call(db, session_id: str, nome: str, params: Dict[str, Any],
                          esito: str, durata_ms: int) -> None:
    try:
        await db["chat_tool_calls"].insert_one({
            "id": str(uuid.uuid4()),
            "conversation_id": session_id,
            "nome_strumento": nome,
            "parametri_sanitizzati": {k: v for k, v in (params or {}).items() if k != "raw"},
            "esito": esito,
            "durata_ms": durata_ms,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        pass


# ============================================================================
# AGENT LOOP
# ============================================================================

async def rispondi(domanda: str, session_id: str, db,
                    storico: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Risponde a una domanda con il motore AI. Ritorna la risposta strutturata.

    `storico`: lista [{domanda, risposta}] dei turni precedenti della stessa
    sessione, per dare continuita' alla conversazione.
    """
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY", "").strip())
    system = _system_prompt(domanda)

    messages: List[Dict[str, Any]] = []
    for voce in (storico or [])[-STORICO_MESSAGGI_CONTESTO:]:
        if voce.get("domanda"):
            messages.append({"role": "user", "content": str(voce["domanda"])[:2000]})
        if voce.get("risposta"):
            messages.append({"role": "assistant", "content": str(voce["risposta"])[:2000]})
    messages.append({"role": "user", "content": domanda})

    strumenti_usati: List[str] = []
    documenti_citati: List[Dict[str, Any]] = []

    def _aggiungi_citati(nuovi):
        for d in nuovi:
            if not any(c["tipo"] == d["tipo"] and c["id"] == d["id"] for c in documenti_citati):
                documenti_citati.append(d)

    for _ in range(MAX_ITERAZIONI_TOOL):
        response = await client.messages.create(
            model=_model_name(),
            max_tokens=2000,
            system=system,
            messages=messages,
            tools=TOOLS_SCHEMA,
        )

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if not tool_uses:
            # Il modello ha risposto in testo libero senza componi_risposta:
            # accettiamo comunque, con affidabilita' prudente.
            testo = "".join(b.text for b in response.content if b.type == "text").strip()
            return {
                "risposta_testuale": testo or "Non sono riuscito a produrre una risposta.",
                "livello_affidabilita": "dubbio",
                "documenti_consultati": strumenti_usati,
                "documenti_citati": documenti_citati,
                "dati_mancanti": [], "anomalie": [], "azioni_proposte": [],
                "richiede_conferma_utente": False,
                "motore": "ai",
            }

        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for tu in tool_uses:
            if tu.name == "componi_risposta":
                strutturata = dict(tu.input or {})
                strutturata.setdefault("documenti_consultati", [])
                strutturata["documenti_consultati"] = list(strutturata["documenti_consultati"]) + \
                    [s for s in strumenti_usati if s not in strutturata["documenti_consultati"]]
                strutturata.setdefault("livello_affidabilita", "dubbio")
                strutturata.setdefault("dati_mancanti", [])
                strutturata.setdefault("anomalie", [])
                strutturata.setdefault("azioni_proposte", [])
                strutturata.setdefault("richiede_conferma_utente", False)
                strutturata["documenti_citati"] = documenti_citati
                strutturata["motore"] = "ai"
                return strutturata

            executor = _TOOL_EXECUTORS.get(tu.name)
            t0 = time.monotonic()
            try:
                if executor is None:
                    risultato: Any = {"errore": f"strumento sconosciuto: {tu.name}"}
                    esito = "sconosciuto"
                else:
                    risultato = await executor(db, tu.input or {})
                    esito = "ok"
                    strumenti_usati.append(
                        f"{tu.name}({len(risultato) if isinstance(risultato, list) else 1} risultati)"
                    )
                    _aggiungi_citati(_documenti_citati_da_tool(tu.name, risultato))
            except Exception as e:
                logger.exception(f"Chat AI: errore strumento {tu.name}")
                risultato = {"errore": str(e)[:300]}
                esito = "errore"
            durata_ms = int((time.monotonic() - t0) * 1000)
            await _log_tool_call(db, session_id, tu.name, tu.input or {}, esito, durata_ms)

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": json.dumps(risultato, ensure_ascii=False, default=str)[:30000],
            })

        messages.append({"role": "user", "content": tool_results})

    return {
        "risposta_testuale": "Ho raggiunto il limite di ricerche senza arrivare a una "
                              "conclusione affidabile. Prova a restringere la domanda "
                              "(periodo, fornitore o dipendente specifico).",
        "livello_affidabilita": "dubbio",
        "documenti_consultati": strumenti_usati,
        "dati_mancanti": ["conclusione non raggiunta entro il limite di iterazioni"],
        "anomalie": [], "azioni_proposte": [], "richiede_conferma_utente": False,
        "motore": "ai",
    }
