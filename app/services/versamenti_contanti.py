"""Versamenti e prelievi di contante: riconosciuti dall'estratto conto.

Il titolare: «non devo far riparare niente all'applicazione — nell'estratto
conto c'e' il segno, la descrizione e l'importo, quindi non vedo perche'
dovrebbe sbagliare». Ha ragione, e questo modulo sostituisce il vecchio
comando «Ripara versamenti», che era un bottone da premere a mano e che il
15/09/2026 era stato spento perche' sbagliava.

**Perche' sbagliava, e perche' qui non succede.** In Prima Nota Cassa una
gamba del versamento puo' esserci gia': non scritta a mano — il titolare non
ne registra nessuno a mano (20/09/2026) — ma portata dall'integrazione
legacy, che il 15/09/2026 ha importato 18 righe «Versamento contanti in
banca» dall'archivio CeraldiFatture. Il vecchio codice creava comunque la
gamba di cassa, e il contante usciva due volte. Qui la gamba si cerca
**prima**: se c'e' gia' si collega, non si riscrive.

E si collega **solo a una riga che si dichiara versamento** (categoria di
trasferimento, oppure la parola in descrizione). Cercarla per solo importo e
data, come faceva la prima versione di questo modulo, e' la stessa regola
vietata altrove: il giorno in cui un pagamento fornitore in contanti coincide
d'importo con un versamento, quella riga verrebbe presa, la sua categoria
sovrascritta con `trasferimento_interno` e il pagamento sparirebbe come tale.

Le due gambe:
- **versamento** (entrata in banca): uscita da Cassa, entrata in Banca;
- **prelievo** (uscita dalla banca): uscita da Banca, entrata in Cassa.

Sono due movimenti speculari collegati da `trasferimento_collegato_id`, con
categoria `trasferimento_interno` e lo stesso `operation_id`, come prescrive
CLAUDE.md — non un flag sul singolo movimento.

Uno **storno** non e' un secondo versamento: e' una rettifica della banca, e
resta fuori.

L'idempotenza e' sull'id della riga di estratto conto: rileggere lo stesso
estratto non crea niente di nuovo. Non serve nessun comando di riparazione,
perche' non c'e' niente da riparare.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.services.scritture_contabili import scrivi_movimento_se_assente

logger = logging.getLogger(__name__)

CATEGORIA = "trasferimento_interno"
# Giorni fra l'uscita del contante dal negozio e la data di contabilizzazione
# in banca. Tre coprono anche il versamento del venerdi' registrato il lunedi'.
GIORNI_TOLLERANZA = 3

#: Le categorie con cui una riga di Prima Nota **dichiara** di essere una
#: gamba di trasferimento. Misurate in produzione il 20/09/2026: 80 righe
#: `trasferimento_interno` e 36 `Versamento Banca`, nessun altro valore.
CATEGORIE_TRASFERIMENTO = frozenset({"trasferimento_interno", "versamento banca"})

#: Chi non ha la categoria lo dice nella descrizione: le 18 righe legacy sono
#: «Versamento contanti in banca — Da estratto conto».
PAROLE_TRASFERIMENTO = ("versament", "prelev", "preliev")


def _data_iso(doc: Dict[str, Any]) -> str:
    grezza = str(doc.get("data") or doc.get("date") or doc.get("data_contabile") or "")
    if len(grezza) >= 10 and grezza[4] == "-":
        return grezza[:10]
    if len(grezza) == 10 and grezza[2] == "/":
        giorno, mese, anno = grezza.split("/")
        return f"{anno}-{mese}-{giorno}"
    return grezza[:10]


def _importo(doc: Dict[str, Any]) -> float:
    try:
        return round(abs(float(doc.get("importo") or doc.get("amount") or 0)), 2)
    except (TypeError, ValueError):
        return 0.0


def _verso(doc: Dict[str, Any]) -> str:
    valore = str(doc.get("tipo") or doc.get("type") or "").strip().lower()
    if valore in {"entrata", "credito", "credit", "dare"}:
        return "entrata"
    if valore in {"uscita", "debito", "debit", "avere"}:
        return "uscita"
    try:
        return "entrata" if float(doc.get("importo") or 0) > 0 else "uscita"
    except (TypeError, ValueError):
        return ""


def _id_ec(doc: Dict[str, Any]) -> str:
    for campo in ("id", "movement_id", "transaction_id", "_id"):
        valore = doc.get(campo)
        if valore:
            return str(valore)
    return ""


def classifica(movimento_ec: Dict[str, Any]) -> Optional[str]:
    """«versamento», «prelievo» o None. Il riconoscimento e' uno solo.

    Le funzioni stanno in `routers/bank/estratto_conto.py` perche' le usa
    anche la categorizzazione: qui si importano, non si riscrivono.
    """
    from app.routers.bank.estratto_conto import (
        is_prelievo_contanti,
        is_storno_versamento,
        is_versamento_contanti,
    )

    descrizione = str(
        movimento_ec.get("descrizione_originale")
        or movimento_ec.get("descrizione")
        or movimento_ec.get("description")
        or ""
    )
    if is_storno_versamento(descrizione):
        return None

    verso = _verso(movimento_ec)
    # Il segno deve concordare con la causale: un «versamento» in uscita non
    # e' un versamento, e trattarlo come tale ribalterebbe il movimento.
    if is_versamento_contanti(descrizione) and verso == "entrata":
        return "versamento"
    if is_prelievo_contanti(descrizione) and verso == "uscita":
        return "prelievo"
    return None


def _si_dichiara_trasferimento(riga: Dict[str, Any]) -> bool:
    """`True` se questa riga di Prima Nota dice di essere un trasferimento.

    Una riga che non lo dice non viene agganciata: si crea la gamba nuova.
    Meglio una gamba in piu' da verificare che un pagamento fornitore
    trasformato in versamento senza che nessuno se ne accorga.
    """
    categoria = str(riga.get("categoria") or "").strip().lower()
    if categoria in CATEGORIE_TRASFERIMENTO:
        return True
    testo = " ".join(
        str(riga.get(campo) or "")
        for campo in ("categoria", "descrizione", "description", "causale", "dettaglio")
    ).lower()
    return any(parola in testo for parola in PAROLE_TRASFERIMENTO)


async def _gamba_di_cassa_gia_scritta(
    db, *, data_banca: str, importo: float, tipo_cassa: str, giorni: int,
) -> Optional[Dict[str, Any]]:
    """La gamba di cassa gia' in archivio per questo versamento, se c'e'.

    Tre condizioni insieme, tutte obbligatorie: la riga **si dichiara**
    trasferimento (categoria o descrizione), ha l'importo esatto al centesimo,
    e cade nella finestra di giorni attorno alla data della banca. In piu'
    deve essere **libera**: una riga chiude un solo versamento.

    La dichiarazione e' la condizione che mancava. Senza, bastava l'importo
    uguale per prendersi una riga di tutt'altra natura — un pagamento
    fornitore in contanti — e sovrascriverne la categoria.
    """
    try:
        riferimento = datetime.strptime(data_banca, "%Y-%m-%d")
    except ValueError:
        return None

    finestra = {
        (riferimento + timedelta(days=scarto)).strftime("%Y-%m-%d")
        for scarto in range(-giorni, giorni + 1)
    }
    candidati = await db["prima_nota_cassa"].find(
        {
            "tipo": tipo_cassa,
            "status": {"$nin": ["deleted", "archived"]},
        },
        {"_id": 0},
    ).to_list(5000)

    for riga in candidati:
        if riga.get("trasferimento_collegato_id") or riga.get("operation_id"):
            continue
        if not _si_dichiara_trasferimento(riga):
            continue
        if _data_iso(riga) not in finestra:
            continue
        if abs(_importo(riga) - importo) > 0.005:
            continue
        return riga
    return None


async def riconosci_versamenti(
    db, *, anno: Optional[int] = None, dry_run: bool = True,
    giorni_tolleranza: int = GIORNI_TOLLERANZA,
) -> Dict[str, Any]:
    """Scrive le due gambe per ogni versamento o prelievo dell'estratto conto.

    `dry_run` per difetto: dice cosa farebbe senza scrivere. Rieseguirlo non
    duplica mai, perche' ogni gamba porta l'id della riga di estratto conto.
    """
    from app.database import Collections

    movimenti = await db[Collections.BANK_STATEMENTS].find({}, {"_id": 0}).to_list(50000)

    esiti: List[Dict[str, Any]] = []
    conteggi = {
        "esaminati": 0, "versamenti": 0, "prelievi": 0,
        "gambe_cassa_create": 0, "gambe_cassa_collegate": 0,
        "gia_registrati": 0, "senza_data_o_importo": 0,
    }

    for movimento_ec in movimenti:
        tipo = classifica(movimento_ec)
        if not tipo:
            continue
        conteggi["esaminati"] += 1

        data = _data_iso(movimento_ec)
        importo = _importo(movimento_ec)
        ec_id = _id_ec(movimento_ec)
        if not data or importo <= 0 or not ec_id:
            # Senza una delle tre non c'e' prova: si segnala, non si indovina.
            conteggi["senza_data_o_importo"] += 1
            esiti.append({"ec_id": ec_id, "tipo": tipo, "esito": "dati_insufficienti",
                          "data": data, "importo": importo})
            continue
        if anno and not data.startswith(f"{anno}-"):
            continue

        conteggi["versamenti" if tipo == "versamento" else "prelievi"] += 1
        operazione = f"{tipo}:{ec_id}"
        descrizione = str(movimento_ec.get("descrizione_originale")
                          or movimento_ec.get("descrizione") or "")

        # Chi esce e chi entra, secondo il verso del contante.
        if tipo == "versamento":
            tipo_cassa, tipo_banca = "uscita", "entrata"
        else:
            tipo_cassa, tipo_banca = "entrata", "uscita"

        comune = {
            "data": data,
            "importo": importo,
            "categoria": CATEGORIA,
            "descrizione": descrizione or f"{tipo.capitalize()} contanti",
            "operation_id": operazione,
            "movimento_ec_id": ec_id,
            "source": f"estratto_conto_{tipo}",
        }

        cassa_esistente = await _gamba_di_cassa_gia_scritta(
            db, data_banca=data, importo=importo, tipo_cassa=tipo_cassa,
            giorni=giorni_tolleranza,
        )

        if dry_run:
            esiti.append({
                "ec_id": ec_id, "tipo": tipo, "data": data, "importo": importo,
                "esito": "collegherebbe" if cassa_esistente else "creerebbe",
                "cassa_esistente_id": (cassa_esistente or {}).get("id", ""),
            })
            conteggi["gambe_cassa_collegate" if cassa_esistente else "gambe_cassa_create"] += 1
            continue

        # La gamba bancaria: la riga di estratto conto E' la prova.
        id_banca, banca_gia_presente = await scrivi_movimento_se_assente(
            db, "banca", {"operation_id": operazione},
            {**comune, "tipo": tipo_banca},
        )

        if cassa_esistente:
            # C'era gia': si collega, non si riscrive. E' il caso che il
            # vecchio comando sbagliava, facendo uscire il contante due volte.
            id_cassa = cassa_esistente["id"]
            await db["prima_nota_cassa"].update_one(
                {"id": id_cassa},
                {"$set": {
                    "operation_id": operazione,
                    "movimento_ec_id": ec_id,
                    "trasferimento_collegato_id": id_banca,
                    "categoria": CATEGORIA,
                }},
            )
            conteggi["gambe_cassa_collegate"] += 1
            esito = "collegata"
        else:
            id_cassa, cassa_gia_presente = await scrivi_movimento_se_assente(
                db, "cassa", {"operation_id": operazione},
                {**comune, "tipo": tipo_cassa, "trasferimento_collegato_id": id_banca},
            )
            if cassa_gia_presente and banca_gia_presente:
                conteggi["gia_registrati"] += 1
                esito = "gia_registrato"
            else:
                conteggi["gambe_cassa_create"] += 1
                esito = "creata"

        await db["prima_nota_banca"].update_one(
            {"id": id_banca}, {"$set": {"trasferimento_collegato_id": id_cassa}},
        )
        esiti.append({"ec_id": ec_id, "tipo": tipo, "data": data, "importo": importo,
                      "esito": esito, "id_cassa": id_cassa, "id_banca": id_banca})

    return {
        "dry_run": dry_run,
        "anno": anno,
        "giorni_tolleranza": giorni_tolleranza,
        **conteggi,
        "movimenti": esiti[:500],
        "eseguito_il": datetime.now(timezone.utc).isoformat(),
    }
