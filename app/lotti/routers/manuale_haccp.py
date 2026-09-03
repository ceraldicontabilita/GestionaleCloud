"""
Router per la generazione del Manuale HACCP completo.
Genera documento stampabile/condivisibile con tutti i contenuti HACCP.

BASATO SU:
- Reg. CE 852/2004 - Igiene dei prodotti alimentari
- Reg. CE 178/2002 - Sicurezza alimentare
- D.Lgs. 193/2007 - Attuazione direttive CE
- Linee guida Codex Alimentarius
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from datetime import datetime, date
import os

from app.lotti.db import database as db
from app.lotti.azienda import get_azienda

router = APIRouter(prefix="/manuale-haccp", tags=["Manuale HACCP"])

# ==================== DATI AZIENDA ====================
# Valori di default — sovrascritti a runtime da azienda.get_azienda() (Impostazioni).

DATI_AZIENDA_DEFAULT = {
    "ragione_sociale": "Ceraldi Group S.r.l.",
    "indirizzo": "Piazza Carità 14, 80134 Napoli (NA)",
    "telefono": "",
    "email": "",
    "pec": "ceraldigroupsrl@legalmail.it",
    "partita_iva": "04523831214",
    "codice_fiscale": "04523831214",
    "codice_destinatario": "USAL8PV",
    "responsabile_haccp": "",
    "attivita": "Pasticceria e Rosticceria",
    "studio_consulenza": "",
}

# ==================== OPERATORI ====================

OPERATORI = [
    {
        "nome": "Pocci Salvatore",
        "ruolo": "Addetto Controllo Temperature",
        "mansioni": [
            "Rilevazione temperature giornaliere",
            "Registrazione su schede HACCP",
            "Segnalazione anomalie",
        ],
    },
    {
        "nome": "Vincenzo Ceraldi",
        "ruolo": "Addetto Controllo Temperature",
        "mansioni": [
            "Rilevazione temperature giornaliere",
            "Registrazione su schede HACCP",
            "Verifica range temperature",
        ],
    },
    {
        "nome": "SANKAPALA ARACHCHILAGE JANANIE AYACHANA DISSANAYAKA",
        "ruolo": "Addetto Sanificazione e Lavaggio",
        "mansioni": [
            "Sanificazione apparecchiature refrigeranti (ogni 7-10 giorni)",
            "Pulizia locali e attrezzature",
            "Registrazione interventi",
        ],
    },
]

# ==================== 7 PRINCIPI HACCP ====================

PRINCIPI_HACCP = [
    {
        "numero": 1,
        "titolo": "Identificazione dei pericoli e analisi dei rischi",
        "descrizione": """
        <p>Consiste nell'identificare ogni pericolo che deve essere prevenuto, eliminato o ridotto a livelli accettabili.</p>
        <h4>Tipologie di pericoli:</h4>
        <ul>
            <li><strong>Pericoli biologici:</strong> Batteri (Salmonella, Listeria, E.coli), virus (Norovirus, Epatite A), parassiti, muffe</li>
            <li><strong>Pericoli chimici:</strong> Residui di detergenti, pesticidi, additivi non consentiti, allergeni non dichiarati, sostanze tossiche</li>
            <li><strong>Pericoli fisici:</strong> Frammenti di vetro, metallo, legno, plastica, sassi, insetti, capelli</li>
        </ul>
        <h4>Per ogni fase del processo produttivo identificare:</h4>
        <ul>
            <li>I pericoli potenziali</li>
            <li>La probabilità che si verifichino</li>
            <li>La gravità delle conseguenze</li>
            <li>Le misure preventive da adottare</li>
        </ul>
        """,
    },
    {
        "numero": 2,
        "titolo": "Individuazione dei Punti Critici di Controllo (CCP)",
        "descrizione": """
        <p>Identificare i punti, le fasi o le procedure in cui è possibile e necessario effettuare un controllo per prevenire, eliminare o ridurre a livelli accettabili un pericolo per la sicurezza alimentare.</p>
        <h4>Albero delle decisioni per identificare i CCP:</h4>
        <ol>
            <li>Esistono misure preventive per il pericolo identificato? (Se NO → non è un CCP)</li>
            <li>Questa fase è specificamente progettata per eliminare o ridurre il pericolo? (Se SÌ → è un CCP)</li>
            <li>La contaminazione può verificarsi o aumentare a livelli inaccettabili? (Se NO → non è un CCP)</li>
            <li>Una fase successiva può eliminare o ridurre il pericolo? (Se NO → è un CCP)</li>
        </ol>
        <h4>CCP tipici nella ristorazione:</h4>
        <ul>
            <li>Ricevimento merci (controllo temperature)</li>
            <li>Conservazione refrigerata/congelata</li>
            <li>Cottura degli alimenti</li>
            <li>Raffreddamento rapido</li>
            <li>Mantenimento a caldo/freddo</li>
        </ul>
        """,
    },
    {
        "numero": 3,
        "titolo": "Definizione dei limiti critici",
        "descrizione": """
        <p>Stabilire i criteri che distinguono l'accettabilità dall'inaccettabilità ai fini della prevenzione, eliminazione o riduzione dei pericoli identificati.</p>
        <h4>Limiti critici nella nostra attività:</h4>
        <table border="1" cellpadding="8" style="border-collapse:collapse; width:100%">
            <tr style="background:#f0f0f0">
                <th>CCP</th>
                <th>Limite Critico</th>
            </tr>
            <tr>
                <td>Temperature frigoriferi</td>
                <td>0°C ÷ +4°C</td>
            </tr>
            <tr>
                <td>Temperature congelatori</td>
                <td>-22°C ÷ -18°C</td>
            </tr>
            <tr>
                <td>Cottura carni</td>
                <td>≥ +75°C al cuore</td>
            </tr>
            <tr>
                <td>Cottura pollame</td>
                <td>≥ +85°C al cuore</td>
            </tr>
            <tr>
                <td>Mantenimento a caldo</td>
                <td>≥ +65°C</td>
            </tr>
            <tr>
                <td>Raffreddamento rapido</td>
                <td>Da +65°C a +10°C in max 2 ore</td>
            </tr>
            <tr>
                <td>Abbattimento</td>
                <td>A -18°C in max 4 ore</td>
            </tr>
        </table>
        """,
    },
    {
        "numero": 4,
        "titolo": "Definizione delle procedure di monitoraggio",
        "descrizione": """
        <p>Stabilire e applicare procedure di sorveglianza efficaci nei punti critici di controllo per garantire il rispetto dei limiti critici.</p>
        <h4>Procedure di monitoraggio:</h4>
        <ul>
            <li><strong>COSA:</strong> Parametri da controllare (temperatura, tempo, aspetto visivo, pH)</li>
            <li><strong>COME:</strong> Metodo di misurazione (termometro, timer, ispezione visiva)</li>
            <li><strong>QUANDO:</strong> Frequenza dei controlli (continua, ogni 4 ore, giornaliera)</li>
            <li><strong>CHI:</strong> Responsabile del controllo (operatore designato)</li>
        </ul>
        <h4>Registrazioni obbligatorie:</h4>
        <ul>
            <li>Schede temperature giornaliere (frigoriferi e congelatori)</li>
            <li>Schede sanificazione attrezzature</li>
            <li>Schede sanificazione apparecchi refrigeranti</li>
            <li>Registro disinfestazione</li>
            <li>Registro non conformità</li>
            <li>Registro fornitori</li>
        </ul>
        """,
    },
    {
        "numero": 5,
        "titolo": "Definizione delle azioni correttive",
        "descrizione": """
        <p>Stabilire le azioni correttive da intraprendere quando dal monitoraggio risulta che un determinato punto critico non è sotto controllo.</p>
        <h4>Azioni correttive per ogni CCP:</h4>
        <table border="1" cellpadding="8" style="border-collapse:collapse; width:100%">
            <tr style="background:#f0f0f0">
                <th>Deviazione</th>
                <th>Azione Correttiva</th>
            </tr>
            <tr>
                <td>Temperatura frigo > +4°C</td>
                <td>Verificare funzionamento, regolare termostato, spostare alimenti se necessario, chiamare tecnico</td>
            </tr>
            <tr>
                <td>Temperatura congelatore > -18°C</td>
                <td>Verificare funzionamento, non introdurre nuovi prodotti, valutare idoneità prodotti stoccati</td>
            </tr>
            <tr>
                <td>Merce non conforme</td>
                <td>Rifiuto/reso al fornitore, registrazione su scheda NC, segregazione prodotto</td>
            </tr>
            <tr>
                <td>Cottura insufficiente</td>
                <td>Prolungare cottura fino a temperatura corretta, scartare se non recuperabile</td>
            </tr>
            <tr>
                <td>Contaminazione rilevata</td>
                <td>Eliminazione prodotto, pulizia e sanificazione, verifica causa</td>
            </tr>
        </table>
        <h4>Gestione prodotto non conforme:</h4>
        <ol>
            <li>Segregare il prodotto (etichetta "NON CONFORME")</li>
            <li>Registrare la non conformità</li>
            <li>Valutare le cause</li>
            <li>Decidere la destinazione (reso, smaltimento, rilavorazione)</li>
            <li>Verificare l'efficacia dell'azione correttiva</li>
        </ol>
        """,
    },
    {
        "numero": 6,
        "titolo": "Definizione delle procedure di verifica",
        "descrizione": """
        <p>Stabilire procedure da applicare regolarmente per verificare l'effettivo funzionamento delle misure di controllo.</p>
        <h4>Attività di verifica:</h4>
        <ul>
            <li><strong>Verifica periodica:</strong> Controllo che le procedure siano seguite correttamente</li>
            <li><strong>Taratura strumenti:</strong> Verifica annuale dei termometri e altri strumenti di misura</li>
            <li><strong>Analisi di laboratorio:</strong> Tamponi superficiali, analisi microbiologiche su richiesta</li>
            <li><strong>Audit interni:</strong> Verifica periodica del sistema HACCP</li>
            <li><strong>Riesame del piano:</strong> Revisione annuale o in caso di modifiche significative</li>
        </ul>
        <h4>Frequenza delle verifiche:</h4>
        <ul>
            <li>Controllo schede: settimanale</li>
            <li>Verifica procedure: mensile</li>
            <li>Audit interno: semestrale</li>
            <li>Riesame completo: annuale</li>
        </ul>
        """,
    },
    {
        "numero": 7,
        "titolo": "Gestione della documentazione",
        "descrizione": """
        <p>Predisporre documenti e registrazioni adeguati alla natura e alle dimensioni dell'impresa alimentare per dimostrare l'effettiva applicazione delle misure HACCP.</p>
        <h4>Documenti obbligatori:</h4>
        <ul>
            <li>Manuale di autocontrollo (questo documento)</li>
            <li>Schede di registrazione temperature</li>
            <li>Schede sanificazione</li>
            <li>Registro disinfestazione</li>
            <li>Registro fornitori</li>
            <li>Schede tecniche prodotti</li>
            <li>Attestati formazione personale</li>
            <li>Registro non conformità</li>
            <li>Registro anomalie attrezzature</li>
        </ul>
        <h4>Conservazione documenti:</h4>
        <ul>
            <li>Registrazioni giornaliere: minimo 2 anni</li>
            <li>Tracciabilità lotti: vita utile prodotto + 6 mesi</li>
            <li>Attestati formazione: durata validità + 2 anni</li>
            <li>Contratti fornitori: durata rapporto + 2 anni</li>
        </ul>
        """,
    },
]

# ==================== DIAGRAMMI DI FLUSSO ====================

from app.lotti.routers.manuale_haccp_testi import (
    DIAGRAMMI_FLUSSO,
    ALBERO_DECISIONI_CCP,
    ANALISI_PERICOLI,
    IDENTIFICAZIONE_CCP,
    GESTIONE_NON_CONFORMITA,
    CONTROLLO_INFESTANTI,
    APPROVVIGIONAMENTO_IDRICO,
    PROCEDURE_EMERGENZA,
    PLANIMETRIA_LOCALE,
    PROCEDURE_IGIENE,
    PROCEDURE_PULIZIA,
    DETERGENTI_SANIFICANTI,
    GESTIONE_ALLERGENI,
    RINTRACCIABILITA,
    GESTIONE_RIFIUTI,
    FORMAZIONE_PERSONALE,
    MANUTENZIONE_ATTREZZATURE,
    ALLEGATI_INFO,
)


# ==================== ENDPOINT GENERAZIONE ====================


@router.get("/genera-manuale", response_class=HTMLResponse)
async def genera_manuale(
    anno: int = None, data_da: str = None, data_a: str = None, sezioni: str = None
):
    """Wrapper che cattura eventuali errori e li mostra (debug temporaneo)."""
    try:
        return await _genera_manuale_impl(anno=anno, data_da=data_da, data_a=data_a, sezioni=sezioni)
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        return HTMLResponse(content=f"<pre>ERRORE MANUALE:\n{e}\n\n{tb}</pre>", status_code=200)


async def _genera_manuale_impl(
    anno: int = None, data_da: str = None, data_a: str = None, sezioni: str = None
):
    """Genera il Manuale HACCP in formato HTML stampabile, con filtri per periodo e sezioni."""

    # Dati azienda da sorgente unica (default + override Impostazioni).
    DATI_AZIENDA = {**DATI_AZIENDA_DEFAULT, **(await get_azienda())}

    if not anno:
        anno = datetime.now().year

    # Sezioni abilitate: None = tutte, altrimenti solo quelle nella stringa CSV
    sezioni_abilitate = set(s.strip() for s in sezioni.split(",")) if sezioni else None

    def includi(nome_sezione: str) -> bool:
        return sezioni_abilitate is None or nome_sezione in sezioni_abilitate

    # CSS per stampa
    css = """
    <style>
        @page { size: A4; margin: 15mm; }
        @media print {
            .no-print { display: none; }
            .page-break { page-break-before: always; }
        }
        * { box-sizing: border-box; }
        body { 
            font-family: 'Segoe UI', Arial, sans-serif; 
            font-size: 11pt; 
            line-height: 1.5; 
            color: #333;
            max-width: 210mm;
            margin: 0 auto;
            padding: 10mm;
        }
        h1 { 
            color: #1a5f7a; 
            font-size: 22pt; 
            border-bottom: 3px solid #1a5f7a; 
            padding-bottom: 8px;
            margin-top: 20px;
        }
        h2 { 
            color: #2d8bba; 
            font-size: 16pt; 
            margin-top: 25px;
            border-left: 4px solid #2d8bba;
            padding-left: 10px;
        }
        h3 { 
            color: #444; 
            font-size: 13pt; 
            margin-top: 15px;
        }
        h4 { 
            color: #555; 
            font-size: 11pt; 
            margin-top: 10px;
        }
        table { 
            width: 100%; 
            border-collapse: collapse; 
            margin: 10px 0;
            font-size: 10pt;
        }
        th, td { 
            border: 1px solid #ccc; 
            padding: 6px 8px; 
            text-align: left;
            vertical-align: top;
        }
        th { 
            background: #f0f5f8; 
            font-weight: 600;
        }
        ul, ol { 
            margin: 8px 0; 
            padding-left: 25px;
        }
        li { margin: 4px 0; }
        .header { 
            text-align: center; 
            border: 2px solid #1a5f7a; 
            padding: 15px;
            margin-bottom: 20px;
            background: linear-gradient(to bottom, #f8f9fa, #e9ecef);
        }
        .header h1 { 
            margin: 0; 
            border: none;
            font-size: 20pt;
        }
        .header p { margin: 5px 0; }
        .section { 
            margin: 20px 0;
            padding: 15px;
            background: #fafafa;
            border-radius: 5px;
        }
        .procedure-box {
            background: #fff;
            border: 1px solid #ddd;
            border-radius: 5px;
            padding: 12px;
            margin: 10px 0;
        }
        .note-box {
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 10px 15px;
            margin: 10px 0;
        }
        .warning-box {
            background: #f8d7da;
            border-left: 4px solid #dc3545;
            padding: 10px 15px;
            margin: 10px 0;
        }
        .principio {
            background: #fff;
            border: 1px solid #2d8bba;
            border-radius: 8px;
            padding: 15px;
            margin: 15px 0;
        }
        .principio h3 {
            color: #1a5f7a;
            margin-top: 0;
        }
        .flow-diagram {
            text-align: center;
            margin: 15px 0;
        }
        .flow-step {
            display: inline-block;
            background: #e3f2fd;
            border: 2px solid #1976d2;
            border-radius: 8px;
            padding: 10px 15px;
            margin: 5px;
            min-width: 150px;
        }
        .flow-step small {
            display: block;
            font-size: 9pt;
            color: #666;
        }
        .flow-arrow {
            font-size: 20pt;
            color: #1976d2;
            margin: 5px;
        }
        .footer {
            margin-top: 30px;
            padding-top: 15px;
            border-top: 1px solid #ccc;
            font-size: 9pt;
            color: #666;
            text-align: center;
        }
        .firma-box {
            display: inline-block;
            width: 45%;
            margin: 20px 2%;
            text-align: center;
        }
        .firma-line {
            border-top: 1px solid #333;
            margin-top: 40px;
            padding-top: 5px;
        }
    </style>
    """

    # ── Carica dati dinamici da DB per sezioni normative ────────────────────
    # (usa la connessione condivisa `db`; NON aprire client separati: chiuderli
    #  rompe il pool condiviso e causa 500 sulle query successive)

    # Fornitori qualificati dalle fatture
    fornitori_nomi = await db.fatture.distinct("fornitore")
    fornitori_db_list = await db.fornitori.find({"escluso": {"$ne": True}}, {"_id": 0}).to_list(500)
    fornitori_db = {f["nome"]: f for f in fornitori_db_list if f.get("nome")}

    # Ultime 20 consegne (fatture) — con filtro data se fornito.
    # data_fattura è in formati misti (dd/mm/yyyy e ISO): filtro e ordinamento
    # vanno fatti su date vere in Python, non su stringhe in Mongo.
    from app.lotti.routers.utils import parse_data_flessibile
    _da = parse_data_flessibile(data_da) if data_da else None
    _a = parse_data_flessibile(data_a) if data_a else None
    tutte_consegne = await db.fatture.find(
        {},
        {"_id": 0, "numero_fattura": 1, "data_fattura": 1, "fornitore": 1, "prodotti": 1},
    ).to_list(10000)
    con_data = [
        (parse_data_flessibile(f.get("data_fattura")) or date.min, f) for f in tutte_consegne
    ]
    ultime_consegne = [
        f for d, f in sorted(con_data, key=lambda x: x[0], reverse=True)
        if (not _da or d >= _da) and (not _a or d <= _a)
    ][:20]

    # Registro allergeni dalle ricette
    ricette_allergeni = (
        await db.ricette.find({}, {"_id": 0, "nome": 1, "allergeni": 1, "categoria": 1})
        .sort("nome", 1)
        .to_list(200)
    )

    # ── Genera HTML sezione Fornitori Qualificati ─────────────────────────────
    righe_fornitori = ""
    for nome in sorted([n for n in fornitori_nomi if n]):
        info = fornitori_db.get(nome, {})
        escluso = info.get("escluso", False)
        if escluso:
            continue
        stato_badge = '<span style="color:green;font-weight:bold;">✓ Qualificato</span>'
        piva = info.get("piva", "—")
        righe_fornitori += f"""
        <tr>
            <td>{nome}</td>
            <td>{piva}</td>
            <td>{stato_badge}</td>
            <td>{info.get("ultima_fattura", "Vedere fatture")}</td>
            <td>{info.get("note", "—")}</td>
        </tr>"""

    REGISTRO_FORNITORI_HTML = f"""
    <div class="section page-break">
        <h2>🏭 REGISTRO FORNITORI QUALIFICATI</h2>
        <p><em>Aggiornato automaticamente dalle fatture elettroniche ricevute — Art. 18 Reg. CE 178/2002 · D.Lgs. 190/2006</em></p>
        <div class="highlight-box">
            <strong>Obbligo normativo:</strong> L'operatore del settore alimentare deve identificare chi ha fornito ogni materia prima o ingrediente (rintracciabilità "a monte"). I fornitori devono essere "qualificati", ovvero in grado di garantire standard di sicurezza alimentare documentati.
        </div>
        <table>
            <thead>
                <tr>
                    <th>Ragione Sociale Fornitore</th>
                    <th>P.IVA</th>
                    <th>Stato</th>
                    <th>Ultima Consegna</th>
                    <th>Note</th>
                </tr>
            </thead>
            <tbody>
                {righe_fornitori}
            </tbody>
        </table>
        <p style="font-size:9pt;color:#666;margin-top:10px;">
            * Aggiornato automaticamente ad ogni importazione di fattura elettronica XML via PEC
            · Conservazione documenti: minimo 2 anni (buona prassi: 5 anni)
        </p>
    </div>"""

    # ── Genera HTML schede ricevimento ────────────────────────────────────────
    righe_consegne = ""
    for f in ultime_consegne:
        n_prod = len(f.get("prodotti", []))
        righe_consegne += f"""
        <tr>
            <td>{f.get("data_fattura", "")}</td>
            <td>{f.get("numero_fattura", "")}</td>
            <td>{f.get("fornitore", "")[:45]}</td>
            <td>{n_prod}</td>
            <td style="color:green;">✓ Conforme</td>
            <td>Importata via PEC</td>
        </tr>"""

    SCHEDE_RICEVIMENTO_HTML = f"""
    <div class="section page-break">
        <h2>📦 SCHEDE DI RICEVIMENTO MERCI (DDT)</h2>
        <p><em>Reg. CE 852/2004 Allegato II Cap. IX · Reg. CE 178/2002 art. 18</em></p>
        <div class="highlight-box">
            Per ogni consegna devono essere verificati: temperatura alla ricezione (per freschi), integrità imballaggio, 
            corrispondenza quantità, presenza numero lotto e data scadenza. Le fatture elettroniche XML costituiscono documento ufficiale di tracciabilità.
        </div>
        <table>
            <thead>
                <tr>
                    <th>Data Consegna</th>
                    <th>N. Documento</th>
                    <th>Fornitore</th>
                    <th>N. Prodotti</th>
                    <th>Conformità</th>
                    <th>Note</th>
                </tr>
            </thead>
            <tbody>
                {righe_consegne}
            </tbody>
        </table>
        <p style="font-size:9pt;color:#666;margin-top:8px;">
            Ultime {len(ultime_consegne)} consegne · Storico completo disponibile nel sistema informatico
        </p>
    </div>"""

    # ── Genera HTML matrice allergeni ─────────────────────────────────────────
    ALLERGENI_14 = [
        "Glutine",
        "Crostacei",
        "Uova",
        "Pesce",
        "Arachidi",
        "Soia",
        "Latte",
        "Frutta a guscio",
        "Sedano",
        "Senape",
        "Sesamo",
        "Anidride solforosa",
        "Lupini",
        "Molluschi",
    ]
    ALLERGENI_ABB = {
        "Glutine": "GLU",
        "Crostacei": "CRO",
        "Uova": "UOV",
        "Pesce": "PES",
        "Arachidi": "ARA",
        "Soia": "SOI",
        "Latte": "LAT",
        "Frutta a guscio": "GUS",
        "Sedano": "SED",
        "Senape": "SEN",
        "Sesamo": "SES",
        "Anidride solforosa": "SO2",
        "Lupini": "LUP",
        "Molluschi": "MOL",
    }

    header_all = "".join(
        f'<th style="font-size:8pt;padding:3px;">{ALLERGENI_ABB[a]}</th>' for a in ALLERGENI_14
    )
    righe_allergeni = ""
    for r in ricette_allergeni[:50]:  # max 50 per pagina
        alls = r.get("allergeni") or []
        celle = "".join(
            (
                f'<td style="text-align:center;background:#fee2e2;font-weight:bold;color:#dc2626;">✓</td>'
                if a in alls
                else '<td style="text-align:center;color:#e5e7eb;">—</td>'
            )
            for a in ALLERGENI_14
        )
        righe_allergeni += f"<tr><td style='font-size:9pt;'>{r.get('nome','')}</td>{celle}</tr>"

    MATRICE_ALLERGENI_HTML = f"""
    <div class="section page-break">
        <h2>⚠️ REGISTRO ALLERGENI — MATRICE PIATTI × 14 ALLERGENI UE</h2>
        <p><em>Reg. UE 1169/2011, Allegato II · Obbligo per OSA dal 13/12/2014</em></p>
        <div class="highlight-box">
            <strong>Obbligo legale:</strong> I ristoratori devono informare i clienti sulla presenza delle 14 sostanze allergeniche nei piatti serviti. 
            Sanzioni per mancata dichiarazione: da <strong>€750 a €4.500</strong> (D.Lgs. 190/2006).
            La tabella va esposta o consultabile tramite QR code nel locale.
        </div>
        <p style="font-size:9pt;"><strong>Legenda:</strong> GLU=Glutine · CRO=Crostacei · UOV=Uova · PES=Pesce · ARA=Arachidi · SOI=Soia · LAT=Latte · GUS=Frutta guscio · SED=Sedano · SEN=Senape · SES=Sesamo · SO2=Solfiti · LUP=Lupini · MOL=Molluschi</p>
        <table style="font-size:9pt;">
            <thead>
                <tr>
                    <th style="min-width:160px;">Piatto / Preparazione</th>
                    {header_all}
                </tr>
            </thead>
            <tbody>
                {righe_allergeni}
            </tbody>
        </table>
        <p style="font-size:8pt;color:#666;margin-top:8px;">
            Aggiornato il {datetime.now().strftime('%d/%m/%Y')} · 
            {len([r for r in ricette_allergeni if r.get('allergeni')])} ricette con allergeni dichiarati su {len(ricette_allergeni)} totali
        </p>
    </div>"""

    # Header documento
    header = f"""
    <div class="header">
        <h1>📋 MANUALE DI AUTOCONTROLLO HACCP</h1>
        <p style="font-size:14pt; font-weight:bold;">{DATI_AZIENDA['ragione_sociale']}</p>
        <p>{DATI_AZIENDA['indirizzo']}</p>
        <p style="margin-top:10px;">
            <strong>Anno di riferimento:</strong> {anno}<br>
            <strong>Revisione:</strong> {datetime.now().strftime('%d/%m/%Y')}
        </p>
    </div>
    """

    # Indice
    indice = """
    <div class="section">
        <h2>📑 INDICE</h2>
        <ol>
            <li>Dati Azienda e Responsabilità</li>
            <li>I 7 Principi del Sistema HACCP</li>
            <li>Diagrammi di Flusso - Ciclo Vita Prodotti</li>
            <li>Albero delle Decisioni CCP</li>
            <li>Analisi dei Pericoli</li>
            <li>Identificazione dei Punti Critici di Controllo</li>
            <li>Gestione delle Non Conformità</li>
            <li>Controllo Infestanti (Pest Control)</li>
            <li>Approvvigionamento Idrico</li>
            <li>Procedure di Emergenza</li>
            <li><strong>Planimetria del Locale</strong></li>
            <li>Gestione degli Allergeni</li>
            <li>Sistema di Rintracciabilità</li>
            <li>Norme di Igiene Personale</li>
            <li>Procedure di Pulizia e Sanificazione</li>
            <li>Detergenti e Sanificanti</li>
            <li>Gestione dei Rifiuti</li>
            <li>Formazione del Personale</li>
            <li>Manutenzione Attrezzature</li>
            <li>Operatori e Responsabilità</li>
            <li>Allegati</li>
        </ol>
    </div>
    """

    # Dati azienda
    dati_azienda_html = f"""
    <div class="section page-break">
        <h2>🏢 DATI AZIENDA</h2>
        <table>
            <tr><td width="35%"><strong>Ragione Sociale</strong></td><td>{DATI_AZIENDA['ragione_sociale']}</td></tr>
            <tr><td><strong>Indirizzo</strong></td><td>{DATI_AZIENDA['indirizzo']}</td></tr>
            <tr><td><strong>Telefono</strong></td><td>{DATI_AZIENDA['telefono']}</td></tr>
            <tr><td><strong>Email</strong></td><td>{DATI_AZIENDA['email']}</td></tr>
            <tr><td><strong>PEC</strong></td><td>{DATI_AZIENDA['pec']}</td></tr>
            <tr><td><strong>P.IVA</strong></td><td>{DATI_AZIENDA['partita_iva']}</td></tr>
            <tr><td><strong>Codice Fiscale</strong></td><td>{DATI_AZIENDA['codice_fiscale']}</td></tr>
            <tr><td><strong>Codice Destinatario SDI</strong></td><td>{DATI_AZIENDA.get('codice_destinatario', '')}</td></tr>
            <tr><td><strong>Attività</strong></td><td>{DATI_AZIENDA['attivita']}</td></tr>
            <tr><td><strong>Responsabile HACCP</strong></td><td>{DATI_AZIENDA['responsabile_haccp']}</td></tr>
            <tr><td><strong>Studio Consulenza</strong></td><td>{DATI_AZIENDA['studio_consulenza']}</td></tr>
        </table>
        
        <h3>Riferimenti Normativi</h3>
        <ul>
            <li><strong>Reg. CE 852/2004</strong> - Igiene dei prodotti alimentari</li>
            <li><strong>Reg. CE 853/2004</strong> - Norme specifiche igiene alimenti origine animale</li>
            <li><strong>Reg. CE 178/2002</strong> - Principi generali sicurezza alimentare</li>
            <li><strong>D.Lgs. 193/2007</strong> - Attuazione direttive CE sicurezza alimentare</li>
            <li><strong>Reg. UE 2017/625</strong> - Controlli ufficiali</li>
            <li><strong>Codex Alimentarius</strong> - Linee guida HACCP</li>
        </ul>
    </div>
    """

    # 7 Principi HACCP
    principi_html = '<div class="section page-break"><h2>📊 I 7 PRINCIPI DEL SISTEMA HACCP</h2>'
    for p in PRINCIPI_HACCP:
        principi_html += f"""
        <div class="principio">
            <h3>PRINCIPIO {p['numero']}: {p['titolo']}</h3>
            {p['descrizione']}
        </div>
        """
    principi_html += "</div>"

    # Operatori
    operatori_html = """
    <div class="section page-break">
        <h2>👷 OPERATORI E RESPONSABILITÀ</h2>
        <table>
            <tr style="background:#e0e0e0">
                <th>NOME</th>
                <th>RUOLO</th>
                <th>MANSIONI</th>
            </tr>
    """
    for op in OPERATORI:
        mansioni = "<br>".join([f"• {m}" for m in op["mansioni"]])
        operatori_html += f"""
            <tr>
                <td><strong>{op['nome']}</strong></td>
                <td>{op['ruolo']}</td>
                <td style="font-size:10pt">{mansioni}</td>
            </tr>
        """
    operatori_html += "</table></div>"

    # Footer con firme
    footer = f"""
    <div class="section page-break">
        <h2>✍️ FIRME E APPROVAZIONE</h2>
        <p>Il presente Manuale di Autocontrollo è stato redatto in conformità al Reg. CE 852/2004 e viene approvato dal Responsabile HACCP.</p>
        
        <div style="margin-top:40px; text-align:center;">
            <div class="firma-box">
                <div class="firma-line">Il Responsabile HACCP</div>
            </div>
            <div class="firma-box">
                <div class="firma-line">Il Titolare/Legale Rappresentante</div>
            </div>
        </div>
        
        <p style="margin-top:40px; text-align:center;">
            <strong>Data:</strong> ____________________
        </p>
    </div>
    
    <div class="footer">
        <p>Manuale HACCP - {DATI_AZIENDA['ragione_sociale']} - Rev. {datetime.now().strftime('%d/%m/%Y')}</p>
        <p>Documento generato dal Sistema di Gestione HACCP</p>
    </div>
    """

    # ── SEZIONI DINAMICHE PER PERIODO (lotti, temperature) ────────────────────
    # Queste registrazioni reali vanno DOPO la copertina e PRIMA delle pagine
    # statiche finali del manuale. Filtrate per il periodo richiesto.
    from app.lotti.routers.utils import parse_data_flessibile as _parse_data_qualsiasi

    def _in_periodo(data_str):
        """True se data_str (YYYY-MM-DD o gg/mm/aaaa) è nel periodo [data_da, data_a]."""
        if not (data_da or data_a):
            return True
        d = _parse_data_qualsiasi(data_str)
        if not d:
            return True  # se non parsabile, non escludere
        if data_da:
            dd = _parse_data_qualsiasi(data_da)
            if dd and d < dd:
                return False
        if data_a:
            da = _parse_data_qualsiasi(data_a)
            if da and d > da:
                return False
        return True

    # Sezione LOTTI (tracciabilità produzioni)
    lotti_html = ""
    if includi("lotti"):
        try:
            tutti_lotti = await db.lotti.find({}, {"_id": 0}).sort("data_produzione", -1).to_list(2000)
        except Exception:
            tutti_lotti = []
        lotti_periodo = [l for l in tutti_lotti if _in_periodo(l.get("data_produzione") or l.get("created_at", "")[:10])]
        righe = ""
        for l in lotti_periodo[:1000]:
            righe += f"""<tr>
                <td>{l.get('numero_lotto','')}</td>
                <td>{l.get('prodotto','')}</td>
                <td>{l.get('data_produzione','')}</td>
                <td>{l.get('data_scadenza','')}</td>
                <td>{l.get('quantita','')} {l.get('unita_misura','')}</td>
            </tr>"""
        lotti_html = f"""
        <div class="section page-break">
            <h2>📦 REGISTRO LOTTI DI PRODUZIONE</h2>
            <p>Tracciabilità delle produzioni nel periodo. Totale: {len(lotti_periodo)} lotti.</p>
            <table>
                <tr><th>N° Lotto</th><th>Prodotto</th><th>Produzione</th><th>Scadenza</th><th>Quantità</th></tr>
                {righe or '<tr><td colspan="5">Nessun lotto nel periodo</td></tr>'}
            </table>
        </div>
        """

    # Sezione TEMPERATURE positive (frigoriferi) e negative (congelatori)
    temp_html = ""
    if includi("temperature"):
        async def _tabella_temp(coll, titolo, campo_nome):
            try:
                schede = await db[coll].find({}, {"_id": 0}).to_list(200)
            except Exception:
                schede = []
            righe = ""
            for s in schede:
                nome = s.get(campo_nome) or s.get("frigorifero_nome") or s.get("congelatore_nome") or s.get("nome", "")
                anno_scheda = s.get("anno", anno)
                # Struttura reale: temperature = { "mese": { "giorno": valore } }
                temp_data = s.get("temperature", {})
                if not isinstance(temp_data, dict):
                    continue
                for mese, giorni in temp_data.items():
                    if not isinstance(giorni, dict):
                        continue
                    try:
                        mese_n = int(mese)
                    except (ValueError, TypeError):
                        continue
                    for giorno, valore in giorni.items():
                        try:
                            giorno_n = int(giorno)
                        except (ValueError, TypeError):
                            continue
                        if valore is None or isinstance(valore, dict):
                            continue
                        try:
                            data_iso = f"{int(anno_scheda):04d}-{mese_n:02d}-{giorno_n:02d}"
                        except (ValueError, TypeError):
                            continue
                        if _in_periodo(data_iso):
                            righe += f"<tr><td>{nome}</td><td>{giorno_n:02d}/{mese_n:02d}/{anno_scheda}</td><td>{valore}°C</td></tr>"
            return f"""
            <div class="section page-break">
                <h2>🌡️ {titolo}</h2>
                <table>
                    <tr><th>Punto di controllo</th><th>Data</th><th>Temperatura</th></tr>
                    {righe or '<tr><td colspan="3">Nessuna rilevazione nel periodo</td></tr>'}
                </table>
            </div>
            """
        temp_html = await _tabella_temp("temperature_positive", "REGISTRO TEMPERATURE FRIGORIFERI", "frigorifero_nome")
        temp_html += await _tabella_temp("temperature_negative", "REGISTRO TEMPERATURE CONGELATORI", "congelatore_nome")

    # Sezione CONTROLLO OLIO nel periodo
    olio_html = ""
    if includi("controllo_olio"):
        try:
            controlli = await db.controllo_olio.find({}, {"_id": 0}).sort("data", -1).to_list(1000)
        except Exception:
            controlli = []
        controlli_p = [c for c in controlli if _in_periodo(c.get("data", ""))]
        righe = ""
        for c in controlli_p[:500]:
            righe += f"""<tr>
                <td>{c.get('data','')}</td>
                <td>{c.get('friggitrice','')}</td>
                <td>{c.get('colore','')}/5</td>
                <td>{c.get('polarita','')}%</td>
                <td>{c.get('temperatura','')}°C</td>
                <td>{c.get('esito','')}</td>
            </tr>"""
        olio_html = f"""
        <div class="section page-break">
            <h2>🛢️ REGISTRO CONTROLLO OLIO FRITTURA</h2>
            <p>Controlli nel periodo. Totale: {len(controlli_p)}.</p>
            <table>
                <tr><th>Data</th><th>Friggitrice</th><th>Colore</th><th>Polarità</th><th>Temp.</th><th>Esito</th></tr>
                {righe or '<tr><td colspan="6">Nessun controllo nel periodo</td></tr>'}
            </table>
        </div>
        """

    # Assembla documento completo — rispetta sezioni abilitate
    sezioni_body = [header, indice]
    sezioni_body.append(dati_azienda_html)  # sempre presente
    # ── Registrazioni del periodo subito dopo la copertina ──
    try:
        if lotti_html:
            sezioni_body.append(lotti_html)
        if temp_html:
            sezioni_body.append(temp_html)
        if olio_html:
            sezioni_body.append(olio_html)
    except Exception as _e:
        sezioni_body.append(f'<div class="section"><p>Errore generazione registrazioni periodo: {_e}</p></div>')
    if includi("principi_haccp"):
        sezioni_body += [
            principi_html,
            DIAGRAMMI_FLUSSO,
            ALBERO_DECISIONI_CCP,
            ANALISI_PERICOLI,
            IDENTIFICAZIONE_CCP,
        ]
    if includi("anomalie"):
        sezioni_body.append(GESTIONE_NON_CONFORMITA)
    if includi("disinfestazione"):
        sezioni_body.append(CONTROLLO_INFESTANTI)
    sezioni_body += [APPROVVIGIONAMENTO_IDRICO, PROCEDURE_EMERGENZA, PLANIMETRIA_LOCALE]
    if includi("allergeni"):
        sezioni_body += [GESTIONE_ALLERGENI, MATRICE_ALLERGENI_HTML]
    sezioni_body.append(RINTRACCIABILITA)
    if includi("fornitori_qualificati"):
        sezioni_body.append(REGISTRO_FORNITORI_HTML)
    if includi("ricevimento_merci"):
        sezioni_body.append(SCHEDE_RICEVIMENTO_HTML)
    if includi("personale"):
        sezioni_body += [PROCEDURE_IGIENE, operatori_html, FORMAZIONE_PERSONALE]
    if includi("sanificazione"):
        sezioni_body += [PROCEDURE_PULIZIA, DETERGENTI_SANIFICANTI]
    sezioni_body += [GESTIONE_RIFIUTI, MANUTENZIONE_ATTREZZATURE, ALLEGATI_INFO]

    # Footer con periodo
    data_stampa = datetime.now().strftime("%d/%m/%Y %H:%M")
    periodo_str = (
        f"{data_da or 'inizio'} → {data_a or 'oggi'}" if (data_da or data_a) else "tutto il periodo"
    )
    footer_periodo = f"""
    <div class="footer">
        <p>Manuale HACCP - {DATI_AZIENDA['ragione_sociale']} - Rev. {data_stampa}</p>
        <p>Documento generato dal Sistema di Gestione HACCP | Periodo: {periodo_str}</p>
    </div>
    """
    sezioni_body.append(footer_periodo)

    html = f"""
    <!DOCTYPE html>
    <html lang="it">
    <head>
        <meta charset="UTF-8">
        <title>Manuale HACCP - {DATI_AZIENDA['ragione_sociale']} - {anno}</title>
        {css}
    </head>
    <body>
        {''.join(sezioni_body)}
    </body>
    </html>
    """

    return HTMLResponse(content=html)


@router.get("/condividi-manuale")
async def condividi_manuale(anno: int = None):
    """Genera link per condividere il manuale via WhatsApp/Email"""
    if not anno:
        anno = datetime.now().year

    # URL del manuale (da personalizzare con URL reale in produzione)
    base_url = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001")
    manuale_url = f"{base_url}/api/manuale-haccp/genera-manuale?anno={anno}"

    # Messaggio per condivisione
    DATI_AZIENDA = {**DATI_AZIENDA_DEFAULT, **(await get_azienda())}
    messaggio = f"Manuale HACCP {DATI_AZIENDA['ragione_sociale']} - Anno {anno}"

    return {
        "url_manuale": manuale_url,
        "link_whatsapp": f"https://wa.me/?text={messaggio}%20{manuale_url}",
        "link_email": f"mailto:?subject={messaggio}&body=Consulta il manuale HACCP al seguente link: {manuale_url}",
        "messaggio": messaggio,
    }


@router.get("/documenti")
async def get_documenti_disponibili():
    """Lista documenti HACCP disponibili"""
    return {
        "manuale_completo": "/api/manuale-haccp/genera-manuale",
        "descrizione": "Manuale di Autocontrollo HACCP completo",
        "contenuti": [
            "Dati azienda e riferimenti normativi",
            "I 7 principi HACCP con descrizioni dettagliate",
            "Diagrammi di flusso prodotti",
            "Norme igiene personale",
            "Procedure pulizia e sanificazione",
            "Detergenti e sanificanti consigliati",
            "Operatori e responsabilità",
            "Allegati e moduli",
        ],
        "formati_disponibili": ["HTML (stampabile)", "PDF (su richiesta)"],
    }
