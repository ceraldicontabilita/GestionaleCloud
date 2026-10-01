"""Validazione e normalizzazione della partita IVA: un posto solo.

Chi confronta due P.IVA (deduplica fornitori, importer fatture, scheda
fornitore) passa da qui. Nessun valore si inventa: una P.IVA che non passa il
controllo resta com'e' e viene **segnalata** («P.IVA da verificare»), mai
corretta di nascosto.

Codici di segnalazione (`esito_piva`):
- `lunghezza`            italiana (solo cifre) con cifre diverse da 11
- `checksum`             11 cifre ma controllo di Luhn italiano errato
- `uguale_cf_persona`    nel campo P.IVA c'e' il codice fiscale di una persona
- `formato`              ne' 11 cifre ne' IdPaese UE + codice (es. prefisso perso)
- `estera_come_italiana` prefisso UE non italiano su un fornitore dichiarato IT
- `assente_con_fatture`  nessuna P.IVA ma il fornitore ha fatture
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# IdPaese UE (IVA) ammessi come prefisso. EL = Grecia, XI = Irlanda del Nord.
PREFISSI_UE = (
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL", "ES", "FI", "FR",
    "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO",
    "SE", "SI", "SK", "XI",
)
_RE_ESTERA = re.compile(r"^(%s)[0-9A-Z]{2,14}$" % "|".join(p for p in PREFISSI_UE if p != "IT"))
_RE_CF_PERSONA = re.compile(r"^[A-Z]{6}[0-9]{2}[A-Z][0-9]{2}[A-Z][0-9]{3}[A-Z]$")

MOTIVI = {
    "lunghezza": "La P.IVA italiana deve avere 11 cifre.",
    "checksum": "Il codice di controllo della P.IVA non torna.",
    "uguale_cf_persona": "Nel campo P.IVA c'e' un codice fiscale di persona.",
    "formato": "Formato P.IVA non riconosciuto (prefisso del paese mancante?).",
    "estera_come_italiana": "P.IVA di un altro paese UE su un fornitore italiano.",
    "assente_con_fatture": "Nessuna P.IVA in anagrafica ma il fornitore ha fatture.",
}


def normalizza_piva(valore: Any) -> str:
    """Solo lettere e cifre maiuscole; il prefisso IT davanti a 11 cifre si toglie."""
    if valore is None:
        return ""
    pulita = re.sub(r"[^0-9A-Za-z]", "", str(valore)).upper()
    if len(pulita) == 13 and pulita.startswith("IT") and pulita[2:].isdigit():
        return pulita[2:]
    return pulita


def chiave_confronto(valore: Any) -> str:
    """Chiave per dire «stessa P.IVA»: normalizzata e, se solo cifre, senza zeri iniziali."""
    p = normalizza_piva(valore)
    return p.lstrip("0") if p.isdigit() else p


def luhn_italiano_ok(p: str) -> bool:
    if not re.fullmatch(r"[0-9]{11}", p or ""):
        return False
    somma = 0
    for i, c in enumerate(p, start=1):
        d = int(c)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        somma += d
    return somma % 10 == 0


def piva_valida(valore: Any) -> bool:
    """Italiana (11 cifre, Luhn ok) oppure UE con IdPaese. Vuoto = non valida."""
    p = normalizza_piva(valore)
    if not p:
        return False
    if p.isdigit():
        return luhn_italiano_ok(p)
    return bool(_RE_ESTERA.match(p))


def esito_piva(
    piva: Any,
    *,
    codice_fiscale: Any = None,
    nazione: Any = None,
    fatture: int = 0,
) -> Optional[Dict[str, Any]]:
    """Segnalazione per la scheda fornitore, o `None` se la P.IVA e' a posto.

    Una P.IVA vuota si segnala solo se il fornitore ha fatture: un'anagrafica
    senza fatture e senza P.IVA e' un dato mancante, non un errore.
    """
    p = normalizza_piva(piva)
    codici: List[str] = []
    paese = str(nazione or "").strip().upper()
    if not p:
        if fatture and int(fatture) > 0:
            codici.append("assente_con_fatture")
    elif p.isdigit():
        if len(p) != 11:
            codici.append("lunghezza")
        elif not luhn_italiano_ok(p):
            codici.append("checksum")
    elif _RE_CF_PERSONA.match(p):
        codici.append("uguale_cf_persona")
    elif _RE_ESTERA.match(p):
        if paese in ("IT", "ITA", "ITALIA"):
            codici.append("estera_come_italiana")
    else:
        codici.append("formato")
    if not codici:
        return None
    return {
        "codici": codici,
        "motivo": " ".join(MOTIVI[c] for c in codici),
    }


def vista_piva(record: Dict[str, Any]) -> Dict[str, Any]:
    """Campi per la scheda e l'elenco fornitori: «P.IVA da verificare» col motivo."""
    esito = esito_piva(
        record.get("partita_iva") or record.get("piva") or record.get("vat_number"),
        codice_fiscale=record.get("codice_fiscale"),
        nazione=record.get("nazione"),
        fatture=int(record.get("fatture_count") or 0),
    )
    return {
        "piva_da_verificare": bool(esito),
        "piva_codici": esito["codici"] if esito else [],
        "piva_motivo": esito["motivo"] if esito else None,
    }
