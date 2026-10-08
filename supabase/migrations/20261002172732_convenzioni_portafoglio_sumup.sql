-- Portafoglio hotel e ricariche SumUp Hosted Checkout.
-- La chiave SumUp resta nel backend. Il database registra richieste e movimenti,
-- ma accredita soltanto una conferma PAID verificata dal backend con l'API SumUp.

create sequence if not exists public.bb_ricariche_numero;

create table if not exists public.bb_ricariche_sumup (
  id uuid primary key default extensions.gen_random_uuid(),
  struttura_id uuid not null references public.bb_strutture(id) on delete cascade,
  riferimento text not null unique,
  idempotenza text not null unique,
  importo numeric(10,2) not null check (importo > 0),
  valuta text not null default 'EUR' check (valuta = 'EUR'),
  stato text not null default 'CREATA' check (
    stato in ('CREATA','PENDING','PAID','FAILED','EXPIRED','ERROR','PARTIALLY_REFUNDED','REFUNDED')
  ),
  checkout_id text unique,
  hosted_url text,
  merchant_code text,
  transaction_id text,
  transaction_code text,
  rimborsato numeric(10,2) not null default 0 check (rimborsato >= 0),
  movimento_accredito uuid unique references public.bb_movimenti(id),
  ultimo_errore text,
  ultimo_evento jsonb not null default '{}'::jsonb,
  creato timestamptz not null default now(),
  aggiornato timestamptz not null default now(),
  ultima_verifica timestamptz,
  scade_il timestamptz not null default now() + interval '30 minutes',
  pagato_il timestamptz,
  rimborsato_il timestamptz
);

create index if not exists bb_ricariche_sumup_struttura
  on public.bb_ricariche_sumup(struttura_id, creato desc);
create index if not exists bb_ricariche_sumup_verifica
  on public.bb_ricariche_sumup(stato, ultima_verifica, creato)
  where checkout_id is not null;

alter table public.bb_ricariche_sumup enable row level security;
revoke all on table public.bb_ricariche_sumup from public, anon, authenticated;
revoke all on sequence public.bb_ricariche_numero from public, anon, authenticated;

alter table public.bb_movimenti
  add column if not exists ricarica_sumup_id uuid references public.bb_ricariche_sumup(id),
  add column if not exists riferimento_esterno text;

create unique index if not exists bb_movimenti_riferimento_esterno
  on public.bb_movimenti(riferimento_esterno)
  where riferimento_esterno is not null;

alter table public.bb_movimenti drop constraint if exists bb_movimenti_tipo_check;
alter table public.bb_movimenti add constraint bb_movimenti_tipo_check
  check (tipo in ('ricarica','prenotazione','rimborso','storno_ricarica'));

create or replace function public.bb_alb_ricarica_prepara(
  sid uuid, p text, imp numeric, pidempotenza text
) returns json
language plpgsql security definer set search_path='' as $$
declare s public.bb_strutture; r public.bb_ricariche_sumup; base text; numero bigint;
begin
  perform public.bb_check_alb(sid,p);
  select * into s from public.bb_strutture where id=sid and disattivata_il is null for update;
  if not found then raise exception 'Struttura non attiva'; end if;
  if imp < public.bb_cfg('ricarica_min','5')::numeric
     or imp > public.bb_cfg('ricarica_max','2000')::numeric
     or round(imp,2) <> imp then
    raise exception 'Importo non valido (da % a % €)',
      public.bb_cfg('ricarica_min','5'), public.bb_cfg('ricarica_max','2000');
  end if;
  pidempotenza:=left(trim(coalesce(pidempotenza,'')),80);
  if length(pidempotenza)<8 then raise exception 'Identificativo richiesta non valido'; end if;
  select * into r from public.bb_ricariche_sumup where idempotenza=pidempotenza;
  if found then
    if r.struttura_id<>sid or r.importo<>imp then raise exception 'Richiesta già usata con dati diversi'; end if;
    return json_build_object('id',r.id,'riferimento',r.riferimento,'importo',r.importo,
      'struttura',s.nome,'stato',r.stato,'url',r.hosted_url);
  end if;
  numero:=nextval('public.bb_ricariche_numero');
  base:=trim(both '-' from regexp_replace(upper(s.nome),'[^A-Z0-9]+','-','g'));
  if base='' then base:='HOTEL'; end if;
  insert into public.bb_ricariche_sumup(
    struttura_id,riferimento,idempotenza,importo
  ) values (
    sid,'RICARICA-'||left(base,24)||'-'||lpad(numero::text,6,'0'),pidempotenza,imp
  ) returning * into r;
  return json_build_object('id',r.id,'riferimento',r.riferimento,'importo',r.importo,
    'struttura',s.nome,'stato',r.stato);
end $$;

create or replace function public.bb_ricarica_collega_checkout(
  prid uuid, pcheckout text, purl text, pmerchant text, pstatus text default 'PENDING'
) returns void
language plpgsql security definer set search_path='' as $$
begin
  perform public.gc_assert_runtime_secret();
  if coalesce(trim(pcheckout),'')='' or purl !~ '^https://checkout[.]sumup[.]com/' then
    raise exception 'Checkout SumUp non valido';
  end if;
  update public.bb_ricariche_sumup set
    checkout_id=trim(pcheckout), hosted_url=purl, merchant_code=trim(pmerchant),
    stato=case when upper(pstatus)='PENDING' then 'PENDING' else 'CREATA' end,
    aggiornato=now(), ultimo_errore=null
  where id=prid and stato in ('CREATA','ERROR');
  if not found then raise exception 'Ricarica non collegabile'; end if;
end $$;

create or replace function public.bb_ricarica_errore(prid uuid, perrore text) returns void
language plpgsql security definer set search_path='' as $$
begin
  perform public.gc_assert_runtime_secret();
  update public.bb_ricariche_sumup set stato='ERROR',ultimo_errore=left(perrore,400),aggiornato=now()
  where id=prid and stato in ('CREATA','PENDING','ERROR');
end $$;

create or replace function public.bb_ricarica_applica_sumup(
  pcheckout text, preference text, pamount numeric, pcurrency text, pmerchant text,
  pstatus text, ptransaction_id text default '', ptransaction_code text default '',
  prefunded numeric default 0, praw jsonb default '{}'::jsonb
) returns json
language plpgsql security definer set search_path='' as $$
declare r public.bb_ricariche_sumup; mid uuid; delta numeric; nuovo_stato text;
begin
  perform public.gc_assert_runtime_secret();
  select * into r from public.bb_ricariche_sumup
   where checkout_id=trim(pcheckout) for update;
  if not found then return json_build_object('ignorato',true); end if;
  if r.riferimento<>trim(preference) or r.importo<>round(pamount,2)
     or r.valuta<>upper(trim(pcurrency))
     or (coalesce(r.merchant_code,'')<>'' and r.merchant_code<>trim(pmerchant)) then
    update public.bb_ricariche_sumup set stato='ERROR',
      ultimo_errore='Dati SumUp non coerenti con la ricarica registrata',aggiornato=now(),ultima_verifica=now()
      where id=r.id;
    raise exception 'Dati checkout non coerenti';
  end if;

  prefunded:=least(r.importo,greatest(0,round(coalesce(prefunded,0),2)));
  if upper(trim(pstatus))='PAID' then
    insert into public.bb_movimenti(
      struttura_id,tipo,importo,nota,confermato,ricarica_sumup_id,riferimento_esterno
    ) values (
      r.struttura_id,'ricarica',r.importo,'Ricarica SumUp · '||r.riferimento,true,r.id,
      'sumup:'||r.checkout_id||':paid'
    ) on conflict (riferimento_esterno) where riferimento_esterno is not null do nothing
    returning id into mid;
    if mid is null then
      select id into mid from public.bb_movimenti
       where riferimento_esterno='sumup:'||r.checkout_id||':paid';
    end if;
    delta:=prefunded-r.rimborsato;
    if delta>0 then
      insert into public.bb_movimenti(
        struttura_id,tipo,importo,nota,confermato,ricarica_sumup_id,riferimento_esterno
      ) values (
        r.struttura_id,'storno_ricarica',-delta,
        'Rimborso SumUp '||prefunded||' € · '||r.riferimento,true,r.id,
        'sumup:'||r.checkout_id||':refund:'||round(prefunded*100)::bigint
      ) on conflict (riferimento_esterno) where riferimento_esterno is not null do nothing;
    end if;
    nuovo_stato:=case when prefunded>=r.importo then 'REFUNDED'
      when prefunded>0 then 'PARTIALLY_REFUNDED' else 'PAID' end;
    update public.bb_ricariche_sumup set
      stato=nuovo_stato, movimento_accredito=mid,
      transaction_id=coalesce(nullif(trim(ptransaction_id),''),transaction_id),
      transaction_code=coalesce(nullif(trim(ptransaction_code),''),transaction_code),
      rimborsato=greatest(rimborsato,prefunded),
      pagato_il=coalesce(pagato_il,now()),
      rimborsato_il=case when prefunded>0 then coalesce(rimborsato_il,now()) else rimborsato_il end,
      ultimo_evento=coalesce(praw,'{}'::jsonb),ultimo_errore=null,
      aggiornato=now(),ultima_verifica=now()
    where id=r.id;
  elsif upper(trim(pstatus)) in ('FAILED','EXPIRED') then
    update public.bb_ricariche_sumup set stato=upper(trim(pstatus)),
      ultimo_evento=coalesce(praw,'{}'::jsonb),aggiornato=now(),ultima_verifica=now()
    where id=r.id and movimento_accredito is null;
  else
    update public.bb_ricariche_sumup set
      stato=case when scade_il<now() and movimento_accredito is null then 'EXPIRED' else stato end,
      ultimo_evento=coalesce(praw,'{}'::jsonb),aggiornato=now(),ultima_verifica=now()
    where id=r.id;
  end if;
  return json_build_object('id',r.id,'stato',nuovo_stato,'accreditato',mid is not null);
end $$;

create or replace function public.bb_sumup_ricariche_da_verificare(
  plimite int default 50, psid uuid default null
) returns json
language plpgsql security definer set search_path='' as $$
declare risultato json;
begin
  perform public.gc_assert_runtime_secret();
  with candidati as (
    select r.id from public.bb_ricariche_sumup r
    where r.checkout_id is not null
      and (psid is null or r.struttura_id=psid)
      and r.creato>now()-interval '365 days'
      and r.stato not in ('FAILED','REFUNDED','ERROR')
      and (r.ultima_verifica is null or r.ultima_verifica<now()-case when psid is null then interval '10 minutes' else interval '5 seconds' end)
    order by case when r.stato in ('CREATA','PENDING','EXPIRED') then 0 else 1 end,r.creato
    for update skip locked limit least(100,greatest(1,plimite))
  ), presi as (
    update public.bb_ricariche_sumup r set ultima_verifica=now()
    from candidati c where r.id=c.id
    returning r.checkout_id
  )
  select coalesce(json_agg(checkout_id),'[]'::json) into risultato from presi;
  return risultato;
end $$;

create or replace function public.bb_alb_portafoglio(sid uuid,p text) returns json
language plpgsql security definer set search_path='' as $$
declare disponibile numeric; impegnato numeric; acquistato numeric; restituito numeric; consumato numeric;
begin
  perform public.bb_check_alb(sid,p);
  disponibile:=public.bb_saldo(sid);
  select coalesce(sum(greatest(v.qta-v.usate,0)*v.fascia),0) into impegnato
   from public.bb_vouchers v
   where v.struttura_id=sid and not v.annullato and v.data_fine>=public.bb_oggi();
  select coalesce(sum(-m.importo),0) into acquistato from public.bb_movimenti m
   where m.struttura_id=sid and m.confermato and m.tipo='prenotazione' and m.importo<0;
  select coalesce(sum(m.importo),0) into restituito from public.bb_movimenti m
   where m.struttura_id=sid and m.confermato and m.tipo='rimborso' and m.importo>0;
  consumato:=greatest(0,acquistato-restituito-impegnato);
  return json_build_object(
    'disponibile',disponibile,'impegnato',impegnato,'consumato',consumato,
    'ricariche',(select coalesce(json_agg(x order by x.creato desc),'[]'::json) from (
      select r.id,r.riferimento,r.importo,r.valuta,r.stato,r.rimborsato,r.hosted_url,
        r.creato,r.pagato_il,r.rimborsato_il
      from public.bb_ricariche_sumup r where r.struttura_id=sid limit 100
    ) x)
  );
end $$;

revoke all on function public.bb_alb_ricarica_prepara(uuid,text,numeric,text) from public;
revoke all on function public.bb_ricarica_collega_checkout(uuid,text,text,text,text) from public;
revoke all on function public.bb_ricarica_errore(uuid,text) from public;
revoke all on function public.bb_ricarica_applica_sumup(text,text,numeric,text,text,text,text,text,numeric,jsonb) from public;
revoke all on function public.bb_sumup_ricariche_da_verificare(int,uuid) from public;
revoke all on function public.bb_alb_portafoglio(uuid,text) from public;
grant execute on function public.bb_alb_ricarica_prepara(uuid,text,numeric,text) to anon,authenticated;
grant execute on function public.bb_ricarica_collega_checkout(uuid,text,text,text,text) to anon,authenticated;
grant execute on function public.bb_ricarica_errore(uuid,text) to anon,authenticated;
grant execute on function public.bb_ricarica_applica_sumup(text,text,numeric,text,text,text,text,text,numeric,jsonb) to anon,authenticated;
grant execute on function public.bb_sumup_ricariche_da_verificare(int,uuid) to anon,authenticated;
grant execute on function public.bb_alb_portafoglio(uuid,text) to anon,authenticated;

-- Il vecchio percorso eseguiva chiamate HTTP dal database e non aveva webhook.
-- Resta nello storico delle migrazioni, ma non è più richiamabile dal browser.
revoke all on function public.bb_alb_ricarica_sumup(uuid,text,numeric,text) from public,anon,authenticated;
