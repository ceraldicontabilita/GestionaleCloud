"""
Contabilità Italiana Completa
=============================

Implementazione completa della contabilità secondo le norme italiane:

1. CESPITI E AMMORTAMENTI
   - Registrazione acquisto beni strumentali
   - Calcolo ammortamento secondo coefficienti ministeriali
   - Libro cespiti

2. BILANCIO CEE (IV Direttiva / Codice Civile)
   - Stato Patrimoniale (Attivo/Passivo)
   - Conto Economico
   - Nota Integrativa

3. PRIMA NOTA CASSA E BANCA
   - Giornale di cassa
   - Giornale banca
   - Versamenti e prelievi

4. STIPENDI E PERSONALE
   - Acconti su stipendi
   - Registrazione buste paga
   - Contributi INPS/INAIL
   - TFR

5. RITENUTE D'ACCONTO
   - Professionisti
   - Agenti
   - Certificazione Unica

6. RATEI E RISCONTI
   - Scritture di assestamento
   - Competenza temporale

7. CHIUSURA ESERCIZIO
   - Scritture di chiusura
   - Determinazione utile/perdita
   - Riapertura conti
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel, Field

from app.database import Database

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================
# COEFFICIENTI AMMORTAMENTO MINISTERIALI
# D.M. 31/12/1988 e successive modifiche
# ============================================

COEFFICIENTI_AMMORTAMENTO = {
    # Fabbricati
    'fabbricati_industriali': 3.0,
    'fabbricati_commerciali': 3.0,
    'costruzioni_leggere': 10.0,
    
    # Impianti e macchinari
    'impianti_generici': 10.0,
    'impianti_specifici': 15.0,
    'macchinari': 15.0,
    
    # Attrezzature
    'attrezzature': 15.0,
    'attrezzature_varie': 15.0,
    
    # Mobili e arredi
    'mobili_arredi': 12.0,
    'mobili_ufficio': 12.0,
    
    # Macchine ufficio
    'macchine_ufficio_elettroniche': 20.0,
    'computer': 20.0,
    'software': 20.0,
    
    # Automezzi
    'autovetture': 25.0,
    'autocarri': 20.0,
    'motocicli': 25.0,
    
    # Beni immateriali
    'brevetti': 20.0,
    'marchi': 10.0,
    'avviamento': 10.0,  # Max 10 anni
}


# ============================================
# PIANO DEI CONTI BILANCIO CEE
# Struttura secondo Codice Civile art. 2424-2425
# ============================================

PIANO_CONTI_CEE = {
    # === STATO PATRIMONIALE - ATTIVO ===
    # A) Crediti verso soci
    'A_crediti_soci': {'code': '100000', 'name': 'Crediti verso soci per versamenti dovuti', 'cee': 'A'},
    
    # B) Immobilizzazioni
    # B.I - Immobilizzazioni immateriali
    'BI1_costi_impianto': {'code': '110100', 'name': 'Costi di impianto e ampliamento', 'cee': 'B.I.1'},
    'BI2_costi_sviluppo': {'code': '110200', 'name': 'Costi di sviluppo', 'cee': 'B.I.2'},
    'BI3_brevetti': {'code': '110300', 'name': 'Diritti brevetti e utilizz. opere ingegno', 'cee': 'B.I.3'},
    'BI4_concessioni': {'code': '110400', 'name': 'Concessioni, licenze, marchi', 'cee': 'B.I.4'},
    'BI5_avviamento': {'code': '110500', 'name': 'Avviamento', 'cee': 'B.I.5'},
    'BI6_immob_corso': {'code': '110600', 'name': 'Immobilizzazioni in corso e acconti', 'cee': 'B.I.6'},
    'BI7_altre_immob': {'code': '110700', 'name': 'Altre immobilizzazioni immateriali', 'cee': 'B.I.7'},
    
    # B.II - Immobilizzazioni materiali
    'BII1_terreni': {'code': '120100', 'name': 'Terreni e fabbricati', 'cee': 'B.II.1'},
    'BII2_impianti': {'code': '120200', 'name': 'Impianti e macchinario', 'cee': 'B.II.2'},
    'BII3_attrezzature': {'code': '120300', 'name': 'Attrezzature industriali e commerciali', 'cee': 'B.II.3'},
    'BII4_altri_beni': {'code': '120400', 'name': 'Altri beni', 'cee': 'B.II.4'},
    'BII5_immob_corso': {'code': '120500', 'name': 'Immobilizzazioni in corso e acconti', 'cee': 'B.II.5'},
    
    # Fondi ammortamento
    'fondo_amm_fabbricati': {'code': '125100', 'name': 'Fondo amm.to fabbricati', 'cee': 'B.II.1'},
    'fondo_amm_impianti': {'code': '125200', 'name': 'Fondo amm.to impianti', 'cee': 'B.II.2'},
    'fondo_amm_attrezzature': {'code': '125300', 'name': 'Fondo amm.to attrezzature', 'cee': 'B.II.3'},
    'fondo_amm_altri_beni': {'code': '125400', 'name': 'Fondo amm.to altri beni', 'cee': 'B.II.4'},
    
    # C) Attivo circolante
    # C.I - Rimanenze
    'CI1_materie_prime': {'code': '130100', 'name': 'Materie prime, sussidiarie e consumo', 'cee': 'C.I.1'},
    'CI2_prodotti_corso': {'code': '130200', 'name': 'Prodotti in corso di lavorazione', 'cee': 'C.I.2'},
    'CI3_lavori_corso': {'code': '130300', 'name': 'Lavori in corso su ordinazione', 'cee': 'C.I.3'},
    'CI4_prodotti_finiti': {'code': '130400', 'name': 'Prodotti finiti e merci', 'cee': 'C.I.4'},
    'CI5_acconti': {'code': '130500', 'name': 'Acconti a fornitori', 'cee': 'C.I.5'},
    
    # C.II - Crediti
    'CII1_crediti_clienti': {'code': '140100', 'name': 'Crediti verso clienti', 'cee': 'C.II.1'},
    'CII2_crediti_controllate': {'code': '140200', 'name': 'Crediti verso imprese controllate', 'cee': 'C.II.2'},
    'CII3_crediti_collegate': {'code': '140300', 'name': 'Crediti verso imprese collegate', 'cee': 'C.II.3'},
    'CII4_crediti_controllanti': {'code': '140400', 'name': 'Crediti verso controllanti', 'cee': 'C.II.4'},
    'CII5_crediti_tributari': {'code': '140500', 'name': 'Crediti tributari', 'cee': 'C.II.5'},
    'CII5bis_imposte_anticipate': {'code': '140510', 'name': 'Imposte anticipate', 'cee': 'C.II.5-bis'},
    'CII5ter_crediti_altri': {'code': '140520', 'name': 'Crediti verso altri', 'cee': 'C.II.5-ter'},
    
    # C.III - Attività finanziarie
    'CIII_partecipazioni': {'code': '150000', 'name': 'Attività finanziarie non immob.', 'cee': 'C.III'},
    
    # C.IV - Disponibilità liquide
    'CIV1_depositi_bancari': {'code': '160100', 'name': 'Depositi bancari e postali', 'cee': 'C.IV.1'},
    'CIV2_assegni': {'code': '160200', 'name': 'Assegni', 'cee': 'C.IV.2'},
    'CIV3_cassa': {'code': '160300', 'name': 'Denaro e valori in cassa', 'cee': 'C.IV.3'},
    
    # D) Ratei e risconti attivi
    'D_ratei_attivi': {'code': '170100', 'name': 'Ratei attivi', 'cee': 'D'},
    'D_risconti_attivi': {'code': '170200', 'name': 'Risconti attivi', 'cee': 'D'},
    
    # === STATO PATRIMONIALE - PASSIVO ===
    # A) Patrimonio netto
    'A1_capitale': {'code': '200100', 'name': 'Capitale sociale', 'cee': 'A.I'},
    'A2_sovrapprezzo': {'code': '200200', 'name': 'Riserva da sovrapprezzo azioni', 'cee': 'A.II'},
    'A3_rivalutazione': {'code': '200300', 'name': 'Riserve di rivalutazione', 'cee': 'A.III'},
    'A4_riserva_legale': {'code': '200400', 'name': 'Riserva legale', 'cee': 'A.IV'},
    'A5_riserve_statutarie': {'code': '200500', 'name': 'Riserve statutarie', 'cee': 'A.V'},
    'A6_altre_riserve': {'code': '200600', 'name': 'Altre riserve', 'cee': 'A.VI'},
    'A7_riserva_copertura': {'code': '200700', 'name': 'Riserva per copertura flussi fin.', 'cee': 'A.VII'},
    'A8_utili_portati': {'code': '200800', 'name': 'Utili (perdite) portati a nuovo', 'cee': 'A.VIII'},
    'A9_utile_esercizio': {'code': '200900', 'name': 'Utile (perdita) dell\'esercizio', 'cee': 'A.IX'},
    
    # B) Fondi per rischi e oneri
    'B1_fondi_pensione': {'code': '210100', 'name': 'Fondi per trattamento quiescenza', 'cee': 'B.1'},
    'B2_fondi_imposte': {'code': '210200', 'name': 'Fondi per imposte, anche differite', 'cee': 'B.2'},
    'B3_fondi_derivati': {'code': '210300', 'name': 'Strumenti finanziari derivati passivi', 'cee': 'B.3'},
    'B4_altri_fondi': {'code': '210400', 'name': 'Altri fondi', 'cee': 'B.4'},
    
    # C) TFR
    'C_tfr': {'code': '220000', 'name': 'Trattamento di fine rapporto', 'cee': 'C'},
    
    # D) Debiti
    'D1_obbligazioni': {'code': '230100', 'name': 'Obbligazioni', 'cee': 'D.1'},
    'D2_obbligazioni_conv': {'code': '230200', 'name': 'Obbligazioni convertibili', 'cee': 'D.2'},
    'D3_debiti_soci': {'code': '230300', 'name': 'Debiti verso soci per finanziamenti', 'cee': 'D.3'},
    'D4_debiti_banche': {'code': '230400', 'name': 'Debiti verso banche', 'cee': 'D.4'},
    'D5_debiti_altri_fin': {'code': '230500', 'name': 'Debiti verso altri finanziatori', 'cee': 'D.5'},
    'D6_acconti': {'code': '230600', 'name': 'Acconti da clienti', 'cee': 'D.6'},
    'D7_debiti_fornitori': {'code': '230700', 'name': 'Debiti verso fornitori', 'cee': 'D.7'},
    'D8_debiti_titoli': {'code': '230800', 'name': 'Debiti rappresentati da titoli di credito', 'cee': 'D.8'},
    'D9_debiti_controllate': {'code': '230900', 'name': 'Debiti verso imprese controllate', 'cee': 'D.9'},
    'D10_debiti_collegate': {'code': '231000', 'name': 'Debiti verso imprese collegate', 'cee': 'D.10'},
    'D11_debiti_controllanti': {'code': '231100', 'name': 'Debiti verso controllanti', 'cee': 'D.11'},
    'D12_debiti_tributari': {'code': '231200', 'name': 'Debiti tributari', 'cee': 'D.12'},
    'D13_debiti_previdenziali': {'code': '231300', 'name': 'Debiti verso istituti previdenza', 'cee': 'D.13'},
    'D14_altri_debiti': {'code': '231400', 'name': 'Altri debiti', 'cee': 'D.14'},
    
    # E) Ratei e risconti passivi
    'E_ratei_passivi': {'code': '240100', 'name': 'Ratei passivi', 'cee': 'E'},
    'E_risconti_passivi': {'code': '240200', 'name': 'Risconti passivi', 'cee': 'E'},
    
    # === CONTO ECONOMICO ===
    # A) Valore della produzione
    'A1_ricavi_vendite': {'code': '300100', 'name': 'Ricavi vendite e prestazioni', 'cee': 'A.1', 'ce': True},
    'A2_var_rimanenze_prod': {'code': '300200', 'name': 'Variazione rimanenze prodotti', 'cee': 'A.2', 'ce': True},
    'A3_var_lavori_corso': {'code': '300300', 'name': 'Variazione lavori in corso', 'cee': 'A.3', 'ce': True},
    'A4_incrementi_immob': {'code': '300400', 'name': 'Incrementi immob. per lavori interni', 'cee': 'A.4', 'ce': True},
    'A5_altri_ricavi': {'code': '300500', 'name': 'Altri ricavi e proventi', 'cee': 'A.5', 'ce': True},
    
    # B) Costi della produzione
    'B6_materie_prime': {'code': '400100', 'name': 'Materie prime, sussidiarie, consumo', 'cee': 'B.6', 'ce': True},
    'B7_servizi': {'code': '400200', 'name': 'Costi per servizi', 'cee': 'B.7', 'ce': True},
    'B8_godimento_terzi': {'code': '400300', 'name': 'Costi per godimento beni di terzi', 'cee': 'B.8', 'ce': True},
    'B9_personale': {'code': '400400', 'name': 'Costi per il personale', 'cee': 'B.9', 'ce': True},
    'B9a_salari': {'code': '400410', 'name': 'Salari e stipendi', 'cee': 'B.9.a', 'ce': True},
    'B9b_oneri_sociali': {'code': '400420', 'name': 'Oneri sociali', 'cee': 'B.9.b', 'ce': True},
    'B9c_tfr': {'code': '400430', 'name': 'Trattamento di fine rapporto', 'cee': 'B.9.c', 'ce': True},
    'B9d_pensione': {'code': '400440', 'name': 'Trattamento di quiescenza', 'cee': 'B.9.d', 'ce': True},
    'B9e_altri_costi_pers': {'code': '400450', 'name': 'Altri costi del personale', 'cee': 'B.9.e', 'ce': True},
    'B10_ammortamenti': {'code': '400500', 'name': 'Ammortamenti e svalutazioni', 'cee': 'B.10', 'ce': True},
    'B10a_amm_immateriali': {'code': '400510', 'name': 'Amm.to immobilizzazioni immateriali', 'cee': 'B.10.a', 'ce': True},
    'B10b_amm_materiali': {'code': '400520', 'name': 'Amm.to immobilizzazioni materiali', 'cee': 'B.10.b', 'ce': True},
    'B10c_svalutazioni_immob': {'code': '400530', 'name': 'Altre svalutazioni immobilizzazioni', 'cee': 'B.10.c', 'ce': True},
    'B10d_svalutazioni_crediti': {'code': '400540', 'name': 'Svalutazione crediti attivo circ.', 'cee': 'B.10.d', 'ce': True},
    'B11_var_rimanenze': {'code': '400600', 'name': 'Variazione rimanenze materie', 'cee': 'B.11', 'ce': True},
    'B12_accantonamenti': {'code': '400700', 'name': 'Accantonamenti per rischi', 'cee': 'B.12', 'ce': True},
    'B13_altri_accantonamenti': {'code': '400800', 'name': 'Altri accantonamenti', 'cee': 'B.13', 'ce': True},
    'B14_oneri_diversi': {'code': '400900', 'name': 'Oneri diversi di gestione', 'cee': 'B.14', 'ce': True},
    
    # C) Proventi e oneri finanziari
    'C15_proventi_partecip': {'code': '500100', 'name': 'Proventi da partecipazioni', 'cee': 'C.15', 'ce': True},
    'C16_altri_proventi_fin': {'code': '500200', 'name': 'Altri proventi finanziari', 'cee': 'C.16', 'ce': True},
    'C17_interessi_oneri': {'code': '500300', 'name': 'Interessi e altri oneri finanziari', 'cee': 'C.17', 'ce': True},
    'C17bis_utili_perdite_cambi': {'code': '500400', 'name': 'Utili e perdite su cambi', 'cee': 'C.17-bis', 'ce': True},
    
    # D) Rettifiche di valore attività finanziarie
    'D18_rivalutazioni': {'code': '600100', 'name': 'Rivalutazioni', 'cee': 'D.18', 'ce': True},
    'D19_svalutazioni': {'code': '600200', 'name': 'Svalutazioni', 'cee': 'D.19', 'ce': True},
    
    # Imposte
    'imposte_correnti': {'code': '700100', 'name': 'Imposte sul reddito correnti', 'cee': '20', 'ce': True},
    'imposte_differite': {'code': '700200', 'name': 'Imposte differite e anticipate', 'cee': '20', 'ce': True},
}


# ============================================
# MODELLI
# ============================================

class CespiteCreate(BaseModel):
    """Registrazione nuovo cespite"""
    descrizione: str
    categoria: str  # Key da COEFFICIENTI_AMMORTAMENTO
    data_acquisto: str
    valore_acquisto: float
    fornitore_id: Optional[str] = None
    fornitore_nome: Optional[str] = None
    fattura_ref: Optional[str] = None
    conto_cespite: str = '120400'  # Default: Altri beni
    conto_fondo: str = '125400'  # Default: Fondo amm. altri beni
    conto_ammortamento: str = '400520'  # Default: Amm.to immob. materiali


class AmmortamentoCalcolo(BaseModel):
    """Parametri calcolo ammortamento"""
    cespite_id: str
    anno: int
    quota_ridotta_primo_anno: bool = True  # Primo anno al 50%


class VersamentoCassa(BaseModel):
    """Versamento contanti in banca"""
    data: str
    importo: float
    causale: Optional[str] = "Versamento contanti"


class PrelievoContanti(BaseModel):
    """Prelievo contanti da banca"""
    data: str
    importo: float
    causale: Optional[str] = "Prelievo contanti"


class AccontoStipendio(BaseModel):
    """Acconto su stipendio"""
    dipendente_id: str
    dipendente_nome: str
    data: str
    importo: float
    modalita: str = "cassa"  # cassa o banca
    note: Optional[str] = None


class RegistrazioneBustaPaga(BaseModel):
    """Registrazione contabile busta paga"""
    dipendente_id: str
    dipendente_nome: str
    mese: int
    anno: int
    data_registrazione: str
    lordo: float
    netto: float
    inps_dipendente: float
    inps_azienda: float
    irpef: float
    addizionali: float = 0
    tfr_mese: float = 0
    acconti_da_recuperare: float = 0  # Acconti già erogati da scalare


class RitenutaAcconto(BaseModel):
    """Registrazione ritenuta d'acconto"""
    fornitore_id: str
    fornitore_nome: str
    data: str
    fattura_ref: str
    imponibile: float
    aliquota_ritenuta: float = 20.0  # Default 20%
    tipo: str = "professionale"  # professionale, agente, occasionale


class RateoRisconto(BaseModel):
    """Scrittura rateo/risconto"""
    tipo: str  # rateo_attivo, rateo_passivo, risconto_attivo, risconto_passivo
    data: str
    importo: float
    descrizione: str
    conto_origine: str  # Costo o ricavo di origine
    data_inizio_competenza: str
    data_fine_competenza: str


# ============================================
# HELPER FUNCTIONS
# ============================================

def round_currency(amount: float) -> float:
    """Arrotonda a 2 decimali"""
    return float(Decimal(str(amount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


async def crea_scrittura_contabile(db, data: str, ref: str, righe: List[Dict], tipo: str = "general") -> str:
    """Helper per creare scrittura contabile bilanciata"""
    move_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    total_dare = sum(r.get('dare', 0) for r in righe)
    total_avere = sum(r.get('avere', 0) for r in righe)
    
    if abs(total_dare - total_avere) > 0.01:
        raise HTTPException(status_code=400, detail=f"Scrittura non bilanciata: DARE {total_dare} ≠ AVERE {total_avere}")
    
    # Header
    await db["prima_nota"].insert_one({
        "id": move_id,
        "date": data,
        "ref": ref,
        "journal_type": tipo,
        "total_debit": round_currency(total_dare),
        "total_credit": round_currency(total_avere),
        "state": "posted",
        "created_at": now
    })
    
    # Righe
    for i, r in enumerate(righe):
        await db["prima_nota_righe"].insert_one({
            "id": str(uuid.uuid4()),
            "move_id": move_id,
            "sequence": i + 1,
            "account_code": r['conto'],
            "account_name": r.get('nome_conto', ''),
            "debit": round_currency(r.get('dare', 0)),
            "credit": round_currency(r.get('avere', 0)),
            "balance": round_currency(r.get('dare', 0) - r.get('avere', 0)),
            "partner_id": r.get('partner_id'),
            "partner_name": r.get('partner_name'),
            "name": r.get('descrizione', ''),
            "date": data,
            "created_at": now
        })
    
    return move_id


# ============================================
# CESPITI E AMMORTAMENTI
# ============================================

@router.post("/cespiti/registra")
async def registra_cespite(cespite: CespiteCreate) -> Dict[str, Any]:
    """
    Registra l'acquisto di un cespite ammortizzabile.
    
    Scrittura contabile:
    - DARE: Conto cespite (es. Impianti)
    - DARE: IVA a credito (se applicabile)
    - AVERE: Debiti vs fornitori (o Banca/Cassa se pagato)
    """
    db = Database.get_db()
    
    # Verifica categoria
    if cespite.categoria not in COEFFICIENTI_AMMORTAMENTO:
        raise HTTPException(status_code=400, detail=f"Categoria non valida. Valide: {list(COEFFICIENTI_AMMORTAMENTO.keys())}")
    
    coeff = COEFFICIENTI_AMMORTAMENTO[cespite.categoria]
    cespite_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    # Calcola IVA (22% default)
    iva = round_currency(cespite.valore_acquisto * 0.22)
    totale = round_currency(cespite.valore_acquisto + iva)
    
    # Scrittura contabile acquisto
    righe = [
        {
            'conto': cespite.conto_cespite,
            'nome_conto': f'Cespite: {cespite.descrizione}',
            'dare': cespite.valore_acquisto,
            'avere': 0,
            'descrizione': f'Acquisto {cespite.descrizione}'
        },
        {
            'conto': '140500',  # IVA a credito
            'nome_conto': 'IVA ns/credito',
            'dare': iva,
            'avere': 0,
            'descrizione': 'IVA 22% su acquisto cespite'
        },
        {
            'conto': '230700',  # Debiti fornitori
            'nome_conto': 'Debiti vs fornitori',
            'dare': 0,
            'avere': totale,
            'partner_id': cespite.fornitore_id,
            'partner_name': cespite.fornitore_nome,
            'descrizione': f'Fattura {cespite.fattura_ref or ""}'
        }
    ]
    
    move_id = await crea_scrittura_contabile(
        db, cespite.data_acquisto, 
        f"CESP/{cespite_id[:8]}", 
        righe, "purchase"
    )
    
    # Salva anagrafica cespite
    doc = {
        "id": cespite_id,
        "descrizione": cespite.descrizione,
        "categoria": cespite.categoria,
        "coefficiente_ammortamento": coeff,
        "data_acquisto": cespite.data_acquisto,
        "valore_acquisto": round_currency(cespite.valore_acquisto),
        "valore_residuo": round_currency(cespite.valore_acquisto),
        "fondo_ammortamento": 0,
        "totale_ammortizzato": 0,
        "conto_cespite": cespite.conto_cespite,
        "conto_fondo": cespite.conto_fondo,
        "conto_ammortamento": cespite.conto_ammortamento,
        "fornitore_id": cespite.fornitore_id,
        "fornitore_nome": cespite.fornitore_nome,
        "fattura_ref": cespite.fattura_ref,
        "stato": "attivo",
        "move_id_acquisto": move_id,
        "ammortamenti": [],
        "created_at": now
    }
    await db["cespiti"].insert_one(doc.copy())
    
    return {
        "success": True,
        "cespite_id": cespite_id,
        "descrizione": cespite.descrizione,
        "valore_acquisto": round_currency(cespite.valore_acquisto),
        "coefficiente": coeff,
        "anni_ammortamento": round(100 / coeff, 1),
        "move_id": move_id
    }


@router.post("/cespiti/ammortamento")
async def calcola_ammortamento(params: AmmortamentoCalcolo) -> Dict[str, Any]:
    """
    Calcola e registra l'ammortamento annuale di un cespite.
    
    Scrittura contabile:
    - DARE: Ammortamento (costo CE)
    - AVERE: Fondo ammortamento (SP)
    
    Primo anno: quota ridotta al 50% (prassi fiscale italiana)
    """
    db = Database.get_db()
    
    cespite = await db["cespiti"].find_one({"id": params.cespite_id})
    if not cespite:
        raise HTTPException(status_code=404, detail="Cespite non trovato")
    
    if cespite.get("stato") != "attivo":
        raise HTTPException(status_code=400, detail="Cespite non più attivo")
    
    # Verifica se già ammortizzato quest'anno
    amm_esistente = [a for a in cespite.get("ammortamenti", []) if a.get("anno") == params.anno]
    if amm_esistente:
        raise HTTPException(status_code=400, detail=f"Ammortamento {params.anno} già registrato")
    
    valore_acquisto = cespite["valore_acquisto"]
    coeff = cespite["coefficiente_ammortamento"]
    fondo_attuale = cespite.get("fondo_ammortamento", 0)
    valore_residuo = valore_acquisto - fondo_attuale
    
    if valore_residuo <= 0:
        raise HTTPException(status_code=400, detail="Cespite completamente ammortizzato")
    
    # Calcola quota ammortamento
    quota_annua = round_currency(valore_acquisto * coeff / 100)
    
    # Primo anno al 50%?
    anno_acquisto = int(cespite["data_acquisto"][:4])
    if params.anno == anno_acquisto and params.quota_ridotta_primo_anno:
        quota_annua = round_currency(quota_annua / 2)
    
    # Non superare il residuo
    if quota_annua > valore_residuo:
        quota_annua = round_currency(valore_residuo)
    
    # Scrittura contabile
    data_amm = f"{params.anno}-12-31"
    righe = [
        {
            'conto': cespite["conto_ammortamento"],
            'nome_conto': 'Ammortamento',
            'dare': quota_annua,
            'avere': 0,
            'descrizione': f'Ammortamento {params.anno} - {cespite["descrizione"]}'
        },
        {
            'conto': cespite["conto_fondo"],
            'nome_conto': 'Fondo ammortamento',
            'dare': 0,
            'avere': quota_annua,
            'descrizione': f'Fondo amm. {cespite["descrizione"]}'
        }
    ]
    
    move_id = await crea_scrittura_contabile(db, data_amm, f"AMM/{params.anno}/{params.cespite_id[:8]}", righe, "general")
    
    # Aggiorna cespite
    nuovo_fondo = round_currency(fondo_attuale + quota_annua)
    nuovo_residuo = round_currency(valore_acquisto - nuovo_fondo)
    
    amm_record = {
        "anno": params.anno,
        "quota": quota_annua,
        "fondo_progressivo": nuovo_fondo,
        "residuo": nuovo_residuo,
        "move_id": move_id,
        "data": data_amm
    }
    
    stato = "attivo" if nuovo_residuo > 0 else "ammortizzato"
    
    await db["cespiti"].update_one(
        {"id": params.cespite_id},
        {
            "$set": {
                "fondo_ammortamento": nuovo_fondo,
                "valore_residuo": nuovo_residuo,
                "totale_ammortizzato": nuovo_fondo,
                "stato": stato
            },
            "$push": {"ammortamenti": amm_record}
        }
    )
    
    return {
        "success": True,
        "cespite_id": params.cespite_id,
        "anno": params.anno,
        "quota_ammortamento": quota_annua,
        "fondo_totale": nuovo_fondo,
        "valore_residuo": nuovo_residuo,
        "stato": stato,
        "move_id": move_id
    }


@router.get("/cespiti")
async def lista_cespiti(stato: str = Query(None)) -> Dict[str, Any]:
    """Lista cespiti con situazione ammortamento"""
    db = Database.get_db()
    
    query = {}
    if stato:
        query["stato"] = stato
    
    cespiti = await db["cespiti"].find(query, {"_id": 0}).to_list(500)
    
    return {
        "success": True,
        "totale": len(cespiti),
        "cespiti": cespiti
    }


# ============================================
# VERSAMENTI E PRELIEVI CASSA/BANCA
# ============================================

@router.post("/cassa-banca/versamento")
async def versamento_in_banca(vers: VersamentoCassa) -> Dict[str, Any]:
    """
    Versamento contanti in banca.
    
    Scrittura:
    - DARE: Banca c/c
    - AVERE: Cassa
    """
    db = Database.get_db()
    
    righe = [
        {
            'conto': '160100',  # Banca
            'nome_conto': 'Depositi bancari',
            'dare': vers.importo,
            'avere': 0,
            'descrizione': vers.causale
        },
        {
            'conto': '160300',  # Cassa
            'nome_conto': 'Cassa',
            'dare': 0,
            'avere': vers.importo,
            'descrizione': vers.causale
        }
    ]
    
    move_id = await crea_scrittura_contabile(db, vers.data, f"VERS/{vers.data}", righe, "bank")
    
    return {
        "success": True,
        "tipo": "versamento",
        "importo": vers.importo,
        "data": vers.data,
        "move_id": move_id
    }


@router.post("/cassa-banca/prelievo")
async def prelievo_contanti(prel: PrelievoContanti) -> Dict[str, Any]:
    """
    Prelievo contanti da banca.
    
    Scrittura:
    - DARE: Cassa
    - AVERE: Banca c/c
    """
    db = Database.get_db()
    
    righe = [
        {
            'conto': '160300',  # Cassa
            'nome_conto': 'Cassa',
            'dare': prel.importo,
            'avere': 0,
            'descrizione': prel.causale
        },
        {
            'conto': '160100',  # Banca
            'nome_conto': 'Depositi bancari',
            'dare': 0,
            'avere': prel.importo,
            'descrizione': prel.causale
        }
    ]
    
    move_id = await crea_scrittura_contabile(db, prel.data, f"PREL/{prel.data}", righe, "cash")
    
    return {
        "success": True,
        "tipo": "prelievo",
        "importo": prel.importo,
        "data": prel.data,
        "move_id": move_id
    }


# ============================================
# ACCONTI STIPENDI
# ============================================

@router.post("/personale/acconto")
async def registra_acconto_stipendio(acc: AccontoStipendio) -> Dict[str, Any]:
    """
    Registra acconto su stipendio.
    
    Scrittura:
    - DARE: Crediti vs dipendenti (o Anticipi a dipendenti)
    - AVERE: Cassa o Banca
    
    L'acconto verrà recuperato in busta paga.
    """
    db = Database.get_db()
    
    conto_uscita = '160300' if acc.modalita == 'cassa' else '160100'
    nome_uscita = 'Cassa' if acc.modalita == 'cassa' else 'Banca'
    
    righe = [
        {
            'conto': '140520',  # Crediti vs altri (dipendenti)
            'nome_conto': 'Anticipi a dipendenti',
            'dare': acc.importo,
            'avere': 0,
            'partner_id': acc.dipendente_id,
            'partner_name': acc.dipendente_nome,
            'descrizione': f'Acconto stipendio {acc.dipendente_nome}'
        },
        {
            'conto': conto_uscita,
            'nome_conto': nome_uscita,
            'dare': 0,
            'avere': acc.importo,
            'descrizione': f'Erogazione acconto {acc.dipendente_nome}'
        }
    ]
    
    move_id = await crea_scrittura_contabile(db, acc.data, f"ACC/{acc.dipendente_id[:8]}/{acc.data}", righe, "cash" if acc.modalita == 'cassa' else "bank")
    
    # Salva acconto per recupero in busta paga
    await db["acconti_stipendi"].insert_one({
        "id": str(uuid.uuid4()),
        "dipendente_id": acc.dipendente_id,
        "dipendente_nome": acc.dipendente_nome,
        "data": acc.data,
        "importo": round_currency(acc.importo),
        "modalita": acc.modalita,
        "note": acc.note,
        "recuperato": False,
        "move_id": move_id,
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    return {
        "success": True,
        "tipo": "acconto_stipendio",
        "dipendente": acc.dipendente_nome,
        "importo": acc.importo,
        "modalita": acc.modalita,
        "move_id": move_id
    }


@router.post("/personale/busta-paga")
async def registra_busta_paga(busta: RegistrazioneBustaPaga) -> Dict[str, Any]:
    """
    Registrazione contabile busta paga.
    
    Scritture:
    1. Costo del personale:
       - DARE: Salari e stipendi (lordo)
       - DARE: Oneri sociali azienda (INPS azienda)
       - DARE: Accantonamento TFR
       - AVERE: Debiti vs dipendenti (netto - acconti)
       - AVERE: Debiti INPS (contributi dip. + azienda)
       - AVERE: Debiti IRPEF (ritenute)
       - AVERE: Fondo TFR
       - AVERE: Crediti vs dipendenti (recupero acconti)
    """
    db = Database.get_db()
    
    netto_da_pagare = round_currency(busta.netto - busta.acconti_da_recuperare)
    totale_inps = round_currency(busta.inps_dipendente + busta.inps_azienda)
    totale_ritenute = round_currency(busta.irpef + busta.addizionali)
    
    righe = [
        # DARE - Costi
        {
            'conto': '400410',  # Salari e stipendi
            'nome_conto': 'Salari e stipendi',
            'dare': busta.lordo,
            'avere': 0,
            'descrizione': f'Stipendio {busta.mese}/{busta.anno} - {busta.dipendente_nome}'
        },
        {
            'conto': '400420',  # Oneri sociali
            'nome_conto': 'Oneri sociali',
            'dare': busta.inps_azienda,
            'avere': 0,
            'descrizione': f'INPS c/azienda {busta.mese}/{busta.anno}'
        },
    ]
    
    # TFR se presente
    if busta.tfr_mese > 0:
        righe.append({
            'conto': '400430',  # TFR costo
            'nome_conto': 'Accantonamento TFR',
            'dare': busta.tfr_mese,
            'avere': 0,
            'descrizione': f'TFR {busta.mese}/{busta.anno}'
        })
    
    # AVERE - Debiti
    righe.extend([
        {
            'conto': '231400',  # Debiti vs dipendenti
            'nome_conto': 'Debiti vs dipendenti',
            'dare': 0,
            'avere': netto_da_pagare,
            'partner_id': busta.dipendente_id,
            'partner_name': busta.dipendente_nome,
            'descrizione': f'Netto {busta.mese}/{busta.anno}'
        },
        {
            'conto': '231300',  # Debiti INPS
            'nome_conto': 'Debiti vs INPS',
            'dare': 0,
            'avere': totale_inps,
            'descrizione': f'Contributi {busta.mese}/{busta.anno}'
        },
        {
            'conto': '231200',  # Debiti tributari (IRPEF)
            'nome_conto': 'Debiti tributari',
            'dare': 0,
            'avere': totale_ritenute,
            'descrizione': f'IRPEF + Add. {busta.mese}/{busta.anno}'
        },
    ])
    
    # Fondo TFR
    if busta.tfr_mese > 0:
        righe.append({
            'conto': '220000',  # Fondo TFR
            'nome_conto': 'Fondo TFR',
            'dare': 0,
            'avere': busta.tfr_mese,
            'descrizione': f'Acc. TFR {busta.mese}/{busta.anno}'
        })
    
    # Recupero acconti
    if busta.acconti_da_recuperare > 0:
        righe.append({
            'conto': '140520',  # Crediti vs dipendenti
            'nome_conto': 'Anticipi a dipendenti',
            'dare': 0,
            'avere': busta.acconti_da_recuperare,
            'partner_id': busta.dipendente_id,
            'partner_name': busta.dipendente_nome,
            'descrizione': f'Recupero acconti {busta.dipendente_nome}'
        })
        
        # Marca acconti come recuperati
        await db["acconti_stipendi"].update_many(
            {"dipendente_id": busta.dipendente_id, "recuperato": False},
            {"$set": {"recuperato": True, "mese_recupero": f"{busta.anno}-{busta.mese:02d}"}}
        )
    
    move_id = await crea_scrittura_contabile(
        db, busta.data_registrazione, 
        f"PAGA/{busta.anno}/{busta.mese:02d}/{busta.dipendente_id[:8]}", 
        righe, "general"
    )
    
    return {
        "success": True,
        "tipo": "busta_paga",
        "dipendente": busta.dipendente_nome,
        "periodo": f"{busta.mese}/{busta.anno}",
        "lordo": busta.lordo,
        "netto": busta.netto,
        "netto_da_pagare": netto_da_pagare,
        "acconti_recuperati": busta.acconti_da_recuperare,
        "move_id": move_id
    }


# ============================================
# RITENUTE D'ACCONTO
# ============================================

@router.post("/ritenute/registra")
async def registra_ritenuta_acconto(rit: RitenutaAcconto) -> Dict[str, Any]:
    """
    Registra fattura con ritenuta d'acconto.
    
    Es. Fattura professionista €1000 + IVA 22% - Ritenuta 20%:
    - Imponibile: €1000
    - IVA: €220
    - Ritenuta 20%: €200 (su imponibile)
    - Totale fattura: €1220
    - Da pagare al fornitore: €1020 (totale - ritenuta)
    - Da versare all'Erario: €200 (ritenuta)
    """
    db = Database.get_db()
    
    iva = round_currency(rit.imponibile * 0.22)
    totale_fattura = round_currency(rit.imponibile + iva)
    ritenuta = round_currency(rit.imponibile * rit.aliquota_ritenuta / 100)
    da_pagare = round_currency(totale_fattura - ritenuta)
    
    righe = [
        {
            'conto': '400200',  # Costi per servizi
            'nome_conto': 'Costi per servizi',
            'dare': rit.imponibile,
            'avere': 0,
            'descrizione': f'{rit.tipo} - {rit.fornitore_nome}'
        },
        {
            'conto': '140500',  # IVA credito
            'nome_conto': 'IVA ns/credito',
            'dare': iva,
            'avere': 0,
            'descrizione': 'IVA 22%'
        },
        {
            'conto': '230700',  # Debiti fornitori
            'nome_conto': 'Debiti vs fornitori',
            'dare': 0,
            'avere': da_pagare,
            'partner_id': rit.fornitore_id,
            'partner_name': rit.fornitore_nome,
            'descrizione': f'Fattura {rit.fattura_ref} al netto ritenuta'
        },
        {
            'conto': '231200',  # Debiti tributari (Erario c/ritenute)
            'nome_conto': 'Erario c/ritenute',
            'dare': 0,
            'avere': ritenuta,
            'descrizione': f'Ritenuta {rit.aliquota_ritenuta}% su {rit.fattura_ref}'
        }
    ]
    
    move_id = await crea_scrittura_contabile(db, rit.data, f"RIT/{rit.fattura_ref}", righe, "purchase")
    
    # Salva per CU
    await db["ritenute_acconto"].insert_one({
        "id": str(uuid.uuid4()),
        "fornitore_id": rit.fornitore_id,
        "fornitore_nome": rit.fornitore_nome,
        "data": rit.data,
        "fattura_ref": rit.fattura_ref,
        "imponibile": round_currency(rit.imponibile),
        "aliquota": rit.aliquota_ritenuta,
        "ritenuta": ritenuta,
        "tipo": rit.tipo,
        "versata": False,
        "move_id": move_id,
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    return {
        "success": True,
        "tipo": "ritenuta_acconto",
        "fornitore": rit.fornitore_nome,
        "imponibile": rit.imponibile,
        "iva": iva,
        "totale_fattura": totale_fattura,
        "ritenuta": ritenuta,
        "da_pagare_fornitore": da_pagare,
        "da_versare_erario": ritenuta,
        "move_id": move_id
    }


# ============================================
# RATEI E RISCONTI
# ============================================

@router.post("/assestamento/rateo-risconto")
async def registra_rateo_risconto(rr: RateoRisconto) -> Dict[str, Any]:
    """
    Registra scrittura di rateo o risconto.
    
    - RATEO ATTIVO: Ricavo di competenza non ancora fatturato
      DARE: Ratei attivi, AVERE: Ricavo
      
    - RATEO PASSIVO: Costo di competenza non ancora fatturato
      DARE: Costo, AVERE: Ratei passivi
      
    - RISCONTO ATTIVO: Costo pagato ma di competenza futura
      DARE: Risconti attivi, AVERE: Costo (storno)
      
    - RISCONTO PASSIVO: Ricavo incassato ma di competenza futura
      DARE: Ricavo (storno), AVERE: Risconti passivi
    """
    db = Database.get_db()
    
    conti_map = {
        'rateo_attivo': ('170100', 'Ratei attivi', rr.conto_origine, True),  # DARE rateo, AVERE ricavo
        'rateo_passivo': (rr.conto_origine, '', '240100', True),  # DARE costo, AVERE rateo
        'risconto_attivo': ('170200', 'Risconti attivi', rr.conto_origine, True),  # DARE risconto, AVERE costo
        'risconto_passivo': (rr.conto_origine, '', '240200', True),  # DARE ricavo, AVERE risconto
    }
    
    if rr.tipo not in conti_map:
        raise HTTPException(status_code=400, detail=f"Tipo non valido: {rr.tipo}")
    
    if rr.tipo == 'rateo_attivo':
        righe = [
            {'conto': '170100', 'nome_conto': 'Ratei attivi', 'dare': rr.importo, 'avere': 0, 'descrizione': rr.descrizione},
            {'conto': rr.conto_origine, 'nome_conto': 'Ricavo', 'dare': 0, 'avere': rr.importo, 'descrizione': rr.descrizione}
        ]
    elif rr.tipo == 'rateo_passivo':
        righe = [
            {'conto': rr.conto_origine, 'nome_conto': 'Costo', 'dare': rr.importo, 'avere': 0, 'descrizione': rr.descrizione},
            {'conto': '240100', 'nome_conto': 'Ratei passivi', 'dare': 0, 'avere': rr.importo, 'descrizione': rr.descrizione}
        ]
    elif rr.tipo == 'risconto_attivo':
        righe = [
            {'conto': '170200', 'nome_conto': 'Risconti attivi', 'dare': rr.importo, 'avere': 0, 'descrizione': rr.descrizione},
            {'conto': rr.conto_origine, 'nome_conto': 'Costo (storno)', 'dare': 0, 'avere': rr.importo, 'descrizione': f'Storno {rr.descrizione}'}
        ]
    else:  # risconto_passivo
        righe = [
            {'conto': rr.conto_origine, 'nome_conto': 'Ricavo (storno)', 'dare': rr.importo, 'avere': 0, 'descrizione': f'Storno {rr.descrizione}'},
            {'conto': '240200', 'nome_conto': 'Risconti passivi', 'dare': 0, 'avere': rr.importo, 'descrizione': rr.descrizione}
        ]
    
    move_id = await crea_scrittura_contabile(db, rr.data, f"ASS/{rr.tipo[:3].upper()}/{rr.data}", righe, "general")
    
    return {
        "success": True,
        "tipo": rr.tipo,
        "importo": rr.importo,
        "descrizione": rr.descrizione,
        "competenza": f"{rr.data_inizio_competenza} - {rr.data_fine_competenza}",
        "move_id": move_id
    }


# ============================================
# BILANCIO CEE
# ============================================

@router.get("/bilancio/stato-patrimoniale")
async def get_stato_patrimoniale(anno: int = Query(...)) -> Dict[str, Any]:
    """
    Genera lo Stato Patrimoniale secondo schema CEE.
    
    Art. 2424 Codice Civile
    """
    db = Database.get_db()
    
    # Query saldi al 31/12
    data_fine = f"{anno}-12-31"
    
    pipeline = [
        {"$match": {"date": {"$lte": data_fine}}},
        {
            "$group": {
                "_id": "$account_code",
                "account_name": {"$first": "$account_name"},
                "totale_dare": {"$sum": "$debit"},
                "totale_avere": {"$sum": "$credit"}
            }
        }
    ]
    
    saldi = await db["prima_nota_righe"].aggregate(pipeline).to_list(500)
    
    # Organizza per sezione CEE
    attivo = {"totale": 0, "sezioni": {}}
    passivo = {"totale": 0, "sezioni": {}}
    
    for s in saldi:
        code = s["_id"]
        saldo = round_currency(s["totale_dare"] - s["totale_avere"])
        
        if not code:
            continue
            
        # Classifica per primo carattere codice
        if code.startswith('1'):  # Attivo
            if saldo > 0:
                attivo["totale"] += saldo
                sezione = code[:2]
                if sezione not in attivo["sezioni"]:
                    attivo["sezioni"][sezione] = {"conti": [], "totale": 0}
                attivo["sezioni"][sezione]["conti"].append({
                    "codice": code,
                    "nome": s.get("account_name", ""),
                    "saldo": saldo
                })
                attivo["sezioni"][sezione]["totale"] += saldo
                
        elif code.startswith('2'):  # Passivo + PN
            if saldo != 0:
                # I conti passivo hanno saldo avere (negativo in questa logica)
                saldo_passivo = -saldo if saldo < 0 else saldo
                passivo["totale"] += saldo_passivo
                sezione = code[:2]
                if sezione not in passivo["sezioni"]:
                    passivo["sezioni"][sezione] = {"conti": [], "totale": 0}
                passivo["sezioni"][sezione]["conti"].append({
                    "codice": code,
                    "nome": s.get("account_name", ""),
                    "saldo": saldo_passivo
                })
                passivo["sezioni"][sezione]["totale"] += saldo_passivo
    
    return {
        "success": True,
        "anno": anno,
        "data_riferimento": data_fine,
        "attivo": attivo,
        "passivo": passivo,
        "quadratura": round_currency(attivo["totale"] - passivo["totale"])
    }


@router.get("/bilancio/conto-economico")
async def get_conto_economico(anno: int = Query(...)) -> Dict[str, Any]:
    """
    Genera il Conto Economico secondo schema CEE.
    
    Art. 2425 Codice Civile
    """
    db = Database.get_db()
    
    # Query movimenti dell'anno
    data_inizio = f"{anno}-01-01"
    data_fine = f"{anno}-12-31"
    
    pipeline = [
        {"$match": {"date": {"$gte": data_inizio, "$lte": data_fine}}},
        {
            "$group": {
                "_id": "$account_code",
                "account_name": {"$first": "$account_name"},
                "totale_dare": {"$sum": "$debit"},
                "totale_avere": {"$sum": "$credit"}
            }
        }
    ]
    
    saldi = await db["prima_nota_righe"].aggregate(pipeline).to_list(500)
    
    ricavi = {"totale": 0, "voci": []}
    costi = {"totale": 0, "voci": []}
    
    for s in saldi:
        code = s["_id"]
        if not code:
            continue
            
        # Ricavi (codici 3xx, 5xx, 6xx positivi)
        if code.startswith('3') or code.startswith('5'):
            importo = round_currency(s["totale_avere"] - s["totale_dare"])
            if importo != 0:
                ricavi["totale"] += importo
                ricavi["voci"].append({
                    "codice": code,
                    "nome": s.get("account_name", ""),
                    "importo": importo
                })
        
        # Costi (codici 4xx)
        elif code.startswith('4'):
            importo = round_currency(s["totale_dare"] - s["totale_avere"])
            if importo != 0:
                costi["totale"] += importo
                costi["voci"].append({
                    "codice": code,
                    "nome": s.get("account_name", ""),
                    "importo": importo
                })
    
    utile_perdita = round_currency(ricavi["totale"] - costi["totale"])
    
    return {
        "success": True,
        "anno": anno,
        "periodo": f"{data_inizio} - {data_fine}",
        "valore_produzione": ricavi,
        "costi_produzione": costi,
        "risultato_operativo": utile_perdita,
        "utile_perdita_esercizio": utile_perdita
    }
