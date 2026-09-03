"""
Router: ordini_fornitori
Gestisce ordini ai fornitori creati dal tracciabilità (tablet/telefono).
Gli ordini vengono salvati con stato='bozza' e source='tracciabilita',
poi completati e inviati dall'amministratore via listino-prezzi-merci.
"""

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
from typing import List, Optional
import re
import uuid
from datetime import datetime, timezone, timedelta

from app.lotti.db import database as db

router = APIRouter(prefix="/ordini-fornitori", tags=["Ordini Fornitori"])


# ── Modelli ─────────────────────────────────────────────────
class ProdottoOrdine(BaseModel):
    prodotto_id: str
    nome: str
    fornitore: str = ""
    quantita: float = 1.0
    unita: str = "kg"
    prezzo_ultimo: float = 0.0
    note: str = ""
    richiesto_da: str = ""  # chi ha messo il prodotto in ordine (tracciabilità)


class RicettaDaProdurre(BaseModel):
    ricetta_id: str
    nome: str
    reparto: str = ""
    quantita: float = 1.0  # numero di lotti da produrre
    note: str = ""


class OrdineCreate(BaseModel):
    reparto: str = ""
    operatore: str = ""
    prodotti: List[ProdottoOrdine]
    ricette_da_produrre: List[RicettaDaProdurre] = []
    note_operatore: str = ""


# ── Endpoints ───────────────────────────────────────────────
@router.get("/prodotti-suggeriti")
async def get_prodotti_suggeriti(fornitore: Optional[str] = Query(None), limit: int = Query(500)):
    """
    Ritorna prodotti dal dizionario_prodotti ordinati per rilevanza:
    1. Prodotti sotto scorta (quantita_disponibile_kg < soglia)
    2. Prodotti più acquistati (conteggio_acquisti desc)
    Solo prodotti con prezzo_kg > 0 (reali, non ERP-only).
    """
    filtro = {"prezzo_kg": {"$gt": 0}}
    if fornitore:
        filtro["fornitore"] = fornitore

    prodotti = (
        await db.dizionario_prodotti.find(filtro, {"_id": 0})
        .sort([("conteggio_acquisti", -1), ("ultima_fattura_data", -1)])
        .limit(limit)
        .to_list(limit)
    )

    # Arricchisce con flag sotto_scorta
    risultato = []
    for p in prodotti:
        disp = float(p.get("quantita_disponibile_kg") or 0)
        scorta_min = float(p.get("scorta_minima") or 0)

        # Heuristic: sotto scorta se disponibile < 1 kg oppure < scorta_minima impostata
        sotto_scorta = disp < 1.0 if scorta_min == 0 else disp < scorta_min

        risultato.append(
            {
                "id": p.get("id"),
                "nome": p.get("nome_canonico") or p.get("nome_normalizzato", "").title(),
                "nome_normalizzato": p.get("nome_normalizzato"),
                "fornitore": p.get("fornitore", ""),
                "categoria": p.get("categoria_canonica") or p.get("categoria") or "Altro",
                "prezzo_kg": float(p.get("prezzo_kg") or 0),
                "unita_confezione": p.get("unita_confezione", "kg"),
                "peso_confezione": float(p.get("peso_confezione") or 1),
                "ultima_fattura_data": p.get("ultima_fattura_data", ""),
                "quantita_disponibile_kg": disp,
                "scorta_minima": scorta_min,
                "sotto_scorta": sotto_scorta,
                "conteggio_acquisti": int(p.get("conteggio_acquisti") or 0),
                "foto_url": p.get("foto_url"),
            }
        )

    # Ordina: sotto scorta prima, poi per conteggio_acquisti
    risultato.sort(key=lambda x: (not x["sotto_scorta"], -x["conteggio_acquisti"]))
    return risultato


class OrdineCreateFull(OrdineCreate):
    source: str = "tracciabilita"  # "tracciabilita" | "manuale"


@router.post("")
async def crea_ordine(payload: OrdineCreateFull):
    """Crea un nuovo ordine. source='tracciabilita' (automatico) o 'manuale'."""
    if not payload.prodotti:
        raise HTTPException(status_code=400, detail="Nessun prodotto selezionato")

    now = datetime.now(timezone.utc).isoformat()
    oggi = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Aggiunte dai CATALOGHI (Acquaviva/Alpha): si fondono nella bozza del giorno
    # dello stesso catalogo invece di creare una bozza per ogni tocco.
    if (payload.source or "").startswith("catalogo"):
        esistente = await db.ordini_fornitori.find_one(
            {"source": payload.source, "data_ordine": oggi, "stato": "bozza"})
        if esistente:
            righe = esistente.get("prodotti", [])
            for p in payload.prodotti:
                riga = p.model_dump()
                stessa = next((r for r in righe if r.get("prodotto_id") == riga.get("prodotto_id")), None)
                if stessa:
                    stessa["quantita"] = float(stessa.get("quantita", 0)) + float(riga.get("quantita", 0))
                else:
                    righe.append(riga)
            righe = await arricchisci_iva_righe(righe)
            await db.ordini_fornitori.update_one(
                {"id": esistente["id"]},
                {"$set": {"prodotti": righe, "totali": calcola_totali_ordine(righe),
                           "updated_at": now}})
            return {"success": True, "ordine_id": esistente["id"], "unito_a_bozza": True}

    ordine = {
        "id": str(uuid.uuid4()),
        "data_ordine": oggi,
        "stato": "bozza",
        "source": payload.source,
        "reparto": payload.reparto,
        "operatore": payload.operatore,
        "prodotti": await arricchisci_iva_righe([p.model_dump() for p in payload.prodotti]),
        "ricette_da_produrre": [r.model_dump() for r in payload.ricette_da_produrre],
        "note_operatore": payload.note_operatore,
        "created_at": now,
        "updated_at": now,
    }
    ordine["totali"] = calcola_totali_ordine(ordine["prodotti"])
    await db.ordini_fornitori.insert_one(ordine)
    ordine.pop("_id", None)
    return {"success": True, "ordine_id": ordine["id"], "ordine": ordine}


async def _iva_pct_per_nome(nome: str) -> float:
    """Aliquota IVA del prodotto dal dizionario (salvata dagli import XML).
    0 = sconosciuta."""
    if not nome:
        return 0.0
    doc = await db.dizionario_prodotti.find_one(
        {"iva_pct": {"$gt": 0}, "$or": [
            {"nome_normalizzato": nome.strip().lower()},
            {"nome_canonico": {"$regex": f"^{re.escape(nome)}$", "$options": "i"}},
            {"ingrediente_canonico": {"$regex": f"^{re.escape(nome)}$", "$options": "i"}},
        ]},
        {"_id": 0, "iva_pct": 1},
    )
    return float(doc["iva_pct"]) if doc else 0.0


async def arricchisci_iva_righe(righe: list) -> list:
    """Completa riga.iva_pct dal dizionario dove manca."""
    for r in righe or []:
        if not r.get("iva_pct"):
            r["iva_pct"] = await _iva_pct_per_nome(r.get("nome", ""))
    return righe


def calcola_totali_ordine(righe: list) -> dict:
    """Totali da gestionale: imponibile = Σ prezzo×qta; IVA per riga con la
    sua aliquota; totale = imponibile + IVA. Le righe senza prezzo o senza
    aliquota vengono conteggiate a parte (trasparenza, niente numeri finti)."""
    imponibile = iva = 0.0
    senza_prezzo = senza_iva = 0
    for r in righe or []:
        prezzo = float(r.get("prezzo_ultimo") or 0)
        qta = float(r.get("quantita") or 0)
        if prezzo <= 0 or qta <= 0:
            senza_prezzo += 1
            continue
        riga_imp = prezzo * qta
        imponibile += riga_imp
        aliquota = float(r.get("iva_pct") or 0)
        if aliquota > 0:
            iva += riga_imp * aliquota / 100.0
        else:
            senza_iva += 1
    return {"imponibile": round(imponibile, 2), "iva": round(iva, 2),
            "totale": round(imponibile + iva, 2),
            "righe_senza_prezzo": senza_prezzo, "righe_senza_iva": senza_iva}


async def _aggiorna_totali_ordine(ordine_id: str) -> dict:
    """Ricalcola e persiste i totali di un ordine (dopo ogni modifica righe)."""
    o = await db.ordini_fornitori.find_one({"id": ordine_id}, {"_id": 0, "prodotti": 1})
    if not o:
        return {}
    righe = await arricchisci_iva_righe(o.get("prodotti") or [])
    tot = calcola_totali_ordine(righe)
    await db.ordini_fornitori.update_one(
        {"id": ordine_id}, {"$set": {"prodotti": righe, "totali": tot}})
    return tot


async def aggiungi_a_bozza_riordino(nome: str, prodotto_id: str, quantita: float,
                                    unita: str = "pz", nota: str = "",
                                    richiesto_da: str = "") -> dict:
    """Mette UN prodotto nel circuito riordino (bozza per fornitore, stessa
    forma del motore automatico). Usato dalla LAVAGNA quando una consegna trova
    lo stock esaurito: prima quella richiesta moriva lì e nessuno ordinava
    (fix 02/07/2026). Dedup incrociata: se il prodotto è già in un ordine
    aperto non fa nulla."""
    from app.lotti.routers.prodotti_master import _comparatore_60gg, normalize_nome
    gia_ids, gia_nomi = await _prodotti_gia_in_ordine()
    if (prodotto_id and prodotto_id in gia_ids) or normalize_nome(nome) in gia_nomi:
        return {"ok": True, "gia_in_ordine": True}
    if not prodotto_id:
        # id univoco: righe con prodotto_id "" collidevano in modifica-quantità
        # e conferma-righe (tutte indistinguibili tra loro)
        prodotto_id = f"auto-{uuid.uuid4().hex[:12]}"

    best = None
    mp = await db.prodotti_master.find_one(
        {"nome_canonico": {"$regex": f"^{re.escape(nome)}$", "$options": "i"}},
        {"_id": 0, "prezzi_storici": 1})
    if mp:
        comp = _comparatore_60gg(mp.get("prezzi_storici", []))
        best = comp[0] if comp else None
    fornitore = (best and best["fornitore"]) or "DA ASSEGNARE"
    riga = {"prodotto_id": str(prodotto_id), "nome": nome, "fornitore": fornitore,
            "quantita": max(float(quantita) or 1, 1), "unita": unita or "pz",
            "prezzo_ultimo": (best and best["prezzo"]) or 0,
            "note": nota or "esaurito in consegna lavagna",
            "richiesto_da": richiesto_da or "sistema"}
    now = datetime.now(timezone.utc).isoformat()
    # accoda alla bozza riordino aperta di quel fornitore, se c'è; altrimenti creala
    bozza = await db.ordini_fornitori.find_one(
        {"source": "riordino_auto", "stato": "bozza", "fornitore": fornitore}, {"_id": 0, "id": 1})
    if not bozza:
        bozza = await db.ordini_fornitori.find_one(
            {"source": "riordino_auto", "stato": "bozza", "prodotti.fornitore": fornitore},
            {"_id": 0, "id": 1})
    riga["iva_pct"] = await _iva_pct_per_nome(nome)
    if bozza:
        await db.ordini_fornitori.update_one(
            {"id": bozza["id"]}, {"$push": {"prodotti": riga}, "$set": {"updated_at": now}})
        await _aggiorna_totali_ordine(bozza["id"])
        return {"ok": True, "ordine_id": bozza["id"], "accodato": True}
    ordine = {"id": str(uuid.uuid4()), "data_ordine": now[:10], "stato": "bozza",
              "source": "riordino_auto", "reparto": "", "operatore": "Sistema riordino",
              "fornitore": fornitore,
              "prodotti": [riga], "ricette_da_produrre": [],
              "note_operatore": "Riordino da lavagna: prodotto esaurito alla consegna",
              "created_at": now, "updated_at": now}
    ordine["totali"] = calcola_totali_ordine([riga])
    await db.ordini_fornitori.insert_one(ordine)
    return {"ok": True, "ordine_id": ordine["id"], "creato": True}


@router.post("/pulisci-e-rigenera-riordini")
async def pulisci_e_rigenera_riordini(request: Request, conferma: bool = False):
    """PULIZIA ARRETRATO BOZZE AUTOMATICHE (02/07/2026): i vecchi job doppioni
    hanno accumulato ~149 bozze auto-generate mai riviste (dal 15/06). Sono
    proposte rigenerabili: questo endpoint le elimina (SOLO source automatiche,
    SOLO stato bozza — le manuali non si toccano) e fa rigenerare al motore
    unico un set fresco basato sulle scorte di OGGI. Anteprima di default;
    ?conferma=true per eseguire. Il tasto sta in Controllo Dati."""
    await _richiedi_admin(request)
    # alert_mancanti ESCLUSI: derivano dalla riconciliazione fatture (merce
    # ordinata mai consegnata) e NON sono rigenerabili dalle scorte di oggi.
    AUTO = ["riordino_auto", "automatico_scorta", "automatico_lotti"]
    filtro = {"source": {"$in": AUTO}, "stato": "bozza"}
    n = await db.ordini_fornitori.count_documents(filtro)
    if not conferma:
        per_source = {}
        async for o in db.ordini_fornitori.find(filtro, {"_id": 0, "source": 1}):
            per_source[o["source"]] = per_source.get(o["source"], 0) + 1
        return {"ok": True, "anteprima": True, "bozze_da_eliminare": n,
                "per_source": per_source,
                "nota": "conferma=true per eliminare e rigenerare"}
    res = await db.ordini_fornitori.delete_many(filtro)
    rigenerate = await esegui_riordino_automatico(dry_run=False)
    return {"ok": True, "eliminate": res.deleted_count,
            "rigenerate": rigenerate.get("bozze_create", []),
            "prodotti_riordinati": rigenerate.get("prodotti_riordinati", 0)}


@router.post("/genera-riordino")
async def genera_riordino_automatico(request: Request, dry_run: bool = False):
    """RIORDINO AUTOMATICO: scandisce il magazzino bar e per ogni prodotto con
    stock <= soglia_minima propone la quantita' di riordino. Crea bozze per
    fornitore (source='riordino_auto') che il titolare valuta su 'Da inviare'.
    dry_run=true: mostra cosa verrebbe creato SENZA creare nulla.
    Anti-duplicato: salta i prodotti gia' presenti in una bozza riordino aperta."""
    await _richiedi_admin(request)
    return await esegui_riordino_automatico(dry_run)


async def _prodotti_gia_in_ordine() -> tuple:
    """Set di (prodotto_id, nome normalizzato) presenti in QUALSIASI ordine
    aperto, di QUALSIASI source. Dedup INCROCIATA (fix 02/07/2026): prima ogni
    percorso guardava solo il proprio source e lo stesso prodotto fisico poteva
    finire in due bozze diverse (riordino_auto + automatico_scorta)."""
    from app.lotti.routers.prodotti_master import normalize_nome
    # ricevuto_parziale e il legacy "inviato" sono ANCORA ordini aperti: senza
    # di essi il motore riproponeva merce già ordinata e in arrivo. Cap alto e
    # ordinato per data: con l'arretrato storico 200 doc non bastavano.
    aperte = await db.ordini_fornitori.find(
        {"stato": {"$in": ["bozza", "confermato", "inviato_fornitori",
                            "inviato_manualmente", "inviato", "ricevuto_parziale"]}},
        {"_id": 0, "prodotti.prodotto_id": 1, "prodotti.nome": 1},
        sort=[("created_at", -1)],
    ).to_list(1000)
    ids = {pp.get("prodotto_id") for o in aperte for pp in o.get("prodotti", []) if pp.get("prodotto_id")}
    nomi = {normalize_nome(pp.get("nome", "")) for o in aperte for pp in o.get("prodotti", []) if pp.get("nome")}
    return ids, nomi


GIORNI_STORICO_CONSUMI = 28   # finestra di apprendimento del consumo reale
GIORNI_COPERTURA = 7          # l'ordine proposto deve coprire una settimana


def proposta_da_consumo(consumo_medio_giornaliero: float, stock: float,
                        giorni_copertura: int = GIORNI_COPERTURA) -> float:
    """Quanto ordinare per coprire `giorni_copertura` giorni di CONSUMO REALE,
    tolto lo stock attuale (logica 'vero magazziniere', richiesta Enzo
    03/07/2026). 0 se lo stock basta già o se non c'è storico consumi.
    Funzione pura: testabile senza DB."""
    if consumo_medio_giornaliero <= 0 or giorni_copertura <= 0:
        return 0.0
    fabbisogno = consumo_medio_giornaliero * giorni_copertura
    return max(0.0, round(fabbisogno - max(stock or 0.0, 0.0), 2))


async def _consumi_medi_bar() -> dict:
    """Consumo medio giornaliero per prodotto bar dagli scarichi REALI
    (magazzino_bar_movimenti, ultimi GIORNI_STORICO_CONSUMI giorni).
    {prodotto_id: consumo_medio_giornaliero}."""
    limite = (datetime.now(timezone.utc) - timedelta(days=GIORNI_STORICO_CONSUMI)).isoformat()
    totali: dict = {}
    async for m in db.magazzino_bar_movimenti.find(
        {"tipo": "scarico", "data": {"$gte": limite}},
        {"_id": 0, "prodotto_id": 1, "quantita": 1},
    ):
        pid = m.get("prodotto_id")
        if pid:
            totali[pid] = totali.get(pid, 0.0) + float(m.get("quantita") or 0)
    return {pid: round(tot / GIORNI_STORICO_CONSUMI, 4) for pid, tot in totali.items()}


async def _giorni_non_operativi_ordini(oggi):
    """Calendario reale: festivita, ponti, ferie aziendali e chiusure manuali.
    Non usa i vecchi generatori casuali presenti nelle viste HACCP storiche."""
    from datetime import date as _date
    from app.lotti.routers.corrispettivi import festivita_anno, _info_ponte
    from app.lotti.routers.chiusure import get_ferie_aziendali
    giorni = set()
    eventi = []
    for anno in {oggi.year, oggi.year + 1}:
        for g, nome in festivita_anno(anno):
            giorni.add(g); eventi.append({"data": g.isoformat(), "nome": nome, "fonte": "festivita"})
            ponte = _info_ponte(g)
            if ponte:
                pg = _date.fromisoformat(ponte["giorno_ponte"])
                giorni.add(pg); eventi.append({"data": pg.isoformat(), "nome": ponte["tipo"], "fonte": "ponte"})
        for item in get_ferie_aziendali(anno):
            giorni.add(item["data"])
            eventi.append({"data": item["data"].isoformat(), "nome": item["nome"], "fonte": "chiusura_azienda"})
        async for item in db.chiusure_custom.find({"anno": anno}, {"_id": 0}):
            raw = str(item.get("data") or "")
            try:
                g = _date.fromisoformat(raw) if "-" in raw else datetime.strptime(raw, "%d/%m/%Y").date()
            except ValueError:
                continue
            giorni.add(g); eventi.append({"data": g.isoformat(), "nome": item.get("nome") or "Chiusura", "fonte": "chiusura_manual"})
    return giorni, eventi


async def _fattore_previsione_corrispettivi(mese: int, anno_target: int) -> dict:
    """Fattore prudente e spiegabile, ricavato solo da mesi completi passati."""
    try:
        from app.lotti.routers.corrispettivi import _campi_rilevati, _parse_data, _to_float
        campo_data, campo_importo = await _campi_rilevati()
        if not campo_data or not campo_importo:
            raise ValueError("schema corrispettivi non disponibile")
        per_anno = {}
        async for doc in db.corrispettivi.find({}, {"_id": 0, campo_data: 1, campo_importo: 1}):
            g = _parse_data(doc.get(campo_data))
            if g and g.month == mese and g.year < anno_target:
                per_anno[g.year] = per_anno.get(g.year, 0.0) + _to_float(doc.get(campo_importo))
        anni = sorted(a for a, valore in per_anno.items() if valore > 0)
        if len(anni) < 2:
            return {"fattore": 1.0, "verificato": False, "motivo": "storico corrispettivi insufficiente"}
        rapporti = [per_anno[b] / per_anno[a] for a, b in zip(anni, anni[1:]) if per_anno[a] > 0]
        fattore = max(0.75, min(sum(rapporti) / len(rapporti), 1.30))
        return {"fattore": round(fattore, 3), "verificato": True, "anni": anni,
                "motivo": f"andamento corrispettivi del mese {mese} sugli anni {anni[0]}-{anni[-1]}"}
    except Exception as exc:
        return {"fattore": 1.0, "verificato": False, "motivo": f"previsione non applicata: {str(exc)[:100]}"}


async def esegui_riordino_automatico(dry_run: bool = False):
    """MOTORE UNICO del riordino automatico (unificazione 02/07/2026): copre
    ENTRAMBI gli universi di scorta — bar (magazzino_bar_prodotti.soglia_minima)
    e materie prime (dizionario_prodotti.scorta_minima) — con dedup incrociata
    su tutti gli ordini aperti. Sostituisce anche il vecchio job 08:00
    'check_scorta_minima' che creava una bozza cumulativa parallela.

    LOGICA CALENDARIO: usa giorni e preavviso del singolo fornitore, salta
    festivita/ponti/chiusure e copre fino alla consegna successiva. La previsione
    da corrispettivi e limitata a un intervallo prudente e resta documentata su
    ogni riga. Nessun invio automatico: vengono create solo bozze."""
    import math
    from datetime import date as _date

    from zoneinfo import ZoneInfo
    ora_roma = datetime.now(ZoneInfo("Europe/Rome"))
    oggi_d = ora_roma.date()
    # DUE trigger (03/07/2026, logica "vero magazziniere"):
    # 1. SOGLIA: stock <= soglia_minima impostata a mano (come prima);
    # 2. CONSUMO: lo stock non copre GIORNI_COPERTURA giorni di consumo REALE
    #    (dagli scarichi degli ultimi 28gg) — scatta anche senza soglia.
    prods = await db.magazzino_bar_prodotti.find({}, {"_id": 0}).to_list(3000)
    consumi = await _consumi_medi_bar()
    sotto = []
    for p in prods:
        _st = float(p.get("stock", 0) or 0)
        _sg = float(p.get("soglia_minima", 0) or 0)
        _consumo = consumi.get(p.get("id"), 0.0)
        trigger_soglia = _sg > 0 and _st <= _sg
        trigger_consumo = _consumo > 0 and _st < _consumo * GIORNI_COPERTURA
        if trigger_soglia or trigger_consumo:
            p["_consumo_medio"] = _consumo
            sotto.append(p)

    gia_ids, gia_nomi = await _prodotti_gia_in_ordine()
    from app.lotti.routers.prodotti_master import normalize_nome as _nn
    sotto = [p for p in sotto
             if p.get("id") not in gia_ids and _nn(p.get("nome", "")) not in gia_nomi]

    # Per ogni prodotto sotto-scorta scelgo il MIGLIOR FORNITORE (prezzo di
    # fattura più basso e recente) col comparatore unico, e ci metto il prezzo
    # vero. Così il riordino non eredita un fornitore stantio con prezzo €0.
    from app.lotti.routers.prodotti_master import _comparatore_60gg, normalize_nome
    master = await db.prodotti_master.find({}, {"_id": 0, "nome_canonico": 1, "prezzi_storici": 1}).to_list(5000)
    best_by_key = {}
    for mp in master:
        comp = _comparatore_60gg(mp.get("prezzi_storici", []))
        if comp:
            best_by_key[normalize_nome(mp.get("nome_canonico", ""))] = comp[0]

    per_forn = {}
    for p in sotto:
        st = float(p.get("stock", 0) or 0)
        sg = float(p.get("soglia_minima", 0) or 0)
        # riordino fino a 2× soglia (come le materie prime): riordinare "fino a
        # soglia" ritriggerava un nuovo ordine da 1 pezzo il giorno dopo
        # proposta = il MAGGIORE tra il fabbisogno da soglia e quello da
        # consumo reale (copertura GIORNI_COPERTURA giorni di scarichi medi)
        consumo = float(p.get("_consumo_medio", 0) or 0)
        qta_soglia = float(p.get("quantita_riordino", 0) or 0) or (max(1, math.ceil(sg * 2 - st)) if sg > 0 else 0)
        qta_consumo = proposta_da_consumo(consumo, st)
        qta = max(qta_soglia, qta_consumo) or 1
        # miglior fornitore dal comparatore; fallback al fornitore memorizzato
        best = best_by_key.get(normalize_nome(p.get("nome", "")))
        f = (best and best["fornitore"]) or p.get("fornitore") or "DA ASSEGNARE"
        prezzo = (best and best["prezzo"]) or 0
        nota_consumo = f" · consumo reale {consumo:g}/giorno (copertura {GIORNI_COPERTURA}gg)" if consumo > 0 else ""
        per_forn.setdefault(f, []).append({
            "prodotto_id": str(p.get("id")), "nome": p.get("nome", ""), "fornitore": f,
            "quantita": qta, "unita": p.get("unita", "pz"), "prezzo_ultimo": prezzo,
            "richiesto_da": "riordino automatico",
            "note": f"stock {st:g}" + (f" / soglia {sg:g}" if sg > 0 else "") + nota_consumo
                    + (f" · {best['giorni_fa']}gg fa" if best and best.get("giorni_fa") is not None else ""),
        })
        # dedup intra-run: lo stesso prodotto fisico non deve rientrare dal
        # loop materie prime nella stessa esecuzione
        gia_ids.add(str(p.get("id")))
        gia_nomi.add(_nn(p.get("nome", "")))

    # ── Universo 2: MATERIE PRIME (dizionario_prodotti.scorta_minima) ────────
    # Era il vecchio job 08:00: creava UNA bozza cumulativa senza fornitore e
    # con quantità scorta*3. Ora: stesse bozze per fornitore, quantità fino a
    # 2× soglia, stessa dedup incrociata.
    materie = await db.dizionario_prodotti.find(
        {"scorta_minima": {"$gt": 0}, "conteggio_acquisti": {"$gt": 0}},
        {"_id": 0, "id": 1, "nome_normalizzato": 1, "nome_canonico": 1, "fornitore": 1,
         "quantita_disponibile_kg": 1, "scorta_minima": 1, "prezzo_kg": 1, "unita_confezione": 1},
    ).to_list(500)
    for p in materie:
        disp = float(p.get("quantita_disponibile_kg") or 0)
        sg = float(p.get("scorta_minima") or 0)
        if disp >= sg:
            continue
        nome = (p.get("nome_canonico") or p.get("nome_normalizzato") or "").title()
        if not nome or p.get("id") in gia_ids or _nn(nome) in gia_nomi:
            continue
        best = best_by_key.get(_nn(nome))
        f = (best and best["fornitore"]) or p.get("fornitore") or "DA ASSEGNARE"
        prezzo = (best and best["prezzo"]) or float(p.get("prezzo_kg") or 0)
        per_forn.setdefault(f, []).append({
            "prodotto_id": str(p.get("id")), "nome": nome, "fornitore": f,
            "quantita": round(max(sg * 2 - disp, 1), 2),
            # la quantità sopra è SEMPRE in kg (scorta e disponibilità sono in
            # kg): unita_confezione poteva essere "pz" → ordine sballato
            "unita": "kg", "prezzo_ultimo": prezzo,
            "richiesto_da": "riordino automatico",
            "note": f"materia prima: {disp:.2f} kg / soglia {sg:.2f} kg",
        })

    # Applica il calendario del SINGOLO fornitore e la previsione da
    # corrispettivi. Nessun raddoppio globale: ogni quantita conserva i fattori
    # e le fonti che l'hanno determinata.
    from app.lotti.servizi.pianificazione_ordini import piano_consegne, applica_fattori_quantita
    non_operativi, eventi_calendario = await _giorni_non_operativi_ordini(oggi_d)
    profili = {
        x.get("nome"): x async for x in db.fornitori_anagrafica.find({}, {"_id": 0})
        if x.get("nome")
    }
    pianificazione = {}
    previsioni = {}
    sospesi = []
    for f in list(per_forn):
        profilo = profili.get(f) or {}
        if profilo.get("procedura_ordini_attiva") is False:
            sospesi.append({"fornitore": f, "motivo": "procedura ordini disattivata"})
            per_forn.pop(f, None)
            continue
        piano = piano_consegne(oggi_d, profilo, non_operativi, ora_corrente=ora_roma.time())
        pianificazione[f] = piano
        data_target = _date.fromisoformat(piano["prima_consegna"]) if piano.get("prima_consegna") else oggi_d
        chiave_prev = (data_target.month, data_target.year)
        if chiave_prev not in previsioni:
            previsioni[chiave_prev] = await _fattore_previsione_corrispettivi(*chiave_prev)
        previsione = previsioni[chiave_prev]
        for riga in per_forn[f]:
            base = riga["quantita"]
            riga["quantita_base"] = base
            riga["quantita"] = applica_fattori_quantita(
                base, piano["giorni_copertura"], previsione["fattore"], riga.get("unita")
            )
            riga["pianificazione"] = {
                "giorni_copertura": piano["giorni_copertura"],
                "prima_consegna": piano.get("prima_consegna"),
                "consegna_successiva": piano.get("consegna_successiva"),
                "fattore_corrispettivi": previsione["fattore"],
                "corrispettivi_verificati": previsione["verificato"],
            }
            riga["note"] += f" · {piano['motivo']} · {previsione['motivo']}"

    anteprima = [{"fornitore": f, "righe": len(rr)} for f, rr in per_forn.items()]
    if dry_run:
        return {"ok": True, "dry_run": True, "prodotti_sotto_soglia": len(sotto),
                "bozze_che_verrebbero_create": anteprima,
                "pianificazione_fornitori": pianificazione,
                "previsioni_corrispettivi": {f"{m:02d}/{a}": p for (m, a), p in previsioni.items()},
                "procedure_sospese": sospesi,
                "eventi_calendario": eventi_calendario}
    if not per_forn:
        return {"ok": True, "dry_run": False, "bozze_create": [],
                "prodotti_riordinati": 0, "pianificazione_fornitori": {},
                "previsioni_corrispettivi": {}, "procedure_sospese": sospesi}

    now = datetime.now(timezone.utc).isoformat()
    oggi = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    creati = []
    for f, righe in per_forn.items():
        righe = await arricchisci_iva_righe(righe)
        import hashlib
        stable_id = "riordino-auto:" + oggi + ":" + hashlib.sha256(f.encode("utf-8")).hexdigest()[:16]
        ordine = {"id": stable_id, "data_ordine": oggi, "stato": "bozza",
                  "source": "riordino_auto", "reparto": "", "operatore": "Sistema riordino",
                  "fornitore": f, "totali": calcola_totali_ordine(righe),
                  "prodotti": righe, "ricette_da_produrre": [],
                  "note_operatore": f"Riordino automatico sotto-scorta del {oggi}",
                  "pianificazione": pianificazione.get(f),
                  "previsione_corrispettivi": previsioni.get((
                      (_date.fromisoformat(pianificazione[f]["prima_consegna"]) if pianificazione[f].get("prima_consegna") else oggi_d).month,
                      (_date.fromisoformat(pianificazione[f]["prima_consegna"]) if pianificazione[f].get("prima_consegna") else oggi_d).year,
                  )),
                  "created_at": now, "updated_at": now}
        esistente = await db.ordini_fornitori.find_one({"id": stable_id}, {"_id": 0})
        if esistente and esistente.get("stato") == "bozza":
            vecchie = esistente.get("prodotti") or []
            chiavi = {(x.get("prodotto_id"), _nn(x.get("nome", ""))) for x in vecchie}
            nuove = [x for x in righe if (x.get("prodotto_id"), _nn(x.get("nome", ""))) not in chiavi]
            unite = vecchie + nuove
            await db.ordini_fornitori.update_one({"id": stable_id}, {"$set": {
                "prodotti": unite, "totali": calcola_totali_ordine(unite),
                "pianificazione": ordine["pianificazione"],
                "previsione_corrispettivi": ordine["previsione_corrispettivi"],
                "updated_at": now,
            }})
        elif esistente:
            sospesi.append({"fornitore": f, "motivo": "bozza giornaliera gia confermata: revisione manuale"})
        else:
            await db.ordini_fornitori.insert_one(ordine)
            creati.append({"fornitore": f, "righe": len(righe), "ordine_id": ordine["id"]})
    return {"ok": True, "bozze_create": creati,
            "prodotti_riordinati": sum(len(righe) for righe in per_forn.values()),
            "pianificazione_fornitori": pianificazione,
            "previsioni_corrispettivi": {f"{m:02d}/{a}": p for (m, a), p in previsioni.items()},
            "procedure_sospese": sospesi}


@router.get("/count-pendenti")
async def count_pendenti():
    """Conta ordini con almeno una riga e ancora non inviati ai fornitori.

    NOTA: prima il filtro era solo `stato in [bozza,inviato]`, ma le bozze
    auto-create vuote (0 righe) generavano contatori fantasma. Ora richiediamo
    anche `righe.0` esistente (almeno 1 riga).
    """
    # Solo le BOZZE con almeno una riga sono "da inviare": gli ordini gia
    # inviati (stato 'inviato' legacy o 'inviato_fornitori') NON sono pendenti.
    n = await db.ordini_fornitori.count_documents(
        {
            "stato": {"$in": ["bozza", "confermato"]},
            "prodotti.0": {"$exists": True},
        }
    )
    return {"count": n}


class CarrelloSospesiPayload(BaseModel):
    righe: List[dict] = []


@router.get("/carrello-sospesi")
async def get_carrello_sospesi():
    """Carrello dei prodotti 'sospesi' (da ordinare piu tardi), persistente lato
    server: sopravvive a cambio dispositivo/giorno. Documento unico condiviso."""
    doc = await db.carrello_sospesi.find_one({"_id": "default"}, {"_id": 0})
    return {"righe": (doc or {}).get("righe", [])}


@router.put("/carrello-sospesi")
async def set_carrello_sospesi(payload: CarrelloSospesiPayload):
    """Salva (upsert) il carrello sospesi lato server."""
    await db.carrello_sospesi.update_one(
        {"_id": "default"},
        {"$set": {"righe": payload.righe, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return {"ok": True, "n": len(payload.righe)}


@router.get("/task-produzione-oggi")
async def get_task_produzione_oggi():
    """
    Restituisce le ricette da produrre legate a ordini recentemente ricevuti.
    Usata dalla Dashboard e dal Tablet per mostrare il piano produzione del giorno.
    Resiliente: in caso di errore non manda in 500 la Dashboard, ritorna vuoto.
    """
    try:
        return await _task_produzione_oggi_impl()
    except Exception as e:
        import logging, traceback
        logging.getLogger("ordini").error("task-produzione-oggi: %s\n%s", e, traceback.format_exc())
        return {"tasks": [], "totale": 0, "errore": str(e)}


async def _task_produzione_oggi_impl():
    # Ordini ricevuti negli ultimi 3 giorni con ricette da produrre
    cutoff = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    ordini = (
        await db.ordini_fornitori.find(
            {
                "stato": {"$in": ["ricevuto", "inviato_fornitori"]},
                "ricette_da_produrre": {"$exists": True, "$ne": []},
                "updated_at": {"$gte": cutoff},
            },
            {"_id": 0, "id": 1, "data_ordine": 1, "stato": 1, "ricette_da_produrre": 1},
        )
        .sort("updated_at", -1)
        .to_list(20)
    )

    tasks = []
    for ordine in ordini:
        for ricetta in ordine.get("ricette_da_produrre", []) or []:
            if not isinstance(ricetta, dict):
                continue  # voce malformata: salta invece di esplodere
            tasks.append(
                {
                    "ordine_id": ordine.get("id", ""),
                    "data_ordine": ordine.get("data_ordine", ""),
                    "ricetta_id": ricetta.get("ricetta_id"),
                    "ricetta_nome": ricetta.get("nome") or ricetta.get("ricetta_nome"),
                    "pezzi": ricetta.get("pezzi") or ricetta.get("quantita", 0),
                    "reparto": ricetta.get("reparto", ""),
                    "prodotta": ricetta.get("prodotta", False),
                }
            )

    return {"tasks": tasks, "totale": len(tasks)}


@router.delete("/{ordine_id}")
async def elimina_ordine(ordine_id: str):
    res = await db.ordini_fornitori.delete_one({"id": ordine_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Ordine non trovato")
    return {"ok": True}


@router.get("")
async def lista_ordini(
    stato: Optional[str] = Query(None), source: Optional[str] = Query(None), limit: int = Query(50)
):
    """Lista ordini, filtrabili per stato e source. Senza source restituisce tutti."""
    filtro = {}
    if stato:
        filtro["stato"] = stato
    if source:
        filtro["source"] = source

    ordini = (
        await db.ordini_fornitori.find(filtro, {"_id": 0})
        .sort("created_at", -1)
        .limit(limit)
        .to_list(limit)
    )
    return ordini


@router.get("/automatici")
async def lista_ordini_automatici():
    """
    Lista le proposte d'ordine automatiche in attesa di conferma admin.
    Fix 02/07/2026: filtrava solo source fantasma mai scritti da nessuno
    (automatico_giacenza/tablet_pasticceria) → sempre vuoto e badge admin
    sempre spento. Ora include i source REALI (riordino_auto, alert_mancanti)
    più i legacy per i documenti storici.
    """
    ordini = (
        await db.ordini_fornitori.find(
            {"source": {"$in": ["riordino_auto", "alert_mancanti", "automatico_scorta", "automatico_lotti", "automatico_giacenza", "tablet_pasticceria"]}, "stato": "bozza"},
            {"_id": 0},
        )
        .sort("created_at", -1)
        .to_list(200)
    )
    return ordini




async def _richiedi_admin(request: Request):
    """Le azioni di revisione ordini (conferma/invio) sono SOLO del titolare.
    Via principale: il token JWT del login centrale con ruolo amministratore
    (chi e' entrato dal gate col PIN admin e' gia' verificato). Fallback:
    header X-Admin-Pin per i flussi tablet senza login."""
    # 1) token del sistema auth centralizzato
    try:
        from app.lotti.auth import _ha_token_valido
        data = _ha_token_valido(request)
        if data and data.get("ruolo") == "amministratore":
            return
    except Exception as e:
        # fail-closed: si passa al fallback PIN, ma l'errore va visto nei log
        import logging
        logging.getLogger(__name__).warning(f"[admin-check] verifica token fallita: {e}")
    # 2) fallback X-Admin-Pin
    pin = (request.headers.get("X-Admin-Pin") or "").strip() if request else ""
    if not pin:
        raise HTTPException(403, "Operazione riservata al titolare: inserisci il PIN amministratore")
    from app.lotti.routers.tablet_operatori import pin_amministratore_valido
    if not await pin_amministratore_valido(pin):
        raise HTTPException(403, "PIN amministratore non valido")


@router.post("/verifica-admin")
async def verifica_admin(request: Request):
    """Verifica il PIN amministratore (usato dal pannello 'Da inviare')."""
    await _richiedi_admin(request)
    return {"ok": True}


@router.put("/{ordine_id}/conferma")
async def conferma_ordine(ordine_id: str, request: Request = None):
    await _richiedi_admin(request)
    """
    Conferma una bozza → stato 'confermato' (NON inviato).
    Regola: gli ordini non partono mai da soli; l'invio è un'azione separata.
    """
    r = await db.ordini_fornitori.update_one(
        {"id": ordine_id},
        {
            "$set": {
                "stato": "confermato",
                "prodotti.$[].confermato": True,
                "confermato_il": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )
    if r.matched_count == 0:
        raise HTTPException(404, "Ordine non trovato")
    return {"ok": True, "stato": "confermato"}


@router.put("/{ordine_id}/conferma-righe")
async def conferma_righe(ordine_id: str, payload: dict, request: Request = None):
    await _richiedi_admin(request)
    """Segna confermate SOLO alcune righe. Payload: {prodotto_ids: [...]}.
    Le righe non in lista vengono s-confermate. Stato: 'confermato' se almeno
    una riga è confermata, altrimenti torna 'bozza'."""
    ids = set(map(str, (payload or {}).get("prodotto_ids") or []))
    ordine = await db.ordini_fornitori.find_one({"id": ordine_id}, {"_id": 0})
    if not ordine:
        raise HTTPException(404, "Ordine non trovato")
    prodotti = ordine.get("prodotti") or []
    n_conf = 0
    for p in prodotti:
        p["confermato"] = str(p.get("prodotto_id")) in ids
        n_conf += 1 if p["confermato"] else 0
    nuovo_stato = "confermato" if n_conf else "bozza"
    await db.ordini_fornitori.update_one(
        {"id": ordine_id},
        {"$set": {
            "prodotti": prodotti,
            "stato": nuovo_stato,
            "confermato_il": datetime.now(timezone.utc).isoformat() if n_conf else None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    return {"ok": True, "stato": nuovo_stato, "righe_confermate": n_conf, "righe_totali": len(prodotti)}


@router.post("/{ordine_id}/invia")
async def invia_ordine_confermato(ordine_id: str, request: Request = None):
    await _richiedi_admin(request)
    """Invia al fornitore SOLO le righe confermate. Le righe non confermate
    restano in una bozza residua (stesso fornitore/fonte). L'email parte con
    le sole righe confermate; lo stato dell'ordine inviato diventa
    'inviato_fornitori' (settato dal modulo email a invio riuscito)."""
    # CLAIM ATOMICO dell'invio: solo la PRIMA richiesta che porta l'ordine a
    # "inviato_fornitori" prosegue. Un doppio tap su "Invia" (o due schede
    # aperte) trovava l'ordine ancora non inviato in entrambe le richieste e
    # creava DUE bozze residue + pubblicava ORDINE_INVIATO due volte.
    now = datetime.now(timezone.utc).isoformat()
    # FIX 24/07/2026 (audit flussi): la validazione "ci sono righe confermate?"
    # deve avvenire PRIMA del claim — prima l'ordine veniva marcato
    # inviato_fornitori e POI falliva con 400: restava "bruciato" per sempre
    # (il retry trovava gia_inviato e non partiva mai).
    pre = await db.ordini_fornitori.find_one({"id": ordine_id}, {"_id": 0, "prodotti": 1, "stato": 1})
    if not pre:
        raise HTTPException(404, "Ordine non trovato")
    if pre.get("stato") != "inviato_fornitori" and not any(p.get("confermato") for p in pre.get("prodotti") or []):
        raise HTTPException(400, "Nessuna riga confermata: conferma le righe da inviare")

    ordine = await db.ordini_fornitori.find_one_and_update(
        {"id": ordine_id, "stato": {"$ne": "inviato_fornitori"}},
        {"$set": {"stato": "inviato_fornitori", "inviato_at": now, "updated_at": now}},
    )
    if not ordine:
        # è già stato inviato da una richiesta concorrente
        return {"success": True, "gia_inviato": True}
    ordine.pop("_id", None)
    prodotti = ordine.get("prodotti") or []
    confermate = [p for p in prodotti if p.get("confermato")]
    residue = [p for p in prodotti if not p.get("confermato")]
    if not confermate:
        raise HTTPException(400, "Nessuna riga confermata: conferma le righe da inviare")
    bozza_residua_id = None
    if residue:
        bozza_residua_id = str(uuid.uuid4())
        residua = {
            **{k: v for k, v in ordine.items() if k not in ("id", "prodotti", "stato", "confermato_il")},
            "id": bozza_residua_id,
            "prodotti": [{**p, "confermato": False} for p in residue],
            "stato": "bozza",
            "note_operatore": (ordine.get("note_operatore") or "") + " [righe non confermate del precedente invio]",
            "created_at": now,
            "updated_at": now,
        }
        await db.ordini_fornitori.insert_one(residua)

    # Invio automatico (PEC/email) rimosso: l'ordine viene segnato come confermato
    # e va inviato manualmente al fornitore scaricando il PDF (GET .../pdf).
    await db.ordini_fornitori.update_one(
        {"id": ordine_id},
        # Stato CANONICO del flusso (bozza→confermato→inviato_fornitori).
        # BUG STORICO corretto il 02/07/2026: qui si scriveva "inviato_manualmente",
        # ma ricezione merce e riconciliazione fattura cercavano solo
        # "inviato_fornitori" → gli ordini inviati non si chiudevano MAI da soli.
        {"$set": {"prodotti": confermate, "updated_at": now,
                  "stato": "inviato_fornitori", "inviato_at": now}},
    )

    from app.lotti.eventi import publish
    await publish("ORDINE_INVIATO", {
        "ordine_id": ordine_id, "fornitore": ordine.get("fornitore", ""),
        "righe": len(confermate),
    })
    return {"ok": True, "esito_email": {"inviato": False, "motivo": "Invio automatico rimosso: scarica il PDF e invia manualmente"},
            "bozza_residua_id": bozza_residua_id,
            "righe_inviate": len(confermate), "righe_rimaste_bozza": len(residue)}


@router.put("/{ordine_id}/modifica-quantita")
async def modifica_quantita_ordine(ordine_id: str, payload: dict):
    """
    Admin modifica le quantità prima della conferma.
    Payload: { prodotti: [{ prodotto_id, quantita }] }
    """
    ordine = await db.ordini_fornitori.find_one({"id": ordine_id}, {"_id": 0})
    if not ordine:
        raise HTTPException(404, "Ordine non trovato")

    nuove_qty = {p["prodotto_id"]: p["quantita"] for p in payload.get("prodotti", [])}
    prodotti_upd = []
    for p in ordine.get("prodotti", []):
        pid = p.get("prodotto_id", "")
        if pid in nuove_qty:
            prodotti_upd.append({**p, "quantita": nuove_qty[pid]})
        else:
            prodotti_upd.append(p)

    await db.ordini_fornitori.update_one(
        {"id": ordine_id},
        {
            "$set": {
                "prodotti": prodotti_upd,
                "totali": calcola_totali_ordine(await arricchisci_iva_righe(prodotti_upd)),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )
    return await db.ordini_fornitori.find_one({"id": ordine_id}, {"_id": 0})


@router.put("/{ordine_id}/sostituisci-prodotti")
async def sostituisci_prodotti_ordine(ordine_id: str, payload: dict):
    """
    Sostituisce l'intera lista prodotti dell'ordine (per modificare quantità
    ED eliminare singole righe prima dell'invio).
    Payload: { prodotti: [{ prodotto_id?, nome, quantita, ... }] }
    """
    ordine = await db.ordini_fornitori.find_one({"id": ordine_id}, {"_id": 0})
    if not ordine:
        raise HTTPException(404, "Ordine non trovato")

    nuovi = payload.get("prodotti", [])
    # conserva i campi originali per prodotto_id, sovrascrivendo solo quantità/nome forniti
    orig_by_id = {p.get("prodotto_id", ""): p for p in ordine.get("prodotti", [])}
    prodotti_upd = []
    for p in nuovi:
        pid = p.get("prodotto_id", "")
        base = dict(orig_by_id.get(pid, {}))
        base.update({k: v for k, v in p.items() if v is not None})
        prodotti_upd.append(base)

    prodotti_upd = await arricchisci_iva_righe(prodotti_upd)
    await db.ordini_fornitori.update_one(
        {"id": ordine_id},
        {"$set": {"prodotti": prodotti_upd, "totali": calcola_totali_ordine(prodotti_upd),
                   "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return await db.ordini_fornitori.find_one({"id": ordine_id}, {"_id": 0})


@router.get("/{ordine_id}")
async def get_ordine(ordine_id: str):
    ordine = await db.ordini_fornitori.find_one({"id": ordine_id}, {"_id": 0})
    if not ordine:
        raise HTTPException(status_code=404, detail="Ordine non trovato")
    return ordine


# ══════════════════════════════════════════════════════════════════════════════
# ORDINI AUTOMATICI — giacenza calante → proposta ordine → conferma admin
# ══════════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
# RICONCILIAZIONE FATTURA ↔ ORDINE
# Quando arriva una fattura, confronta i prodotti con l'ultimo ordine inviato
# allo stesso fornitore. Spunta i ricevuti, crea alert per i mancanti.
# ══════════════════════════════════════════════════════════════════════════════

import logging as _logging

_logger_ord = _logging.getLogger(__name__)


def _normalizza_nome(nome: str) -> str:
    """Normalizzazione minima per il confronto prodotto fattura ↔ ordine."""
    import re as _re

    return _re.sub(r"\s+", " ", (nome or "").lower().strip())


def _match_prodotto(nome_fattura: str, nome_ordine: str, soglia: float = 0.65) -> bool:
    """True se i due nomi si riferiscono allo stesso prodotto (match fuzzy semplice)."""
    nf = _normalizza_nome(nome_fattura)
    no = _normalizza_nome(nome_ordine)
    if not nf or not no:
        return False
    # Match esatto
    if nf == no:
        return True
    # Containment: uno contiene l'altro
    if nf in no or no in nf:
        return True
    # Parole in comune / Jaccard
    wf = set(nf.split())
    wo = set(no.split())
    if not wf or not wo:
        return False
    jaccard = len(wf & wo) / len(wf | wo)
    return jaccard >= soglia


async def riconcilia_fattura_con_ordine(
    fornitore: str,
    prodotti_fattura: list,  # [{descrizione, quantita, ...}]
    fattura_id: str,
    data_fattura: str,
) -> dict:
    """
    Chiamata automaticamente dopo ogni import fattura (PEC o XML).

    1. Trova l'ordine inviato più recente per questo fornitore
    2. Confronta prodotti fattura ↔ prodotti ordine
    3. Segna come ricevuti i prodotti trovati in fattura
    4. Crea alert per i prodotti ordinati ma NON presenti in fattura
    5. Aggiorna stato ordine → 'ricevuto_parziale' o 'ricevuto'

    Ritorna un dizionario con il riepilogo della riconciliazione.
    """
    if not fornitore or not prodotti_fattura:
        return {"riconciliato": False, "motivo": "fornitore o prodotti mancanti"}

    # Cerca l'ordine INVIATO più recente per QUESTO fornitore.
    # Regole: (a) si riconciliano solo ordini realmente inviati — le bozze e
    # i confermati non ancora inviati non vanno chiusi da una consegna di
    # routine; (b) MAI il fallback su ordini di altri fornitori (chiudeva
    # bozze estranee marcandole "ricevuto").
    rx_forn = re.escape(fornitore[:10])
    ordine = await db.ordini_fornitori.find_one(
        {
            "stato": {"$in": ["inviato_fornitori", "inviato_manualmente", "inviato"]},
            "$or": [
                {"prodotti.fornitore": {"$regex": rx_forn, "$options": "i"}},
                {"fornitore": {"$regex": rx_forn, "$options": "i"}},
            ],
        },
        {"_id": 0},
        sort=[("created_at", -1)],
    )
    if not ordine:
        return {"riconciliato": False, "motivo": f"nessun ordine inviato per {fornitore}"}

    prodotti_ordine = ordine.get("prodotti", [])
    nomi_fattura = [
        _normalizza_nome(p.get("descrizione", "") or p.get("nome", "")) for p in prodotti_fattura
    ]

    ricevuti = []
    mancanti = []

    for prod_ord in prodotti_ordine:
        nome_ord = prod_ord.get("nome", "") or prod_ord.get("prodotto_nome", "")
        trovato = any(_match_prodotto(nf, nome_ord) for nf in nomi_fattura if nf)

        if trovato:
            ricevuti.append({**prod_ord, "ricevuto": True, "fattura_id": fattura_id})
        else:
            # Solo se il prodotto era per questo fornitore
            fornitore_prod = (prod_ord.get("fornitore") or "").lower()
            if (
                not fornitore_prod
                or fornitore[:8].lower() in fornitore_prod
                or fornitore_prod in fornitore.lower()
            ):
                mancanti.append({**prod_ord, "ricevuto": False})

    # Aggiorna l'ordine con la riconciliazione
    nuovo_stato = "ricevuto" if not mancanti else "ricevuto_parziale"
    await db.ordini_fornitori.update_one(
        {"id": ordine["id"]},
        {
            "$set": {
                "stato": nuovo_stato,
                "riconciliazione": {
                    "fattura_id": fattura_id,
                    "data_fattura": data_fattura,
                    "fornitore": fornitore,
                    "ricevuti": ricevuti,
                    "mancanti": mancanti,
                    "riconciliato_il": datetime.now(timezone.utc).isoformat(),
                },
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )

    # Crea alert per prodotti mancanti → da reinserire in ordine
    if mancanti:
        await db.ordini_fornitori.insert_one(
            {
                "id": str(uuid.uuid4()),
                "data_ordine": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "stato": "bozza",
                "source": "alert_mancanti",
                "fornitore_origine": fornitore,
                "ordine_origine_id": ordine["id"],
                "fattura_id": fattura_id,
                "prodotti": mancanti,
                "ricette_da_produrre": [],
                "note_operatore": (
                    f"⚠ Prodotti NON ricevuti dalla fattura {data_fattura} ({fornitore}). "
                    f"Verificare con il fornitore e riordinare se necessario."
                ),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    _logger_ord.info(
        f"[RICONCILIAZIONE] {fornitore} — ordine {ordine['id'][:8]}: "
        f"{len(ricevuti)} ricevuti, {len(mancanti)} mancanti → stato={nuovo_stato}"
    )

    return {
        "riconciliato": True,
        "ordine_id": ordine["id"],
        "stato_ordine": nuovo_stato,
        "ricevuti": len(ricevuti),
        "mancanti": len(mancanti),
        "alert_creato": len(mancanti) > 0,
    }


@router.get("/{ordine_id}/riconciliazione")
async def get_riconciliazione(ordine_id: str):
    """Ritorna i dettagli di riconciliazione di un ordine (ricevuti + mancanti)."""
    ordine = await db.ordini_fornitori.find_one({"id": ordine_id}, {"_id": 0})
    if not ordine:
        raise HTTPException(404, "Ordine non trovato")
    return {
        "ordine_id": ordine_id,
        "stato": ordine.get("stato"),
        "riconciliazione": ordine.get("riconciliazione"),
        "prodotti": ordine.get("prodotti", []),
    }


# ── Task produzione da ordini ricevuti ────────────────────────────────────────



@router.patch("/{ordine_id}/segna-ricetta-prodotta")
async def segna_ricetta_prodotta(ordine_id: str, ricetta_id: str):
    """Segna una ricetta dell'ordine come prodotta (spunta nel pianificatore)."""
    ordine = await db.ordini_fornitori.find_one({"id": ordine_id}, {"_id": 0})
    if not ordine:
        raise HTTPException(404, "Ordine non trovato")

    ricette = ordine.get("ricette_da_produrre", [])
    for r in ricette:
        if r.get("ricetta_id") == ricetta_id or r.get("nome") == ricetta_id:
            r["prodotta"] = True
            r["prodotta_il"] = datetime.now(timezone.utc).isoformat()

    await db.ordini_fornitori.update_one(
        {"id": ordine_id},
        {
            "$set": {
                "ricette_da_produrre": ricette,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )
    return {"ok": True}
