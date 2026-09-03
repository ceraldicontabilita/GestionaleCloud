"""
Router Farciture (richiesta Enzo 03/07/2026): quando un prodotto-base fatto
in casa (es. Cornetto Vuoto) viene prelevato dalla giacenza frigo/abbattitore
per andare al banco, questo modulo lo divide nei gusti secondo le proporzioni
già impostate in Colazione per la stagione attiva, scarica la dose di
farcitura per ciascun gusto (config in data/farciture.json) RIUSANDO lo
stesso motore FIFO delle ricette (nessun sistema di scarico parallelo), e
registra ogni gruppo in vendita al banco sotto il prodotto giusto.
"""
import json
import os
import re
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Body

from app.lotti.db import database as db

router = APIRouter(prefix="/farciture", tags=["Farciture"])


def set_database(database):
    global db
    db = database


_CONFIG = None


def _carica_config() -> dict:
    """Carica (una volta) data/farciture.json — stesso pattern di
    schede_prodotti.json in schede_tecniche.py."""
    global _CONFIG
    if _CONFIG is not None:
        return _CONFIG
    try:
        p = os.path.join(os.path.dirname(__file__), "..", "data", "farciture.json")
        with open(p, encoding="utf-8") as f:
            _CONFIG = json.load(f) or {}
    except Exception:
        _CONFIG = {"farciture": {}, "prodotti_base": {}}
    return _CONFIG


def _prodotto_base_config(nome_prodotto: str) -> Optional[dict]:
    cfg = _carica_config()
    return (cfg.get("prodotti_base") or {}).get((nome_prodotto or "").strip())


@router.get("/prodotto-base/{nome_prodotto}")
async def farcitura_disponibile(nome_prodotto: str):
    """Dice se un prodotto ha farciture configurate — usato dal frontend per
    mostrare/nascondere il bottone 'Dividi nei gusti' sulla giacenza."""
    conf = _prodotto_base_config(nome_prodotto)
    return {"disponibile": conf is not None, "gusti": (conf or {}).get("gusti_collegati", [])}


def _riparto_proporzionale(quote: dict, pezzi_totali: int) -> dict:
    """Riparto proporzionale con arrotondamento a resto più grande (metodo
    Hare/Niemeyer): la somma finale torna SEMPRE esattamente pezzi_totali,
    qualunque sia il resto della divisione (funzione pura, testata a parte)."""
    totale_configurato = sum(quote.values())
    if totale_configurato <= 0 or pezzi_totali <= 0:
        return {k: 0 for k in quote}
    grezzo = {k: pezzi_totali * v / totale_configurato for k, v in quote.items()}
    interi = {k: int(v) for k, v in grezzo.items()}
    resto = pezzi_totali - sum(interi.values())
    ordine_resti = sorted(grezzo.items(), key=lambda kv: -(kv[1] - int(kv[1])))
    for k, _ in ordine_resti[:max(0, resto)]:
        interi[k] += 1
    return interi


async def _dividi_proporzionale(gusti_collegati: list, stagione: str, prodotto_base_nome: str, pezzi_totali: int) -> dict:
    """Legge le proporzioni GIA' impostate in Colazione (Aggiungi prodotti ->
    Configura) per la stagione data — i `pezzi` di ogni item 'Cornetto
    <gusto>' — e le scala su pezzi_totali mantenendo lo stesso rapporto
    (es. 4+4+4+4+4=20 configurati, prelievo 40 -> 8+8+8+8+8). Il prodotto
    base stesso (es. 'Cornetto Vuoto') e' il gusto 'vuoto': nessuna
    farcitura, resta cosi' com'e'. Match gusto<->nome item a CONFINI DI
    PAROLA (non sottostringa nuda: stesso bug già visto altrove nel
    progetto con match troppo larghi)."""
    doc = await db.colazione_template.find_one({"nome": stagione}, {"_id": 0, "items": 1})
    items = (doc or {}).get("items") or []

    pesi = {}  # gusto -> (pezzi_configurati, item_colazione)
    base_pezzi_configurati = 0
    for it in items:
        nome_it = it.get("prodotto_nome") or ""
        if nome_it.strip().lower() == prodotto_base_nome.strip().lower():
            base_pezzi_configurati = it.get("pezzi") or 0
            continue
        for gusto in gusti_collegati:
            if re.search(r"\b" + re.escape(gusto) + r"\b", nome_it, re.IGNORECASE):
                pesi[gusto] = (it.get("pezzi") or 0, it)
                break

    totale_configurato = base_pezzi_configurati + sum(p for p, _ in pesi.values())
    if totale_configurato <= 0:
        raise HTTPException(
            400,
            f"Nessuna proporzione impostata in Colazione '{stagione}' per {prodotto_base_nome}: "
            "configurala prima in Colazione -> Aggiungi prodotti -> Configura.",
        )

    quote = {"vuoto": base_pezzi_configurati, **{g: p for g, (p, _) in pesi.items()}}
    interi = _riparto_proporzionale(quote, pezzi_totali)

    return {"divisione": interi, "items_colazione": {g: it for g, (_, it) in pesi.items()}}


@router.get("/anteprima-divisione")
async def anteprima_divisione(prodotto_base_nome: str, pezzi: int, stagione: str):
    """Calcola la divisione nei gusti SENZA scaricare nulla — per farla
    vedere/correggere all'operatore prima di confermare."""
    conf = _prodotto_base_config(prodotto_base_nome)
    if not conf:
        raise HTTPException(400, f"Nessuna farcitura configurata per '{prodotto_base_nome}'")
    if pezzi <= 0:
        raise HTTPException(400, "pezzi deve essere positivo")
    risultato = await _dividi_proporzionale(conf["gusti_collegati"], stagione, prodotto_base_nome, pezzi)
    return {"divisione": risultato["divisione"], "pezzi_totali": pezzi, "stagione": stagione}


@router.post("/{lotto_id}/dividi-e-manda-al-banco")
async def dividi_e_manda_al_banco(lotto_id: str, data: dict = Body(...)):
    """
    Body: {prodotto_base_nome, stagione, divisione:{gusto: pezzi, "vuoto": pezzi},
           reparto, operatore_id, operatore_nome}
    1. Scala la giacenza del lotto base (frigo/abbattitore) per il totale.
    2. Per ogni gusto farcito: scarica la dose (FIFO, stesso motore delle
       ricette — scala_lotti_fornitori_per_ricetta con una "ricetta virtuale"
       fatta solo dagli ingredienti di farcitura) e registra la vendita al
       banco sotto il prodotto Colazione giusto. Il gusto "vuoto" si
       registra cosi' com'e', senza scarico farcitura.
    """
    from app.lotti.routers.lotti_produzione import scala_lotti_fornitori_per_ricetta, peek_lotto_fifo_attivo
    from app.lotti.routers.vendita_banco import registra_vendita_banco, VenditaBancoIn

    lotto = await db.lotti.find_one({"id": lotto_id}, {"_id": 0})
    if lotto and lotto.get("stato") == "bloccato_richiamo":
        raise HTTPException(status_code=423,
            detail="Lotto BLOCCATO da richiamo: operazione non consentita (serve lo sblocco amministrativo)")
    if not lotto:
        raise HTTPException(404, "Lotto non trovato")

    prodotto_base_nome = (data.get("prodotto_base_nome") or lotto.get("prodotto", "")).strip()
    stagione = data.get("stagione")
    divisione = {k: int(v) for k, v in (data.get("divisione") or {}).items() if int(v or 0) > 0}
    reparto = data.get("reparto", "pasticceria")
    operatore_id = data.get("operatore_id")
    operatore_nome = data.get("operatore_nome")

    conf = _prodotto_base_config(prodotto_base_nome)
    if not conf:
        raise HTTPException(400, f"Nessuna farcitura configurata per '{prodotto_base_nome}'")

    pezzi_totali = sum(divisione.values())
    disponibile = lotto.get("quantita") or 0
    if pezzi_totali <= 0 or pezzi_totali > disponibile:
        raise HTTPException(400, f"Quantità non valida: disponibili {disponibile}, richiesti {pezzi_totali}")

    # 1. Scala la giacenza del lotto base
    if pezzi_totali >= disponibile:
        await db.lotti.update_one({"id": lotto_id}, {"$set": {
            "consumato": True, "data_consumo": datetime.now(timezone.utc).isoformat(), "quantita": 0}})
    else:
        await db.lotti.update_one({"id": lotto_id}, {"$set": {"quantita": round(disponibile - pezzi_totali, 3)}})

    # 2. Item Colazione per ogni gusto (per prodotto_id/nome/foto corretti)
    doc = await db.colazione_template.find_one({"nome": stagione}, {"_id": 0, "items": 1}) if stagione else None
    items_per_nome = {(it.get("prodotto_nome") or "").strip().lower(): it for it in (doc or {}).get("items") or []}
    farciture_cfg = _carica_config().get("farciture", {})
    numero_riferimento = f"FARC-{lotto.get('numero_lotto', '')}"

    risultati = []
    for gusto, pezzi in divisione.items():
        scarico_farcitura = None
        if gusto == "vuoto":
            prod_id, prod_nome, foto = lotto.get("id"), prodotto_base_nome, lotto.get("foto_url")
        else:
            match = next(
                (it for nome_it, it in items_per_nome.items()
                 if re.search(r"\b" + re.escape(gusto) + r"\b", nome_it, re.IGNORECASE)),
                None,
            )
            prod_id = (match or {}).get("prodotto_id") or f"{prodotto_base_nome}-{gusto}"
            prod_nome = (match or {}).get("prodotto_nome") or f"{prodotto_base_nome} {gusto.title()}"
            foto = (match or {}).get("foto_url")

            ingredienti_dettaglio = []
            for comp in (farciture_cfg.get(gusto) or {}).get("componenti", []):
                alternative = comp.get("ingredienti_alternativi", [])
                scelto = None
                for alt in alternative:
                    if await peek_lotto_fifo_attivo({"nome": alt}):
                        scelto = alt
                        break
                ingredienti_dettaglio.append({
                    "nome": scelto or (alternative[0] if alternative else ""),
                    "quantita": comp.get("dose_g", 0),
                    "unita_misura": "g",
                })
            virtual_ricetta = {"nome": f"Farcitura {gusto}", "ingredienti_dettaglio": ingredienti_dettaglio}
            scarico_farcitura = await scala_lotti_fornitori_per_ricetta(virtual_ricetta, pezzi, numero_riferimento)

        vendita = await registra_vendita_banco(VenditaBancoIn(
            prodotto_id=prod_id, prodotto_nome=prod_nome, reparto=reparto,
            pezzi_prodotti=pezzi, foto_url=foto, lotto_id=lotto_id,
            numero_lotto=lotto.get("numero_lotto"), operatore_id=operatore_id,
            operatore_nome=operatore_nome,
        ))
        risultati.append({
            "gusto": gusto, "pezzi": pezzi, "prodotto_nome": prod_nome,
            "scarico_farcitura": scarico_farcitura, "vendita_id": vendita.get("id"),
        })

    return {"status": "ok", "pezzi_totali": pezzi_totali, "risultati": risultati}
