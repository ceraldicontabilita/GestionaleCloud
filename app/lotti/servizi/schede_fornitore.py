"""Schede tecniche dei fornitori: il PDF originale, gli allergeni, i valori nutrizionali.

Per un controllo ASL ogni prodotto acquistato deve poter esibire la scheda del
produttore. ME.PA. Alimentari le manda per posta da ``noreply@ordersender.biz``
(«Mepa - Scheda prodotto cod. articolo IRCA089», corpo «… del prodotto IRCA089 -
IRCA CACAO 22/24 CF 1 KG (CT 10CF)»). La descrizione dopo il codice è **la
stessa** della riga in fattura: è la chiave che lega scheda, fattura, lotto e
articolo (``articoli_fattura.chiave_descrizione``), senza somiglianze.

Il downloader unico (``email_full_download``) salva il PDF come ogni allegato
(SHA-256, dedup) e chiama :func:`registra_scheda_tecnica`. Qui si legge il
testo e si estraggono allergeni e valori nutrizionali **solo se scritti**: un
valore assente resta vuoto e la scheda è marcata ``da_verificare``, mai
riempita con un numero plausibile.
"""
from __future__ import annotations

import html
import quopri
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.lotti.servizi.articoli_fattura import chiave_descrizione

__all__ = [
    "ALLERGENI_UE",
    "FORNITORE_MEPA",
    "FONTE_EMAIL_FORNITORE",
    "testo_corpo",
    "estrai_codice_e_descrizione",
    "leggi_allergeni",
    "leggi_valori_nutrizionali",
    "leggi_metadati_tecnici",
    "registra_scheda_tecnica",
    "allergeni_da_schede",
    "completa_allergeni_con_schede",
]

FORNITORE_MEPA = "ME.PA. ALIMENTARI S.R.L."
#: ``fonte`` delle schede arrivate per posta dal fornitore: l'originale per
#: l'ASL, che il salvataggio manuale di un link non sovrascrive.
FONTE_EMAIL_FORNITORE = "email_fornitore"

#: I 14 allergeni del Reg. UE 1169/2011, con gli id usati dalle etichette di
#: Lotti (``routers/utils._ALLERGENI_KEYS``) e i nomi con cui compaiono nelle
#: schede dei produttori.
ALLERGENI_UE: Dict[str, List[str]] = {
    "glutine": ["glutine", "cereali contenenti glutine", "frumento", "grano", "orzo", "segale", "avena", "farro", "kamut"],
    "crostacei": ["crostacei"],
    "uova": ["uova", "uovo", "ovoprodotti"],
    "pesce": ["pesce", "pesci"],
    "arachidi": ["arachidi", "arachide"],
    "soia": ["soia", "soja"],
    "latte": ["latte", "lattosio", "prodotti a base di latte", "derivati del latte"],
    "frutta_guscio": ["frutta a guscio", "frutta in guscio", "mandorle", "nocciole", "noci", "pistacchi",
                      "anacardi", "noci pecan", "noci del brasile", "noci macadamia"],
    "sedano": ["sedano"],
    "senape": ["senape"],
    "sesamo": ["sesamo", "semi di sesamo"],
    "solfiti": ["solfiti", "anidride solforosa"],
    "lupini": ["lupini", "lupino"],
    "molluschi": ["molluschi"],
}

_SI = r"(?:s[iì]|yes|presente|contiene|present)"
_NO = r"(?:no|assente|absent|non presente)"


def _pulisci(testo: str) -> str:
    return re.sub(r"[ \t]+", " ", (testo or "").replace("\r", "")).lower()


def _trova_allergeni(testo: str) -> List[str]:
    trovati: List[str] = []
    for aid, nomi in ALLERGENI_UE.items():
        for nome in nomi:
            if re.search(rf"(?<![a-zà-ù]){re.escape(nome)}(?![a-zà-ù])", testo):
                trovati.append(aid)
                break
    return trovati


def _sezione_ingredienti(testo: str) -> str:
    """Restituisce solo la dichiarazione ingredienti, fermandosi al titolo dopo.

    Nei PDF reali i titoli sono spesso numerati (``7 Ingredienti``, ``9
    Allergeni``). Una regex libera finiva per includere l'intera tabella degli
    allergeni e trasformava tutte le sue etichette in ingredienti presenti.
    """
    righe = testo.splitlines()
    raccolte: list[str] = []
    dentro = False
    stop = re.compile(
        r"^\s*(?:\d+\s+)?(?:allergeni|cross contamination|modalit[aà]|caratteristiche|packaging|"
        r"conservazione|parametri|dichiarazione nutrizionale|valori nutrizionali|etichettatura|imballaggio|"
        r"(?:il prodotto\s+)?pu[oò] contenere)\b",
        re.I,
    )
    start = re.compile(r"^\s*(?:\d+\s+)?(?:ingredienti|composizione merceologica|composition)\b", re.I)
    for riga in righe:
        if not dentro:
            if not start.search(riga) or re.search(r"ingredienti\s*/\s*allergeni", riga, re.I):
                continue
            dentro = True
            coda = re.sub(start, "", riga, count=1).lstrip(" :.-")
            if coda:
                raccolte.append(coda)
            continue
        if stop.search(riga):
            break
        # ``8 Composizione`` continua la stessa dichiarazione.
        if re.match(r"^\s*\d+\s+composizione\b", riga, re.I):
            continue
        raccolte.append(riga)
        if len(raccolte) >= 40 or sum(map(len, raccolte)) >= 1800:
            break
    return "\n".join(raccolte)


def _blocco_esplicito(testo: str, start: str, stop: str, *, max_righe: int = 12) -> Optional[str]:
    """Legge un blocco etichettato senza completarlo con dati dedotti."""
    righe = (testo or "").replace("\r", "").splitlines()
    raccolte: list[str] = []
    dentro = False
    rx_start = re.compile(start, re.I)
    rx_stop = re.compile(stop, re.I)
    for riga in righe:
        pulita = re.sub(r"\s+", " ", riga).strip()
        if not dentro:
            if not rx_start.search(pulita):
                continue
            dentro = True
            coda = rx_start.sub("", pulita, count=1).lstrip(" :.-–—")
            if coda:
                raccolte.append(coda)
            continue
        if raccolte and rx_stop.search(pulita):
            break
        if pulita:
            raccolte.append(pulita)
        if len(raccolte) >= max_righe or sum(map(len, raccolte)) >= 1800:
            break
    valore = "\n".join(raccolte).strip()
    return valore or None


def leggi_metadati_tecnici(testo_pdf: str) -> Dict[str, Optional[str]]:
    """Metadati dichiarati nella scheda, come testo originale verificabile.

    I layout dei produttori non sono uniformi. Questa funzione riconosce solo
    intestazioni esplicite e non ricava produttore, durata o confezione dal nome
    del file o da conoscenze esterne.
    """
    testo = (testo_pdf or "").replace("\r", "")
    stop_comune = (
        r"^(?:\d+\s+)?(?:caratteristiche|allergeni|valori nutrizionali|dichiarazione nutrizionale|"
        r"conservazione|condizioni di conservazione|modalit[aà].*conservazione|confezione|packaging|"
        r"imballaggio|utilizzo|dosaggio|informazioni prodotto)\b"
    )
    composizione = _sezione_ingredienti(testo) or _blocco_esplicito(
        testo, r"^(?:\d+\s+)?composizione merceologica\b", stop_comune)
    conservazione = _blocco_esplicito(
        testo,
        r"^(?:\d+\s+)?(?:condizioni di conservazione|modalit[aà].*conservazione|conservazione)\b",
        r"^(?:\d+\s+)?(?:imballaggio|packaging|confezione|allergeni|ingredienti|valori nutrizionali|"
        r"dichiarazione nutrizionale|caratteristiche|etichettatura)\b",
        max_righe=10,
    )
    shelf_life = _blocco_esplicito(
        testo,
        r"^(?:\d+\s+)?(?:t\.m\.c\.?\s*/?\s*shelf\s*life|shelf\s*-?\s*life|conservabilit[aà]|"
        r"termine minimo di conservazione|durata di conservazione)\b",
        r"^(?:\d+\s+)?(?:imballaggio|packaging|confezione|allergeni|ingredienti|valori nutrizionali|"
        r"dichiarazione nutrizionale|caratteristiche|etichettatura)\b",
        max_righe=6,
    )
    confezionamento = _blocco_esplicito(
        testo,
        r"^(?:\d+\s+)?(?:imballaggio(?:\s*-\s*pallettizzazione)?|packaging(?: information)?|"
        r"confezione|confezionamento)\b",
        r"^(?:\d+\s+)?(?:conservazione|condizioni di conservazione|shelf\s*-?\s*life|allergeni|"
        r"ingredienti|valori nutrizionali|dichiarazione nutrizionale|caratteristiche)\b",
        max_righe=10,
    )

    produttore = None
    for riga in testo.splitlines()[:80]:
        pulita = re.sub(r"\s+", " ", riga).strip(" .")
        if re.search(r"\b(?:s\.\s*p\.\s*a\.?|s\.\s*r\.\s*l\.?)\b", pulita, re.I) \
                and not re.search(r"societ[aà] soggetta|cap\. soc", pulita, re.I):
            produttore = pulita[:240]
            break

    revisione = None
    for pattern in (
        r"(?im)^\s*((?:rev(?:isione)?\.?|versione)\s*[:.]?\s*[A-Z0-9.]+(?:\s+(?:del|data|dd)\s*:?\s*\d{1,2}[./-]\d{1,2}[./-]\d{2,4})?)",
        r"(?im)^\s*(Mod\.[^\n]{0,80}\bRev\.?\s*[A-Z0-9.]+[^\n]{0,40})$",
    ):
        m = re.search(pattern, testo)
        if m:
            revisione = re.sub(r"\s+", " ", m.group(1)).strip()
            break

    data_documento = None
    m = re.search(r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})\b", revisione or "")
    if not m:
        m = re.search(
            r"(?im)\b(?:approvata?[^\n]{0,25}\bin data|stampato il|agg\.?)\s*:?\s*"
            r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})\b",
            testo,
        )
    if m:
        data_documento = m.group(1)

    return {
        "produttore_dichiarato": produttore,
        "composizione_dichiarata": composizione,
        "conservazione_dichiarata": conservazione,
        "shelf_life_dichiarata": shelf_life,
        "confezionamento_dichiarato": confezionamento,
        "revisione_dichiarata": revisione,
        "data_documento_dichiarata": data_documento,
    }


def testo_corpo(corpo: str) -> str:
    """Il corpo della mail come testo semplice.

    Order Sender manda la parte testo **ancora** in quoted-printable (``=0A``,
    ``=09``, a capo morbidi ``=`` a fine riga) e la parte HTML con le entità
    (``HOPLA&#39;``): senza decodifica la descrizione non coincide con la riga
    di fattura («HOPLA'»).
    """
    testo = corpo or ""
    if re.search(r"=0A|=09|=\r?\n", testo):
        testo = quopri.decodestring(testo.encode("utf-8", errors="replace")).decode("utf-8", errors="replace")
    testo = re.sub(r"<[^>]+>", " ", testo)
    return html.unescape(testo)


def estrai_codice_e_descrizione(oggetto: str, corpo: str = "") -> Dict[str, Optional[str]]:
    """Codice articolo e descrizione dalla mail di Order Sender.

    Il corpo dice «del prodotto COOP012 - PANNA SPRAY FIORDINEVE CF 500 GR (CT
    6X500GR) Order Sender Enterprise»; l'oggetto porta almeno il codice.
    """
    corpo = testo_corpo(corpo)
    codice = None
    m = re.search(r"cod\.?\s*articolo\s+([A-Z0-9][A-Z0-9._-]*)", oggetto or "", re.I)
    if m:
        codice = m.group(1).upper()
    descrizione = None
    m = re.search(r"del prodotto\s+([A-Z0-9][A-Z0-9._-]*)\s+-\s+(.+?)(?:\s+Order Sender|\s*$)",
                  (corpo or "").replace("\n", " "), re.I)
    if m:
        codice = codice or m.group(1).upper()
        descrizione = re.sub(r"\s+", " ", m.group(2)).strip() or None
    return {"codice_articolo": codice, "descrizione": descrizione}


def leggi_allergeni(testo_pdf: str) -> Dict[str, Any]:
    """Allergeni presenti e tracce, letti dal testo della scheda.

    Tre forme riconosciute, dalla più affidabile: righe di tabella
    («Latte e derivati   SI»), elenchi dopo «Allergeni:» / «Contiene:»,
    e «Può contenere tracce di …» (le tracce restano separate dai presenti).
    Se non si riconosce nessuna forma: stato ``da_verificare``, niente dedotto.
    """
    testo = _pulisci(testo_pdf)
    presenti: List[str] = []
    assenti: List[str] = []
    tracce: List[str] = []
    righe_tabella = 0

    tabella_contaminazione = bool(
        re.search(r"(?is)cross.?contamination.{0,500}(?:carry-over|stabilimento)", testo)
        or re.search(r"(?is)cross-.{0,1000}contamination", testo)
    )
    tabella_simboli_ambigua = bool(re.search(
        r"(?i)allergeni.{0,300}\b(?:assenza|presenza certa|presenza possibile)\b", testo, re.S))
    for riga in testo.split("\n"):
        if re.search(r"pu[oò] contenere|tracce", riga):
            continue
        for segmento in re.split(r"[]", riga):
            trovati = _trova_allergeni(segmento)
            if len(trovati) != 1:
                continue
            coda = segmento.split(":", 1)[-1] if ":" in segmento else segmento
            if not tabella_contaminazione and re.search(rf"(?<![a-zà-ù]){_SI}(?![a-zà-ù])\s*$", coda.strip()):
                presenti.append(trovati[0]); righe_tabella += 1
            elif not tabella_contaminazione and re.search(rf"(?<![a-zà-ù]){_NO}(?![a-zà-ù])\s*$", coda.strip()):
                assenti.append(trovati[0]); righe_tabella += 1
            elif not tabella_simboli_ambigua and re.search(r"\+\s*$", coda.strip()):
                presenti.append(trovati[0]); righe_tabella += 1
            elif not tabella_simboli_ambigua and re.search(r"-\s*$", coda.strip()):
                assenti.append(trovati[0]); righe_tabella += 1

    # La composizione e' una dichiarazione esplicita. E' piu' affidabile delle
    # tabelle estratte come testo: in molti PDF le tre colonne
    # assenza/presenza/tracce collassano e resta soltanto una ``X`` senza la sua
    # coordinata. Una X isolata non viene quindi mai interpretata.
    ingredienti = _sezione_ingredienti(testo)
    if ingredienti:
        presenti.extend(_trova_allergeni(ingredienti))

    for m in re.finditer(r"(?:allergeni(?: presenti)?|contiene(?:\s+allergen[ei])?)\s*[:\-]?\s*([^\n]{0,240})", testo):
        span = m.group(1)
        if re.match(r"\s*(nessuno|assenti|non contiene)", span):
            continue
        presenti.extend(a for a in _trova_allergeni(span.split("pu")[0]) if a not in assenti)

    for m in re.finditer(r"(?:pu[oò] contenere(?: tracce di)?|tracce di)\s*[:\-]?\s*([^\n.]{0,240})", testo):
        tracce.extend(_trova_allergeni(m.group(1)))

    presenti = list(dict.fromkeys(presenti))
    tracce = [a for a in dict.fromkeys(tracce) if a not in presenti]
    tabella_x_ambigua = tabella_simboli_ambigua or bool(
        re.search(r"(?im)^\s*(?:x|cc)\s*$", testo)
    ) or bool(re.search(r"(?is)trasformazione diretta.{0,250}possibile contaminazione", testo)) \
        or tabella_contaminazione
    riconosciuto = bool(presenti or tracce or righe_tabella or re.search(r"allergen", testo))
    stato = "letti" if (presenti or righe_tabella or tracce) and not tabella_x_ambigua else (
        "da_verificare" if tabella_x_ambigua else (
            "sezione_senza_allergeni" if riconosciuto else "da_verificare"
        )
    )
    return {
        "allergeni": presenti,
        "allergeni_tracce": tracce,
        "allergeni_assenti": list(dict.fromkeys(assenti)),
        "allergeni_stato": stato,
        "tabella_colonne_da_verificare": tabella_x_ambigua,
    }


_VOCI_NUTRIZIONALI = {
    "energia_kj": r"energia[^\n\d]{0,40}?(\d+(?:[.,]\d+)?)[ \t]*kj",
    "energia_kcal": r"(\d+(?:[.,]\d+)?)[ \t]*kcal",
    "grassi_g": r"(?<!di cui )grassi(?! saturi)[^\n\d]{0,30}?(\d+(?:[.,]\d+)?)\s*g",
    "grassi_saturi_g": r"saturi[^\n\d]{0,30}?(\d+(?:[.,]\d+)?)\s*g",
    "carboidrati_g": r"carboidrati[^\n\d]{0,30}?(\d+(?:[.,]\d+)?)\s*g",
    "zuccheri_g": r"zuccheri[^\n\d]{0,30}?(\d+(?:[.,]\d+)?)\s*g",
    "fibre_g": r"fibr[ae][^\n\d]{0,30}?(\d+(?:[.,]\d+)?)\s*g",
    "proteine_g": r"proteine[^\n\d]{0,30}?(\d+(?:[.,]\d+)?)\s*g",
    "sale_g": r"(?<![a-zà-ù])sale(?![a-zà-ù])[^\n\d]{0,30}?(\d+(?:[.,]\d+)?)\s*g",
}


def leggi_valori_nutrizionali(testo_pdf: str) -> Dict[str, Optional[str]]:
    """Valori per 100 g come stringhe decimali (mai float): ``None`` se assenti.

    Si cerca solo dopo l'intestazione della tabella nutrizionale, per non
    prendere un «sale» o un «grassi» dalla lista ingredienti.
    """
    testo = _pulisci(testo_pdf)
    m = re.search(r"(valori nutrizionali|dichiarazione nutrizionale|informazioni nutrizionali|nutrition)", testo)
    if not m:
        return {k: None for k in _VOCI_NUTRIZIONALI}
    tabella = testo[m.start(): m.start() + 1500]
    valori: Dict[str, Optional[str]] = {}
    for chiave, pattern in _VOCI_NUTRIZIONALI.items():
        trovato = re.search(pattern, tabella)
        valori[chiave] = trovato.group(1).replace(",", ".") if trovato else None
    # Formato PreGel: ``527 / 126 (kJ / kcal)``. Le etichette e i valori sono
    # spesso su righe diverse, quindi il parser precedente non vedeva energia.
    coppia = re.search(r"(\d+(?:[.,]\d+)?)\s*/\s*(\d+(?:[.,]\d+)?)\s*\(\s*kj\s*/\s*kcal\s*\)", tabella)
    if coppia:
        valori["energia_kj"] = coppia.group(1).replace(",", ".")
        valori["energia_kcal"] = coppia.group(2).replace(",", ".")
    coppia_inversa = re.search(
        r"(\d+(?:[.,]\d+)?)\s*/\s*(\d+(?:[.,]\d+)?)\s*(?:kcal\s*/\s*k\s*j|kcal\s*/\s*kj)", tabella)
    if coppia_inversa:
        valori["energia_kcal"] = coppia_inversa.group(1).replace(".", "").replace(",", ".")
        valori["energia_kj"] = coppia_inversa.group(2).replace(".", "").replace(",", ".")
    kcal_kj = re.search(
        r"kcal[ \t]+(\d+(?:[.,]\d+)?)[ \t]+k(?:joule|j)[ \t]+(\d+(?:[.,]\d+)?)", tabella)
    if kcal_kj:
        valori["energia_kcal"] = kcal_kj.group(1).replace(".", "").replace(",", ".")
        valori["energia_kj"] = kcal_kj.group(2).replace(".", "").replace(",", ".")
    valori_su_righe = re.search(
        r"(\d+(?:[.,]\d+)?)[ \t]*kcal[ \t]*\n[ \t]*(\d+(?:[.,]\d+)?)[ \t]*kj", tabella)
    if valori_su_righe:
        valori["energia_kcal"] = valori_su_righe.group(1).replace(".", "").replace(",", ".")
        valori["energia_kj"] = valori_su_righe.group(2).replace(".", "").replace(",", ".")
    return valori


async def registra_scheda_tecnica(
    db_lotti,
    *,
    documento_id: str,
    pdf_sha256: str,
    testo_pdf: str,
    oggetto: str,
    corpo: str = "",
    email_uid: str = "",
    email_data: str = "",
    fornitore: str = FORNITORE_MEPA,
    drive_file_id: str | None = None,
    filename: str = "",
) -> Dict[str, Any]:
    """Crea o aggiorna la scheda tecnica di un articolo in ``schede_tecniche``.

    Idempotente per (fornitore, codice articolo): una scheda nuova per lo stesso
    articolo sostituisce i dati letti ma conserva l'elenco dei PDF ricevuti.
    """
    ident = estrai_codice_e_descrizione(oggetto, corpo)
    descrizione = ident["descrizione"] or ident["codice_articolo"] or ""
    chiave = chiave_descrizione(descrizione)
    if not chiave:
        return {"registrata": False, "motivo": "codice e descrizione assenti"}
    allergeni = leggi_allergeni(testo_pdf)
    nutrizione = leggi_valori_nutrizionali(testo_pdf)
    metadati = leggi_metadati_tecnici(testo_pdf)
    adesso = datetime.now(timezone.utc).isoformat()
    filtro = ({"fornitore": fornitore, "codice_articolo": ident["codice_articolo"], "tipo": "tecnica"}
              if ident["codice_articolo"] else {"prodotto_key": chiave, "tipo": "tecnica",
                                                "fonte": FONTE_EMAIL_FORNITORE})
    esistente = await db_lotti.schede_tecniche.find_one(filtro, {"_id": 0, "pdf_ricevuti": 1})
    ricevuti = list((esistente or {}).get("pdf_ricevuti") or [])
    if pdf_sha256 not in [r.get("sha256") for r in ricevuti]:
        ricevuti.append({"sha256": pdf_sha256, "documento_id": documento_id,
                         "email_uid": email_uid, "email_data": email_data, "ricevuto_at": adesso})
    doc = {
        **filtro,
        "prodotto_key": chiave,
        "nome_prodotto": descrizione,
        "fornitore": fornitore,
        "codice_articolo": ident["codice_articolo"],
        "url": f"/lotti/api/schede-tecniche/pdf/{documento_id}",
        "documento_id": documento_id,
        "pdf_sha256": pdf_sha256,
        "pdf_ricevuti": ricevuti,
        "fonte": FONTE_EMAIL_FORNITORE,
        "verificato": False,
        "composizione": [r.strip() for r in (metadati.get("composizione_dichiarata") or "").splitlines()
                         if r.strip()],
        **allergeni,
        "valori_nutrizionali_100g": nutrizione,
        "nutrizione_stato": "letti" if any(nutrizione.values()) else "da_verificare",
        "metadati_tecnici": metadati,
        "aggiornato_at": adesso,
    }
    if drive_file_id:
        doc["drive_file_id"] = drive_file_id
    if filename:
        doc["filename"] = filename
    await db_lotti.schede_tecniche.update_one(filtro, {"$set": doc}, upsert=True)
    return {"registrata": True, "prodotto_key": chiave, "codice_articolo": ident["codice_articolo"],
            "allergeni": allergeni["allergeni"], "allergeni_stato": allergeni["allergeni_stato"],
            "nutrizione_stato": doc["nutrizione_stato"]}


async def allergeni_da_schede(db_lotti, nomi_ingredienti: List[str]) -> Dict[str, Dict[str, Any]]:
    """Allergeni dichiarati dalle schede dei prodotti che servono questi ingredienti.

    Due strade, entrambe per identità: il nome è già la descrizione di un
    articolo con scheda (il lotto FIFO consumato), oppure ingrediente →
    articoli confermati che lo servono (``nome_mapping``) → schede con la
    stessa descrizione. Una proposta non confermata non attribuisce allergeni.
    """
    from app.lotti.servizi.articoli_fattura import carica_associazioni, serve_ingrediente

    associazioni = await carica_associazioni(db_lotti)
    schede = await db_lotti.schede_tecniche.find(
        {"tipo": "tecnica", "allergeni": {"$exists": True}},
        {"_id": 0, "prodotto_key": 1, "nome_prodotto": 1, "allergeni": 1, "allergeni_tracce": 1},
    ).to_list(5000)
    per_chiave = {s["prodotto_key"]: s for s in schede if s.get("prodotto_key")}
    esito: Dict[str, Dict[str, Any]] = {}
    def aggiungi(aid: str, nome: str, scheda: Dict[str, Any]) -> None:
        voce = esito.setdefault(aid, {"ingredienti": [], "schede": []})
        if nome not in voce["ingredienti"]:
            voce["ingredienti"].append(nome)
        if scheda.get("nome_prodotto") not in voce["schede"]:
            voce["schede"].append(scheda.get("nome_prodotto"))

    for nome in nomi_ingredienti or []:
        # il lotto consumato è proprio quell'articolo: stessa descrizione
        diretta = per_chiave.get(chiave_descrizione(nome))
        if diretta:
            for aid in diretta.get("allergeni") or []:
                aggiungi(aid, nome, diretta)
        for chiave, assoc in associazioni.items():
            scheda = per_chiave.get(chiave)
            if not scheda or not assoc.get("confermato") or not serve_ingrediente(assoc, nome):
                continue
            for aid in scheda.get("allergeni") or []:
                aggiungi(aid, nome, scheda)
    return esito


async def completa_allergeni_con_schede(db_lotti, nomi_ingredienti: List[str], info: Dict[str, Any]) -> Dict[str, Any]:
    """Aggiunge all'esito di ``_rileva_allergeni`` quelli dichiarati dalle schede.

    Il nome «Universal Cake» non dice latte né uova: la scheda del produttore
    sì. Un allergene dichiarato dalla scheda di un articolo confermato entra
    in etichetta con la fonte. Un guasto qui non blocca la produzione.
    """
    try:
        da_schede = await allergeni_da_schede(db_lotti, nomi_ingredienti)
    except Exception:  # noqa: BLE001 — l'etichetta resta quella dai nomi
        import logging
        logging.getLogger(__name__).exception("allergeni da schede non letti")
        return info
    if not da_schede:
        return info
    from app.lotti.routers.utils import _ALLERGENI_KEYS

    presenti = list(info.get("allergeni_presenti") or [])
    dettaglio = dict(info.get("allergeni_dettaglio") or {})
    for aid, voce in da_schede.items():
        if aid not in presenti:
            presenti.append(aid)
        nome = (_ALLERGENI_KEYS.get(aid) or {}).get("nome", aid)
        dettaglio.setdefault(aid, {"nome": nome, "ingredienti": voce["ingredienti"]})
        dettaglio[aid]["schede"] = voce["schede"]
    nomi = [dettaglio[a]["nome"] for a in presenti if a in dettaglio]
    return {
        **info,
        "allergeni_presenti": presenti,
        "allergeni_dettaglio": dettaglio,
        "testo_etichetta": ("Contiene: " + ", ".join(nomi)) if nomi else info.get("testo_etichetta", ""),
        "contiene_allergeni": bool(presenti),
    }
