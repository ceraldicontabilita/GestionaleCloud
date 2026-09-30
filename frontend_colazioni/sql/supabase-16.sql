-- v16: prezzo modificabile per ogni prodotto di una colazione (solo lato titolare)
alter table bb_colazione_voci add column if not exists prezzo numeric(8,2);

create or replace function bb_voci_col_json_p(cid uuid) returns json language sql security definer set search_path=public as $$
 select coalesce(json_agg(json_build_object('id',v.id,'nome',coalesce(nullif(v.nome,''),p.nome,''),'qta',v.qta,'prodotto_id',v.prodotto_id,'prezzo',v.prezzo,
     'allergeni',case when v.prodotto_id is not null then coalesce(p.allergeni,'{}') else v.allergeni end,'ingredienti',v.ingredienti) order by v.ordine,v.id),'[]'::json)
   from bb_colazione_voci v left join bb_prodotti p on p.id=v.prodotto_id where v.colazione_id=cid $$;

create or replace function bb_colazioni_json(sid uuid, solo_attive boolean) returns json language sql security definer set search_path=public as $$
 select coalesce(json_agg(json_build_object('id',c.id,'nome',c.nome,'prezzo',c.prezzo,'descrizione',c.descrizione,'attiva',c.attiva,
   'voci',case when solo_attive then bb_voci_col_json(c.id) else bb_voci_col_json_p(c.id) end) order by c.ordine,c.nome),'[]'::json)
   from bb_colazioni c where c.struttura_id=sid and (not solo_attive or c.attiva) $$;

create or replace function bb_tit_colazioni_salva(p text, sid uuid, righe jsonb) returns json language plpgsql security definer set search_path=public,extensions as $$
declare r jsonb; v jsonb; cid uuid; i int:=0; j int; keep uuid[]:='{}'; nm text; pr numeric; pid int; vn text; vp numeric;
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
 delete from bb_colazioni c where c.struttura_id=sid and c.id<>all(keep) and not exists(select 1 from bb_vouchers x where x.colazione_id=c.id);
 update bb_colazioni set attiva=false where struttura_id=sid and id<>all(keep);
 return bb_colazioni_json(sid,false);
end $$;
