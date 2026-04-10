"""
API Salari Unificati V2 - Endpoint per gestione completa stipendi.

Endpoint:
- GET  /saldo/{cf}           → Saldo completo dipendente (stipendi + ferie + ROL + TFR)
- GET  /riepilogo             → Riepilogo tutti dipendenti con evidenziazione debiti
- POST /pagamento             → Registra pagamento (acconto o saldo)
- POST /riconcilia-banca      → Riconcilia cedolini con estratto conto
- GET  /non-pagati            → Lista cedolini non pagati o parziali
- GET  /ferie-rol             → Saldi ferie e ROL per tutti i dipendenti
"""

from fastapi import APIRouter, HTTPException, Query, Body
from typing import Dict, Any, Optional
import logging

from app.database import Database
from app.utils.error_handler import handle_errors

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/saldo/{codice_fiscale}")
@handle_errors
async def get_saldo_dipendente(
    codice_fiscale: str,
    anno: Optional[int] = Query(None)
) -> Dict[str, Any]:
    """
    Saldo completo di un dipendente:
    - Stipendi: netto, pagato, residuo, storico acconti
    - Ferie: maturate, godute, residue (anno corrente + AP)
    - ROL: maturato, goduto, residuo
    - TFR: accantonamento mese, totale
    - Permessi ex-festività
    """
    from app.services.salari_unificati_v2 import get_saldo_completo_dipendente
    db = Database.get_db()
    return await get_saldo_completo_dipendente(db, codice_fiscale=codice_fiscale, anno=anno)


@router.get("/riepilogo")
@handle_errors
async def riepilogo_tutti_dipendenti(
    anno: Optional[int] = Query(None)
) -> Dict[str, Any]:
    """
    Riepilogo salari per TUTTI i dipendenti.
    Evidenzia chi ha debiti residui o cedolini non pagati.
    Mostra saldo debito/credito, ferie, ROL.
    """
    from app.services.salari_unificati_v2 import get_riepilogo_salari_tutti
    db = Database.get_db()
    return await get_riepilogo_salari_tutti(db, anno=anno)


@router.post("/pagamento")
@handle_errors
async def registra_pagamento(
    data: Dict[str, Any] = Body(...)
) -> Dict[str, Any]:
    """
    Registra pagamento (acconto o saldo) per un cedolino.
    
    Body:
    - cedolino_id: ID del cedolino
    - importo: importo pagato
    - metodo: "bonifico" | "assegno" | "contanti" (vietato post-2018)
    - data_pagamento: "YYYY-MM-DD" (opzionale, default oggi)
    - tipo: "acconto" | "saldo"
    - note: note libere
    """
    from app.services.salari_unificati_v2 import registra_pagamento_salario
    
    db = Database.get_db()
    
    cedolino_id = data.get("cedolino_id")
    importo = float(data.get("importo", 0))
    metodo = data.get("metodo", "bonifico")
    data_pag = data.get("data_pagamento")
    tipo = data.get("tipo", "saldo")
    note = data.get("note", "")
    
    if not cedolino_id:
        raise HTTPException(status_code=400, detail="cedolino_id richiesto")
    if importo <= 0:
        raise HTTPException(status_code=400, detail="importo deve essere > 0")
    
    # Validazione contanti post-2018
    cedolino = await db["cedolini"].find_one({"id": cedolino_id})
    if cedolino and metodo.lower() in ["contanti", "cassa", "cash"]:
        anno_ced = int(cedolino.get("anno", 0))
        mese_ced = int(cedolino.get("mese", 0))
        if anno_ced > 2018 or (anno_ced == 2018 and mese_ced >= 7):
            raise HTTPException(
                status_code=422,
                detail="Pagamento stipendio in contanti vietato dal 1/7/2018 (L.205/2017)"
            )
    
    return await registra_pagamento_salario(
        db, cedolino_id, importo, metodo, data_pag, note, tipo
    )


@router.post("/riconcilia-banca")
@handle_errors
async def riconcilia_cedolini_banca(
    data: Dict[str, Any] = Body(...)
) -> Dict[str, Any]:
    """
    Riconcilia cedolini non pagati con movimenti estratto conto.
    Cerca corrispondenze per nome/IBAN/importo e registra pagamenti.
    """
    from app.services.cedolini_manager import riconcilia_stipendio_automatico
    
    db = Database.get_db()
    anno = data.get("anno", None)
    from datetime import datetime as dt
    if not anno:
        anno = dt.now().year
    
    # Cedolini non completamente pagati
    cedolini = await db["cedolini"].find({
        "anno": {"$in": [anno, str(anno)]},
        "pagato": {"$ne": True}
    }, {"_id": 0}).to_list(500)
    
    riconciliati = 0
    errori = []
    dettagli = []
    
    for ced in cedolini:
        cf = ced.get("codice_fiscale")
        nome = ced.get("nome_dipendente", "")
        netto = float(ced.get("netto") or ced.get("netto_mese") or 0)
        importo_pagato = float(ced.get("importo_pagato") or 0)
        residuo = netto - importo_pagato
        mese = int(ced.get("mese", 0))
        
        if residuo <= 0.01 or not cf:
            continue
        
        # Cerca match nell'estratto conto
        pn_id = ced.get("id", "")
        riconc = await riconcilia_stipendio_automatico(
            db, nome, residuo, mese, anno, pn_id, ced.get("iban")
        )
        
        if riconc:
            # Registra pagamento
            from app.services.salari_unificati_v2 import registra_pagamento_salario
            await registra_pagamento_salario(
                db, ced["id"], residuo, "bonifico",
                note=f"Riconciliazione automatica estratto conto",
                tipo_pagamento="saldo"
            )
            riconciliati += 1
            dettagli.append({
                "nome": nome,
                "periodo": f"{mese}/{anno}",
                "importo": residuo
            })
        else:
            errori.append({
                "nome": nome,
                "periodo": f"{mese}/{anno}",
                "residuo": residuo,
                "motivo": "Nessun match in estratto conto"
            })
    
    return {
        "riconciliati": riconciliati,
        "non_trovati": len(errori),
        "dettagli_riconciliati": dettagli,
        "da_verificare": errori[:20]
    }


@router.get("/non-pagati")
@handle_errors
async def get_cedolini_non_pagati(
    anno: Optional[int] = Query(None)
) -> Dict[str, Any]:
    """
    Lista cedolini non pagati o parzialmente pagati.
    Evidenzia importi residui per ciascun dipendente.
    """
    db = Database.get_db()
    from datetime import datetime as dt
    
    if not anno:
        anno = dt.now().year
    
    cedolini = await db["cedolini"].find({
        "anno": {"$in": [anno, str(anno)]},
        "pagato": {"$ne": True}
    }, {"_id": 0}).sort([("nome_dipendente", 1), ("mese", 1)]).to_list(500)
    
    # Raggruppa per dipendente
    per_dipendente = {}
    for c in cedolini:
        nome = c.get("nome_dipendente", "Sconosciuto")
        if nome not in per_dipendente:
            per_dipendente[nome] = {
                "nome": nome,
                "codice_fiscale": c.get("codice_fiscale"),
                "mesi": [],
                "totale_netto": 0,
                "totale_pagato": 0,
                "totale_residuo": 0
            }
        
        netto = float(c.get("netto") or c.get("netto_mese") or 0)
        pagato = float(c.get("importo_pagato") or 0)
        residuo = netto - pagato
        
        per_dipendente[nome]["mesi"].append({
            "cedolino_id": c.get("id"),
            "mese": c.get("mese"),
            "netto": netto,
            "pagato": pagato,
            "residuo": round(residuo, 2),
            "acconti": len(c.get("pagamenti", []))
        })
        per_dipendente[nome]["totale_netto"] += netto
        per_dipendente[nome]["totale_pagato"] += pagato
        per_dipendente[nome]["totale_residuo"] += residuo
    
    # Arrotonda e ordina per residuo desc
    lista = list(per_dipendente.values())
    for d in lista:
        d["totale_netto"] = round(d["totale_netto"], 2)
        d["totale_pagato"] = round(d["totale_pagato"], 2)
        d["totale_residuo"] = round(d["totale_residuo"], 2)
    lista.sort(key=lambda x: -x["totale_residuo"])
    
    return {
        "anno": anno,
        "dipendenti_con_residui": lista,
        "totale_residuo_globale": round(sum(d["totale_residuo"] for d in lista), 2),
        "conteggio_cedolini": len(cedolini)
    }


@router.get("/ferie-rol")
@handle_errors
async def get_ferie_rol_tutti(
    anno: Optional[int] = Query(None)
) -> Dict[str, Any]:
    """
    Saldi ferie e ROL per tutti i dipendenti attivi.
    Dati estratti dall'ultimo cedolino di ciascun dipendente.
    """
    db = Database.get_db()
    from datetime import datetime as dt
    
    if not anno:
        anno = dt.now().year
    
    dipendenti = await db["dipendenti"].find(
        {"stato": {"$ne": "cessato"}},
        {"_id": 0}
    ).sort("cognome", 1).to_list(200)
    
    risultati = []
    
    for dip in dipendenti:
        cf = dip.get("codice_fiscale")
        if not cf:
            continue
        
        # Ultimo cedolino dell'anno
        ultimo = await db["cedolini"].find_one(
            {"codice_fiscale": cf, "anno": {"$in": [anno, str(anno)]}},
            {"_id": 0},
            sort=[("mese", -1)]
        )
        
        ferie = float(dip.get("ferie_residue") or (ultimo or {}).get("ferie_residue") or 0)
        rol = float(dip.get("rol_residuo") or (ultimo or {}).get("rol_residuo") or 0)
        exf = float(dip.get("permessi_ex_fest_residui") or (ultimo or {}).get("permessi_ex_fest") or 0)
        tfr = float(dip.get("tfr_accantonato") or (ultimo or {}).get("tfr_accantonato") or 0)
        
        risultati.append({
            "nome": dip.get("nome_completo") or f"{dip.get('cognome', '')} {dip.get('nome', '')}",
            "codice_fiscale": cf,
            "ultimo_cedolino": (ultimo or {}).get("periodo", dip.get("ultimo_cedolino", "N/D")),
            "ferie_residue": round(ferie, 2),
            "ferie_maturate": round(float(dip.get("ferie_maturate_anno") or (ultimo or {}).get("ferie_maturate") or 0), 2),
            "ferie_godute": round(float(dip.get("ferie_godute_anno") or (ultimo or {}).get("ferie_godute") or 0), 2),
            "rol_residuo": round(rol, 2),
            "rol_maturato": round(float(dip.get("rol_maturato_anno") or (ultimo or {}).get("rol_maturato") or 0), 2),
            "rol_goduto": round(float(dip.get("rol_goduto_anno") or (ultimo or {}).get("rol_goduto") or 0), 2),
            "permessi_ex_fest": round(exf, 2),
            "tfr_accantonato": round(tfr, 2),
        })
    
    return {
        "anno": anno,
        "dipendenti": risultati,
        "totali": {
            "ferie_residue_totali": round(sum(r["ferie_residue"] for r in risultati), 2),
            "rol_residuo_totale": round(sum(r["rol_residuo"] for r in risultati), 2),
            "tfr_totale": round(sum(r["tfr_accantonato"] for r in risultati), 2),
        }
    }
