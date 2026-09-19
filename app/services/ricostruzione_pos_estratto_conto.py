"""Il POS reale NUMIA ricostruito dagli accrediti dell'estratto conto.

**Perche' esiste.** Il gestionale costruisce il trasferimento POS del giorno
dalla chiusura reale del terminale (`chiusure_pos_manuali`), mai
dall'elettronico XML — decisione del titolare del 07/08/2026, perche' l'XML
non sa dire quanto sia passato da NUMIA e quanto da SumUp. Di SumUp le
chiusure arrivano da sole dall'API. **NUMIA non ha API**, e nessuno digita la
chiusura serale: in `chiusure_pos_manuali` non e' mai entrata una riga NUMIA.
Risultato misurato il 19/09/2026: 180 giornate del 2026 su 183 ferme in
`attende_chiusura_pos_reale`, e 888 accrediti NUMIA per 342.087,35 EUR senza
nessun trasferimento da riconciliare.

**La fonte.** Gli accrediti NUMIA sono gia' nell'estratto conto e portano in
causale il **giorno operativo** (`DEL gg/mm/aa`), diverso dalla data di
accredito. Il titolare (19/09/2026): «vanno sommati con la data di accredito
dell'estratto conto, in descrizione c'e' un incasso del giorno; sommati tutti
gli importi dello stesso giorno dovranno quadrare con la registrazione XML
pagamento elettronico». I dati gli danno ragione al centesimo: su 30 giornate
del 2026 in cui NUMIA e' l'unico circuito, la somma degli accrediti per
giorno operativo e l'elettronico dell'XML coincidono esattamente.

**Perche' non e' un confronto circolare.** L'accredito diventa l'attesa, e
poi la riconcilia. Il controllo che conta pero' e' un altro, ed e' fiscale:
l'elettronico dichiarato nell'XML contro il denaro davvero incassato dal POS.
Quelle due grandezze restano indipendenti, e il confronto vive nella Coerenza
POS, non qui.

**Le commissioni.** NUMIA le addebita a parte (109 righe, -3.166,86 EUR sul
2026), quindi gli accrediti sono al lordo e si confrontano con l'XML senza
correzioni. Verificato: se fossero al netto, nessuna giornata quadrerebbe al
centesimo.

**Cosa non fa.** Non tocca SumUp, che la sua fonte ce l'ha. Non sovrascrive
una chiusura letta dal terminale o arrivata da un'API: `FONTE_ESTRATTO_CONTO`
sta sotto entrambe nella scala di attendibilita'.
"""
import logging
from typing import Any, Dict, List, Optional

from app.services import conti_pos
from app.services.scritture_contabili import (
    FONTE_ESTRATTO_CONTO,
    normalizza_gestore_pos,
    registra_chiusura_pos_reale,
)

logger = logging.getLogger(__name__)

__all__ = [
    "incassi_numia_per_giorno_vendita",
    "giorni_gia_coperti",
    "ricostruisci_chiusure_numia",
]

COLL_EC = "estratto_conto_movimenti"
COLL_CHIUSURE = "chiusure_pos_manuali"

NOTE = "ricostruito dagli accrediti dell'estratto conto (NUMIA non ha API)"


async def incassi_numia_per_giorno_vendita(
    db, *, anno: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """Somma gli accrediti NUMIA per giorno operativo.

    Un solo prefetch: una interrogazione per giorno, su un anno di accrediti,
    e' proibita dal §4. Le righe gia' riconciliate contano lo stesso — il
    giorno operativo e' un fatto, non uno stato di lavorazione.
    """
    from app.services.pos_evidence import (
        _e_accredito_pos_numia_con_giorno,
        _giorno_operazione_pos,
    )

    per_giorno: Dict[str, Dict[str, Any]] = {}
    async for mov in db[COLL_EC].find(
        {"tipo": {"$ne": "uscita"}},
        {"_id": 0, "id": 1, "data": 1, "importo": 1,
         "descrizione": 1, "descrizione_originale": 1},
    ):
        descrizione = mov.get("descrizione_originale") or mov.get("descrizione") or ""
        if not _e_accredito_pos_numia_con_giorno(descrizione):
            continue
        importo = float(mov.get("importo") or 0)
        # Un rimborso o uno storno arriva come importo negativo sulla stessa
        # causale: va sottratto dall'incasso del giorno, non ignorato.
        giorno = _giorno_operazione_pos(descrizione, str(mov.get("data") or ""))
        if anno and not giorno.startswith(str(anno)):
            continue
        voce = per_giorno.setdefault(giorno, {"importo": 0.0, "accrediti": 0})
        voce["accrediti"] += 1
        voce["importo"] = round(voce["importo"] + importo, 2)
    return per_giorno


async def giorni_gia_coperti(db) -> Dict[str, str]:
    """Giorni che hanno gia' una chiusura NUMIA, con la fonte che l'ha scritta."""
    coperti: Dict[str, str] = {}
    async for riga in db[COLL_CHIUSURE].find(
        {}, {"_id": 0, "data": 1, "gestore": 1, "fonte_dato": 1},
    ):
        if normalizza_gestore_pos(riga.get("gestore")) != conti_pos.NUMIA:
            continue
        giorno = str(riga.get("data") or "")[:10]
        if giorno:
            coperti[giorno] = str(riga.get("fonte_dato") or "")
    return coperti


async def ricostruisci_chiusure_numia(
    db, *, dry_run: bool = True, anno: Optional[str] = None,
    actor: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Scrive la chiusura NUMIA mancante di ogni giorno con accrediti.

    Idempotente: un giorno che ha gia' la sua chiusura viene saltato, qualunque
    fonte l'abbia scritta. Un giorno che chiude a zero o in negativo (solo
    storni) non produce una chiusura: un incasso negativo non esiste, e
    `registra_chiusura_pos_reale` lo rifiuterebbe.
    """
    incassi = await incassi_numia_per_giorno_vendita(db, anno=anno)
    coperti = await giorni_gia_coperti(db)

    da_scrivere = {
        giorno: voce for giorno, voce in incassi.items()
        if giorno not in coperti and voce["importo"] > 0
    }
    saltati_negativi = sorted(
        g for g, v in incassi.items() if g not in coperti and v["importo"] <= 0
    )

    esito: Dict[str, Any] = {
        "dry_run": dry_run,
        "anno": anno,
        "giorni_con_accrediti": len(incassi),
        "giorni_gia_coperti": len([g for g in incassi if g in coperti]),
        "giorni_da_ricostruire": len(da_scrivere),
        "importo_da_ricostruire": round(
            sum(v["importo"] for v in da_scrivere.values()), 2),
        "giorni_saltati_senza_incasso": saltati_negativi,
        "scritti": 0,
        "errori": 0,
        "motivi_errore": [],
        "primi_giorni": [
            {"giorno": g, "accrediti": da_scrivere[g]["accrediti"],
             "importo": da_scrivere[g]["importo"]}
            for g in sorted(da_scrivere)[:5]
        ],
    }
    if dry_run:
        return esito

    motivi: List[str] = esito["motivi_errore"]
    for giorno in sorted(da_scrivere):
        try:
            await registra_chiusura_pos_reale(
                db, giorno, da_scrivere[giorno]["importo"],
                gestore=conti_pos.NUMIA, fonte=FONTE_ESTRATTO_CONTO,
                note=NOTE, actor=actor,
            )
            esito["scritti"] += 1
        except Exception as exc:  # noqa: BLE001 — l'esito va riportato, non nascosto
            esito["errori"] += 1
            if len(motivi) < 10:
                motivi.append(f"{giorno}: {exc}")
            logger.exception("Chiusura NUMIA non ricostruita per %s", giorno)
    return esito
