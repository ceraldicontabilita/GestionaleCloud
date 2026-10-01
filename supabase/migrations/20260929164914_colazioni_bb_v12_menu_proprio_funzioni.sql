update bb_prodotti p set immagine = (select m.image from menu.menu_products m where m.id=p.id), descrizione_lunga='', materiali='' where true;

create or replace function bb_catalogo() returns json language sql security definer set search_path=public as
$$ select coalesce(json_agg(json_build_object('id',p.id,'nome',p.nome,'desc',p.descrizione,'prezzo',p.prezzo,'allergeni',p.allergeni,'tags',p.tags,
     'cat',c.nome,'sub',coalesce(s.nome,''),'img',p.immagine,'varianti',p.varianti) order by c.ordine,s.ordine,p.nome),'[]'::json)
   from bb_prodotti p join bb_prod_cat c on c.id=p.cat_id left join bb_prod_sub s on s.id=p.sub_id
   where p.visibile and c.attivo and c.ospiti and coalesce(s.attivo,true) and p.prezzo>0 $$;

create or replace function bb_voci_json(f int) returns json language sql security definer set search_path=public as
$$ select coalesce(json_agg(json_build_object('id',v.id,'nome',coalesce(nullif(v.nome,''),p.nome,''),'qta',v.qta,'prodotto_id',v.prodotto_id,
     'allergeni',case when v.prodotto_id is not null then coalesce(p.allergeni,'{}') else v.allergeni end,'ingredienti',v.ingredienti) order by v.ordine,v.id),'[]'::json)
   from bb_menu_voci v left join bb_prodotti p on p.id=v.prodotto_id where v.fascia=f $$;

create or replace function bb_ospite_salva(vid text,prichieste jsonb,pextra jsonb) returns json language plpgsql security definer set search_path=public as $$
declare v bb_vouchers; ex jsonb:='[]'; tot numeric:=0; e jsonb; pr record; g record; n int:=0; nuovi text[]; vecchi text[];
begin
 select * into v from bb_vouchers where id=upper(trim(vid)) for update;
 if not found then raise exception 'Codice non trovato'; end if;
 if v.annullato then raise exception 'Questa colazione è stata annullata'; end if;
 if v.usate>0 or v.data<bb_oggi() then raise exception 'Non è più possibile modificare questa colazione'; end if;
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

create or replace function bb_tit_voci_salva(p text,pfascia int,righe jsonb) returns void language plpgsql security definer set search_path=public,extensions as $$
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
   if not exists(select 1 from bb_prodotti where id=pid) then raise exception 'Prodotto % non trovato',pid; end if;
   if nm='' then select nome into nm from bb_prodotti where id=pid; end if;
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

select (select count(*) from bb_prodotti) prodotti, json_array_length(bb_catalogo()) nel_catalogo_ospiti,
 (select count(*) from bb_prodotti where immagine is not null) con_immagine_fallback;

