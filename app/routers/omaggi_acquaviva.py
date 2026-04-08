"""
Router Omaggi Acquaviva — /api/omaggi-acquaviva
================================================
Calcola gli omaggi ricevuti da Acquaviva per ogni ordine (fattura).

Regola:
- 1 omaggio ogni 10 cartoni acquistati (cumulativo tra ordini)
- I cartoni si accumulano: se un ordine ha 7 cart → 0 omaggi, mancano 3
- Ordine successivo con 5 cart → totale cumulativo 12 → 1 omaggio maturato,
  avanzano 2 cartoni per il prossimo ciclo
- Il valore di ogni omaggio = pezzi_per_cartone × prezzo_vendita del prodotto
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import Optional
import re
from datetime import datetime

from app.database import get_database

router = APIRouter()

# ─── SOGLIA OMAGGI ────────────────────────────────────────────────────────────
SOGLIA_OMAGGI = 10  # 1 omaggio ogni N cartoni

# ─── HELPER: estrai pezzi per cartone dalla descrizione fattura ───────────────
def _pezzi_da_descrizione(desc: str) -> Optional[int]:
    """
    Cerca pattern '35G 4.95KG' o '80G 5.8KG' → calcola pezzi/cartone.
    Oppure cerca pattern espliciti come '6X80G' → 6 pezzi.
    """
    desc_up = desc.upper()

    # Pattern "NxPesoG" es. "6X80G", "12X35G"
    m = re.search(r'(\d+)\s*[Xx×]\s*(\d+(?:[.,]\d+)?)\s*G', desc_up)
    if m:
        return int(m.group(1))

    # Pattern "PesoG PesoKG" → pezzi = kg*1000/g
    m = re.search(r'(\d+(?:[.,]\d+)?)\s*G\b.{1,20}?(\d+(?:[.,]\d+)?)\s*KG', desc_up)
    if m:
        try:
            g = float(m.group(1).replace(',', '.'))
            kg = float(m.group(2).replace(',', '.'))
            if g > 0 and 0.5 < kg < 50:
                return round(kg * 1000 / g)
        except Exception:
            pass

    return None


def _match_fornitore(denominazione: str, filtro: str) -> bool:
    """Verifica se la denominazione del cedente contiene il filtro (case-insensitive)."""
    return filtro.lower() in (denominazione or '').lower()


# ─── ENDPOINT PRINCIPALE ──────────────────────────────────────────────────────
@router.get("/api/omaggi-acquaviva")
async def get_omaggi_acquaviva(
    fornitore: str = Query("acquaviva", description="Filtro parziale sul nome fornitore"),
    soglia: int = Query(SOGLIA_OMAGGI, description="Cartoni per ogni omaggio"),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Analizza tutte le fatture del fornitore (default: Acquaviva) e calcola:
    - Cartoni acquistati per ordine (righe a prezzo > 0)
    - Omaggi ricevuti per ordine (righe a prezzo = 0)
    - Valore omaggi = pezzi_per_cartone × prezzo_vendita (da fattura righe normali)
    - Progressivo cumulativo: cartoni accumulati, omaggi maturati, cartoni mancanti
    """
    # 1. Carica tutte le fatture del fornitore ordinate per data ASC
    fatture = await db["fatture_passive"].find(
        {"fornitore_denominazione": {"$regex": fornitore, "$options": "i"}},
        {"_id": 0, "fornitore_denominazione": 1, "numero": 1, "data": 1, "linee": 1}
    ).sort("data", 1).to_list(500)

    if not fatture:
        return {
            "fornitore_cercato": fornitore,
            "soglia_omaggi": soglia,
            "ordini": [],
            "totale_cartoni_acquistati": 0,
            "totale_omaggi_maturati": 0,
            "totale_omaggi_ricevuti": 0,
            "cartoni_residui": 0,
            "valore_totale_omaggi": 0.0,
            "messaggio": "Nessuna fattura trovata per questo fornitore"
        }

    totale_cartoni_accumulati = 0   # cumulativo running
    omaggi_maturati_totali = 0      # omaggi già erogati (usati per calcolo residui)
    ordini = []

    for fat in fatture:
        linee = fat.get("linee") or []
        numero = fat.get("numero") or fat.get("numero", "?")
        data = fat.get("data") or fat.get("data", "?")
        cedente = fat.get("fornitore_denominazione", fornitore)

        # Separa righe prodotti normali (prezzo > 0) da omaggi (prezzo = 0)
        righe_normali = []
        righe_omaggi = []

        for linea in linee:
            pu = float(linea.get("prezzo_unitario") or 0)
            qty = float(linea.get("quantita") or 0)
            if qty <= 0:
                continue
            if pu <= 0:
                righe_omaggi.append(linea)
            else:
                righe_normali.append(linea)

        # Cartoni acquistati in questo ordine
        cartoni_ordine = sum(float(r.get("quantita") or 0) for r in righe_normali)

        # Prezzi di vendita delle righe normali → mappa descrizione_upper → prezzo_unitario
        prezzi_map: dict[str, float] = {}
        pezzi_map: dict[str, Optional[int]] = {}
        for r in righe_normali:
            desc = (r.get("descrizione") or "").strip().upper()
            if desc:
                prezzi_map[desc] = float(r.get("prezzo_unitario") or 0)
                pezzi_map[desc] = _pezzi_da_descrizione(r.get("descrizione") or "")

        # Analizza omaggi ricevuti in questo ordine
        dettaglio_omaggi = []
        valore_omaggi_ordine = 0.0

        for r in righe_omaggi:
            desc = (r.get("descrizione") or "").strip()
            qty_omaggio = float(r.get("quantita") or 0)
            desc_up = desc.upper()

            # Cerca prezzo di riferimento: prima match esatto, poi fuzzy per prime 2 parole
            prezzo_rif = prezzi_map.get(desc_up, 0.0)
            pezzi_cart = pezzi_map.get(desc_up)

            if prezzo_rif == 0:
                # Fuzzy: prime 2 parole
                parole = desc_up.split()[:2]
                for k, v in prezzi_map.items():
                    if all(p in k for p in parole):
                        prezzo_rif = v
                        pezzi_cart = pezzi_map.get(k)
                        break

            # Calcolo pezzi totali omaggio
            pezzi_omaggio = int(qty_omaggio * pezzi_cart) if pezzi_cart else None

            # Valore: pezzi × prezzo_unitario (= prezzo al pezzo dalla riga normale)
            # prezzo_unitario in fattura è per CARTONE, quindi divido per pezzi/cartone
            prezzo_pezzo = (prezzo_rif / pezzi_cart) if (pezzi_cart and prezzo_rif > 0) else 0.0
            valore = round((pezzi_omaggio or qty_omaggio) * prezzo_pezzo, 2)
            valore_omaggi_ordine += valore

            dettaglio_omaggi.append({
                "descrizione": desc,
                "cartoni_omaggio": qty_omaggio,
                "pezzi_cartone": pezzi_cart,
                "pezzi_totali": pezzi_omaggio,
                "prezzo_unitario_cartone_rif": round(prezzo_rif, 4),
                "prezzo_pezzo_rif": round(prezzo_pezzo, 4),
                "valore_stimato": valore,
            })

        # Calcolo progressivo cumulativo
        cartoni_prima = totale_cartoni_accumulati
        totale_cartoni_accumulati += cartoni_ordine

        # Omaggi maturati FINO A QUESTO ORDINE (cumulativo)
        omaggi_maturati_fino_ora = int(totale_cartoni_accumulati // soglia)
        omaggi_nuovi_questo_ordine = omaggi_maturati_fino_ora - omaggi_maturati_totali
        omaggi_maturati_totali = omaggi_maturati_fino_ora

        cartoni_nel_ciclo = totale_cartoni_accumulati % soglia  # residui nel ciclo corrente
        cartoni_mancanti = soglia - cartoni_nel_ciclo if cartoni_nel_ciclo > 0 else 0

        ordini.append({
            "numero_fattura": numero,
            "data": data,
            "cedente": cedente,
            # Acquisti
            "cartoni_acquistati": cartoni_ordine,
            "righe_acquisto": len(righe_normali),
            "dettaglio_acquisto": [
                {
                    "descrizione": r.get("descrizione", ""),
                    "quantita": float(r.get("quantita") or 0),
                    "prezzo_unitario": float(r.get("prezzo_unitario") or 0),
                    "pezzi_cartone": _pezzi_da_descrizione(r.get("descrizione") or ""),
                }
                for r in righe_normali
            ],
            # Omaggi ricevuti
            "omaggi_ricevuti": len(righe_omaggi),
            "dettaglio_omaggi": dettaglio_omaggi,
            "valore_omaggi_stimato": round(valore_omaggi_ordine, 2),
            # Progressivo cumulativo
            "progressivo": {
                "cartoni_accumulati_prima": cartoni_prima,
                "cartoni_accumulati_dopo": totale_cartoni_accumulati,
                "omaggi_maturati_nuovi": omaggi_nuovi_questo_ordine,
                "omaggi_maturati_totali": omaggi_maturati_fino_ora,
                "cartoni_nel_ciclo_corrente": cartoni_nel_ciclo,
                "cartoni_mancanti_prossimo_omaggio": cartoni_mancanti,
            }
        })

    # Totale finale
    cartoni_ciclo_finale = totale_cartoni_accumulati % soglia
    mancanti_finale = (soglia - cartoni_ciclo_finale) if cartoni_ciclo_finale > 0 else 0
    valore_totale = sum(o["valore_omaggi_stimato"] for o in ordini)
    omaggi_ricevuti_totali = sum(o["omaggi_ricevuti"] for o in ordini)

    return {
        "fornitore_cercato": fornitore,
        "soglia_omaggi": soglia,
        "totale_ordini": len(ordini),
        "totale_cartoni_acquistati": totale_cartoni_accumulati,
        "totale_omaggi_maturati": omaggi_maturati_totali,
        "totale_omaggi_ricevuti": omaggi_ricevuti_totali,
        "cartoni_nel_ciclo_corrente": cartoni_ciclo_finale,
        "cartoni_mancanti_prossimo_omaggio": mancanti_finale,
        "valore_totale_omaggi": round(valore_totale, 2),
        "ordini": ordini,
    }
