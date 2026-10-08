-- Colazioni B&B · migrazione 2: import menù, annullo/rimborso, impostazioni bar, dati demo

alter table bb_menu add column if not exists allergeni text not null default '';
alter table bb_strutture add column if not exists demo boolean not null default false;
alter table bb_strutture add column if not exists telefono text not null default '';
alter table bb_vouchers add column if not exists annullato boolean not null default false;

alter function bb_oggi() set search_path=public;
alter function bb_saldo(uuid) set search_path=public;

insert into bb_config values ('bar_nome','Bar Pasticceria Ceraldi'),('bar_indirizzo',''),('bar_tel',''),('bar_orari',''),('bar_maps','') on conflict do nothing;

create or replace function bb_bar_pubblico() returns json language sql security definer set search_path=public as
$$ select coalesce(json_object_agg(k,v),'{}'::json) from bb_config where k like 'bar\_%' $$;

create or replace function bb_menu_pubblico() returns json language sql security definer set search_path=public as
$$ select coalesce(json_object_agg(fascia::text,descrizione),'{}'::json) from bb_menu $$;

create or replace function bb_menu_allergeni() returns json language sql security definer set search_path=public as
$$ select coalesce(json_object_agg(fascia::text,allergeni),'{}'::json) from bb_menu $$;

create or replace function bb_ospite(vid text) returns json language sql security definer set search_path=public as
$$ select json_build_object('id',v.id,'fascia',v.fascia,'qta',v.qta,'usate',v.usate,'data',v.data,'ospite',v.ospite,'annullato',v.annullato,
   'struttura',s.nome,'indirizzo',s.indirizzo,'menu',(select descrizione from bb_menu where fascia=v.fascia),
   'allergeni',(select allergeni from bb_menu where fascia=v.fascia),'bar',bb_bar_pubblico())
   from bb_vouchers v join bb_strutture s on s.id=v.struttura_id where v.id=upper(trim(vid)) $$;

create or replace function bb_alb_stato(sid uuid,p text) returns json language plpgsql security definer set search_path=public,extensions as $$
begin
 perform bb_check_alb(sid,p);
 return json_build_object(
  'struttura',(select json_build_object('id',id,'nome',nome,'indirizzo',indirizzo,'fasce',fasce,'saldo',bb_saldo(id)) from bb_strutture where id=sid),
  'oggi',bb_oggi(),'bar',bb_bar_pubblico(),'menu',bb_menu_pubblico(),
  'movimenti',(select coalesce(json_agg(m order by m.t desc),'[]'::json) from (select id,t,tipo,importo,nota,confermato from bb_movimenti where struttura_id=sid) m),
  'vouchers',(select coalesce(json_agg(v order by v.creato desc),'[]'::json) from (select id,fascia,qta,usate,data,ospite,creato,annullato from bb_vouchers where struttura_id=sid) v));
end $$;

-- annullo: rimborsa al borsellino le colazioni non ritirate
create or replace function bb_annulla(vid text) returns json language plpgsql security definer set search_path=public,extensions as $$
declare v bb_vouchers; resto int;
begin
 select * into v from bb_vouchers where id=upper(trim(vid)) for update;
 if not found then raise exception 'Codice non trovato'; end if;
 if v.annullato then raise exception 'Già annullato'; end if;
 resto := v.qta-v.usate;
 if resto<=0 then raise exception 'Nulla da rimborsare: già ritirato'; end if;
 update bb_vouchers set annullato=true where id=v.id;
 insert into bb_movimenti(struttura_id,tipo,importo,nota) values (v.struttura_id,'rimborso',resto*v.fascia,'Annullo '||resto||'× €'||v.fascia||' · '||v.ospite);
 return json_build_object('rimborsato',resto*v.fascia);
end $$;
revoke execute on function bb_annulla(text) from public,anon,authenticated;

create or replace function bb_alb_annulla(sid uuid,p text,vid text) returns json language plpgsql security definer set search_path=public,extensions as $$
begin
 perform bb_check_alb(sid,p);
 if not exists(select 1 from bb_vouchers where id=upper(trim(vid)) and struttura_id=sid) then raise exception 'Codice non trovato'; end if;
 return bb_annulla(vid);
end $$;

create or replace function bb_tit_annulla(p text,vid text) returns json language plpgsql security definer set search_path=public,extensions as $$
begin perform bb_check_tit(p); return bb_annulla(vid); end $$;

create or replace function bb_tit_riscatta(p text,vid text) returns json language plpgsql security definer set search_path=public,extensions as $$
declare v bb_vouchers; s text; msg text; ok boolean:=false;
begin
 perform bb_check_tit(p);
 select * into v from bb_vouchers where id=upper(trim(vid)) for update;
 if not found then return json_build_object('ok',false,'msg','Codice non trovato'); end if;
 if v.annullato then msg:='Voucher annullato';
 elsif v.usate>=v.qta then msg:='Già utilizzato interamente';
 elsif v.data<bb_oggi() then msg:='Voucher scaduto ('||v.data||')';
 elsif v.data>bb_oggi() then msg:='Valido dal '||v.data;
 else update bb_vouchers set usate=usate+1, riscatti=riscatti||now() where id=v.id returning * into v; ok:=true; msg:='Colazione consegnata'; end if;
 select nome into s from bb_strutture where id=v.struttura_id;
 return json_build_object('ok',ok,'msg',msg,'voucher',json_build_object('id',v.id,'fascia',v.fascia,'qta',v.qta,'usate',v.usate,'ospite',v.ospite,'struttura',s,
   'menu',(select descrizione from bb_menu where fascia=v.fascia),'allergeni',(select allergeni from bb_menu where fascia=v.fascia)));
end $$;

create or replace function bb_tit_stato(p text) returns json language plpgsql security definer set search_path=public,extensions as $$
begin
 perform bb_check_tit(p);
 return json_build_object(
  'oggi',bb_oggi(),'bar',bb_bar_pubblico(),'menu',bb_menu_pubblico(),'allergeni',bb_menu_allergeni(),
  'strutture',(select coalesce(json_agg(x order by x.nome),'[]'::json) from (select id,nome,indirizzo,telefono,demo,fasce,bb_saldo(id) saldo from bb_strutture) x),
  'attesa',(select coalesce(json_agg(x order by x.t),'[]'::json) from (select m.id,m.t,m.importo,s.nome from bb_movimenti m join bb_strutture s on s.id=m.struttura_id where not m.confermato) x),
  'movimenti',(select coalesce(json_agg(x order by x.t desc),'[]'::json) from (select m.id,m.struttura_id,s.nome struttura,m.t,m.tipo,m.importo,m.nota,m.confermato from bb_movimenti m join bb_strutture s on s.id=m.struttura_id) x),
  'vouchers',(select coalesce(json_agg(x order by x.creato desc),'[]'::json) from (select v.id,v.struttura_id,s.nome struttura,v.fascia,v.qta,v.usate,v.data,v.ospite,v.creato,v.annullato from bb_vouchers v join bb_strutture s on s.id=v.struttura_id) x));
end $$;

create or replace function bb_tit_menu_import(p text,righe jsonb) returns int language plpgsql security definer set search_path=public,extensions as $$
declare r jsonb; n int:=0; f int;
begin
 perform bb_check_tit(p);
 for r in select * from jsonb_array_elements(righe) loop
  f := (r->>'fascia')::int;
  if f<1 or f>100 or coalesce(trim(r->>'descrizione'),'')='' then raise exception 'Riga non valida: %',r; end if;
  insert into bb_menu(fascia,descrizione,allergeni) values (f,trim(r->>'descrizione'),coalesce(trim(r->>'allergeni'),''))
   on conflict (fascia) do update set descrizione=excluded.descrizione, allergeni=excluded.allergeni;
  n:=n+1;
 end loop;
 return n;
end $$;

create or replace function bb_tit_menu_elimina(p text,pfascia int) returns void language plpgsql security definer set search_path=public,extensions as $$
begin perform bb_check_tit(p); delete from bb_menu where fascia=pfascia; end $$;

create or replace function bb_tit_menu_set(p text,pfascia int,pdesc text) returns void language plpgsql security definer set search_path=public,extensions as $$
begin perform bb_check_tit(p); update bb_menu set descrizione=pdesc where fascia=pfascia; end $$;

create or replace function bb_tit_bar_set(p text,pk text,pv text) returns void language plpgsql security definer set search_path=public,extensions as $$
begin
 perform bb_check_tit(p);
 if pk not in ('bar_nome','bar_indirizzo','bar_tel','bar_orari','bar_maps') then raise exception 'Chiave non valida'; end if;
 insert into bb_config values (pk,coalesce(pv,'')) on conflict (k) do update set v=excluded.v;
end $$;

create or replace function bb_tit_pin_cambia(p text,nuovo text) returns void language plpgsql security definer set search_path=public,extensions as $$
begin
 perform bb_check_tit(p);
 if coalesce(length(nuovo),0)<6 then raise exception 'PIN titolare: minimo 6 cifre'; end if;
 update bb_config set v=crypt(nuovo,gen_salt('bf')) where k='tit_pin';
end $$;

create or replace function bb_tit_elimina_demo(p text) returns int language plpgsql security definer set search_path=public,extensions as $$
declare n int;
begin perform bb_check_tit(p); delete from bb_strutture where demo; get diagnostics n=row_count; return n; end $$;

create or replace function bb_tit_struttura_salva(p text,sid uuid,pnome text,pindirizzo text,ppin text,pfasce int[]) returns json
language plpgsql security definer set search_path=public,extensions as $$
declare nid uuid:=sid;
begin
 perform bb_check_tit(p);
 if sid is null then
  if coalesce(length(ppin),0)<4 then raise exception 'PIN minimo 4 cifre'; end if;
  insert into bb_strutture(nome,indirizzo,pin_hash,fasce) values (pnome,coalesce(pindirizzo,''),crypt(ppin,gen_salt('bf')),coalesce(pfasce,'{3,5,10,12}')) returning id into nid;
 else
  update bb_strutture set nome=coalesce(pnome,nome), indirizzo=coalesce(pindirizzo,indirizzo), fasce=coalesce(pfasce,fasce),
    pin_hash=case when ppin is null or ppin='' then pin_hash else crypt(ppin,gen_salt('bf')) end where id=sid;
 end if;
 return json_build_object('id',nid);
end $$;

do $$ declare f record; begin
 for f in select p.oid::regprocedure as sig from pg_proc p join pg_namespace n on n.oid=p.pronamespace
          where n.nspname='public' and p.proname in ('bb_bar_pubblico','bb_menu_allergeni','bb_alb_annulla','bb_tit_annulla','bb_tit_menu_import','bb_tit_menu_elimina','bb_tit_bar_set','bb_tit_pin_cambia','bb_tit_elimina_demo')
 loop execute format('revoke all on function %s from public',f.sig); execute format('grant execute on function %s to anon',f.sig); end loop; end $$;

-- ===== DATI DIMOSTRATIVI (demo=true, eliminabili dal pannello Impostazioni) =====
do $$
declare s1 uuid; s2 uuid; s3 uuid; d int; v text; q int; fa int; n text; u int;
 nomi text[]:=array['Rossi','Bianchi','Esposito','Russo','Smith','Müller','García','Dupont','Johnson','Romano','Colombo','Schmidt'];
 fx int[]; sid uuid; i int; k int;
begin
 if exists(select 1 from bb_strutture where demo) then return; end if;
 insert into bb_strutture(nome,indirizzo,telefono,pin_hash,fasce,demo) values ('B&B Vesuvio (DEMO)','Via Toledo 100, Napoli','+39 081 000 0001',crypt('1111',gen_salt('bf')),'{3,5,10,12}',true) returning id into s1;
 insert into bb_strutture(nome,indirizzo,telefono,pin_hash,fasce,demo) values ('Hotel Partenope (DEMO)','Via Partenope 20, Napoli','+39 081 000 0002',crypt('2222',gen_salt('bf')),'{4,6,8,10}',true) returning id into s2;
 insert into bb_strutture(nome,indirizzo,telefono,pin_hash,fasce,demo) values ('Casa Mergellina (DEMO)','Riviera di Chiaia 50, Napoli','+39 081 000 0003',crypt('3333',gen_salt('bf')),'{5,7,9,12,15}',true) returning id into s3;
 insert into bb_movimenti(struttura_id,t,tipo,importo,nota) values
  (s1,now()-interval '9 days','ricarica',1000,'Ricarica (demo)'),(s2,now()-interval '9 days','ricarica',1200,'Ricarica (demo)'),(s3,now()-interval '8 days','ricarica',1000,'Ricarica (demo)'),
  (s1,now()-interval '3 days','ricarica',150,'Ricarica (demo)'),(s2,now()-interval '3 days','ricarica',200,'Ricarica (demo)');
 insert into bb_movimenti(struttura_id,tipo,importo,nota,confermato) values (s3,'ricarica',100,'Ricarica richiesta (in attesa di conferma)',false);
 i:=0;
 for d in -6..3 loop
  foreach sid in array array[s1,s2,s3] loop
   for k in 1..(1+ (abs(d)+ (case when sid=s1 then 0 when sid=s2 then 1 else 2 end)) % 3) loop
    i:=i+1;
    select fasce into fx from bb_strutture where id=sid;
    fa := fx[1+(i*7)%array_length(fx,1)];
    q := 1+(i*3)%3;
    n := nomi[1+(i*5)%array_length(nomi,1)]||' – cam. '||(1+i%9);
    u := case when d<0 then (case when i%7=0 then q-1 else q end) when d=0 then (i%2) else 0 end;
    if u>q then u:=q; end if;
    v := upper(substr(md5('demo'||i),1,10));
    insert into bb_vouchers(id,struttura_id,fascia,qta,usate,data,ospite,creato) values (v,sid,fa,q,u,bb_oggi()+d,n,now()+ (d||' days')::interval - interval '2 days');
    insert into bb_movimenti(struttura_id,t,tipo,importo,nota) values (sid,now()+(d||' days')::interval - interval '2 days','prenotazione',-fa*q,q||'× €'||fa||' · '||n);
   end loop;
  end loop;
 end loop;
end $$;
