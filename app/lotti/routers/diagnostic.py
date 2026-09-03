"""Endpoint diagnostico - lista collection e conteggi dal DB live"""

import os
import logging
_LOG_INIT = logging.getLogger("uvicorn.error")
from fastapi import APIRouter, Depends
from app.lotti.auth import require_admin
from app.lotti.db import database as db

router = APIRouter(prefix="/diagnostic", tags=["diagnostic"])


@router.get("/db-overview")
async def db_overview():
    coll_names = await db.list_collection_names()
    risultato = {}
    for c in sorted(coll_names):
        try:
            n = await db[c].count_documents({})
            sample = None
            if n > 0:
                doc = await db[c].find_one({}, {"_id": 0})
                if doc:
                    keys = list(doc.keys())[:15]
                    sample = {k: str(doc.get(k))[:60] for k in keys}
            risultato[c] = {"count": n, "sample_keys": sample}
        except Exception as e:
            risultato[c] = {"error": str(e)[:100]}
    return risultato


# Lista protetta: tutto ciò che il codice Lotti usa (estratta dal codice il
# 02/07/2026) + collezioni di sistema. Cintura contro errori del chiamante.
_COLLEZIONI_PROTETTE = {
        "ricette", "fornitori", "dizionario_prodotti", "fatture", "lotti",
        "prodotti_vendita", "lotti_fornitori", "ordini_fornitori",
        "magazzino_bar_prodotti", "nome_mapping", "listino_prodotti",
        "acquaviva_prodotti", "temperature_positive", "prodotti_master",
        "temperature_negative", "scheduler_logs", "tablet_operatori",
        "prodotti_canonici", "fornitori_qualifica", "vendite_banco",
        "sanificazione_schede", "anomalie", "fornitori_rivendita",
        "attrezzature_config", "schede_tecniche", "produzioni",
        "fornitori_anagrafica", "sconti_merce", "magazzino_bar_movimenti",
        "dizionario_ingredienti", "ricerca_web_tentativi", "gelati_invenduti",
        "controllo_olio", "temperature_cottura", "sistema_stato",
        "ricezioni_merce", "prodotti_alias", "colazione_template",
        "materie_prime", "import_jobs", "sanificazione", "ricette_libro",
        "corrispettivi", "task_dipendenti", "magazzino_overrides",
        "magazzino_bar_cat_merge", "disinfestazione_annuale",
        "catalogo_forno_prodotti", "sanificazione_apparecchi",
        "reclami_fornitori", "prodotti_da_classificare",
        "magazzino_bar_richieste", "anomalie_registro", "sync_status",
        "saima_ricettari", "pipeline_logs", "mappature_ingredienti",
        "log_scraping", "log_eventi", "log_attivita", "alert_prezzi",
        "backup_meta", "backups", "haccp_documenti", "email_log",
        "ordini_email_log", "listino_bar", "impostazioni", "stampanti_config",
}

# Resti MORTI di vecchie versioni Lotti (censimento 02/07/2026): mai citati dal
# codice attuale, candidati alla rinomina reversibile in cestino_<nome>.
# NB: warehouse_inventory RIMOSSA dai candidati il 02/07 sera — sembrava morta
# (1 doc) ma è passata a 212 doc in giornata: la scrive un'ALTRA app. Mai
# fidarsi del solo grep sul codice Lotti per le collezioni condivise.
_CANDIDATE_CESTINO = [
    "haccp_lotti", "warehouse_movements", "warehouse_stocks",
    "tracciabilita", "schede_tecniche_jobs",
    "schede_tecniche_prodotti", "ordini_app_storico", "ordini_app_reparti",
    "produzione_mattina_template",
]


@router.get("/pulizia-collezioni-proposta")
async def pulizia_collezioni_proposta():
    """Calcola la proposta di pulizia: collezioni VUOTE non protette (drop senza
    rischio) + resti morti Lotti noti (rinomina reversibile in cestino_*).
    Solo lettura: il pannello Controllo Dati la mostra, Enzo conferma."""
    esistenti = await db.list_collection_names()
    vuote = []
    for c in sorted(esistenti):
        if c in _COLLEZIONI_PROTETTE or c.startswith(("system.", "cestino_")):
            continue
        if await db[c].count_documents({}) == 0:
            vuote.append(c)
    cestino = []
    for c in _CANDIDATE_CESTINO:
        if c in esistenti:
            cestino.append({"collezione": c, "documenti": await db[c].count_documents({})})
    return {"drop_vuote": vuote, "rinomina_cestino": cestino,
            "nota": "vuote = eliminabili senza rischio; cestino = rinomina reversibile"}


@router.post("/pulizia-collezioni")
async def pulizia_collezioni(payload: dict = None, _admin=Depends(require_admin)):
    """Pulizia collezioni autorizzata da Enzo (02/07/2026, bolletta Atlas).
    Body: {drop_vuote: [nomi], rinomina_cestino: [nomi], conferma: bool}.
    - drop_vuote: eliminate SOLO se davvero vuote al momento dell'esecuzione
      (ricontrollo server-side; se contiene documenti viene saltata).
    - rinomina_cestino: rinominate in 'cestino_<nome>' — REVERSIBILE, i dati
      restano; si droppa in un secondo momento quando è certo che nulla le usa.
    - Rifiuta qualsiasi collezione usata dal codice Lotti (lista protetta) o
      già nel cestino. Senza conferma=true: solo anteprima, non tocca nulla."""
    from fastapi import HTTPException
    payload = payload or {}
    drop_vuote = [str(c).strip() for c in (payload.get("drop_vuote") or []) if str(c).strip()]
    rinomina = [str(c).strip() for c in (payload.get("rinomina_cestino") or []) if str(c).strip()]
    conferma = bool(payload.get("conferma", False))
    if not drop_vuote and not rinomina:
        raise HTTPException(400, "nessuna collezione indicata")

    protette = _COLLEZIONI_PROTETTE
    esistenti = set(await db.list_collection_names())

    report = {"drop": [], "rinomina": [], "saltate": [], "conferma": conferma}
    for nome in drop_vuote:
        if nome in protette or nome.startswith("system."):
            report["saltate"].append({"collezione": nome, "motivo": "protetta"})
            continue
        if nome not in esistenti:
            report["saltate"].append({"collezione": nome, "motivo": "non esiste"})
            continue
        n = await db[nome].count_documents({})
        if n > 0:
            report["saltate"].append({"collezione": nome, "motivo": f"NON vuota ({n} documenti)"})
            continue
        if conferma:
            await db[nome].drop()
        report["drop"].append(nome)

    for nome in rinomina:
        if nome in protette or nome.startswith("system.") or nome.startswith("cestino_"):
            report["saltate"].append({"collezione": nome, "motivo": "protetta o già nel cestino"})
            continue
        if nome not in esistenti:
            report["saltate"].append({"collezione": nome, "motivo": "non esiste"})
            continue
        n = await db[nome].count_documents({})
        if conferma:
            await db[nome].rename(f"cestino_{nome}", dropTarget=False)
        report["rinomina"].append({"collezione": nome, "documenti": n,
                                   "nuovo_nome": f"cestino_{nome}"})

    return report


@router.get("/temperature-status/{anno}")
async def temperature_status(anno: int):
    """Cosa c'è davvero nelle schede temperature per l'anno"""
    pos = await db.temperature_positive.find({"anno": anno}, {"_id": 0}).to_list(50)
    neg = await db.temperature_negative.find({"anno": anno}, {"_id": 0}).to_list(50)

    def riassumi(schede, label):
        out = []
        for s in schede:
            mesi_pieni = {}
            for m, dati in (s.get("temperature", {}) or {}).items():
                if dati:
                    mesi_pieni[m] = len(dati)
            out.append(
                {
                    "numero": s.get(
                        f"frigorifero_numero" if label == "frigo" else "congelatore_numero"
                    ),
                    "nome": s.get(f"frigorifero_nome" if label == "frigo" else "congelatore_nome"),
                    "mesi_con_dati": mesi_pieni,
                    "totale_giorni_compilati": sum(mesi_pieni.values()),
                }
            )
        return out

    return {
        "anno": anno,
        "frigoriferi": riassumi(pos, "frigo"),
        "congelatori": riassumi(neg, "freezer"),
    }


@router.get("/salute-sistema")
async def salute_sistema():
    """
    Stato di salute del sistema per la dashboard: cosa gira in automatico
    (ultima esecuzione di ogni job notturno) + conteggi chiave.
    Pensato per mostrare semafori verdi/gialli all'utente.
    """
    from datetime import datetime, timezone, timedelta

    # Job monitorati con descrizione leggibile e soglia di "freschezza" (ore)
    JOBS = [
        {"job": "normalizza_nuovi_prodotti", "label": "Normalizzazione nomi prodotti", "ore_max": 26, "emoji": "🏷️"},
        {"job": "pulizia_lotti_scaduti", "label": "Pulizia lotti scaduti", "ore_max": 26, "emoji": "🧹"},
        {"job": "check_scorta_minima", "label": "Controllo scorte minime", "ore_max": 26, "emoji": "📊"},
        {"job": "haccp_daily", "label": "Registri HACCP giornalieri", "ore_max": 26, "emoji": "📋"},
        {"job": "automatismi_haccp", "label": "Controlli olio/temperature/reclami", "ore_max": 130, "emoji": "🌡️"},
        {"job": "backup_notturno", "label": "Backup dati", "ore_max": 26, "emoji": "💾"},
    ]

    ora = datetime.now(timezone.utc)
    stato_job = []
    for j in JOBS:
        ultimo = await db.scheduler_logs.find_one(
            {"job": j["job"]}, {"_id": 0}, sort=[("timestamp", -1)]
        )
        verde = False
        quando = None
        if ultimo and ultimo.get("timestamp"):
            try:
                ts = datetime.fromisoformat(ultimo["timestamp"].replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                delta_ore = (ora - ts).total_seconds() / 3600
                verde = delta_ore <= j["ore_max"]
                quando = ultimo["timestamp"]
            except Exception:
                _LOG_INIT.debug("[diagnostic] errore non bloccante ignorato")
        stato_job.append({
            "label": j["label"],
            "emoji": j["emoji"],
            "ok": verde,
            "ultima_esecuzione": quando,
        })

    # Conteggi chiave
    try:
        n_fatture = await db.fatture.count_documents({})
    except Exception:
        n_fatture = 0
    try:
        # "consumato" NON è un valore di stato (è un flag booleano): il vecchio
        # conteggio non escludeva nulla. Si usa il filtro canonico dei lotti aperti.
        from app.lotti.routers.supervisor_operativo import FILTRO_LOTTO_APERTO
        n_lotti_attivi = await db.lotti.count_documents(dict(FILTRO_LOTTO_APERTO))
    except Exception:
        n_lotti_attivi = 0
    try:
        n_ordini_bozza = await db.ordini_fornitori.count_documents({"stato": "bozza"})
    except Exception:
        n_ordini_bozza = 0
    try:
        n_prodotti = await db.dizionario_prodotti.count_documents({})
    except Exception:
        n_prodotti = 0

    tutti_ok = all(s["ok"] for s in stato_job)

    return {
        "tutto_ok": tutti_ok,
        "job": stato_job,
        "conteggi": {
            "fatture": n_fatture,
            "lotti_attivi": n_lotti_attivi,
            "ordini_bozza": n_ordini_bozza,
            "prodotti": n_prodotti,
        },
        "aggiornato_il": ora.isoformat(),
    }


# ── Riepilogo registro HACCP: tutte le registrazioni obbligatorie in un colpo ──
@router.get("/registro-haccp")
async def registro_haccp_riepilogo():
    """Aggrega lo stato di tutte le registrazioni HACCP obbligatorie + organico.
    Una sola chiamata per il cruscotto del registro (temperature, lotti, anomalie,
    sanificazione, controllo olio, reclami, libretti sanitari, personale per postazione)."""
    from datetime import datetime, timezone, timedelta

    oggi = datetime.now(timezone.utc)
    oggi_ymd = oggi.strftime("%Y-%m-%d")
    inizio_mese = oggi.replace(day=1).strftime("%Y-%m-%d")

    async def _count(coll, filtro=None):
        try:
            return await db[coll].count_documents(filtro or {})
        except Exception:
            return 0

    # Temperature oggi: lette dalle SCHEDE ANNUALI (struttura reale dei registri)
    anno_i, mese_s, giorno_s = oggi.year, str(oggi.month), str(oggi.day)

    async def _temp_oggi(coll):
        n = 0
        try:
            async for s in db[coll].find({"anno": anno_i}, {"_id": 0, "temperature": 1}):
                v = ((s.get("temperature") or {}).get(mese_s) or {}).get(giorno_s)
                if v not in (None, "", {}):
                    n += 1
        except Exception:
            _LOG_INIT.debug("[diagnostic] errore non bloccante ignorato")
        return n

    temp_pos_oggi = await _temp_oggi("temperature_positive")
    temp_neg_oggi = await _temp_oggi("temperature_negative")
    temp_cottura_mese = await _count("temperature_cottura", {"data": {"$gte": inizio_mese}})
    # Controllo olio
    olio_mese = await _count("controllo_olio", {"data": {"$gte": inizio_mese}})
    # Lotti attivi: sistema lotti UNICO (db.lotti, non esauriti)
    lotti_attivi = await _count("lotti", {"esaurito": {"$ne": True}})
    # Anomalie aperte
    anomalie_aperte = await _count("anomalie", {"stato": {"$ne": "risolta"}})
    # Sanificazione oggi: X segnate oggi nella scheda mensile reale
    sanif_oggi = 0
    try:
        s = await db.sanificazione_schede.find_one(
            {"anno": anno_i, "mese": oggi.month}, {"_id": 0, "registrazioni": 1}
        )
        if s:
            sanif_oggi = sum(
                1 for v in (s.get("registrazioni") or {}).values()
                if isinstance(v, dict) and v.get(giorno_s) == "X"
            )
    except Exception:
        _LOG_INIT.debug("[diagnostic] errore non bloccante ignorato")
    # Reclami aperti
    reclami_aperti = await _count("reclami_fornitori", {"stato": "aperto"})

    # Organico + libretti
    operatori = await db.tablet_operatori.find(
        {"attivo": True}, {"_id": 0, "pin": 0}
    ).to_list(200)
    organico = {}
    libretti_scaduti = 0
    libretti_in_scadenza = 0
    libretti_non_registrati = 0
    oggi_d = oggi.date()
    for d in operatori:
        if d.get("ruolo") == "amministratore":
            continue
        post = d.get("postazione") or "Non assegnata"
        scad = d.get("libretto_sanitario_scadenza") or ""
        stato = "non_registrato"
        giorni = None
        if scad:
            try:
                ds = datetime.strptime(scad[:10], "%Y-%m-%d").date()
                giorni = (ds - oggi_d).days
                if giorni < 0:
                    stato = "scaduto"; libretti_scaduti += 1
                elif giorni <= 30:
                    stato = "in_scadenza"; libretti_in_scadenza += 1
                else:
                    stato = "valido"
            except Exception:
                libretti_non_registrati += 1
        else:
            libretti_non_registrati += 1
        organico.setdefault(post, []).append({
            "nome": d.get("nome", ""),
            "cognome": d.get("cognome", ""),
            "mansione": d.get("mansione", ""),
            "libretto_scadenza": scad,
            "stato_libretto": stato,
            "giorni_alla_scadenza": giorni,
        })

    return {
        "data": oggi_ymd,
        "temperature": {
            "positive_oggi": temp_pos_oggi,
            "negative_oggi": temp_neg_oggi,
            "cottura_mese": temp_cottura_mese,
        },
        "controllo_olio_mese": olio_mese,
        "lotti_attivi": lotti_attivi,
        "anomalie_aperte": anomalie_aperte,
        "sanificazione_oggi": sanif_oggi,
        "reclami_aperti": reclami_aperti,
        "organico": organico,
        "libretti": {
            "scaduti": libretti_scaduti,
            "in_scadenza": libretti_in_scadenza,
            "non_registrati": libretti_non_registrati,
        },
        "totale_dipendenti": len([d for d in operatori if d.get("ruolo") != "amministratore"]),
        "aggiornato_il": oggi.isoformat(),
    }


@router.get("/integrazioni")
async def stato_integrazioni():
    """Stato di configurazione delle integrazioni esterne.

    Riporta SOLO la presenza/assenza delle variabili d'ambiente (booleani),
    MAI il loro valore. Serve per capire dall'esterno cosa e gia configurato
    in produzione (Render) senza esporre segreti ne inviare email/messaggi di test.
    """
    def has(name: str) -> bool:
        return bool((os.environ.get(name) or "").strip())

    relay_ok = has("GMAIL_RELAY_URL") and has("GMAIL_RELAY_SECRET")
    email_ok = relay_ok or ((has("GMAIL_EMAIL") or has("SMTP_EMAIL") or has("ADMIN_EMAIL")) and (has("GMAIL_APP_PASSWORD") or has("SMTP_PASSWORD")))
    pec_ok = (has("ARUBA_PEC_USER") or has("PEC_USER")) and (has("ARUBA_PEC_PASSWORD") or has("PEC_PASSWORD"))
    wa_ok = (has("WHATSAPP_API_TOKEN") or has("WHATSAPP_TOKEN")) and (has("WHATSAPP_PHONE_NUMBER_ID") or has("WHATSAPP_PHONE_ID"))
    wa_dest = [n for n in ("WHATSAPP_RECIPIENT_1", "WHATSAPP_RECIPIENT_2") if has(n)]

    return {
        "email": {
            "gmail_configurato": email_ok,
            "GMAIL_EMAIL": has("GMAIL_EMAIL"),
            "GMAIL_APP_PASSWORD": has("GMAIL_APP_PASSWORD"),
            "pec_configurato": pec_ok,
            "ARUBA_PEC_USER": has("ARUBA_PEC_USER"),
            "ARUBA_PEC_PASSWORD": has("ARUBA_PEC_PASSWORD"),
            "ponte_apps_script": relay_ok,
            "invio_possibile": email_ok or pec_ok,
        },
        "whatsapp": {
            "configurato": wa_ok,
            "WHATSAPP_API_TOKEN": has("WHATSAPP_API_TOKEN"),
            "WHATSAPP_PHONE_NUMBER_ID": has("WHATSAPP_PHONE_NUMBER_ID"),
            "destinatari_default": len(wa_dest),
        },
        "database": {
            "tipo": "supabase" if has("LOTTI_SUPABASE_URL") else "memoria_non_persistente",
            "LOTTI_SUPABASE_URL": has("LOTTI_SUPABASE_URL"),
            "LOTTI_SUPABASE_ANON_KEY": has("LOTTI_SUPABASE_ANON_KEY"),
            "LOTTI_DB_SECRET": has("LOTTI_DB_SECRET"),
            "LOTTI_DB_NAME": os.environ.get("LOTTI_DB_NAME", "Gestionale"),
        },
    }


@router.get("/env-keys")
async def env_keys():
    """Elenca i NOMI (mai i valori) delle variabili d'ambiente presenti che
    riguardano le integrazioni, per diagnosticare nomi diversi da quelli attesi
    dal codice. Non espone alcun valore."""
    pattern = ("smtp", "gmail", "mail", "whatsapp", "wa_", "pec", "aruba",
               "recipient", "phone", "twilio", "sendgrid", "mailgun")
    presenti = sorted([k for k in os.environ.keys() if any(p in k.lower() for p in pattern)])
    return {
        "env_presenti_rilevanti": presenti,
        "attesi_dal_codice": {
            "email_gmail": ["GMAIL_EMAIL", "GMAIL_APP_PASSWORD"],
            "email_pec": ["ARUBA_PEC_USER", "ARUBA_PEC_PASSWORD"],
            "whatsapp": ["WHATSAPP_API_TOKEN", "WHATSAPP_PHONE_NUMBER_ID",
                         "WHATSAPP_RECIPIENT_1", "WHATSAPP_RECIPIENT_2"],
        },
    }
