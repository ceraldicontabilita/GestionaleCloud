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

**Identificazione col web** (``identifica_col_web``): per le righe del Dizionario
senza categoria certa il modello cerca il prodotto con lo strumento server-side
di Anthropic (``cerca_sul_web``, lo stesso della ricerca delle schede tecniche:
stessa chiave, nessuna variabile nuova; la chiamata e il suo registro sono
quelli del client unico ``anthropic_llm_client.LlmChat``, scopo ``lotti_web``). La categoria si scrive da sola **solo**
se web e testo della fattura concordano (marca o prodotto nella descrizione, o
EAN), con confidenza alta e almeno una fonte, e si dichiara (``categoria_fonte =
"web"``, ``abbinato_ai``, ``categoria_web_fonti``); i dubbi restano proposte in
``nome_mapping`` (``fonte = "web"``, ``GET /proposte-web``). Mai categorie fuori
da ``dizionario_ingredienti.CATEGORIE``; non certo = nessuna categoria + motivo.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional

from app.lotti.servizi.confronto_fornitori import impronta_descrizione, pulisci
from app.services.anthropic_llm_client import LlmChat, chiave_api, modello_veloce

logger = logging.getLogger(__name__)

COLLEZIONE = "articoli_letti_ai"
STATO_ID = "lettura_articoli_ai"
VERSIONE = 1
SCOPO = "lotti_letture"
SCOPO_WEB = "lotti_web"
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
    return chiave_api()


def _client(scopo: str, *, system: str = "", max_tokens: int) -> LlmChat:
    """Il solo client (modello veloce, registro e tetto del gestionale)."""
    return LlmChat(_chiave_api(), system_prompt=system, model=modello_veloce(), timeout_s=90.0,
                   max_tokens=max_tokens, scopo=scopo)


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
    Torna {descrizione: lettura validata}; le mancanti restano da leggere.
    ``client``: un ``LlmChat`` (o un finto con ``crea_messaggio``)."""
    if not _chiave_api() or not descrizioni:
        return {}
    client = client or _client(SCOPO, system=_SISTEMA, max_tokens=MAX_TOKEN)
    lista = "\n".join(f"{i + 1}. {pulisci(d)}" for i, d in enumerate(descrizioni))
    risposta = await client.crea_messaggio(
        [{"role": "user", "content": f"Leggi queste {len(descrizioni)} descrizioni:\n{lista}"}],
        system=_SISTEMA, max_tokens=MAX_TOKEN)
    testo = risposta.get("testo") or ""
    if diagnosi is not None:
        diagnosi["stop_reason"] = risposta.get("stop_reason")
        diagnosi["inizio_risposta"] = testo[:120]
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
               "modello": modello_veloce(), "letto_il": adesso}
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
                     letti=0, errori=0, ultimo_errore=None, modello=modello_veloce(), versione=VERSIONE)
        blocchi = [da_leggere[i:i + PER_CHIAMATA] for i in range(0, len(da_leggere), PER_CHIAMATA)]
        semaforo = asyncio.Semaphore(IN_PARALLELO)
        letti = errori = 0
        ultimo_errore: Optional[str] = None
        in_attesa: Dict[str, Dict[str, Any]] = {}
        scrittura = asyncio.Lock()

        import contextlib

        # un solo client per tutto il giro (le chiamate corrono in parallelo nel suo thread pool)
        async with contextlib.nullcontext(_client(SCOPO, system=_SISTEMA, max_tokens=MAX_TOKEN)) as client:
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


# ── ricerca sul web (strumento server-side di Anthropic) ────────────────────


class RicercaWebErrore(RuntimeError):
    """La ricerca web e' fallita (risposta non 200 o corpo illeggibile)."""


async def cerca_sul_web(prompt: str, *, max_tokens: int = 1500, max_uses: int = 3,
                        client=None) -> Dict[str, Any]:
    """Una domanda al modello con lo strumento server-side di ricerca web: l'unico punto che lo chiama.

    Torna ``{"testo": risposta, "fonti": [url delle pagine consultate]}``. Le
    fonti vengono dai blocchi del tool (non da cio' che il modello scrive).
    Un errore dell'API (risposta non 200, tetto) e' ``RicercaWebErrore``."""
    if not _chiave_api():
        raise RicercaWebErrore("manca ANTHROPIC_API_KEY")
    client = client or _client(SCOPO_WEB, max_tokens=max_tokens)
    try:
        return await client.cerca_sul_web(prompt, max_tokens=max_tokens, max_uses=max_uses)
    except RicercaWebErrore:
        raise
    except Exception as exc:  # noqa: BLE001 - un solo tipo di errore per chi chiama
        raise RicercaWebErrore(f"{type(exc).__name__}: {str(exc)[:200]}") from exc


# ── identificazione del prodotto col web per il Dizionario ──────────────────

# Costi: 5 descrizioni a giro (un giro ogni 20 minuti nello scheduler), 2 ricerche
# per descrizione, al massimo TETTO_WEB_GIORNALIERO chiamate al giorno (giorno di Roma, contate
# nel registro unico del client, scopo ``lotti_web``).
# Una descrizione cercata non si ricerca per RIPROVA_WEB_GIORNI giorni.
WEB_PER_GIRO = 5
WEB_MAX_USES = 2
TETTO_WEB_GIORNALIERO = 120
RIPROVA_WEB_GIORNI = 30
STATO_WEB_ID = "identifica_col_web"

_SISTEMA_WEB = (
    "Sei l'assistente di magazzino di una pasticceria italiana. Ti do la descrizione ESATTA di una riga di fattura "
    "di un grossista alimentare (abbreviata, maiuscola, con formato e confezione). Cerca sul web che prodotto e', "
    "preferendo la pagina del produttore o di un catalogo affidabile. "
    "Rispondi SOLO con un oggetto JSON piatto, nessun altro testo: "
    '{"marca": "...", "prodotto": "...", "formato": "...", "categoria": "...", "ean": "...", '
    '"confidenza": "alta|media|bassa", "motivo": "..."}. '
    "categoria DEVE essere esattamente una di queste: {categorie}. "
    'Se non sei certo del prodotto reale usa "categoria": null e spiega in motivo: non inventare mai. '
    'ean solo se lo hai letto in una pagina, altrimenti "". confidenza alta solo se hai trovato il prodotto esatto.'
)


def _adesso_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_piatto(testo: str) -> Dict[str, Any]:
    for grezzo in reversed(re.findall(r"\{[^{}]*\}", testo or "", re.S)):
        try:
            dato = json.loads(grezzo)
        except json.JSONDecodeError:
            continue
        if isinstance(dato, dict):
            return dato
    return {}


def _parole(testo: Any) -> List[str]:
    return [p for p in re.findall(r"[a-zà-ÿ0-9]+", str(testo or "").lower()) if len(p) >= 4 and not p.isdigit()]


def _compare_nel_testo(valore: Any, descrizione: str) -> bool:
    """Una parola significativa del valore compare (anche abbreviata, min. 4 lettere) nella descrizione."""
    nel_testo = _parole(descrizione)
    return any(a.startswith(b) or b.startswith(a) for a in _parole(valore) for b in nel_testo)


def valida_identificazione(dato: Dict[str, Any], descrizione: str) -> Dict[str, Any]:
    """La risposta del web ripulita. ``categoria`` e' None se fuori elenco; ``concorda``
    dice se il testo di fattura conferma marca/prodotto o l'EAN."""
    from app.lotti.servizi.dizionario_ingredienti import CATEGORIE

    def t(campo: str, massimo: int = 120) -> str:
        return re.sub(r"\s+", " ", str(dato.get(campo) or "")).strip()[:massimo]

    ufficiali = {c.lower(): c for c in CATEGORIE}
    categoria = ufficiali.get(t("categoria").lower())
    motivo = t("motivo", 300)
    if t("categoria") and not categoria:
        motivo = f"categoria fuori elenco: {t('categoria', 40)}"
    elif not categoria and not motivo:
        motivo = "il web non ha identificato il prodotto"
    confidenza = t("confidenza", 10).lower()
    ean = re.sub(r"\D", "", t("ean", 20))
    ean_scritto = len(ean) in (8, 12, 13, 14) and ean in re.sub(r"\D", "", str(descrizione))
    marca, prodotto = t("marca", 60), t("prodotto", 100)
    concorda = ean_scritto or _compare_nel_testo(marca, descrizione) or _compare_nel_testo(prodotto, descrizione)
    return {"marca": marca, "prodotto": prodotto, "formato": t("formato", 60), "categoria": categoria,
            "confidenza": confidenza if confidenza in ("alta", "media", "bassa") else "bassa",
            "motivo": motivo, "concorda": bool(concorda)}


def decidi_associazione(ident: Dict[str, Any], fonti: List[str], descrizione: str) -> str:
    """``certo`` (si scrive da sola), ``proposta`` (da confermare) o ``niente``.

    Certo solo con categoria ufficiale, confidenza alta, almeno una fonte, concordanza col testo
    di fattura e nessun contrasto con la categoria che il nome dice da solo."""
    from app.lotti.servizi.dizionario_ingredienti import categoria_da_testo

    if not ident.get("categoria"):
        return "niente"
    dal_nome = categoria_da_testo(descrizione)
    if (ident["confidenza"] == "alta" and fonti and ident["concorda"]
            and (dal_nome is None or dal_nome == ident["categoria"])):
        return "certo"
    return "proposta" if ident.get("prodotto") else "niente"


def _oggi_roma() -> str:
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("Europe/Rome")).date().isoformat()


async def _stato_web(db, **campi: Any) -> None:
    await db.sync_status.update_one({"_id": STATO_WEB_ID}, {"$set": campi}, upsert=True)


async def _chiamate_oggi(db) -> int:
    """Chiamate web di oggi dal registro unico del gestionale (scopo ``lotti_web``);
    senza l'archivio del gestionale (test) si conta sullo stato di Lotti."""
    from app.services.anthropic_llm_client import _archivio, chiamate_oggi

    archivio = _archivio()
    if archivio is not None:
        return await chiamate_oggi(archivio, scopo=SCOPO_WEB)
    stato = await db.sync_status.find_one({"_id": STATO_WEB_ID}, {"_id": 0, "giorno": 1, "chiamate": 1}) or {}
    return int(stato.get("chiamate") or 0) if stato.get("giorno") == _oggi_roma() else 0


async def _conta_chiamata(db) -> None:
    """Contatore di riserva per quando il registro unico non c'e' (test)."""
    from app.services.anthropic_llm_client import _archivio

    if _archivio() is None:
        await _stato_web(db, giorno=_oggi_roma(), chiamate=await _chiamate_oggi(db) + 1)


async def _candidati_web(db, limite: int) -> List[Dict[str, Any]]:
    """Righe del Dizionario senza categoria certa mai cercate (o cercate piu' di N giorni fa)."""
    from datetime import timedelta

    from app.lotti.servizi.dizionario_ingredienti import e_bevanda

    soglia = (datetime.now(timezone.utc) - timedelta(days=RIPROVA_WEB_GIORNI)).isoformat()
    righe = await db.dizionario_prodotti.find(
        {"$and": [
            {"categoria_fonte": {"$ne": "manuale"}},
            {"escluso_ricette": {"$ne": True}},
            {"$or": [{"categoria_canonica": {"$in": [None, "", "Varie Alimentari"]}},
                     {"categoria_canonica": {"$exists": False}}]},
            {"$or": [{"web_cercato_at": {"$exists": False}}, {"web_cercato_at": None},
                     {"web_cercato_at": {"$lt": soglia}}]},
        ]},
        {"_id": 0, "id": 1, "nome_originale": 1, "nome_normalizzato": 1, "fornitore": 1,
         "categoria_canonica": 1},
    ).to_list(1000)
    servizi = {str(d.get("id")) for d in await getattr(db, COLLEZIONE).find(
        {"servizio": True}, {"_id": 0, "id": 1}).to_list(None)}
    out = []
    for r in righe:
        nome = str(r.get("nome_originale") or "").strip()
        if not r.get("id") or len(nome) < 4 or e_bevanda(r) or impronta_descrizione(nome) in servizi:
            continue
        out.append(r)
        if len(out) >= limite:
            break
    return out


async def _proponi_mapping(db, riga: Dict[str, Any], ident: Dict[str, Any], fonti: List[str]) -> bool:
    """Proposta da confermare in ``nome_mapping`` (fonte web). Mai su una riga che esiste gia'
    e non e' una proposta web: la conferma o l'apprendimento di una persona vincono."""
    from app.lotti.servizi.articoli_fattura import chiave_descrizione, invalida_cache

    chiave = chiave_descrizione(riga.get("nome_originale"))
    if not chiave:
        return False
    esistente = await db.nome_mapping.find_one({"descrizione_key": chiave}, {"_id": 0, "fonte": 1, "confermato": 1})
    if esistente and (esistente.get("confermato") is True or esistente.get("fonte") != "web"):
        return False
    campi = {
        "descrizione_key": chiave, "descrizione_originale": str(riga.get("nome_originale") or "").strip(),
        "nome_canc": ident["prodotto"], "ingredienti_ricetta": [],
        "alimentare": ident["categoria"] != "Non Alimentare",
        "fonte": "web", "confermato": False, "proposto_at": _adesso_iso(),
        "categoria": ident["categoria"], "confidenza": ident["confidenza"],
        "cosa_e": " ".join(x for x in (ident["marca"], ident["prodotto"], ident["formato"]) if x),
        "fornitore": riga.get("fornitore") or "",
    }
    if fonti:
        campi["fonte_url"] = fonti[0]
    if ident["motivo"]:
        campi["note"] = ident["motivo"]
    await db.nome_mapping.update_one({"descrizione_key": chiave}, {"$set": campi}, upsert=True)
    invalida_cache()
    return True


async def identifica_col_web(db, limite: int = WEB_PER_GIRO, client=None) -> Dict[str, Any]:
    """Un giro: cerca sul web le prime ``limite`` righe senza categoria certa.

    Idempotente: ogni riga cercata porta ``web_cercato_at`` e per ``RIPROVA_WEB_GIORNI`` giorni non
    si ricerca, quindi il secondo giro sulle stesse righe trova 0 candidati. Un errore dell'API non
    marca la riga (si riprova al giro dopo) e ferma il giro."""
    from app.lotti.servizi.dizionario_ingredienti import CATEGORIE

    esito: Dict[str, Any] = {"ok": True, "cercate": 0, "associate": 0, "proposte": 0,
                             "non_identificate": 0, "errori": 0}
    if not _chiave_api():
        return {**esito, "ok": False, "motivo": "ANTHROPIC_API_KEY non configurata"}
    disponibili = TETTO_WEB_GIORNALIERO - await _chiamate_oggi(db)
    if disponibili <= 0:
        return {**esito, "motivo": "tetto giornaliero raggiunto"}
    sistema = _SISTEMA_WEB.replace("{categorie}", "; ".join(CATEGORIE))
    for riga in await _candidati_web(db, min(limite, disponibili)):
        descrizione = str(riga["nome_originale"]).strip()
        forn = f' Il fornitore e\' "{riga["fornitore"]}".' if riga.get("fornitore") else ""
        await _conta_chiamata(db)
        try:
            ris = await cerca_sul_web(f"{sistema}\n\nDescrizione di fattura: «{descrizione}».{forn}",
                                      max_uses=WEB_MAX_USES, client=client)
        except Exception as exc:  # noqa: BLE001 - la riga non si marca: si riprova al giro dopo
            esito["errori"] += 1
            esito["ultimo_errore"] = f"{type(exc).__name__}: {exc}"[:300]
            logger.warning("[identifica_web] ricerca fallita: %s: %s", type(exc).__name__, exc)
            break
        esito["cercate"] += 1
        ident = valida_identificazione(_json_piatto(ris["testo"]), descrizione)
        decisione = decidi_associazione(ident, ris["fonti"], descrizione)
        adesso = _adesso_iso()
        campi: Dict[str, Any] = {"web_cercato_at": adesso, "web_esito": decisione}
        if decisione == "certo":
            campi.update({"categoria_canonica": ident["categoria"], "categoria_fonte": "web",
                          "categoria_auto_il": adesso, "categoria_web_fonti": ris["fonti"][:3],
                          "abbinato_ai": True,
                          "web_prodotto": " ".join(x for x in (ident["marca"], ident["prodotto"],
                                                               ident["formato"]) if x)})
            esito["associate"] += 1
        elif decisione == "proposta":
            if await _proponi_mapping(db, riga, ident, ris["fonti"]):
                esito["proposte"] += 1
        else:
            campi["web_motivo"] = ident["motivo"]
            esito["non_identificate"] += 1
        await db.dizionario_prodotti.update_one({"id": riga["id"]}, {"$set": campi})
    await _stato_web(db, ultimo_giro=_adesso_iso(), ultimo_esito={k: v for k, v in esito.items() if k != "ok"})
    return esito
