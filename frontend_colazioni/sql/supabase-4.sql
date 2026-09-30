-- Colazioni B&B · migrazione 4: ricarica del borsellino con SumUp (Hosted Checkout)
-- La chiave API sta nel Vault di Supabase con nome 'sumup_api_key' (mai nel browser).
-- Il credito viene accreditato SOLO dopo aver verificato con SumUp che il pagamento risulta PAID,
-- con importo e riferimento uguali a quelli registrati.

alter table bb_movimenti add column if not exists sumup_id text;
alter table bb_movimenti add column if not exists sumup_url text;

create or replace function bb_sumup_key() returns text language sql security definer set search_path=public,vault as
$$ select decrypted_secret from vault.decrypted_secrets where name='sumup_api_key' limit 1 $$;
revoke execute on function bb_sumup_key() from public,anon,authenticated;

create or replace function bb_sumup_attivo() returns boolean language sql security definer set search_path=public,vault as
$$ select exists(select 1 from vault.decrypted_secrets where name='sumup_api_key') $$;
revoke all on function bb_sumup_attivo() from public; grant execute on function bb_sumup_attivo() to anon;

create or replace function bb_sumup_merchant() returns text language plpgsql security definer set search_path=public,extensions as $$
declare m text; r extensions.http_response;
begin
 select v into m from bb_config where k='sumup_merchant_code';
 if m is not null and m<>'' then return m; end if;
 r := extensions.http(('GET','https://api.sumup.com/v0.1/me',array[extensions.http_header('Authorization','Bearer '||bb_sumup_key())],null,null)::extensions.http_request);
 m := r.content::jsonb->'merchant_profile'->>'merchant_code';
 if m is null then raise exception 'Codice esercente SumUp non trovato'; end if;
 insert into bb_config values ('sumup_merchant_code',m) on conflict (k) do update set v=excluded.v;
 return m;
end $$;
revoke execute on function bb_sumup_merchant() from public,anon,authenticated;

create or replace function bb_alb_ricarica_sumup(sid uuid,p text,imp numeric,ret text) returns json language plpgsql security definer set search_path=public,extensions as $$
declare mid uuid; r extensions.http_response; j jsonb; s bb_strutture;
begin
 perform bb_check_alb(sid,p);
 if not bb_sumup_attivo() then raise exception 'Pagamento online non ancora attivo'; end if;
 if imp<5 or imp>2000 then raise exception 'Importo non valido (5–2000 €)'; end if;
 if ret is null or ret !~ '^https://' then raise exception 'Indirizzo di ritorno non valido'; end if;
 select * into s from bb_strutture where id=sid;
 insert into bb_movimenti(struttura_id,tipo,importo,nota,confermato) values (sid,'ricarica',imp,'Ricarica SumUp (in attesa di pagamento)',false) returning id into mid;
 begin
  perform http_set_curlopt('CURLOPT_TIMEOUT','15');
  r := http(('POST','https://api.sumup.com/v0.1/checkouts',array[http_header('Authorization','Bearer '||bb_sumup_key())],'application/json',
    jsonb_build_object('checkout_reference',mid::text,'amount',imp,'currency','EUR','merchant_code',bb_sumup_merchant(),
      'description','Ricarica borsellino colazioni · '||s.nome,'redirect_url',ret,'hosted_checkout',jsonb_build_object('enabled',true))::text)::http_request);
  j := r.content::jsonb;
  if r.status not between 200 and 299 or j->>'hosted_checkout_url' is null then raise exception 'SumUp: % %',r.status,left(r.content,200); end if;
  update bb_movimenti set sumup_id=j->>'id', sumup_url=j->>'hosted_checkout_url' where id=mid;
  return json_build_object('url',j->>'hosted_checkout_url');
 exception when others then
  delete from bb_movimenti where id=mid;
  raise exception 'Pagamento non disponibile al momento. Riprova o ricarica dal bar. (%)',left(sqlerrm,120);
 end;
end $$;
grant execute on function bb_alb_ricarica_sumup(uuid,text,numeric,text) to anon;
revoke execute on function bb_alb_ricarica_sumup(uuid,text,numeric,text) from public;

-- verifica con SumUp le ricariche in attesa di una struttura; accredita solo se PAID e coerenti
create or replace function bb_sumup_verifica(sid uuid) returns void language plpgsql security definer set search_path=public,extensions as $$
declare m record; r extensions.http_response; j jsonb;
begin
 if not bb_sumup_attivo() then return; end if;
 for m in select * from bb_movimenti where struttura_id=sid and not confermato and sumup_id is not null and t>now()-interval '3 days' loop
  begin
   perform http_set_curlopt('CURLOPT_TIMEOUT','10');
   r := http(('GET','https://api.sumup.com/v0.1/checkouts/'||m.sumup_id,array[http_header('Authorization','Bearer '||bb_sumup_key())],null,null)::http_request);
   j := r.content::jsonb;
   if r.status=200 and j->>'status'='PAID' and (j->>'amount')::numeric=m.importo and j->>'currency'='EUR' and j->>'checkout_reference'=m.id::text then
     update bb_movimenti set confermato=true, nota='Ricarica SumUp pagata' where id=m.id and not confermato;
   elsif r.status=200 and j->>'status' in ('FAILED','EXPIRED') then
     delete from bb_movimenti where id=m.id and not confermato;
   end if;
  exception when others then null;
  end;
 end loop;
 -- ricarica abbandonata da oltre 3 giorni: la rimuovo
 delete from bb_movimenti where struttura_id=sid and not confermato and sumup_id is not null and t<=now()-interval '3 days';
end $$;
revoke execute on function bb_sumup_verifica(uuid) from public,anon,authenticated;

create or replace function bb_alb_stato(sid uuid,p text) returns json language plpgsql security definer set search_path=public,extensions as $$
begin
 perform bb_check_alb(sid,p);
 perform bb_sumup_verifica(sid);
 return json_build_object(
  'struttura',(select json_build_object('id',id,'nome',nome,'indirizzo',indirizzo,'fasce',fasce,'saldo',bb_saldo(id)) from bb_strutture where id=sid),
  'oggi',bb_oggi(),'bar',bb_bar_pubblico(),'menu',bb_menu_pubblico(),'sumup',bb_sumup_attivo(),
  'movimenti',(select coalesce(json_agg(m order by m.t desc),'[]'::json) from (select id,t,tipo,importo,nota,confermato,sumup_url from bb_movimenti where struttura_id=sid) m),
  'vouchers',(select coalesce(json_agg(v order by v.creato desc),'[]'::json) from (select id,fascia,qta,usate,data,ospite,creato,annullato from bb_vouchers where struttura_id=sid) v));
end $$;

-- il titolare non deve "confermare a mano" le ricariche SumUp: sono automatiche
create or replace function bb_tit_stato(p text) returns json language plpgsql security definer set search_path=public,extensions as $$
begin
 perform bb_check_tit(p);
 return json_build_object(
  'oggi',bb_oggi(),'bar',bb_bar_pubblico(),'menu',bb_menu_pubblico(),'allergeni',bb_menu_allergeni(),'sumup',bb_sumup_attivo(),
  'strutture',(select coalesce(json_agg(x order by x.nome),'[]'::json) from (select id,nome,indirizzo,telefono,demo,fasce,bb_saldo(id) saldo from bb_strutture) x),
  'attesa',(select coalesce(json_agg(x order by x.t),'[]'::json) from (select m.id,m.t,m.importo,s.nome from bb_movimenti m join bb_strutture s on s.id=m.struttura_id where not m.confermato and m.sumup_id is null) x),
  'movimenti',(select coalesce(json_agg(x order by x.t desc),'[]'::json) from (select m.id,m.struttura_id,s.nome struttura,m.t,m.tipo,m.importo,m.nota,m.confermato from bb_movimenti m join bb_strutture s on s.id=m.struttura_id) x),
  'vouchers',(select coalesce(json_agg(x order by x.creato desc),'[]'::json) from (select v.id,v.struttura_id,s.nome struttura,v.fascia,v.qta,v.usate,v.data,v.ospite,v.creato,v.annullato from bb_vouchers v join bb_strutture s on s.id=v.struttura_id) x));
end $$;
