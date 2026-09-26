"""
Autenticazione per-dipendente via PIN personale.

Ogni dipendente ha un PIN personale (salvato come hash sul suo documento, mai
in chiaro) e un `ruolo_app`. Il login richiede la persona (chiave opaca del
selettore, mai l'id interno) + pin, così non ci sono collisioni tra PIN uguali. Emette un JWT coerente con il resto del portale
(jose + settings), con role = ruolo_app.
"""
import hashlib
import hmac
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional

import bcrypt

from app.hr.config import settings
from app.hr.database import Database, Collections
from app.services.workforce_tokens import create_workforce_token

logger = logging.getLogger(__name__)

RUOLI_VALIDI = {"dipendente", "responsabile_turni", "admin"}

# 14/09/2026 (titolare, R2-R4): UNA persona = UN PIN, impostato nella scheda
# HR e valido sia per il portale sia per firmare in Lotti (lotti, sanificazioni,
# temperature). I PIN storici di Lotti (bcrypt) sono stati migrati qui come
# sono; i PIN gia' presenti in HR erano SHA-256 non salato: restano validi in
# lettura, ma ogni PIN nuovo viene salvato con bcrypt + un'impronta HMAC
# (``pin_lookup``, segreto = chiave JWT dell'app HR, mai nel database) che
# permette di trovare la persona in un colpo solo senza provare bcrypt su
# tutti i dipendenti a ogni tocco del tablet.


def hash_pin(pin: str) -> str:
    return bcrypt.hashpw(pin.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def hash_pin_legacy(pin: str) -> str:
    """SHA-256 storico (solo per confronto con i PIN salvati prima del 14/09/2026)."""
    return hashlib.sha256(pin.encode("utf-8")).hexdigest()


def verify_pin(pin: str, pin_hash: str) -> bool:
    if not pin or not pin_hash:
        return False
    pin_hash = str(pin_hash)
    if pin_hash.startswith("$2"):
        try:
            return bcrypt.checkpw(pin.encode("utf-8"), pin_hash.encode("ascii"))
        except (ValueError, TypeError):
            return False
    return hmac.compare_digest(hash_pin_legacy(pin), pin_hash)


def pin_lookup(pin: str) -> str:
    """Impronta HMAC del PIN: serve solo a trovare la riga, il controllo vero resta l'hash."""
    return hmac.new(str(settings.SECRET_KEY).encode("utf-8"), pin.encode("utf-8"), hashlib.sha256).hexdigest()


def _valid_pin_format(pin: str) -> bool:
    return bool(pin) and pin.isascii() and pin.isdigit() and 4 <= len(pin) <= 8


def crea_token_dipendente(dip: Dict[str, Any]) -> str:
    return create_workforce_token(
        sub=dip["id"],
        name=dip.get("nome_completo", ""),
        role=dip.get("ruolo_app", "dipendente"),
        secret=settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
        expires_in=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        auth_method="pin_dipendente",
    )


async def login_dipendente_per_nome(nome: str, pin: str) -> Optional[Dict[str, Any]]:
    """Login senza elenco esposto: il dipendente scrive il PROPRIO cognome (o
    nome e cognome) e il PIN. Si cercano i dipendenti attivi che corrispondono
    al nome e si accetta solo quello il cui PIN verifica — così due omonimi non
    collidono e nessun nome viene mai mostrato prima dell'autenticazione."""
    nome = (nome or "").strip()
    if len(nome) < 2 or not pin or not pin.isascii() or not pin.isdigit() or not 4 <= len(pin) <= 12:
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
    # Un amministratore non entra da qui (vedi login_dipendente): non e' un
    # candidato, qualunque PIN scriva.
    verificati = [
        dip for dip in candidati
        if dip.get("ruolo_app") != "admin" and _valid_pin_format(pin)
        and bool(dip.get("pin_hash")) and verify_pin(pin, dip["pin_hash"])
    ]
    if len(verificati) != 1:
        return None  # nessuno o ambiguo (stesso nome E stesso PIN): niente accesso
    dip = verificati[0]
    token = crea_token_dipendente(dip)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": dip["id"],
        "name": dip.get("nome_completo", ""),
        "role": dip.get("ruolo_app", "dipendente"),
        "tipo": "dipendente",
        "auth_method": "pin_dipendente",
    }


def _nome_completo(dip: Dict[str, Any]) -> str:
    return (dip.get("nome_completo") or f"{dip.get('nome', '')} {dip.get('cognome', '')}").strip().lower()


def _dipendente_eleggibile(dip: Dict[str, Any]) -> bool:
    """Rapporto in forza (stesso criterio dell'anagrafica: ``stato_rapporto``)."""
    from app.hr.services.stato_rapporto import e_in_forza

    return e_in_forza(dip)


async def login_dipendente(dipendente_id: str, pin: str) -> Optional[Dict[str, Any]]:
    """Valida il PIN personale del dipendente e ritorna il token, oppure None.

    Una sola fonte: ``pin_hash`` sulla scheda HR (lo stesso PIN che firma in
    Lotti). Un amministratore (``ruolo_app == "admin"``) non entra da qui con
    nessun PIN: il PIN amministratore si digita solo nel login del Gestionale e
    HR ne legge la sessione (``/auth/session``); il suo PIN personale serve
    alla firma HACCP sul tablet, non a questo login.
    """
    if not _valid_pin_format(pin or ""):
        return None
    db = Database.get_db()
    dip = await db[Collections.EMPLOYEES].find_one({"id": dipendente_id})
    if not dip or not _dipendente_eleggibile(dip) or dip.get("ruolo_app") == "admin":
        return None
    if not (dip.get("pin_hash") and verify_pin(pin, dip["pin_hash"])):
        return None
    token = crea_token_dipendente(dip)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": dip["id"],
        "name": dip.get("nome_completo", ""),
        "role": dip.get("ruolo_app", "dipendente"),
        "tipo": "dipendente",
        "auth_method": "pin_dipendente",
    }


# Il selettore «tocca il tuo nome» non consegna gli id interni dell'anagrafica
# (li usano i router HR, Lotti e i ponti del gestionale): per ogni nome da' una
# chiave opaca, HMAC dell'id col segreto HR e un dominio proprio, che serve
# SOLO a questo login. Senza il segreto non si ricava l'id dalla chiave ne' la
# chiave dall'id, e nessun altro endpoint la accetta.
_DOMINIO_CHIAVE_LOGIN = b"hr-portale-login-v1:"
_LUNGHEZZA_CHIAVE_LOGIN = 32  # 128 bit in esadecimale
_ESADECIMALE = frozenset("0123456789abcdef")


def chiave_login(dipendente_id: str) -> str:
    return hmac.new(
        str(settings.SECRET_KEY).encode("utf-8"),
        _DOMINIO_CHIAVE_LOGIN + str(dipendente_id).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:_LUNGHEZZA_CHIAVE_LOGIN]


def _selezionabile_al_login(d: Dict[str, Any]) -> bool:
    """In forza, con un PIN personale e non amministratore. Il PIN
    amministratore si digita solo nel login del Gestionale: l'amministratore
    entra in HR con quella sessione (``/auth/session``), mai da questo elenco."""
    return bool(
        d.get("id") and _dipendente_eleggibile(d)
        and d.get("pin_hash") and d.get("ruolo_app") != "admin"
    )


async def _selezionabili_al_login() -> List[Dict[str, Any]]:
    db = Database.get_db()
    return [d async for d in db[Collections.EMPLOYEES].find({"merged_into": {"$exists": False}})
            if _selezionabile_al_login(d)]


def _nomi_visualizzati(dips: List[Dict[str, Any]]) -> List[str]:
    """Il nome di battesimo; fra omonimi si aggiunge l'iniziale del cognome e,
    se non basta, il cognome intero. Senza nome e cognome separati resta il
    nome completo dell'anagrafica (che e' «COGNOME NOME»)."""
    parti = []
    for d in dips:
        nome = str(d.get("nome") or "").strip()
        cognome = str(d.get("cognome") or "").strip()
        completo = str(d.get("nome_completo") or f"{cognome} {nome}").strip()
        parti.append((nome, cognome, completo))

    etichette = [n if (n and c) else comp for n, c, comp in parti]
    for distingui in (lambda n, c: f"{n} {c[0]}.", lambda n, c: f"{n} {c}"):
        uso: Dict[str, int] = {}
        for e in etichette:
            uso[e.lower()] = uso.get(e.lower(), 0) + 1
        etichette = [
            distingui(n, c) if (n and c and uso[e.lower()] > 1) else e
            for e, (n, c, _completo) in zip(etichette, parti)
        ]
    return etichette


async def elenco_dipendenti_per_login() -> List[Dict[str, Any]]:
    """Nomi dei dipendenti in forza CON un PIN impostato, per il selettore di
    login del portale (tocca il tuo nome, poi il PIN). Decisione esplicita del
    titolare (28/08/2026): i nomi sono pubblici, niente digitazione su un
    dispositivo condiviso. Per ogni nome solo la chiave opaca di login
    (``chiave_login``) e il nome da mostrare: nessun id interno, PIN, ruolo o
    altro dato. Chi non ha ancora un PIN non compare (un nome selezionabile il
    cui PIN verrebbe sempre rifiutato sarebbe un bug, non una comodita')."""
    dips = await _selezionabili_al_login()
    out = [{"chiave": chiave_login(d["id"]), "nome": nome}
           for d, nome in zip(dips, _nomi_visualizzati(dips))]
    out.sort(key=lambda x: x["nome"].lower())
    return out


async def login_dipendente_da_chiave(chiave: str, pin: str) -> Optional[Dict[str, Any]]:
    """Login dal selettore: la chiave opaca si risolve qui, lato server, fra le
    sole persone che l'elenco mostra. Una chiave inventata, un id interno al
    posto della chiave, una chiave di un segreto ruotato o di chi non e' piu'
    selezionabile non aprono niente."""
    chiave = str(chiave or "").strip().lower()
    if len(chiave) != _LUNGHEZZA_CHIAVE_LOGIN or not set(chiave) <= _ESADECIMALE:
        return None
    trovati = [d for d in await _selezionabili_al_login()
               if hmac.compare_digest(chiave_login(d["id"]), chiave)]
    if len(trovati) != 1:
        return None
    return await login_dipendente(trovati[0]["id"], pin)


async def dipendente_con_pin_uguale(db, pin: str, escludi_id: str = "") -> Optional[Dict[str, Any]]:
    """Un ALTRO dipendente in forza usa gia' questo PIN? (R3: PIN unico fra
    gli attivi.) Confronto sull'impronta quando c'e', altrimenti sull'hash."""
    impronta = pin_lookup(pin)
    async for d in db[Collections.EMPLOYEES].find(
            {"merged_into": {"$exists": False}, "pin_hash": {"$exists": True}},
            {"_id": 0, "id": 1, "nome_completo": 1, "nome": 1, "cognome": 1,
             "pin_hash": 1, "pin_lookup": 1, "attivo": 1, "stato": 1, "in_carico": 1}):
        if d.get("id") == escludi_id or not _dipendente_eleggibile(d) or not d.get("pin_hash"):
            continue
        if d.get("pin_lookup"):
            if hmac.compare_digest(str(d["pin_lookup"]), impronta):
                return d
            continue
        if verify_pin(pin, d["pin_hash"]):
            return d
    return None


async def trova_dipendente_per_pin(pin: str, solo_operatori_lotti: bool = False) -> List[Dict[str, Any]]:
    """La persona che ha questo PIN (usato dal tablet Lotti per firmare).

    Cerca prima per impronta (una query, niente bcrypt); se nessuno ce l'ha
    ancora (PIN migrati da Lotti o SHA-256 storici) prova l'hash di ogni
    dipendente in forza con un PIN e, trovato, scrive l'impronta cosi' la
    volta dopo e' immediata. Un cessato non viene mai restituito, qualunque
    PIN abbia ancora salvato. Con ``solo_operatori_lotti`` esclude chi ha
    ``lotti_operatore`` = false nella scheda HR.
    """
    if not _valid_pin_format(pin):
        return []
    db = Database.get_db()
    impronta = pin_lookup(pin)

    def ok(d):
        if not _dipendente_eleggibile(d):
            return False
        if solo_operatori_lotti and d.get("lotti_operatore") is False:
            return False
        return True

    trovati = [d for d in await db[Collections.EMPLOYEES].find(
        {"pin_lookup": impronta, "merged_into": {"$exists": False}}, {"_id": 0}).to_list(50) if ok(d)]
    if trovati:
        return [d for d in trovati if verify_pin(pin, d.get("pin_hash") or "")]
    candidati = await db[Collections.EMPLOYEES].find(
        {"pin_hash": {"$exists": True}, "merged_into": {"$exists": False}}, {"_id": 0}).to_list(500)
    for d in candidati:
        if not ok(d) or d.get("pin_lookup") or not d.get("pin_hash"):
            continue
        if verify_pin(pin, d["pin_hash"]):
            await db[Collections.EMPLOYEES].update_one({"id": d["id"]}, {"$set": {"pin_lookup": impronta}})
            trovati.append(d)
    return trovati


async def imposta_pin(dipendente_id: str, pin: str) -> bool:
    if not _valid_pin_format(pin):
        raise ValueError("PIN non valido: 4-8 cifre")
    db = Database.get_db()
    altro = await dipendente_con_pin_uguale(db, pin, escludi_id=dipendente_id)
    if altro:
        raise ValueError("Questo PIN e' gia' di un altro dipendente attivo: scegline un altro")
    r = await db[Collections.EMPLOYEES].update_one(
        {"id": dipendente_id},
        {"$set": {"pin_hash": hash_pin(pin), "pin_lookup": pin_lookup(pin),
                  "pin_updated_at": datetime.now(timezone.utc).isoformat()},
         "$unset": {"pin_migrato_da_lotti": ""}},
    )
    return r.matched_count > 0


async def rimuovi_pin(dipendente_id: str) -> bool:
    db = Database.get_db()
    r = await db[Collections.EMPLOYEES].update_one(
        {"id": dipendente_id}, {"$unset": {"pin_hash": "", "pin_lookup": "", "pin_updated_at": ""}}
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
