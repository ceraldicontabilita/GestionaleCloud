# ============================================================
# AGGIUNGERE IN app/services/deduplica.py (dopo cerca_duplicato_movimento)
# ============================================================

async def cerca_duplicato_dipendente(
    codice_fiscale: Optional[str],
    nome: Optional[str],
    cognome: Optional[str],
    data_nascita: Optional[str],
    iban: Optional[str],
    db
) -> Dict[str, Any]:
    """
    Cerca dipendenti duplicati per CF, nome+cognome+nascita o IBAN.
    """
    coll = db["dipendenti"]
    
    # Match 1: codice fiscale
    if codice_fiscale:
        cf_clean = codice_fiscale.strip().upper()
        existing = await coll.find_one(
            {"codice_fiscale": cf_clean},
            {"_id": 0, "id": 1, "nome": 1, "cognome": 1}
        )
        if existing:
            return _result(True, "certo", existing,
                          f"CF identico: {cf_clean}")
    
    # Match 2: nome + cognome + data nascita
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
            return _result(True, "certo", existing,
                          f"Nome+cognome+nascita identici")
    
    # Match 3: nome + cognome senza nascita (probabile)
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
            return _result(True, "probabile", existing,
                          f"Nome+cognome identici (senza data nascita)")
    
    # Match 4: IBAN stipendio
    if iban:
        iban_clean = iban.strip().replace(" ", "").upper()
        existing = await coll.find_one(
            {"iban_cedolino": iban_clean},
            {"_id": 0, "id": 1, "nome": 1, "cognome": 1}
        )
        if existing:
            return _result(True, "probabile", existing,
                          f"IBAN identico: {iban_clean}")
    
    return _result(False)
