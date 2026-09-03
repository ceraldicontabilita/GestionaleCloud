import logging

"""
Router per la gestione delle Anomalie e Non Conformità.
Registra attrezzature in disuso, malfunzionamenti, problemi.

RIFERIMENTI NORMATIVI:
- Reg. CE 852/2004 - Igiene dei prodotti alimentari
- Reg. CE 178/2002 - Principi generali sicurezza alimentare
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime, timezone, date, timedelta
from typing import List
import re
import uuid

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/anomalie", tags=["Anomalie"])

# MongoDB connection
# ==================== COSTANTI ====================

TIPI_ANOMALIA = [
    "Attrezzatura in disuso",
    "Malfunzionamento",
    "Guasto",
    "Manutenzione programmata",
    "Pulizia straordinaria",
    "Sostituzione",
    "Altro",
]

STATI_ANOMALIA = ["Aperta", "In corso", "Risolta", "Chiusa"]

CATEGORIE_ATTREZZATURA = [
    "Frigorifero",
    "Congelatore",
    "Tavolo di lavoro",
    "Forno",
    "Piano cottura",
    "Lavastoviglie",
    "Affettatrice",
    "Impastatrice",
    "Friggitrice",
    "Abbattitore",
    "Vetrina refrigerata",
    "Scaffalatura",
    "Altro",
]

# ==================== MODELLI ====================


class Anomalia(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    data_segnalazione: str  # DD/MM/YYYY
    attrezzatura: str
    categoria: str
    tipo: str
    descrizione: str
    stato: str = "Aperta"
    operatore_segnalazione: str = ""
    azione_correttiva: str = ""
    esito_verifica: str = ""
    data_verifica: str = ""
    data_risoluzione: str = ""
    operatore_risoluzione: str = ""
    operatore_presa_in_carico: str = ""
    data_presa_in_carico: str = ""
    note: str = ""
    priorita: str = "Media"  # Alta, Media, Bassa
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class NuovaAnomaliaRequest(BaseModel):
    attrezzatura: str
    categoria: str
    tipo: str
    descrizione: str
    operatore_segnalazione: str = ""
    priorita: str = "Media"
    note: str = ""


class AggiornaAnomaliaRequest(BaseModel):
    stato: str = None
    azione_correttiva: str = None
    esito_verifica: str = None
    operatore_risoluzione: str = None
    operatore_presa_in_carico: str = None
    note: str = None


# ==================== ENDPOINTS ====================


@router.get("/lista")
async def get_anomalie(anno: int = None, stato: str = None, categoria: str = None):
    """Ottiene la lista delle anomalie con filtri opzionali"""
    query = {}

    if anno:
        query["data_segnalazione"] = {"$regex": f"^{anno}"}

    if stato:
        query["stato"] = stato

    if categoria:
        query["categoria"] = categoria

    anomalie = await db.anomalie.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    return anomalie


@router.get("/tipi")
async def get_tipi_anomalia():
    """Lista tipi di anomalia"""
    return TIPI_ANOMALIA


@router.get("/stati")
async def get_stati_anomalia():
    """Lista stati anomalia"""
    return STATI_ANOMALIA


@router.get("/categorie")
async def get_categorie_attrezzatura():
    """Lista categorie attrezzatura"""
    return CATEGORIE_ATTREZZATURA


@router.get("/statistiche")
async def get_statistiche(anno: int = None):
    """Statistiche anomalie"""
    query = {}
    if anno:
        query["data_segnalazione"] = {"$regex": f"^{anno}"}

    anomalie = await db.anomalie.find(query, {"_id": 0}).to_list(1000)

    # Conta per stato
    per_stato = {}
    for a in anomalie:
        stato = a.get("stato", "Sconosciuto")
        per_stato[stato] = per_stato.get(stato, 0) + 1

    # Conta per categoria
    per_categoria = {}
    for a in anomalie:
        cat = a.get("categoria", "Altro")
        per_categoria[cat] = per_categoria.get(cat, 0) + 1

    # Conta per priorità
    per_priorita = {}
    for a in anomalie:
        prio = a.get("priorita", "Media")
        per_priorita[prio] = per_priorita.get(prio, 0) + 1

    return {
        "totale": len(anomalie),
        "per_stato": per_stato,
        "per_categoria": per_categoria,
        "per_priorita": per_priorita,
        "aperte": per_stato.get("Aperta", 0) + per_stato.get("In corso", 0),
        "risolte": per_stato.get("Risolta", 0) + per_stato.get("Chiusa", 0),
    }


@router.get("/{anomalia_id}")
async def get_anomalia(anomalia_id: str):
    """Ottiene una singola anomalia"""
    anomalia = await db.anomalie.find_one({"id": anomalia_id}, {"_id": 0})
    if not anomalia:
        raise HTTPException(status_code=404, detail="Anomalia non trovata")
    return anomalia


@router.post("/registra")
@router.post("/")
async def registra_anomalia(data: NuovaAnomaliaRequest):
    """Registra una nuova anomalia"""
    oggi = date.today()

    nuova_anomalia = {
        "id": str(uuid.uuid4()),
        "data_segnalazione": oggi.strftime("%Y-%m-%d"),
        "attrezzatura": data.attrezzatura,
        "categoria": data.categoria,
        "tipo": data.tipo,
        "descrizione": data.descrizione,
        "stato": "Aperta",
        "operatore_segnalazione": data.operatore_segnalazione,
        "azione_correttiva": "",
        "data_risoluzione": "",
        "operatore_risoluzione": "",
        "note": data.note,
        "priorita": data.priorita,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    await db.anomalie.insert_one(nuova_anomalia)

    # Rimuovi _id per la risposta
    if "_id" in nuova_anomalia:
        del nuova_anomalia["_id"]

    # ── Hook: se anomalia riguarda frigo/congelatore → trova lotti presenti ──
    try:
        cat = (data.categoria or "").lower()
        attr = (data.attrezzatura or "").lower()
        is_temperatura = (
            "frigo" in cat
            or "congelator" in cat
            or "frigo" in attr
            or "congelator" in attr
            or "temperatura" in (data.tipo or "").lower()
        )
        if is_temperatura:
            lotti_coinvolti = await db.lotti.find(
                {
                    "frigo_numero": {"$regex": data.attrezzatura[:6], "$options": "i"},
                    "consumato": {"$ne": True},
                    "esaurito": {"$ne": True},
                    "stato": {"$nin": ["smaltito", "esaurito"]},
                },
                {
                    "_id": 0,
                    "id": 1,
                    "prodotto": 1,
                    "numero_lotto": 1,
                    "data_scadenza": 1,
                    "quantita": 1,
                    "unita_misura": 1,
                },
            ).to_list(50)

            if lotti_coinvolti:
                await db.anomalie.update_one(
                    {"id": nuova_anomalia["id"]},
                    {
                        "$set": {
                            "lotti_coinvolti": lotti_coinvolti,
                            "lotti_a_rischio": len(lotti_coinvolti),
                            "nota_tracciabilita": (
                                f"Rilevati {len(lotti_coinvolti)} lotti nel {data.attrezzatura} "
                                f"al momento dell'anomalia. Verificare integrità prodotti."
                            ),
                        }
                    },
                )
                nuova_anomalia["lotti_coinvolti"] = lotti_coinvolti
                nuova_anomalia["lotti_a_rischio"] = len(lotti_coinvolti)
    except Exception:
        logger.debug("[anomalie] errore non bloccante ignorato")

    # ── Hook: aggiorna Manuale HACCP dinamico ───────────────────────────────
    try:
        import asyncio
        from app.lotti.routers.haccp_manuale_auto import aggiorna_sezioni_manuale

        asyncio.create_task(aggiorna_sezioni_manuale())
    except Exception:
        logger.debug("[anomalie] errore non bloccante ignorato")

    return {"success": True, "anomalia": nuova_anomalia}


@router.get("/{anomalia_id}/lotti-attuali")
async def lotti_attuali_anomalia(anomalia_id: str):
    """Ricalcola IN TEMPO REALE i lotti attualmente nell'attrezzatura
    dell'anomalia (Tranche 2 — Intelligenza operativa frigoriferi). Diverso
    da `lotti_coinvolti` (snapshot salvato al momento della segnalazione):
    tra la segnalazione e l'intervento i lotti potrebbero già essere stati
    spostati/consumati, quindi qui si riparte da una query live."""
    anomalia = await db.anomalie.find_one({"id": anomalia_id}, {"_id": 0})
    if not anomalia:
        raise HTTPException(status_code=404, detail="Anomalia non trovata")
    attrezzatura = (anomalia.get("attrezzatura") or "").strip()
    if not attrezzatura:
        return {"anomalia_id": anomalia_id, "attrezzatura": "", "totale": 0, "lotti": []}

    # Match ESATTO (case-insensitive) sul nome intero: un prefisso troncato
    # (com'è il caso della snapshot `lotti_coinvolti` alla creazione, che usa
    # solo i primi 6 caratteri) farebbe confondere es. "Frigorifero N°2" con
    # "Frigorifero N°9" — qui la query deve restare corretta perché è quella
    # su cui si basa lo spostamento massivo vero e proprio.
    from app.lotti.routers.utils import FILTRO_LOTTO_APERTO
    items = await db.lotti.find(
        {
            "frigo_numero": {"$regex": f"^{re.escape(attrezzatura)}$", "$options": "i"},
            **FILTRO_LOTTO_APERTO,
        },
        {"_id": 0},
    ).to_list(200)
    from app.lotti.servizi.lotto_arricchimento_service import arricchisci_lotto
    lotti = [arricchisci_lotto(dict(it)) for it in items if (it.get("quantita") or 0) > 0]
    return {"anomalia_id": anomalia_id, "attrezzatura": attrezzatura, "totale": len(lotti), "lotti": lotti}


class SpostaLottiMassivoRequest(BaseModel):
    lotti_ids: List[str]
    tipo: str  # frigo|congelatore|abbattitore|banco|magazzino
    numero: str = ""
    nome: str = ""
    reparto: str = ""
    motivo: str = ""
    azione_correttiva_haccp: str = ""
    operatore_id: str = ""
    operatore_nome: str = ""


@router.post("/{anomalia_id}/sposta-lotti-massivo")
async def sposta_lotti_massivo(anomalia_id: str, body: SpostaLottiMassivoRequest):
    """Sposta in blocco i lotti presenti in un'attrezzatura in anomalia verso
    una nuova posizione, registrando per ciascuno il movimento con
    riferimento all'anomalia (Reg. CE 852/2004 — tracciabilità dell'azione
    correttiva). Riusa lo stesso registro movimenti/posizione di Tranche 0-1,
    un lotto alla volta, così ogni spostamento resta un evento indipendente
    in cronologia (non un'unica riga aggregata che nasconderebbe i dettagli
    per singolo lotto)."""
    anomalia = await db.anomalie.find_one({"id": anomalia_id}, {"_id": 0})
    if not anomalia:
        raise HTTPException(status_code=404, detail="Anomalia non trovata")
    if not body.lotti_ids:
        raise HTTPException(status_code=400, detail="Nessun lotto selezionato")

    from app.lotti.servizi.movimenti_lotto_service import costruisci_posizione, registra_movimento

    spostati = []
    for lotto_id in body.lotti_ids:
        lotto = await db.lotti.find_one({"id": lotto_id}, {"_id": 0})
        if not lotto:
            continue
        posizione_da = lotto.get("posizione")
        posizione_a = costruisci_posizione(
            tipo=body.tipo, numero=body.numero or body.nome, nome=body.nome or body.numero,
            reparto=body.reparto, operatore_id=body.operatore_id, operatore_nome=body.operatore_nome,
            quantita=lotto.get("quantita"),
        )
        if posizione_a is None:
            raise HTTPException(status_code=400, detail="Tipo o numero posizione di destinazione mancante")

        update = {"posizione": posizione_a}
        update["frigo_numero"] = posizione_a["numero"] if posizione_a["tipo"] in ("frigo", "congelatore", "abbattitore") else ""
        await db.lotti.update_one({"id": lotto_id}, {"$set": update})

        try:
            await registra_movimento(
                lotto_id, "spostamento_massivo_anomalia",
                numero_lotto=lotto.get("numero_lotto", ""),
                posizione_da=posizione_da, posizione_a=posizione_a,
                quantita=lotto.get("quantita"),
                operatore_id=body.operatore_id, operatore_nome=body.operatore_nome,
                motivo=body.motivo or f"Spostamento massivo da anomalia su {anomalia.get('attrezzatura', '')}",
                azione_correttiva_haccp=body.azione_correttiva_haccp or None,
                documento_collegato={"tipo": "anomalia", "id": anomalia_id},
            )
        except Exception:
            logger.exception("[anomalie] registrazione movimento spostamento massivo fallita (non bloccante)")
        spostati.append(lotto_id)

    await db.anomalie.update_one(
        {"id": anomalia_id},
        {"$push": {"spostamenti_massivi": {
            "data_ora": datetime.now(timezone.utc).isoformat(),
            "lotti_spostati": spostati,
            "posizione_destinazione": {"tipo": body.tipo, "numero": body.numero or body.nome, "reparto": body.reparto},
            "operatore_nome": body.operatore_nome,
            "motivo": body.motivo,
            "azione_correttiva_haccp": body.azione_correttiva_haccp,
        }}},
    )
    return {"status": "ok", "spostati": len(spostati), "lotti_ids": spostati}


@router.put("/{anomalia_id}")
async def aggiorna_anomalia(
    anomalia_id: str, data: AggiornaAnomaliaRequest, request: Request
):
    """Aggiorna un'anomalia e conserva la prova dell'intervento.

    Un'anomalia non puo' essere chiusa con il solo cambio di stato: servono
    azione correttiva, verifica finale e identita' dell'operatore. Quando il
    token e' presente il nome firmato nel JWT prevale su quello inviato dal
    browser, impedendo di attribuire l'intervento a un'altra persona.
    """
    anomalia = await db.anomalie.find_one({"id": anomalia_id})
    if not anomalia:
        raise HTTPException(status_code=404, detail="Anomalia non trovata")

    adesso = datetime.now(timezone.utc)
    aggiornamenti = {"updated_at": adesso.isoformat()}
    utente = getattr(getattr(request, "state", None), "user", None) or {}
    nome_token = str(utente.get("nome") or "").strip()
    stato_nuovo = (data.stato or "").strip()
    if stato_nuovo and stato_nuovo not in STATI_ANOMALIA:
        raise HTTPException(status_code=400, detail="Stato anomalia non valido")

    azione = (
        str(data.azione_correttiva).strip()
        if data.azione_correttiva is not None
        else str(anomalia.get("azione_correttiva") or "").strip()
    )
    esito = (
        str(data.esito_verifica).strip()
        if data.esito_verifica is not None
        else str(anomalia.get("esito_verifica") or "").strip()
    )
    operatore = nome_token or str(data.operatore_risoluzione or "").strip()

    if stato_nuovo in ("Risolta", "Chiusa"):
        mancanti = []
        if not azione:
            mancanti.append("azione correttiva")
        if not esito:
            mancanti.append("verifica finale")
        if not operatore:
            mancanti.append("operatore")
        if mancanti:
            raise HTTPException(
                status_code=400,
                detail="Per chiudere l'anomalia indica: " + ", ".join(mancanti),
            )

    if stato_nuovo:
        aggiornamenti["stato"] = stato_nuovo
        if stato_nuovo == "In corso":
            aggiornamenti["operatore_presa_in_carico"] = (
                nome_token or str(data.operatore_presa_in_carico or "").strip()
            )
            aggiornamenti["data_presa_in_carico"] = adesso.isoformat()
        if stato_nuovo in ["Risolta", "Chiusa"]:
            aggiornamenti["data_risoluzione"] = date.today().strftime("%d/%m/%Y")
            aggiornamenti["data_verifica"] = adesso.isoformat()
            aggiornamenti["operatore_risoluzione"] = operatore

    if data.azione_correttiva is not None:
        aggiornamenti["azione_correttiva"] = azione

    if data.esito_verifica is not None:
        aggiornamenti["esito_verifica"] = esito

    if data.note is not None:
        aggiornamenti["note"] = data.note

    await db.anomalie.update_one({"id": anomalia_id}, {"$set": aggiornamenti})

    # Registro append-only: consente di ricostruire chi ha fatto cosa e quando,
    # anche se la card viene modificata di nuovo in seguito.
    await db.anomalie_eventi.insert_one({
        "id": str(uuid.uuid4()),
        "anomalia_id": anomalia_id,
        "evento": (
            "risoluzione" if stato_nuovo in ("Risolta", "Chiusa")
            else "presa_in_carico" if stato_nuovo == "In corso"
            else "aggiornamento"
        ),
        "stato_precedente": anomalia.get("stato", ""),
        "stato_nuovo": stato_nuovo or anomalia.get("stato", ""),
        "azione_correttiva": azione if data.azione_correttiva is not None else "",
        "esito_verifica": esito if data.esito_verifica is not None else "",
        "operatore": operatore or nome_token,
        "timestamp": adesso.isoformat(),
    })

    aggiornata = await db.anomalie.find_one({"id": anomalia_id}, {"_id": 0})
    return {"success": True, "message": "Anomalia aggiornata", "anomalia": aggiornata}


@router.delete("/{anomalia_id}")
async def elimina_anomalia(anomalia_id: str):
    """Elimina un'anomalia"""
    result = await db.anomalie.delete_one({"id": anomalia_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Anomalia non trovata")
    return {"success": True, "message": "Anomalia eliminata"}


@router.post("/genera-storico")
async def genera_storico(start_anno: int = 2022, end_anno: int = 2025):
    """Genera anomalie storiche di esempio per testing"""
    import random

    # Prima elimina anomalie esistenti nel range
    await db.anomalie.delete_many(
        {
            "data_segnalazione": {
                "$regex": f"/({start_anno}|{start_anno+1}|{start_anno+2}|{start_anno+3})$"
            }
        }
    )

    anomalie_generate = 0

    # Descrizioni dettagliate per ogni tipo di anomalia
    DESCRIZIONI_DETTAGLIATE = {
        "Attrezzatura in disuso": [
            "Guarnizione porta danneggiata - non mantiene temperatura",
            "Motore compressore rumoroso - necessita sostituzione",
            "Display temperatura non funzionante",
            "Sbrinamento automatico bloccato",
            "Perdita di gas refrigerante rilevata",
        ],
        "Malfunzionamento": [
            "Temperatura non stabile - oscilla di ±3°C",
            "Ventola interna bloccata - accumulo ghiaccio",
            "Termostato non risponde ai comandi",
            "Spia allarme accesa costantemente",
            "Rumore anomalo dal compressore",
        ],
        "Guasto": [
            "Compressore non si avvia",
            "Cortocircuito impianto elettrico",
            "Rottura serpentina evaporatore",
            "Guasto scheda elettronica",
            "Blocco totale sistema refrigerante",
        ],
        "Manutenzione programmata": [
            "Sostituzione filtri prevista da piano manutenzione",
            "Pulizia condensatore programmata",
            "Controllo livello gas refrigerante",
            "Verifica tenuta guarnizioni",
            "Taratura termostato annuale",
        ],
    }

    AZIONI_CORRETTIVE = {
        "Attrezzatura in disuso": [
            "Sostituita guarnizione porta - ripristinata tenuta",
            "Sostituito compressore con ricambio originale",
            "Installato nuovo display digitale",
            "Riparato sistema sbrinamento - test OK",
            "Ricarica gas R134a + verifica perdite",
        ],
        "Malfunzionamento": [
            "Regolato termostato - temperatura ora stabile",
            "Sbloccata ventola + rimosso ghiaccio accumulato",
            "Sostituito termostato - risponde correttamente",
            "Reset sistema allarme - verificato funzionamento",
            "Lubrificato compressore - rumore eliminato",
        ],
        "Guasto": [
            "Sostituito compressore - apparecchio funzionante",
            "Riparato impianto elettrico da tecnico autorizzato",
            "Sostituita serpentina - sistema refrigerante OK",
            "Installata nuova scheda elettronica",
            "Ripristinato circuito refrigerante completo",
        ],
        "Manutenzione programmata": [
            "Sostituiti filtri aria come da programma",
            "Pulizia condensatore eseguita - efficienza ripristinata",
            "Livello gas verificato - nella norma",
            "Guarnizioni verificate - tenuta ottimale",
            "Termostato tarato - precisione ±0.5°C",
        ],
    }

    for anno in range(start_anno, end_anno + 1):
        # NOTE: random usato per generazione dati demo HACCP con seed fisso (riproducibilità). NON usato per operazioni di sicurezza.
        random.seed(anno * 7777)  # Seed fisso per consistenza

        # 3-5 anomalie all'anno
        num_anomalie = random.randint(3, 5)

        for _ in range(num_anomalie):
            mese = random.randint(1, 12)
            giorno = random.randint(1, 28)

            # Solo date passate
            data_segnalazione = date(anno, mese, giorno)
            if data_segnalazione > date.today():
                continue

            categoria = random.choice(CATEGORIE_ATTREZZATURA)

            # Determina attrezzatura basata su categoria
            if categoria == "Frigorifero":
                attrezzatura = f"Frigorifero N°{random.randint(1, 12)}"
            elif categoria == "Congelatore":
                attrezzatura = f"Congelatore N°{random.randint(1, 12)}"
            elif categoria == "Tavolo di lavoro":
                attrezzatura = (
                    f"Tavolo lavoro {random.choice(['cucina', 'laboratorio', 'preparazione'])}"
                )
            else:
                attrezzatura = f"{categoria} principale"

            tipo = random.choice(TIPI_ANOMALIA[:4])  # Solo i primi 4 tipi più comuni

            # Descrizione dettagliata in base al tipo
            descrizione = random.choice(
                DESCRIZIONI_DETTAGLIATE.get(
                    tipo,
                    [
                        "Anomalia rilevata durante controllo periodico",
                        "Segnalazione operatore - verifica necessaria",
                    ],
                )
            )

            # 90% risolte per dati storici
            stato = "Risolta" if random.random() < 0.9 else "Aperta"

            # Data risoluzione: MASSIMO 2 giorni dopo la segnalazione
            data_risoluzione_str = ""
            azione_correttiva = ""
            if stato == "Risolta":
                giorni_risoluzione = random.randint(0, 2)  # 0, 1 o 2 giorni
                data_risoluzione_obj = data_segnalazione + timedelta(days=giorni_risoluzione)
                # Non superare la data odierna
                if data_risoluzione_obj > date.today():
                    data_risoluzione_obj = date.today()
                data_risoluzione_str = data_risoluzione_obj.strftime("%d/%m/%Y")

                # Azione correttiva dettagliata
                azione_correttiva = random.choice(
                    AZIONI_CORRETTIVE.get(
                        tipo,
                        [
                            "Intervento tecnico completato con successo",
                            "Problema risolto - attrezzatura ripristinata",
                        ],
                    )
                )

            nuova_anomalia = {
                "id": str(uuid.uuid4()),
                "data_segnalazione": f"{giorno:02d}/{mese:02d}/{anno}",
                "attrezzatura": attrezzatura,
                "categoria": categoria,
                "tipo": tipo,
                "descrizione": descrizione,
                "stato": stato,
                "operatore_segnalazione": random.choice(["Pocci Salvatore", "Vincenzo Ceraldi"]),
                "azione_correttiva": azione_correttiva,
                "data_risoluzione": data_risoluzione_str,
                "operatore_risoluzione": (
                    random.choice(["Pocci Salvatore", "Vincenzo Ceraldi"])
                    if stato == "Risolta"
                    else ""
                ),
                "note": "",
                "priorita": random.choice(["Alta", "Media", "Bassa"]),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

            await db.anomalie.insert_one(nuova_anomalia)
            anomalie_generate += 1

    return {
        "success": True,
        "message": f"Generate {anomalie_generate} anomalie storiche",
        "anni": list(range(start_anno, end_anno + 1)),
    }


# ==================== REPORT PDF ANOMALIE ====================

from fastapi.responses import HTMLResponse

from app.lotti.db import database as db


@router.get("/report-pdf/{anno}", response_class=HTMLResponse)
async def genera_report_pdf_anomalie(anno: int):
    """
    Genera un report PDF/HTML delle anomalie per un anno specifico.
    Utilizzabile per ispezioni ASL e documentazione HACCP.
    """

    # Recupera tutte le anomalie dell'anno. NIENTE regex sul formato:
    # data_segnalazione è a formato misto (ISO "2026-.." e dd/mm/yyyy). La
    # vecchia regex "^{anno}" prendeva solo le ISO → le anomalie scritte
    # dd/mm/yyyy sparivano dal report ASL annuale. Si filtra sull'anno reale.
    from app.lotti.routers.utils import parse_data_flessibile
    tutte = await db.anomalie.find({}, {"_id": 0}).to_list(20000)
    anomalie = [
        a for a in tutte
        if (parse_data_flessibile(a.get("data_segnalazione")) or date(1900, 1, 1)).year == anno
    ]

    # Statistiche
    totale = len(anomalie)
    risolte = sum(1 for a in anomalie if a.get("stato") == "Risolta")
    aperte = sum(1 for a in anomalie if a.get("stato") in ["Aperta", "In corso"])

    # Raggruppa per categoria
    per_categoria = {}
    for a in anomalie:
        cat = a.get("categoria", "Altro")
        if cat not in per_categoria:
            per_categoria[cat] = []
        per_categoria[cat].append(a)

    # Genera HTML
    html = f"""
    <!DOCTYPE html>
    <html lang="it">
    <head>
        <meta charset="UTF-8">
        <title>Report Anomalie HACCP - {anno}</title>
        <style>
            @page {{ size: A4; margin: 15mm; }}
            body {{ font-family: Arial, sans-serif; font-size: 11pt; line-height: 1.4; color: #333; }}
            .header {{ text-align: center; border-bottom: 3px solid #d32f2f; padding-bottom: 15px; margin-bottom: 20px; }}
            .header h1 {{ color: #d32f2f; margin: 0; font-size: 18pt; }}
            .header p {{ margin: 5px 0; color: #666; }}
            .stats {{ display: flex; justify-content: space-around; margin: 20px 0; padding: 15px; background: #f5f5f5; border-radius: 8px; }}
            .stat {{ text-align: center; }}
            .stat-value {{ font-size: 24pt; font-weight: bold; }}
            .stat-label {{ font-size: 10pt; color: #666; }}
            .stat-risolte .stat-value {{ color: #388e3c; }}
            .stat-aperte .stat-value {{ color: #d32f2f; }}
            .categoria {{ margin: 20px 0; page-break-inside: avoid; }}
            .categoria h2 {{ background: #1976d2; color: white; padding: 8px 15px; margin: 0; font-size: 12pt; border-radius: 4px 4px 0 0; }}
            table {{ width: 100%; border-collapse: collapse; margin: 0; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; font-size: 9pt; }}
            th {{ background: #e3f2fd; font-weight: bold; }}
            .stato-risolta {{ background: #e8f5e9; color: #2e7d32; font-weight: bold; }}
            .stato-aperta {{ background: #ffebee; color: #c62828; font-weight: bold; }}
            .stato-incorso {{ background: #fff3e0; color: #ef6c00; font-weight: bold; }}
            .priorita-alta {{ color: #d32f2f; font-weight: bold; }}
            .priorita-media {{ color: #f57c00; }}
            .priorita-bassa {{ color: #388e3c; }}
            .descrizione {{ font-size: 8pt; color: #666; max-width: 200px; }}
            .azione {{ font-size: 8pt; color: #1976d2; max-width: 200px; font-style: italic; }}
            .footer {{ margin-top: 30px; text-align: center; font-size: 9pt; color: #999; border-top: 1px solid #ddd; padding-top: 15px; }}
            .firma {{ margin-top: 40px; display: flex; justify-content: space-between; }}
            .firma-box {{ width: 45%; text-align: center; }}
            .firma-linea {{ border-top: 1px solid #333; margin-top: 40px; padding-top: 5px; }}
            @media print {{ .no-print {{ display: none; }} }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🔧 REGISTRO ANOMALIE E NON CONFORMITÀ</h1>
            <p><strong>Ceraldi Group S.R.L.</strong> - Piazza Carità 14, 80134 Napoli (NA)</p>
            <p>Anno di riferimento: <strong>{anno}</strong> | Generato il: {datetime.now().strftime('%d/%m/%Y alle %H:%M')}</p>
        </div>
        
        <div class="stats">
            <div class="stat">
                <div class="stat-value">{totale}</div>
                <div class="stat-label">TOTALE ANOMALIE</div>
            </div>
            <div class="stat stat-risolte">
                <div class="stat-value">{risolte}</div>
                <div class="stat-label">RISOLTE</div>
            </div>
            <div class="stat stat-aperte">
                <div class="stat-value">{aperte}</div>
                <div class="stat-label">APERTE/IN CORSO</div>
            </div>
            <div class="stat">
                <div class="stat-value">{round(risolte/totale*100) if totale > 0 else 0}%</div>
                <div class="stat-label">TASSO RISOLUZIONE</div>
            </div>
        </div>
    """

    # Tabella per ogni categoria
    for categoria, anomalie_cat in sorted(per_categoria.items()):
        html += f"""
        <div class="categoria">
            <h2>📦 {categoria} ({len(anomalie_cat)} anomalie)</h2>
            <table>
                <tr>
                    <th width="8%">Data</th>
                    <th width="15%">Attrezzatura</th>
                    <th width="10%">Tipo</th>
                    <th width="20%">Descrizione</th>
                    <th width="7%">Priorità</th>
                    <th width="8%">Stato</th>
                    <th width="8%">Risoluz.</th>
                    <th width="20%">Azione Correttiva</th>
                </tr>
        """

        for a in sorted(anomalie_cat, key=lambda x: x.get("data_segnalazione", ""), reverse=True):
            stato = a.get("stato", "")
            stato_class = (
                "stato-risolta"
                if stato == "Risolta"
                else ("stato-aperta" if stato == "Aperta" else "stato-incorso")
            )

            priorita = a.get("priorita", "Media")
            priorita_class = f"priorita-{priorita.lower()}"

            html += f"""
                <tr>
                    <td>{a.get('data_segnalazione', '')}</td>
                    <td>{a.get('attrezzatura', '')}</td>
                    <td>{a.get('tipo', '')}</td>
                    <td class="descrizione">{a.get('descrizione', '')}</td>
                    <td class="{priorita_class}">{priorita}</td>
                    <td class="{stato_class}">{stato}</td>
                    <td>{a.get('data_risoluzione', '-')}</td>
                    <td class="azione">{a.get('azione_correttiva', '-')}</td>
                </tr>
            """

        html += """
            </table>
        </div>
        """

    # Footer con firme
    html += f"""
        <div class="firma">
            <div class="firma-box">
                <div class="firma-linea">Responsabile HACCP</div>
            </div>
            <div class="firma-box">
                <div class="firma-linea">Data e Timbro</div>
            </div>
        </div>
        
        <div class="footer">
            <p>Documento generato automaticamente dal Sistema HACCP - Ceraldi Group S.R.L.</p>
            <p>Conforme a Reg. CE 852/2004 e Reg. CE 178/2002</p>
        </div>
        
        <div class="no-print" style="margin-top:20px; text-align:center;">
            <button onclick="window.print()" style="padding:10px 30px; font-size:14pt; background:#1976d2; color:white; border:none; border-radius:5px; cursor:pointer;">
                🖨️ Stampa Report
            </button>
        </div>
    </body>
    </html>
    """

    return HTMLResponse(content=html)


@router.get("/report-pdf-range", response_class=HTMLResponse)
async def genera_report_pdf_range(start_anno: int, end_anno: int):
    """Genera report anomalie per un range di anni"""

    # Filtro sull'anno reale, non su regex di formato: la vecchia "/({anni})$"
    # prendeva solo le date dd/mm/yyyy → le anomalie ISO sparivano dal report.
    from app.lotti.routers.utils import parse_data_flessibile
    tutte = await db.anomalie.find({}, {"_id": 0}).to_list(20000)
    anomalie = [
        a for a in tutte
        if start_anno <= (parse_data_flessibile(a.get("data_segnalazione")) or date(1900, 1, 1)).year <= end_anno
    ]

    totale = len(anomalie)
    risolte = sum(1 for a in anomalie if a.get("stato") == "Risolta")

    html = f"""
    <!DOCTYPE html>
    <html lang="it">
    <head>
        <meta charset="UTF-8">
        <title>Report Anomalie {start_anno}-{end_anno}</title>
        <style>
            body {{ font-family: Arial, sans-serif; font-size: 11pt; padding: 20px; }}
            .header {{ text-align: center; margin-bottom: 20px; }}
            h1 {{ color: #d32f2f; }}
            table {{ width: 100%; border-collapse: collapse; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; font-size: 9pt; }}
            th {{ background: #1976d2; color: white; }}
            .stato-risolta {{ background: #e8f5e9; }}
            .stato-aperta {{ background: #ffebee; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Report Anomalie {start_anno} - {end_anno}</h1>
            <p>Ceraldi Group S.R.L. | Totale: {totale} | Risolte: {risolte} ({round(risolte/totale*100) if totale > 0 else 0}%)</p>
        </div>
        <table>
            <tr>
                <th>Data</th>
                <th>Attrezzatura</th>
                <th>Tipo</th>
                <th>Descrizione</th>
                <th>Stato</th>
                <th>Risoluzione</th>
                <th>Azione Correttiva</th>
            </tr>
    """

    for a in sorted(anomalie, key=lambda x: x.get("data_segnalazione", ""), reverse=True):
        stato_class = "stato-risolta" if a.get("stato") == "Risolta" else "stato-aperta"
        html += f"""
            <tr class="{stato_class}">
                <td>{a.get('data_segnalazione', '')}</td>
                <td>{a.get('attrezzatura', '')}</td>
                <td>{a.get('tipo', '')}</td>
                <td>{a.get('descrizione', '')[:50]}...</td>
                <td>{a.get('stato', '')}</td>
                <td>{a.get('data_risoluzione', '-')}</td>
                <td>{a.get('azione_correttiva', '-')[:50]}...</td>
            </tr>
        """

    html += """
        </table>
        <div style="margin-top:20px; text-align:center;">
            <button onclick="window.print()">🖨️ Stampa</button>
        </div>
    </body>
    </html>
    """

    return HTMLResponse(content=html)
