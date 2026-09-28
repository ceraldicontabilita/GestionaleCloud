"""Avviso quando una fonte contabile smette di arrivare.

18/09/2026. Il titolare ha aperto Prima Nota → Banca e ha trovato solo
«Credito verso SumUp — POS ... Da verificare», un saldo a -186.866,90 e
nessun versamento. Nessuna logica era rotta: dal 24/08 non arriva piu'
nulla — niente estratto conto, niente corrispettivi RT, niente file Numia —
e l'unica fonte ancora viva (l'API SumUp) continuava a scrivere le sue
attese di accredito, che restano «da verificare» per sempre perche' non
c'e' nessun estratto conto contro cui chiuderle.

Il guasto vero non e' il dato mancante: e' che il sistema taceva. Una
pagina che mostra un saldo progressivo su una prima nota parziale, senza
dire che la fonte e' ferma da tre settimane, e' peggio di una pagina
vuota. Qui la mancanza diventa un avviso esplicito, con il numero di
giorni e l'ultima data vista.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Una fonte giornaliera ferma da piu' di una settimana non e' un ritardo:
# e' un'interruzione. Sotto i 7 giorni restano i ponti e le chiusure.
GIORNI_TOLLERATI = 7

# 19/09/2026: una fonte puo' arrivare regolarmente e restare comunque senza
# categoria (problema diverso da una fonte ferma: verificato il 18/09/2026,
# 1.764 dei 1.920 movimenti bancari 2026 — il 92% — non avevano categoria, e
# senza categoria un movimento non entra mai in Prima Nota Banca). Sopra
# questa soglia il saldo progressivo mostrato e' inattendibile e va detto;
# sotto il 10% i residui sono normali (causali non standard, bonifici a
# controparti mai viste) e non serve piu' avvisare.
SOGLIA_COPERTURA_CATEGORIA = 10.0

FONTI: tuple[dict[str, Any], ...] = (
    {
        "chiave": "estratto_conto",
        "collection": "estratto_conto_movimenti",
        "campi_data": ("data", "data_operazione", "date"),
        "etichetta": "Estratto conto bancario",
        "conseguenza": (
            "senza estratto conto nessun versamento, accredito POS o bonifico "
            "entra in Prima Nota, e le attese di accredito restano «da verificare»"
        ),
    },
    {
        "chiave": "corrispettivi",
        "collection": "corrispettivi",
        "campi_data": ("data", "date"),
        "etichetta": "Corrispettivi giornalieri",
        "conseguenza": (
            "senza corrispettivi non nascono il credito verso il gestore POS "
            "ne' l'incasso di cassa del giorno"
        ),
        # 28/09/2026, titolare: il PC del negozio si e' fermato e nessuno se
        # n'e' accorto per settimane. Il bar apre tutti i giorni (i
        # corrispettivi 2026 coprono ogni giorno della settimana), quindi
        # conta ogni giorno tranne le chiusure dichiarate, e dopo due giorni
        # d'apertura senza chiusura RT l'avviso arriva anche su Telegram.
        "giorni_tollerati": 2,
        "salta_chiusure": True,
        "telegram": True,
    },
    {
        "chiave": "pos_numia",
        # La chiusura del giorno, da qualunque fonte: export del terminale o
        # ricostruzione dagli accrediti dell'estratto conto (NUMIA non ha API).
        "collection": "chiusure_pos_manuali",
        "campi_data": ("data", "date"),
        "solo_gestore": "numia",
        # 28/09/2026, titolare: Numia dismesso dopo il 04/09/2026, restano i
        # terminali SumUp. Il fermo si misura fino all'ultima vendita Numia
        # accreditata in banca, non fino a oggi: un terminale spento non e'
        # una fonte ferma, un giorno accreditato senza chiusura si'.
        "riferimento": "ultima_vendita_numia_in_banca",
        "etichetta": "Chiusure POS Numia",
        "conseguenza": (
            "senza la chiusura del giorno l'accredito Numia dell'estratto "
            "conto non si puo' riconciliare per giorno di vendita"
        ),
    },
)


def _oggi() -> date:
    return datetime.now(timezone.utc).date()


async def _riferimento(db, fonte: Dict[str, Any], oggi: date) -> date:
    """Fino a che giorno la fonte doveva arrivare: oggi, salvo le fonti che
    dipendono da un terminale che puo' essere spento."""
    if fonte.get("riferimento") != "ultima_vendita_numia_in_banca":
        return oggi
    from app.services.ricostruzione_pos_estratto_conto import incassi_numia_per_giorno_vendita

    try:
        giorni = await incassi_numia_per_giorno_vendita(db, anno=str(oggi.year))
    except Exception as exc:  # noqa: BLE001 - senza accrediti leggibili si usa oggi
        logger.warning("Fonti ferme: accrediti Numia non leggibili (%s: %s)", type(exc).__name__, exc)
        return oggi
    ultime = [g for g in (_giorno(k) for k in giorni) if g]
    return min(max(ultime), oggi) if ultime else oggi


def _giorno(valore: Any) -> Optional[date]:
    testo = str(valore or "")[:10]
    if len(testo) != 10:
        return None
    try:
        return date.fromisoformat(testo)
    except ValueError:
        return None


async def _ultima_data(db, fonte: Dict[str, Any]) -> Optional[date]:
    """Data piu' recente della collezione, letta senza payload.

    Legge la proiezione leggera: la collezione delle transazioni POS ha
    decine di migliaia di righe e rileggerle intere a ogni giro di
    scheduler costerebbe piu' del controllo stesso.
    """
    from app.document_repository import metadata_projection

    collection = fonte["collection"]
    try:
        documenti = await db[collection].find({}, metadata_projection(collection)).to_list(None)
    except Exception as exc:  # noqa: BLE001 - una fonte illeggibile non ferma le altre
        logger.warning("Fonti ferme: %s non leggibile (%s)", collection, exc)
        return None
    massimo: Optional[date] = None
    if fonte.get("solo_gestore"):
        from app.services.scritture_contabili import normalizza_gestore_pos

        documenti = [d for d in documenti
                     if normalizza_gestore_pos(d.get("gestore")) == fonte["solo_gestore"]]
    for documento in documenti:
        for campo in fonte["campi_data"]:
            giorno = _giorno(documento.get(campo))
            if giorno and (massimo is None or giorno > massimo):
                massimo = giorno
                break
    return massimo


async def _giorni_fermi(db, fonte: Dict[str, Any], ultima: date, riferimento: date) -> int:
    """Giorni dall'ultimo dato; per chi lo chiede, senza i giorni di chiusura
    dell'attivita' (ferie, ristrutturazione: nessun corrispettivo e' dovuto)."""
    giorni = (riferimento - ultima).days
    if giorni <= 0 or not fonte.get("salta_chiusure"):
        return giorni
    from datetime import timedelta

    from app.services.chiusure_attivita import giorni_chiusi

    da = (ultima + timedelta(days=1)).isoformat()
    try:
        chiusi = await giorni_chiusi(db, da, riferimento.isoformat())
    except Exception as exc:  # noqa: BLE001 - senza registro si contano tutti
        logger.warning("Fonti ferme: chiusure non leggibili (%s: %s)", type(exc).__name__, exc)
        chiusi = set()
    return giorni - len(chiusi)


async def _avvisa_telegram(fonte: Dict[str, Any], dettaglio: str) -> None:
    from app.services.telegram_notifications import send_notification

    esito = await send_notification(f"<b>Fonte ferma</b>\n{dettaglio}")
    if not esito.get("success"):
        logger.warning("Fonti ferme: Telegram non inviato per %s (%s)",
                       fonte["chiave"], esito.get("error"))


async def controlla_fonti_ferme(db, *, giorni_tollerati: int = GIORNI_TOLLERATI,
                                oggi: Optional[date] = None) -> Dict[str, Any]:
    """Apre un avviso per ogni fonte ferma da troppi giorni, lo chiude quando
    la fonte riparte. Non scrive nessun movimento: dichiara soltanto che il
    dato non c'e', perche' un dato mancante non si inventa."""
    from app.services.alert_engine import genera_alert, risolvi_alert

    riferimento = oggi or _oggi()
    esito: Dict[str, Any] = {"controllate": 0, "ferme": [], "riprese": [], "vuote": []}
    for fonte in FONTI:
        esito["controllate"] += 1
        ultima = await _ultima_data(db, fonte)
        chiave = fonte["chiave"]
        if ultima is None:
            esito["vuote"].append(chiave)
            continue
        giorni = await _giorni_fermi(db, fonte, ultima, await _riferimento(db, fonte, riferimento))
        if giorni > fonte.get("giorni_tollerati", giorni_tollerati):
            dettaglio = (
                f"{fonte['etichetta']}: nessun dato da {giorni} giorni "
                f"(ultimo: {ultima.strftime('%d/%m/%Y')}). "
                f"Conseguenza: {fonte['conseguenza']}."
            )
            nuovo = await genera_alert(
                "FONTE_CONTABILE_FERMA", chiave, fonte["collection"], dettaglio, db,
                extra={"fonte": chiave, "ultima_data": ultima.isoformat(),
                       "giorni_fermi": giorni, "etichetta": fonte["etichetta"]},
            )
            # Un messaggio quando l'avviso nasce, non a ogni giro orario.
            if nuovo and fonte.get("telegram"):
                await _avvisa_telegram(fonte, dettaglio)
            esito["ferme"].append({"fonte": chiave, "ultima_data": ultima.isoformat(),
                                   "giorni": giorni})
        else:
            chiusi = await risolvi_alert("FONTE_CONTABILE_FERMA", chiave, db,
                                         resolved_by="fonte_ripartita")
            if chiusi:
                esito["riprese"].append(chiave)
    return esito


async def stato_fonti(db, *, oggi: Optional[date] = None) -> List[Dict[str, Any]]:
    """Ultima data e giorni di fermo per ogni fonte, per mostrarlo in pagina."""
    riferimento = oggi or _oggi()
    righe: List[Dict[str, Any]] = []
    for fonte in FONTI:
        ultima = await _ultima_data(db, fonte)
        giorni = (await _giorni_fermi(db, fonte, ultima, await _riferimento(db, fonte, riferimento))
                  if ultima else None)
        righe.append({
            "fonte": fonte["chiave"],
            "etichetta": fonte["etichetta"],
            "ultima_data": ultima.isoformat() if ultima else None,
            "giorni_fermi": giorni,
            "ferma": bool(giorni is not None
                          and giorni > fonte.get("giorni_tollerati", GIORNI_TOLLERATI)),
            "conseguenza": fonte["conseguenza"],
        })
    return righe


async def copertura_categoria_banca(
    db, *, anno: Optional[int] = None, soglia: float = SOGLIA_COPERTURA_CATEGORIA,
) -> Dict[str, Any]:
    """Quota di movimenti bancari dell'anno senza categoria riconosciuta.

    Diverso dal fermo di una fonte: l'estratto conto puo' arrivare puntuale
    ogni mese e i suoi movimenti restare comunque senza categoria (nessuna
    causale contabile nota), e senza categoria un movimento non entra mai in
    Prima Nota Banca (`entra_in_prima_nota`). Il saldo progressivo mostrato
    in pagina, in quel caso, non e' il saldo del conto: e' il saldo della
    sola minoranza di movimenti che il motore ha riconosciuto.
    """
    anno_riferimento = anno or _oggi().year
    collection = db["estratto_conto_movimenti"]
    query_anno = {"data": {"$regex": f"^{anno_riferimento}"}}
    try:
        totale = await collection.count_documents(query_anno)
        senza_categoria = await collection.count_documents({
            **query_anno,
            "$or": [{"categoria": None}, {"categoria": ""}, {"categoria": {"$exists": False}}],
            # Una riga segnata da ignorare (copia, duplicato) non aspetta categoria.
            "ignorata": {"$ne": True},
        })
    except Exception as exc:  # noqa: BLE001 - non deve far fallire la pagina
        logger.warning("Copertura categoria banca non calcolabile (%s)", exc)
        return {"anno": anno_riferimento, "totale": None, "senza_categoria": None,
                "percentuale": None, "soglia": soglia, "sopra_soglia": False}

    percentuale = round((senza_categoria / totale) * 100, 1) if totale else 0.0
    return {
        "anno": anno_riferimento,
        "totale": totale,
        "senza_categoria": senza_categoria,
        "percentuale": percentuale,
        "soglia": soglia,
        "sopra_soglia": totale > 0 and percentuale > soglia,
    }
