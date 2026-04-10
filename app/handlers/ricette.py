"""
Handler Ricette — reagisce a ingrediente.prezzo_cambiato e fattura.importata
Quando cambia il prezzo di un ingrediente, ricalcola automaticamente
il costo di produzione e il margine di tutte le ricette che lo usano.
Crea alert se il margine scende sotto soglia.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SOGLIA_MARGINE_ALERT = 0.20   # alert se margine scende sotto il 20%
VARIAZIONE_MIN = 0.05         # ignora variazioni sotto il 5% (rumore)


def _calcola_costo_ricetta(ricetta: Dict, prezzi: Dict[str, float]) -> float:
    """
    Calcola il costo totale di una ricetta basandosi sui prezzi correnti.
    prezzi: {nome_ingrediente: prezzo_per_unita}
    """
    costo = 0.0
    for ingrediente in ricetta.get("ingredienti", []):
        nome = (ingrediente.get("nome") or
                ingrediente.get("prodotto") or "").lower().strip()
        quantita = float(ingrediente.get("quantita") or
                         ingrediente.get("qty") or 0)
        um = (ingrediente.get("unita_misura") or
              ingrediente.get("um") or "kg").lower()

        # Trova il prezzo per questo ingrediente
        prezzo = 0.0
        for nome_chiave, p in prezzi.items():
            if nome_chiave in nome or nome in nome_chiave:
                prezzo = p
                break

        if prezzo > 0 and quantita > 0:
            # Converti unità se necessario (es. g → kg)
            if um in ("g", "gr", "grammi"):
                quantita /= 1000
            elif um in ("ml", "millilitri"):
                quantita /= 1000
            costo += prezzo * quantita

    return round(costo, 4)


async def handler_aggiorna_costo_ricette(payload: Dict[str, Any], db) -> Dict[str, Any]:
    """
    Quando cambia il prezzo di un ingrediente (da fattura o da aggiornamento manuale):
    1. Trova tutte le ricette che usano quell'ingrediente
    2. Ricalcola costo di produzione
    3. Aggiorna margine
    4. Crea alert se margine < 20%
    """
    if db is None:
        return {"skipped": True, "reason": "db non disponibile"}

    # Estrai informazioni sull'ingrediente dal payload
    # Il payload può venire da fattura.importata (righe) o da ingrediente.prezzo_cambiato
    ingrediente_nome = payload.get("ingrediente_nome") or payload.get("nome") or ""
    nuovo_prezzo     = float(payload.get("nuovo_prezzo") or
                             payload.get("prezzo_unitario") or 0)
    vecchio_prezzo   = float(payload.get("vecchio_prezzo") or 0)

    # Se viene da fattura, estrai ingrediente dalle righe
    righe = payload.get("righe") or payload.get("linee") or []
    ingredienti_aggiornati = []

    if righe and not ingrediente_nome:
        # Processa le righe della fattura per trovare ingredienti noti
        for riga in righe:
            desc = (riga.get("descrizione") or riga.get("description") or "").lower()
            prezzo = float(riga.get("prezzo_unitario") or riga.get("unit_price") or 0)
            if prezzo > 0 and desc:
                ingredienti_aggiornati.append({"nome": desc, "prezzo": prezzo})
    elif ingrediente_nome and nuovo_prezzo > 0:
        ingredienti_aggiornati = [{"nome": ingrediente_nome.lower(), "prezzo": nuovo_prezzo}]

    if not ingredienti_aggiornati:
        return {"skipped": True, "reason": "nessun ingrediente con prezzo"}

    # Carica tutte le ricette
    ricette = await db["ricette"].find({}, {"_id": 0}).to_list(500)
    if not ricette:
        return {"skipped": True, "reason": "nessuna ricetta nel DB"}

    # Costruisci mappa prezzi correnti per tutti gli ingredienti noti
    prezzi_correnti: Dict[str, float] = {}
    for ing in ingredienti_aggiornati:
        prezzi_correnti[ing["nome"]] = ing["prezzo"]

    # Integra con prezzi già salvati nel DB (price_history)
    try:
        history = await db["price_history"].find(
            {}, {"_id": 0, "nome": 1, "prezzo_medio": 1}
        ).to_list(1000)
        for h in history:
            nome = (h.get("nome") or "").lower()
            if nome and nome not in prezzi_correnti:
                prezzi_correnti[nome] = float(h.get("prezzo_medio") or 0)
    except Exception:
        pass

    ricette_aggiornate = 0
    alert_margine      = 0
    aggiornate_lista   = []

    for ricetta in ricette:
        ricetta_id   = ricetta.get("id") or ""
        nome_ricetta = ricetta.get("nome") or ""
        ingredienti  = ricetta.get("ingredienti") or []

        if not ingredienti or not ricetta_id:
            continue

        # Verifica se questa ricetta usa uno degli ingredienti aggiornati
        usa_ingrediente = False
        for ing in ingredienti_aggiornati:
            for componente in ingredienti:
                nome_comp = (componente.get("nome") or
                             componente.get("prodotto") or "").lower()
                if ing["nome"][:6] in nome_comp or nome_comp[:6] in ing["nome"]:
                    usa_ingrediente = True
                    break
            if usa_ingrediente:
                break

        if not usa_ingrediente:
            continue

        # Ricalcola costo
        nuovo_costo = _calcola_costo_ricetta(ricetta, prezzi_correnti)
        if nuovo_costo <= 0:
            continue

        vecchio_costo = float(ricetta.get("costo_produzione") or 0)
        prezzo_vendita = float(ricetta.get("prezzo_vendita") or
                               ricetta.get("prezzo") or 0)

        # Calcola margine
        if prezzo_vendita > 0:
            margine = (prezzo_vendita - nuovo_costo) / prezzo_vendita
        else:
            margine = None

        # Aggiorna ricetta
        update_fields = {
            "costo_produzione": nuovo_costo,
            "costo_aggiornato_at": datetime.now(timezone.utc).isoformat(),
        }
        if margine is not None:
            update_fields["margine"] = round(margine, 4)
            update_fields["margine_percentuale"] = round(margine * 100, 2)

        await db["ricette"].update_one(
            {"id": ricetta_id},
            {"$set": update_fields}
        )
        ricette_aggiornate += 1
        aggiornate_lista.append(nome_ricetta)

        # Alert se margine sotto soglia
        if margine is not None and margine < SOGLIA_MARGINE_ALERT:
            # Anti-duplicato alert: non creare se già esiste uno recente
            alert_esistente = await db["agenti_segnalazioni"].find_one({
                "agente": "HandlerRicette",
                "dati.ricetta_id": ricetta_id,
                "risolta": {"$ne": True},
            })
            if not alert_esistente:
                await db["agenti_segnalazioni"].insert_one({
                    "id": str(uuid.uuid4()),
                    "agente": "HandlerRicette",
                    "tipo": "avviso",
                    "titolo": (f"Margine basso: {nome_ricetta} "
                               f"({round(margine*100,1)}%)"),
                    "descrizione": (
                        f"Dopo l'aggiornamento prezzi, la ricetta '{nome_ricetta}' "
                        f"ha un margine del {round(margine*100,1)}% "
                        f"(costo produzione: €{nuovo_costo:.3f}, "
                        f"prezzo vendita: €{prezzo_vendita:.2f}). "
                        f"Soglia di allerta: {int(SOGLIA_MARGINE_ALERT*100)}%."
                    ),
                    "azione": "Magazzino → Ricette → rivedi prezzo o ingredienti",
                    "letta": False,
                    "risolta": False,
                    "dati": {
                        "ricetta_id":    ricetta_id,
                        "ricetta_nome":  nome_ricetta,
                        "margine":       round(margine, 4),
                        "costo":         nuovo_costo,
                        "prezzo_vendita": prezzo_vendita,
                    },
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })
                alert_margine += 1

        # Aggiorna price_history per questo ingrediente
        for ing in ingredienti_aggiornati:
            try:
                await db["price_history"].update_one(
                    {"nome": ing["nome"]},
                    {"$set": {
                        "nome":          ing["nome"],
                        "prezzo_attuale": ing["prezzo"],
                        "updated_at":    datetime.now(timezone.utc).isoformat(),
                    },
                     "$push": {"storico": {
                         "data":   datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                         "prezzo": ing["prezzo"],
                     }}},
                    upsert=True
                )
            except Exception:
                pass

    logger.info(
        f"[HandlerRicette] {ricette_aggiornate} ricette aggiornate | "
        f"{alert_margine} alert margine"
    )

    return {
        "ricette_aggiornate": ricette_aggiornate,
        "alert_margine":      alert_margine,
        "ricette_lista":      aggiornate_lista[:10],
    }
