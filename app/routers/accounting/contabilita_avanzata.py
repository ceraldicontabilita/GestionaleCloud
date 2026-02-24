"""
Router Contabilità Avanzata

Endpoint per:
- Categorizzazione intelligente fatture → Piano dei Conti
- Calcolo IRES/IRAP in tempo reale
- Rielaborazione massiva delle fatture
- Bilancio dettagliato con deducibilità
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from typing import Dict, Any
from datetime import datetime, timezone
import uuid
import logging
import io

from app.database import Database
from app.services.categorizzazione_contabile import (
    get_categorizzatore,
    categorizza_fattura_completa,
    PIANO_CONTI_ESTESO
)
from app.services.calcolo_imposte import CalcolatoreImposte, ALIQUOTE_IRAP

# PDF generation
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from app.utils.error_handler import handle_errors

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/piano-conti-esteso")
@handle_errors
async def get_piano_conti_esteso() -> Dict[str, Any]:
    """
    Restituisce il Piano dei Conti esteso con tutte le voci
    necessarie per una contabilità precisa.
    """
    db = Database.get_db()
    
    # Verifica se il piano esteso è già nel DB
    conti_db = await db["piano_conti"].find({}, {"_id": 0}).to_list(500)
    
    # Crea lista completa
    conti_completi = []
    codici_esistenti = {c.get("codice") for c in conti_db}
    
    # Aggiungi conti mancanti
    for codice, info in PIANO_CONTI_ESTESO.items():
        if codice in codici_esistenti:
            # Conto esistente - recupera dal DB
            conto_db = next((c for c in conti_db if c.get("codice") == codice), None)
            if conto_db:
                conti_completi.append(conto_db)
        else:
            # Conto nuovo - aggiungi con saldo 0
            conti_completi.append({
                "codice": codice,
                "nome": info["nome"],
                "categoria": info["categoria"],
                "natura": info["natura"],
                "saldo": 0,
                "nuovo": True
            })
    
    # Ordina per codice
    conti_completi.sort(key=lambda x: x.get("codice", ""))
    
    # Raggruppa per categoria
    grouped = {}
    for conto in conti_completi:
        cat = conto.get("categoria", "altro")
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append(conto)
    
    return {
        "conti": conti_completi,
        "grouped": grouped,
        "totale_conti": len(conti_completi),
        "conti_nuovi": len([c for c in conti_completi if c.get("nuovo")])
    }


@router.post("/inizializza-piano-esteso")
@handle_errors
async def inizializza_piano_conti_esteso() -> Dict[str, Any]:
    """
    Inizializza/aggiorna il Piano dei Conti con tutte le voci estese.
    Preserva i saldi esistenti.
    """
    db = Database.get_db()
    
    # Recupera conti esistenti
    conti_esistenti = await db["piano_conti"].find({}, {"_id": 0}).to_list(500)
    saldi_esistenti = {c.get("codice"): c.get("saldo", 0) for c in conti_esistenti}
    
    conti_aggiunti = 0
    conti_aggiornati = 0
    now = datetime.now(timezone.utc).isoformat()
    
    for codice, info in PIANO_CONTI_ESTESO.items():
        existing = await db["piano_conti"].find_one({"codice": codice})
        
        if existing:
            # Aggiorna solo nome e categoria se diversi
            if existing.get("nome") != info["nome"] or existing.get("categoria") != info["categoria"]:
                await db["piano_conti"].update_one(
                    {"codice": codice},
                    {"$set": {
                        "nome": info["nome"],
                        "categoria": info["categoria"],
                        "natura": info["natura"],
                        "updated_at": now
                    }}
                )
                conti_aggiornati += 1
        else:
            # Crea nuovo conto
            nuovo_conto = {
                "id": str(uuid.uuid4()),
                "codice": codice,
                "nome": info["nome"],
                "categoria": info["categoria"],
                "natura": info["natura"],
                "gruppo_codice": codice[:2],
                "attivo": True,
                "saldo": 0,
                "created_at": now,
                "updated_at": now
            }
            await db["piano_conti"].insert_one(nuovo_conto.copy())
            conti_aggiunti += 1
    
    return {
        "success": True,
        "conti_aggiunti": conti_aggiunti,
        "conti_aggiornati": conti_aggiornati,
        "totale_piano_conti": len(PIANO_CONTI_ESTESO)
    }


@router.post("/ricategorizza-fatture")
@handle_errors
async def ricategorizza_tutte_fatture() -> Dict[str, Any]:
    """
    Ricategorizza TUTTE le fatture esistenti usando il sistema
    di categorizzazione intelligente.
    
    Per ogni fattura:
    1. Analizza le descrizioni delle linee
    2. Determina il conto corretto
    3. Aggiorna i movimenti contabili
    4. Ricalcola i saldi del piano dei conti
    """
    db = Database.get_db()
    categorizzatore = get_categorizzatore()
    
    # Reset saldi piano dei conti (tranne cassa/banca popolati da altre fonti)
    conti_da_non_resettare = ["01.01.01", "01.01.02"]  # Cassa, Banca
    await db["piano_conti"].update_many(
        {"codice": {"$nin": conti_da_non_resettare}},
        {"$set": {"saldo": 0}}
    )
    
    # Elimina movimenti contabili esistenti
    await db["movimenti_contabili"].delete_many({})
    
    # Processa tutte le fatture
    fatture = await db["invoices"].find({
        "$or": [
            {"entity_status": {"$ne": "deleted"}},
            {"entity_status": {"$exists": False}}
        ]
    }, {"_id": 0}).to_list(10000)
    
    stats = {
        "fatture_processate": 0,
        "movimenti_creati": 0,
        "errori": [],
        "categorie": {},
        "conti_utilizzati": {}
    }
    
    for fattura in fatture:
        try:
            fattura_id = fattura.get("id")
            if not fattura_id:
                continue
            
            linee = fattura.get("linee", [])
            fornitore = fattura.get("supplier_name", "")
            
            # Categorizza la fattura
            categorizzazione = categorizza_fattura_completa(linee, fornitore)
            
            # Estrai importi
            importo_totale = float(fattura.get("total_amount", 0) or 0)
            iva = float(fattura.get("iva", fattura.get("total_tax", 0)) or 0)
            imponibile = importo_totale - iva if importo_totale > iva else importo_totale
            
            if importo_totale <= 0:
                continue
            
            # Determina conto costo principale dalla categorizzazione
            conto_costo = "05.01.01"  # Default
            conto_nome = "Acquisto merci"
            
            if categorizzazione["riepilogo_conti"]:
                # Usa il conto con importo maggiore
                conto_principale = max(
                    categorizzazione["riepilogo_conti"],
                    key=lambda x: x["importo"]
                )
                conto_costo = conto_principale["codice"]
                conto_nome = conto_principale["nome"]
            
            # Crea movimento contabile
            movimento_id = str(uuid.uuid4())
            data_fattura = fattura.get("invoice_date", datetime.now(timezone.utc).isoformat()[:10])
            
            movimento = {
                "id": movimento_id,
                "tipo": "fattura_acquisto",
                "data": data_fattura,
                "descrizione": f"Fattura {fattura.get('invoice_number', '')} - {fornitore}",
                "fattura_id": fattura_id,
                "categoria_principale": categorizzazione["categoria_principale"],
                "percentuale_deducibilita_ires": categorizzazione["percentuale_deducibilita_ires"],
                "percentuale_deducibilita_irap": categorizzazione["percentuale_deducibilita_irap"],
                "righe": [
                    {
                        "conto_codice": conto_costo,
                        "conto_nome": conto_nome,
                        "dare": imponibile,
                        "avere": 0
                    },
                    {
                        "conto_codice": "01.04.01",
                        "conto_nome": "IVA a credito",
                        "dare": iva,
                        "avere": 0
                    },
                    {
                        "conto_codice": "02.01.01",
                        "conto_nome": "Debiti v/fornitori",
                        "dare": 0,
                        "avere": importo_totale
                    }
                ],
                "totale_dare": imponibile + iva,
                "totale_avere": importo_totale,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            await db["movimenti_contabili"].insert_one(movimento.copy())
            
            # Aggiorna saldi conti
            await aggiorna_saldo_conto(db, conto_costo, imponibile, "dare")
            await aggiorna_saldo_conto(db, "01.04.01", iva, "dare")
            await aggiorna_saldo_conto(db, "02.01.01", importo_totale, "avere")
            
            # Aggiorna fattura con categorizzazione
            await db["invoices"].update_one(
                {"id": fattura_id},
                {"$set": {
                    "registrata_contabilita": True,
                    "movimento_contabile_id": movimento_id,
                    "categoria_contabile": categorizzazione["categoria_principale"],
                    "conto_costo_codice": conto_costo,
                    "conto_costo_nome": conto_nome,
                    "percentuale_deducibilita_ires": categorizzazione["percentuale_deducibilita_ires"],
                    "percentuale_deducibilita_irap": categorizzazione["percentuale_deducibilita_irap"]
                }}
            )
            
            # Aggiorna statistiche
            stats["fatture_processate"] += 1
            stats["movimenti_creati"] += 1
            
            cat = categorizzazione["categoria_principale"]
            stats["categorie"][cat] = stats["categorie"].get(cat, 0) + 1
            stats["conti_utilizzati"][conto_costo] = stats["conti_utilizzati"].get(conto_costo, 0) + 1
            
        except Exception as e:
            stats["errori"].append(f"Fattura {fattura.get('invoice_number', 'N/A')}: {str(e)}")
    
    # Registra anche i corrispettivi
    corrispettivi = await db["corrispettivi"].find({}, {"_id": 0}).to_list(5000)
    
    for corr in corrispettivi:
        try:
            corr_id = corr.get("id")
            if not corr_id:
                continue
            
            totale = float(corr.get("totale", 0) or 0)
            if totale <= 0:
                continue
            
            # Calcola IVA (10% per ristorazione)
            aliquota = 0.10
            iva = round(totale * aliquota / (1 + aliquota), 2)
            imponibile = totale - iva
            
            # Importi per tipo pagamento
            cassa = float(corr.get("pagato_contante", corr.get("pagato_cassa", 0)) or 0)
            pos = float(corr.get("pagato_elettronico", 0) or 0)
            
            if cassa + pos == 0:
                cassa = totale
            
            # Crea movimento
            movimento_id = str(uuid.uuid4())
            data_corr = corr.get("data", datetime.now(timezone.utc).isoformat()[:10])
            
            righe = []
            
            if cassa > 0:
                righe.append({
                    "conto_codice": "01.01.01",
                    "conto_nome": "Cassa",
                    "dare": cassa,
                    "avere": 0
                })
            
            if pos > 0:
                righe.append({
                    "conto_codice": "01.01.02",
                    "conto_nome": "Banca c/c",
                    "dare": pos,
                    "avere": 0
                })
            
            righe.extend([
                {
                    "conto_codice": "04.01.02",
                    "conto_nome": "Ricavi vendite bar",
                    "dare": 0,
                    "avere": imponibile
                },
                {
                    "conto_codice": "02.03.01",
                    "conto_nome": "IVA a debito",
                    "dare": 0,
                    "avere": iva
                }
            ])
            
            movimento = {
                "id": movimento_id,
                "tipo": "corrispettivo",
                "data": data_corr,
                "descrizione": f"Corrispettivo del {data_corr}",
                "corrispettivo_id": corr_id,
                "righe": righe,
                "totale_dare": cassa + pos,
                "totale_avere": totale,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            await db["movimenti_contabili"].insert_one(movimento.copy())
            
            # Aggiorna saldi
            if cassa > 0:
                await aggiorna_saldo_conto(db, "01.01.01", cassa, "dare")
            if pos > 0:
                await aggiorna_saldo_conto(db, "01.01.02", pos, "dare")
            await aggiorna_saldo_conto(db, "04.01.02", imponibile, "avere")
            await aggiorna_saldo_conto(db, "02.03.01", iva, "avere")
            
            # Marca corrispettivo
            await db["corrispettivi"].update_one(
                {"id": corr_id},
                {"$set": {"registrato_contabilita": True, "movimento_contabile_id": movimento_id}}
            )
            
        except Exception as e:
            stats["errori"].append(f"Corrispettivo {corr.get('id', 'N/A')}: {str(e)}")
    
    return {
        "success": True,
        **stats,
        "errori": stats["errori"][:20]
    }


async def aggiorna_saldo_conto(db, codice_conto: str, importo: float, tipo: str):
    """Aggiorna il saldo di un conto nel piano dei conti."""
    # Crea il conto se non esiste
    conto = await db["piano_conti"].find_one({"codice": codice_conto})
    
    if not conto:
        info = PIANO_CONTI_ESTESO.get(codice_conto, {
            "nome": f"Conto {codice_conto}",
            "categoria": "costi" if codice_conto.startswith("05") else "altro",
            "natura": "economico"
        })
        conto = {
            "id": str(uuid.uuid4()),
            "codice": codice_conto,
            "nome": info["nome"],
            "categoria": info["categoria"],
            "natura": info["natura"],
            "saldo": 0,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db["piano_conti"].insert_one(conto.copy())
    
    categoria = conto.get("categoria", "")
    saldo_attuale = float(conto.get("saldo", 0) or 0)
    
    # Regola contabile:
    # ATTIVO e COSTI: DARE aumenta, AVERE diminuisce
    # PASSIVO, PN e RICAVI: AVERE aumenta, DARE diminuisce
    if categoria in ["attivo", "costi"]:
        nuovo_saldo = saldo_attuale + importo if tipo == "dare" else saldo_attuale - importo
    else:
        nuovo_saldo = saldo_attuale + importo if tipo == "avere" else saldo_attuale - importo
    
    await db["piano_conti"].update_one(
        {"codice": codice_conto},
        {"$set": {"saldo": nuovo_saldo, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )


@router.get("/calcolo-imposte")
@handle_errors
async def calcola_imposte_realtime(
    regione: str = Query("default", description="Regione per aliquota IRAP"),
    anno: int = Query(default=None, description="Anno fiscale (default: tutti)")
) -> Dict[str, Any]:
    """
    Calcola IRES e IRAP in tempo reale basandosi sui dati contabili.
    
    Restituisce:
    - Utile civilistico
    - Variazioni fiscali in aumento/diminuzione
    - Reddito imponibile
    - IRES dovuta
    - Base imponibile IRAP
    - IRAP dovuta
    - Totale imposte
    - Aliquota effettiva
    """
    db = Database.get_db()
    calcolatore = CalcolatoreImposte(regione)
    
    try:
        risultato = await calcolatore.calcola_imposte_da_db(db, anno)
        
        anno_label = anno if anno else "tutti gli anni"
        
        # Converti in dict per JSON
        return {
            "anno": anno,
            "utile_civilistico": risultato.utile_civilistico,
            "ires": {
                "variazioni_aumento": [
                    {
                        "descrizione": v.descrizione,
                        "importo": v.importo,
                        "norma": v.norma_riferimento
                    }
                    for v in risultato.variazioni_aumento_ires
                ],
                "variazioni_diminuzione": [
                    {
                        "descrizione": v.descrizione,
                        "importo": v.importo,
                        "norma": v.norma_riferimento
                    }
                    for v in risultato.variazioni_diminuzione_ires
                ],
                "totale_variazioni_aumento": risultato.totale_variazioni_aumento_ires,
                "totale_variazioni_diminuzione": risultato.totale_variazioni_diminuzione_ires,
                "reddito_imponibile": risultato.reddito_imponibile_ires,
                "aliquota": 24.0,
                "imposta_dovuta": risultato.ires_dovuta
            },
            "irap": {
                "regione": regione,
                "aliquota": calcolatore.aliquota_irap,
                "valore_produzione": risultato.valore_produzione_irap,
                "deduzioni": risultato.deduzioni_irap,
                "base_imponibile": risultato.base_imponibile_irap,
                "imposta_dovuta": risultato.irap_dovuta
            },
            "totale_imposte": risultato.totale_imposte,
            "aliquota_effettiva": risultato.aliquota_effettiva,
            "note": [
                f"Calcolo basato su fatture e corrispettivi dell'anno {anno_label}",
                "Variazioni fiscali automatiche per telefonia (20% indeducibile) e carburante auto (80% indeducibile)",
                f"Aliquota IRAP regione {regione}: {calcolatore.aliquota_irap}%"
            ]
        }
    except Exception as e:
        logger.error(f"Errore calcolo imposte: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bilancio-dettagliato")
@handle_errors
async def get_bilancio_dettagliato() -> Dict[str, Any]:
    """
    Genera un bilancio dettagliato con:
    - Stato Patrimoniale (Attivo/Passivo/PN)
    - Conto Economico (Ricavi/Costi)
    - Dettaglio deducibilità fiscale per ogni voce di costo
    - Calcolo imposte integrato
    """
    db = Database.get_db()
    
    conti = await db["piano_conti"].find({}, {"_id": 0}).to_list(1000)
    
    bilancio = {
        "stato_patrimoniale": {
            "attivo": {"voci": [], "totale": 0},
            "passivo": {"voci": [], "totale": 0},
            "patrimonio_netto": {"voci": [], "totale": 0}
        },
        "conto_economico": {
            "ricavi": {"voci": [], "totale": 0},
            "costi": {
                "per_categoria": {},
                "voci": [],
                "totale": 0,
                "totale_deducibile_ires": 0,
                "totale_deducibile_irap": 0
            },
            "risultato_operativo": 0,
            "utile_ante_imposte": 0
        },
        "data_generazione": datetime.now(timezone.utc).isoformat()
    }
    
    # Mappa deducibilità per codice conto
    deducibilita_map = {
        "05.02.07": {"ires": 80, "irap": 80, "nota": "Telefonia - 80% deducibile"},
        "05.02.11": {"ires": 20, "irap": 20, "nota": "Carburante uso promiscuo - 20% deducibile"},
        "05.06.05": {"ires": 0, "irap": 100, "nota": "IMU - non deducibile IRES"},
    }
    
    for conto in conti:
        codice = conto.get("codice", "")
        nome = conto.get("nome", "")
        categoria = conto.get("categoria", "")
        saldo = float(conto.get("saldo", 0) or 0)
        
        voce = {
            "codice": codice,
            "nome": nome,
            "saldo": saldo
        }
        
        if categoria == "attivo":
            bilancio["stato_patrimoniale"]["attivo"]["voci"].append(voce)
            bilancio["stato_patrimoniale"]["attivo"]["totale"] += saldo
            
        elif categoria == "passivo":
            bilancio["stato_patrimoniale"]["passivo"]["voci"].append(voce)
            bilancio["stato_patrimoniale"]["passivo"]["totale"] += saldo
            
        elif categoria == "patrimonio_netto":
            bilancio["stato_patrimoniale"]["patrimonio_netto"]["voci"].append(voce)
            bilancio["stato_patrimoniale"]["patrimonio_netto"]["totale"] += saldo
            
        elif categoria == "ricavi":
            bilancio["conto_economico"]["ricavi"]["voci"].append(voce)
            bilancio["conto_economico"]["ricavi"]["totale"] += saldo
            
        elif categoria == "costi":
            # Aggiungi info deducibilità
            ded_info = deducibilita_map.get(codice, {"ires": 100, "irap": 100, "nota": ""})
            voce["deducibilita_ires"] = ded_info["ires"]
            voce["deducibilita_irap"] = ded_info["irap"]
            voce["nota_fiscale"] = ded_info["nota"]
            voce["importo_deducibile_ires"] = saldo * ded_info["ires"] / 100
            voce["importo_deducibile_irap"] = saldo * ded_info["irap"] / 100
            
            bilancio["conto_economico"]["costi"]["voci"].append(voce)
            bilancio["conto_economico"]["costi"]["totale"] += saldo
            bilancio["conto_economico"]["costi"]["totale_deducibile_ires"] += voce["importo_deducibile_ires"]
            bilancio["conto_economico"]["costi"]["totale_deducibile_irap"] += voce["importo_deducibile_irap"]
            
            # Raggruppa per sottocategoria (prime 5 cifre del codice)
            sottocategoria = codice[:5]
            if sottocategoria not in bilancio["conto_economico"]["costi"]["per_categoria"]:
                bilancio["conto_economico"]["costi"]["per_categoria"][sottocategoria] = {
                    "nome": _get_nome_sottocategoria(sottocategoria),
                    "voci": [],
                    "totale": 0
                }
            bilancio["conto_economico"]["costi"]["per_categoria"][sottocategoria]["voci"].append(voce)
            bilancio["conto_economico"]["costi"]["per_categoria"][sottocategoria]["totale"] += saldo
    
    # Calcola risultati
    bilancio["conto_economico"]["risultato_operativo"] = (
        bilancio["conto_economico"]["ricavi"]["totale"] -
        bilancio["conto_economico"]["costi"]["totale"]
    )
    bilancio["conto_economico"]["utile_ante_imposte"] = bilancio["conto_economico"]["risultato_operativo"]
    
    # Arrotonda tutti i valori
    def arrotonda_nested(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, float):
                    obj[k] = round(v, 2)
                else:
                    arrotonda_nested(v)
        elif isinstance(obj, list):
            for item in obj:
                arrotonda_nested(item)
    
    arrotonda_nested(bilancio)
    
    return bilancio


def _get_nome_sottocategoria(codice: str) -> str:
    """Restituisce il nome della sottocategoria di costo."""
    nomi = {
        "05.01": "Acquisti merci e materie prime",
        "05.02": "Costi per servizi",
        "05.03": "Costo del personale",
        "05.04": "Ammortamenti",
        "05.05": "Oneri finanziari",
        "05.06": "Imposte e tasse",
        "05.07": "Oneri straordinari"
    }
    return nomi.get(codice, f"Categoria {codice}")


@router.get("/categorizzazione-preview")
@handle_errors
async def preview_categorizzazione(
    descrizione: str = Query(..., description="Descrizione prodotto"),
    fornitore: str = Query("", description="Nome fornitore")
) -> Dict[str, Any]:
    """
    Anteprima della categorizzazione per una descrizione.
    Utile per testare le regole prima dell'elaborazione massiva.
    """
    categorizzatore = get_categorizzatore()
    result = categorizzatore.categorizza_linea(descrizione, fornitore)
    
    return {
        "input": {
            "descrizione": descrizione,
            "fornitore": fornitore
        },
        "categorizzazione": {
            "categoria_merceologica": result.categoria_merceologica,
            "conto_codice": result.conto_codice,
            "conto_nome": result.conto_nome,
            "categoria_fiscale": result.categoria_fiscale.value,
            "deducibilita_ires": result.percentuale_deducibilita_ires,
            "deducibilita_irap": result.percentuale_deducibilita_irap,
            "note_fiscali": result.note_fiscali,
            "confidenza": result.confidenza
        }
    }


@router.get("/aliquote-irap")
@handle_errors
async def get_aliquote_irap() -> Dict[str, Any]:
    """Restituisce le aliquote IRAP per tutte le regioni."""
    return {
        "aliquote": ALIQUOTE_IRAP,
        "nota": "Aliquote IRAP 2024-2025. L'aliquota può variare in base alla regione di operatività."
    }


@router.get("/statistiche-categorizzazione")
@handle_errors
async def get_statistiche_categorizzazione() -> Dict[str, Any]:
    """
    Statistiche sulla categorizzazione delle fatture.
    Mostra distribuzione per categoria, deducibilità media, etc.
    """
    db = Database.get_db()
    
    # Aggregazione per categoria
    pipeline = [
        {"$match": {"categoria_contabile": {"$exists": True}}},
        {"$group": {
            "_id": "$categoria_contabile",
            "count": {"$sum": 1},
            "totale_importo": {"$sum": "$total_amount"},
            "media_deducibilita_ires": {"$avg": "$percentuale_deducibilita_ires"},
            "media_deducibilita_irap": {"$avg": "$percentuale_deducibilita_irap"}
        }},
        {"$sort": {"totale_importo": -1}}
    ]
    
    risultati = await db["invoices"].aggregate(pipeline).to_list(100)
    
    # Totali
    totale_fatture = await db["invoices"].count_documents({"categoria_contabile": {"$exists": True}})
    totale_non_categorizzate = await db["invoices"].count_documents({
        "$or": [
            {"categoria_contabile": {"$exists": False}},
            {"categoria_contabile": None}
        ]
    })
    
    return {
        "distribuzione_categorie": [
            {
                "categoria": r["_id"],
                "numero_fatture": r["count"],
                "importo_totale": round(r["totale_importo"], 2),
                "deducibilita_media_ires": round(r["media_deducibilita_ires"] or 0, 1),
                "deducibilita_media_irap": round(r["media_deducibilita_irap"] or 0, 1)
            }
            for r in risultati
        ],
        "totale_categorizzate": totale_fatture,
        "totale_non_categorizzate": totale_non_categorizzate,
        "percentuale_copertura": round(
            totale_fatture / (totale_fatture + totale_non_categorizzate) * 100, 1
        ) if (totale_fatture + totale_non_categorizzate) > 0 else 0
    }


@router.get("/export/pdf-dichiarazione")
@handle_errors
async def export_pdf_dichiarazione(
    anno: int = Query(default=2024, description="Anno fiscale"),
    regione: str = Query(default="campania", description="Regione per aliquota IRAP")
) -> StreamingResponse:
    """
    Genera un PDF con il prospetto completo per la dichiarazione dei redditi.
    Include: Bilancio, Calcolo IRES, Calcolo IRAP, Variazioni Fiscali.
    """
    db = Database.get_db()
    
    # Raccogli dati
    calcolatore = CalcolatoreImposte(regione=regione)
    
    # Calcola imposte dal database filtrate per anno
    risultato = await calcolatore.calcola_imposte_da_db(db, anno)
    
    # Crea PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=1.5*cm, bottomMargin=1.5*cm)
    styles = getSampleStyleSheet()
    
    # Stili personalizzati
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=18, alignment=TA_CENTER, spaceAfter=20)
    heading_style = ParagraphStyle('Heading', parent=styles['Heading2'], fontSize=14, spaceAfter=10, spaceBefore=15)
    subheading_style = ParagraphStyle('SubHeading', parent=styles['Heading3'], fontSize=12, spaceAfter=8)
    normal_style = ParagraphStyle('Normal', parent=styles['Normal'], fontSize=10)
    right_style = ParagraphStyle('Right', parent=styles['Normal'], fontSize=10, alignment=TA_RIGHT)
    
    elements = []
    
    # Intestazione
    elements.append(Paragraph(f"PROSPETTO DICHIARAZIONE REDDITI - ANNO {anno}", title_style))
    elements.append(Paragraph(f"Generato il {datetime.now().strftime('%d/%m/%Y %H:%M')}", normal_style))
    elements.append(Spacer(1, 20))
    
    # Sezione 1: Riepilogo Imposte
    elements.append(Paragraph("1. RIEPILOGO IMPOSTE", heading_style))
    
    riepilogo_data = [
        ["Descrizione", "Importo €"],
        ["Utile Civilistico", f"{risultato.utile_civilistico:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")],
        ["Reddito Imponibile IRES", f"{risultato.reddito_imponibile_ires:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")],
        ["IRES Dovuta (24%)", f"{risultato.ires_dovuta:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")],
        ["Base Imponibile IRAP", f"{risultato.base_imponibile_irap:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")],
        [f"IRAP Dovuta ({calcolatore.aliquota_irap}%)", f"{risultato.irap_dovuta:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")],
        ["TOTALE IMPOSTE", f"{risultato.totale_imposte:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")],
        ["Aliquota Effettiva", f"{risultato.aliquota_effettiva:.2f}%"],
    ]
    
    t = Table(riepilogo_data, colWidths=[10*cm, 5*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e3a5f')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e8f4f8')),
        ('FONTNAME', (0, -2), (-1, -1), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 20))
    
    # Sezione 2: Variazioni IRES in Aumento
    elements.append(Paragraph("2. VARIAZIONI FISCALI IRES - IN AUMENTO", heading_style))
    
    if risultato.variazioni_aumento_ires:
        var_aum_data = [["Descrizione", "Norma", "Importo €"]]
        for v in risultato.variazioni_aumento_ires:
            var_aum_data.append([
                v.descrizione[:50],
                v.norma_riferimento[:30] if v.norma_riferimento else "",
                f"{v.importo:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            ])
        var_aum_data.append(["TOTALE VARIAZIONI IN AUMENTO", "", f"{risultato.totale_variazioni_aumento_ires:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")])
        
        t = Table(var_aum_data, colWidths=[8*cm, 4*cm, 3*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#d4380d')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#fff2e8')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
        ]))
        elements.append(t)
    else:
        elements.append(Paragraph("Nessuna variazione in aumento", normal_style))
    
    elements.append(Spacer(1, 15))
    
    # Sezione 3: Variazioni IRES in Diminuzione
    elements.append(Paragraph("3. VARIAZIONI FISCALI IRES - IN DIMINUZIONE", heading_style))
    
    if risultato.variazioni_diminuzione_ires:
        var_dim_data = [["Descrizione", "Norma", "Importo €"]]
        for v in risultato.variazioni_diminuzione_ires:
            var_dim_data.append([
                v.descrizione[:50],
                v.norma_riferimento[:30] if v.norma_riferimento else "",
                f"{v.importo:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            ])
        var_dim_data.append(["TOTALE VARIAZIONI IN DIMINUZIONE", "", f"{risultato.totale_variazioni_diminuzione_ires:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")])
        
        t = Table(var_dim_data, colWidths=[8*cm, 4*cm, 3*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#389e0d')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f6ffed')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
        ]))
        elements.append(t)
    else:
        elements.append(Paragraph("Nessuna variazione in diminuzione", normal_style))
    
    elements.append(PageBreak())
    
    # Sezione 4: Dettaglio IRAP
    elements.append(Paragraph("4. CALCOLO IRAP - DETTAGLIO", heading_style))
    elements.append(Paragraph(f"Regione: {regione.upper()} - Aliquota: {calcolatore.aliquota_irap}%", subheading_style))
    
    irap_data = [
        ["Voce", "Importo €"],
        ["Valore della Produzione", f"{risultato.valore_produzione_irap:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")],
        ["(-) Deduzioni", f"{risultato.deduzioni_irap:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")],
        ["Base Imponibile", f"{risultato.base_imponibile_irap:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")],
        [f"IRAP Dovuta ({calcolatore.aliquota_irap}%)", f"{risultato.irap_dovuta:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")],
    ]
    
    t = Table(irap_data, colWidths=[10*cm, 5*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#722ed1')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f9f0ff')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 20))
    
    # Sezione 5: Quadro Riassuntivo IRES
    elements.append(Paragraph("5. QUADRO RIASSUNTIVO IRES", heading_style))
    
    quadro_data = [
        ["Rigo", "Descrizione", "Importo €"],
        ["RF1", "Utile/Perdita Civilistico", f"{risultato.utile_civilistico:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")],
        ["RF5", "Variazioni in Aumento", f"+{risultato.totale_variazioni_aumento_ires:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")],
        ["RF55", "Variazioni in Diminuzione", f"-{risultato.totale_variazioni_diminuzione_ires:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")],
        ["RF63", "Reddito Imponibile", f"{risultato.reddito_imponibile_ires:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")],
        ["RN4", "IRES Lorda (24%)", f"{risultato.ires_dovuta:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")],
    ]
    
    t = Table(quadro_data, colWidths=[2*cm, 9*cm, 4*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1890ff')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 30))
    
    # Note finali
    elements.append(Paragraph("NOTE", heading_style))
    note_text = f"""
    • Calcolo basato sui saldi attuali del Piano dei Conti al {datetime.now().strftime('%d/%m/%Y')}
    • Variazioni fiscali automatiche applicate per: Telefonia (20% indeducibile IRES), 
      Carburanti auto (80% indeducibile), Noleggio auto a lungo termine (limite deducibilità)
    • Aliquota IRAP regione {regione.upper()}: {calcolatore.aliquota_irap}%
    • Il presente prospetto è generato automaticamente e non sostituisce la consulenza professionale
    """
    elements.append(Paragraph(note_text, normal_style))
    
    # Genera PDF
    doc.build(elements)
    
    buffer.seek(0)
    filename = f"dichiarazione_redditi_{anno}.pdf"
    
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
