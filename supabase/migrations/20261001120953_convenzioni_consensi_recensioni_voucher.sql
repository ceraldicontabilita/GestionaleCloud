-- Consensi ospite e inviti recensione per il flusso Colazioni B&B.
-- Il numero WhatsApp arriva gia' cifrato dal backend: il browser non puo'
-- scrivere direttamente ne' leggere le tabelle sottostanti.

insert into public.bb_config(k,v) values
 ('privacy_notice_version','2026-10-01-v1'),
 ('privacy_notice_url','/privacy'),
 ('review_google_url','https://g.page/r/CQqRnemKplctEBM/review'),
 ('review_tripadvisor_url','https://www.tripadvisor.it/UserReviewEdit-g187785-d2695184-Ceraldi_Caffe-Naples_Province_of_Naples_Campania.html'),
 ('review_invite_delay_minutes','180')
on conflict (k) do nothing;

create or replace function public.bb_tit_config_set(p text,pk text,pv text) returns void
language plpgsql security definer set search_path='' as $$
begin
 perform public.bb_check_tit(p);
 pv := trim(coalesce(pv,''));
 if pk not in (
  'bar_nome','bar_indirizzo','bar_tel','bar_orari','bar_maps','bar_email','bar_whatsapp',
  'ricarica_min','ricarica_max','anticipo_max_giorni','ordini_limite_ora','msg_ospite',
  'msg_invito','sumup_merchant_code','supplemento_tavolo','privacy_notice_version',
  'privacy_notice_url','review_google_url','review_tripadvisor_url','review_invite_delay_minutes'
 ) then raise exception 'Impostazione non valida'; end if;
 if pk='ricarica_min' and (pv !~ '^\d+$' or pv::int not between 1 and 1000) then raise exception 'Ricarica minima: numero tra 1 e 1000'; end if;
 if pk='ricarica_max' and (pv !~ '^\d+$' or pv::int not between 5 and 10000) then raise exception 'Ricarica massima: numero tra 5 e 10000'; end if;
 if pk='anticipo_max_giorni' and (pv !~ '^\d+$' or pv::int not between 1 and 365) then raise exception 'Giorni di anticipo: numero tra 1 e 365'; end if;
 if pk='review_invite_delay_minutes' and (pv !~ '^\d+$' or pv::int not between 0 and 10080) then raise exception 'Attesa invito: minuti tra 0 e 10080'; end if;
 if pk='ordini_limite_ora' and pv<>'' and pv !~ '^([01]\d|2[0-3]):[0-5]\d$' then raise exception 'Orario nel formato 20:00 (oppure vuoto)'; end if;
 if pk='supplemento_tavolo' then
  pv:=replace(pv,',','.');
  if pv !~ '^\d+(\.\d{1,2})?$' or pv::numeric not between 0 and 100 then raise exception 'Supplemento: importo tra 0 e 100'; end if;
 end if;
 if pk in ('bar_maps','review_google_url','review_tripadvisor_url') and pv<>'' and pv !~ '^https://' then raise exception 'Il link deve iniziare con https://'; end if;
 if pk='privacy_notice_url' and pv<>'' and pv !~ '^(https://|/)' then raise exception 'Informativa: usa un link https:// oppure un percorso /...'; end if;
 if pk='privacy_notice_version' and (pv='' or length(pv)>80) then raise exception 'Versione informativa non valida'; end if;
 insert into public.bb_config(k,v) values (pk,pv) on conflict (k) do update set v=excluded.v;
end $$;
revoke all on function public.bb_tit_config_set(text,text,text) from public, anon, authenticated;
grant execute on function public.bb_tit_config_set(text,text,text) to anon;

create table if not exists public.bb_ospite_aperture (
  id uuid primary key default extensions.gen_random_uuid(),
  voucher_id text not null references public.bb_vouchers(id) on delete cascade,
  struttura_id uuid not null references public.bb_strutture(id) on delete cascade,
  fonte text not null check (fonte in ('qr','nfc','wifi','link','whatsapp')),
  informativa_versione text not null,
  aperto_il timestamptz not null default now()
);

create table if not exists public.bb_ospite_consensi (
  id uuid primary key default extensions.gen_random_uuid(),
  voucher_id text not null references public.bb_vouchers(id) on delete cascade,
  struttura_id uuid not null references public.bb_strutture(id) on delete cascade,
  finalita text not null check (finalita in ('geolocalizzazione','whatsapp')),
  azione text not null check (azione in ('concesso','negato','revocato')),
  fonte text not null check (fonte in ('qr','nfc','wifi','link','whatsapp')),
  informativa_versione text not null,
  metadati jsonb not null default '{}'::jsonb,
  avvenuto_il timestamptz not null default now()
);
create index if not exists bb_ospite_consensi_stato_idx
  on public.bb_ospite_consensi(voucher_id,finalita,avvenuto_il desc);

create table if not exists public.bb_ospite_posizioni (
  voucher_id text primary key references public.bb_vouchers(id) on delete cascade,
  latitudine numeric(9,6) not null,
  longitudine numeric(9,6) not null,
  accuratezza_m numeric(10,2),
  rilevata_il timestamptz not null default now()
);

create table if not exists public.bb_ospite_contatti (
  voucher_id text primary key references public.bb_vouchers(id) on delete cascade,
  telefono_cifrato text not null,
  telefono_impronta text not null,
  telefono_finale text not null,
  consenso_attivo boolean not null default true,
  aggiornato_il timestamptz not null default now()
);

create table if not exists public.bb_voucher_recensioni_inviti (
  voucher_id text primary key references public.bb_vouchers(id) on delete cascade,
  dovuto_il timestamptz not null,
  stato text not null default 'in_attesa'
    check (stato in ('in_attesa','invio','inviato','annullato','errore')),
  tentativi int not null default 0,
  provider_id text,
  ultimo_errore text,
  inviato_il timestamptz,
  aggiornato_il timestamptz not null default now()
);
create index if not exists bb_voucher_recensioni_inviti_coda_idx
  on public.bb_voucher_recensioni_inviti(stato,dovuto_il);

create table if not exists public.bb_voucher_recensioni_click (
  id uuid primary key default extensions.gen_random_uuid(),
  voucher_id text not null references public.bb_vouchers(id) on delete cascade,
  destinazione text not null check (destinazione in ('google','tripadvisor')),
  cliccato_il timestamptz not null default now()
);

alter table public.bb_ospite_aperture enable row level security;
alter table public.bb_ospite_consensi enable row level security;
alter table public.bb_ospite_posizioni enable row level security;
alter table public.bb_ospite_contatti enable row level security;
alter table public.bb_voucher_recensioni_inviti enable row level security;
alter table public.bb_voucher_recensioni_click enable row level security;
revoke all on public.bb_ospite_aperture, public.bb_ospite_consensi,
 public.bb_ospite_posizioni, public.bb_ospite_contatti,
 public.bb_voucher_recensioni_inviti, public.bb_voucher_recensioni_click
 from public, anon, authenticated;

create or replace function public.bb_ospite_privacy_stato(vid text) returns json
language sql stable security definer set search_path='' as $$
 with v as (
  select id from public.bb_vouchers where id=upper(trim(vid)) and not annullato
 ), ultimi as (
  select distinct on (c.finalita) c.finalita,c.azione
  from public.bb_ospite_consensi c join v on v.id=c.voucher_id
  order by c.finalita,c.avvenuto_il desc,c.id desc
 )
 select json_build_object(
  'geolocalizzazione',coalesce((select azione='concesso' from ultimi where finalita='geolocalizzazione'),false),
  'whatsapp',coalesce((select azione='concesso' from ultimi where finalita='whatsapp'),false),
  'telefono_finale',(select telefono_finale from public.bb_ospite_contatti x join v on v.id=x.voucher_id where x.consenso_attivo),
  'informativa_versione',public.bb_cfg('privacy_notice_version','2026-10-01-v1'),
  'informativa_url',public.bb_cfg('privacy_notice_url','/privacy'),
  'google_url',public.bb_cfg('review_google_url',''),
  'tripadvisor_url',public.bb_cfg('review_tripadvisor_url',''))
$$;
revoke all on function public.bb_ospite_privacy_stato(text) from public, anon, authenticated;
grant execute on function public.bb_ospite_privacy_stato(text) to anon, authenticated;

create or replace function public.bb_ospite_evento_runtime(
  vid text, pfonte text, pfinalita text, pazion text, pversione text,
  ptelefono_cifrato text default null, pimpronta text default null,
  pfinale text default null, plat numeric default null, plon numeric default null,
  paccuratezza numeric default null
) returns json language plpgsql security definer set search_path='' as $$
declare v public.bb_vouchers; fonte text:=lower(trim(coalesce(pfonte,'link')));
 delay_min int; base_invito timestamptz; eventi_ora int;
begin
 perform public.gc_assert_runtime_secret();
 select * into v from public.bb_vouchers where id=upper(trim(vid)) and not annullato;
 if not found then raise exception 'Voucher non valido'; end if;
 if fonte not in ('qr','nfc','wifi','link','whatsapp') then fonte:='link'; end if;
 if pfinalita not in ('apertura','geolocalizzazione','whatsapp','recensione_google','recensione_tripadvisor') then raise exception 'Finalita non valida'; end if;
 select
  (select count(*) from public.bb_ospite_aperture where voucher_id=v.id and aperto_il>now()-interval '1 hour')+
  (select count(*) from public.bb_ospite_consensi where voucher_id=v.id and avvenuto_il>now()-interval '1 hour')+
  (select count(*) from public.bb_voucher_recensioni_click where voucher_id=v.id and cliccato_il>now()-interval '1 hour')
 into eventi_ora;
 if eventi_ora>=120 then raise exception 'Troppe richieste: riprova piu tardi'; end if;
 if pfinalita='apertura' then
  insert into public.bb_ospite_aperture(voucher_id,struttura_id,fonte,informativa_versione)
  values(v.id,v.struttura_id,fonte,left(trim(pversione),80));
  return public.bb_ospite_privacy_stato(v.id);
 end if;
 if pfinalita like 'recensione_%' then
  insert into public.bb_voucher_recensioni_click(voucher_id,destinazione)
  values(v.id,case when pfinalita='recensione_google' then 'google' else 'tripadvisor' end);
  return public.bb_ospite_privacy_stato(v.id);
 end if;
 if pazion not in ('concesso','negato','revocato') then raise exception 'Azione non valida'; end if;
 if coalesce(trim(pversione),'')='' then raise exception 'Versione informativa mancante'; end if;
 insert into public.bb_ospite_consensi(voucher_id,struttura_id,finalita,azione,fonte,informativa_versione,metadati)
 values(v.id,v.struttura_id,pfinalita,pazion,fonte,left(trim(pversione),80),
  jsonb_strip_nulls(jsonb_build_object('accuratezza_m',paccuratezza)));
 if pfinalita='geolocalizzazione' then
  if pazion='concesso' then
   if plat is null or plon is null or plat not between -90 and 90 or plon not between -180 and 180 then raise exception 'Posizione non valida'; end if;
   insert into public.bb_ospite_posizioni(voucher_id,latitudine,longitudine,accuratezza_m)
   values(v.id,plat,plon,paccuratezza)
   on conflict(voucher_id) do update set latitudine=excluded.latitudine,longitudine=excluded.longitudine,
    accuratezza_m=excluded.accuratezza_m,rilevata_il=now();
  elsif pazion='revocato' then
   delete from public.bb_ospite_posizioni where voucher_id=v.id;
  end if;
 elsif pfinalita='whatsapp' then
  if pazion='concesso' then
   if coalesce(ptelefono_cifrato,'')='' or coalesce(pimpronta,'')='' or pfinale !~ '^\d{4}$' then raise exception 'Recapito WhatsApp non valido'; end if;
   insert into public.bb_ospite_contatti(voucher_id,telefono_cifrato,telefono_impronta,telefono_finale,consenso_attivo)
   values(v.id,ptelefono_cifrato,pimpronta,pfinale,true)
   on conflict(voucher_id) do update set telefono_cifrato=excluded.telefono_cifrato,
    telefono_impronta=excluded.telefono_impronta,telefono_finale=excluded.telefono_finale,
    consenso_attivo=true,aggiornato_il=now();
   delay_min:=greatest(0,public.bb_cfg('review_invite_delay_minutes','180')::int);
   base_invito:=greatest(now(),(v.data::timestamp + interval '12 hours') at time zone 'Europe/Rome');
   insert into public.bb_voucher_recensioni_inviti(voucher_id,dovuto_il,stato)
   values(v.id,base_invito+make_interval(mins=>delay_min),'in_attesa')
   on conflict(voucher_id) do update set dovuto_il=excluded.dovuto_il,stato='in_attesa',
    ultimo_errore=null,aggiornato_il=now();
  else
   update public.bb_ospite_contatti set consenso_attivo=false,aggiornato_il=now() where voucher_id=v.id;
   update public.bb_voucher_recensioni_inviti set stato='annullato',aggiornato_il=now()
    where voucher_id=v.id and stato in ('in_attesa','errore');
  end if;
 end if;
 return public.bb_ospite_privacy_stato(v.id);
end $$;
revoke all on function public.bb_ospite_evento_runtime(text,text,text,text,text,text,text,text,numeric,numeric,numeric) from public, anon, authenticated;
grant execute on function public.bb_ospite_evento_runtime(text,text,text,text,text,text,text,text,numeric,numeric,numeric) to anon, service_role;

create or replace function public.bb_recensioni_claim_runtime(plimit int default 20) returns json
language plpgsql security definer set search_path='' as $$
declare risultato json;
begin
 perform public.gc_assert_runtime_secret();
 with candidati as (
  select j.voucher_id from public.bb_voucher_recensioni_inviti j
  join public.bb_ospite_contatti c on c.voucher_id=j.voucher_id and c.consenso_attivo
  where j.stato in ('in_attesa','errore') and j.dovuto_il<=now() and j.tentativi<5
  order by j.dovuto_il for update skip locked limit least(greatest(plimit,1),50)
 ), presi as (
  update public.bb_voucher_recensioni_inviti j set stato='invio',tentativi=tentativi+1,aggiornato_il=now()
  from candidati x where x.voucher_id=j.voucher_id returning j.voucher_id
 )
 select coalesce(json_agg(json_build_object(
  'voucher_id',v.id,'telefono_cifrato',c.telefono_cifrato,'struttura',s.nome,
  'google_url',public.bb_cfg('review_google_url',''),'tripadvisor_url',public.bb_cfg('review_tripadvisor_url',''))),'[]'::json)
 into risultato from presi p join public.bb_vouchers v on v.id=p.voucher_id
 join public.bb_ospite_contatti c on c.voucher_id=v.id join public.bb_strutture s on s.id=v.struttura_id;
 return risultato;
end $$;
revoke all on function public.bb_recensioni_claim_runtime(int) from public, anon, authenticated;
grant execute on function public.bb_recensioni_claim_runtime(int) to anon, service_role;

create or replace function public.bb_recensioni_esito_runtime(vid text, pok boolean, pprovider_id text default null, perrore text default null) returns void
language plpgsql security definer set search_path='' as $$
begin
 perform public.gc_assert_runtime_secret();
 update public.bb_voucher_recensioni_inviti set stato=case when pok then 'inviato' else 'errore' end,
  provider_id=left(pprovider_id,240),ultimo_errore=left(perrore,500),
  inviato_il=case when pok then now() else inviato_il end,aggiornato_il=now()
 where voucher_id=upper(trim(vid));
end $$;
revoke all on function public.bb_recensioni_esito_runtime(text,boolean,text,text) from public, anon, authenticated;
grant execute on function public.bb_recensioni_esito_runtime(text,boolean,text,text) to anon, service_role;

