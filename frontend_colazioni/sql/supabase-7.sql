-- Colazioni B&B · migrazione 7: camere per struttura, composizione dei menù (con allergeni dal menù Ceraldi),
-- richieste dell'ospite (senza ingredienti, allergie, senza glutine) ed extra a carrello. L'ospite NON vede prezzi della colazione.

create table if not exists bb_camere (
  id uuid primary key default gen_random_uuid(),
  struttura_id uuid not null references bb_strutture(id) on delete cascade,
  nome text not null, ospiti int not null default 2 check (ospiti between 1 and 10), ordine int not null default 0);
create table if not exists bb_menu_voci (
  id uuid primary key default gen_random_uuid(),
  fascia int not null references bb_menu(fascia) on delete cascade,
  ordine int not null default 0, nome text not null default '', qta int not null default 1 check (qta between 1 and 10),
  prodotto_id int, ingredienti text[] not null default '{}', allergeni text[] not null default '{}');
create index if not exists bb_camere_s on bb_camere(struttura_id);
create index if not exists bb_voci_f on bb_menu_voci(fascia);
alter table bb_camere enable row level security;
alter table bb_menu_voci enable row level security;
revoke all on bb_camere, bb_menu_voci from anon, authenticated;

alter table bb_vouchers add column if not exists camera text not null default '';
alter table bb_vouchers add column if not exists ospiti int not null default 1;
alter table bb_vouchers add column if not exists richieste jsonb not null default '{}';
alter table bb_vouchers add column if not exists extra jsonb not null default '[]';
alter table bb_vouchers add column if not exists extra_totale numeric(10,2) not null default 0;
alter table bb_vouchers add column if not exists extra_pagato boolean not null default false;
alter table bb_vouchers add column if not exists richieste_agg timestamptz;

-- ===== catalogo dal menù Ceraldi (schema menu), sempre aggiornato =====
create or replace function bb_prezzo(t text) returns numeric language sql immutable set search_path=public as
$$ select case when regexp_replace(coalesce(t,''),'[^0-9,.]','','g') ~ '^[0-9]+([.,][0-9]+)?$' then replace(regexp_replace(t,'[^0-9,.]','','g'),',','.')::numeric else 0 end $$;
revoke execute on function bb_prezzo(text) from public,anon,authenticated;

create or replace function bb_catalogo() returns json language sql security definer set search_path=public,menu as
$$ select coalesce(json_agg(json_build_object('id',p.id,'nome',p.name_it,'desc',coalesce(p.description_it,''),'prezzo',bb_prezzo(p.price),
     'allergeni',coalesce(p.allergens,'{}'),'cat',c.name_it,'sub',coalesce(s.name_it,''),'img',p.image) order by c.id,s.id,p.name_it),'[]'::json)
   from menu.menu_products p join menu.menu_categories c on c.id=p.category_id left join menu.menu_subcategories s on s.id=p.subcategory_id
   where p.visible and c.id in (5170,5181,19632,23110,1000000) and bb_prezzo(p.price)>0 $$;
revoke all on function bb_catalogo() from public; grant execute on function bb_catalogo() to anon;

create or replace function bb_allergeni_elenco() returns json language sql security definer set search_path=public,menu as
$$ select coalesce(json_agg(json_build_object('id',id,'nome',name_it,'icon',icon) order by name_it),'[]'::json) from menu.menu_allergens $$;
revoke all on function bb_allergeni_elenco() from public; grant execute on function bb_allergeni_elenco() to anon;

create or replace function bb_voci_json(f int) returns json language sql security definer set search_path=public,menu as
$$ select coalesce(json_agg(json_build_object('id',v.id,'nome',coalesce(nullif(v.nome,''),p.name_it,''),'qta',v.qta,'prodotto_id',v.prodotto_id,
     'allergeni',case when v.prodotto_id is not null then coalesce(p.allergens,'{}') else v.allergeni end,'ingredienti',v.ingredienti) order by v.ordine,v.id),'[]'::json)
   from bb_menu_voci v left join menu.menu_products p on p.id=v.prodotto_id where v.fascia=f $$;
revoke execute on function bb_voci_json(int) from public,anon,authenticated;

-- ===== pagina ospite: nessun prezzo della colazione =====
create or replace function bb_ospite(vid text) returns json language sql security definer set search_path=public as
$$ select json_build_object('id',v.id,'qta',v.qta,'usate',v.usate,'data',v.data,'ospite',v.ospite,'camera',v.camera,'ospiti',v.ospiti,'annullato',v.annullato,
   'struttura',s.nome,'indirizzo',s.indirizzo,'menu',(select descrizione from bb_menu where fascia=v.fascia),'voci',bb_voci_json(v.fascia),
   'richieste',v.richieste,'extra',v.extra,'extra_totale',v.extra_totale,'extra_pagato',v.extra_pagato,
   'allergeni_elenco',bb_allergeni_elenco(),'bar',bb_bar_pubblico(),'oggi',bb_oggi())
   from bb_vouchers v join bb_strutture s on s.id=v.struttura_id where v.id=upper(trim(vid)) $$;

create or replace function bb_ospite_salva(vid text,prichieste jsonb,pextra jsonb) returns json language plpgsql security definer set search_path=public,menu as $$
declare v bb_vouchers; ex jsonb:='[]'; tot numeric:=0; e jsonb; pr record; n int:=0;
begin
 select * into v from bb_vouchers where id=upper(trim(vid)) for update;
 if not found then raise exception 'Codice non trovato'; end if;
 if v.annullato then raise exception 'Questa colazione è stata annullata'; end if;
 if v.usate>0 or v.data<bb_oggi() then raise exception 'Non è più possibile modificare questa colazione'; end if;
 prichieste := coalesce(prichieste,'{}');
 if jsonb_typeof(prichieste)<>'object' or length(prichieste::text)>6000 then raise exception 'Richiesta non valida o troppo lunga'; end if;
 if v.extra_pagato then
  ex := v.extra; tot := v.extra_totale;
 else
  if jsonb_typeof(coalesce(pextra,'[]'))<>'array' then raise exception 'Ordine non valido'; end if;
  for e in select * from jsonb_array_elements(coalesce(pextra,'[]')) loop
   n := n+1; exit when n>40;
   select p.id, p.name_it nome, bb_prezzo(p.price) pz into pr from menu.menu_products p
     where p.id=(e->>'id')::int and p.visible and p.category_id in (5170,5181,19632,23110,1000000);
   if found and pr.pz>0 and coalesce((e->>'qta')::int,0) between 1 and 20 then
    ex := ex || jsonb_build_object('id',pr.id,'nome',pr.nome,'qta',(e->>'qta')::int,'prezzo',pr.pz);
    tot := tot + pr.pz*(e->>'qta')::int;
   end if;
  end loop;
 end if;
 update bb_vouchers set richieste=prichieste, extra=ex, extra_totale=tot, richieste_agg=now() where id=v.id;
 return bb_ospite(v.id);
end $$;
revoke all on function bb_ospite_salva(text,jsonb,jsonb) from public; grant execute on function bb_ospite_salva(text,jsonb,jsonb) to anon;

-- ===== camere =====
create or replace function bb_camere_set(sid uuid,camere jsonb) returns void language plpgsql security definer set search_path=public as $$
declare c jsonb; i int:=0;
begin
 if jsonb_typeof(camere)<>'array' or jsonb_array_length(camere)>150 then raise exception 'Elenco camere non valido (max 150)'; end if;
 delete from bb_camere where struttura_id=sid;
 for c in select * from jsonb_array_elements(camere) loop
  if coalesce(trim(c->>'nome'),'')='' then continue; end if;
  i:=i+1;
  insert into bb_camere(struttura_id,nome,ospiti,ordine) values (sid,left(trim(c->>'nome'),40),least(10,greatest(1,coalesce((c->>'ospiti')::int,2))),i);
 end loop;
end $$;
revoke execute on function bb_camere_set(uuid,jsonb) from public,anon,authenticated;

create or replace function bb_alb_camere_salva(sid uuid,p text,camere jsonb) returns void language plpgsql security definer set search_path=public,extensions as $$
begin perform bb_check_alb(sid,p); perform bb_camere_set(sid,camere); end $$;
create or replace function bb_tit_camere_salva(p text,sid uuid,camere jsonb) returns void language plpgsql security definer set search_path=public,extensions as $$
begin perform bb_check_tit(p); perform bb_camere_set(sid,camere); end $$;
revoke all on function bb_alb_camere_salva(uuid,text,jsonb), bb_tit_camere_salva(text,uuid,jsonb) from public;
grant execute on function bb_alb_camere_salva(uuid,text,jsonb), bb_tit_camere_salva(text,uuid,jsonb) to anon;

-- ===== creazione colazioni per più camere in un colpo (tutto o niente) =====
create or replace function bb_alb_crea_batch(sid uuid,p text,pfascia int,pperospite int,pdata date,righe jsonb) returns json
language plpgsql security definer set search_path=public,extensions as $$
declare s bb_strutture; r jsonb; vid text; q int; oc int; nome text; cam text; tot numeric:=0; lim text; ora_lim timestamptz; ids jsonb:='[]';
begin
 perform bb_check_alb(sid,p);
 select * into s from bb_strutture where id=sid for update;
 if not (pfascia = any(s.fasce)) then raise exception 'Menu non attivo per questa struttura'; end if;
 if pperospite<1 or pperospite>5 then raise exception 'Colazioni a testa: da 1 a 5'; end if;
 if pdata<bb_oggi() then raise exception 'Data nel passato'; end if;
 if pdata>bb_oggi()+bb_cfg('anticipo_max_giorni','60')::int then raise exception 'Puoi prenotare al massimo % giorni prima',bb_cfg('anticipo_max_giorni','60'); end if;
 lim := bb_cfg('ordini_limite_ora','');
 if lim<>'' then
  ora_lim := ((pdata-1)::text||' '||lim)::timestamp at time zone 'Europe/Rome';
  if now()>ora_lim then raise exception 'Le colazioni per il % vanno ordinate entro le % del giorno prima',to_char(pdata,'DD/MM'),lim; end if;
 end if;
 if jsonb_typeof(righe)<>'array' or jsonb_array_length(righe)=0 or jsonb_array_length(righe)>150 then raise exception 'Seleziona almeno una camera'; end if;
 for r in select * from jsonb_array_elements(righe) loop
  oc := coalesce((r->>'ospiti')::int,1);
  if oc<1 or oc>10 then raise exception 'Ospiti per camera: da 1 a 10'; end if;
  tot := tot + pfascia*oc*pperospite;
 end loop;
 if bb_saldo(sid)<tot then raise exception 'Saldo insufficiente: servono % €, disponibili % €',tot,bb_saldo(sid); end if;
 for r in select * from jsonb_array_elements(righe) loop
  oc := (r->>'ospiti')::int; q := oc*pperospite;
  cam := left(trim(coalesce(r->>'camera','')),40);
  nome := coalesce(nullif(left(trim(coalesce(r->>'nome','')),60),''),nullif(cam,''),'Ospite');
  vid := upper(substr(encode(gen_random_bytes(8),'hex'),1,10));
  insert into bb_vouchers(id,struttura_id,fascia,qta,data,ospite,camera,ospiti) values (vid,sid,pfascia,q,pdata,nome,cam,oc);
  insert into bb_movimenti(struttura_id,tipo,importo,nota) values (sid,'prenotazione',-pfascia*q,coalesce(nullif(cam,'')||' · ','')||q||'× €'||pfascia||' · '||nome);
  ids := ids || jsonb_build_object('id',vid,'camera',cam,'nome',nome);
 end loop;
 return json_build_object('creati',ids,'totale',tot);
end $$;
revoke all on function bb_alb_crea_batch(uuid,text,int,int,date,jsonb) from public; grant execute on function bb_alb_crea_batch(uuid,text,int,int,date,jsonb) to anon;

-- ===== composizione dei menù (titolare) =====
create or replace function bb_tit_voci_salva(p text,pfascia int,righe jsonb) returns void language plpgsql security definer set search_path=public,menu,extensions as $$
declare r jsonb; i int:=0; nomi text[]:='{}'; nm text; pid int;
begin
 perform bb_check_tit(p);
 if not exists(select 1 from bb_menu where fascia=pfascia) then raise exception 'Fascia inesistente'; end if;
 if jsonb_typeof(righe)<>'array' or jsonb_array_length(righe)>30 then raise exception 'Composizione non valida (max 30 voci)'; end if;
 delete from bb_menu_voci where fascia=pfascia;
 for r in select * from jsonb_array_elements(righe) loop
  i:=i+1; pid := nullif(r->>'prodotto_id','')::int;
  nm := left(trim(coalesce(r->>'nome','')),80);
  if pid is not null then
   if not exists(select 1 from menu.menu_products where id=pid) then raise exception 'Prodotto % non trovato',pid; end if;
   if nm='' then select name_it into nm from menu.menu_products where id=pid; end if;
  end if;
  if nm='' then raise exception 'Ogni voce deve avere un nome'; end if;
  insert into bb_menu_voci(fascia,ordine,nome,qta,prodotto_id,ingredienti,allergeni) values
   (pfascia,i,nm,least(10,greatest(1,coalesce((r->>'qta')::int,1))),pid,
    coalesce(array(select left(trim(x),40) from jsonb_array_elements_text(coalesce(r->'ingredienti','[]')) x where trim(x)<>''),'{}'),
    coalesce(array(select a.id from jsonb_array_elements_text(coalesce(r->'allergeni','[]')) x join menu.menu_allergens a on a.id=x),'{}'));
  nomi := nomi || (case when coalesce((r->>'qta')::int,1)>1 then (r->>'qta')||'× ' else '' end)||nm;
 end loop;
 if array_length(nomi,1)>0 then update bb_menu set descrizione=array_to_string(nomi,' + ') where fascia=pfascia; end if;
end $$;
revoke all on function bb_tit_voci_salva(text,int,jsonb) from public; grant execute on function bb_tit_voci_salva(text,int,jsonb) to anon;

create or replace function bb_tit_extra_incassato(p text,vid text) returns void language plpgsql security definer set search_path=public,extensions as $$
begin perform bb_check_tit(p); update bb_vouchers set extra_pagato=true where id=upper(trim(vid)) and extra_totale>0; end $$;
revoke all on function bb_tit_extra_incassato(text,text) from public; grant execute on function bb_tit_extra_incassato(text,text) to anon;

-- ===== stato albergatore / titolare / riscatto: con camere, richieste ed extra =====
create or replace function bb_alb_stato(sid uuid,p text) returns json language plpgsql security definer set search_path=public,extensions as $$
begin
 perform bb_check_alb(sid,p);
 perform bb_sumup_verifica(sid);
 return json_build_object(
  'struttura',(select json_build_object('id',id,'nome',nome,'indirizzo',indirizzo,'fasce',fasce,'saldo',bb_saldo(id)) from bb_strutture where id=sid),
  'oggi',bb_oggi(),'bar',bb_bar_pubblico(),'menu',bb_menu_pubblico(),'sumup',bb_sumup_attivo(),
  'config',json_build_object('ricarica_min',bb_cfg('ricarica_min','5')::numeric,'ricarica_max',bb_cfg('ricarica_max','2000')::numeric,'anticipo',bb_cfg('anticipo_max_giorni','60')::int,'limite_ora',bb_cfg('ordini_limite_ora',''),'msg',bb_cfg('msg_ospite','{link}')),
  'camere',(select coalesce(json_agg(json_build_object('id',c.id,'nome',c.nome,'ospiti',c.ospiti) order by c.ordine),'[]'::json) from bb_camere c where c.struttura_id=sid),
  'movimenti',(select coalesce(json_agg(m order by m.t desc),'[]'::json) from (select id,t,tipo,importo,nota,confermato,sumup_url from bb_movimenti where struttura_id=sid) m),
  'vouchers',(select coalesce(json_agg(v order by v.creato desc),'[]'::json) from (select id,fascia,qta,usate,data,ospite,camera,ospiti,creato,annullato,(richieste<>'{}'::jsonb) has_richieste,extra_totale,extra_pagato from bb_vouchers where struttura_id=sid) v));
end $$;

create or replace function bb_tit_stato(p text) returns json language plpgsql security definer set search_path=public,extensions as $$
begin
 perform bb_check_tit(p);
 return json_build_object(
  'oggi',bb_oggi(),'bar',bb_bar_pubblico(),'menu',bb_menu_pubblico(),'allergeni',bb_menu_allergeni(),'sumup',bb_sumup_attivo(),
  'config',(select coalesce(json_object_agg(k,v),'{}'::json) from bb_config where k<>'tit_pin'),
  'voci',(select coalesce(json_object_agg(fascia::text,bb_voci_json(fascia)),'{}'::json) from bb_menu),
  'allergeni_elenco',bb_allergeni_elenco(),
  'camere',(select coalesce(json_object_agg(sid::text,cj),'{}'::json) from (select c.struttura_id sid, json_agg(json_build_object('nome',c.nome,'ospiti',c.ospiti) order by c.ordine) cj from bb_camere c group by c.struttura_id) x),
  'strutture',(select coalesce(json_agg(x order by x.nome),'[]'::json) from (select id,nome,indirizzo,telefono,demo,fasce,bb_saldo(id) saldo from bb_strutture) x),
  'attesa',(select coalesce(json_agg(x order by x.t),'[]'::json) from (select m.id,m.t,m.importo,s.nome from bb_movimenti m join bb_strutture s on s.id=m.struttura_id where not m.confermato and m.sumup_id is null) x),
  'movimenti',(select coalesce(json_agg(x order by x.t desc),'[]'::json) from (select m.id,m.struttura_id,s.nome struttura,m.t,m.tipo,m.importo,m.nota,m.confermato from bb_movimenti m join bb_strutture s on s.id=m.struttura_id) x),
  'vouchers',(select coalesce(json_agg(x order by x.creato desc),'[]'::json) from (select v.id,v.struttura_id,s.nome struttura,v.fascia,v.qta,v.usate,v.data,v.ospite,v.camera,v.ospiti,v.creato,v.annullato,v.richieste,v.extra,v.extra_totale,v.extra_pagato from bb_vouchers v join bb_strutture s on s.id=v.struttura_id) x));
end $$;

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
 return json_build_object('ok',ok,'msg',msg,'voucher',json_build_object('id',v.id,'fascia',v.fascia,'qta',v.qta,'usate',v.usate,'ospite',v.ospite,'camera',v.camera,'ospiti',v.ospiti,'struttura',s,
   'menu',(select descrizione from bb_menu where fascia=v.fascia),'voci',bb_voci_json(v.fascia),'richieste',v.richieste,'extra',v.extra,'extra_totale',v.extra_totale,'extra_pagato',v.extra_pagato));
end $$;

-- ===== dati dimostrativi: composizioni e camere =====
insert into bb_menu_voci(fascia,ordine,nome,qta,prodotto_id,ingredienti,allergeni)
select * from (values
 (3,1,'',1,153797,'{}'::text[],'{}'::text[]),(3,2,'',1,153754,'{}','{}'),
 (4,1,'',1,153797,'{}','{}'),(4,2,'',1,153754,'{}','{}'),(4,3,'',1,153895,'{}','{}'),
 (5,1,'',1,153797,'{}','{}'),(5,2,'',1,153883,'{}','{}'),(5,3,'',1,153754,'{}','{}'),
 (6,1,'',1,153797,'{}','{}'),(6,2,'',1,153883,'{}','{}'),(6,3,'',1,153754,'{}','{}'),(6,4,'',1,153926,'{}','{}'),
 (7,1,'',2,153797,'{}','{}'),(7,2,'',1,153754,'{}','{}'),(7,3,'',1,153926,'{}','{}'),
 (8,1,'',1,153797,'{}','{}'),(8,2,'',1,153883,'{}','{}'),(8,3,'',1,153754,'{}','{}'),(8,4,'',1,155356,'{}','{}'),
 (9,1,'',1,153797,'{}','{}'),(9,2,'',1,153868,'{}','{}'),(9,3,'',1,153888,'{}','{}'),(9,4,'',1,153754,'{}','{}'),(9,5,'',1,155356,'{}','{}'),
 (10,1,'Pizzetta',1,null,'{}','{gluten,milk}'),(10,2,'Bibita',1,null,'{}','{}'),
 (11,1,'Pizzetta',1,null,'{}','{gluten,milk}'),(11,2,'',1,153868,'{}','{}'),(11,3,'Bibita',1,null,'{}','{}'),
 (12,1,'Full English breakfast',1,null,'{uova,bacon,salsiccia,fagioli,funghi,pomodoro grigliato,toast}','{gluten,eggs}'),(12,2,'',1,153754,'{}','{}'),
 (15,1,'Full English breakfast',1,null,'{uova,bacon,salsiccia,fagioli,funghi,pomodoro grigliato,toast}','{gluten,eggs}'),(15,2,'',1,155356,'{}','{}'),(15,3,'',1,153868,'{}','{}')
) v(fascia,ordine,nome,qta,prodotto_id,ingredienti,allergeni)
where not exists (select 1 from bb_menu_voci) and exists (select 1 from bb_menu m where m.fascia=v.fascia);

insert into bb_camere(struttura_id,nome,ospiti,ordine)
select s.id, c.nome, c.ospiti, c.ordine from bb_strutture s
join (values ('B&B Vesuvio (DEMO)','Camera 1',2,1),('B&B Vesuvio (DEMO)','Camera 2',2,2),('B&B Vesuvio (DEMO)','Camera 3',3,3),('B&B Vesuvio (DEMO)','Camera 4',2,4),('B&B Vesuvio (DEMO)','Camera 5',1,5),('B&B Vesuvio (DEMO)','Camera 6',4,6),
 ('Hotel Partenope (DEMO)','Suite Vesuvio',2,1),('Hotel Partenope (DEMO)','Suite Capri',2,2),('Hotel Partenope (DEMO)','Suite Procida',3,3),('Hotel Partenope (DEMO)','Camera 101',2,4),('Hotel Partenope (DEMO)','Camera 102',2,5),
 ('Casa Mergellina (DEMO)','Stanza Ischia',2,1),('Casa Mergellina (DEMO)','Stanza Sorrento',2,2),('Casa Mergellina (DEMO)','Stanza Amalfi',3,3)) c(sn,nome,ospiti,ordine) on c.sn=s.nome
where s.demo and not exists (select 1 from bb_camere x where x.struttura_id=s.id);
