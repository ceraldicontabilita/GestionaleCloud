-- Destinazione unica GestionaleCloud: dati copiati con ID invariati tramite
-- procedura di migrazione verificata fuori banda. Questa migration rende
-- riproducibile la struttura, non duplica i dati.
create schema if not exists hr;
create schema if not exists lotti;

do $$
declare table_name text;
begin
  foreach table_name in array array[
    'app_acconti_dipendenti','app_alerts','app_assegnazioni_turni_cloud',
    'app_audit_log','app_bonifici','app_bonifici_da_associare',
    'app_cedolini','app_cedolini_accettazioni','app_dipendenti',
    'app_dipendenti_ordine','app_documenti_cloud','app_employee_contracts',
    'app_ferie_cloud','app_impostazioni','app_missioni_cloud',
    'app_pagamenti_esiti','app_pagamenti_storico','app_paghe_mensili',
    'app_presenze','app_presenze_cloud','app_presenze_invii',
    'app_tablet_operatori','app_tfr_accantonamenti','app_tfr_liquidazioni',
    'app_tfr_simulazione_periodi','app_timbrature','app_turni_cloud','app_users'
  ]
  loop
    execute format(
      'create table if not exists hr.%I (id text primary key, doc jsonb not null)',
      table_name
    );
    execute format('alter table hr.%I enable row level security', table_name);
  end loop;
end $$;

create table if not exists lotti.lotti_documents (
  collection text not null,
  doc_id text not null,
  data jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (collection, doc_id)
);

create table if not exists lotti.lotti_store_config (
  singleton boolean primary key default true,
  secret_sha256 text not null,
  source text not null default 'recovered_mongodb_backup',
  created_at timestamptz not null default now()
);

alter table lotti.lotti_documents enable row level security;
alter table lotti.lotti_store_config enable row level security;

insert into storage.buckets (id, name, public)
values ('menu-images', 'menu-images', true)
on conflict (id) do update set public = excluded.public;
