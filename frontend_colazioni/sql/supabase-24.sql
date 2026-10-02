-- Colazioni B&B v24: una struttura demo deve registrare il gestore prima dell'accesso.

create or replace function bb_hotel_info(codice text) returns json language sql security definer set search_path=public as
$$ select json_build_object('id',id,'nome',nome,'sfondo',sfondo,'benvenuto',benvenuto,'attivo',pin_hash is not null,'demo',demo,'pin_off',bb_pin_off(),'bar',bb_bar_pubblico())
   from bb_strutture where accesso=lower(trim(codice)) $$;
revoke all on function bb_hotel_info(text) from public;
grant execute on function bb_hotel_info(text) to anon, authenticated;

create or replace function bb_alb_login(paccesso text, ppin text) returns json language plpgsql security definer set search_path=public,extensions as $$
declare s bb_strutture; k text; ki text; sec int; rest int;
begin
 select * into s from bb_strutture where accesso=lower(trim(coalesce(paccesso,'')));
 if not found or s.pin_hash is null then return json_build_object('ok',false,'msg','Accesso non ancora attivato'); end if;
 if s.demo then return json_build_object('ok',false,'registrazione_richiesta',true,'msg','Registrati con il link condiviso dal bar e scegli il tuo PIN personale'); end if;
 k := 'alb:'||s.accesso; ki := 'ip:'||bb_ip();
 sec := greatest(bb_blocco(k),bb_blocco(ki));
 if sec>0 then return json_build_object('ok',false,'bloccato',sec,'msg','Troppi tentativi: riprova tra '||ceil(sec/60.0)::int||' minuti'); end if;
 if s.pin_hash = crypt(coalesce(ppin,''),s.pin_hash) then
  perform bb_tentativi_ok(k);
  return json_build_object('ok',true,'token',bb_sessione_nuova('alb',s.id,12),'sid',s.id,'nome',s.nome);
 end if;
 rest := bb_fallito(k,5); perform bb_fallito(ki,25);
 return json_build_object('ok',false,'restanti',rest,'msg',case when rest>0 then 'PIN errato: ti restano '||rest||' tentativi' else 'Troppi tentativi: riprova tra 15 minuti' end);
end $$;
revoke all on function bb_alb_login(text,text) from public;
grant execute on function bb_alb_login(text,text) to anon, authenticated;

create or replace function bb_invito_accetta(token text, ppin text, pindirizzo text, ptelefono text, pemail text) returns json language plpgsql security definer set search_path=public,extensions as $$
declare s bb_strutture; rec text;
begin
 select * into s from bb_strutture where invito_token=lower(trim(token)) for update;
 if not found then raise exception 'Invito non valido o già utilizzato'; end if;
 if coalesce(length(ppin),0)<4 or length(ppin)>20 then raise exception 'Il PIN deve avere almeno 4 caratteri'; end if;
 if ppin in ('1111','2222','3333') then raise exception 'Scegli un PIN personale diverso da quello di prova'; end if;
 rec := bb_codice_recupero();
 update bb_strutture set pin_hash=crypt(ppin,gen_salt('bf')), recupero_hash=crypt(bb_norm_codice(rec),gen_salt('bf')), invito_token=null, demo=false,
   indirizzo=coalesce(nullif(left(trim(coalesce(pindirizzo,'')),150),''),indirizzo), telefono=coalesce(nullif(left(trim(coalesce(ptelefono,'')),30),''),telefono), email=coalesce(nullif(left(trim(coalesce(pemail,'')),100),''),email)
   where id=s.id;
 update bb_richieste_pin set chiusa=true where struttura_id=s.id and not chiusa;
 delete from bb_sessioni where struttura_id=s.id;
 return json_build_object('id',s.id,'accesso',s.accesso,'nome',s.nome,'recupero',rec,'token',bb_sessione_nuova('alb',s.id,12));
end $$;
revoke all on function bb_invito_accetta(text,text,text,text,text) from public;
grant execute on function bb_invito_accetta(text,text,text,text,text) to anon, authenticated;
