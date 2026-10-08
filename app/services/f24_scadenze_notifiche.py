"""
Servizio Notifiche Scadenze F24 - Push Alert Proattivi

Controlla giornalmente le scadenze F24 imminenti e invia:
- Alert via Telegram (immediato)
- Alert via Email (riepilogo)
- Salva notifiche nel DB per il frontend (badge + campanella)

Livelli di urgenza:
- CRITICA: scadenza oggi o scaduta
- ALTA: scadenza entro 3 giorni
- MEDIA: scadenza entro 7 giorni
- BASSA: scadenza entro 15 giorni
"""

import logging
import os
from datetime import datetime, date, timedelta, timezone
from typing import Dict, Any, List, Optional
import uuid

from app.database import Database

logger = logging.getLogger(__name__)


async def destinatario_notifiche(db) -> Optional[str]:
    """A chi mandare l'email delle scadenze F24.

    Fino al 19/09/2026 questa email **non e' mai partita**. Cercava il
    destinatario in `configurazioni` e poi in `users`: due collezioni in cui
    non e' mai stata scritta una riga, in nessun punto del codice. Nessun
    destinatario, nessun invio, e nemmeno una riga di log a dirlo — proprio
    sulle scadenze fiscali, dove il silenzio costa una sanzione.

    Le due collezioni restano come prima scelta, se un giorno le si popola.
    L'ultima parola ce l'ha `ADMIN_EMAIL`, la stessa variabile Render che HR
    usa gia' per le sue notifiche: una convenzione sola, non una nuova.
    Quando non c'e' nessun destinatario lo si **dice**.
    """
    for collezione, query, campi in (
        ("configurazioni", {"tipo": "notifiche_email"}, ("email_notifiche", "email")),
        ("users", {"role": "admin"}, ("email",)),
    ):
        try:
            doc = await db[collezione].find_one(query, {"_id": 0}) or {}
        except Exception:  # noqa: BLE001 — una fonte assente non ferma le altre
            logger.debug("Destinatario: %s non leggibile", collezione, exc_info=True)
            continue
        for campo in campi:
            valore = str(doc.get(campo) or "").strip()
            if valore:
                return valore

    da_ambiente = str(os.getenv("ADMIN_EMAIL") or "").strip()
    if da_ambiente:
        return da_ambiente

    logger.warning(
        "[F24] Nessun destinatario per le scadenze: `configurazioni` e `users` "
        "sono vuote e ADMIN_EMAIL non e' impostata. L'email non parte."
    )
    return None

# Costanti
# f24_unificato copre sia gli F24 con schema italiano (stato="pagato",
# data_scadenza) sia quelli con schema inglese arrivati dalla scansione email
# automatica (status="paid", scadenza) — unificato come collection il
# 13/07/2026, ma vedi controlla_scadenze_f24 sotto per come vengono
# riconosciuti entrambi gli schemi nella stessa query.
COLLECTION_F24 = "f24_unificato"
COLLECTION_ALERT = "alert_scadenze_f24"
COLLECTION_NOTIFICHE = "notifiche_scadenze"


def _calcola_urgenza(data_scadenza: date) -> Dict[str, Any]:
    """Calcola urgenza e giorni rimanenti per una scadenza."""
    oggi = date.today()
    giorni = (data_scadenza - oggi).days
    
    if giorni < 0:
        return {"livello": "SCADUTA", "giorni": giorni, "colore": "#7f1d1d", "emoji": "🚨"}
    elif giorni == 0:
        return {"livello": "CRITICA", "giorni": 0, "colore": "#dc2626", "emoji": "🔴"}
    elif giorni <= 3:
        return {"livello": "ALTA", "giorni": giorni, "colore": "#ea580c", "emoji": "🟠"}
    elif giorni <= 7:
        return {"livello": "MEDIA", "giorni": giorni, "colore": "#ca8a04", "emoji": "🟡"}
    elif giorni <= 15:
        return {"livello": "BASSA", "giorni": giorni, "colore": "#2563eb", "emoji": "🔵"}
    else:
        return {"livello": "OK", "giorni": giorni, "colore": "#16a34a", "emoji": "✅"}


def _parse_data_scadenza(f24: Dict) -> Optional[date]:
    """Estrae la data di scadenza da un F24."""
    # Prova vari campi
    for campo in ["scadenza", "data_scadenza", "data_versamento", "scadenza_stimata"]:
        val = f24.get(campo)
        if val:
            try:
                if isinstance(val, date):
                    return val
                if isinstance(val, datetime):
                    return val.date()
                if isinstance(val, str) and len(val) >= 10:
                    return datetime.strptime(val[:10], "%Y-%m-%d").date()
            except (ValueError, TypeError):
                continue
    
    # Se non c'è data scadenza esplicita, usa il periodo
    periodo = f24.get("periodo", "")
    if periodo:
        try:
            # Formato: "01/2026" o "2026-01"
            if "/" in periodo:
                parts = periodo.split("/")
                mese = int(parts[0])
                anno = int(parts[1])
            elif "-" in periodo:
                parts = periodo.split("-")
                anno = int(parts[0])
                mese = int(parts[1])
            else:
                return None
            
            # Scadenza F24: 16 del mese successivo
            mese_scadenza = mese + 1
            anno_scadenza = anno
            if mese_scadenza > 12:
                mese_scadenza = 1
                anno_scadenza += 1
            
            return date(anno_scadenza, mese_scadenza, 16)
        except (ValueError, TypeError, IndexError):
            pass
    
    return None


async def controlla_scadenze_f24() -> Dict[str, Any]:
    """
    Controlla tutte le scadenze F24 e genera alert per quelle imminenti.
    Ritorna un riepilogo delle scadenze trovate.
    """
    db = Database.get_db()
    oggi = date.today()
    limite = oggi + timedelta(days=15)
    
    # Bug trovato in audit 15/07/2026: COLLECTION_F24 e
    # COLLECTION_F24_COMMERCIALISTA sono la STESSA collection dall'unificazione
    # del 13/07 ("f24_unificato" per entrambe), ma qui venivano ancora
    # interrogate con DUE query separate e concatenate — ogni F24 finiva
    # doppio nella lista. In più, le due query controllavano solo UNO dei due
    # schemi campo (stato="pagato" / status="paid") ciascuna: un F24 pagato
    # tramite create_f24 (campo "status", valore inglese "paid") non veniva
    # MAI riconosciuto come pagato da nessuna delle due — generava un falso
    # alert "scaduto/non pagato" ogni giorno (Telegram/email/campanella).
    # Ora un'unica query sulla stessa collection, che riconosce entrambi gli
    # schemi contemporaneamente (un campo mancante non blocca l'altro).
    f24_list = await db[COLLECTION_F24].find(
        {
            "stato": {"$nin": ["pagato", "annullato", "deleted"]},
            "status": {"$nin": ["paid", "pagato", "annullato", "deleted", "cancelled"]},
        },
        {"_id": 0}
    ).to_list(1000)
    
    scadenze_imminenti = []
    scadenze_scadute = []
    alert_generati = 0
    
    for f24 in f24_list:
        data_scadenza = _parse_data_scadenza(f24)
        if not data_scadenza:
            continue
        
        # Solo scadenze entro 15 giorni o già scadute (ma non oltre 30 giorni fa)
        if data_scadenza > limite:
            continue
        if data_scadenza < oggi - timedelta(days=30):
            continue
        
        urgenza = _calcola_urgenza(data_scadenza)
        importo = float(f24.get("importo_totale", 0) or f24.get("totale", 0) or f24.get("totale_versato", 0) or 0)
        
        alert_data = {
            "f24_id": f24.get("id", str(uuid.uuid4())),
            "tipo": "SCADENZA_F24",
            "livello": urgenza["livello"],
            "giorni_rimanenti": urgenza["giorni"],
            "data_scadenza": data_scadenza.isoformat(),
            "importo": importo,
            "periodo": f24.get("periodo", ""),
            "descrizione": f24.get("descrizione") or f"F24 {f24.get('periodo', '')}",
            "codice_tributo": f24.get("codice_tributo", ""),
            "emoji": urgenza["emoji"],
            "colore": urgenza["colore"],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "letto": False,
            "notificato_email": False,
            "notificato_telegram": False
        }
        
        if urgenza["giorni"] < 0:
            scadenze_scadute.append(alert_data)
        else:
            scadenze_imminenti.append(alert_data)
        
        # Salva/aggiorna alert nel DB (upsert per evitare duplicati)
        await db[COLLECTION_ALERT].update_one(
            {"f24_id": alert_data["f24_id"], "tipo": "SCADENZA_F24"},
            {"$set": alert_data},
            upsert=True
        )
        alert_generati += 1
    
    # Ordina per urgenza
    scadenze_imminenti.sort(key=lambda x: x["giorni_rimanenti"])
    scadenze_scadute.sort(key=lambda x: x["giorni_rimanenti"])
    
    return {
        "data_controllo": oggi.isoformat(),
        "scadenze_imminenti": scadenze_imminenti,
        "scadenze_scadute": scadenze_scadute,
        "totale_alert": alert_generati,
        "importo_totale_imminente": round(sum(s["importo"] for s in scadenze_imminenti), 2),
        "importo_totale_scaduto": round(sum(s["importo"] for s in scadenze_scadute), 2),
    }


# ── F24 pagato in ritardo (decisione del titolare, 02/10/2026) ───────────────
#
# Il giorno DOPO la scadenza un modello F24 a debito senza quietanza ne'
# addebito CERTO in banca apre l'alert `F24_PAGAMENTO_IN_RITARDO`, nel
# catalogo unico. Il messaggio porta i giorni di ritardo e il ravvedimento
# calcolato dallo scadenzario (sanzione ridotta per fascia + interessi legali),
# che cresce ogni giorno: l'alert aperto si AGGIORNA, non si duplica. Si chiude
# da solo con la quietanza o l'addebito CERTO; un alert ignorato dal titolare
# non rinasce. Gira nel job delle 08:00 (`check_scadenze_f24_task`), lo stesso
# delle notifiche: non e' un secondo giro.

CODICE_ALERT_RITARDO = "F24_PAGAMENTO_IN_RITARDO"
#: Oltre questa finestra un modello scaduto e' storia (2018-2024 senza
#: quietanza abbinata): si conta (`oltre_finestra`), non si segnala.
FINESTRA_RITARDO_GIORNI = 365
_STATI_F24_FUORI = {"eliminato", "deleted", "annullato", "cancelled", "pagato", "paid"}


def _euro(cents: int) -> str:
    testo = f"{int(cents) / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{testo} €"


def _e_modello_f24(f24: Dict[str, Any]) -> bool:
    """Un modello (del commercialista o caricato), non una quietanza ne' un ravvedimento."""
    from app.services.f24_controllo_incrociato import e_modello_di_ravvedimento

    if f24.get("entity_status") == "deleted":
        return False
    if str(f24.get("status") or f24.get("stato") or "").lower() in _STATI_F24_FUORI:
        return False
    tipo = str(f24.get("tipo_documento") or f24.get("document_kind") or "").lower()
    if "quietanza" in tipo:
        return False
    return not e_modello_di_ravvedimento(f24)


def _scadenza_del_modello(f24: Dict[str, Any]):
    """(scadenza, fonte): `data_scadenza` se il modello la porta, altrimenti la regola del codice."""
    from app.services.scadenzario_tributi import scadenza_modello

    testo = str(f24.get("data_scadenza") or "")[:10]
    if testo:
        try:
            return date.fromisoformat(testo), "data_scadenza del modello"
        except ValueError:
            pass
    return scadenza_modello(f24)


def testo_alert_ritardo(f24: Dict[str, Any], scadenza: date, fonte: str, ravvedimento: Dict[str, Any]) -> str:
    giorni = (date.fromisoformat(ravvedimento["al"]) - scadenza).days
    descrizione = f24.get("descrizione") or f24.get("file_name") or f24.get("filename") or str(f24.get("id"))
    codici = ", ".join(sorted({f"{r['codice']} {r['periodo']}" for r in ravvedimento["righe"] + ravvedimento["righe_da_verificare"]}))
    testo = (
        f"F24 {descrizione} scaduto il {scadenza.strftime('%d/%m/%Y')} ({fonte}): "
        f"{giorni} giorni di ritardo, nessuna quietanza ne' addebito in banca. "
        f"Tributi a debito {_euro(ravvedimento['tributo_cents'])}"
        + (f" ({codici})" if codici else "") + ". "
    )
    if ravvedimento["righe"]:
        fasce = sorted({r["fascia"] for r in ravvedimento["righe"]})
        testo += (
            f"Ravvedimento al {date.fromisoformat(ravvedimento['al']).strftime('%d/%m/%Y')}: sanzione "
            f"{_euro(ravvedimento['sanzione_cents'])} ({'; '.join(fasce)}) + interessi legali "
            f"{_euro(ravvedimento['interessi_cents'])} = {_euro(ravvedimento['totale_cents'])} in tutto; "
            "cresce ogni giorno. "
        )
    if ravvedimento["righe_da_verificare"]:
        testo += (
            "Righe INPS/INAIL: sanzioni civili dell'ente, da verificare col consulente "
            f"({', '.join(r['codice'] for r in ravvedimento['righe_da_verificare'])}). "
        )
    return testo.strip()


async def segnala_f24_in_ritardo(db, oggi: Optional[date] = None) -> Dict[str, Any]:
    """Apre, aggiorna e chiude gli alert `F24_PAGAMENTO_IN_RITARDO`. Idempotente."""
    from app.constants.canale_documento import (
        STATO_ALERT_APERTO, STATO_ALERT_IGNORATO,
    )
    from app.db_collections import COLL_QUIETANZE_F24
    from app.services.alert_engine import COLL_ALERTS, genera_alert, risolvi_alert
    from app.services.f24_payment_evidence import stato_evidenza_pagamento
    from app.services.scadenzario_tributi import ravvedimento_atteso_modello

    oggi = oggi or date.today()
    esito = {"data": oggi.isoformat(), "aperti": 0, "aggiornati": 0, "chiusi": 0, "ignorati": 0,
             "senza_scadenza": 0, "oltre_finestra": 0, "in_ritardo": [], "chiusi_ids": []}

    modelli = [f for f in await db[COLLECTION_F24].find(
        {"status": {"$nin": sorted(_STATI_F24_FUORI)}}, {"_id": 0, "pdf_data": 0},
    ).to_list(5000) if _e_modello_f24(f)]

    # Quietanze agganciate dal lato della quietanza (`f24_associati`): il
    # modello non sempre porta `quietanza_id`.
    con_quietanza = set()
    for q in await db[COLL_QUIETANZE_F24].find({}, {"_id": 0, "f24_associati": 1, "status": 1,
                                                    "entity_status": 1}).to_list(5000):
        if q.get("entity_status") == "deleted" or str(q.get("status") or "").lower() in {"eliminato", "deleted"}:
            continue
        con_quietanza.update(str(v) for v in (q.get("f24_associati") or []) if v)

    alert_esistenti: Dict[str, Dict[str, Any]] = {}
    for a in await db[COLL_ALERTS].find(
        {"codice": CODICE_ALERT_RITARDO, "stato": {"$in": [STATO_ALERT_APERTO, STATO_ALERT_IGNORATO]}},
        {"_id": 0, "id": 1, "entita_id": 1, "stato": 1},
    ).to_list(5000):
        alert_esistenti[str(a.get("entita_id"))] = a

    for f24 in modelli:
        fid = str(f24.get("id") or "")
        if not fid:
            continue
        esistente = alert_esistenti.get(fid)
        provato = (stato_evidenza_pagamento(f24)["versato_documentalmente"] or fid in con_quietanza)
        if provato:
            if esistente and esistente.get("stato") == STATO_ALERT_APERTO:
                esito["chiusi"] += await risolvi_alert(CODICE_ALERT_RITARDO, fid, db,
                                                       resolved_by="quietanza_o_addebito_banca")
                esito["chiusi_ids"].append(fid)
            continue
        scadenza, fonte = _scadenza_del_modello(f24)
        if scadenza is None:
            esito["senza_scadenza"] += 1
            continue
        if scadenza >= oggi:
            continue  # scade oggi o dopo: non e' in ritardo (il giorno DOPO lo e')
        if (oggi - scadenza).days > FINESTRA_RITARDO_GIORNI:
            esito["oltre_finestra"] += 1
            continue
        ravvedimento = ravvedimento_atteso_modello(f24, oggi)
        dettaglio = testo_alert_ritardo(f24, scadenza, fonte, ravvedimento)
        extra = {"f24_id": fid, "scadenza": scadenza.isoformat(), "scadenza_fonte": fonte,
                 "giorni_ritardo": (oggi - scadenza).days, "ravvedimento": ravvedimento}
        esito["in_ritardo"].append({"f24_id": fid, "scadenza": scadenza.isoformat(),
                                    "giorni_ritardo": (oggi - scadenza).days,
                                    "ravvedimento_totale_cents": ravvedimento["totale_cents"]})
        if esistente and esistente.get("stato") == STATO_ALERT_IGNORATO:
            esito["ignorati"] += 1
            continue
        if esistente:
            # Il ravvedimento cresce ogni giorno: si aggiorna l'alert aperto, non se ne apre un altro.
            await db[COLL_ALERTS].update_one(
                {"id": esistente["id"], "stato": STATO_ALERT_APERTO},
                {"$set": {"dettaglio": dettaglio, "extra": extra,
                          "updated_at": datetime.now(timezone.utc).isoformat()}},
            )
            esito["aggiornati"] += 1
            continue
        creato = await genera_alert(
            CODICE_ALERT_RITARDO, fid, COLLECTION_F24, dettaglio, db, extra=extra,
        )
        esito["aperti"] += int(bool(creato))
    return esito


async def invia_notifiche_scadenze() -> Dict[str, Any]:
    """
    Invia notifiche push (Telegram + Email) per scadenze F24 imminenti.
    Chiamata dal scheduler giornaliero.
    """
    db = Database.get_db()

    # F24 gia' scaduti senza prova di pagamento: alert nel catalogo unico, stesso giro.
    try:
        ritardi = await segnala_f24_in_ritardo(db)
        logger.info("[F24] pagamenti in ritardo: aperti=%s aggiornati=%s chiusi=%s ignorati=%s",
                    ritardi["aperti"], ritardi["aggiornati"], ritardi["chiusi"], ritardi["ignorati"])
    except Exception as exc:  # noqa: BLE001 - il ritardo non ferma le notifiche di scadenza
        logger.error("[F24] alert pagamenti in ritardo non calcolati (%s: %s)", type(exc).__name__, exc)
        ritardi = {"errore": f"{type(exc).__name__}: {exc}"}

    # Prima controlla le scadenze
    risultato = await controlla_scadenze_f24()

    tutte_scadenze = risultato["scadenze_scadute"] + risultato["scadenze_imminenti"]

    if not tutte_scadenze:
        logger.info("📅 [F24] Nessuna scadenza imminente")
        return {"notifiche_inviate": 0, "messaggio": "Nessuna scadenza imminente", "ritardi": ritardi}

    # Filtra solo quelle non ancora notificate oggi
    da_notificare = [s for s in tutte_scadenze if s["livello"] in ["SCADUTA", "CRITICA", "ALTA", "MEDIA"]]

    if not da_notificare:
        return {"notifiche_inviate": 0, "messaggio": "Tutte le scadenze già notificate o non urgenti",
                "ritardi": ritardi}
    
    notifiche_telegram = 0
    notifiche_email = 0
    
    # === TELEGRAM ===
    try:
        from app.services.telegram_notifications import is_configured, send_notification
        
        if is_configured():
            # Componi messaggio Telegram
            linee = ["📅 *SCADENZE F24 IN ARRIVO*\n"]
            
            for s in da_notificare:
                giorni = s["giorni_rimanenti"]
                importo = s["importo"]
                desc = s["descrizione"][:50]
                emoji = s["emoji"]
                
                if giorni < 0:
                    tempo = f"⚠️ SCADUTO da {abs(giorni)} giorni!"
                elif giorni == 0:
                    tempo = "🚨 SCADE OGGI!"
                elif giorni == 1:
                    tempo = "⏰ Scade DOMANI"
                else:
                    tempo = f"📆 Scade tra {giorni} giorni ({s['data_scadenza']})"
                
                linee.append(f"{emoji} *{desc}*")
                linee.append(f"   💰 €{importo:,.2f} - {tempo}")
                linee.append("")
            
            totale = sum(s["importo"] for s in da_notificare)
            linee.append(f"💰 *Totale da versare: €{totale:,.2f}*")
            linee.append("\n👉 Vai alla dashboard F24 per dettagli")
            
            messaggio = "\n".join(linee)
            
            await send_notification(messaggio)
            notifiche_telegram = len(da_notificare)
            logger.info(f"📱 [F24] Notifica Telegram inviata: {notifiche_telegram} scadenze")
    except Exception as e:
        logger.warning(f"📱 [F24] Errore notifica Telegram: {e}")
    
    # === EMAIL ===
    try:
        from app.services.email_service import EmailService
        
        email_service = EmailService()
        if email_service.is_configured:
            # Componi email HTML
            html = _build_email_scadenze_html(da_notificare)
            
            destinatario = await destinatario_notifiche(db)

            if destinatario:
                n_scadenze = len(da_notificare)
                urgenti = len([s for s in da_notificare if s["livello"] in ["SCADUTA", "CRITICA"]])
                
                subject = f"⚠️ {n_scadenze} Scadenze F24"
                if urgenti > 0:
                    subject = f"🚨 {urgenti} F24 URGENTI + {n_scadenze - urgenti} in scadenza"
                
                sent = await email_service._send_email(destinatario, subject, html)
                if sent:
                    notifiche_email = len(da_notificare)
                    logger.info(f"📧 [F24] Email inviata a {destinatario}: {notifiche_email} scadenze")
    except Exception as e:
        logger.warning(f"📧 [F24] Errore notifica email: {e}")
    
    # Segna come notificate
    for s in da_notificare:
        update_fields = {}
        if notifiche_telegram > 0:
            update_fields["notificato_telegram"] = True
            update_fields["data_notifica_telegram"] = datetime.now(timezone.utc).isoformat()
        if notifiche_email > 0:
            update_fields["notificato_email"] = True
            update_fields["data_notifica_email"] = datetime.now(timezone.utc).isoformat()
        
        if update_fields:
            await db[COLLECTION_ALERT].update_one(
                {"f24_id": s["f24_id"], "tipo": "SCADENZA_F24"},
                {"$set": update_fields}
            )
    
    # Salva anche come notifiche generiche per il frontend (campanella)
    for s in da_notificare:
        if s["livello"] in ["SCADUTA", "CRITICA", "ALTA"]:
            await db[COLLECTION_NOTIFICHE].update_one(
                {"f24_id": s["f24_id"], "tipo": "SCADENZA_F24"},
                {"$set": {
                    "id": str(uuid.uuid4()),
                    "f24_id": s["f24_id"],
                    "tipo": "SCADENZA_F24",
                    "data_scadenza": s["data_scadenza"],
                    "descrizione": f"{s['emoji']} F24 {s['descrizione']} - €{s['importo']:,.2f}",
                    "importo": s["importo"],
                    "priorita": s["livello"].lower(),
                    "completata": False,
                    "created_at": datetime.now(timezone.utc).isoformat()
                }},
                upsert=True
            )
    
    return {
        "notifiche_telegram": notifiche_telegram,
        "notifiche_email": notifiche_email,
        "scadenze_notificate": len(da_notificare),
        "ritardi": ritardi,
        "dettaglio": [
            {
                "descrizione": s["descrizione"],
                "importo": s["importo"],
                "giorni": s["giorni_rimanenti"],
                "livello": s["livello"]
            }
            for s in da_notificare
        ]
    }


def _build_email_scadenze_html(scadenze: List[Dict]) -> str:
    """Costruisce email HTML con le scadenze F24."""
    
    righe = ""
    for s in scadenze:
        colore_bg = "#fff5f5" if s["livello"] in ["SCADUTA", "CRITICA"] else "#fffbeb" if s["livello"] == "ALTA" else "#f0fdf4"
        colore_testo = s["colore"]
        
        giorni = s["giorni_rimanenti"]
        if giorni < 0:
            tempo = f"<strong style='color:#991b1b'>SCADUTO da {abs(giorni)} giorni</strong>"
        elif giorni == 0:
            tempo = "<strong style='color:#dc2626'>SCADE OGGI</strong>"
        elif giorni == 1:
            tempo = "<strong style='color:#ea580c'>Scade DOMANI</strong>"
        else:
            tempo = f"Scade tra <strong>{giorni} giorni</strong> ({s['data_scadenza']})"
        
        righe += f"""
        <tr style="background:{colore_bg}">
            <td style="padding:12px;border-bottom:1px solid #e5e7eb">{s['emoji']} {s['descrizione']}</td>
            <td style="padding:12px;border-bottom:1px solid #e5e7eb;text-align:right;font-weight:bold">€{s['importo']:,.2f}</td>
            <td style="padding:12px;border-bottom:1px solid #e5e7eb">{tempo}</td>
            <td style="padding:12px;border-bottom:1px solid #e5e7eb;color:{colore_testo};font-weight:bold">{s['livello']}</td>
        </tr>
        """
    
    totale = sum(s["importo"] for s in scadenze)
    
    return f"""
    <html>
    <body style="font-family:Arial,sans-serif;max-width:700px;margin:0 auto;padding:20px">
        <div style="background:#1e40af;color:white;padding:20px;border-radius:8px 8px 0 0">
            <h1 style="margin:0;font-size:22px">📅 Scadenze F24 - Riepilogo</h1>
            <p style="margin:5px 0 0;opacity:0.9">{datetime.now().strftime('%d-%m-%Y %H:%M')} - Ceraldi Group</p>
        </div>
        
        <div style="border:1px solid #e5e7eb;border-top:none;padding:20px;border-radius:0 0 8px 8px">
            <p style="margin-top:0">Sono state rilevate <strong>{len(scadenze)} scadenze F24</strong> che richiedono attenzione:</p>
            
            <table style="width:100%;border-collapse:collapse;margin:15px 0">
                <thead>
                    <tr style="background:#f8fafc">
                        <th style="padding:10px;text-align:left;border-bottom:2px solid #e5e7eb">Descrizione</th>
                        <th style="padding:10px;text-align:right;border-bottom:2px solid #e5e7eb">Importo</th>
                        <th style="padding:10px;text-align:left;border-bottom:2px solid #e5e7eb">Scadenza</th>
                        <th style="padding:10px;text-align:left;border-bottom:2px solid #e5e7eb">Stato</th>
                    </tr>
                </thead>
                <tbody>
                    {righe}
                </tbody>
                <tfoot>
                    <tr style="background:#f1f5f9;font-weight:bold">
                        <td style="padding:12px">TOTALE</td>
                        <td style="padding:12px;text-align:right">€{totale:,.2f}</td>
                        <td colspan="2" style="padding:12px"></td>
                    </tr>
                </tfoot>
            </table>
            
            <p style="color:#6b7280;font-size:13px;margin-bottom:0">
                Questo è un alert automatico del sistema ERP Impresasempliceonline.<br/>
                Accedi alla dashboard F24 per i dettagli completi e procedere al pagamento.
            </p>
        </div>
    </body>
    </html>
    """
