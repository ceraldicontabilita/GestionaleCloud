"""Procedure periodiche ritirate dal titolare l'11/10/2026.

Il blocco precede la configurazione del server: nessuna variabile ambiente o
riavvio puo' riattivare queste 71 procedure. I relativi comandi manuali e le
elaborazioni avviate da un import restano disponibili.
"""

import os


ERP_RETIRED_JOBS = frozenset({
    "domain_outbox", "sumup_sync", "ai_tesoreria_shadow",
    "ai_cash_flow_13w_shadow", "ai_contabile_shadow", "ai_fiscale_shadow",
    "ai_acquisti_shadow", "ai_crediti_shadow", "ai_compliance_shadow",
    "link_verbali_fatture", "protocollo_drive_incrementale",
    "cedolini_stampe_controllo", "fonti_ferme", "acube_controllo",
    "controlli_incrociati", "incroci_fiscali", "drive_censimento_doppioni",
    "f24_doppioni", "bonifici_pdf_inbox", "allinea_status_documenti",
    "riallinea_cessazioni_auto", "chiusure_attivita", "cedolini_hr_riverifica",
    "cedolini_tipo_dal_pdf", "hr_pagamenti_deposito", "mittenti_email_sync",
    "tax_code_registry_sync", "collaudo_invarianti", "cedolini_bloccati",
    "dedup_fatture", "quietanze_orfane", "pagamenti_dichiarati",
    "banca_versamenti_proiezione", "f24_quietanze_banca", "fatture_emesse",
    "fatture_estere_riallineamento", "automazioni_prima_nota",
    "verbali_email_scan", "verbali_notifications", "scadenze_partite_check",
    "controllo_pos_calendario", "controllo_canoni_noleggio",
    "f24_scadenze_check", "verifica_trattenute_retro", "f24_scadenze_check_pm",
    "fornitori_duplicati_check", "fornitori_unifica_duplicati", "gmail_full_scan",
    "paypal_recupera_fatture_email", "lotti_dizionario_categorie",
    "lotti_identifica_col_web", "agenti_proposte", "agenti_righe_acquisti",
    "paypal_automatico", "categorie_banca", "bonifici_via_estratto",
    "pec_cartelle_notifiche", "notifiche_operative_colazioni",
    "ricariche_sumup_hotel",
})
HR_RETIRED_JOBS = frozenset({"sincronizza_paghe", "scadenze"})
LOTTI_RETIRED_JOBS = frozenset({
    "aggiorna_riferimenti_fatture", "pulizia_lotti_scaduti",
    "haccp_daily_generation", "digest_mattutino", "backup_notturno",
    "pipeline_aggiornamento", "normalizza_nuovi_prodotti",
    "sincronizza_operatori_hr", "sync_gestionale_fatture", "lettura_articoli_ai",
})
RETIRED_PERIODIC_JOBS = ERP_RETIRED_JOBS | HR_RETIRED_JOBS | LOTTI_RETIRED_JOBS


def scheduler_job_enabled(job_id: str) -> bool:
    if job_id in RETIRED_PERIODIC_JOBS:
        return False
    selected = {
        value.strip()
        for value in os.getenv("SCHEDULER_JOB_ALLOWLIST", "").split(",")
        if value.strip()
    }
    return not selected or job_id in selected
