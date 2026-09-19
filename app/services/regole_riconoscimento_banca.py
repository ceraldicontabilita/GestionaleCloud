"""Regole di riconoscimento IMPARATE per i movimenti bancari (19/09/2026).

Il titolare vuole poter "insegnare" al sistema a chi appartiene un movimento
anche quando il motore generico (`app.services.categorizzazione_movimenti`)
lo riconoscerebbe gia' da solo con parole chiave generiche — l'esempio dato:
un movimento che il motore chiamerebbe solo "Commissioni bancarie" ma che lui
sa essere di un fornitore preciso (es. Nexi). La scelta va MEMORIZZATA e
riapplicata ai prossimi movimenti con causale simile, e deve poter essere
ELIMINATA se sbagliata.

Collezione `regole_riconoscimento_banca` — stesso schema semplice a documento
di `mittenti_email`/`sistema_stato` (un id, i campi utili, niente
sub-collezioni). Ogni regola:

- ``id``: uuid.
- ``pattern``: frammento di causale normalizzato (maiuscolo, spazi singoli),
  su cui si riconosce il movimento.
- ``entita_tipo``: ``"fornitore"`` (l'anagrafica fornitori esistente,
  `app/routers/suppliers_module`) oppure ``"categoria"`` (categoria libera,
  quando non si tratta di un fornitore con anagrafica).
- ``entita_id`` / ``entita_nome``: a chi si riferisce la regola.
- ``categoria``: categoria da scrivere sul movimento. Opzionale se
  ``entita_tipo == "fornitore"``: se non specificata esplicitamente, un
  fornitore riconosciuto vale "Fatture" (stessa convenzione del motore
  generico: un riferimento a fornitore e' una fattura sua).
- ``creata_il``, ``creata_da``.

**Una regola imparata vince SEMPRE su un riconoscimento generico**: viene
controllata prima delle parole chiave in
`app.services.categorizzazione_movimenti.categorizza_movimento_bancario`.

**Eliminare una regola non tocca retroattivamente i movimenti gia' assegnati
da quella regola** (stesso principio di "Identita', prove e attese" in
CLAUDE.md: una prova successiva non riscrive il passato): la regola smette
solo di applicarsi ai prossimi movimenti/import.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

COLLEZIONE = "regole_riconoscimento_banca"

ENTITA_TIPI_VALIDI = {"fornitore", "categoria"}

# Frammenti da ripulire da una causale bancaria reale prima di usarla come
# pattern: riferimenti bancari variabili (RIF. ..., CRO), date ed importi.
# Senza questo passaggio ogni causale sarebbe un pattern diverso anche per lo
# stesso fornitore (stesso identificativo RIF/CRO non si ripete mai).
_RE_RIF = re.compile(r"\bRIF\.?\s*[A-Z0-9]+(?:/[A-Z0-9]+)?\b", re.I)
_RE_DATA = re.compile(r"\b\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}\b")
_RE_IMPORTO = re.compile(r"\b\d{1,3}(?:\.\d{3})*,\d{2}\b")
_RE_CODICE_LUNGO = re.compile(r"\b[A-Z]*\d{4,}[A-Z0-9]*\b")
_RE_TRATTINI = re.compile(r"[-–—]+")

# Sotto questa lunghezza il pattern ripulito non e' piu' abbastanza
# specifico da avere senso (es. e' rimasto solo "FAVORE -"): meglio la
# causale intera normalizzata che un frammento inutile.
_LUNGHEZZA_MINIMA_PATTERN = 4

# Audit 19/09/2026 su PR #500: vocabolario bancario comune a QUALSIASI
# movimento, di QUALSIASI controparte — "COMMISSIONI SU BONIFICI ESTERI"
# imparato da un movimento Nexi combacerebbe anche con le commissioni di un
# fornitore completamente diverso, se la causale non nomina mai il circuito.
# Un pattern fatto solo di queste parole non e' un riconoscimento, e' un
# indovinare (vietato da CLAUDE.md, "Ingresso documenti").
_PAROLE_GENERICHE_BANCARIE = {
    "COMMISSIONE", "COMMISSIONI", "SPESA", "SPESE", "BONIFICO", "BONIFICI",
    "BANCA", "BANCARIO", "BANCARIA", "BANCARI", "BANCARIE", "ESTERO",
    "ESTERI", "NAZIONALE", "NAZIONALI", "DISPOSIZIONE", "DISPOSIZIONI",
    "ADDEBITO", "ADDEBITI", "ACCREDITO", "ACCREDITI", "PAGAMENTO",
    "PAGAMENTI", "OPERAZIONE", "OPERAZIONI", "VALUTA", "CONTO", "CORRENTE",
    "TRASFERIMENTO", "TRASFERIMENTI", "SEPA", "SDD", "RID", "FAVORE",
    "ORDINANTE", "BENEFICIARIO", "BENEFICIARI", "TITOLO", "CAUSALE",
    "VARIE", "DIVERSI", "GENERICO", "GENERICA", "RIF", "DEL", "DELLA",
    "DELLO", "DEGLI", "DELLE", "PER", "CON", "SUL", "SULLA",
}


def _e_pattern_troppo_generico(pattern: str) -> bool:
    """True se il pattern non contiene nessuna parola specifica (un nome,
    un circuito, un servizio): solo vocabolario bancario comune. Un pattern
    cosi' non identifica la controparte imparata, cattura chiunque."""
    parole = re.findall(r"[A-ZÀ-Ù]+", pattern.upper())
    distintive = [p for p in parole if len(p) >= 4 and p not in _PAROLE_GENERICHE_BANCARIE]
    return len(distintive) == 0


def _normalizza(testo: Any) -> str:
    return re.sub(r"\s+", " ", str(testo or "").strip()).upper()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Separatore "duro" usato solo internamente da `estrai_pattern_da_causale`
# per marcare i frammenti variabili tolti dalla causale: un carattere di
# controllo che non compare mai in una causale bancaria reale.
_SEPARATORE_INTERNO = "\x00"


def estrai_pattern_da_causale(causale: Any) -> str:
    """Pattern ragionevole da una causale bancaria reale.

    Toglie riferimenti bancari (``RIF. MB0B00923006/90679785``), date e
    importi — sono variabili da un movimento all'altro dello stesso
    fornitore/servizio e farebbero fallire il riconoscimento dei prossimi —
    e tiene il frammento di testo stabile piu' lungo rimasto, non l'intera
    causale ripulita ricucita: due frammoti separati da un riferimento tolto
    (es. "SPA" e "DEL") non sono un pattern contiguo che ricompare tale e
    quale nella prossima causale, che avra' un riferimento diverso in mezzo.

    Se dopo la pulizia resta troppo poco per essere un pattern sensato
    (causale generica, tutta numeri/riferimenti), usa la causale intera
    normalizzata: e' la scelta piu' sicura quando non c'e' un frammento
    testuale stabile da isolare (lasciata segnalata come caso ambiguo per il
    titolare).
    """
    intera = _normalizza(causale)
    if not intera:
        return ""
    marcata = _RE_RIF.sub(_SEPARATORE_INTERNO, intera)
    marcata = _RE_DATA.sub(_SEPARATORE_INTERNO, marcata)
    marcata = _RE_IMPORTO.sub(_SEPARATORE_INTERNO, marcata)
    marcata = _RE_CODICE_LUNGO.sub(_SEPARATORE_INTERNO, marcata)
    marcata = _RE_TRATTINI.sub(_SEPARATORE_INTERNO, marcata)
    frammenti = [_normalizza(f) for f in marcata.split(_SEPARATORE_INTERNO)]
    migliore = max(frammenti, key=len, default="")
    if len(migliore) >= _LUNGHEZZA_MINIMA_PATTERN:
        return migliore
    return intera


def _valida_regola(*, pattern: str, entita_tipo: str, entita_id: Optional[str],
                    entita_nome: Optional[str]) -> str:
    pattern_norm = _normalizza(pattern)
    if not pattern_norm:
        raise ValueError("pattern mancante")
    if _e_pattern_troppo_generico(pattern_norm):
        raise ValueError(
            f"il pattern \"{pattern_norm}\" e' troppo generico (solo vocabolario "
            "bancario comune, nessun nome/servizio specifico riconoscibile): "
            "applicandolo rischierebbe di catturare movimenti di controparti "
            "diverse. Scegliere un movimento la cui causale nomini davvero il "
            "fornitore/servizio, oppure usare una categoria manuale per questo "
            "singolo movimento."
        )
    if entita_tipo not in ENTITA_TIPI_VALIDI:
        raise ValueError(f"entita_tipo deve essere uno di {sorted(ENTITA_TIPI_VALIDI)}")
    if entita_tipo == "fornitore" and not entita_id:
        raise ValueError("entita_id obbligatorio quando entita_tipo == 'fornitore'")
    if not entita_id and not entita_nome:
        raise ValueError("serve entita_id o entita_nome")
    return pattern_norm


async def crea_regola(
    db, *, pattern: str, entita_tipo: str, entita_id: Optional[str] = None,
    entita_nome: Optional[str] = None, categoria: Optional[str] = None,
    creata_da: Optional[str] = None,
) -> Dict[str, Any]:
    pattern_norm = _valida_regola(
        pattern=pattern, entita_tipo=entita_tipo, entita_id=entita_id, entita_nome=entita_nome,
    )
    categoria_norm = (categoria or "").strip() or None
    if not categoria_norm and entita_tipo == "fornitore":
        categoria_norm = "Fatture"
    regola = {
        "id": str(uuid.uuid4()),
        "pattern": pattern_norm,
        "entita_tipo": entita_tipo,
        "entita_id": entita_id,
        "entita_nome": (entita_nome or "").strip() or None,
        "categoria": categoria_norm,
        "creata_il": _now_iso(),
        "creata_da": creata_da,
    }
    await db[COLLEZIONE].insert_one(dict(regola))
    return regola


async def lista_regole(db) -> List[Dict[str, Any]]:
    regole = await db[COLLEZIONE].find({}, {"_id": 0}).to_list(10000)
    regole.sort(key=lambda r: r.get("creata_il") or "", reverse=True)
    return regole


async def elimina_regola(db, regola_id: str) -> bool:
    """Rimuove solo la regola: i movimenti gia' assegnati da essa restano
    come sono (nessun tocco retroattivo, vedi docstring del modulo)."""
    esito = await db[COLLEZIONE].delete_one({"id": regola_id})
    eliminati = getattr(esito, "deleted_count", None)
    if eliminati is None:
        return True
    return eliminati > 0


async def carica_regole(db) -> List[Dict[str, Any]]:
    """Prefetch unico da usare nei giri di import/backfill (CLAUDE.md, "Regole
    per chi scrive codice sui dati": mai una query per movimento)."""
    return await db[COLLEZIONE].find({}, {"_id": 0}).to_list(10000)


def trova_regola_per_descrizione(regole: List[Dict[str, Any]], descrizione: Any) -> Optional[Dict[str, Any]]:
    """La regola il cui pattern combacia con la descrizione, la piu'
    specifica (pattern piu' lungo) quando piu' regole combaciano."""
    desc_norm = _normalizza(descrizione)
    if not desc_norm:
        return None
    migliore: Optional[Dict[str, Any]] = None
    for regola in regole:
        pattern = regola.get("pattern") or ""
        if pattern and pattern in desc_norm:
            if migliore is None or len(pattern) > len(migliore.get("pattern") or ""):
                migliore = regola
    return migliore
