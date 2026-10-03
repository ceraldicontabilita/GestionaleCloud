"""Regole inderogabili per i pagamenti ai dipendenti.

Dal 1 luglio 2018 i pagamenti della retribuzione non possono essere trattati
come contanti durante un rapporto in corso.  L'unica eccezione operativa
ammessa dal titolare e' un pagamento eseguito dopo la cessazione: per questo
la data di fine rapporto deve essere presente e resta copiata sulla prova.

Le funzioni pure di questo modulo sono usate sia dagli endpoint di scrittura
sia dalle viste e dalla bonifica storica: una riga vecchia non puo' continuare
ad alterare il saldo soltanto perche' e' stata salvata prima della regola.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.hr.services import stato_rapporto


DATA_DIVIETO_CONTANTI = "2018-07-01"
MOTIVO_CONTANTI_NON_AMMESSO = "contanti_post_2018_senza_cessazione_compatibile"


def _data_iso(valore: Any) -> Optional[str]:
    return stato_rapporto.data_iso(valore)


def data_cessazione(dipendente: Dict[str, Any]) -> Optional[str]:
    """Data canonica conservata nell'anagrafica, anche per i lettori storici."""
    return stato_rapporto.data_fine_rapporto(dipendente or {})


def valuta_contanti(dipendente: Dict[str, Any], data_pagamento: Any) -> Tuple[bool, str, Optional[str]]:
    """Ritorna ``(ammesso, motivo, data_cessazione)``.

    Prima del 01/07/2018 la regola non si applica. Da quella data servono sia
    uno stato cessato sia una data di cessazione certa e il pagamento non puo'
    precedere la cessazione.
    """
    data = _data_iso(data_pagamento)
    if not data:
        return False, "data_pagamento_mancante", data_cessazione(dipendente)
    if data < DATA_DIVIETO_CONTANTI:
        return True, "ante_2018_07_01", data_cessazione(dipendente)
    fine = data_cessazione(dipendente)
    if stato_rapporto.e_in_forza(dipendente or {}):
        return False, "rapporto_in_corso", fine
    if not fine:
        return False, "cessazione_senza_data", None
    if data < fine:
        return False, "pagamento_anteriore_alla_cessazione", fine
    return True, "pagamento_post_cessazione", fine


def filtra_acconti_contanti(
    dipendente: Dict[str, Any], acconti: Iterable[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Separa gli acconti contanti validi da quelli che non devono fare saldo."""
    validi: List[Dict[str, Any]] = []
    scartati: List[Dict[str, Any]] = []
    for originale in acconti or []:
        acconto = dict(originale or {})
        ammesso, motivo, fine = valuta_contanti(dipendente, acconto.get("data"))
        if ammesso:
            if fine:
                acconto["data_cessazione_rapporto"] = fine
            validi.append(acconto)
        else:
            scartati.append({**acconto, "motivo": MOTIVO_CONTANTI_NON_AMMESSO,
                             "dettaglio_motivo": motivo,
                             "data_cessazione_rapporto": fine})
    return validi, scartati


def chiave_acconto(acconto: Dict[str, Any]) -> Tuple[str, str]:
    return str(acconto.get("data") or ""), str(acconto.get("importo") or "")


async def bonifica_storico(db, *, dry_run: bool = True, force: bool = False) -> Dict[str, Any]:
    """Corregge lo storico in modo idempotente e reversibile.

    * gli acconti in contanti non ammessi escono dal saldo ma restano in
      ``acconti_scartati_regola_2018``;
    * documenti/righe banca che citano un solo dipendente diventano prove
      certe; il mese e' automatico-certo soltanto se lo sono tutti i suoi
      pagamenti, senza alterare una conferma manuale.
    """
    migrazione = "hr-pagamenti-contanti-cessazione-e-riferimento-certo-v1"
    stato = await db.sistema_stato.find_one({"key": migrazione}, {"_id": 0})
    if stato and stato.get("completato") and not dry_run and not force:
        return {"dry_run": False, "gia_completato": True, "migrazione": migrazione,
                "completato_il": stato.get("completato_il")}

    dipendenti = await db.dipendenti.find(
        {"merged_into": {"$exists": False}}, {"_id": 0}).to_list(5000)
    dip_map = {d.get("id"): d for d in dipendenti if d.get("id")}

    from app.hr.routers.dipendenti_cloud import indici_da_dipendenti
    from app.services.hr_pagamenti_deposito import (
        ORIGINE_BANCA, ORIGINE_PDF, e_pagamento_non_stipendio, risolvi_dipendente,
    )

    indici = indici_da_dipendenti(dipendenti)
    ora = datetime.now(timezone.utc).isoformat()
    report: Dict[str, Any] = {
        "dry_run": dry_run, "migrazione": migrazione,
        "paghe_esaminate": 0, "mesi_con_contanti_corretti": 0,
        "movimenti_contanti_scartati": 0, "prove_esaminate": 0,
        "prove_promosse_certe": 0, "periodi_promossi_certi": 0,
        "dettaglio_contanti": [], "dettaglio_prove": [],
    }
    periodi_contanti = set()

    paghe = await db.paghe_mensili.find({}, {"_id": 0}).to_list(10000)
    for paga in paghe:
        report["paghe_esaminate"] += 1
        acconti = list(paga.get("acconti") or [])
        if not acconti:
            continue
        validi, scartati = filtra_acconti_contanti(
            dip_map.get(paga.get("dipendente_id"), {}), acconti)
        if not scartati:
            continue
        report["mesi_con_contanti_corretti"] += 1
        report["movimenti_contanti_scartati"] += len(scartati)
        periodo = (paga.get("dipendente_id"), int(paga.get("anno") or 0), int(paga.get("mese") or 0))
        periodi_contanti.add(periodo)
        if len(report["dettaglio_contanti"]) < 100:
            report["dettaglio_contanti"].append({
                "dipendente_id": periodo[0], "anno": periodo[1], "mese": periodo[2],
                "scartati": scartati,
            })
        if dry_run:
            continue
        precedenti = list(paga.get("acconti_scartati_regola_2018") or [])
        gia = {chiave_acconto(a) for a in precedenti}
        nuovi = [{**a, "scartato_il": ora} for a in scartati if chiave_acconto(a) not in gia]
        await db.paghe_mensili.update_one(
            {"dipendente_id": periodo[0], "anno": periodo[1], "mese": periodo[2]},
            {"$set": {"acconti": validi,
                      "acconti_scartati_regola_2018": precedenti + nuovi,
                      "bonificato_regola_contanti_il": ora,
                      "updated_at": ora}},
        )

    esiti = await db.pagamenti_esiti.find({}, {"_id": 0, "pdf_data": 0}).to_list(20000)
    certi_per_key: Dict[str, bool] = {}
    periodi_esiti: Dict[Tuple[Any, int, int], List[str]] = {}
    for esito in esiti:
        report["prove_esaminate"] += 1
        key = str(esito.get("key") or esito.get("id") or "")
        origine = str(esito.get("origine") or "")
        testo = " ".join(str(esito.get(k) or "") for k in (
            "codice_fiscale", "beneficiario", "causale"))
        certo = bool(esito.get("associazione_certa"))
        motivo = esito.get("associazione_certa_motivo")
        # Solo una prova documentale/bancaria, mai un importo scritto a mano.
        if not certo and (origine in {ORIGINE_BANCA, ORIGINE_PDF} or key.startswith(("ecm:", "gc:"))):
            if not e_pagamento_non_stipendio(testo):
                candidato, motivo_trovato = risolvi_dipendente(indici, testo)
                if candidato and str(candidato.get("id")) == str(esito.get("dipendente_id")):
                    certo, motivo = True, motivo_trovato
                    report["prove_promosse_certe"] += 1
                    if len(report["dettaglio_prove"]) < 100:
                        report["dettaglio_prove"].append({
                            "key": key, "dipendente_id": esito.get("dipendente_id"),
                            "motivo": motivo, "origine": origine,
                        })
                    if not dry_run:
                        fine = data_cessazione(dip_map.get(esito.get("dipendente_id"), {}))
                        await db.pagamenti_esiti.update_one(
                            {"key": esito.get("key")},
                            {"$set": {"associazione_certa": True,
                                      "associazione_certa_motivo": motivo,
                                      "associazione_certa_fonte": origine or "storico",
                                      "data_cessazione_rapporto": fine,
                                      "associazione_certa_at": ora}},
                        )
        certi_per_key[key] = certo
        try:
            periodo = (esito.get("dipendente_id"), int(esito.get("anno")), int(esito.get("mese")))
        except (TypeError, ValueError):
            continue
        periodi_esiti.setdefault(periodo, []).append(key)

    for periodo, keys in periodi_esiti.items():
        tutti_certi = bool(keys) and all(certi_per_key.get(k, False) for k in keys)
        if tutti_certi:
            report["periodi_promossi_certi"] += 1
        if not dry_run:
            await db.paghe_mensili.update_one(
                {"dipendente_id": periodo[0], "anno": periodo[1], "mese": periodo[2]},
                {"$set": {"bonifico_riconciliato_auto": tutti_certi,
                          "updated_at": ora}},
            )

    if not dry_run:
        from app.hr.routers.dipendenti_cloud import _ricalcola_stato_paga

        for dip, anno, mese in periodi_contanti:
            if dip and anno and mese:
                await _ricalcola_stato_paga(db, dip, anno, mese)
        await db.sistema_stato.update_one(
            {"key": migrazione},
            {"$set": {"key": migrazione, "completato": True,
                      "completato_il": ora, "report": {
                          k: v for k, v in report.items() if not k.startswith("dettaglio_")
                      }}},
            upsert=True,
        )
    return report
