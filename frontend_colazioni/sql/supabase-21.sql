-- v21: fase 2 della sicurezza. Restano solo le sessioni con token:
--  * titolare: la sessione la apre il gestionale (bb_tit_sessione_apri), nessun PIN suo;
--  * albergatore: bb_alb_login (blocco dopo 5 errori) e token di 12 ore.
-- Spariscono il PIN in chiaro come credenziale delle RPC, la "modalità prova" e il vecchio PIN del titolare.

create or replace function bb_check_tit(p text) returns void language plpgsql security definer set search_path=public,extensions as $$
begin
 if not bb_sessione_ok(p,'tit') then raise exception 'Sessione scaduta: rientra con il PIN'; end if;
end $$;

create or replace function bb_check_tit_strict(p text) returns void language plpgsql security definer set search_path=public,extensions as $$
begin
 if not bb_sessione_ok(p,'tit') then raise exception 'Sessione scaduta: rientra con il PIN'; end if;
end $$;

create or replace function bb_check_alb(sid uuid, p text) returns void language plpgsql security definer set search_path=public,extensions as $$
begin
 if not exists(select 1 from bb_strutture where id=sid and pin_hash is not null) then raise exception 'Accesso non ancora attivato'; end if;
 if not bb_sessione_ok(p,'alb',sid) then raise exception 'Sessione scaduta: rientra con il PIN'; end if;
end $$;

-- i controlli non si chiamano più dall'esterno (senza blocco dei tentativi permetterebbero di provare i PIN)
revoke all on function bb_check_tit(text), bb_check_tit_strict(text), bb_check_alb(uuid,text) from public, anon, authenticated;

-- la "modalità prova" non esiste più
create or replace function bb_pin_off() returns boolean language sql stable security definer set search_path=public as $$ select false $$;
create or replace function bb_pin_stato() returns json language sql security definer set search_path=public as $$ select json_build_object('attivo',false,'fino',null) $$;
delete from bb_config where k in ('pin_off_until','tit_pin');
drop function if exists bb_tit_pin_off(text,int);
drop function if exists bb_tit_pin_cambia(text,text);
