"""Identita' logica condivisa delle righe di ``prima_nota_salari`` (PR 14/15).

Audit del commercialista 03/09/2026 (``memoria/AUDIT_COMMERCIALISTA_2026-09-03.md``
§5): la collezione ha sempre avuto due canali che scrivono la stessa
competenza con chiavi diverse (``import_key`` sull'importo, per l'import da
Excel/indice cedolini Drive; ``cedolino_id``/tipo raw, per il sync dal
registro interno ``cedolini``). Nessuno dei due sa che l'altro esiste perche'
il canale Excel non scrive mai il codice fiscale sulla riga: due righe della
stessa identita' (stesso dipendente, stesso mese, stesso tipo busta) restano
irriconoscibili l'una all'altra.

Questo modulo e' il punto UNICO di risoluzione dell'identita' logica
``(codice_fiscale, anno, mese, tipo_cedolino)``, riusato da:
- gli importer che scrivono ``prima_nota_salari`` (``import-salari-verificati``
  in ``routers/accounting/prima_nota_salari.py``, ``sincronizza_prima_nota_da_cedolini``
  in ``services/salari_sync.py``);
- il sync con l'archivio HR (PR 15, ``services/salari_sync_hr.py``);
- la bonifica dei doppioni (PR 14, ``services/bonifica_prima_nota_salari_doppioni.py``).

Vocabolario del tipo cedolino: quello dell'app HR
(``ordinario``/``tredicesima``/``quattordicesima``, vedi
``hr_cedolini_deposito.tipo_cedolino_hr``) — il registro interno del
gestionale chiama l'ordinario "mensile", l'import da Excel non scrive affatto
il campo (implicitamente ordinario). Riusare la stessa funzione di
normalizzazione gia' scritta per il deposito in HR evita un terzo vocabolario
parallelo.

Risoluzione del codice fiscale mancante: solo per nome UNIVOCO in anagrafica
(``dipendenti``, stessa tabella e stesso confronto a token gia' usato da
``services/stipendi_bonifici.py``/``services/identity_matching.py``). Un nome
che corrisponde a piu' di un dipendente, o a nessuno, non risolve: la riga
resta visibile solo nei report di verifica, mai fusa "a caso" con un'altra
(regola del titolare, CLAUDE.md "Identita', duplicati e relazioni").
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.services.hr_cedolini_deposito import tipo_cedolino_hr
from app.services.identity_matching import nome_tokens

# Vocabolario canonico: quello dell'app HR. "mensile" (registro interno) e
# "" (import Excel, campo assente) sono gia' mappati su "ordinario" da
# ``tipo_cedolino_hr``.
TIPI_CANONICI = {"ordinario", "tredicesima", "quattordicesima"}

ChiaveSalario = Tuple[str, int, int, str]


def tipo_cedolino_canonico(valore: Any) -> str:
    """Un solo vocabolario tipo cedolino in tutto il gestionale: quello HR."""
    tipo = tipo_cedolino_hr(valore)
    return tipo if tipo else "ordinario"


def nome_riga_salario(riga: Dict[str, Any]) -> str:
    for chiave in ("dipendente_nome", "dipendente", "nome_dipendente"):
        valore = str(riga.get(chiave) or "").strip()
        if valore:
            return valore
    return ""


class IndiceDipendenti:
    """Anagrafica gestionale caricata una volta, per risolvere il CF dal nome."""

    def __init__(self, dipendenti: List[Dict[str, Any]]):
        self.per_id: Dict[str, Dict[str, Any]] = {}
        self.per_cf: Dict[str, Dict[str, Any]] = {}
        gruppi: Dict[frozenset, List[Dict[str, Any]]] = {}
        for dip in dipendenti:
            did = str(dip.get("id") or "").strip()
            cf = str(dip.get("codice_fiscale") or dip.get("cf") or "").strip().upper()
            if did:
                self.per_id[did] = dip
            if cf:
                self.per_cf[cf] = dip
            nome = str(
                dip.get("nome_completo")
                or f"{dip.get('cognome', '')} {dip.get('nome', '')}".strip()
            )
            tokens = nome_tokens(nome)
            if len(tokens) >= 2:
                gruppi.setdefault(tokens, []).append(dip)
        # Un nome che corrisponde a piu' di un dipendente non risolve mai:
        # l'omonimia va segnalata, non indovinata.
        self._per_tokens: Dict[frozenset, Optional[Dict[str, Any]]] = {
            tokens: (voci[0] if len(voci) == 1 else None)
            for tokens, voci in gruppi.items()
        }

    def cf_per_nome(self, nome: str) -> Optional[str]:
        tokens = nome_tokens(nome)
        if len(tokens) < 2:
            return None
        dip = self._per_tokens.get(tokens)
        if not dip:
            return None
        cf = str(dip.get("codice_fiscale") or dip.get("cf") or "").strip().upper()
        return cf or None

    def dipendente_per_cf(self, cf: str) -> Optional[Dict[str, Any]]:
        return self.per_cf.get(str(cf or "").strip().upper())


async def carica_indice_dipendenti(db) -> IndiceDipendenti:
    from app.database import Collections

    dipendenti = await db[Collections.EMPLOYEES].find(
        {},
        {
            "_id": 0, "id": 1, "nome": 1, "cognome": 1,
            "nome_completo": 1, "codice_fiscale": 1, "cf": 1,
        },
    ).to_list(5000)
    return IndiceDipendenti(dipendenti)


def risolvi_codice_fiscale(riga: Dict[str, Any], indice: IndiceDipendenti) -> Optional[str]:
    """CF della riga: quello proprio, altrimenti quello risolto per nome univoco."""
    cf_proprio = str(riga.get("codice_fiscale") or "").strip().upper()
    if cf_proprio:
        return cf_proprio
    return indice.cf_per_nome(nome_riga_salario(riga))


def chiave_logica_riga(
    riga: Dict[str, Any], indice: IndiceDipendenti,
) -> Optional[ChiaveSalario]:
    """``(codice_fiscale, anno, mese, tipo_cedolino)`` canonico, o ``None``.

    ``None`` quando il CF non e' risolvibile (nessun dipendente con quel nome
    univoco in anagrafica) o quando anno/mese non sono leggibili: la riga
    resta visibile solo nei report, mai fusa "a caso" con un'altra.
    """
    cf = risolvi_codice_fiscale(riga, indice)
    if not cf:
        return None
    try:
        anno = int(riga.get("anno"))
        mese = int(riga.get("mese"))
    except (TypeError, ValueError):
        return None
    if anno < 2000 or not 1 <= mese <= 12:
        return None
    tipo = tipo_cedolino_canonico(riga.get("tipo_cedolino"))
    return cf, anno, mese, tipo


def righe_con_stessa_chiave(
    chiave: ChiaveSalario,
    righe: List[Dict[str, Any]],
    indice: IndiceDipendenti,
) -> List[Dict[str, Any]]:
    """Sottoinsieme di ``righe`` con la stessa identita' logica di ``chiave``."""
    return [riga for riga in righe if chiave_logica_riga(riga, indice) == chiave]


def punteggio_completezza(riga: Dict[str, Any]) -> Tuple[int, str]:
    """Quanto e' "autorevole" una riga: piu' campi di provenienza valorizzati
    vince; a parita' vince la piu' recente (``created_at``)."""
    punti = sum(
        1 for campo in ("codice_fiscale", "dipendente_id", "cedolino_id", "hr_cedolino_id")
        if riga.get(campo)
    )
    if riga.get("movimenti_bancari_ids"):
        punti += 1
    return punti, str(riga.get("created_at") or "")


def riga_piu_autorevole(righe: List[Dict[str, Any]]) -> Dict[str, Any]:
    """La riga da tenere in un gruppo di duplicati certi (stessa identita' E
    stesso importo atteso): piu' campi valorizzati, poi la piu' recente."""
    return max(righe, key=punteggio_completezza)


def importo_atteso_riga(riga: Dict[str, Any]) -> float:
    try:
        return round(float(riga.get("importo_busta") or riga.get("importo") or 0), 2)
    except (TypeError, ValueError):
        return 0.0
