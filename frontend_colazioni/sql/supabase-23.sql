-- v23: inviti recensione per struttura, consensi separati e coda WhatsApp.
-- Applicare una sola volta dal SQL editor Supabase. Tutte le tabelle hanno RLS
-- senza policy: dal browser si passa esclusivamente per le RPC qui definite.

insert into bb_config(k,v) values
 ('recensioni_google_url',''),
 ('recensioni_tripadvisor_url',''),
 ('recensioni_informativa_versione','2026-10-01-v1'),
 ('recensioni_informativa_url',''),
 ('recensioni_ritardo_minuti','180')
on conflict (k) do nothing;

create table if not exists bb_recensioni_link (
 id uuid primary key default gen_random_uuid(),
 struttura_id uuid not null unique references bb_strutture(id) on delete cascade,
 token uuid not null unique default gen_random_uuid(),
 attivo boolean not null default true,
 creato timestamptz not null default now(),
 aggiornato timestamptz not null default now());

create table if not exists bb_recensioni_visite (
 id uuid primary key default gen_random_uuid(),
 sessione uuid not null unique default gen_random_uuid(),
 review_token uuid not null unique default gen_random_uuid(),
 struttura_id uuid not null references bb_strutture(id) on delete cascade,
 fonte text not null check (fonte in ('qr','nfc','wifi','link')),
 informativa_versione text not null,
 informativa_url text not null default '',
 telefono text,
 creato timestamptz not null default now(),
 completato timestamptz,
 scade timestamptz not null default (now()+interval '90 days'));

create table if not exists bb_recensioni_consensi (
 id uuid primary key default gen_random_uuid(),
 visita_id uuid not null references bb_recensioni_visite(id) on delete cascade,
 finalita text not null check (finalita in ('geolocalizzazione','whatsapp')),
 azione text not null check (azione in ('acconsentito','negato','revocato')),
 informativa_versione text not null,
 fonte text not null,
 ip text not null default '?',
 client text not null default '',
 dettagli jsonb not null default '{}'::jsonb,
 avvenuto timestamptz not null default now());
create index if not exists bb_rec_consenso_visita on bb_recensioni_consensi(visita_id,finalita,avvenuto desc);

create table if not exists bb_recensioni_posizioni (
 id uuid primary key default gen_random_uuid(),
 visita_id uuid not null references bb_recensioni_visite(id) on delete cascade,
 latitudine numeric(9,6) not null check (latitudine between -90 and 90),
 longitudine numeric(9,6) not null check (longitudine between -180 and 180),
 accuratezza_m numeric(10,2),
 rilevato timestamptz not null default now());

create table if not exists bb_recensioni_inviti (
 id uuid primary key default gen_random_uuid(),
 visita_id uuid not null unique references bb_recensioni_visite(id) on delete cascade,
 previsto timestamptz not null,
 stato text not null default 'in_attesa' check (stato in ('in_attesa','invio','inviato','annullato','errore')),
 tentativi int not null default 0,
 provider_id text,
 ultimo_errore text,
 inviato timestamptz,
 aggiornato timestamptz not null default now());
create index if not exists bb_rec_inviti_previsto on bb_recensioni_inviti(stato,previsto);

create table if not exists bb_recensioni_click (
 id uuid primary key default gen_random_uuid(),
 visita_id uuid not null references bb_recensioni_visite(id) on delete cascade,
 destinazione text not null check (destinazione in ('google','tripadvisor')),
 avvenuto timestamptz not null default now());

alter table bb_recensioni_link enable row level security;
alter table bb_recensioni_visite enable row level security;
alter table bb_recensioni_consensi enable row level security;
alter table bb_recensioni_posizioni enable row level security;
alter table bb_recensioni_inviti enable row level security;
alter table bb_recensioni_click enable row level security;

create or replace function bb_recensioni_consenso_attivo(pvisita uuid, pfinalita text)
returns boolean language sql stable security definer set search_path=public as $$
 select coalesce((select azione='acconsentito' from bb_recensioni_consensi
  where visita_id=pvisita and finalita=pfinalita order by avvenuto desc,id desc limit 1),false) $$;
revoke all on function bb_recensioni_consenso_attivo(uuid,text) from public,anon,authenticated;

create or replace function bb_recensioni_link_pubblico(ptoken uuid) returns json
language sql stable security definer set search_path=public as $$
 select json_build_object(
  'struttura',s.nome,
  'informativa_versione',bb_cfg('recensioni_informativa_versione','2026-10-01-v1'),
  'informativa_url',bb_cfg('recensioni_informativa_url',''))
 from bb_recensioni_link l join bb_strutture s on s.id=l.struttura_id
 where l.token=ptoken and l.attivo and s.pin_hash is not null $$;
grant execute on function bb_recensioni_link_pubblico(uuid) to anon,authenticated;

create or replace function bb_recensioni_visita_apri(ptoken uuid, pfonte text) returns json
language plpgsql security definer set search_path=public,extensions as $$
declare l bb_recensioni_link; v bb_recensioni_visite;
begin
 select * into l from bb_recensioni_link where token=ptoken and attivo;
 if not found then raise exception 'Link non valido o disattivato'; end if;
 if pfonte not in ('qr','nfc','wifi','link') then pfonte:='link'; end if;
 insert into bb_recensioni_visite(struttura_id,fonte,informativa_versione,informativa_url)
 values(l.struttura_id,pfonte,bb_cfg('recensioni_informativa_versione','2026-10-01-v1'),bb_cfg('recensioni_informativa_url','')) returning * into v;
 return json_build_object('sessione',v.sessione,'creato',v.creato);
end $$;
grant execute on function bb_recensioni_visita_apri(uuid,text) to anon,authenticated;

create or replace function bb_recensioni_consenso(
 psessione uuid, pfinalita text, pacconsento boolean, pversione text, pclient text default '') returns json
language plpgsql security definer set search_path=public,extensions as $$
declare v bb_recensioni_visite;
begin
 select * into v from bb_recensioni_visite where sessione=psessione and scade>now();
 if not found then raise exception 'Sessione non valida o scaduta'; end if;
 if pfinalita not in ('geolocalizzazione','whatsapp') then raise exception 'Finalità non valida'; end if;
 if pversione<>v.informativa_versione then raise exception 'Informativa aggiornata: ricarica la pagina'; end if;
 insert into bb_recensioni_consensi(visita_id,finalita,azione,informativa_versione,fonte,ip,client,dettagli)
 values(v.id,pfinalita,case when pacconsento then 'acconsentito' else 'negato' end,v.informativa_versione,'pagina_colazione',bb_ip(),left(coalesce(pclient,''),300),jsonb_build_object('azione_esplicita',true));
 if pfinalita='whatsapp' and not pacconsento then
  update bb_recensioni_inviti set stato='annullato',aggiornato=now() where visita_id=v.id and stato in ('in_attesa','errore');
 end if;
 return json_build_object('salvato',true,'avvenuto',now());
end $$;
grant execute on function bb_recensioni_consenso(uuid,text,boolean,text,text) to anon,authenticated;

create or replace function bb_recensioni_telefono(psessione uuid, ptelefono text) returns void
language plpgsql security definer set search_path=public,extensions as $$
declare v bb_recensioni_visite; n text;
begin
 select * into v from bb_recensioni_visite where sessione=psessione and scade>now();
 if not found then raise exception 'Sessione non valida o scaduta'; end if;
 if not bb_recensioni_consenso_attivo(v.id,'whatsapp') then raise exception 'Consenso WhatsApp assente'; end if;
 n:=regexp_replace(coalesce(ptelefono,''),'[ ()\.-]','','g');
 if n !~ '^\+[1-9][0-9]{7,14}$' then raise exception 'Usa il formato internazionale, per esempio +393331234567'; end if;
 update bb_recensioni_visite set telefono=n where id=v.id;
end $$;
grant execute on function bb_recensioni_telefono(uuid,text) to anon,authenticated;

create or replace function bb_recensioni_posizione(psessione uuid, plat numeric, plon numeric, paccuratezza numeric default null) returns void
language plpgsql security definer set search_path=public,extensions as $$
declare v bb_recensioni_visite;
begin
 select * into v from bb_recensioni_visite where sessione=psessione and scade>now();
 if not found then raise exception 'Sessione non valida o scaduta'; end if;
 if not bb_recensioni_consenso_attivo(v.id,'geolocalizzazione') then raise exception 'Consenso geolocalizzazione assente'; end if;
 insert into bb_recensioni_posizioni(visita_id,latitudine,longitudine,accuratezza_m) values(v.id,plat,plon,paccuratezza);
end $$;
grant execute on function bb_recensioni_posizione(uuid,numeric,numeric,numeric) to anon,authenticated;

create or replace function bb_recensioni_revoca(psessione uuid, pfinalita text, pclient text default '') returns json
language plpgsql security definer set search_path=public,extensions as $$
declare v bb_recensioni_visite;
begin
 select * into v from bb_recensioni_visite where sessione=psessione and scade>now();
 if not found then raise exception 'Sessione non valida o scaduta'; end if;
 if pfinalita not in ('geolocalizzazione','whatsapp') then raise exception 'Finalità non valida'; end if;
 insert into bb_recensioni_consensi(visita_id,finalita,azione,informativa_versione,fonte,ip,client,dettagli)
 values(v.id,pfinalita,'revocato',v.informativa_versione,'pagina_colazione',bb_ip(),left(coalesce(pclient,''),300),jsonb_build_object('azione_esplicita',true));
 if pfinalita='whatsapp' then
  update bb_recensioni_inviti set stato='annullato',aggiornato=now() where visita_id=v.id and stato in ('in_attesa','errore');
 end if;
 return json_build_object('revocato',true,'avvenuto',now());
end $$;
grant execute on function bb_recensioni_revoca(uuid,text,text) to anon,authenticated;

create or replace function bb_recensioni_completa(psessione uuid) returns json
language plpgsql security definer set search_path=public,extensions as $$
declare v bb_recensioni_visite; rit int; pianificato boolean:=false; quando timestamptz;
begin
 select * into v from bb_recensioni_visite where sessione=psessione and scade>now();
 if not found then raise exception 'Sessione non valida o scaduta'; end if;
 if not exists(select 1 from bb_recensioni_consensi where visita_id=v.id and finalita='geolocalizzazione')
    or not exists(select 1 from bb_recensioni_consensi where visita_id=v.id and finalita='whatsapp') then
  raise exception 'Completa entrambe le scelte prima di proseguire';
 end if;
 update bb_recensioni_visite set completato=coalesce(completato,now()) where id=v.id;
 if bb_recensioni_consenso_attivo(v.id,'whatsapp') and v.telefono is not null then
  begin rit:=greatest(0,least(10080,bb_cfg('recensioni_ritardo_minuti','180')::int)); exception when others then rit:=180; end;
  quando:=now()+make_interval(mins=>rit);
  insert into bb_recensioni_inviti(visita_id,previsto) values(v.id,quando)
  on conflict(visita_id) do nothing;
  pianificato:=true;
 end if;
 return json_build_object('completato',true,'invito_pianificato',pianificato,'previsto',quando);
end $$;
grant execute on function bb_recensioni_completa(uuid) to anon,authenticated;

create or replace function bb_recensioni_invito_pubblico(ptoken uuid) returns json
language sql stable security definer set search_path=public as $$
 select json_build_object('struttura',s.nome,'google_url',bb_cfg('recensioni_google_url',''),'tripadvisor_url',bb_cfg('recensioni_tripadvisor_url',''))
 from bb_recensioni_visite v join bb_strutture s on s.id=v.struttura_id
 where v.review_token=ptoken and v.scade>now() $$;
grant execute on function bb_recensioni_invito_pubblico(uuid) to anon,authenticated;

create or replace function bb_recensioni_click(ptoken uuid, pdestinazione text) returns void
language plpgsql security definer set search_path=public,extensions as $$
declare vid uuid;
begin
 if pdestinazione not in ('google','tripadvisor') then raise exception 'Destinazione non valida'; end if;
 select id into vid from bb_recensioni_visite where review_token=ptoken and scade>now();
 if vid is null then raise exception 'Invito non valido o scaduto'; end if;
 insert into bb_recensioni_click(visita_id,destinazione) values(vid,pdestinazione);
end $$;
grant execute on function bb_recensioni_click(uuid,text) to anon,authenticated;

create or replace function bb_tit_recensioni_stato(p text, sid uuid) returns json
language plpgsql security definer set search_path=public,extensions as $$
declare l bb_recensioni_link;
begin
 perform bb_check_tit(p);
 if not exists(select 1 from bb_strutture where id=sid) then raise exception 'Struttura non trovata'; end if;
 insert into bb_recensioni_link(struttura_id) values(sid) on conflict(struttura_id) do nothing;
 select * into l from bb_recensioni_link where struttura_id=sid;
 return json_build_object(
  'token',l.token,'attivo',l.attivo,
  'config',json_build_object('google_url',bb_cfg('recensioni_google_url',''),'tripadvisor_url',bb_cfg('recensioni_tripadvisor_url',''),'informativa_versione',bb_cfg('recensioni_informativa_versione','2026-10-01-v1'),'informativa_url',bb_cfg('recensioni_informativa_url',''),'ritardo_minuti',bb_cfg('recensioni_ritardo_minuti','180')::int),
  'visite',(select count(*) from bb_recensioni_visite where struttura_id=sid),
  'optin_whatsapp',(select count(*) from bb_recensioni_visite v where v.struttura_id=sid and bb_recensioni_consenso_attivo(v.id,'whatsapp')),
  'inviti_inviati',(select count(*) from bb_recensioni_inviti i join bb_recensioni_visite v on v.id=i.visita_id where v.struttura_id=sid and i.stato='inviato'),
  'click_google',(select count(*) from bb_recensioni_click c join bb_recensioni_visite v on v.id=c.visita_id where v.struttura_id=sid and c.destinazione='google'),
  'click_tripadvisor',(select count(*) from bb_recensioni_click c join bb_recensioni_visite v on v.id=c.visita_id where v.struttura_id=sid and c.destinazione='tripadvisor'));
end $$;
grant execute on function bb_tit_recensioni_stato(text,uuid) to anon,authenticated;

create or replace function bb_tit_recensioni_link_rigenera(p text, sid uuid) returns uuid
language plpgsql security definer set search_path=public,extensions as $$
declare t uuid:=gen_random_uuid();
begin
 perform bb_check_tit(p);
 insert into bb_recensioni_link(struttura_id,token) values(sid,t)
 on conflict(struttura_id) do update set token=t,attivo=true,aggiornato=now();
 return t;
end $$;
grant execute on function bb_tit_recensioni_link_rigenera(text,uuid) to anon,authenticated;

create or replace function bb_tit_recensioni_config_salva(p text, pdati jsonb) returns void
language plpgsql security definer set search_path=public,extensions as $$
declare g text:=trim(coalesce(pdati->>'google_url','')); tr text:=trim(coalesce(pdati->>'tripadvisor_url','')); u text:=trim(coalesce(pdati->>'informativa_url','')); ver text:=left(trim(coalesce(pdati->>'informativa_versione','')),60); rit int;
begin
 perform bb_check_tit(p);
 if g<>'' and g !~ '^https://' then raise exception 'Il link Google deve iniziare con https://'; end if;
 if tr<>'' and tr !~ '^https://' then raise exception 'Il link Tripadvisor deve iniziare con https://'; end if;
 if u<>'' and u !~ '^https://' then raise exception 'Il link informativa deve iniziare con https://'; end if;
 if ver='' then raise exception 'Scrivi la versione dell’informativa'; end if;
 begin rit:=greatest(0,least(10080,(pdati->>'ritardo_minuti')::int)); exception when others then raise exception 'Il ritardo deve essere un numero di minuti'; end;
 insert into bb_config(k,v) values('recensioni_google_url',g),('recensioni_tripadvisor_url',tr),('recensioni_informativa_url',u),('recensioni_informativa_versione',ver),('recensioni_ritardo_minuti',rit::text)
 on conflict(k) do update set v=excluded.v;
end $$;
grant execute on function bb_tit_recensioni_config_salva(text,jsonb) to anon,authenticated;

create or replace function bb_recensioni_inviti_prendi(plimite int default 20) returns json
language plpgsql security definer set search_path=public,extensions as $$
declare risultato json;
begin
 perform public.gc_assert_runtime_secret();
 with candidati as (
  select i.id from bb_recensioni_inviti i join bb_recensioni_visite v on v.id=i.visita_id
  where i.stato in ('in_attesa','errore') and i.previsto<=now() and i.tentativi<5 and v.telefono is not null
    and bb_recensioni_consenso_attivo(v.id,'whatsapp')
  order by i.previsto for update of i skip locked limit least(100,greatest(1,plimite))
 ), presi as (
  update bb_recensioni_inviti i set stato='invio',tentativi=i.tentativi+1,aggiornato=now()
  from candidati c where i.id=c.id returning i.*
 )
 select coalesce(json_agg(json_build_object('job_id',p.id,'telefono',v.telefono,'struttura',s.nome,'review_token',v.review_token)),'[]'::json)
 into risultato from presi p join bb_recensioni_visite v on v.id=p.visita_id join bb_strutture s on s.id=v.struttura_id;
 return risultato;
end $$;
revoke all on function bb_recensioni_inviti_prendi(int) from public;
grant execute on function bb_recensioni_inviti_prendi(int) to anon,authenticated;

create or replace function bb_recensioni_invito_esito(pjob uuid, pinviato boolean, pprovider text default '', perrore text default '') returns void
language plpgsql security definer set search_path=public,extensions as $$
begin
 perform public.gc_assert_runtime_secret();
 update bb_recensioni_inviti set
  stato=case when pinviato then 'inviato' when tentativi>=5 then 'errore' else 'errore' end,
  provider_id=case when pinviato then left(pprovider,200) else provider_id end,
  ultimo_errore=case when pinviato then null else left(perrore,400) end,
  inviato=case when pinviato then now() else inviato end,
  previsto=case when pinviato then previsto else now()+make_interval(mins=>least(60,power(2,least(tentativi,5))::int)) end,
  aggiornato=now()
 where id=pjob and stato='invio';
end $$;
revoke all on function bb_recensioni_invito_esito(uuid,boolean,text,text) from public;
grant execute on function bb_recensioni_invito_esito(uuid,boolean,text,text) to anon,authenticated;

revoke all on bb_recensioni_link,bb_recensioni_visite,bb_recensioni_consensi,bb_recensioni_posizioni,bb_recensioni_inviti,bb_recensioni_click from anon,authenticated;
