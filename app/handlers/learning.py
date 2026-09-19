"""
Handler Learning — reagisce a fattura.importata
Classifica la fattura per centro di costo e calcola deducibilità/detraibilità.
"""
import logging
from collections import defaultdict
from typing import Any, Dict

logger = logging.getLogger(__name__)


async def handler_classifica_cdc(payload: Dict[str, Any], db) -> Dict[str, Any]:
    """
    Chiama la Learning Machine per classificare la fattura per centro di costo.
    Aggiorna la fattura con: centro_costo_id, imponibile_deducibile_ires, iva_detraibile.
    """
    if db is None:
        return {"skipped": True, "reason": "db non disponibile"}

    fattura_id = payload.get("fattura_id") or payload.get("id")
    if not fattura_id:
        return {"skipped": True, "reason": "fattura_id mancante"}

    try:
        from app.services.learning_machine_cdc import (
            carica_configurazioni_learning,
            classifica_fattura_con_learning,
            calcola_importi_fiscali,
            somma_gia_dedotto_periodo_anno,
        )

        # Il payload reale pubblicato da fatture_upload.py usa campi piatti
        # (fornitore_ragione_sociale, righe_linee) non un oggetto "fornitore"
        # annidato — supportiamo entrambe le forme per compatibilità.
        fornitore_nome = (payload.get("fornitore") or {}).get("ragione_sociale") \
            or payload.get("fornitore_ragione_sociale", "")
        descrizione    = payload.get("descrizione", "")
        righe          = payload.get("righe") or payload.get("righe_linee") or payload.get("linee", [])
        imponibile     = float(payload.get("imponibile") or 0)
        iva            = float(payload.get("iva") or 0)

        # MOTORE UNICO col learning: consulta PRIMA le configurazioni
        # dell'utente (fornitori_keywords), poi la tabella statica. Prima
        # le fatture nuove ignoravano ciò che l'utente aveva insegnato.
        configurazioni = await carica_configurazioni_learning(db)
        cdc_id, cdc_config, confidence, fonte = await classifica_fattura_con_learning(
            db, fornitore_nome, descrizione, righe,
            configurazioni=configurazioni,
        )

        importi = calcola_importi_fiscali(imponibile, iva, cdc_config)

        # Tetto annuo cumulativo per centri con `limite_annuo` (audit
        # 19/09/2026, punto 4: noleggio auto, 3.615,20 €/anno PER CONTRATTO,
        # non per singola fattura). Interroga il db solo quando serve: e' un
        # caso raro rispetto al volume totale di fatture classificate.
        numero_contratto_noleggio = None
        if cdc_config.get("limite_annuo"):
            from app.services.noleggio.parsers import estrai_numero_contratto

            fattura_completa = await db["invoices"].find_one(
                {"id": fattura_id},
                {"_id": 0, "linee": 1, "dati_contratto": 1, "supplier_vat": 1,
                 "invoice_date": 1, "data_fattura": 1},
            ) or {}
            numero_contratto_noleggio = estrai_numero_contratto(fattura_completa)
            fornitore_piva = fattura_completa.get("supplier_vat") or payload.get("fornitore_piva")
            data_riferimento = (
                fattura_completa.get("invoice_date") or fattura_completa.get("data_fattura")
                or payload.get("data_documento") or ""
            )
            try:
                anno_riferimento = int(str(data_riferimento)[:4])
            except (TypeError, ValueError):
                anno_riferimento = None

            gia_dedotto_anno = await somma_gia_dedotto_periodo_anno(
                db, cdc_id=cdc_id, anno=anno_riferimento,
                numero_contratto=numero_contratto_noleggio, fornitore_piva=fornitore_piva,
                escludi_fattura_id=fattura_id,
            )
            importi = calcola_importi_fiscali(
                imponibile, iva, cdc_config, imponibile_gia_dedotto_anno=gia_dedotto_anno,
            )

        # La classificazione di testata resta per compatibilita' con bilanci e
        # filtri storici, ma la fonte contabile analitica e' per singola riga:
        # lo stesso fornitore puo' vendere bevande, detergenti e manutenzione
        # nella medesima fattura.
        classificazioni_righe = []
        ripartizione = defaultdict(lambda: {
            "imponibile": 0.0, "iva": 0.0, "totale": 0.0, "righe": 0,
        })
        righe_da_verificare = 0

        def _numero(value: Any) -> float:
            try:
                return float(str(value or "0").replace(",", "."))
            except (TypeError, ValueError):
                return 0.0

        for posizione, riga in enumerate(righe):
            if not isinstance(riga, dict):
                continue
            riga_cdc, riga_config, riga_conf, riga_fonte = await classifica_fattura_con_learning(
                db, fornitore_nome, "", [riga],
                configurazioni=configurazioni,
            )
            imponibile_riga = round(_numero(
                riga.get("prezzo_totale") or riga.get("importo") or riga.get("totale")
            ), 2)
            aliquota = _numero(riga.get("aliquota_iva"))
            iva_riga = round(imponibile_riga * aliquota / 100, 2) if aliquota else 0.0
            totale_riga = round(imponibile_riga + iva_riga, 2)
            richiede_verifica = riga_cdc == "99_ALTRI_COSTI" or riga_conf < 0.6
            if richiede_verifica:
                righe_da_verificare += 1

            classificazioni_righe.append({
                "posizione": posizione,
                "numero_linea": riga.get("numero_linea") or str(posizione + 1),
                "descrizione": riga.get("descrizione", ""),
                "centro_costo_id": riga_cdc,
                "centro_costo_nome": riga_config.get("nome", ""),
                "confidence": round(float(riga_conf), 4),
                "fonte": riga_fonte,
                "imponibile": imponibile_riga,
                "iva": iva_riga,
                "totale": totale_riga,
                "richiede_verifica": richiede_verifica,
            })
            quota = ripartizione[riga_cdc]
            quota["centro_costo_id"] = riga_cdc
            quota["centro_costo_nome"] = riga_config.get("nome", "")
            quota["imponibile"] += imponibile_riga
            quota["iva"] += iva_riga
            quota["totale"] += totale_riga
            quota["righe"] += 1

        centri_ripartiti = []
        for quota in ripartizione.values():
            for campo in ("imponibile", "iva", "totale"):
                quota[campo] = round(quota[campo], 2)
            centri_ripartiti.append(dict(quota))
        centri_ripartiti.sort(key=lambda quota: (-abs(quota["imponibile"]), quota["centro_costo_id"]))
        imponibile_classificato = round(sum(q["imponibile"] for q in centri_ripartiti), 2)
        differenza_imponibile = round(imponibile - imponibile_classificato, 2)

        update = {
            "centro_costo_id":               cdc_id,
            "centro_costo_nome":             cdc_config.get("nome", ""),
            "classificazione_confidence":    confidence,
            "classificazione_fonte":         fonte,
            "imponibile_deducibile_ires":    importi.get("imponibile_deducibile_ires", 0),
            "imponibile_indeducibile_ires":  importi.get("imponibile_indeducibile_ires", 0),
            "iva_detraibile":                importi.get("iva_detraibile", 0),
            "iva_indetraibile":              importi.get("iva_indetraibile", 0),
            "classificato_da":               "learning_machine",
            "classificazioni_righe":         classificazioni_righe,
            "centri_costo_ripartizione":     centri_ripartiti,
            "classificazione_mista":         len(centri_ripartiti) > 1,
            "righe_da_verificare":           righe_da_verificare,
            "imponibile_non_allocato":       differenza_imponibile,
            "stato_classificazione": (
                "da_verificare"
                if righe_da_verificare or abs(differenza_imponibile) > 0.05
                else "classificata"
            ),
        }
        if cdc_config.get("limite_annuo"):
            # Persistiti per il cumulo annuo delle PROSSIME fatture dello
            # stesso contratto (somma_gia_dedotto_periodo_anno le rilegge).
            update["numero_contratto_noleggio"] = numero_contratto_noleggio
            update["imponibile_limitato_periodo"] = importi.get("imponibile_limitato_periodo")

        await db["invoices"].update_one({"id": fattura_id}, {"$set": update})

        logger.info(f"[HandlerLearning] Fattura {fattura_id} → CDC: {cdc_config.get('nome')} (conf={confidence:.2f})")
        return {
            "centro_costo": cdc_config.get("nome"),
            "confidence": confidence,
            "classificazione_mista": len(centri_ripartiti) > 1,
            "righe_classificate": len(classificazioni_righe),
            "righe_da_verificare": righe_da_verificare,
        }

    except Exception as e:
        logger.warning(f"[HandlerLearning] Classificazione fallita per {fattura_id}: {e}")
        return {"error": str(e)}
