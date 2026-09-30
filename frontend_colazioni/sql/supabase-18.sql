-- v18: colazioni standard del back office (struttura_id null) importabili in ogni struttura
alter table bb_colazioni alter column struttura_id drop not null;

create or replace function bb_colazioni_json(sid uuid, solo_attive boolean) returns json language sql security definer set search_path=public as $$
 select coalesce(json_agg(json_build_object('id',c.id,'nome',c.nome,'prezzo',c.prezzo,'descrizione',c.descrizione,'attiva',c.attiva,
   'voci',case when solo_attive then bb_voci_col_json(c.id) else bb_voci_col_json_p(c.id) end) order by c.ordine,c.nome),'[]'::json)
   from bb_colazioni c where c.struttura_id is not distinct from sid and (not solo_attive or c.attiva) $$;

create or replace function bb_tit_colazioni_salva(p text, sid uuid, righe jsonb) returns json language plpgsql security definer set search_path=public,extensions as $$
declare r jsonb; v jsonb; cid uuid; i int:=0; j int; keep uuid[]:='{}'; nm text; pr numeric; pid int; vn text; vp numeric;
begin
 perform bb_check_tit(p);
 if sid is not null and not exists(select 1 from bb_strutture where id=sid) then raise exception 'Struttura non trovata'; end if;
 if jsonb_typeof(righe)<>'array' or jsonb_array_length(righe)>30 then raise exception 'Elenco colazioni non valido (max 30)'; end if;
 for r in select * from jsonb_array_elements(righe) loop
  i:=i+1;
  nm := left(trim(coalesce(r->>'nome','')),60);
  if nm='' then raise exception 'Ogni colazione deve avere un nome'; end if;
  pr := coalesce((r->>'prezzo')::numeric,-1);
  if pr<0 or pr>200 then raise exception 'Prezzo non valido per "%"',nm; end if;
  cid := nullif(r->>'id','')::uuid;
  if cid is not null and exists(select 1 from bb_colazioni where id=cid and struttura_id is not distinct from sid) then
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
    vp := nullif(v->>'prezzo','')::numeric;
    if vp is not null and (vp<0 or vp>200) then raise exception 'Prezzo non valido per la voce "%"',vn; end if;
    if pid is not null then
     if not exists(select 1 from bb_prodotti where id=pid) then raise exception 'Prodotto % non trovato',pid; end if;
     if vn='' then select nome into vn from bb_prodotti where id=pid; end if;
    end if;
    if vn='' then raise exception 'Ogni voce deve avere un nome (in "%")',nm; end if;
    insert into bb_colazione_voci(colazione_id,ordine,nome,qta,prodotto_id,prezzo,ingredienti,allergeni) values
     (cid,j,vn,least(10,greatest(1,coalesce((v->>'qta')::int,1))),pid,vp,
      coalesce(array(select left(trim(x),40) from jsonb_array_elements_text(coalesce(v->'ingredienti','[]')) x where trim(x)<>''),'{}'),
      coalesce(array(select a.id from jsonb_array_elements_text(coalesce(v->'allergeni','[]')) x join menu.menu_allergens a on a.id=x),'{}'));
   end loop;
  end if;
 end loop;
 delete from bb_colazioni c where c.struttura_id is not distinct from sid and c.id<>all(keep) and not exists(select 1 from bb_vouchers x where x.colazione_id=c.id);
 update bb_colazioni set attiva=false where struttura_id is not distinct from sid and id<>all(keep);
 return bb_colazioni_json(sid,false);
end $$;

-- prima volta: le fasce storiche diventano colazioni standard
insert into bb_colazioni(struttura_id,nome,prezzo,descrizione,ordine)
select null,'Colazione da €'||m.fascia::text,m.fascia,coalesce(m.descrizione,''),row_number() over (order by m.fascia)
from bb_menu m where not exists(select 1 from bb_colazioni where struttura_id is null);
insert into bb_colazione_voci(colazione_id,ordine,nome,qta,prodotto_id,ingredienti,allergeni)
select c.id,v.ordine,v.nome,v.qta,v.prodotto_id,v.ingredienti,v.allergeni from bb_colazioni c join bb_menu_voci v on v.fascia=c.prezzo::int
where c.struttura_id is null and not exists(select 1 from bb_colazione_voci x where x.colazione_id=c.id);

create or replace function bb_tit_stato(p text) returns json language plpgsql security definer set search_path=public,extensions as $$
begin
 perform bb_check_tit(p);
 return json_build_object(
  'oggi',bb_oggi(),'bar',bb_bar_pubblico(),'menu',bb_menu_pubblico(),'allergeni',bb_menu_allergeni(),'sumup',bb_sumup_attivo(),'pin_off',bb_pin_stato(),
  'config',(select coalesce(json_object_agg(k,v),'{}'::json) from bb_config where k<>'tit_pin'),
  'voci',(select coalesce(json_object_agg(fascia::text,bb_voci_json(fascia)),'{}'::json) from bb_menu),
  'standard',bb_colazioni_json(null,false),
  'colazioni',(select coalesce(json_object_agg(id::text,bb_colazioni_json(id,false)),'{}'::json) from bb_strutture),
  'allergeni_elenco',bb_allergeni_elenco(),
  'camere',(select coalesce(json_object_agg(sid::text,cj),'{}'::json) from (select c.struttura_id sid, json_agg(json_build_object('nome',c.nome,'ospiti',c.ospiti) order by c.ordine) cj from bb_camere c group by c.struttura_id) x),
  'strutture',(select coalesce(json_agg(x order by x.nome),'[]'::json) from (select id,nome,indirizzo,telefono,email,demo,servizio_tavolo,accesso,invito_token,(pin_hash is not null) attivo,bb_saldo(id) saldo from bb_strutture) x),
  'attesa',(select coalesce(json_agg(x order by x.t),'[]'::json) from (select m.id,m.t,m.importo,s.nome from bb_movimenti m join bb_strutture s on s.id=m.struttura_id where not m.confermato and m.sumup_id is null) x),
  'movimenti',(select coalesce(json_agg(x order by x.t desc),'[]'::json) from (select m.id,m.struttura_id,s.nome struttura,m.t,m.tipo,m.importo,m.nota,m.confermato from bb_movimenti m join bb_strutture s on s.id=m.struttura_id) x),
  'vouchers',(select coalesce(json_agg(x order by x.creato desc),'[]'::json) from (select v.id,v.struttura_id,s.nome struttura,v.fascia,v.qta,v.usate,v.data,v.data_fine,v.ospite,v.camera,v.ospiti,v.colazione_id,v.colazione_nome,v.creato,v.annullato,v.richieste,v.extra,v.extra_totale,v.extra_pagato,
     (select coalesce(json_agg((t at time zone 'Europe/Rome')::date),'[]'::json) from unnest(v.riscatti) t) riscatti
     from bb_vouchers v join bb_strutture s on s.id=v.struttura_id) x));
end $$;
