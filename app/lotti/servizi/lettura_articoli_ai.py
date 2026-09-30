"""Lettura AI delle descrizioni di articolo (fatture XML e listini fornitori).

Ogni fornitore scrive lo stesso articolo a modo suo: «TONNO OLIO GIR.GR.80x6
MAREVIVO», «MARE VIVO TONNO GIRASOLE 80GRX6». Qui un modello legge una volta
sola ogni descrizione e ne restituisce una lettura strutturata:

* ``nome``: nome standard leggibile («Tonno all'olio di girasole Mare Vivo 80 g × 6»);
* ``marca``, ``prodotto``, ``variante``: le parti che identificano l'articolo;
* ``misura`` + ``unita`` (g/ml del singolo pezzo) e ``pezzi`` per confezione;
* ``servizio``: la riga non e' merce (trasporto, spese, sconti).

**Non si inventano numeri**: misura e pezzi si accettano solo se il numero e'
scritto nella descrizione (``numero_scritto``); altrimenti restano vuoti. La
lettura e' un'ipotesi dichiarata: il confronto la usa per unire le descrizioni
e lo scrive (``abbinato_ai``), una persona puo' sempre separarle.

Le letture stanno in ``articoli_letti_ai`` (chiave = impronta della
descrizione ripulita, ``confronto_fornitori.impronta_descrizione``): una
descrizione gia' letta non si rilegge, finche' non cambia ``VERSIONE``. Il
giro gira in sottofondo con lo stato in ``sync_status`` (``_id =
"lettura_articoli_ai"``). ``nome_mapping`` resta un'altra cosa: l'ingrediente
per le ricette («Burro»), non l'articolo commerciale da ordinare.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional

from app.lotti.servizi.confronto_fornitori import impronta_descrizione, pulisci

logger = logging.getLogger(__name__)

COLLEZIONE = "articoli_letti_ai"
STATO_ID = "lettura_articoli_ai"
VERSIONE = 1
MODELLO = "claude-haiku-4-5"
PER_CHIAMATA = 25
MAX_TOKEN = 8000
IN_PARALLELO = 4
SCRITTURA_OGNI = 400

_SISTEMA = (
    "Leggi descrizioni di articoli scritte da grossisti alimentari italiani su fatture e listini "
    "(abbreviate, maiuscole, con formato e confezione). Per ogni descrizione numerata rispondi con UN SOLO "
    "array JSON, nessun altro testo: "
    '[{"i":1,"nome":"...","marca":"...","prodotto":"...","variante":"...","misura":80,"unita":"g","pezzi":6,"servizio":false}]. '
    "Regole: "
    "nome = nome standard in italiano, leggibile, forma: prodotto, variante, marca, formato "
    "(es. \"Tonno all'olio di girasole Mare Vivo 80 g × 6\", \"Coca-Cola Zero lattina 33 cl × 24\"). "
    "marca = marchio commerciale (anche se nella descrizione compare solo il prodotto di marca, es. Nutella → Ferrero); "
    "\"\" se non c'e' una marca. "
    "prodotto = tipo di prodotto in 1-4 parole minuscole, senza marca, formato o confezione, in forma canonica "
    "(es. \"tonno olio girasole\", \"pomodori pelati\", \"maionese\", \"acqua naturale\"). "
    "variante = gusto o tipo che distingue articoli della stessa marca (\"zero\", \"frizzante\", \"integrale\"), \"\" se nessuna. "
    "misura = peso in grammi o volume in millilitri DEL SINGOLO PEZZO, solo se scritto nella descrizione "
    "(KG.3 = 3000 g, CL33 = 330 ml, LT.1,5 = 1500 ml), altrimenti null. unita = \"g\" o \"ml\" o null. "
    "pezzi = numero di pezzi della confezione se scritto (X6, CTX24, 12X132), altrimenti null. "
    "servizio = true se la riga non e' merce (trasporto, spese, sconto, cauzione, imballo). "
    "Non inventare mai numeri che non sono scritti."
)


def _chiave_api() -> str:
    return os.environ.get("ANTHROPIC_API_KEY", "").strip()


def _numeri_scritti(testo: str) -> List[Decimal]:
    out: List[Decimal] = []
    for n in re.findall(r"\d+(?:[.,]\d+)?", testo):
        try:
            out.append(Decimal(n.replace(",", ".")))
        except Exception:  # noqa: BLE001 - un numero illeggibile non e' un numero
            continue
    return out


def numero_scritto(valore: Any, testo: str, fattori: Iterable[int] = (1,)) -> bool:
    """Il numero (o il numero diviso per un fattore di unita') compare nel testo."""
    try:
        v = Decimal(str(valore))
    except Exception:  # noqa: BLE001
        return False
    if v <= 0:
        return False
    scritti = _numeri_scritti(testo)
    return any(v == n * f for n in scritti for f in fattori)


def valida(lettura: Dict[str, Any], descrizione: str) -> Dict[str, Any]:
    """La lettura del modello, ripulita: misura e pezzi solo se scritti."""
    testo = pulisci(descrizione)
    unita = lettura.get("unita") if lettura.get("unita") in ("g", "ml") else None
    misura = lettura.get("misura")
    if misura is None or unita is None or not numero_scritto(misura, testo, (1, 10, 1000)):
        misura, unita = None, None
    pezzi = lettura.get("pezzi")
    try:
        pezzi = int(pezzi) if pezzi is not None else None
    except (TypeError, ValueError):
        pezzi = None
    if pezzi is not None and (pezzi < 2 or not numero_scritto(pezzi, testo)):
        pezzi = None

    def t(campo: str, massimo: int = 120) -> str:
        return re.sub(r"\s+", " ", str(lettura.get(campo) or "")).strip()[:massimo]

    return {
        "nome": t("nome", 160),
        "marca": t("marca", 60),
        "prodotto": t("prodotto", 80).lower(),
        "variante": t("variante", 60).lower(),
        "misura": None if misura is None else f"{Decimal(str(misura)).normalize():f}",
        "unita": unita,
        "pezzi": pezzi,
        "servizio": bool(lettura.get("servizio")),
    }


def _estrai_array(testo: str) -> List[Dict[str, Any]]:
    """Gli oggetti letti dalla risposta, anche se l'array e' troncato o ha testo attorno.

    Una risposta tagliata a meta' (limite di token) o con una frase davanti non
    deve far perdere le letture complete che contiene: si leggono gli oggetti
    uno a uno dal primo ``[``.
    """
    testo = re.sub(r"```(?:json)?", "", testo or "")
    inizio = testo.find("[")
    if inizio < 0:
        return []
    try:
        dati = json.loads(testo[inizio:testo.rindex("]") + 1])
        return [d for d in dati if isinstance(d, dict)]
    except (json.JSONDecodeError, ValueError):
        pass
    decoder = json.JSONDecoder()
    out: List[Dict[str, Any]] = []
    pos = inizio + 1
    while pos < len(testo):
        graffa = testo.find("{", pos)
        if graffa < 0:
            break
        try:
            oggetto, pos = decoder.raw_decode(testo, graffa)
        except json.JSONDecodeError:
            break  # l'ultimo oggetto e' tagliato: si tengono quelli completi
        if isinstance(oggetto, dict):
            out.append(oggetto)
    return out


async def leggi_con_ai(descrizioni: List[str], client=None,
                       diagnosi: Optional[Dict[str, Any]] = None) -> Dict[str, Dict[str, Any]]:
    """Una chiamata per al massimo ``PER_CHIAMATA`` descrizioni.
    Torna {descrizione: lettura validata}; le mancanti restano da leggere."""
    chiave = _chiave_api()
    if not chiave or not descrizioni:
        return {}
    import httpx

    lista = "\n".join(f"{i + 1}. {pulisci(d)}" for i, d in enumerate(descrizioni))
    corpo = {
        "model": MODELLO,
        "max_tokens": MAX_TOKEN,
        "system": _SISTEMA,
        "messages": [{"role": "user", "content": f"Leggi queste {len(descrizioni)} descrizioni:\n{lista}"}],
    }
    intestazioni = {"x-api-key": chiave, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    proprio = client is None
    client = client or httpx.AsyncClient(timeout=90)
    try:
        r = await client.post("https://api.anthropic.com/v1/messages", headers=intestazioni, json=corpo)
        r.raise_for_status()
        risposta = r.json()
        testo = "".join(b.get("text", "") for b in risposta.get("content", []) if isinstance(b, dict))
        if diagnosi is not None:
            diagnosi["stop_reason"] = risposta.get("stop_reason")
            diagnosi["inizio_risposta"] = testo[:120]
    finally:
        if proprio:
            await client.aclose()
    out: Dict[str, Dict[str, Any]] = {}
    for item in _estrai_array(testo):
        try:
            i = int(item.get("i", 0)) - 1
        except (TypeError, ValueError):
            continue
        if 0 <= i < len(descrizioni):
            out[descrizioni[i]] = valida(item, descrizioni[i])
    return out


def letture_per_impronta(docs: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {str(d.get("id")): d for d in docs if d.get("id") and d.get("versione") == VERSIONE}


async def _salva(db, letture: Dict[str, Dict[str, Any]]) -> int:
    if not letture:
        return 0
    from pymongo import UpdateOne

    adesso = datetime.now(timezone.utc).isoformat()
    ops = []
    for descrizione, lettura in letture.items():
        impronta = impronta_descrizione(descrizione)
        doc = {**lettura, "id": impronta, "descrizione": pulisci(descrizione), "versione": VERSIONE,
               "modello": MODELLO, "letto_il": adesso}
        ops.append(UpdateOne({"id": impronta}, {"$set": doc, "$setOnInsert": {"_id": impronta}}, upsert=True))
    await getattr(db, COLLEZIONE).bulk_write(ops, ordered=False)
    return len(ops)


async def _stato(db, **campi: Any) -> None:
    await db.sync_status.update_one({"_id": STATO_ID}, {"$set": campi}, upsert=True)


_in_corso = asyncio.Lock()


async def leggi_mancanti(db, descrizioni: Iterable[str], limite: int = 3000) -> Dict[str, Any]:
    """Legge le descrizioni che non hanno ancora una lettura valida.

    Idempotente: rilanciato subito dopo, trova ``da_leggere=0``."""
    if _in_corso.locked():
        return {"ok": False, "motivo": "lettura gia' in corso"}
    async with _in_corso:
        gia = letture_per_impronta(await getattr(db, COLLEZIONE).find({}, {"_id": 0, "id": 1, "versione": 1}).to_list(None))
        uniche: Dict[str, str] = {}
        for d in descrizioni:
            testo = pulisci(d)
            if not testo:
                continue
            impronta = impronta_descrizione(d)
            if impronta not in gia and impronta not in uniche:
                uniche[impronta] = d
        # vicine nella stessa chiamata le descrizioni dello stesso formato e con le
        # stesse parole: il modello le legge nello stesso modo (nomi coerenti)
        from app.lotti.servizi.confronto_fornitori import leggi

        def ordine(d: str):
            art = leggi(d)
            return (art.unita, art.misura or 0, " ".join(art.parole))

        da_leggere = sorted(uniche.values(), key=ordine)[:limite]
        adesso = datetime.now(timezone.utc).isoformat()
        if not _chiave_api():
            await _stato(db, stato="senza_chiave", da_leggere=len(uniche), aggiornato_il=adesso,
                         ultimo_errore="ANTHROPIC_API_KEY non configurata: nessuna lettura AI")
            return {"ok": False, "motivo": "ANTHROPIC_API_KEY non configurata", "da_leggere": len(uniche)}
        await _stato(db, stato="in_corso", iniziato_il=adesso, da_leggere=len(uniche), in_questo_giro=len(da_leggere),
                     letti=0, errori=0, ultimo_errore=None, modello=MODELLO, versione=VERSIONE)
        blocchi = [da_leggere[i:i + PER_CHIAMATA] for i in range(0, len(da_leggere), PER_CHIAMATA)]
        semaforo = asyncio.Semaphore(IN_PARALLELO)
        letti = errori = 0
        ultimo_errore: Optional[str] = None
        in_attesa: Dict[str, Dict[str, Any]] = {}
        scrittura = asyncio.Lock()

        import httpx

        async with httpx.AsyncClient(timeout=90) as client:
            async def uno(blocco: List[str]) -> None:
                nonlocal letti, errori, ultimo_errore
                async with semaforo:
                    risultato: Dict[str, Dict[str, Any]] = {}
                    diagnosi: Dict[str, Any] = {}
                    da_fare = list(blocco)
                    for tentativo in range(3):
                        try:
                            # le mancanti si rileggono a gruppi piu' piccoli: una risposta
                            # tagliata o senza JSON non deve perdere tutto il blocco
                            piccoli = [da_fare[i:i + max(1, len(da_fare) // (tentativo + 1))]
                                       for i in range(0, len(da_fare), max(1, len(da_fare) // (tentativo + 1)))]
                            for parte in piccoli if tentativo else [da_fare]:
                                risultato.update(await leggi_con_ai(parte, client=client, diagnosi=diagnosi))
                        except Exception as exc:  # noqa: BLE001 - si conta e si riprova
                            ultimo_errore = f"{type(exc).__name__}: {exc}"[:300]
                            await asyncio.sleep(5 * (tentativo + 1))
                        da_fare = [d for d in blocco if d not in risultato]
                        if not da_fare:
                            break
                    if da_fare and not ultimo_errore:
                        # risposta 200 ma senza letture: si dice perche', mai in silenzio
                        ultimo_errore = (f"{len(da_fare)} descrizioni senza lettura: stop_reason="
                                         f"{diagnosi.get('stop_reason')}, inizio risposta "
                                         f"{diagnosi.get('inizio_risposta')!r}")[:300]
                    if da_fare:
                        logger.warning("[lettura_ai] %d descrizioni su %d non lette: %s",
                                       len(da_fare), len(blocco), ultimo_errore)
                    if not risultato:
                        errori += len(blocco)
                        return
                async with scrittura:
                    in_attesa.update(risultato)
                    letti += len(risultato)
                    errori += len(blocco) - len(risultato)
                    if len(in_attesa) >= SCRITTURA_OGNI:
                        await _salva(db, dict(in_attesa))
                        in_attesa.clear()
                        await _stato(db, letti=letti, errori=errori, ultimo_errore=ultimo_errore)

            await asyncio.gather(*(uno(b) for b in blocchi))
        await _salva(db, in_attesa)
        fine = datetime.now(timezone.utc).isoformat()
        restano = len(uniche) - letti
        await _stato(db, stato="completato", completato_il=fine, letti=letti, errori=errori,
                     ultimo_errore=ultimo_errore, da_leggere=restano)
        logger.info("[lettura_ai] lette %d descrizioni, %d non lette, restano %d", letti, errori, restano)
        return {"ok": True, "letti": letti, "errori": errori, "restano": restano}
