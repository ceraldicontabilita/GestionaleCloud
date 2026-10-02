-- Colazioni B&B: il titolare compone le colazioni cercando direttamente nel
-- Menu digitale. Il catalogo pubblico degli extra resta invariato: questa RPC
-- amministrativa include anche le ricette Lotti ancora senza prezzo, cosi' il
-- prezzo puo' essere completato prima di renderle ordinabili.

create or replace function public.bb_tit_catalogo(p text) returns json
language plpgsql security definer set search_path=''
as $$
begin
  perform public.bb_check_tit(p);
  return (
    select coalesce(json_agg(json_build_object(
      'id', mp.id,
      'nome', coalesce(nullif(mp.name_it,''), mp.name, ''),
      'desc', coalesce(mp.description_it, mp.description, ''),
      'prezzo', public.bb_prezzo(mp.price),
      'allergeni', coalesce(mp.allergens, '{}'),
      'cat', coalesce(nullif(c.name_it,''), c.name, ''),
      'sub', coalesce(nullif(s.name_it,''), s.name, ''),
      'img', mp.image,
      'visibile', mp.visible,
      'origine', mp.origine,
      'lotti_ref', mp.lotti_ref
    ) order by coalesce(nullif(c.name_it,''),c.name,''),
               coalesce(nullif(s.name_it,''),s.name,''),
               coalesce(nullif(mp.name_it,''),mp.name,'')), '[]'::json)
    from menu.menu_products mp
    join menu.menu_categories c on c.id=mp.category_id
    left join menu.menu_subcategories s on s.id=mp.subcategory_id
    where (mp.visible and public.bb_prezzo(mp.price)>0)
       or mp.origine='lotti'
  );
end $$;
revoke all on function public.bb_tit_catalogo(text) from public,anon,authenticated;
grant execute on function public.bb_tit_catalogo(text) to anon;

-- Le colazioni salvano gli id del Menu digitale. Le funzioni di lettura
-- recuperano nome e allergeni dalla stessa fonte, senza una copia concorrente.
create or replace function public.bb_voci_col_json(cid uuid) returns json
language sql security definer set search_path=''
as $$
  select coalesce(json_agg(json_build_object(
    'id',v.id,
    'nome',coalesce(nullif(v.nome,''),nullif(mp.name_it,''),mp.name,''),
    'qta',v.qta,
    'prodotto_id',v.prodotto_id,
    'allergeni',case when v.prodotto_id is not null then coalesce(mp.allergens,'{}') else v.allergeni end,
    'ingredienti',v.ingredienti
  ) order by v.ordine,v.id),'[]'::json)
  from public.bb_colazione_voci v
  left join menu.menu_products mp on mp.id=v.prodotto_id
  where v.colazione_id=cid
$$;

create or replace function public.bb_voci_col_json_p(cid uuid) returns json
language sql security definer set search_path=''
as $$
  select coalesce(json_agg(json_build_object(
    'id',v.id,
    'nome',coalesce(nullif(v.nome,''),nullif(mp.name_it,''),mp.name,''),
    'qta',v.qta,
    'prodotto_id',v.prodotto_id,
    'prezzo',v.prezzo,
    'allergeni',case when v.prodotto_id is not null then coalesce(mp.allergens,'{}') else v.allergeni end,
    'ingredienti',v.ingredienti
  ) order by v.ordine,v.id),'[]'::json)
  from public.bb_colazione_voci v
  left join menu.menu_products mp on mp.id=v.prodotto_id
  where v.colazione_id=cid
$$;
revoke all on function public.bb_voci_col_json(uuid), public.bb_voci_col_json_p(uuid)
  from public,anon,authenticated;

create or replace function public.bb_tit_colazioni_salva(p text, sid uuid, righe jsonb) returns json
language plpgsql security definer set search_path=''
as $$
declare
  r jsonb; v jsonb; cid uuid; i int:=0; j int; keep uuid[]:='{}';
  nm text; pr numeric; pid int; vn text; vp numeric;
begin
  perform public.bb_check_tit(p);
  if sid is not null and not exists(select 1 from public.bb_strutture where id=sid) then
    raise exception 'Struttura non trovata';
  end if;
  if jsonb_typeof(righe)<>'array' or jsonb_array_length(righe)>30 then
    raise exception 'Elenco colazioni non valido (max 30)';
  end if;
  for r in select * from jsonb_array_elements(righe) loop
    i:=i+1;
    nm:=left(trim(coalesce(r->>'nome','')),60);
    if nm='' then raise exception 'Ogni colazione deve avere un nome'; end if;
    pr:=coalesce((r->>'prezzo')::numeric,-1);
    if pr<0 or pr>200 then raise exception 'Prezzo non valido per "%"',nm; end if;
    cid:=nullif(r->>'id','')::uuid;
    if cid is not null and exists(
      select 1 from public.bb_colazioni where id=cid and struttura_id is not distinct from sid
    ) then
      update public.bb_colazioni set nome=nm,prezzo=pr,
        descrizione=left(coalesce(r->>'descrizione',''),200),ordine=i,
        attiva=coalesce((r->>'attiva')::boolean,true)
      where id=cid;
    else
      insert into public.bb_colazioni(struttura_id,nome,prezzo,descrizione,ordine,attiva)
      values (sid,nm,pr,left(coalesce(r->>'descrizione',''),200),i,
              coalesce((r->>'attiva')::boolean,true)) returning id into cid;
    end if;
    keep:=keep||cid;
    delete from public.bb_colazione_voci where colazione_id=cid;
    if jsonb_typeof(r->'voci')='array' then
      if jsonb_array_length(r->'voci')>30 then raise exception 'Troppe voci in "%"',nm; end if;
      j:=0;
      for v in select * from jsonb_array_elements(r->'voci') loop
        j:=j+1;
        pid:=nullif(v->>'prodotto_id','')::int;
        vn:=left(trim(coalesce(v->>'nome','')),80);
        vp:=nullif(v->>'prezzo','')::numeric;
        if vp is not null and (vp<0 or vp>200) then
          raise exception 'Prezzo non valido per la voce "%"',vn;
        end if;
        if pid is not null then
          if not exists(select 1 from menu.menu_products where id=pid) then
            raise exception 'Prodotto % non trovato nel Menu digitale',pid;
          end if;
          if vn='' then
            select coalesce(nullif(name_it,''),name,'') into vn
            from menu.menu_products where id=pid;
          end if;
        end if;
        if vn='' then raise exception 'Ogni voce deve avere un nome (in "%")',nm; end if;
        insert into public.bb_colazione_voci(
          colazione_id,ordine,nome,qta,prodotto_id,prezzo,ingredienti,allergeni
        ) values (
          cid,j,vn,least(10,greatest(1,coalesce((v->>'qta')::int,1))),pid,vp,
          coalesce(array(
            select left(trim(x),40)
            from jsonb_array_elements_text(coalesce(v->'ingredienti','[]')) x
            where trim(x)<>''
          ),'{}'),
          coalesce(array(
            select a.id
            from jsonb_array_elements_text(coalesce(v->'allergeni','[]')) x
            join menu.menu_allergens a on a.id=x
          ),'{}')
        );
      end loop;
    end if;
  end loop;
  delete from public.bb_colazioni c
  where c.struttura_id is not distinct from sid and c.id<>all(keep)
    and not exists(select 1 from public.bb_vouchers x where x.colazione_id=c.id);
  update public.bb_colazioni set attiva=false
  where struttura_id is not distinct from sid and id<>all(keep);
  return public.bb_colazioni_json(sid,false);
end $$;
revoke all on function public.bb_tit_colazioni_salva(text,uuid,jsonb)
  from public,anon,authenticated;
grant execute on function public.bb_tit_colazioni_salva(text,uuid,jsonb) to anon;
