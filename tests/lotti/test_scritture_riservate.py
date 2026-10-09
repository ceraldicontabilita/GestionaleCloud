"""Ogni rotta di scrittura di Lotti ha una decisione esplicita su chi la usa.

Il gate globale (``auth_dependency``) chiede solo un token valido: un
dipendente passa. Fino al 26/09/2026 223 scritture su 349 erano aperte a
chiunque avesse un PIN, comprese cancellazioni, prezzi, approvazione dei
fornitori, backfill e «dichiara tutto conforme».

Regola: una rotta POST/PUT/PATCH/DELETE o dipende da ``require_admin``
(o ``require_automation_or_admin``, o ``require_permesso`` per i ruoli HACCP e
caporeparto di ``servizi/ruoli.py``), oppure è elencata qui sotto fra le
**operazioni di reparto** (registrare un fatto HACCP, un lotto, un prelievo,
una vendita). Una rotta nuova che non sta in nessuna delle due fa fallire la
CI: chi la scrive deve decidere.
"""
import ast
from pathlib import Path

RADICE = Path(__file__).resolve().parents[2] / "app" / "lotti" / "routers"
GUARDIE = ("require_admin", "require_automation_or_admin", "require_permesso")

OPERAZIONI_DI_REPARTO = {
    "acquaviva:senza_glutine_al_banco",
    "anomalie:registra_anomalia",
    "anomalie:sposta_lotti_massivo",
    "colazione:registra_colazione",
    "colazione:scegli_fonte",
    "controllo_olio:registra_controllo_olio",
    "controllo_olio:aggiorna_controllo_olio",
    "disinfestazione:registra_intervento",
    "disinfestazione:registra_monitoraggio",
    "farciture:dividi_e_manda_al_banco",
    "food_cost:suggerisci_ingredienti",
    "food_cost:dose_produzione",
    # Calcoli di lievito e impasto: non scrivono nulla (27/09/2026).
    "food_cost:lievito_per_produzione",
    "food_cost:calcolatore_impasto",
    "food_cost:calcolatore_mix_farine",
    "food_cost:calcolatore_temperatura_acqua",
    "food_cost:leggi_ingredienti_foto",
    "food_cost:auto_rileva_allergeni_singola",
    "food_cost:usa_ricetta",
    "food_cost:calcola_nutrizionale_ricetta",
    "fornitori_schede:salva_nota_ricevimento",
    "gelati:aggiungi_invenduto",
    "gelati:set_esito_invenduto",
    "gelati:recupera_invenduto",
    "gelati:aggiungi_produzione",
    "listino:genera_pdf",
    "lotti:registra_abbattimento_pesce",
    "lotti:registra_ricevimento_pesce",
    "lotti:concludi_abbattimento",
    "lotti:create_lotto",
    "lotti_produzione:marca_lotto_consumato",
    "lotti_produzione:manda_lotto_al_banco",
    "lotti_produzione:sposta_posizione_lotto",
    "lotti_produzione:congela_lotto",
    "lotti_produzione:recupera_lotto",
    "lotti_produzione:registra_produzione_e_crea_lotto",
    "lotti_produzione:genera_lotto_da_ricetta",
    "magazzino_bar:carico",
    "magazzino_bar:crea_richiesta",
    "magazzino_bar:evadi_richiesta",
    "magazzino_bar:annulla_richiesta",
    "magazzino_bar:scarico",
    "magazzino_bar:rettifica_inventario",
    "magazzino_bar:salva_linea",
    "magazzino_bar:riordina_sotto_soglia",
    "magazzino_unificato:scarico_unificato",
    "ordini_fornitori:crea_ordine",
    "ordini_fornitori:aggiungi_richiesta_acquisto",
    "ordini_fornitori:rimuovi_richiesta_acquisto",
    "ordini_fornitori:segna_ricetta_prodotta",
    "produzione_consigliata:registra_decisione",
    "reclami_fornitori:crea_reclamo",
    "reclami_fornitori:aggiorna_stato_reclamo",
    "ricette:aggiorna_foto",
    "ricette:upload_foto",
    "ricezione_merce:registra_ricezione",
    "ricezione_merce:aggiorna_ricezione",
    "saima_ricettari:verifica_disponibilita_ricetta",
    "sanificazione:registra_sanificazione",
    "sanificazione:registra_giorno_completo",
    "sanificazione:registra_sanificazione_apparecchio",
    "schede_tecniche:salva_scheda",
    "schede_tecniche:parse_etichetta",
    "schede_tecniche:leggi_foto_ai",
    "shelf_life:calcola_shelf_life",
    "stampanti:accoda_stampa",
    "stampanti:coda_esito",
    "supervisor_operativo:segna_alert_prezzo_letto",
    "tablet_operatori:login_pin",
    "task_dipendenti:usa_oggi_lotto",
    "task_dipendenti:completa_task",
    "temperature_cottura:registra_temperatura_cottura",
    "temperature_cottura:aggiorna_temperatura_cottura",
    "temperature_negative:registra_temperatura",
    "temperature_positive:registra_temperatura",
    "vendita_banco:registra_vendita_banco_route",
    "vendita_banco:registra_invenduto",
    "vendita_banco:riapri_vendita",
}


def _rotte_di_scrittura():
    for file in sorted(RADICE.glob("*.py")):
        albero = ast.parse(file.read_text(encoding="utf-8"))
        for nodo in albero.body:
            if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in nodo.decorator_list:
                if (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)
                        and dec.func.attr in ("post", "put", "patch", "delete")):
                    firma = ast.unparse(nodo.args) + ast.unparse(dec)
                    yield f"{file.stem}:{nodo.name}", any(g in firma for g in GUARDIE)


def test_ogni_scrittura_ha_una_decisione():
    senza_decisione = sorted(
        nome for nome, protetta in _rotte_di_scrittura()
        if not protetta and nome not in OPERAZIONI_DI_REPARTO
    )
    assert not senza_decisione, (
        "Rotte di scrittura aperte a ogni dipendente senza decisione: aggiungi "
        "Depends(require_admin) oppure elencale fra le operazioni di reparto: "
        + ", ".join(senza_decisione)
    )


def test_elenco_operazioni_non_ha_voci_morte():
    presenti = {nome for nome, protetta in _rotte_di_scrittura() if not protetta}
    morte = sorted(OPERAZIONI_DI_REPARTO - presenti)
    assert not morte, "Voci da togliere (rotta sparita o ora riservata): " + ", ".join(morte)


def test_scritture_delicate_riservate():
    protette = {nome for nome, p in _rotte_di_scrittura() if p}
    for nome in (
        "haccp_auto:dichiara_conformi_oggi", "fornitori_qualifica:approva_batch_qualifica",
        "pipeline:trigger_pipeline", "prodotti_vendita:sync_prodotti_acquaviva",
        "acquaviva:set_prezzi_prodotto", "saima_ricettari:aggiungi_ricettario",
        "saima_ricettari:elimina_ricettario", "schede_tecniche:scrape_scheda",
        "ricette:set_prezzo_vendita", "chiusure:segna_giorno_non_produttivo",
        "temperature_positive:aggiungi_operatore", "vendita_banco:elimina_vendita",
    ):
        assert nome in protette, nome
