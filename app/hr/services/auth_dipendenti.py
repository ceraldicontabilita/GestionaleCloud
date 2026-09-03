"""
Autenticazione per-dipendente via PIN personale.

Ogni dipendente ha un PIN personale (salvato come hash sul suo documento, mai
in chiaro) e un `ruolo_app`. Il login richiede dipendente_id + pin, così non ci
sono collisioni tra PIN uguali. Emette un JWT coerente con il resto del portale
(jose + settings), con role = ruolo_app.
"""
import hashlib
import hmac
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional

from jose import jwt

from app.hr.config import settings
from app.hr.database import Database, Collections

logger = logging.getLogger(__name__)

# Ruoli assegnabili dal portale. "admin" NON e' tra questi: l'amministratore
# e' l'utente del gestionale (login unico con PIN + MFA), e un token con ruolo
# admin firmato dallo stesso segreto aprirebbe tutto il gestionale. Un vecchio
# ruolo_app="admin" in anagrafica vale come "dipendente".
RUOLI_VALIDI = {"dipendente", "responsabile_turni"}


def ruolo_portale(dip: Dict[str, Any]) -> str:
    ruolo = dip.get("ruolo_app", "dipendente")
    return ruolo if ruolo in RUOLI_VALIDI else "dipendente"


def hash_pin(pin: str) -> str:
    return hashlib.sha256(pin.encode("utf-8")).hexdigest()


def verify_pin(pin: str, pin_hash: str) -> bool:
    if not pin or not pin_hash:
        return False
    return hmac.compare_digest(hash_pin(pin), pin_hash)


def _valid_pin_format(pin: str) -> bool:
    return bool(pin) and pin.isdigit() and 4 <= len(pin) <= 8


def crea_token_dipendente(dip: Dict[str, Any]) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": dip["id"],
        "name": dip.get("nome_completo", ""),
        "role": ruolo_portale(dip),
        "tipo": "dipendente",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "auth_method": "pin_dipendente",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


async def login_dipendente_per_nome(nome: str, pin: str) -> Optional[Dict[str, Any]]:
    """Login senza elenco esposto: il dipendente scrive il PROPRIO cognome (o
    nome e cognome) e il PIN. Si cercano i dipendenti attivi che corrispondono
    al nome e si accetta solo quello il cui PIN verifica — così due omonimi non
    collidono e nessun nome viene mai mostrato prima dell'autenticazione."""
    nome = (nome or "").strip()
    if len(nome) < 2 or not _valid_pin_format(pin):
        return None
    db = Database.get_db()
    tokens = [t for t in nome.lower().split() if t]
    candidati = []
    async for d in db[Collections.EMPLOYEES].find(
            {"attivo": {"$ne": False},
             "merged_into": {"$exists": False},
             "stato": {"$nin": ["cessato", "dimesso", "archiviato"]}}):
        completo = (d.get("nome_completo") or f"{d.get('nome', '')} {d.get('cognome', '')}").lower()
        if all(t in completo for t in tokens):
            candidati.append(d)
    verificati = []
    for dip in candidati:
        ok = bool(dip.get("pin_hash")) and verify_pin(pin, dip["pin_hash"])
        if not ok:
            ok = await _pin_operatore_valido(db, dip, pin)
        if ok:
            verificati.append(dip)
    if len(verificati) != 1:
        return None  # nessuno o ambiguo (stesso nome E stesso PIN): niente accesso
    dip = verificati[0]
    token = crea_token_dipendente(dip)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": dip["id"],
        "name": dip.get("nome_completo", ""),
        "role": ruolo_portale(dip),
        "tipo": "dipendente",
        "auth_method": "pin_dipendente",
    }


def _nome_operatore_combacia(nome_op: str, nome_dip: str) -> bool:
    """Stessa regola di corrispondenza nome usata per accettare il PIN cassa:
    l'operatore combacia col dipendente se il suo nome e' contenuto per
    intero, o token per token, nel nome completo del dipendente."""
    nome_op = (nome_op or "").lower().strip()
    return bool(nome_op) and (nome_op in nome_dip or all(tok in nome_dip for tok in nome_op.split() if tok))


def _nome_completo(dip: Dict[str, Any]) -> str:
    return (dip.get("nome_completo") or f"{dip.get('nome', '')} {dip.get('cognome', '')}").strip().lower()


async def _pin_operatore_valido(db, dip: Dict[str, Any], pin: str) -> bool:
    """Verifica il PIN contro la fonte operatori condivisa (tablet_operatori),
    la stessa usata dalla cassa di Lotti. Accetta solo se l'operatore con quel
    PIN corrisponde, per nome, al dipendente selezionato (un dipendente non puo'
    entrare col PIN di un altro). PIN unico cassa+portale, nessuna copia.
    """
    nome_dip = _nome_completo(dip)
    if not nome_dip:
        return False
    candidati = []
    try:
        coll = db["tablet_operatori"]
        doc = await coll.find_one({"attivo": True, "pin_chiaro": pin}, {"_id": 0, "nome": 1})
        if doc:
            candidati.append(doc)
        else:
            try:
                import bcrypt
                for d in await coll.find({"attivo": True}, {"_id": 0, "nome": 1, "pin": 1}).to_list(100):
                    h = (d.get("pin") or "")
                    if h.startswith("$2") and bcrypt.checkpw(pin.encode(), h.encode()):
                        candidati.append(d)
                        break
            except Exception:
                pass
    except Exception:
        return False
    return any(_nome_operatore_combacia(c.get("nome"), nome_dip) for c in candidati)


async def _operatori_attivi_per_nome(db) -> List[str]:
    """Nomi (minuscoli) degli operatori attivi in tablet_operatori — prefetch
    in blocco per elenco_dipendenti_per_login, invece di una query per
    dipendente (stesso pattern anti-N+1 usato altrove nel repo).

    Un fallimento di lettura qui NON va inghiottito (trovato da una review
    automatica): se tornasse silenziosamente [], chi usa solo il PIN della
    cassa sparirebbe dal selettore come se non avesse nessuna credenziale,
    con l'endpoint che risponde comunque 200 — nessun errore da mostrare, il
    "Riprova" già previsto in Login non scatterebbe mai. Lasciando propagare
    l'eccezione, l'endpoint fallisce esplicitamente e il frontend lo tratta
    come l'errore di rete che già gestisce."""
    out = []
    async for o in db["tablet_operatori"].find({"attivo": True}):
        nome_op = (o.get("nome") or "").lower().strip()
        if nome_op:
            out.append(nome_op)
    return out


async def operatore_amministratore(db, pin: str):
    """Operatore con ruolo amministratore e questo PIN, dalla fonte condivisa
    tablet_operatori. Permette l'accesso admin col PIN unico della cassa."""
    try:
        coll = db["tablet_operatori"]
        doc = await coll.find_one(
            {"attivo": True, "pin_chiaro": pin, "ruolo": "amministratore"},
            {"_id": 0, "id": 1, "nome": 1},
        )
        if doc:
            return doc
        try:
            import bcrypt
            for d in await coll.find({"attivo": True, "ruolo": "amministratore"},
                                     {"_id": 0, "id": 1, "nome": 1, "pin": 1}).to_list(50):
                h = (d.get("pin") or "")
                if h.startswith("$2") and bcrypt.checkpw(pin.encode(), h.encode()):
                    return d
        except Exception:
            pass
    except Exception:
        return None
    return None


def _dipendente_eleggibile(dip: Dict[str, Any]) -> bool:
    """Stesso filtro di login_dipendente_per_nome (attivo, non fuso, non
    cessato/dimesso/archiviato) — un dipendente non eleggibile non deve poter
    fare login con NESSUNA delle due fonti PIN, nemmeno quella della cassa."""
    if dip.get("attivo") is False:
        return False
    if "merged_into" in dip:
        return False
    if dip.get("stato") in ("cessato", "dimesso", "archiviato"):
        return False
    return True


async def login_dipendente(dipendente_id: str, pin: str) -> Optional[Dict[str, Any]]:
    """Valida il PIN del dipendente e ritorna il token, oppure None.

    Due fonti accettate (PIN unico aziendale):
      1. PIN personale del portale (pin_hash sul documento), se impostato.
      2. PIN della cassa: stessa fonte operatori di Lotti (tablet_operatori).

    Revoca il pin_hash alla cessazione (vedi handlers/dipendente_handlers.py)
    blocca solo la prima fonte: senza il controllo di eleggibilita' qui, un
    dipendente cessato il cui nome corrisponde ancora a un operatore attivo
    in tablet_operatori avrebbe potuto continuare a entrare a tempo
    indeterminato via PIN cassa (trovato da una review automatica).
    """
    if not _valid_pin_format(pin):
        return None
    db = Database.get_db()
    dip = await db[Collections.EMPLOYEES].find_one({"id": dipendente_id})
    if not dip or not _dipendente_eleggibile(dip):
        return None
    ok = False
    if dip.get("pin_hash") and verify_pin(pin, dip["pin_hash"]):
        ok = True
    if not ok and await _pin_operatore_valido(db, dip, pin):
        ok = True
    if not ok:
        return None
    token = crea_token_dipendente(dip)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": dip["id"],
        "name": dip.get("nome_completo", ""),
        "role": ruolo_portale(dip),
        "tipo": "dipendente",
        "auth_method": "pin_dipendente",
    }


async def elenco_dipendenti_per_login() -> List[Dict[str, Any]]:
    """Nomi dei dipendenti attivi, per il selettore di login del portale
    (tocca il tuo nome, poi il PIN — niente più tastiera).
    Decisione esplicita del titolare: reintroduce l'elenco nomi in login
    (prima rimosso per non esporli pre-autenticazione) in cambio di zero
    digitazione, per un dispositivo condiviso in negozio dove la lista dei
    dipendenti non è comunque un segreto. Restituisce solo id+nome: niente
    PIN, ruolo o altri dati — quelli restano protetti dal PIN al login vero.

    Include chi ha un pin_hash proprio OPPURE il cui nome corrisponde a un
    operatore attivo in tablet_operatori (PIN condiviso della cassa) — le due
    fonti che login_dipendente() accetta. Filtrare solo su pin_hash
    escluderebbe chi usa solo la cassa (col selettore a tocco non c'e' più
    modo di entrare scrivendo il nome); NON filtrare affatto mostrerebbe
    invece dipendenti appena creati senza alcuna credenziale funzionante —
    un nome selezionabile il cui PIN verrebbe sempre rifiutato (trovato da
    una review automatica su entrambi i casi, in due giri separati)."""
    db = Database.get_db()
    operatori_attivi = await _operatori_attivi_per_nome(db)
    out = []
    async for d in db[Collections.EMPLOYEES].find(
            {"attivo": {"$ne": False},
             "merged_into": {"$exists": False},
             "stato": {"$nin": ["cessato", "dimesso", "archiviato"]}}):
        nome = d.get("nome_completo") or f"{d.get('nome', '')} {d.get('cognome', '')}".strip()
        if not (nome and d.get("id")):
            continue
        ha_credenziale = bool(d.get("pin_hash")) or any(
            _nome_operatore_combacia(nome_op, _nome_completo(d)) for nome_op in operatori_attivi)
        if ha_credenziale:
            out.append({"id": d["id"], "nome": nome})
    out.sort(key=lambda x: x["nome"])
    return out


async def imposta_pin(dipendente_id: str, pin: str) -> bool:
    if not _valid_pin_format(pin):
        raise ValueError("PIN non valido: 4-8 cifre")
    db = Database.get_db()
    r = await db[Collections.EMPLOYEES].update_one(
        {"id": dipendente_id},
        {"$set": {"pin_hash": hash_pin(pin),
                  "pin_updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return r.matched_count > 0


async def rimuovi_pin(dipendente_id: str) -> bool:
    db = Database.get_db()
    r = await db[Collections.EMPLOYEES].update_one(
        {"id": dipendente_id}, {"$unset": {"pin_hash": "", "pin_updated_at": ""}}
    )
    return r.matched_count > 0


async def imposta_ruolo(dipendente_id: str, ruolo_app: str) -> bool:
    if ruolo_app not in RUOLI_VALIDI:
        raise ValueError(f"Ruolo non valido: {ruolo_app}")
    db = Database.get_db()
    r = await db[Collections.EMPLOYEES].update_one(
        {"id": dipendente_id}, {"$set": {"ruolo_app": ruolo_app}}
    )
    return r.matched_count > 0
