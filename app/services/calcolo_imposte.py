"""
Servizio Calcolo Imposte IRES e IRAP

Calcola le imposte in tempo reale basandosi su:
- Risultato del Conto Economico
- Variazioni fiscali in aumento/diminuzione
- Aliquote vigenti (IRES 24%, IRAP variabile per regione)

Riferimenti normativi:
- TUIR (DPR 917/1986) per IRES
- D.Lgs. 446/1997 per IRAP
"""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


# ============== ALIQUOTE E LIMITI ==============

# Aliquota IRES ordinaria
ALIQUOTA_IRES = 24.0  # 24%

# Aliquote IRAP per regione (2024-2025)
ALIQUOTE_IRAP = {
    "default": 3.9,  # Aliquota ordinaria
    "abruzzo": 3.9,
    "basilicata": 3.9,
    "calabria": 3.9,
    "campania": 4.97,
    "emilia_romagna": 3.9,
    "friuli_venezia_giulia": 3.9,
    "lazio": 4.82,
    "liguria": 4.9,
    "lombardia": 3.9,
    "marche": 4.73,
    "molise": 4.97,
    "piemonte": 4.20,
    "puglia": 4.82,
    "sardegna": 3.9,
    "sicilia": 4.82,
    "toscana": 3.9,
    "trentino_alto_adige": 2.68,
    "umbria": 4.82,
    "valle_aosta": 2.98,
    "veneto": 3.9,
}

# Deduzioni IRAP
DEDUZIONE_IRAP_BASE = 8000  # Per soggetti con base imponibile <= €180.759,91
DEDUZIONE_IRAP_DIPENDENTI = 7500  # Per ogni dipendente a tempo indeterminato

# Limiti deducibilità specifici
LIMITI_DEDUCIBILITA = {
    "telefonia": 80,  # Art. 102 TUIR - 80%
    "auto_aziendali": 20,  # Art. 164 TUIR - 20% (uso promiscuo)
    "auto_agenti": 80,  # Art. 164 TUIR - 80% (agenti/rappresentanti)
    "rappresentanza": {  # Art. 108 TUIR
        "fino_10m": 1.5,  # 1.5% del fatturato fino a 10M
        "10m_50m": 0.6,  # 0.6% tra 10M e 50M
        "oltre_50m": 0.4,  # 0.4% oltre 50M
    },
    "interessi_passivi_rol": 30,  # Art. 96 TUIR - max 30% ROL
    "ammortamento_auto": 18076,  # Limite costo auto deducibile
    "noleggio_auto_annuo": 3615.20,  # Limite annuo noleggio auto
    "omaggi_unitario": 50,  # Art. 108 TUIR - omaggi fino a €50 interamente deducibili
}


@dataclass
class VariazioneFiscale:
    """Rappresenta una variazione fiscale in aumento o diminuzione"""
    descrizione: str
    importo: float
    tipo: str  # "aumento" o "diminuzione"
    norma_riferimento: str
    applicabile_irap: bool = True


@dataclass
class CalcoloImposte:
    """Risultato del calcolo imposte"""
    # Dati di base
    utile_civilistico: float

    # Variazioni IRES
    variazioni_aumento_ires: List[VariazioneFiscale]
    variazioni_diminuzione_ires: List[VariazioneFiscale]
    totale_variazioni_aumento_ires: float
    totale_variazioni_diminuzione_ires: float
    reddito_imponibile_ires: float
    ires_dovuta: float

    # Variazioni IRAP
    variazioni_aumento_irap: List[VariazioneFiscale]
    variazioni_diminuzione_irap: List[VariazioneFiscale]
    valore_produzione_irap: float
    deduzioni_irap: float
    base_imponibile_irap: float
    irap_dovuta: float

    # Totali
    totale_imposte: float
    aliquota_effettiva: float

    # Basi dal libro giornale (audit 27/09/2026) e cio' che manca per
    # fidarsi del numero: un registro vuoto non e' un utile zero.
    ricavi: Optional[float] = None
    costi: Optional[float] = None
    fonte: str = "movimenti_contabili"
    avvisi: List[str] = field(default_factory=list)


# Macro-gruppi CEE (piano_conti_ufficiale) usati dal valore della produzione
# IRAP: B.9 costi del personale e C.17 oneri finanziari.
_MACRO_PERSONALE = "67"
_MACRO_ONERI_FINANZIARI = "75"


def _anno_scrittura(scrittura: Dict[str, Any]) -> Optional[int]:
    try:
        return int(scrittura.get("anno"))
    except (TypeError, ValueError):
        data = str(scrittura.get("data_documento") or scrittura.get("data") or "")
        try:
            return int(data[:4])
        except ValueError:
            return None


async def basi_imponibili_da_giornale(db, anno: int) -> Dict[str, Any]:
    """Ricavi e costi dell'anno dal LIBRO GIORNALE, classificati col piano
    ufficiale CEE (``sezione_di`` via ``mapping_piano_conti``).

    Audit 27/09/2026 (punto 2): prima i costi erano il ``total_amount`` (IVA
    compresa) di TUTTE le fatture, archiviate comprese, e i ricavi il totale
    dei corrispettivi — cancellati compresi — diviso 1,10, un'aliquota
    inventata. Il giornale ha gia' scorporato l'IVA dall'XML, esclude i
    documenti non attivi e riduce i costi con le note di credito: le basi
    vengono da li'. La chiusura d'esercizio non si somma (azzererebbe i conti
    economici). ``costi_per_codice`` resta per codice di riga, cosi' le
    variazioni fiscali si leggono sugli stessi alias operativi di prima.
    """
    from app.services.mapping_piano_conti import categoria_cee, risolvi_codice_cee
    from app.services.registrazione_contabile import FILTRO_SCRITTURA_ATTIVA

    scritture = await db["movimenti_contabili"].find(
        dict(FILTRO_SCRITTURA_ATTIVA),
        {"_id": 0, "righe": 1, "anno": 1, "data": 1, "data_documento": 1, "tipo": 1},
    ).to_list(None)
    ricavi = costi = personale = oneri_finanziari = 0.0
    costi_per_codice: Dict[str, Dict[str, Any]] = {}
    scritture_anno = 0
    for scrittura in scritture:
        if _anno_scrittura(scrittura) != anno or scrittura.get("tipo") == "chiusura_esercizio":
            continue
        righe = scrittura.get("righe") or []
        if righe:
            scritture_anno += 1
        for riga in righe:
            codice = str(riga.get("conto_codice") or riga.get("conto") or "").strip()
            cee = risolvi_codice_cee(codice)
            categoria = categoria_cee(cee) if cee else None
            if categoria not in {"ricavi", "costi"}:
                continue
            try:
                dare = float(riga.get("dare") or 0)
                avere = float(riga.get("avere") or 0)
            except (TypeError, ValueError):
                logger.warning("Riga non numerica nel giornale (conto %s): esclusa dalle basi", codice)
                continue
            if categoria == "ricavi":
                ricavi += avere - dare
                continue
            importo = dare - avere
            costi += importo
            voce = costi_per_codice.setdefault(codice, {"nome": riga.get("conto_nome") or "", "importo": 0.0})
            voce["importo"] += importo
            if cee.startswith(_MACRO_PERSONALE):
                personale += importo
            elif cee.startswith(_MACRO_ONERI_FINANZIARI):
                oneri_finanziari += importo
    for voce in costi_per_codice.values():
        voce["importo"] = round(voce["importo"], 2)
    return {
        "ricavi": round(ricavi, 2),
        "costi": round(costi, 2),
        "costi_per_codice": costi_per_codice,
        "costo_personale": round(personale, 2),
        "costo_interessi": round(oneri_finanziari, 2),
        "scritture": scritture_anno,
    }


class CalcolatoreImposte:
    """
    Calcola IRES e IRAP basandosi sui dati contabili.

    Logica:
    1. Parte dall'utile civilistico (Ricavi - Costi)
    2. Applica variazioni in aumento (costi non deducibili)
    3. Applica variazioni in diminuzione (agevolazioni)
    4. Calcola imposte su base imponibile finale
    """

    def __init__(self, regione: str = "default"):
        self.regione = regione.lower().replace(" ", "_")
        self.aliquota_irap = ALIQUOTE_IRAP.get(self.regione, ALIQUOTE_IRAP["default"])

    async def calcola_imposte_da_db(self, db, anno: int = None) -> CalcoloImposte:
        """
        Calcola le imposte partendo dai dati nel database.
        Le basi vengono dal libro giornale (`basi_imponibili_da_giornale`).

        Args:
            db: Riferimento all'archivio del runtime
            anno: Anno fiscale (opzionale, default anno corrente)

        Returns:
            CalcoloImposte con tutti i dettagli
        """
        from datetime import datetime as dt

        # Default anno corrente se non specificato
        if anno is None:
            anno = dt.now().year

        logger.info(f"Calcolo imposte per anno {anno}")

        # 1. Basi dal libro giornale (un solo sistema: quello del bilancio).
        basi = await basi_imponibili_da_giornale(db, int(anno))
        totale_costi = basi["costi"]
        totale_ricavi = basi["ricavi"]
        costi_per_tipo: Dict[str, Any] = basi["costi_per_codice"]
        avvisi: List[str] = []
        if not basi["scritture"]:
            avvisi.append(
                f"Libro giornale {anno} vuoto: nessuna base imponibile, le imposte "
                "a zero non sono un calcolo. Registrare prima il pregresso.")
        elif totale_ricavi <= 0:
            avvisi.append(
                f"Nessun ricavo registrato nel giornale {anno}: corrispettivi da registrare.")

        # Utile civilistico
        utile_civilistico = totale_ricavi - totale_costi

        # 2. Calcola variazioni fiscali
        variazioni_aumento_ires = []
        variazioni_diminuzione_ires = []

        # === VARIAZIONI IN AUMENTO (costi non/parzialmente deducibili) ===

        # Telefonia: 20% non deducibile
        costo_telefonia = costi_per_tipo.get("05.02.07", {}).get("importo", 0)
        if costo_telefonia > 0:
            quota_indeducibile = costo_telefonia * 0.20
            variazioni_aumento_ires.append(VariazioneFiscale(
                descrizione="Telefonia - quota non deducibile (20%)",
                importo=quota_indeducibile,
                tipo="aumento",
                norma_riferimento="Art. 102 TUIR",
                applicabile_irap=True
            ))

        # Auto aziendali (se presenti): 80% non deducibile per uso promiscuo
        costo_carburante = costi_per_tipo.get("05.02.11", {}).get("importo", 0)
        if costo_carburante > 0:
            # Assumiamo uso promiscuo: 80% non deducibile
            quota_indeducibile = costo_carburante * 0.80
            variazioni_aumento_ires.append(VariazioneFiscale(
                descrizione="Carburante auto uso promiscuo - quota non deducibile (80%)",
                importo=quota_indeducibile,
                tipo="aumento",
                norma_riferimento="Art. 164 TUIR",
                applicabile_irap=True
            ))

        # Noleggio auto lungo termine: 80% non deducibile per uso promiscuo
        costo_noleggio_auto = costi_per_tipo.get("05.02.22", {}).get("importo", 0)
        if costo_noleggio_auto > 0:
            # Limite annuo €3.615,20 + 80% non deducibile per uso promiscuo
            quota_indeducibile = costo_noleggio_auto * 0.80
            variazioni_aumento_ires.append(VariazioneFiscale(
                descrizione="Noleggio auto uso promiscuo - quota non deducibile (80%)",
                importo=quota_indeducibile,
                tipo="aumento",
                norma_riferimento="Art. 164 TUIR",
                applicabile_irap=True
            ))

        # IMU non deducibile ai fini IRES (deducibile IRAP)
        costo_imu = costi_per_tipo.get("05.06.05", {}).get("importo", 0)
        if costo_imu > 0:
            variazioni_aumento_ires.append(VariazioneFiscale(
                descrizione="IMU non deducibile IRES",
                importo=costo_imu,
                tipo="aumento",
                norma_riferimento="Art. 14 D.Lgs. 23/2011",
                applicabile_irap=False
            ))

        # IRAP non deducibile ai fini IRES (tranne 10% per costo lavoro)
        costo_irap_precedente = costi_per_tipo.get("05.06.04", {}).get("importo", 0)
        if costo_irap_precedente > 0:
            # Deducibile solo 10%
            quota_indeducibile = costo_irap_precedente * 0.90
            variazioni_aumento_ires.append(VariazioneFiscale(
                descrizione="IRAP non deducibile (90%)",
                importo=quota_indeducibile,
                tipo="aumento",
                norma_riferimento="Art. 99 TUIR",
                applicabile_irap=False
            ))

        # === VARIAZIONI IN DIMINUZIONE (agevolazioni) ===

        # ACE (Aiuto alla Crescita Economica) - semplificato
        # Ipotesi: nessun incremento di capitale proprio

        # Deduzione IRAP dal reddito (10%)
        # Calcolata dopo aver determinato l'IRAP

        # Totali variazioni
        tot_var_aumento_ires = sum(v.importo for v in variazioni_aumento_ires)
        tot_var_diminuzione_ires = sum(v.importo for v in variazioni_diminuzione_ires)

        # 3. Calcola reddito imponibile IRES
        reddito_imponibile_ires = utile_civilistico + tot_var_aumento_ires - tot_var_diminuzione_ires
        reddito_imponibile_ires = max(0, reddito_imponibile_ires)  # Non può essere negativo

        # IRES dovuta
        ires_dovuta = reddito_imponibile_ires * ALIQUOTA_IRES / 100

        # 4. Calcola IRAP
        # Base IRAP = Valore della produzione (per società di capitali)
        # Semplificato: Ricavi - Costi (escludendo costi personale e interessi)

        # Personale (B.9) e oneri finanziari (C.17) per conto CEE: comprendono
        # sia gli alias operativi 05.03.x/05.05.x sia i conti CEE che il
        # motore TFR scrive direttamente (67.01.07.01).
        costo_personale = basi["costo_personale"]
        costo_interessi = basi["costo_interessi"]

        # Valore della produzione = Utile + Costo personale + Interessi
        valore_produzione = utile_civilistico + costo_personale + costo_interessi

        # Applica variazioni IRAP (solo quelle applicabili)
        tot_var_aumento_irap = sum(v.importo for v in variazioni_aumento_ires if v.applicabile_irap)
        tot_var_diminuzione_irap = sum(v.importo for v in variazioni_diminuzione_ires if v.applicabile_irap)

        # Deduzioni IRAP
        deduzioni_irap = DEDUZIONE_IRAP_BASE

        # Conta dipendenti (semplificato: se ci sono costi personale)
        if costo_personale > 0:
            # Stima n. dipendenti da costo medio
            n_dipendenti_stimato = int(costo_personale / 25000)  # €25k costo medio
            deduzioni_irap += n_dipendenti_stimato * DEDUZIONE_IRAP_DIPENDENTI

        # Base imponibile IRAP
        base_imponibile_irap = valore_produzione + tot_var_aumento_irap - tot_var_diminuzione_irap - deduzioni_irap
        base_imponibile_irap = max(0, base_imponibile_irap)

        # IRAP dovuta
        irap_dovuta = base_imponibile_irap * self.aliquota_irap / 100

        # 5. Aggiorna variazioni diminuzione IRES con deduzione IRAP
        if irap_dovuta > 0:
            deduzione_irap_da_ires = irap_dovuta * 0.10  # 10% deducibile
            variazioni_diminuzione_ires.append(VariazioneFiscale(
                descrizione="Deduzione IRAP (10%)",
                importo=deduzione_irap_da_ires,
                tipo="diminuzione",
                norma_riferimento="Art. 99 TUIR",
                applicabile_irap=False
            ))

            # Ricalcola IRES con deduzione
            tot_var_diminuzione_ires = sum(v.importo for v in variazioni_diminuzione_ires)
            reddito_imponibile_ires = utile_civilistico + tot_var_aumento_ires - tot_var_diminuzione_ires
            reddito_imponibile_ires = max(0, reddito_imponibile_ires)
            ires_dovuta = reddito_imponibile_ires * ALIQUOTA_IRES / 100

        # Totale imposte
        totale_imposte = ires_dovuta + irap_dovuta

        # Aliquota effettiva
        aliquota_effettiva = (totale_imposte / utile_civilistico * 100) if utile_civilistico > 0 else 0

        return CalcoloImposte(
            utile_civilistico=round(utile_civilistico, 2),
            variazioni_aumento_ires=variazioni_aumento_ires,
            variazioni_diminuzione_ires=variazioni_diminuzione_ires,
            totale_variazioni_aumento_ires=round(tot_var_aumento_ires, 2),
            totale_variazioni_diminuzione_ires=round(tot_var_diminuzione_ires, 2),
            reddito_imponibile_ires=round(reddito_imponibile_ires, 2),
            ires_dovuta=round(ires_dovuta, 2),
            variazioni_aumento_irap=[v for v in variazioni_aumento_ires if v.applicabile_irap],
            variazioni_diminuzione_irap=[v for v in variazioni_diminuzione_ires if v.applicabile_irap],
            valore_produzione_irap=round(valore_produzione, 2),
            deduzioni_irap=round(deduzioni_irap, 2),
            base_imponibile_irap=round(base_imponibile_irap, 2),
            irap_dovuta=round(irap_dovuta, 2),
            totale_imposte=round(totale_imposte, 2),
            aliquota_effettiva=round(aliquota_effettiva, 2),
            ricavi=totale_ricavi,
            costi=totale_costi,
            avvisi=avvisi,
        )

    def calcola_imposte_da_valori(
        self,
        ricavi: float,
        costi: float,
        costo_personale: float = 0,
        costo_interessi: float = 0,
        costo_telefonia: float = 0,
        costo_carburante: float = 0,
        costo_imu: float = 0,
        n_dipendenti: int = 0
    ) -> CalcoloImposte:
        """
        Calcola le imposte da valori passati direttamente.
        Utile per simulazioni e previsioni.
        """
        utile_civilistico = ricavi - costi

        # Variazioni aumento
        variazioni_aumento_ires = []

        if costo_telefonia > 0:
            variazioni_aumento_ires.append(VariazioneFiscale(
                descrizione="Telefonia - quota non deducibile (20%)",
                importo=costo_telefonia * 0.20,
                tipo="aumento",
                norma_riferimento="Art. 102 TUIR",
                applicabile_irap=True
            ))

        if costo_carburante > 0:
            variazioni_aumento_ires.append(VariazioneFiscale(
                descrizione="Carburante auto uso promiscuo - quota non deducibile (80%)",
                importo=costo_carburante * 0.80,
                tipo="aumento",
                norma_riferimento="Art. 164 TUIR",
                applicabile_irap=True
            ))

        if costo_imu > 0:
            variazioni_aumento_ires.append(VariazioneFiscale(
                descrizione="IMU non deducibile IRES",
                importo=costo_imu,
                tipo="aumento",
                norma_riferimento="Art. 14 D.Lgs. 23/2011",
                applicabile_irap=False
            ))

        tot_var_aumento_ires = sum(v.importo for v in variazioni_aumento_ires)
        variazioni_diminuzione_ires = []

        # IRES
        reddito_imponibile_ires = max(0, utile_civilistico + tot_var_aumento_ires)
        ires_dovuta = reddito_imponibile_ires * ALIQUOTA_IRES / 100

        # IRAP
        valore_produzione = utile_civilistico + costo_personale + costo_interessi
        deduzioni_irap = DEDUZIONE_IRAP_BASE + (n_dipendenti * DEDUZIONE_IRAP_DIPENDENTI)

        tot_var_aumento_irap = sum(v.importo for v in variazioni_aumento_ires if v.applicabile_irap)
        base_imponibile_irap = max(0, valore_produzione + tot_var_aumento_irap - deduzioni_irap)
        irap_dovuta = base_imponibile_irap * self.aliquota_irap / 100

        # Deduzione IRAP
        if irap_dovuta > 0:
            deduzione_irap = irap_dovuta * 0.10
            variazioni_diminuzione_ires.append(VariazioneFiscale(
                descrizione="Deduzione IRAP (10%)",
                importo=deduzione_irap,
                tipo="diminuzione",
                norma_riferimento="Art. 99 TUIR",
                applicabile_irap=False
            ))
            reddito_imponibile_ires = max(0, reddito_imponibile_ires - deduzione_irap)
            ires_dovuta = reddito_imponibile_ires * ALIQUOTA_IRES / 100

        totale_imposte = ires_dovuta + irap_dovuta
        aliquota_effettiva = (totale_imposte / utile_civilistico * 100) if utile_civilistico > 0 else 0

        return CalcoloImposte(
            utile_civilistico=round(utile_civilistico, 2),
            variazioni_aumento_ires=variazioni_aumento_ires,
            variazioni_diminuzione_ires=variazioni_diminuzione_ires,
            totale_variazioni_aumento_ires=round(tot_var_aumento_ires, 2),
            totale_variazioni_diminuzione_ires=round(sum(v.importo for v in variazioni_diminuzione_ires), 2),
            reddito_imponibile_ires=round(reddito_imponibile_ires, 2),
            ires_dovuta=round(ires_dovuta, 2),
            variazioni_aumento_irap=[v for v in variazioni_aumento_ires if v.applicabile_irap],
            variazioni_diminuzione_irap=[],
            valore_produzione_irap=round(valore_produzione, 2),
            deduzioni_irap=round(deduzioni_irap, 2),
            base_imponibile_irap=round(base_imponibile_irap, 2),
            irap_dovuta=round(irap_dovuta, 2),
            totale_imposte=round(totale_imposte, 2),
            aliquota_effettiva=round(aliquota_effettiva, 2)
        )


# Funzioni helper
def get_aliquota_irap(regione: str) -> float:
    """Ottiene l'aliquota IRAP per una regione."""
    return ALIQUOTE_IRAP.get(regione.lower().replace(" ", "_"), ALIQUOTE_IRAP["default"])


def get_limite_deducibilita(tipo: str) -> Any:
    """Ottiene il limite di deducibilità per un tipo di costo."""
    return LIMITI_DEDUCIBILITA.get(tipo)
