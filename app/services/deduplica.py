"""
Deduplica Centralizzata — Gestionale Ceraldi Group
====================================================
Funzioni comuni per verificare duplicati su tutte le entità.
Ogni modulo che crea entità deve chiamare queste funzioni PRIMA
di inserire un nuovo record.

Utilizzo:
    from app.services.deduplica import cerca_duplicato_fattura
    
    dup = await cerca_duplicato_fattura(piva, numero, data, totale, hash_file, db)
    if dup["trovato"]:
        if dup["certezza"] == "certo":
            # Non creare, collega al record esistente
        else:
            # Genera alert DUPLICATO
"""
import logging
import hashlib
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


# ============================================================
# RISULTATO STANDARD
# ============================================================
def _result(trovato: bool, certezza: str = "", record: Optional[Dict] = None,
            motivo: str = "") -> Dict[str, Any]:
    return {
        "trovato": trovato,
        "certezza": certezza,  # "certo" | "probabile" | ""
        "record_esistente": record,
        "motivo": motivo
    }


# ============================================================
# FATTURE
# ============================================================
async def cerca_duplicato_fattura(
    piva: Optional[str],
    numero: Optional[str],
    data: Optional[str],
    totale: Optional[float],
    hash_file: Optional[str],
    db
) -> Dict[str, Any]:
    """
    Cerca fatture duplicate per combinazione P.IVA + numero + data.
    Fallback su hash file.
    """
    coll = db["invoices"]
    
    # Match 1: hash file (certezza assoluta)
    if hash_file:
        existing = await coll.find_one(
            {"hash_file": hash_file},
            {"_id": 0, "id": 1, "invoice_key": 1, "fornitore_denominazione": 1}
        )
        if existing:
            return _result(True, "certo", existing, "Hash file identico")
    
    # Match 2: P.IVA + numero + data (molto forte)
    if piva and numero:
        query = {"fornitore_piva": piva, "numero": numero}
        if data:
            query["data_fattura"] = data
        existing = await coll.find_one(query, {"_id": 0, "id": 1, "invoice_key": 1})
        if existing:
            return _result(True, "certo", existing,
                          f"Stessa P.IVA+numero+data: {piva}/{numero}/{data}")
    
    # Match 3: P.IVA + totale + data (probabile)
    if piva and totale and data:
        existing = await coll.find_one(
            {
                "fornitore_piva": piva,
                "total_amount": {"$gte": totale - 0.05, "$lte": totale + 0.05},
                "data_fattura": data
            },
            {"_id": 0, "id": 1, "invoice_key": 1, "numero": 1}
        )
        if existing:
            return _result(True, "probabile", existing,
                          f"Stessa P.IVA+totale+data: {piva}/{totale}/{data}")
    
    return _result(False)


# ============================================================
# FORNITORI
# ============================================================
async def cerca_duplicato_fornitore(
    piva: Optional[str],
    cf: Optional[str],
    denominazione: Optional[str],
    db
) -> Dict[str, Any]:
    """
    Cerca fornitori duplicati per P.IVA, CF o denominazione simile.
    """
    coll = db["fornitori"]
    
    # Match 1: P.IVA esatta
    if piva:
        piva_clean = piva.strip().replace(" ", "")
        existing = await coll.find_one(
            {"anagrafica.piva": piva_clean},
            {"_id": 0, "id": 1, "anagrafica.ragione_sociale": 1}
        )
        if existing:
            return _result(True, "certo", existing,
                          f"P.IVA identica: {piva_clean}")
    
    # Match 2: CF esatto
    if cf:
        cf_clean = cf.strip().upper()
        existing = await coll.find_one(
            {"anagrafica.codice_fiscale": cf_clean},
            {"_id": 0, "id": 1, "anagrafica.ragione_sociale": 1}
        )
        if existing:
            return _result(True, "certo", existing,
                          f"CF identico: {cf_clean}")
    
    # Match 3: denominazione normalizzata (probabile)
    if denominazione:
        norm = _normalizza_nome(denominazione)
        if len(norm) >= 5:
            # Cerca con regex case-insensitive
            import re
            pattern = re.escape(norm[:20])
            cursor = coll.find(
                {"anagrafica.ragione_sociale": {"$regex": pattern, "$options": "i"}},
                {"_id": 0, "id": 1, "anagrafica.ragione_sociale": 1}
            ).limit(3)
            candidates = await cursor.to_list(3)
            if candidates:
                return _result(True, "probabile", candidates[0],
                              f"Denominazione simile a: {candidates[0].get('anagrafica', {}).get('ragione_sociale', '')}")
    
    return _result(False)


# ============================================================
# CEDOLINI
# ============================================================
async def cerca_duplicato_cedolino(
    dipendente_id: Optional[str],
    mese: Optional[int],
    anno: Optional[int],
    tipo: Optional[str],
    hash_file: Optional[str],
    db
) -> Dict[str, Any]:
    """
    Cerca cedolini duplicati per dipendente + periodo + tipo.
    """
    coll = db["cedolini"]
    
    # Match 1: hash file
    if hash_file:
        existing = await coll.find_one(
            {"hash_file": hash_file},
            {"_id": 0, "id": 1, "dipendente_id": 1, "mese": 1, "anno": 1}
        )
        if existing:
            return _result(True, "certo", existing, "Hash file identico")
    
    # Match 2: dipendente + mese + anno + tipo
    if dipendente_id and mese and anno:
        query = {
            "dipendente_id": dipendente_id,
            "mese": mese,
            "anno": anno
        }
        if tipo:
            query["tipo_cedolino"] = tipo
        existing = await coll.find_one(query, {"_id": 0, "id": 1})
        if existing:
            return _result(True, "certo", existing,
                          f"Stesso dip+mese+anno+tipo: {dipendente_id}/{mese}/{anno}/{tipo}")
    
    return _result(False)


# ============================================================
# F24
# ============================================================
async def cerca_duplicato_f24(
    codice_tributo: Optional[str],
    periodo: Optional[str],
    importo: Optional[float],
    anno: Optional[int],
    hash_file: Optional[str],
    db
) -> Dict[str, Any]:
    """
    Cerca F24 duplicati per tributo + periodo + importo.
    """
    coll = db["f24_unificato"]
    
    # Match 1: hash file
    if hash_file:
        existing = await coll.find_one(
            {"hash_file": hash_file},
            {"_id": 0, "id": 1}
        )
        if existing:
            return _result(True, "certo", existing, "Hash file identico")
    
    # Match 2: tributo + periodo + importo
    if importo and periodo:
        query: Dict[str, Any] = {"periodo": periodo}
        if codice_tributo:
            query["codice_tributo"] = codice_tributo
        if anno:
            query["anno"] = anno
        
        cursor = coll.find(query, {"_id": 0, "id": 1, "importo_totale": 1}).limit(5)
        candidates = await cursor.to_list(5)
        
        for cand in candidates:
            imp_cand = cand.get("importo_totale", 0) or 0
            if abs(imp_cand - importo) < 0.10:
                return _result(True, "certo", cand,
                              f"Stesso tributo+periodo+importo: {codice_tributo}/{periodo}/{importo}")
        
        if candidates:
            return _result(True, "probabile", candidates[0],
                          f"Stesso periodo, importo diverso")
    
    return _result(False)


# ============================================================
# MOVIMENTI BANCARI
# ============================================================
async def cerca_duplicato_movimento(
    conto: Optional[str],
    data: Optional[str],
    importo: Optional[float],
    descrizione: Optional[str],
    transaction_id: Optional[str],
    db
) -> Dict[str, Any]:
    """
    Cerca movimenti bancari duplicati nell'estratto conto.
    """
    coll = db["estratto_conto_movimenti"]
    
    # Match 1: transaction_id
    if transaction_id:
        existing = await coll.find_one(
            {"transaction_id": transaction_id},
            {"_id": 0, "id": 1}
        )
        if existing:
            return _result(True, "certo", existing, "Transaction ID identico")
    
    # Match 2: data + importo + descrizione normalizzata
    if data and importo:
        query: Dict[str, Any] = {
            "data": data,
            "importo": {"$gte": importo - 0.01, "$lte": importo + 0.01}
        }
        if conto:
            query["conto"] = conto
        
        cursor = coll.find(query, {"_id": 0, "id": 1, "descrizione": 1}).limit(5)
        candidates = await cursor.to_list(5)
        
        if descrizione and candidates:
            desc_norm = _normalizza_nome(descrizione)
            for cand in candidates:
                cand_norm = _normalizza_nome(cand.get("descrizione", ""))
                if desc_norm == cand_norm or (len(desc_norm) > 10 and desc_norm[:15] == cand_norm[:15]):
                    return _result(True, "certo", cand,
                                  "Data+importo+descrizione identici")
        
        if candidates:
            return _result(True, "probabile", candidates[0],
                          f"Data+importo identici, descrizione diversa")
    
    return _result(False)


# ============================================================
# UTILITY
# ============================================================
def _normalizza_nome(testo: str) -> str:
    """Normalizza un testo per confronto: minuscolo, senza spazi doppi, senza punteggiatura."""
    if not testo:
        return ""
    import re
    t = testo.lower().strip()
    t = re.sub(r'[^\w\s]', '', t)  # rimuovi punteggiatura
    t = re.sub(r'\s+', ' ', t)     # riduci spazi multipli
    return t


def calcola_hash_file(contenuto: bytes) -> str:
    """Calcola SHA256 di un contenuto file."""
    return hashlib.sha256(contenuto).hexdigest()


# ============================================================
# cerca_duplicato_dipendente (Chat 9d)
# ============================================================
async def cerca_duplicato_dipendente(
    codice_fiscale: Optional[str],
    nome: Optional[str],
    cognome: Optional[str],
    data_nascita: Optional[str],
    iban: Optional[str],
    db
) -> Dict[str, Any]:
    """Cerca dipendenti duplicati per CF, nome+cognome+nascita o IBAN."""
    coll = db["dipendenti"]

    if codice_fiscale:
        cf_clean = codice_fiscale.strip().upper()
        existing = await coll.find_one(
            {"codice_fiscale": cf_clean},
            {"_id": 0, "id": 1, "nome": 1, "cognome": 1}
        )
        if existing:
            return _result(True, "certo", existing, f"CF identico: {cf_clean}")

    if nome and cognome and data_nascita:
        import re
        nome_norm = re.sub(r'\s+', ' ', nome.strip().upper())
        cognome_norm = re.sub(r'\s+', ' ', cognome.strip().upper())
        existing = await coll.find_one(
            {
                "nome": {"$regex": f"^{re.escape(nome_norm)}$", "$options": "i"},
                "cognome": {"$regex": f"^{re.escape(cognome_norm)}$", "$options": "i"},
                "data_nascita": data_nascita
            },
            {"_id": 0, "id": 1, "nome": 1, "cognome": 1}
        )
        if existing:
            return _result(True, "certo", existing, "Nome+cognome+nascita identici")

    if nome and cognome:
        import re
        nome_norm = re.sub(r'\s+', ' ', nome.strip().upper())
        cognome_norm = re.sub(r'\s+', ' ', cognome.strip().upper())
        existing = await coll.find_one(
            {
                "nome": {"$regex": f"^{re.escape(nome_norm)}$", "$options": "i"},
                "cognome": {"$regex": f"^{re.escape(cognome_norm)}$", "$options": "i"},
            },
            {"_id": 0, "id": 1, "nome": 1, "cognome": 1}
        )
        if existing:
            return _result(True, "probabile", existing, "Nome+cognome identici (senza data nascita)")

    if iban:
        iban_clean = iban.strip().replace(" ", "").upper()
        existing = await coll.find_one(
            {"iban_cedolino": iban_clean},
            {"_id": 0, "id": 1, "nome": 1, "cognome": 1}
        )
        if existing:
            return _result(True, "probabile", existing, f"IBAN identico: {iban_clean}")

    return _result(False)
