-- Colazioni B&B v25: rende autonomo il JSON fiscale usato al primo accesso.
-- Evita che una cache/risoluzione di funzione interna impedisca l'apertura
-- dell'area albergatore dopo la registrazione del PIN.

create or replace function public.bb_fiscali_ok(s public.bb_strutture)
returns boolean
language sql
immutable
set search_path=public
as $$
 select coalesce(s.ragione_sociale,'')<>''
    and (coalesce(s.piva,'')<>'' or coalesce(s.codice_fiscale,'')<>'')
    and coalesce(s.fatt_indirizzo,'')<>''
    and coalesce(s.fatt_cap,'')<>''
    and coalesce(s.fatt_comune,'')<>''
    and coalesce(s.fatt_provincia,'')<>''
$$;

create or replace function public.bb_fiscali_json(s public.bb_strutture)
returns json
language sql
immutable
set search_path=public
as $$
 select json_build_object(
   'ragione_sociale',s.ragione_sociale,
   'piva',s.piva,
   'codice_fiscale',s.codice_fiscale,
   'indirizzo',s.fatt_indirizzo,
   'cap',s.fatt_cap,
   'comune',s.fatt_comune,
   'provincia',s.fatt_provincia,
   'codice_destinatario',s.codice_destinatario,
   'pec',s.pec,
   'completi',
      coalesce(s.ragione_sociale,'')<>''
      and (coalesce(s.piva,'')<>'' or coalesce(s.codice_fiscale,'')<>'')
      and coalesce(s.fatt_indirizzo,'')<>''
      and coalesce(s.fatt_cap,'')<>''
      and coalesce(s.fatt_comune,'')<>''
      and coalesce(s.fatt_provincia,'')<>''
 )
$$;

revoke all on function public.bb_fiscali_ok(public.bb_strutture) from public, anon, authenticated;
revoke all on function public.bb_fiscali_json(public.bb_strutture) from public, anon, authenticated;
