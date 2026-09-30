-- Colazioni B&B · migrazione 3: navi in porto (Guardia Costiera) e scioperi (MIT), con cache
-- Richiede l'estensione http (schema extensions). Aggiornamento "pigro": al massimo ogni 20 minuti,
-- alla prima richiesta della pagina ospite/titolare; se la fonte non risponde restano gli ultimi dati.

create extension if not exists http with schema extensions;

create table if not exists bb_esterni (
  k text primary key,
  dati jsonb not null default '{}',
  aggiornato timestamptz,
  tentato timestamptz not null default now(),
  errore text);
alter table bb_esterni enable row level security;
revoke all on bb_esterni from anon, authenticated;

create or replace function bb_aggiorna_esterni() returns void language plpgsql security definer set search_path=public,extensions as $$
declare arr jsonb; dep jsonb; navi jsonb; x xml; sc jsonb;
begin
 insert into bb_esterni(k) values ('navi'),('scioperi') on conflict do nothing;
 update bb_esterni set tentato=now() where k in ('navi','scioperi');
 perform http_set_curlopt('CURLOPT_TIMEOUT','10');

 begin
  select content::jsonb into arr from http_get('https://www.mnsw.gov.it/arrivals_departures-api/v1/arrivals');
  select content::jsonb into dep from http_get('https://www.mnsw.gov.it/arrivals_departures-api/v1/departures');
  navi := jsonb_build_object(
   'fonte','Guardia Costiera · EMSWe-Porti','lastUpdate',arr->>'lastUpdate',
   'arrivi',(select coalesce(jsonb_agg(z order by z->>'ora'),'[]') from (
      select jsonb_build_object('nome',e->'ship'->>'name','tipo',case e->'ship'->>'statCode5' when 'A37A2PC' then 'crociera' when 'A36A2PR' then 'traghetto' else 'passeggeri' end,
        'ora',coalesce(e->>'ata',e->>'eta'),'banchina',e->>'berth','stato',e->>'status','da',e->>'previousPort') z
      from jsonb_array_elements(arr->'content') e
      where e->>'arrivalPort'='ITNAP' and (e->'ship'->>'statCode5' in ('A37A2PC','A36A2PR') or e->'ship'->>'type'='PASSENGER')) q),
   'partenze',(select coalesce(jsonb_agg(z order by z->>'ora'),'[]') from (
      select jsonb_build_object('nome',e->'ship'->>'name','tipo',case e->'ship'->>'statCode5' when 'A37A2PC' then 'crociera' when 'A36A2PR' then 'traghetto' else 'passeggeri' end,
        'ora',e->>'etd','banchina',e->>'berth','stato',e->>'status','verso',e->>'nextPort') z
      from jsonb_array_elements(dep->'content') e
      where e->>'departurePort'='ITNAP' and (e->'ship'->>'statCode5' in ('A37A2PC','A36A2PR') or e->'ship'->>'type'='PASSENGER')) q));
  update bb_esterni set dati=navi, aggiornato=now(), errore=null where k='navi';
 exception when others then
  update bb_esterni set errore=left(sqlerrm,300) where k='navi';
 end;

 begin
  select content::xml into x from http_get('https://scioperi.mit.gov.it/mit2/public/scioperi/rss');
  select coalesce(jsonb_agg(s order by s->>'inizio'),'[]') into sc from (
   select jsonb_build_object(
     'inizio',to_char(to_date(substring(t from 'Data inizio: (\d\d/\d\d/\d{4})'),'DD/MM/YYYY'),'YYYY-MM-DD'),
     'fine',to_char(to_date(coalesce(substring(de from 'Data fine: (\d\d/\d\d/\d{4})'),substring(t from 'Data inizio: (\d\d/\d\d/\d{4})')),'DD/MM/YYYY'),'YYYY-MM-DD'),
     'settore',trim(substring(t from 'Settore: (.*?) - Rilevanza')),
     'rilevanza',trim(substring(t from 'Rilevanza: (.*?) - Regione')),
     'regione',trim(substring(t from 'Regione: (.*?) - Provincia')),
     'provincia',trim(substring(t from 'Provincia: (.*)$')),
     'modalita',trim(substring(de from 'modalità: ([^<]*)')),
     'categoria',trim(substring(de from 'Categoria interessata: ([^<]*)')),
     'sindacati',trim(substring(de from 'Sindacati: ([^<]*)'))) s
   from (select (xpath('string(/item/title)',i))[1]::text t,
                replace(replace(replace((xpath('string(/item/description)',i))[1]::text,'&lt;','<'),'&gt;','>'),'&amp;','&') de
         from unnest(xpath('//item',x)) i) d
   where t ~ 'Data inizio: \d\d/\d\d/\d{4}'
     and (t ~ 'Rilevanza: Nazionale' or t ~* 'Regione: *Campania' or t ~* 'Provincia: *Napoli')
     and t !~ 'Settore: Elicotteri') q;
  update bb_esterni set dati=jsonb_build_object('fonte','Ministero delle Infrastrutture e dei Trasporti','elenco',sc), aggiornato=now(), errore=null where k='scioperi';
 exception when others then
  update bb_esterni set errore=left(sqlerrm,300) where k='scioperi';
 end;
end $$;
revoke execute on function bb_aggiorna_esterni() from public,anon,authenticated;

create or replace function bb_esterni_pubblico() returns json language plpgsql security definer set search_path=public,extensions as $$
begin
 if not exists(select 1 from bb_esterni where k='navi' and (aggiornato>now()-interval '20 minutes' or tentato>now()-interval '3 minutes')) then
  perform bb_aggiorna_esterni();
 end if;
 return (select json_build_object(
   'navi',(select dati from bb_esterni where k='navi'),'navi_agg',(select aggiornato from bb_esterni where k='navi'),
   'scioperi',(select dati from bb_esterni where k='scioperi'),'scioperi_agg',(select aggiornato from bb_esterni where k='scioperi'),
   'oggi',bb_oggi()));
end $$;
revoke all on function bb_esterni_pubblico() from public;
grant execute on function bb_esterni_pubblico() to anon;
