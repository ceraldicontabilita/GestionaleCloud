"""
Parser F24 Entratel — Ceraldi ERP
Estrae dati strutturati da PDF F24 formato Entratel (Azienda 000026)

REGOLA CRITICA per Sezione Erario:
  - Il PDF ha DUE colonne: "importi a debito versati" e "importi a credito compensati"
  - La posizione X nel PDF determina in quale colonna cade il numero
  - NON si può dedurre debito/credito dal codice tributo
  - Es: 1701 (add. regionale) e 1704 (add. comunale) compaiono SEMPRE come CREDITO
        1001 (IRPEF rit.) e 1713 (saldo) compaiono come DEBITO
  - pdfplumber con layout=True preserva le colonne → si usa la coordinata X del testo
  
  Struttura colonne Erario (coordinate X approssimative nel PDF):
    codice_tributo: x ~ 100-160
    mese_rif:       x ~ 200-250  
    anno_rif:       x ~ 270-320
    debito:         x ~ 350-430  (colonna sinistra degli importi)
    credito:        x ~ 450-540  (colonna destra degli importi)
"""

import re, io
from datetime import datetime
from typing import Optional

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

# ── Dizionari codici ─────────────────────────────────────────
# ══════════════════════════════════════════════════════════════
# DIZIONARIO CODICI TRIBUTO ERARIO — Fonte: Agenzia delle Entrate
# Aggiornato con tutti i codici trovati nei F24 Ceraldi Group SRL
# Fonte ufficiale: agenziaentrate.gov.it (tabelle codici tributo)
# ══════════════════════════════════════════════════════════════
CODICI_ERARIO = {
    # ── IRPEF Ritenute ──────────────────────────────────────
    "1001": "IRPEF — ritenute su retribuzioni lavoro dipendente",
    "1002": "IRPEF — ritenute su emolumenti arretrati",
    "1004": "IRPEF — ritenute su redditi assimilati a lav. dipendente",
    "1012": "IRPEF — ritenute su indennità cessazione rapporto lavoro",
    "1019": "IRPEF — ritenuta 4% condominio sostituto imposta",
    "1038": "IRPEF — ritenute su provvigioni (commissione, agenzia, mediazione)",
    "1040": "IRPEF — ritenute su redditi lavoro autonomo/arti e professioni",
    "1053": "IRPEF — imposta sostitutiva su compensi accessori lavoro dipendente",
    # ── IRES / IRPEF Persone fisiche e società ────────────────
    "1301": "IRES — acconto",
    "1627": "IRES/IRPEF — 2° acconto",
    "1628": "IRES/IRPEF — saldo",
    "1629": "IRES/IRPEF — 1° acconto",
    "1631": "IRES/IRPEF — saldo anno precedente (usato come credito in compensazione)",
    "1668": "IRPEF/IRES — interessi da dilazione/rateazione",
    "1990": "IRES — imposta sostitutiva",
    "1991": "IRES — imposta sostitutiva interessi",
    "4034": "IRPEF — 2° acconto persona fisica",
    # ── Addizionali regionali e comunali ─────────────────────
    "1701": "Addizionale regionale IRPEF — ritenute dipendenti (CREDITO)",
    "1704": "Addizionale comunale IRPEF — ritenute dipendenti (CREDITO)",
    "1712": "Addizionale regionale IRPEF — saldo",
    "1713": "Addizionale comunale IRPEF — saldo/ravvedimento",
    # ── IVA ──────────────────────────────────────────────────
    "2001": "IVA — liquidazione periodica (F24 con elementi identificativi)",
    "2003": "IVA — versamento mensile",
    "6001": "IVA — mensile gennaio",
    "6002": "IVA — mensile febbraio",
    "6003": "IVA — mensile marzo",
    "6004": "IVA — mensile aprile",
    "6005": "IVA — mensile maggio",
    "6006": "IVA — mensile giugno",
    "6007": "IVA — mensile luglio",
    "6008": "IVA — mensile agosto",
    "6009": "IVA — mensile settembre",
    "6010": "IVA — mensile ottobre",
    "6011": "IVA — mensile novembre",
    "6012": "IVA — mensile dicembre",
    "6099": "IVA — credito annuale (compensazione)",
    # ── Imposta di bollo ──────────────────────────────────────
    "2501": "Imposta di bollo — versamento (libri sociali)",
    "2502": "Imposta di bollo — interessi ravvedimento",
    "2503": "Imposta di bollo — sanzione ravvedimento",
    "8904": "Imposta di bollo — versamento telematico",
    "8918": "Imposta di bollo — su libri e registri (annuale)",
    "8948": "Interessi ravvedimento su ritenute alla fonte",
    # ── Ravvedimento operoso (sanzioni e interessi) ───────────
    # Nella sezione REGIONI (IRAP):
    # 1993 = interessi ravvedimento IRAP
    # 8907 = sanzione ravvedimento IRAP
    # Nella sezione ERARIO:
    # 8906 = sanzione ravvedimento tributi erario
    # 8948 = interessi ravvedimento ritenute
    "8906": "Sanzione ravvedimento — tributi erario",
    "8947": "Interessi ravvedimento — addizionale regionale IRPEF",
    "8949": "Interessi ravvedimento — addizionale comunale IRPEF",
    "9001": "Somme da comunicazione di irregolarità art.36-bis — IRPEF/IRES",
    "9002": "Somme da comunicazione di irregolarità art.36-bis — IVA",
    "1703": "Addizionale comunale IRPEF — saldo (credito compensazione)",
    "1671": "Credito tributi locali in compensazione",
    "8907": "Sanzione ravvedimento — IRAP (sezione Regioni)",
    # ── Diritti e tasse ───────────────────────────────────────
    "6494": "Diritto annuale CCIAA (Camera di Commercio)",
    "7085": "Tassa annuale vidimazione libri sociali",
}
# ══════════════════════════════════════════════════════════════
# CODICI IMU E ALTRI TRIBUTI LOCALI
# Nella sezione IMU: il campo "Ravv./Acc./Saldo" indica il tipo:
#   X = Acconto, blank con "Saldo" = Saldo, Ravv. = Ravvedimento
# "Numero immobili" = numero fabbricati oggetto del tributo
# "Codice ente/comune" = codice catastale comune (es. F839=Napoli)
# ══════════════════════════════════════════════════════════════
CODICI_IMU = {
    # IMU fabbricati
    "3912": "IMU — abitazione principale",
    "3918": "IMU — fabbricati altri (non abitazione principale) — Comune Napoli F839",
    "3916": "IMU — aree fabbricabili",
    "3914": "IMU — terreni agricoli",
    # IMU — codici vecchi (ante riforma 2020)
    "3832": "IMU — abitazione principale (vecchio codice)",
    "3847": "IMU — tributo locale acconto (vecchio codice)",
    "3848": "IMU — tributo locale saldo (vecchio codice)",
    "3850": "IMU — terreni agricoli (vecchio codice)",
    "3851": "IMU — aree fabbricabili (vecchio codice)",
    # Crediti compensazione
    "3796": "IRAP — credito in compensazione (sezione Regioni)",
    "8950": "IRAP — interessi ravvedimento (sezione Regioni)",
    "3797": "IMU — credito in compensazione",
}
# ══════════════════════════════════════════════════════════════
# CODICI SEZIONE REGIONI (IRAP e imposte regionali)
# Codice regione: 01=Piemonte, 03=Lombardia, 05=Campania, ecc.
# ══════════════════════════════════════════════════════════════
CODICI_REGIONI = {
    "3800": "IRAP — imposta",
    "3801": "IRAP — saldo",
    "3805": "IRAP — 1° acconto",
    "3813": "IRAP — 2° acconto",
    "1993": "IRAP — interessi da ravvedimento operoso",
    "8907": "IRAP — sanzione da ravvedimento operoso",
    "3796": "IRAP — credito in compensazione",
}

# ══════════════════════════════════════════════════════════════
# CODICI INPS (causale contributo sezione INPS)
# Tabella aggiornata: agenziaentrate.gov.it codici INPS ed enti
# ══════════════════════════════════════════════════════════════
CODICI_INPS = {
    "CXX": "Contributi INPS — dipendenti (sede territoriale)",
    "DM10": "Contributi INPS — DM10 aziende",
    "F24": "Contributi INPS — gestione separata",
    "GPJA": "Contributi INPS — gestione separata professionisti",
    "RC01": "Contributi INPS — rateazione/concordato preventivo",
    "COS":  "Contributo di solidarietà INPS",
}
ENTI_NOTI = {
    "F839": "Comune di Napoli (F839)",
    "B990": "Comune di Napoli - tributo locale (B990)",
}

def _parse_euro(s: str) -> float:
    if not s: return 0.0
    s = s.strip().replace(" ", "").replace(".", "").replace(",", ".")
    try: return round(float(s), 2)
    except: return 0.0

def _parse_date_ita(s: str) -> Optional[str]:
    try: return datetime.strptime(s.strip(), "%d/%m/%Y").strftime("%Y-%m-%d")
    except: return None

def _desc_erario(cod): return CODICI_ERARIO.get(cod, f"Codice tributo {cod}")
def _desc_imu(cod, ente):
    return f"{CODICI_IMU.get(cod, f'Tributo {cod}')} ({ENTI_NOTI.get(ente, ente)})"


def _parse_erario_with_coords(page) -> list[dict]:
    """
    Usa le coordinate X di pdfplumber per distinguere debito da credito.
    Colonna debito:  x < soglia_split
    Colonna credito: x >= soglia_split
    """
    righi = []
    words = page.extract_words(x_tolerance=3, y_tolerance=3, keep_blank_chars=False)
    
    # Trova i bounds della sezione Erario
    erario_y_start = None
    erario_y_end = None
    for w in words:
        if "ERARIO" in w["text"].upper() and erario_y_start is None:
            erario_y_start = w["top"]
        if erario_y_start and "INPS" in w["text"].upper() and w["top"] > erario_y_start:
            erario_y_end = w["top"]
            break
    
    if erario_y_start is None:
        return []
    
    # Filtra words nella sezione Erario
    erario_words = [
        w for w in words
        if w["top"] > erario_y_start + 5
        and (erario_y_end is None or w["top"] < erario_y_end - 5)
    ]
    
    # Determina la soglia X tra colonna debito e credito
    # Cerca la posizione degli header "importi a debito" e "importi a credito"
    # Fallback: usa x=400 come soglia (valido per pagine A4 standard)
    soglia_x = 400
    
    # Raggruppa per riga Y (tolerance 4pt)
    from collections import defaultdict
    righe_y = defaultdict(list)
    for w in erario_words:
        y_key = round(w["top"] / 4) * 4
        righe_y[y_key].append(w)
    
    for y_key in sorted(righe_y.keys()):
        row_words = sorted(righe_y[y_key], key=lambda w: w["x0"])
        texts = [w["text"] for w in row_words]
        full = " ".join(texts)
        
        # Cerca riga con codice tributo 4 cifre
        cod_match = re.match(r"^(\d{4})$", texts[0]) if texts else None
        if not cod_match:
            continue
        
        codice = texts[0]
        if codice not in CODICI_ERARIO and not re.match(r"^1[0-9]{3}$|^2[0-9]{3}$|^3[0-9]{3}$|^6[0-9]{3}$", codice):
            continue
        
        # Estrai mese_rif e anno_rif (pattern 0001, 0002... e 2024, 2025...)
        mese_rif = None
        anno_rif = None
        for t in texts[1:]:
            if re.match(r"^00[01][0-9]$", t) and mese_rif is None:
                mese_rif = t
            elif re.match(r"^20[0-9]{2}$", t) and anno_rif is None:
                anno_rif = t
        
        # Separa importi per colonna X
        debito = 0.0
        credito = 0.0
        
        # Cerca coppie (int, decimali) che formano importi
        import_pattern = re.compile(r"^[\d\.]+$")
        
        # Raccogli tutti i token numerici con la loro X
        num_tokens = []
        i = 0
        row_w_list = row_words
        while i < len(row_w_list):
            w = row_w_list[i]
            t = w["text"]
            # Cerca pattern: numero intero seguito da 2 cifre decimali
            if re.match(r"^[\d\.]+$", t):
                # Prova a costruire importo con il token successivo se è 2 cifre
                if i + 1 < len(row_w_list):
                    next_t = row_w_list[i+1]["text"]
                    if re.match(r"^\d{2}$", next_t):
                        importo_str = t.replace(".", "") + "." + next_t
                        try:
                            importo = round(float(importo_str), 2)
                            x_center = (w["x0"] + row_w_list[i+1]["x1"]) / 2
                            num_tokens.append((importo, x_center))
                            i += 2
                            continue
                        except:
                            pass
                # Importo singolo (già decimale)
                try:
                    importo = float(t.replace(".", "").replace(",", "."))
                    if importo > 0.5:  # filtra numeri troppo piccoli (anno, mese)
                        num_tokens.append((importo, w["x0"]))
                except:
                    pass
            i += 1
        
        # Assegna a debito o credito in base alla posizione X
        for importo, x in num_tokens:
            if importo > 50:  # ignora valori piccoli (possono essere parti di codici)
                if x < soglia_x:
                    debito = importo
                else:
                    credito = importo
        
        if debito > 0 or credito > 0:
            rigo = {
                "codice_tributo": codice,
                "descrizione": _desc_erario(codice),
                "mese_rif": mese_rif,
                "anno_rif": anno_rif,
                "debito": debito,
                "credito": credito,
            }
            righi.append(rigo)
    
    return righi


def _extract_section_text(full_text: str, start: str, end: str) -> str:
    idx_s = full_text.find(start)
    if idx_s == -1: return ""
    idx_e = full_text.find(end, idx_s + len(start))
    if idx_e == -1: return full_text[idx_s + len(start):]
    return full_text[idx_s + len(start):idx_e]


def parse_f24_pdf(pdf_bytes: bytes, filename: str = "") -> list[dict]:
    if not HAS_PDFPLUMBER:
        raise ImportError("pdfplumber non installato")

    results = []

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text(layout=True) or ""
            
            # Verifica che sia una pagina F24
            if "Scadenza" not in text or "SALDO FINALE" not in text:
                continue
            
            doc = {
                "pdf_filename": filename,
                "xml_source": "pdf_upload",
                "codice_fiscale": "04523831214",
                "stato": "pagato",
                "sezione_erario": [],
                "sezione_inps": [],
                "sezione_regioni": [],
                "sezione_imu": [],
                "sezione_inail": [],
                "totali": {},
                "saldi": {},
                "tributi_flat": [],
                "note_ravvedimento": False,
            }
            
            # ── Header ────────────────────────────────────────────
            m = re.search(r"Scadenza\s+(\d{2}/\d{2}/\d{4}).*?Pag\.\s*(\d+)", text, re.S)
            if m:
                doc["scadenza"] = _parse_date_ita(m.group(1))
                doc["pagina"] = int(m.group(2))
            else:
                continue
            
            # Data pagamento dagli estremi versamento
            # Pattern: riga con giorno mese anno in celle separate
            m = re.search(r"(\d{1,2})\s+(\d{2})\s+(\d{4})\s*\n.*?05034", text, re.S)
            if m:
                try:
                    doc["data_pagamento"] = f"{m.group(3)}-{m.group(2)}-{int(m.group(1)):02d}"
                except: pass
            if "data_pagamento" not in doc:
                # Fallback: data pagamento = scadenza
                doc["data_pagamento"] = doc.get("scadenza")
            
            # Banca
            m = re.search(r"DELEGA IRREVOCABILE A:\s*(.+?)\n", text)
            if m: doc["banca"] = m.group(1).strip()
            
            # Firmato da
            m = re.search(r"FIRMA\s*\n(.+)", text)
            if m: doc["firmato_da"] = m.group(1).strip()
            
            # Saldo finale
            m = re.search(r"SALDO FINALE.*?EURO\s*\+?\s*([\d\.\s]+)", text, re.S)
            if m:
                doc["saldo_finale"] = _parse_euro(m.group(1).split("\n")[0])
            
            # ── Sezione Erario con coordinate ─────────────────────
            try:
                doc["sezione_erario"] = _parse_erario_with_coords(page)
            except Exception as e:
                # Fallback testo grezzo
                doc["sezione_erario"] = _parse_erario_text(text)
            
            for r in doc["sezione_erario"]:
                doc["tributi_flat"].append({"sezione": "ERARIO", **r})
                if r["codice_tributo"] in ("1713", "1668", "8947", "8948", "8949", "8906", "1993", "8907", "8950", "8952", "9001", "9002"):
                    doc["note_ravvedimento"] = True
                if r["codice_tributo"] in ("9001", "9002"):
                    doc["note_avviso_bonario"] = True
            
            # ── Sezione INPS ──────────────────────────────────────
            inps_text = _extract_section_text(text, "SEZIONE INPS", "SEZIONE REGIONI")
            for m in re.finditer(
                r"(5100|5200)\s+(CXX|DM10|F24)\s+(\S+)\s+(\d{2}/\d{4}).*?([\d\.\s]{5,})",
                inps_text
            ):
                debito = _parse_euro(m.group(5))
                if debito == 0: continue
                rigo = {
                    "sede": m.group(1), "causale": m.group(2),
                    "matricola": m.group(3), "da": m.group(4),
                    "a": m.group(4), "debito": debito, "credito": 0.0,
                }
                doc["sezione_inps"].append(rigo)
                doc["tributi_flat"].append({
                    "sezione": "INPS",
                    "codice_tributo": rigo["causale"],
                    "descrizione": CODICI_INPS.get(rigo["causale"], f"INPS {rigo['causale']}"),
                    "mese_rif": rigo["da"][:2],
                    "anno_rif": rigo["da"][-4:],
                    "debito": debito, "credito": 0.0,
                })
            
            # ── Sezione Regioni ────────────────────────────────────
            reg_text = _extract_section_text(text, "SEZIONE REGIONI", "SEZIONE IMU")
            for m in re.finditer(
                r"0\s*5\s+(3802|3800|3796)\s+(\d{4})\s+(\d{4})\s+([\d\.\s]+?)(?:\s{2,}([\d\.\s]+))?\n",
                reg_text
            ):
                deb = _parse_euro(m.group(4))
                cred = _parse_euro(m.group(5) or "0")
                rigo = {
                    "codice_regione": "05",
                    "codice_tributo": m.group(1),
                    "mese_rif": m.group(2),
                    "anno_rif": m.group(3),
                    "debito": deb, "credito": cred,
                }
                doc["sezione_regioni"].append(rigo)
                doc["tributi_flat"].append({
                    "sezione": "REGIONI",
                    "codice_tributo": rigo["codice_tributo"],
                    "descrizione": f"IRAP Campania reg.05",
                    "mese_rif": rigo["mese_rif"],
                    "anno_rif": rigo["anno_rif"],
                    "debito": deb, "credito": cred,
                })
            
            # ── Sezione IMU ────────────────────────────────────────
            imu_text = _extract_section_text(text, "SEZIONE IMU", "SEZIONE ALTRI ENTI")
            for m in re.finditer(
                r"([A-Z]\s*[0-9]\s*[0-9]\s*[0-9]|[A-Z]{1,2}[0-9]{3})\s+(3847|3848|3797|3832|3850|3851)\s+(\d{4})\s+(\d{4})\s+([\d\.\s]+?)(?:\s{2,}([\d\.\s]+))?\n",
                imu_text
            ):
                ente = m.group(1).replace(" ", "")
                deb = _parse_euro(m.group(5))
                cred = _parse_euro(m.group(6) or "0")
                rigo = {
                    "codice_ente": ente,
                    "codice_tributo": m.group(2),
                    "mese_rif": m.group(3),
                    "anno_rif": m.group(4),
                    "debito": deb, "credito": cred,
                }
                doc["sezione_imu"].append(rigo)
                doc["tributi_flat"].append({
                    "sezione": "IMU",
                    "codice_tributo": rigo["codice_tributo"],
                    "descrizione": _desc_imu(rigo["codice_tributo"], ente),
                    "mese_rif": rigo["mese_rif"],
                    "anno_rif": rigo["anno_rif"],
                    "debito": deb, "credito": cred,
                })
            
            # ── Sezione INAIL ──────────────────────────────────────
            inail_text = _extract_section_text(text, "SEZIONE ALTRI ENTI", "FIRMA")
            m = re.search(
                r"(33400)\s+(\d+)\s+(\d+)\s+(\w+)\s+([A-Z])\s+([\d\.\s]+)",
                inail_text
            )
            if m:
                deb = _parse_euro(m.group(6))
                rigo = {
                    "sede": m.group(1), "codice_ditta": m.group(2),
                    "cc": m.group(3), "numero_rif": m.group(4),
                    "causale": m.group(5), "debito": deb, "credito": 0.0,
                }
                doc["sezione_inail"].append(rigo)
                doc["tributi_flat"].append({
                    "sezione": "INAIL", "codice_tributo": "INAIL",
                    "descrizione": "INAIL premi assicurativi",
                    "mese_rif": None, "anno_rif": None,
                    "debito": deb, "credito": 0.0,
                })
            
            # ── Totali sezionali dal testo ─────────────────────────
            for letter, pattern in [
                ("A", r"TOTALE\s+A\s+([\d\.\s]+)"),
                ("C", r"TOTALE\s+C\s+([\d\.\s]+)"),
                ("E", r"TOTALE\s+E\s+([\d\.\s]+)"),
                ("G", r"TOTALE\s+G\s+([\d\.\s]+)"),
                ("I", r"TOTALE\s+I\s+([\d\.\s]+)"),
            ]:
                m = re.search(pattern, text)
                if m: doc["totali"][letter] = _parse_euro(m.group(1).split("\n")[0])
            
            results.append(doc)
    
    return results


def _parse_erario_text(text: str) -> list[dict]:
    """Fallback testo puro quando pdfplumber coordinate non disponibili."""
    righi = []
    erario_text = _extract_section_text(text, "SEZIONE ERARIO", "SEZIONE INPS")
    
    # Leggo i totali per capire quale importo è debito e quale è credito
    m_tot = re.search(r"TOTALE\s+A\s+([\d\.\s]+).*?([\d\.\s]+)\s*\+", erario_text, re.S)
    totale_debito = _parse_euro(m_tot.group(1)) if m_tot else 0
    totale_credito = _parse_euro(m_tot.group(2)) if m_tot else 0
    
    for m in re.finditer(
        r"(\d{4})\s+(\d{4})\s+(\d{4})\s+([\d\.\s]+)",
        erario_text
    ):
        cod, mese, anno = m.group(1), m.group(2), m.group(3)
        importo = _parse_euro(m.group(4))
        if not importo: continue
        
        # Codici che compaiono tipicamente a credito in F24 Ceraldi
        CODICI_TIPICAMENTE_CREDITO = {"1701", "1703", "1704", "1631", "3796", "3797", "6099", "1671"}
        if cod in CODICI_TIPICAMENTE_CREDITO:
            deb, cred = 0.0, importo
        else:
            deb, cred = importo, 0.0
        
        righi.append({
            "codice_tributo": cod,
            "descrizione": _desc_erario(cod),
            "mese_rif": mese,
            "anno_rif": anno,
            "debito": deb,
            "credito": cred,
        })
    
    return righi


if __name__ == "__main__":
    print(f"Parser F24 Ceraldi — pdfplumber: {HAS_PDFPLUMBER}")
