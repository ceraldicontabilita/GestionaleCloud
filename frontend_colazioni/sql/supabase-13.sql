-- Colazioni B&B · migrazione 13: colazioni personalizzate per hotel (nome, prezzo, contenuto) e soggiorni su più giorni

create table if not exists bb_colazioni (
  id uuid primary key default gen_random_uuid(),
  struttura_id uuid not null references bb_strutture(id) on delete cascade,
  nome text not null, prezzo numeric(8,2) not null check (prezzo>=0 and prezzo<=200),
  descrizione text not null default '', ordine int not null default 0, attiva boolean not null default true);
create table if not exists bb_colazione_voci (
  id uuid primary key default gen_random_uuid(),
  colazione_id uuid not null references bb_colazioni(id) on delete cascade,
  ordine int not null default 0, nome text not null default '', qta int not null default 1 check (qta between 1 and 10),
  prodotto_id int, ingredienti text[] not null default '{}', allergeni text[] not null default '{}');
create index if not exists bb_colazioni_s on bb_colazioni(struttura_id);
create index if not exists bb_colazione_voci_c on bb_colazione_voci(colazione_id);
alter table bb_colazioni enable row level security;
alter table bb_colazione_voci enable row level security;
revoke all on bb_colazioni, bb_colazione_voci from anon, authenticated;

alter table bb_vouchers alter column fascia type numeric(8,2);
alter table bb_vouchers add column if not exists colazione_id uuid references bb_colazioni(id) on delete set null;
alter table bb_vouchers add column if not exists colazione_nome text not null default '';
alter table bb_vouchers add column if not exists data_fine date;
update bb_vouchers set data_fine=data where data_fine is null;
alter table bb_vouchers alter column data_fine set not null;

-- le colazioni già configurate per fascia diventano colazioni dell'hotel
insert into bb_colazioni(struttura_id,nome,prezzo,descrizione,ordine)
select s.id,'Colazione da €'||f::text,f,coalesce((select descrizione from bb_menu where fascia=f),''),row_number() over (partition by s.id order by f)
from bb_strutture s cross join lateral unnest(s.fasce) f
where not exists(select 1 from bb_colazioni c where c.struttura_id=s.id);
insert into bb_colazione_voci(colazione_id,ordine,nome,qta,prodotto_id,ingredienti,allergeni)
select c.id,v.ordine,v.nome,v.qta,v.prodotto_id,v.ingredienti,v.allergeni from bb_colazioni c join bb_menu_voci v on v.fascia=c.prezzo::int
where not exists(select 1 from bb_colazione_voci x where x.colazione_id=c.id);

create or replace function bb_voci_col_json(cid uuid) returns json language sql security definer set search_path=public as
$$ select coalesce(json_agg(json_build_object('id',v.id,'nome',coalesce(nullif(v.nome,''),p.nome,''),'qta',v.qta,'prodotto_id',v.prodotto_id,
     'allergeni',case when v.prodotto_id is not null then coalesce(p.allergeni,'{}') else v.allergeni end,'ingredienti',v.ingredienti) order by v.ordine,v.id),'[]'::json)
   from bb_colazione_voci v left join bb_prodotti p on p.id=v.prodotto_id where v.colazione_id=cid $$;
create or replace function bb_colazioni_json(sid uuid,solo_attive boolean) returns json language sql security definer set search_path=public as
$$ select coalesce(json_agg(json_build_object('id',c.id,'nome',c.nome,'prezzo',c.prezzo,'descrizione',c.descrizione,'attiva',c.attiva,'voci',bb_voci_col_json(c.id)) order by c.ordine,c.nome),'[]'::json)
   from bb_colazioni c where c.struttura_id=sid and (not solo_attive or c.attiva) $$;
revoke execute on function bb_voci_col_json(uuid), bb_colazioni_json(uuid,boolean) from public,anon,authenticated;

create or replace function bb_tit_colazioni_salva(p text,sid uuid,righe jsonb) returns json language plpgsql security definer set search_path=public,extensions as $$
declare r jsonb; v jsonb; cid uuid; i int:=0; j int; keep uuid[]:='{}'; nm text; pr numeric; pid int; vn text;
begin
 perform bb_check_tit(p);
 if not exists(select 1 from bb_strutture where id=sid) then raise exception 'Struttura non trovata'; end if;
 if jsonb_typeof(righe)<>'array' or jsonb_array_length(righe)>30 then raise exception 'Elenco colazioni non valido (max 30)'; end if;
 for r in select * from jsonb_array_elements(righe) loop
  i:=i+1;
  nm := left(trim(coalesce(r->>'nome','')),60);
  if nm='' then raise exception 'Ogni colazione deve avere un nome'; end if;
  pr := coalesce((r->>'prezzo')::numeric,-1);
  if pr<0 or pr>200 then raise exception 'Prezzo non valido per "%"',nm; end if;
  cid := nullif(r->>'id','')::uuid;
  if cid is not null and exists(select 1 from bb_colazioni where id=cid and struttura_id=sid) then
   update bb_colazioni set nome=nm,prezzo=pr,descrizione=left(coalesce(r->>'descrizione',''),200),ordine=i,attiva=coalesce((r->>'attiva')::boolean,true) where id=cid;
  else
   insert into bb_colazioni(struttura_id,nome,prezzo,descrizione,ordine,attiva) values (sid,nm,pr,left(coalesce(r->>'descrizione',''),200),i,coalesce((r->>'attiva')::boolean,true)) returning id into cid;
  end if;
  keep := keep||cid;
  delete from bb_colazione_voci where colazione_id=cid;
  if jsonb_typeof(r->'voci')='array' then
   if jsonb_array_length(r->'voci')>30 then raise exception 'Troppe voci in "%"',nm; end if;
   j:=0;
   for v in select * from jsonb_array_elements(r->'voci') loop
    j:=j+1; pid := nullif(v->>'prodotto_id','')::int; vn := left(trim(coalesce(v->>'nome','')),80);
    if pid is not null then
     if not exists(select 1 from bb_prodotti where id=pid) then raise exception 'Prodotto % non trovato',pid; end if;
     if vn='' then select nome into vn from bb_prodotti where id=pid; end if;
    end if;
    if vn='' then raise exception 'Ogni voce deve avere un nome (in "%")',nm; end if;
    insert into bb_colazione_voci(colazione_id,ordine,nome,qta,prodotto_id,ingredienti,allergeni) values
     (cid,j,vn,least(10,greatest(1,coalesce((v->>'qta')::int,1))),pid,
      coalesce(array(select left(trim(x),40) from jsonb_array_elements_text(coalesce(v->'ingredienti','[]')) x where trim(x)<>''),'{}'),
      coalesce(array(select a.id from jsonb_array_elements_text(coalesce(v->'allergeni','[]')) x join menu.menu_allergens a on a.id=x),'{}'));
   end loop;
  end if;
 end loop;
 delete from bb_colazioni c where c.struttura_id=sid and c.id<>all(keep) and not exists(select 1 from bb_vouchers x where x.colazione_id=c.id);
 update bb_colazioni set attiva=false where struttura_id=sid and id<>all(keep);
 return bb_colazioni_json(sid,false);
end $$;
revoke all on function bb_tit_colazioni_salva(text,uuid,jsonb) from public; grant execute on function bb_tit_colazioni_salva(text,uuid,jsonb) to anon;

-- un'unica pagina per l'albergatore: camere, ospiti, giorni e tipo di colazione
create or replace function bb_alb_crea_soggiorni(sid uuid,p text,righe jsonb) returns json language plpgsql security definer set search_path=public,extensions as $$
declare s bb_strutture; r jsonb; vid text; oc int; cam text; dal date; al date; gg int; c bb_colazioni; tot numeric:=0; ids jsonb:='[]'; lim text; ora_lim timestamptz; mx int;
begin
 perform bb_check_alb(sid,p);
 select * into s from bb_strutture where id=sid for update;
 if jsonb_typeof(righe)<>'array' or jsonb_array_length(righe)=0 or jsonb_array_length(righe)>150 then raise exception 'Seleziona almeno una camera'; end if;
 lim := bb_cfg('ordini_limite_ora',''); mx := bb_cfg('anticipo_max_giorni','60')::int;
 for r in select * from jsonb_array_elements(righe) loop
  oc := coalesce((r->>'ospiti')::int,1);
  if oc<1 or oc>10 then raise exception 'Ospiti per camera: da 1 a 10'; end if;
  dal := (r->>'dal')::date; al := coalesce((r->>'al')::date,dal);
  if dal<bb_oggi() then raise exception 'La data di arrivo è nel passato'; end if;
  if al<dal then raise exception 'La data di partenza è prima dell''arrivo'; end if;
  gg := al-dal+1;
  if gg>31 then raise exception 'Soggiorno massimo 31 giorni'; end if;
  if al>bb_oggi()+mx then raise exception 'Puoi prenotare al massimo % giorni prima',mx; end if;
  if lim<>'' then
   ora_lim := ((dal-1)::text||' '||lim)::timestamp at time zone 'Europe/Rome';
   if now()>ora_lim then raise exception 'Le colazioni dal % vanno ordinate entro le % del giorno prima',to_char(dal,'DD/MM'),lim; end if;
  end if;
  select * into c from bb_colazioni where id=nullif(r->>'colazione_id','')::uuid and struttura_id=sid and attiva;
  if not found then raise exception 'Scegli una colazione disponibile per ogni camera'; end if;
  tot := tot + c.prezzo*oc*gg;
 end loop;
 if bb_saldo(sid)<tot then raise exception 'Saldo insufficiente: servono % €, disponibili % €',tot,bb_saldo(sid); end if;
 for r in select * from jsonb_array_elements(righe) loop
  oc := (r->>'ospiti')::int; dal := (r->>'dal')::date; al := coalesce((r->>'al')::date,dal); gg := al-dal+1;
  select * into c from bb_colazioni where id=(r->>'colazione_id')::uuid;
  cam := left(trim(coalesce(r->>'camera','')),40);
  vid := upper(substr(encode(gen_random_bytes(8),'hex'),1,10));
  insert into bb_vouchers(id,struttura_id,fascia,qta,data,data_fine,ospite,camera,ospiti,colazione_id,colazione_nome)
   values (vid,sid,c.prezzo,oc*gg,dal,al,coalesce(nullif(cam,''),'Ospite'),cam,oc,c.id,c.nome);
  insert into bb_movimenti(struttura_id,tipo,importo,nota) values (sid,'prenotazione',-c.prezzo*oc*gg,
   coalesce(nullif(cam,'')||' · ','')||oc||' ospiti × '||gg||' giorni · '||c.nome);
  ids := ids || jsonb_build_object('id',vid,'camera',cam,'nome',coalesce(nullif(cam,''),'Ospite'));
 end loop;
 return json_build_object('creati',ids,'totale',tot);
end $$;
revoke all on function bb_alb_crea_soggiorni(uuid,text,jsonb) from public; grant execute on function bb_alb_crea_soggiorni(uuid,text,jsonb) to anon;

-- pagina ospite
create or replace function bb_ospite(vid text) returns json language sql security definer set search_path=public as
$$ select json_build_object('id',v.id,'qta',v.qta,'usate',v.usate,'data',v.data,'data_fine',v.data_fine,'ospite',v.ospite,'camera',v.camera,'ospiti',v.ospiti,'annullato',v.annullato,
   'struttura',s.nome,'indirizzo',s.indirizzo,'sfondo',s.sfondo,'benvenuto',s.benvenuto,'colazione',v.colazione_nome,
   'menu',coalesce((select descrizione from bb_colazioni where id=v.colazione_id),(select descrizione from bb_menu where fascia=v.fascia)),
   'voci',case when v.colazione_id is not null then bb_voci_col_json(v.colazione_id) else bb_voci_json(v.fascia::int) end,
   'richieste',v.richieste,'extra',v.extra,'extra_totale',v.extra_totale,'extra_pagato',v.extra_pagato,'glutine',bb_glutine_pubblico(),
   'allergeni_elenco',bb_allergeni_elenco(),'bar',bb_bar_pubblico(),'oggi',bb_oggi())
   from bb_vouchers v join bb_strutture s on s.id=v.struttura_id where v.id=upper(trim(vid)) $$;

create or replace function bb_ospite_salva(vid text,prichieste jsonb,pextra jsonb) returns json language plpgsql security definer set search_path=public as $$
declare v bb_vouchers; ex jsonb:='[]'; tot numeric:=0; e jsonb; pr record; g record; n int:=0; nuovi text[]; vecchi text[];
begin
 select * into v from bb_vouchers where id=upper(trim(vid)) for update;
 if not found then raise exception 'Codice non trovato'; end if;
 if v.annullato then raise exception 'Questa colazione è stata annullata'; end if;
 if v.data_fine<bb_oggi() then raise exception 'Il soggiorno è terminato: non è più possibile modificare'; end if;
 prichieste := coalesce(prichieste,'{}');
 if jsonb_typeof(prichieste)<>'object' or length(prichieste::text)>6000 then raise exception 'Richiesta non valida o troppo lunga'; end if;
 select coalesce(array_agg(x->>'variante' order by x->>'variante'),'{}') into nuovi from jsonb_array_elements(coalesce(prichieste->'modifiche','[]')) x
   where x->>'tipo'='senza_glutine' and coalesce(x->>'variante','')<>'';
 if v.extra_pagato then
  select coalesce(array_agg(x->>'variante' order by x->>'variante'),'{}') into vecchi from jsonb_array_elements(coalesce(v.richieste->'modifiche','[]')) x
   where x->>'tipo'='senza_glutine' and coalesce(x->>'variante','')<>'';
  if nuovi is distinct from vecchi then raise exception 'Hai già pagato gli extra: per cambiare le versioni senza glutine rivolgiti al bar'; end if;
  ex := v.extra; tot := v.extra_totale;
 else
  if jsonb_typeof(coalesce(pextra,'[]'))<>'array' then raise exception 'Ordine non valido'; end if;
  for e in select * from jsonb_array_elements(coalesce(pextra,'[]')) loop
   n := n+1; exit when n>40;
   select p.id, p.nome, p.prezzo pz into pr from bb_prodotti p join bb_prod_cat c on c.id=p.cat_id
     where p.id=(e->>'id')::int and p.visibile and c.attivo and c.ospiti;
   if found and pr.pz>0 and coalesce((e->>'qta')::int,0) between 1 and 20 then
    ex := ex || jsonb_build_object('id',pr.id,'nome',pr.nome,'qta',(e->>'qta')::int,'prezzo',pr.pz);
    tot := tot + pr.pz*(e->>'qta')::int;
   end if;
  end loop;
  for e in select * from jsonb_array_elements(coalesce(prichieste->'modifiche','[]')) loop
   if e->>'tipo'='senza_glutine' and coalesce(e->>'variante','')<>'' then
    select nome, differenza into g from bb_senza_glutine where id=(e->>'variante')::uuid;
    if found then
     ex := ex || jsonb_build_object('glutine',true,'nome','Senza glutine: '||g.nome,'qta',1,'prezzo',g.differenza);
     tot := tot + g.differenza;
    end if;
   end if;
  end loop;
 end if;
 update bb_vouchers set richieste=prichieste, extra=ex, extra_totale=tot, richieste_agg=now() where id=v.id;
 return bb_ospite(v.id);
end $$;

-- scanner: un soggiorno vale per più giorni, ma al massimo una colazione a persona al giorno
create or replace function bb_tit_riscatta(p text,vid text) returns json language plpgsql security definer set search_path=public,extensions as $$
declare v bb_vouchers; s text; msg text; ok boolean:=false; oggi_n int;
begin
 perform bb_check_tit(p);
 select * into v from bb_vouchers where id=upper(trim(vid)) for update;
 if not found then return json_build_object('ok',false,'msg','Codice non trovato'); end if;
 select count(*) into oggi_n from unnest(v.riscatti) t where (t at time zone 'Europe/Rome')::date=bb_oggi();
 if v.annullato then msg:='Voucher annullato';
 elsif v.usate>=v.qta then msg:='Già utilizzato interamente';
 elsif bb_oggi()>v.data_fine then msg:='Voucher scaduto ('||to_char(v.data_fine,'DD/MM')||')';
 elsif bb_oggi()<v.data then msg:='Valido dal '||to_char(v.data,'DD/MM');
 elsif oggi_n>=v.ospiti then msg:='Oggi le '||v.ospiti||' colazioni di questa camera sono già state consegnate';
 else update bb_vouchers set usate=usate+1, riscatti=riscatti||now() where id=v.id returning * into v; oggi_n:=oggi_n+1; ok:=true; msg:='Colazione consegnata ('||oggi_n||' di '||v.ospiti||' oggi)'; end if;
 select nome into s from bb_strutture where id=v.struttura_id;
 return json_build_object('ok',ok,'msg',msg,'voucher',json_build_object('id',v.id,'fascia',v.fascia,'qta',v.qta,'usate',v.usate,'ospite',v.ospite,'camera',v.camera,'ospiti',v.ospiti,'struttura',s,
   'data',v.data,'data_fine',v.data_fine,'colazione',v.colazione_nome,'menu',coalesce((select descrizione from bb_colazioni where id=v.colazione_id),(select descrizione from bb_menu where fascia=v.fascia)),
   'voci',case when v.colazione_id is not null then bb_voci_col_json(v.colazione_id) else bb_voci_json(v.fascia::int) end,
   'richieste',v.richieste,'extra',v.extra,'extra_totale',v.extra_totale,'extra_pagato',v.extra_pagato));
end $$;

create or replace function bb_alb_stato(sid uuid,p text) returns json language plpgsql security definer set search_path=public,extensions as $$
begin
 perform bb_check_alb(sid,p);
 perform bb_sumup_verifica(sid);
 return json_build_object(
  'struttura',(select json_build_object('id',id,'nome',nome,'indirizzo',indirizzo,'telefono',telefono,'benvenuto',benvenuto,'accesso',accesso,'saldo',bb_saldo(id)) from bb_strutture where id=sid),
  'oggi',bb_oggi(),'bar',bb_bar_pubblico(),'sumup',bb_sumup_attivo(),
  'config',json_build_object('ricarica_min',bb_cfg('ricarica_min','5')::numeric,'ricarica_max',bb_cfg('ricarica_max','2000')::numeric,'anticipo',bb_cfg('anticipo_max_giorni','60')::int,'limite_ora',bb_cfg('ordini_limite_ora',''),'msg',bb_cfg('msg_ospite','{link}')),
  'colazioni',bb_colazioni_json(sid,true),
  'camere',(select coalesce(json_agg(json_build_object('id',c.id,'nome',c.nome,'ospiti',c.ospiti) order by c.ordine),'[]'::json) from bb_camere c where c.struttura_id=sid),
  'movimenti',(select coalesce(json_agg(m order by m.t desc),'[]'::json) from (select id,t,tipo,importo,nota,confermato,sumup_url from bb_movimenti where struttura_id=sid) m),
  'vouchers',(select coalesce(json_agg(v order by v.creato desc),'[]'::json) from (select id,fascia,qta,usate,data,data_fine,ospite,camera,ospiti,colazione_nome,creato,annullato,(richieste<>'{}'::jsonb) has_richieste,extra_totale,extra_pagato from bb_vouchers where struttura_id=sid) v));
end $$;

create or replace function bb_tit_stato(p text) returns json language plpgsql security definer set search_path=public,extensions as $$
begin
 perform bb_check_tit(p);
 return json_build_object(
  'oggi',bb_oggi(),'bar',bb_bar_pubblico(),'menu',bb_menu_pubblico(),'allergeni',bb_menu_allergeni(),'sumup',bb_sumup_attivo(),'pin_off',bb_pin_stato(),
  'config',(select coalesce(json_object_agg(k,v),'{}'::json) from bb_config where k<>'tit_pin'),
  'voci',(select coalesce(json_object_agg(fascia::text,bb_voci_json(fascia)),'{}'::json) from bb_menu),
  'colazioni',(select coalesce(json_object_agg(id::text,bb_colazioni_json(id,false)),'{}'::json) from bb_strutture),
  'allergeni_elenco',bb_allergeni_elenco(),
  'camere',(select coalesce(json_object_agg(sid::text,cj),'{}'::json) from (select c.struttura_id sid, json_agg(json_build_object('nome',c.nome,'ospiti',c.ospiti) order by c.ordine) cj from bb_camere c group by c.struttura_id) x),
  'strutture',(select coalesce(json_agg(x order by x.nome),'[]'::json) from (select id,nome,indirizzo,telefono,email,demo,accesso,invito_token,(pin_hash is not null) attivo,bb_saldo(id) saldo from bb_strutture) x),
  'attesa',(select coalesce(json_agg(x order by x.t),'[]'::json) from (select m.id,m.t,m.importo,s.nome from bb_movimenti m join bb_strutture s on s.id=m.struttura_id where not m.confermato and m.sumup_id is null) x),
  'movimenti',(select coalesce(json_agg(x order by x.t desc),'[]'::json) from (select m.id,m.struttura_id,s.nome struttura,m.t,m.tipo,m.importo,m.nota,m.confermato from bb_movimenti m join bb_strutture s on s.id=m.struttura_id) x),
  'vouchers',(select coalesce(json_agg(x order by x.creato desc),'[]'::json) from (select v.id,v.struttura_id,s.nome struttura,v.fascia,v.qta,v.usate,v.data,v.data_fine,v.ospite,v.camera,v.ospiti,v.colazione_id,v.colazione_nome,v.creato,v.annullato,v.richieste,v.extra,v.extra_totale,v.extra_pagato,
     (select coalesce(json_agg((t at time zone 'Europe/Rome')::date),'[]'::json) from unnest(v.riscatti) t) riscatti
     from bb_vouchers v join bb_strutture s on s.id=v.struttura_id) x));
end $$;
