-- 08/10/2026 — Copie di prova, quarantene datate e snapshot precedenti non
-- fanno parte del modello applicativo. Il database riparte senza archivi
-- legacy; restano soltanto le tabelle correnti richieste dal codice.

drop table if exists gestionale.corrispettivi_iva_prima_20260914;
drop table if exists gestionale.documents_menu_rimossi_20260915;
drop table if exists gestionale.documents_prima_prova_20260930;
drop table if exists gestionale.documents_rimossi_20260914;
drop table if exists gestionale.fatture_pre2026_rimosse_20260920;
drop table if exists gestionale.quietanze_f24_rimosse_20261001;

drop table if exists hr.app_bonifici_duplicati_20260914;
drop table if exists hr.app_bonifici_modifiche_20260914;
drop table if exists hr.app_cedolini_prima_prova_20260930;
drop table if exists hr.app_dipendenti_modifiche_20260914;
drop table if exists hr.app_dipendenti_prima_20260914b;
drop table if exists hr.app_dipendenti_prima_20260914c;
drop table if exists hr.app_paghe_mensili_rimosse_20260914;
