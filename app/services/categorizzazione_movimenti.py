"""Motore unico di categorizzazione dei movimenti bancari da descrizione.

Prima del 19/09/2026 esistevano DUE funzioni con lo stesso nome
(`categorizza_movimento_bancario`), nessuna delle due collegata al vero
percorso di import (`app/routers/bank/estratto_conto.py`): una qui con il
commento "DA INTEGRARE", l'altra in `app/schemas/accounting_rules.py` con un
piano dei conti (4.3.01, 2.1.01, ...) diverso da quello ufficiale CEE
(`app/services/piano_conti_ufficiale.py`). Risultato: al 18/09/2026, 1.764 dei
1.920 movimenti bancari 2026 (92%) non avevano categoria.

Questo e' l'UNICO motore rimasto. Regole:

- Ritorna un valore SOLO dalla tassonomia operativa gia' in produzione
  (`CATEGORIE_BANCA` in `app/routers/prima_nota_module/common.py`), mai una
  tassonomia parallela: la riga scritta qui deve restare compatibile con
  `mappa_categoria_ec()` e con `entra_in_prima_nota()`.
- Categorizza SOLO quando il pattern e' una parola chiave/sigla non ambigua
  nella descrizione. Non associa mai per solo importo (CLAUDE.md, "Identita',
  prove e attese"): un bonifico che assomiglia a una fattura aperta per
  importo resta senza categoria, non diventa "Fatture" per quello.
- Non tocca gli Stipendi: quelli hanno gia' un motore proprio, piu' rigoroso
  di un controllo per parola chiave (`app/services/stipendi_bonifici.py`,
  nome completo + importo esatto + periodo + candidato univoco). Riprodurre
  qui un secondo riconoscimento stipendi via "ADD.TOT"/"VS.DISP" sarebbe
  esattamente il doppione che questo file elimina.
- Versamento/Prelevamento Banca, PayPal e rata del mutuo si riconoscono con
  gli stessi riconoscitori di `mappa_categoria_ec()` (non una seconda
  regola): il campo `categoria` salvato deve dirlo, o il banner di Prima Nota
  li conta come movimenti da classificare.
- In caso di piu' pattern non ambigui in conflitto sulla stessa descrizione,
  il movimento resta "ambiguo" (categoria None): non si sceglie a caso.

Il riconoscimento del codice tributo F24 riusa i cataloghi ufficiali in
`app/schemas/accounting_rules.py` (F24_ERARIO_CODES, F24_INPS_CODES): stesso
registro versionato usato dal parser dei modelli F24, non un secondo elenco.

**Regole imparate (19/09/2026)**: prima di queste parole chiave generiche,
`categorizza_movimento_bancario` controlla le regole che il titolare ha
salvato a mano (`app.services.regole_riconoscimento_banca`, es. "questo e' di
Nexi" su una causale che il motore da solo chiamerebbe solo "Commissioni
bancarie"). Una regola imparata vince sempre: e' una scelta esplicita del
titolare, piu' specifica di una parola chiave generica. Il chiamante prefetcha
le regole una sola volta (mai una query per movimento) e le passa con il
parametro `regole`.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ============================================================================
# RICONOSCIMENTO
# ============================================================================

# F24: la sigla "F24" (o le varianti sotto) in causale bancaria non ha altro
# significato possibile. Il codice tributo, se presente, arricchisce il
# dettaglio ma non e' condizione: anche "ADDEBITO F24 IVA E RITENUTE" senza
# codice esplicito e' inequivocabilmente un F24.
_F24_KEYWORDS = (
    "F24", "F 24", "MOD.F24", "MOD F24", "DELEGA F24",
    "I24 AGENZIA ENTRATE", "PAGAMENTO F24", "VERSAMENTO F24",
)

# Spese/competenze bancarie: rientrano fra le "categorie bancarie senza
# documento" (CATEGORIE_SENZA_DOCUMENTO) — la banca stessa e' la prova, non
# esiste una fattura a cui agganciarle. Parole intere o sigle specifiche:
# mai "BOLLO" da solo (si confonderebbe col bollo auto/verbali). "COMM.SU" /
# "COMM.SDD" / "SPESE E COMM" e "IMP.BOLLO" sono le abbreviazioni reali della
# banca (BPM), trovate leggendo le causali vere del 2026: senza queste sigle
# il motore riconosceva solo 150 dei 1.764 movimenti 2026 senza categoria,
# con queste 344 (verificato il 19/09/2026 sul progetto Supabase di
# produzione, sola lettura prima di scrivere).
_COMMISSIONI_KEYWORDS = (
    "COMMISSIONI", "COMMISSIONE", "COMM.SU", "COMM.SDD", "COMM.BON", "SPESE E COMM",
    "SPESE BANCARIE", "SPESE TENUTA CONTO",
    "CANONE CONTO", "CANONE MENSILE C/C", "CANONE TRIMESTRALE C/C",
    "IMPOSTA DI BOLLO", "IMPOSTA BOLLO", "IMP.BOLLO", "I.BOLLO", "BOLLO C/C",
    "INTERESSI PASSIVI", "INT.PASSIVI", "INTERESSI DEBITORI", "INT.DEB",
    "COMPETENZE TRIMESTRALI", "COMPETENZE BANCARIE",
    # Le stesse sigle come le scrive il vecchio archivio 2026 (verificato il
    # 28/09/2026 sulle righe ancora senza categoria): con lo spazio, o per
    # esteso sul carnet e sul canone della carta di debito.
    "COMM. BON", "COMM.FISSA", "RILASCIO CARNET", "IMP. BOLLO", "CANONE CARTA",
)

# Utenze: marchi/fornitori di energia, gas, telefonia, acqua non ambigui.
# "UTENZ*" generico e "PAG. UTENZE" sono gia' riconosciuti da
# `mappa_categoria_ec()` a prescindere da questo modulo.
_UTENZE_KEYWORDS = (
    "ENEL", "ENI GAS", "ENI SPA", "A2A", "EDISON", "SORGENIA", "HERA SPA",
    "ACEA", "IREN", "TELECOM ITALIA", "TIM", "TIM SPA", "VODAFONE",
    "WINDTRE", "WIND TRE", "FASTWEB", "ACQUEDOTTO",
)

# Fatture fornitore: solo un riferimento testuale esplicito a una fattura, mai
# il generico "BONIFICO" (lo userebbe qualsiasi bonifico in uscita). Include
# anche assicurazioni e canoni di locazione, che in azienda viaggiano sempre
# con fattura periodica del fornitore/assicuratore — stessa convenzione gia'
# in uso in `_CATEGORIE_EC_PREFISSI` (estratto_conto.py) per la tassonomia
# bancaria: "Assicurazione" e "Altre passivita' - Leasing" -> "Fatture".
_FATTURE_KEYWORDS = (
    "SALDO FATTURA", "SALDO FT", "PAGAM.FATT", "PAGAMENTO FATTURA",
    "PAGAMENTO FORNITORE", "ADD. FATT", "ADD.FATT",
    "ASSICURAZ", "POLIZZA", "PREMIO ASSICURATIVO",
    "CANONE LOCAZIONE", "AFFITTO", "LOCAZIONE UFFICIO", "LOCAZIONE NEGOZIO",
)

# Causali della banca che non lasciano dubbi, verificate il 27/09/2026 sul
# CSV «Elenco entrate/uscite» del titolare (1.943 righe 2026: ogni riga con
# queste causali ha la stessa categoria della banca). Il vecchio archivio le
# scrive senza categoria, e il banner di Prima Nota le contava come «da
# classificare» anche se la causale diceva gia' tutto.
_POS_KEYWORDS = (
    "INC.POS CARTE CREDIT", "INCAS. TRAMITE P.O.S", "INCAS.TRAMITE P.O.S",
    "INCASSO TRAMITE POS",
)
_ASSEGNI_KEYWORDS = ("PRELIEVO ASSEGNO", "VOSTRO ASSEGNO", "ADDEBITO ASSEGNO")

# Decisioni del titolare del 28/09/2026 sulle causali ancora senza categoria.
# «BOLL.CBILL AGENZIA DELLE ENTRATE - R»: rate di cartelle e avvisi pagate col
# circuito CBILL (la «R» e' la riscossione), non un F24.
_RATEIZZAZIONI_ADE_KEYWORDS = ("CBILL AGENZIA DELLE ENTRATE",)
# «BOLL.CBILL REGIONE CAMPANIA»: la tassa automobilistica.
_TASSA_AUTO_KEYWORDS = ("CBILL REGIONE CAMPANIA",)
# Il saldo mensile della carta di credito aziendale: un giroconto verso la
# carta, non un costo; i costi sono le spese dell'estratto Nexi.
# «ADDEBITO NEXI - SDD CORE: … NEXI PAYMENTS S.P.A.» e' lo stesso fatto visto
# dall'altro lato (titolare, 01/10/2026): l'addebito mensile della carta. Il
# riscontro con l'estratto Nexi lo fa `nexi_carta.verifica_addebiti_nexi`.
_CARTA_CREDITO_KEYWORDS = ("SPESA CON CARTA DI CREDITO NEXI", "ADDEBITO NEXI")

_PATTERN_BUCKETS: Dict[str, tuple] = {
    "F24": _F24_KEYWORDS,
    "Commissioni bancarie": _COMMISSIONI_KEYWORDS,
    "Utenze": _UTENZE_KEYWORDS,
    "Fatture": _FATTURE_KEYWORDS,
    "Corrispettivi POS": _POS_KEYWORDS,
    "Assegni": _ASSEGNI_KEYWORDS,
    "Rateizzazioni AdE": _RATEIZZAZIONI_ADE_KEYWORDS,
    "Tassa automobilistica": _TASSA_AUTO_KEYWORDS,
    "Addebito carta di credito": _CARTA_CREDITO_KEYWORDS,
}

# Entrate che non sono ricavi (titolare, 28/09/2026). Il rimborso di un
# fornitore (nota di credito, reso Amazon, bonifico errato restituito) e il
# denaro di un cliente per una torta ordinata: il ricavo della torta e' lo
# scontrino del giorno del ritiro, l'acconto non lo anticipa.
_RE_RIMBORSO_ENTRATA = re.compile(r"\bRIMBORS|\bRESTITUZION|\bAMAZON\b")
_RE_ACCONTO_CLIENTE = re.compile(r"\bTORT[AE]\b")

# Il vecchio archivio scrive l'accredito POS senza prefisso: «NUMIA-INTER DEL
# 30/08/26 PDV …». Solo con il circuito e il giorno: «FATTURA NUMIA» e le
# commissioni del gestore non sono un incasso.
_RE_ACCREDITO_POS = re.compile(r"\bNUMIA-[A-Z]+\s+DEL\s+\d{2}/\d{2}/\d{2}|\bREMUNERAZIONE\s+DCC\b")
# Giroconto fra conti della stessa societa' (titolare, 01/10/2026): la causale lo
# dice da sola («Giroconto da Mastercard SumUp», «BON.DA ceraldi group srl
# Giroconto»): non e' un incasso ne' un costo e non ha un fornitore.
_RE_GIROCONTO = re.compile(
    r"\bGIROCONTO\b|\bMASTERCARD\s+SUMUP\b|\bBON\.?\s*DA\s+CERALDI\s+GROUP\b")
_RE_RATA_MUTUO = re.compile(r"\bMUTUO\s+N\.?\s*\d{3,5}[\s/]+[\d/]{5,}\s+RATA\b")


def _categorie_da_causale(desc: str) -> List[str]:
    """Le categorie che la causale dichiara da sola, con gli stessi
    riconoscitori di Prima Nota (versamento, prelievo, PayPal, rata mutuo):
    uno storno di versamento non e' un versamento."""
    from app.routers.bank.estratto_conto import (
        is_prelievo_contanti, is_storno_versamento, is_versamento_contanti,
    )

    trovate = []
    if is_storno_versamento(desc):
        return trovate
    if is_versamento_contanti(desc):
        trovate.append("Versamento Banca")
    if is_prelievo_contanti(desc):
        trovate.append("Prelevamento Banca")
    if re.search(r"\bPAYPAL\b", desc):
        trovate.append("Pagamento PayPal")
    if _RE_RATA_MUTUO.search(desc):
        trovate.append("Rata mutuo")
    if _RE_GIROCONTO.search(desc):
        trovate.append("Giroconto")
    # «COMPETENZE» da sola e' la liquidazione trimestrale del conto; con altre
    # parole (es. «competenze agosto» in un bonifico) puo' essere uno stipendio.
    if desc.strip() == "COMPETENZE":
        trovate.append("Commissioni bancarie")
    if _RE_ACCREDITO_POS.search(desc) and not any(
        _kw_presente(desc, kw) for kw in _POS_KEYWORDS
    ):
        trovate.append("Corrispettivi POS")
    return trovate

# Codici tributo: stesso registro del parser F24 (nessun secondo elenco).
from app.schemas.accounting_rules import F24_ERARIO_CODES, F24_INPS_CODES  # noqa: E402

_RE_CODICE_ERARIO = re.compile(r"\b([2-6]\d{3})\b")
_RE_CODICE_INPS = re.compile(r"\b(DM\d{2})\b")


def _kw_presente(desc: str, kw: str) -> bool:
    """Cerca la parola chiave rispettando i confini di parola: una sigla
    corta come "IREN" o "ACEA" non deve accendersi dentro "IRENE" o
    "PANACEA SRL" (audit 19/09/2026, verificato: non ancora accaduto sui
    dati reali, ma un rischio latente con un semplice `kw in desc`)."""
    return re.search(r"\b" + re.escape(kw.strip()) + r"\b", desc) is not None


@dataclass(frozen=True)
class EsitoCategorizzazione:
    """Esito del riconoscimento per un singolo movimento."""

    categoria: Optional[str]        # uno dei valori di CATEGORIE_BANCA, o None
    motivo: str                     # spiegazione breve, per audit/report
    codice_tributo: Optional[str] = None
    ambiguo: bool = False
    # Valorizzati solo quando il riconoscimento viene da una regola imparata
    # (`app.services.regole_riconoscimento_banca`) con entita_tipo="fornitore".
    fornitore_id: Optional[str] = None
    fornitore_nome: Optional[str] = None
    regola_id: Optional[str] = None


def _codice_tributo(descrizione_upper: str) -> Optional[str]:
    """Codice tributo F24, se riconosciuto nel registro ufficiale."""
    match_erario = _RE_CODICE_ERARIO.search(descrizione_upper)
    if match_erario and match_erario.group(1) in F24_ERARIO_CODES:
        return match_erario.group(1)
    match_inps = _RE_CODICE_INPS.search(descrizione_upper)
    if match_inps and match_inps.group(1) in F24_INPS_CODES:
        return match_inps.group(1)
    return None


def _esito_da_regola_appresa(regola: Dict[str, Any]) -> EsitoCategorizzazione:
    entita_tipo = regola.get("entita_tipo")
    nome = regola.get("entita_nome") or regola.get("entita_id") or "?"
    motivo = f"regola imparata: pattern '{regola.get('pattern')}' -> {entita_tipo} {nome}"
    return EsitoCategorizzazione(
        categoria=regola.get("categoria") or None,
        motivo=motivo,
        fornitore_id=regola.get("entita_id") if entita_tipo == "fornitore" else None,
        fornitore_nome=regola.get("entita_nome") if entita_tipo == "fornitore" else None,
        regola_id=regola.get("id"),
    )


def categorizza_movimento_bancario(
    descrizione: Optional[str], importo: float = 0.0,
    regole: Optional[List[Dict[str, Any]]] = None,
) -> EsitoCategorizzazione:
    """Riconosce la categoria di un movimento bancario dalla sola descrizione.

    Non associa mai per importo: `importo` resta nella firma solo perche' i
    chiamanti gia' lo passano (compatibilita' con l'uso storico) ma non entra
    in nessuna condizione di riconoscimento.

    `regole`: le regole imparate dal titolare (`app.services
    .regole_riconoscimento_banca.carica_regole`), gia' prefetchate dal
    chiamante. Controllate PRIMA delle parole chiave generiche sotto: vincono
    sempre, sono una scelta esplicita, non un'euristica.
    """
    desc = (descrizione or "").upper()
    if not desc.strip():
        return EsitoCategorizzazione(None, "descrizione assente")

    if regole:
        from app.services.regole_riconoscimento_banca import trova_regola_per_descrizione

        regola = trova_regola_per_descrizione(regole, desc)
        if regola is not None:
            return _esito_da_regola_appresa(regola)

    trovati = [
        nome for nome, keywords in _PATTERN_BUCKETS.items()
        if any(_kw_presente(desc, kw) for kw in keywords)
    ] + _categorie_da_causale(desc)
    # «COMMISSIONI - Comm.sdd ... PayPal» e' una commissione: la parola
    # della commissione vince sul nome del circuito che la cita.
    if "Commissioni bancarie" in trovati and "Pagamento PayPal" in trovati:
        trovati.remove("Pagamento PayPal")

    if len(trovati) > 1:
        return EsitoCategorizzazione(
            None, f"ambiguo: corrisponde a piu' categorie ({', '.join(sorted(trovati))})",
            ambiguo=True,
        )
    if not trovati:
        return EsitoCategorizzazione(None, "nessun pattern non ambiguo riconosciuto")

    categoria = trovati[0]
    if categoria == "F24":
        codice = _codice_tributo(desc)
        motivo = (
            f"parola chiave F24 + codice tributo {codice}" if codice
            else "parola chiave F24 in descrizione"
        )
        return EsitoCategorizzazione("F24", motivo, codice_tributo=codice)

    kw_match = next(
        (kw for kw in _PATTERN_BUCKETS.get(categoria, ()) if _kw_presente(desc, kw)), None,
    )
    if kw_match is None:
        return EsitoCategorizzazione(categoria, "causale bancaria")
    return EsitoCategorizzazione(categoria, f"parola chiave '{kw_match.strip()}'")


# ============================================================================
# BACKFILL — movimenti gia' importati senza categoria
# ============================================================================

_STATO_KEY = "backfill_categorie_banca"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def categoria_dal_collegamento(mov: Dict[str, Any]) -> Optional[str]:
    """La categoria che un abbinamento gia' fatto rende certa: un movimento
    collegato a una fattura paga una fattura, uno collegato a un dipendente e'
    uno stipendio. Collegato a entrambi, o a nessuno, non si decide qui; e
    nemmeno un'entrata (un rimborso del fornitore non e' un pagamento)."""
    tipo = str(mov.get("tipo") or "").lower()
    try:
        importo = float(mov.get("importo") or 0)
    except (TypeError, ValueError):
        importo = 0.0
    # CSV e banca diretta: importo positivo e verso in `tipo`; vecchio
    # archivio: importo con segno.
    uscita = tipo == "uscita" or (not tipo and importo < 0)
    # Il socio lo attribuisce `finanziamenti_soci.classifica_finanziamento_ec`,
    # che gia' esige nome completo del socio e, in uscita, causale di rimborso.
    if mov.get("socio_id"):
        return "Finanziamento soci"
    if not uscita:
        return None
    ha_fattura = bool(mov.get("fattura_id") or mov.get("fattura_ids"))
    ha_dipendente = bool(mov.get("dipendente_id"))
    if ha_fattura and not ha_dipendente:
        return "Fatture"
    if ha_dipendente and not ha_fattura:
        return "Stipendi"
    return None


def categoria_entrata(mov: Dict[str, Any]) -> Optional[str]:
    """Rimborso di un fornitore o acconto di un cliente: solo sulle entrate,
    perche' «RIMBORSO» in uscita e' il contrario (lo restituiamo noi)."""
    tipo = str(mov.get("tipo") or "").lower()
    try:
        importo = float(mov.get("importo") or 0)
    except (TypeError, ValueError):
        importo = 0.0
    if not (tipo == "entrata" or (not tipo and importo > 0)):
        return None
    desc = str(mov.get("descrizione_originale") or mov.get("descrizione") or "").upper()
    acconto = bool(_RE_ACCONTO_CLIENTE.search(desc))
    rimborso = bool(_RE_RIMBORSO_ENTRATA.search(desc))
    if acconto and not rimborso:
        return "Acconti clienti"
    if rimborso and not acconto:
        return "Rimborso"
    return None


async def _movimenti_senza_categoria(db, anno: Optional[int]) -> List[Dict[str, Any]]:
    query: Dict[str, Any] = {
        "$or": [
            {"categoria": None}, {"categoria": ""},
            {"categoria": {"$exists": False}},
        ],
        # Audit 19/09/2026 su PR #500: un fornitore gia' assegnato viene da
        # un'identita' piu' certa (P.IVA/IBAN) di un pattern imparato sulla
        # sola descrizione. CLAUDE.md, "Identita', prove e attese": una
        # relazione certa non si sovrascrive con una meno certa.
        "fornitore_id": {"$exists": False},
    }
    if anno:
        query["data"] = {"$regex": f"^{anno}"}
    return await db["estratto_conto_movimenti"].find(
        query,
        {"_id": 0, "id": 1, "descrizione_originale": 1, "descrizione": 1,
         "importo": 1, "data": 1, "tipo": 1, "fattura_id": 1, "fattura_ids": 1,
         "dipendente_id": 1, "socio_id": 1},
    ).to_list(20000)


async def backfill_categorie_banca(
    db, *, anno: Optional[int] = 2026, dry_run: bool = False,
    on_progress=None, con_stipendi: bool = True,
) -> Dict[str, Any]:
    """Valorizza `categoria` sui movimenti gia' importati, SOLO dove il
    riconoscimento e' certo. Non tocca i movimenti che hanno gia' una
    categoria (dal CSV bancario o da una riconciliazione precedente).

    Ordine:
    1. Motore stipendi esistente (`associa_bonifici_stipendi`): nome
       completo + importo esatto + periodo, non un controllo per parola
       chiave — resta l'unico sistema per gli Stipendi.
    2. Questo motore per parola chiave (F24, Commissioni bancarie, Utenze,
       Fatture) sui movimenti ancora senza categoria dopo il passo 1.

    Con `dry_run=True` non scrive nulla: il passo 1 viene saltato (il motore
    stipendi non ha una modalita' di sola simulazione) e il report copre solo
    il passo 2, dichiarandolo nel risultato.
    """
    stipendi_esito: Optional[Dict[str, Any]] = None
    if not dry_run and con_stipendi:
        try:
            from app.services.stipendi_bonifici import associa_bonifici_stipendi
            stipendi_esito = await associa_bonifici_stipendi(db, anno=anno)
        except Exception as exc:  # noqa: BLE001 - non deve bloccare il resto
            logger.exception("Motore stipendi non completato durante il backfill categorie")
            stipendi_esito = {"errore": str(exc)}

    movimenti = await _movimenti_senza_categoria(db, anno)
    totale = len(movimenti)

    from app.services.regole_riconoscimento_banca import carica_regole
    regole = await carica_regole(db)

    per_categoria: Dict[str, List[str]] = {}
    per_collegamento: Dict[str, List[str]] = {}
    # Movimenti presi da una regola imparata: motivo e (forse) fornitore
    # variano per regola, quindi si raggruppano a parte dal generico per
    # parola chiave (che ha sempre lo stesso motivo/fornitore=nessuno).
    per_regola: Dict[tuple, List[str]] = {}
    dettaglio_f24: Dict[str, str] = {}
    non_riconosciuti = 0
    ambigui = 0
    campioni_non_riconosciuti: List[Dict[str, Any]] = []

    for indice, mov in enumerate(movimenti, start=1):
        descrizione = mov.get("descrizione_originale") or mov.get("descrizione") or ""
        dal_collegamento = categoria_dal_collegamento(mov) or categoria_entrata(mov)
        if dal_collegamento:
            per_collegamento.setdefault(dal_collegamento, []).append(mov["id"])
            continue
        esito = categorizza_movimento_bancario(descrizione, mov.get("importo") or 0, regole=regole)
        if esito.categoria or esito.fornitore_id:
            if esito.regola_id:
                chiave = (esito.categoria, esito.fornitore_id, esito.fornitore_nome, esito.motivo)
                per_regola.setdefault(chiave, []).append(mov["id"])
            elif esito.categoria:
                per_categoria.setdefault(esito.categoria, []).append(mov["id"])
            if esito.codice_tributo:
                dettaglio_f24[mov["id"]] = esito.codice_tributo
        else:
            if esito.ambiguo:
                ambigui += 1
            else:
                non_riconosciuti += 1
            if len(campioni_non_riconosciuti) < 20:
                campioni_non_riconosciuti.append({
                    "id": mov.get("id"),
                    "data": mov.get("data"),
                    "importo": mov.get("importo"),
                    "descrizione": descrizione[:120],
                    "motivo": esito.motivo,
                })
        if on_progress and indice % 200 == 0:
            await on_progress(indice, totale)

    aggiornati = 0
    da_fattura = {"assegnati": 0}
    if not dry_run:
        from app.services.fornitore_da_fattura_banca import assegna_fornitori_da_fatture
        ids_riconosciuti = {i for ids in per_categoria.values() for i in ids}
        ids_riconosciuti.update(i for ids in per_collegamento.values() for i in ids)
        ids_riconosciuti.update(i for ids in per_regola.values() for i in ids)
        restanti = [m for m in movimenti if m.get("id") not in ids_riconosciuti]
        try:
            da_fattura = await assegna_fornitori_da_fatture(db, restanti)
        except Exception as exc:  # noqa: BLE001 - il resto del backfill prosegue
            logger.warning("Fornitore da fattura non letto (%s)", type(exc).__name__)
        aggiornati += da_fattura["assegnati"]
        non_riconosciuti = max(0, non_riconosciuti - da_fattura["assegnati"])
    if not dry_run:
        now_iso = _now()
        for categoria, ids in per_categoria.items():
            if not ids:
                continue
            await db["estratto_conto_movimenti"].update_many(
                {"id": {"$in": ids}},
                {"$set": {
                    "categoria": categoria,
                    "categoria_auto": True,
                    "categoria_auto_motivo": "parola chiave non ambigua (backfill 19/09/2026)",
                    "categoria_auto_at": now_iso,
                }},
            )
            aggiornati += len(ids)
        for categoria, ids in per_collegamento.items():
            await db["estratto_conto_movimenti"].update_many(
                {"id": {"$in": ids}},
                {"$set": {
                    "categoria": categoria,
                    "categoria_auto": True,
                    "categoria_auto_motivo": "abbinamento gia' fatto (fattura, dipendente, socio) o entrata riconosciuta (rimborso, acconto)",
                    "categoria_auto_at": now_iso,
                }},
            )
            aggiornati += len(ids)
        for (categoria, fornitore_id, fornitore_nome, motivo), ids in per_regola.items():
            if not ids:
                continue
            campi: Dict[str, Any] = {
                "categoria_auto": True,
                "categoria_auto_motivo": motivo,
                "categoria_auto_at": now_iso,
            }
            if categoria:
                campi["categoria"] = categoria
            if fornitore_id:
                campi["fornitore_id"] = fornitore_id
                campi["fornitore"] = fornitore_nome
            await db["estratto_conto_movimenti"].update_many(
                {"id": {"$in": ids}}, {"$set": campi},
            )
            aggiornati += len(ids)
        for mov_id, codice in dettaglio_f24.items():
            await db["estratto_conto_movimenti"].update_one(
                {"id": mov_id}, {"$set": {"categoria_codice_tributo": codice}},
            )

    per_categoria_totale: Dict[str, int] = {cat: len(ids) for cat, ids in per_categoria.items()}
    for cat, ids in per_collegamento.items():
        per_categoria_totale[cat] = per_categoria_totale.get(cat, 0) + len(ids)
    for (categoria, _fid, _fnome, _motivo), ids in per_regola.items():
        if categoria:
            per_categoria_totale[categoria] = per_categoria_totale.get(categoria, 0) + len(ids)

    return {
        "success": True,
        "dry_run": dry_run,
        "anno": anno,
        "stipendi": stipendi_esito,
        "movimenti_esaminati": totale,
        "per_categoria": per_categoria_totale,
        "da_regola_appresa": sum(len(ids) for ids in per_regola.values()),
        "da_fattura": da_fattura["assegnati"],
        "aggiornati": aggiornati,
        "non_riconosciuti": non_riconosciuti,
        "ambigui": ambigui,
        "non_categorizzati_totale": non_riconosciuti + ambigui,
        "campioni_non_categorizzati": campioni_non_riconosciuti,
    }


async def stato_backfill_categorie_banca(db) -> Dict[str, Any]:
    stato = await db["sistema_stato"].find_one({"chiave": _STATO_KEY}, {"_id": 0}) or {}
    stato.pop("chiave", None)
    return stato


async def _salva_stato_backfill(db, **campi: Any) -> None:
    campi["aggiornato_at"] = _now()
    await db["sistema_stato"].update_one(
        {"chiave": _STATO_KEY}, {"$set": campi}, upsert=True,
    )


_backfill_in_corso = False


def backfill_in_corso() -> bool:
    return _backfill_in_corso


async def _backfill_in_background(db, anno: Optional[int]) -> None:
    global _backfill_in_corso
    _backfill_in_corso = True
    await _salva_stato_backfill(db, stato="in_corso", avviato_at=_now(), risultato=None, errore=None)

    async def progresso(fatti: int, totale: int) -> None:
        await _salva_stato_backfill(db, avanzamento={"fatti": fatti, "totale": totale})

    try:
        risultato = await backfill_categorie_banca(db, anno=anno, dry_run=False, on_progress=progresso)
        await _salva_stato_backfill(
            db, stato="completato", terminato_at=_now(),
            risultato={k: v for k, v in risultato.items() if k != "success"},
        )
    except Exception as exc:  # noqa: BLE001 - lo stato deve restare leggibile
        logger.exception("Backfill categorie banca interrotto")
        await _salva_stato_backfill(db, stato="errore", errore=str(exc), terminato_at=_now())
    finally:
        _backfill_in_corso = False


def avvia_backfill_in_background(db, anno: Optional[int] = 2026) -> bool:
    """Come `registrazione_contabile.avvia_pregresso_in_background`: risponde
    subito, lo stato si segue con `stato_backfill_categorie_banca`."""
    import asyncio
    if _backfill_in_corso:
        return False
    asyncio.create_task(_backfill_in_background(db, anno))
    return True
