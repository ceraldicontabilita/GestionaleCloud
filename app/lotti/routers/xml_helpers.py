"""
Funzioni helper condivise per il parsing XML di fatture elettroniche
e le utility di normalizzazione testo.
"""

import re
import xml.etree.ElementTree as ET

try:
    from rapidfuzz import fuzz
except ImportError:
    from fuzzywuzzy import fuzz  # fallback se rapidfuzz non ancora installato


# Normalizzazione unità di misura: varianti/sinonimi → forma canonica.
# SOLO mapping certi. Le sigle ambigue (es. "B", "BS") restano invariate.
_UNITA_CANONICHE = {
    "KG": "KG", "KGM": "KG", "KGS": "KG", "CHILOGRAMMI": "KG", "CHILOGRAMMO": "KG",
    "CHILO": "KG", "CHILI": "KG",
    "G": "G", "GR": "G", "GRAMMI": "G", "GRAMMO": "G",
    "L": "L", "LT": "L", "LITRO": "L", "LITRI": "L",
    "ML": "ML", "MILLILITRI": "ML",
    "PZ": "PZ", "PEZZI": "PZ", "PEZZO": "PZ", "NR": "PZ", "N": "PZ",
    "NUMERO": "PZ", "NUM": "PZ", "PCS": "PZ", "PC": "PZ",
    "BT": "BT", "BOTTIGLIA": "BT", "BOTTIGLIE": "BT", "BTG": "BT",
    "CT": "CT", "CARTONE": "CT", "CARTONI": "CT", "COLLO": "CT", "COLLI": "CT",
    "CF": "CF", "CONF": "CF", "CONFEZIONE": "CF", "CONFEZIONI": "CF",
    "RT": "RT", "ROTOLO": "RT", "ROTOLI": "RT",
    "MQ": "MQ", "M2": "MQ",
    "FUSTO": "FUSTO", "FUSTI": "FUSTO",
    "SC": "SC", "SCATOLA": "SC", "SCATOLE": "SC",
}


def normalizza_unita_misura(u) -> str:
    """Normalizza un'unità di misura alla forma canonica.
    Sicura: se la sigla non è riconosciuta la lascia com'è (uppercase),
    senza tirare a indovinare."""
    if not u:
        return ""
    s = str(u).strip().upper()
    if not s:
        return ""
    if s in _UNITA_CANONICHE:
        return _UNITA_CANONICHE[s]
    s2 = s.rstrip(".").replace("°", "")  # "NR.", "N." , "N°"
    if s2 in _UNITA_CANONICHE:
        return _UNITA_CANONICHE[s2]
    return s


def parse_fattura_xml(xml_content: bytes) -> dict:
    """Parse fattura elettronica XML e estrae i dati, inclusi lotti fornitori"""
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError:
        root = ET.fromstring(xml_content.decode("utf-8"))

    result = {
        "fornitore": "",
        "piva": "",
        "numero_fattura": "",
        "data_fattura": "",
        "prodotti": [],
        "cedente_email": "",
        "cedente_telefono": "",
    }

    # Estrae dati cedente (inclusi contatti)
    _in_cedente = False
    _ced_nome = ""
    _ced_cognome = ""
    for elem in root.iter():
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if tag == "CedentePrestatore":
            _in_cedente = True
        if tag == "CessionarioCommittente":
            _in_cedente = False
        if tag == "Denominazione" and _in_cedente and not result["fornitore"]:
            result["fornitore"] = (elem.text or "").strip().strip('"').strip("'")
        # Ditta individuale / persona fisica: niente Denominazione, ma Nome+Cognome
        # nell'Anagrafica del CedentePrestatore. Raccolti SOLO dentro il cedente.
        if tag == "Nome" and _in_cedente and not _ced_nome:
            _ced_nome = (elem.text or "").strip()
        if tag == "Cognome" and _in_cedente and not _ced_cognome:
            _ced_cognome = (elem.text or "").strip()
        if tag == "IdCodice" and _in_cedente and not result["piva"]:
            result["piva"] = elem.text or ""
        if tag == "Numero" and not result["numero_fattura"]:
            result["numero_fattura"] = elem.text or ""
        if tag == "Data" and not result["data_fattura"]:
            result["data_fattura"] = elem.text or ""
        # Contatti cedente (solo dentro il cedente)
        if tag == "Email" and _in_cedente and not result["cedente_email"]:
            result["cedente_email"] = (elem.text or "").strip()
        if tag == "Telefono" and _in_cedente and not result["cedente_telefono"]:
            result["cedente_telefono"] = (elem.text or "").strip()

    # Fallback nome fornitore: se manca la Denominazione (ditta individuale),
    # usa Nome + Cognome del cedente. Evita fatture con P.IVA ma senza nome.
    if not result["fornitore"]:
        nc = (f"{_ced_nome} {_ced_cognome}").strip()
        if nc:
            result["fornitore"] = nc

    for elem in root.iter():
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if tag == "DettaglioLinee":
            prodotto = {
                "descrizione": "",
                "quantita": "",
                "prezzo": "",
                "unita_misura": "",
                "codice_articolo": "",
                "_lotto_data": {},
            }
            altri_dati = []
            for child in elem:
                child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if child_tag == "Descrizione":
                    prodotto["descrizione"] = (child.text or "").strip()
                elif child_tag == "CodiceArticolo":
                    # <CodiceArticolo><CodiceTipo>..</CodiceTipo><CodiceValore>1656</CodiceValore></CodiceArticolo>
                    # È il codice del fornitore: identico a quello dei suoi cataloghi
                    # (Bindi/Tre Marie/Il Pasticcere...) → aggancio prezzo deterministico.
                    for sub in child:
                        sub_tag = sub.tag.split("}")[-1] if "}" in sub.tag else sub.tag
                        if sub_tag == "CodiceValore" and not prodotto["codice_articolo"]:
                            prodotto["codice_articolo"] = (sub.text or "").strip()
                elif child_tag == "Quantita":
                    prodotto["quantita"] = child.text or ""
                elif child_tag == "PrezzoUnitario":
                    prodotto["prezzo"] = child.text or ""
                elif child_tag == "AliquotaIVA":
                    prodotto["iva"] = (child.text or "").strip()
                elif child_tag == "UnitaMisura":
                    prodotto["unita_misura"] = normalizza_unita_misura(child.text)
                elif child_tag == "AltriDatiGestionali":
                    tipo = ""
                    rif_testo = ""
                    rif_data = ""
                    for sub in child:
                        sub_tag = sub.tag.split("}")[-1] if "}" in sub.tag else sub.tag
                        if sub_tag == "TipoDato":
                            tipo = (sub.text or "").strip().upper()
                        elif sub_tag == "RiferimentoTesto":
                            rif_testo = (sub.text or "").strip()
                        elif sub_tag == "RiferimentoData":
                            rif_data = (sub.text or "").strip()

                    if tipo == "DATI LOTTO" and rif_testo:
                        # SAIMA: 'Id: 617435 - Scadenza: 04/04/2026 - Qtà: 2' o 'Qt: 2'
                        # Nota: 'Qtà' può avere encoding corrotto (à fuori ASCII),
                        # quindi usiamo \S* per catturare qualsiasi carattere non-spazio dopo Qt
                        lotto_data = {}
                        id_m = re.search(r"Id:\s*(\w+)", rif_testo, re.IGNORECASE)
                        scad_m = re.search(
                            r"Scadenza:\s*(\d{2}/\d{2}/\d{4})", rif_testo, re.IGNORECASE
                        )
                        qt_m = re.search(r"Qt[^\s:]*\s*:\s*([\d.,]+)", rif_testo, re.IGNORECASE)
                        if id_m:
                            lotto_data["lotto_id_fornitore"] = id_m.group(1)
                        if scad_m:
                            lotto_data["data_scadenza"] = scad_m.group(1)
                        if qt_m:
                            qt_val = qt_m.group(1).replace(",", ".")
                            try:
                                lotto_data["quantita_originale"] = float(qt_val)
                            except ValueError:
                                pass
                        if lotto_data:
                            prodotto["_lotto_data"] = lotto_data

                    elif rif_testo and not prodotto["_lotto_data"]:
                        # Naturissime / altro: testo lotto generico + data
                        lotto_data = {}
                        if re.match(r"^[A-Z]{2}\s*\d+", rif_testo):
                            lotto_data["lotto_id_fornitore"] = rif_testo
                            if rif_data:
                                lotto_data["data_scadenza"] = rif_data
                            prodotto["_lotto_data"] = lotto_data

            if prodotto["descrizione"] and _e_prodotto_valido(prodotto):
                result["prodotti"].append(prodotto)

    return result


def _e_prodotto_valido(prodotto: dict) -> bool:
    """Filtra righe XML che non sono prodotti reali."""
    desc = prodotto.get("descrizione", "").strip()
    if not desc:
        return False
    if desc.startswith("**") or desc.startswith("* "):
        return False
    PREFISSI_DA_SALTARE = [
        "LUOGO DI CONSEGNA",
        "LUOGO CONSEGNA",
        "INDIRIZZO DI CONSEGNA",
        "Rif. Doc.",
        "Rif. Conferma",
        "Rif. Ordine",
        "DESTINAZIONE MERCE",
        "SEDE LEGALE",
        "C/O ",
        "c/o ",
    ]
    desc_upper = desc.upper()
    for prefisso in PREFISSI_DA_SALTARE:
        if desc_upper.startswith(prefisso.upper()) or prefisso in desc:
            return False
    if re.match(r"^\s*\(\d+\s+\d{2}/\d{2}/\d{2,4}\)", desc):
        return False
    if re.match(r"^\d{5}\s+[A-Z]", desc):
        return False
    if re.match(r"^\d{4,5}$", desc):
        return False
    try:
        prezzo = float(str(prodotto.get("prezzo", "0") or "0").replace(",", "."))
        quantita = float(str(prodotto.get("quantita", "0") or "0").replace(",", "."))
        if prezzo == 0 and quantita == 0:
            return False
    except (ValueError, TypeError):
        pass
    return True


def normalizza_testo(testo: str) -> str:
    """Normalizza testo per confronto"""
    if not testo:
        return ""
    testo = re.sub(r"\s+", " ", testo.lower().strip())
    testo = re.sub(r"[^\w\s]", "", testo)
    return testo


def fuzzy_match(testo1: str, testo2: str, soglia: int = 70) -> bool:
    """Confronto fuzzy tra due stringhe con soglia di similarità"""
    if not testo1 or not testo2:
        return False
    t1 = normalizza_testo(testo1)
    t2 = normalizza_testo(testo2)
    ratio = fuzz.ratio(t1, t2)
    partial = fuzz.partial_ratio(t1, t2)
    token_sort = fuzz.token_sort_ratio(t1, t2)
    best_score = max(ratio, partial, token_sort)
    return best_score >= soglia


def cerca_match_ingrediente(ingrediente: str, prodotti_fattura: list, soglia: int = 70):
    """Cerca un match tra ingrediente e prodotti della fattura usando fuzzy matching"""
    ingrediente_norm = normalizza_testo(ingrediente)
    miglior_match = None
    miglior_score = 0
    for prodotto in prodotti_fattura:
        desc = prodotto.get("descrizione", "")
        desc_norm = normalizza_testo(desc)
        ratio = fuzz.ratio(ingrediente_norm, desc_norm)
        partial = fuzz.partial_ratio(ingrediente_norm, desc_norm)
        token_sort = fuzz.token_sort_ratio(ingrediente_norm, desc_norm)
        score = max(ratio, partial, token_sort)
        prima_parola = ingrediente_norm.split()[0] if ingrediente_norm else ""
        if prima_parola and len(prima_parola) > 2 and prima_parola in desc_norm:
            score += 15
        if score > miglior_score and score >= soglia:
            miglior_score = score
            miglior_match = {**prodotto, "score": score}
    return miglior_match


def pulisci_nome_ingrediente(ingrediente: str) -> str:
    """Pulisce il nome dell'ingrediente rimuovendo codici lotto, fattura e info extra."""
    if not ingrediente:
        return ""
    testo = ingrediente.strip()
    testo = re.sub(
        r"\s+[xX]\s*\d+(?:[.,]\d+)?(?:\s*(?:kg|g|lt|ml|l))?(?=\s|$)", "", testo, flags=re.IGNORECASE
    )
    testo = re.sub(r"\s+(non\s+)?contiene\s+allergeni.*$", "", testo, flags=re.IGNORECASE)
    testo = re.sub(
        r'\s*-\s*[A-Za-z\."]+(?:\s+[A-Za-z\."]+)*(?:\s+(?:S\.?[rR]\.?[lL]\.?|S\.?[pP]\.?[aA]\.?|srl|spa))?.*$',
        "",
        testo,
        flags=re.IGNORECASE,
    )
    testo = re.sub(r"\s+L\.?F?\.?\d*/?[\w\-]*", "", testo, flags=re.IGNORECASE)
    testo = re.sub(r"\s+FVI/[\w\-]+", "", testo, flags=re.IGNORECASE)
    testo = re.sub(r"\s+n°?\s*fatt\.?\s*[\w/\-]+", "", testo, flags=re.IGNORECASE)
    testo = re.sub(r"\s*-?\s*\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}", "", testo)
    testo = re.sub(r"\s+SACCHI\s+SALTECHNO.*$", "", testo, flags=re.IGNORECASE)
    testo = re.sub(r"\s+DA\s+KG\.?\s*\d+(?:[.,]\d+)?", "", testo, flags=re.IGNORECASE)
    testo = re.sub(r"\s+KG\.?\s*\d+(?:[.,]\d+)?", "", testo, flags=re.IGNORECASE)
    testo = re.sub(r"\s+\d+(?:[.,]\d+)?\s*KG\b", "", testo, flags=re.IGNORECASE)
    testo = re.sub(r"\s+\d+(?:[.,]\d+)?\s*(?:G|LT|ML|L)\b", "", testo, flags=re.IGNORECASE)
    testo = re.sub(r"\s*-\s*\d{5,}$", "", testo)
    testo = re.sub(r"\s+Orig\.?\s*\w+", "", testo, flags=re.IGNORECASE)
    testo = re.sub(r"\s+RINFORZ\.?\w*", "", testo, flags=re.IGNORECASE)
    testo = re.sub(r"\s+ASTUC\.?\w*", "", testo, flags=re.IGNORECASE)
    testo = re.sub(r"\s+I\s+B\s+\w+", "", testo, flags=re.IGNORECASE)
    testo = re.sub(r"\s+P[xX]\d+", "", testo, flags=re.IGNORECASE)
    testo = re.sub(r"\s+\d+\^\s*\d*", "", testo, flags=re.IGNORECASE)
    testo = re.sub(r"\s+\w*\d+\w*$", "", testo, flags=re.IGNORECASE)
    testo = re.sub(r"\s+GR\.?\d+", "", testo, flags=re.IGNORECASE)
    testo = re.sub(r"\s+", " ", testo)
    testo = re.sub(r"\s*-\s*$", "", testo)
    testo = re.sub(r"^\s*-\s*", "", testo)
    testo = testo.strip()
    if testo:
        parole = testo.split()
        parole_formattate = []
        for i, p in enumerate(parole):
            p_lower = p.lower()
            if p_lower in ["00", "0", "man", "man.", "0/man."]:
                parole_formattate.append(p_lower)
            elif i == 0:
                parole_formattate.append(p.capitalize())
            else:
                parole_formattate.append(p_lower)
        testo = " ".join(parole_formattate)
    return testo


def estrai_quantita_da_descrizione(descrizione: str) -> tuple:
    """Estrae quantità e unità dalla descrizione del prodotto fattura.

    REGOLA: Legge SEMPRE la descrizione per trovare il peso fisico della confezione.
    Gestisce: KG, G, GR, GR., G., ML, LT + formati glued tipo G500, GR.9, BOSCOG500
    ESCLUDE: numeri seguiti da PORZIONI/PEZZI/PZ/NR (conteggi, non pesi)
    """
    if not descrizione:
        return (1, "pz")
    desc = descrizione.upper()

    # Parole che indicano un conteggio di pezzi — NON un peso
    CONTEGGIO = {
        "PORZIONI",
        "PORZIONE",
        "PORZIO",
        "PEZZI",
        "MONOPORZ",
        "MONODOSE",
        "DOSE",
        "SLICE",
        "NR",
        "CONF",
    }

    patterns = [
        (r"(\d+(?:[.,]\d+)?)\s*KG\b", "kg"),
        (r"\bKG[\.\s]*(\d+(?:[.,]\d+)?)", "kg"),  # KG.0.250, KG 1.5
        (r"\bGR?[\.\s]+(\d+(?:[.,]\d+)?)\b", "g"),
        (r"(?<=[A-Z])G(\d{3,})\b", "g"),
        (r"\bG(\d{2,})\b", "g"),
        (r"(\d+(?:[.,]\d+)?)\s*LT?\b", "l"),
        # litri con l'UNITÀ PRIMA del numero, ma SOLO con "LT" ("LT.5", "LT 1,5",
        # "OLIO GIRASOLE LT.10"): mancava e la riga finiva in 'nessuna_info' col
        # prezzo del contenitore preso per €/kg (olio 5L a €40 → 40 invece di 8).
        # Il singolo "L." NON si tocca di proposito: è il prefisso comunissimo del
        # numero di LOTTO ("AGLIO L.372", "BASILICO L.417291") → un pattern L-generico
        # leggerebbe il lotto come litri. Il bare "L.5" resta affidato alla regola
        # confermata (battesimo Dizionario / priorità 0).
        (r"\bLT[\.\s]*(\d+(?:[.,]\d+)?)", "l"),
        (r"(\d+(?:[.,]\d+)?)\s*ML\b", "ml"),
        (r"\bML[\.\s]*(\d+(?:[.,]\d+)?)", "ml"),  # ML200 (succhi/bibite: unità prima)
        # bevande: quasi sempre "CL33" (unità PRIMA del numero, es. "BIRRA CL33X24"),
        # ma alcuni fornitori scrivono "33CL" — gestiti entrambi gli ordini.
        (r"\bCL[\.\s]*(\d+(?:[.,]\d+)?)", "cl"),
        (r"(\d+(?:[.,]\d+)?)\s*CL\b", "cl"),
        (r"(\d+(?:[.,]\d+)?)\s*G\b", "g"),
    ]
    for pattern, unita in patterns:
        match = re.search(pattern, desc)
        if not match:
            continue
        # Controlla la parola subito dopo il match
        end = match.end()
        rest = desc[end : end + 20].strip()
        next_word = re.split(r"\W+", rest)[0] if rest else ""
        if next_word in CONTEGGIO:
            continue  # es. "G. 8 PORZIONI" → skip, è un conteggio
        qty = match.group(1).replace(",", ".")
        val = float(qty)
        if val > 0:
            return (val, unita)
    return (1, "pz")


_RX_MOLTIPLICATORE = re.compile(r"X(\d{1,3})\b")


def _peso_in_kg(valore: float, unita: str) -> float:
    """Converte un peso/volume nell'unità indicata in kg. Convenzione già in uso nel
    progetto: 1 litro trattato 1:1 come 1 kg (densità ~1 per i liquidi gestiti qui)."""
    if unita in ("g", "ml"):
        return valore / 1000.0
    if unita == "cl":
        return valore / 100.0
    return valore  # "kg" o "l"/"lt" già 1:1


def calcola_prezzo_quantita_kg(
    quantita: float,
    prezzo: float,
    unita_misura_fattura: str,
    descrizione: str,
    regola_nota: dict = None,
) -> dict:
    """Calcola quantita_kg/prezzo_kg reali per UNA riga fattura.

    Distingue SEMPRE due situazioni, perché richiedono formule opposte:
    (a) 'quantita' della fattura È GIÀ il peso/volume totale reale (prodotti pesati:
        salame, porchetta, farina a sacchi KG...) → quantita_kg=quantita, prezzo_kg=prezzo.
    (b) 'quantita' conta PEZZI/CONFEZIONI e si conosce il peso di UNA unità (es. burro
        G125 = 125g/pezzo, olio L.5 = 5L/bottiglia) → quantita_kg = quantita(pezzi) *
        peso_unitario_kg, prezzo_kg = prezzo_per_pezzo / peso_unitario_kg.
    Confondere le due (usare la formula (b) quando in realtà è (a), o viceversa) è
    esattamente il bug corretto qui il 01/07/2026: vedi STATO.md.

    Priorità (più alta vince, la successiva è fallback):
      0. regola_nota — dizionario_prodotti.peso_confezione+tipo_quantita già confermato
         per questo nome_normalizzato (manualmente o da una fattura precedente). Se
         presente vince SEMPRE sulle euristiche sotto (è il "motore che si ricorda").
      1. unita_misura_fattura=="KG" — campo strutturato, verificato affidabile su
         pesati reali (farina/zucchero/salumi). Caso (a). MAI generalizzato a LT/L:
         alcuni fornitori usano LT per contare le confezioni, non i litri veri.
      2. peso di UNA unità estratto dal TESTO descrizione (G125, L.5, ML500...). Caso (b).
      3. fallback — nessuna informazione di peso disponibile: valori grezzi passati
         così come sono (la riga finisce nella coda /normalizzazione/prodotti-senza-peso).

    Ritorna sempre lo stesso dict, mai solleva eccezioni per input invalidi:
      quantita_kg, prezzo_kg (None se non calcolabile),
      peso_confezione_det/unita_confezione_det/tipo_quantita_det (da salvare SOLO se
      non-None — quando la fonte è 'regola_nota' sono sempre None: la regola esiste
      già, non va ri-scritta), fonte (per debug/log).
    """
    regola_nota = regola_nota or {}
    esito = {
        "quantita_kg": 0.0,
        "prezzo_kg": None,
        "peso_confezione_det": None,
        "unita_confezione_det": None,
        "tipo_quantita_det": None,
        "fonte": "quantita_o_prezzo_invalidi",
    }
    if not (quantita > 0 and prezzo > 0):
        return esito

    unita_fattura = (unita_misura_fattura or "").strip().upper()
    peso_nota = float(regola_nota.get("peso_confezione") or 0)
    tipo_nota = regola_nota.get("tipo_quantita")

    # NB: peso_nota>0 SENZA tipo_quantita esplicito ("confezioni"/"totale") NON è una
    # regola utilizzabile — sono record scritti dal vecchio auto-save (prima che questo
    # fix esistesse) dove peso_confezione era ambiguo (a volte "totale", a volte "per
    # pezzo") e non c'è modo di distinguerli col solo numero. Si ricade su KG/testo sotto,
    # che ri-deriva E ri-tagga tipo_quantita correttamente: si auto-guarisce da sola.
    if tipo_nota == "conteggio_confezioni":
        # Alias storico scritto dalla ricerca-web schede tecniche: stessa
        # semantica di "confezioni" (quantità fattura = numero confezioni).
        tipo_nota = "confezioni"
    if peso_nota > 0 and tipo_nota in ("confezioni", "totale"):
        # PRIORITÀ 0: regola già nota — vince sempre, non si ri-deriva nulla.
        # peso_nota è già espresso in kg/l equivalenti (dizionario_prodotti.peso_confezione
        # è per convenzione sempre pre-convertito — vedi param "peso_kg" in /correggi-peso
        # e come questa stessa funzione scrive peso_confezione_det più sotto): NESSUNA
        # ulteriore conversione va applicata qui, a differenza del testo grezzo in priorità 2.
        if tipo_nota == "confezioni":
            peso_unitario_kg = peso_nota
            if peso_unitario_kg > 0:
                esito["quantita_kg"] = quantita * peso_unitario_kg
                esito["prezzo_kg"] = prezzo / peso_unitario_kg
                esito["fonte"] = "regola_nota_confezioni"
        else:
            esito["quantita_kg"] = quantita
            esito["prezzo_kg"] = prezzo
            esito["fonte"] = "regola_nota_totale"
    elif unita_fattura == "KG":
        # PRIORITÀ 1: campo strutturato — quantita è già il totale reale.
        esito["quantita_kg"] = quantita
        esito["prezzo_kg"] = prezzo
        esito["fonte"] = "kg_strutturato"
        # Registra la regola per i prossimi acquisti (mai sovrascrive una correzione manuale:
        # lo fa il chiamante, che conosce peso_corretto_manualmente).
        esito["peso_confezione_det"] = round(quantita, 4)
        esito["unita_confezione_det"] = "kg"
        esito["tipo_quantita_det"] = "totale"
    else:
        # PRIORITÀ 2: peso di UNA unità dal testo descrizione.
        qty_testo, unita_testo = estrai_quantita_da_descrizione(descrizione)
        if unita_testo != "pz" and qty_testo:
            peso_unitario_kg = _peso_in_kg(qty_testo, unita_testo)
            # "Cartone/confezione da N pezzi" (CTX24, CFX12, X6...): il peso appena
            # estratto (es. 200ML/33CL) è di UN pezzo, ma quantita/prezzo in fattura
            # sono per l'intero cartone — senza moltiplicare per N, prezzo_kg
            # risulta gonfiato di un fattore N (bug corretto il 02/07/2026: un
            # succo di frutta risultava a >10.000€/kg, vedi STATO.md).
            if 0 < peso_unitario_kg <= 3:
                m_mult = _RX_MOLTIPLICATORE.search(descrizione.upper())
                if m_mult:
                    n_pezzi = int(m_mult.group(1))
                    if 2 <= n_pezzi <= 60:
                        peso_unitario_kg = round(peso_unitario_kg * n_pezzi, 6)
            if peso_unitario_kg > 0:
                esito["quantita_kg"] = quantita * peso_unitario_kg
                esito["prezzo_kg"] = prezzo / peso_unitario_kg
                esito["fonte"] = "testo"
                esito["peso_confezione_det"] = round(peso_unitario_kg, 4)
                esito["unita_confezione_det"] = "kg" if unita_testo in ("kg", "g") else "l"
                esito["tipo_quantita_det"] = "confezioni"
        if esito["fonte"] == "quantita_o_prezzo_invalidi":
            # FALLBACK: nessuna informazione di peso trovata da nessuna fonte.
            esito["quantita_kg"] = quantita
            esito["prezzo_kg"] = prezzo
            esito["fonte"] = "nessuna_info"

    esito["quantita_kg"] = round(esito["quantita_kg"], 4)
    if esito["prezzo_kg"] is not None:
        esito["prezzo_kg"] = round(esito["prezzo_kg"], 4)
    return esito
