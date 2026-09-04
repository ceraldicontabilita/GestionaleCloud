"""
Router Contabilità Avanzata

Endpoint per:
- Categorizzazione intelligente fatture → Piano dei Conti
- Calcolo IRES/IRAP in tempo reale
- Rielaborazione massiva delle fatture
- Bilancio dettagliato con deducibilità
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from app.utils.dependencies import get_current_admin_user
from fastapi.responses import StreamingResponse
from typing import Dict, Any
from datetime import datetime, timezone
import uuid
import logging
import io

from app.services.sheets_document_store import DuplicateRecordError

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
    """Piano dei conti CEE ufficiale (unico piano, audit 03/09/2026 PR 7).

    Le voci "estese" operative (`PIANO_CONTI_ESTESO`) non sono un secondo
    piano: sono alias dei conti CEE e compaiono come tali. Nessuna lettura
    ne' scrittura della collezione dismessa ``piano_conti``.
    """
    from app.services.mapping_piano_conti import (
        piano_conti_cee, raggruppa_per_categoria, risolvi_codice_cee,
    )

    conti = piano_conti_cee()
    non_mappati = sorted(
        codice for codice in PIANO_CONTI_ESTESO if not risolvi_codice_cee(codice)
    )
    return {
        "conti": conti,
        "grouped": raggruppa_per_categoria(conti),
        "totale_conti": len(conti),
        "schema": "CEE",
        "alias_operativi_non_mappati": non_mappati,
        "conti_nuovi": 0,
    }


@router.post("/inizializza-piano-esteso")
@handle_errors
async def inizializza_piano_conti_esteso(_admin: Dict[str, Any] = Depends(get_current_admin_user)) -> Dict[str, Any]:
    """Il piano dei conti e' il CEE ufficiale in codice: non c'e' piu' nulla
    da inizializzare in una collezione (dismessa, PR 7). Nessuna scrittura."""
    from app.services.mapping_piano_conti import piano_conti_cee, risolvi_codice_cee

    return {
        "success": True,
        "conti_aggiunti": 0,
        "conti_aggiornati": 0,
        "totale_piano_conti": len(piano_conti_cee()),
        "alias_operativi": sum(1 for codice in PIANO_CONTI_ESTESO if risolvi_codice_cee(codice)),
        "nota": "Piano dei conti CEE ufficiale: i conti operativi sono alias, nessuna scrittura.",
    }


@router.post("/ricategorizza-fatture")
@handle_errors
async def ricategorizza_tutte_fatture() -> Dict[str, Any]:
    """
    Registrazione incrementale: classifica e registra soltanto fatture e
    corrispettivi ancora assenti dal libro giornale definitivo.

    Passa per il MOTORE UNICO `app.services.registrazione_contabile` (P1 §6.1):
    schema/idempotenza/numero registrazione/audit unificati. La CATEGORIZZAZIONE
    ricca resta qui (conti passati al motore). Non cancella, non azzera e non
    riscrive le registrazioni gia definitive.
    """
    from app.services.registrazione_contabile import (
        registra_fattura, registra_tutti_corrispettivi,
    )

    db = Database.get_db()

    fatture = await db["invoices"].find({
        "$and": [
            {"$or": [
                {"entity_status": {"$ne": "deleted"}},
                {"entity_status": {"$exists": False}},
            ]},
            {"status": {"$nin": ["deleted", "archived"]}},
            {"registrata_contabilita": {"$ne": True}},
        ]
    }, {"_id": 0}).to_list(10000)

    stats = {"fatture_processate": 0, "movimenti_creati": 0, "errori": [],
             "categorie": {}, "conti_utilizzati": {}}

    for fattura in fatture:
        try:
            if not fattura.get("id"):
                continue
            linee = fattura.get("linee", [])
            fornitore = fattura.get("supplier_name", "")
            categorizzazione = categorizza_fattura_completa(linee, fornitore)

            conto_costo, conto_nome = "05.01.01", "Acquisto merci"
            if categorizzazione["riepilogo_conti"]:
                principale = max(categorizzazione["riepilogo_conti"], key=lambda x: x["importo"])
                conto_costo, conto_nome = principale["codice"], principale["nome"]

            conti = {
                "costo": {"codice": conto_costo, "nome": conto_nome},
                "iva_credito": {"codice": "01.04.01", "nome": "IVA a credito"},
                "debito_fornitore": {"codice": "02.01.01", "nome": "Debiti v/fornitori"},
            }
            extra_mov = {
                "categoria_principale": categorizzazione["categoria_principale"],
                "percentuale_deducibilita_ires": categorizzazione["percentuale_deducibilita_ires"],
                "percentuale_deducibilita_irap": categorizzazione["percentuale_deducibilita_irap"],
            }
            extra_fatt = {
                "categoria_contabile": categorizzazione["categoria_principale"],
                "conto_costo_codice": conto_costo,
                "conto_costo_nome": conto_nome,
                "percentuale_deducibilita_ires": categorizzazione["percentuale_deducibilita_ires"],
                "percentuale_deducibilita_irap": categorizzazione["percentuale_deducibilita_irap"],
            }
            r = await registra_fattura(db, fattura, force=False, conti=conti,
                                       extra_movimento=extra_mov, extra_fattura=extra_fatt)
            if r.get("stato") != "registrato":
                continue
            stats["fatture_processate"] += 1
            stats["movimenti_creati"] += 1
            cat = categorizzazione["categoria_principale"]
            stats["categorie"][cat] = stats["categorie"].get(cat, 0) + 1
            stats["conti_utilizzati"][conto_costo] = stats["conti_utilizzati"].get(conto_costo, 0) + 1
        except Exception as e:  # noqa: BLE001
            stats["errori"].append(f"Fattura {fattura.get('invoice_number', 'N/A')}: {str(e)}")

    # Ri-registra i corrispettivi tramite lo stesso motore
    res_corr = await registra_tutti_corrispettivi(db)
    stats["corrispettivi_registrati"] = res_corr.get("registrati", 0)
    stats["errori"].extend(res_corr.get("errori", []))

    return {"success": True, **stats, "errori": stats["errori"][:20]}


async def aggiorna_saldo_conto(db, codice_conto: str, importo: float, tipo: str):
    """Compatibilita': i saldi per conto non si persistono piu' nella
    collezione dismessa ``piano_conti`` (PR 7); delega all'unico punto in
    `piano_conti.aggiorna_saldo_conto`, che non scrive nulla."""
    from app.routers.accounting.piano_conti import aggiorna_saldo_conto as _canonico

    return await _canonico(db, codice_conto, importo, tipo)


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

    # Un solo piano (CEE ufficiale) e un solo calcolo dei saldi
    # (`piano_conti._calcola_saldi_piano_conti`): la collezione ``piano_conti``
    # con i suoi saldi a zero e' dismessa (audit 03/09/2026, PR 7). Le regole
    # di deducibilita' restano espresse sugli alias operativi.
    from app.routers.accounting.piano_conti import _calcola_saldi_piano_conti
    from app.services.mapping_piano_conti import piano_conti_cee, saldi_in_cee

    saldi_operativi = await _calcola_saldi_piano_conti(db, None)
    saldi_cee = saldi_in_cee(saldi_operativi)
    conti = [
        conto for conto in piano_conti_cee(saldi_operativi)
        if conto["alias_operativi"] or abs(saldi_cee.get(conto["codice"], 0.0)) >= 0.005
    ]

    bilancio = {
        "schema": "CEE",
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
        alias = conto.get("alias_operativi") or []

        voce = {
            "codice": codice,
            "nome": nome,
            "alias_operativi": alias,
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
            # Aggiungi info deducibilità (regole sugli alias operativi)
            ded_info = next(
                (deducibilita_map[a] for a in alias if a in deducibilita_map),
                {"ires": 100, "irap": 100, "nota": ""},
            )
            voce["deducibilita_ires"] = ded_info["ires"]
            voce["deducibilita_irap"] = ded_info["irap"]
            voce["nota_fiscale"] = ded_info["nota"]
            voce["importo_deducibile_ires"] = saldo * ded_info["ires"] / 100
            voce["importo_deducibile_irap"] = saldo * ded_info["irap"] / 100

            bilancio["conto_economico"]["costi"]["voci"].append(voce)
            bilancio["conto_economico"]["costi"]["totale"] += saldo
            bilancio["conto_economico"]["costi"]["totale_deducibile_ires"] += voce["importo_deducibile_ires"]
            bilancio["conto_economico"]["costi"]["totale_deducibile_irap"] += voce["importo_deducibile_irap"]

            # Raggruppa per macro-gruppo CEE (prime 2 cifre: 55 Acquisti,
            # 57 Servizi, 67 Personale, ...)
            sottocategoria = codice[:2]
            if sottocategoria not in bilancio["conto_economico"]["costi"]["per_categoria"]:
                bilancio["conto_economico"]["costi"]["per_categoria"][sottocategoria] = {
                    "nome": conto.get("voce_cee") or _get_nome_sottocategoria(sottocategoria),
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
    elements.append(Paragraph(f"Generato il {datetime.now().strftime('%d-%m-%Y %H:%M')}", normal_style))
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
    • Calcolo basato sui saldi attuali del Piano dei Conti al {datetime.now().strftime('%d-%m-%Y')}
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
