-- Gli avvisi al titolare nascono nella stessa transazione della prenotazione o
-- degli extra. Uno scheduler server-side li invia su Telegram anche ad app chiusa.

create table if not exists public.bb_notifiche_operative (
 id uuid primary key default extensions.gen_random_uuid(),
 tipo text not null check (tipo in ('prenotazione_hotel','extra_ospite')),
 chiave text not null unique,
 payload jsonb not null default '{}'::jsonb,
 stato text not null default 'in_attesa' check (stato in ('in_attesa','invio','inviato','errore')),
 tentativi int not null default 0,
 previsto timestamptz not null default now(),
 provider_id text,
 ultimo_errore text,
 creato timestamptz not null default now(),
 aggiornato timestamptz not null default now(),
 inviato timestamptz
);

create index if not exists bb_notifiche_operative_coda_idx
 on public.bb_notifiche_operative(stato,previsto) where stato in ('in_attesa','errore');

alter table public.bb_notifiche_operative enable row level security;
revoke all on public.bb_notifiche_operative from public,anon,authenticated;

create or replace function public.bb_accoda_notifica_voucher() returns trigger
language plpgsql security definer set search_path='' as $$
declare nome_struttura text; periodo text;
begin
 select s.nome into nome_struttura from public.bb_strutture s where s.id=new.struttura_id;
 periodo:=to_char(new.data,'DD/MM/YYYY')||case when new.data_fine is not null and new.data_fine<>new.data then ' - '||to_char(new.data_fine,'DD/MM/YYYY') else '' end;
 if tg_op='INSERT' then
  insert into public.bb_notifiche_operative(tipo,chiave,payload)
  values('prenotazione_hotel','prenotazione:'||new.id,jsonb_build_object(
   'voucher_id',new.id,'struttura',coalesce(nome_struttura,'Struttura'),
   'camera',coalesce(nullif(new.camera,''),'non indicata'),'periodo',periodo,
   'quantita',new.qta,'colazione',coalesce(new.colazione_nome,'Colazione'),
   'servizio_tavolo',coalesce(new.servizio_tavolo,false),
   'totale',round(coalesce(new.fascia,0)*coalesce(new.qta,0),2)))
  on conflict(chiave) do nothing;
 elsif new.extra is distinct from old.extra and jsonb_array_length(coalesce(new.extra,'[]'::jsonb))>0 then
  insert into public.bb_notifiche_operative(tipo,chiave,payload)
  values('extra_ospite','extra:'||new.id||':'||public.bb_tok_hash(coalesce(new.extra,'[]'::jsonb)::text||':'||coalesce(new.extra_totale,0)::text),jsonb_build_object(
   'voucher_id',new.id,'struttura',coalesce(nome_struttura,'Struttura'),
   'camera',coalesce(nullif(new.camera,''),'non indicata'),'periodo',periodo,
   'extra',new.extra,'totale',coalesce(new.extra_totale,0)))
  on conflict(chiave) do nothing;
 end if;
 return new;
end $$;

revoke all on function public.bb_accoda_notifica_voucher() from public,anon,authenticated;

drop trigger if exists bb_vouchers_notifica_prenotazione on public.bb_vouchers;
create trigger bb_vouchers_notifica_prenotazione
 after insert on public.bb_vouchers for each row execute function public.bb_accoda_notifica_voucher();

drop trigger if exists bb_vouchers_notifica_extra on public.bb_vouchers;
create trigger bb_vouchers_notifica_extra
 after update of extra on public.bb_vouchers for each row
 when (old.extra is distinct from new.extra)
 execute function public.bb_accoda_notifica_voucher();

create or replace function public.bb_notifiche_operative_prendi(plimite int default 30) returns json
language plpgsql security definer set search_path='' as $$
declare risultato json;
begin
 perform public.gc_assert_runtime_secret();
 with candidati as (
  select n.id from public.bb_notifiche_operative n
  where n.stato in ('in_attesa','errore') and n.previsto<=now() and n.tentativi<8
  order by n.previsto for update skip locked limit least(100,greatest(1,plimite))
 ), presi as (
  update public.bb_notifiche_operative n set stato='invio',tentativi=n.tentativi+1,aggiornato=now()
  from candidati c where n.id=c.id returning n.*
 )
 select coalesce(json_agg(json_build_object('job_id',p.id,'tipo',p.tipo,'payload',p.payload)),'[]'::json)
 into risultato from presi p;
 return risultato;
end $$;

create or replace function public.bb_notifiche_operative_esito(pjob uuid,pinviato boolean,pprovider text default '',perrore text default '') returns void
language plpgsql security definer set search_path='' as $$
begin
 perform public.gc_assert_runtime_secret();
 update public.bb_notifiche_operative set
  stato=case when pinviato then 'inviato' else 'errore' end,
  provider_id=case when pinviato then left(pprovider,200) else provider_id end,
  ultimo_errore=case when pinviato then null else left(perrore,400) end,
  inviato=case when pinviato then now() else inviato end,
  previsto=case when pinviato then previsto else now()+make_interval(mins=>least(60,power(2,least(tentativi,5))::int)) end,
  aggiornato=now()
 where id=pjob and stato='invio';
end $$;

revoke all on function public.bb_notifiche_operative_prendi(int) from public;
revoke all on function public.bb_notifiche_operative_esito(uuid,boolean,text,text) from public;
grant execute on function public.bb_notifiche_operative_prendi(int) to anon,authenticated;
grant execute on function public.bb_notifiche_operative_esito(uuid,boolean,text,text) to anon,authenticated;
