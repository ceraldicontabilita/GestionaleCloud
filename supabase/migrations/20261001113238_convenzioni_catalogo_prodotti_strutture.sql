-- Catalogo separato per struttura: il titolare sceglie quali prodotti mostrare
-- e il prezzo di vendita specifico. I dati descrittivi sono un'istantanea delle
-- fonti canoniche; nessuna riga di fattura o ricetta viene modificata.

create table if not exists public.bb_struttura_prodotti (
  struttura_id uuid not null references public.bb_strutture(id) on delete cascade,
  prodotto_chiave text not null,
  origine text not null check (origine in ('vandemoortele','produzione_interna','senza_glutine')),
  nome text not null,
  descrizione text not null default '',
  allergeni text[] not null default '{}',
  immagine text,
  prezzo numeric(8,2) not null check (prezzo > 0),
  categoria text not null default '',
  ordine int not null default 0,
  aggiornato timestamptz not null default now(),
  primary key (struttura_id, prodotto_chiave)
);
create index if not exists bb_struttura_prodotti_ordine
  on public.bb_struttura_prodotti(struttura_id, origine, ordine, nome);
alter table public.bb_struttura_prodotti enable row level security;
revoke all on public.bb_struttura_prodotti from public, anon, authenticated;

create or replace function public.bb_prodotti_struttura_json(sid uuid) returns json
language sql stable security definer set search_path='' as $$
 select coalesce(json_agg(json_build_object(
   'chiave',p.prodotto_chiave,'origine',p.origine,'nome',p.nome,
   'descrizione',p.descrizione,'allergeni',p.allergeni,'immagine',p.immagine,
   'prezzo',p.prezzo,'categoria',p.categoria
 ) order by case p.origine when 'vandemoortele' then 0 when 'produzione_interna' then 1 else 2 end,
 p.ordine,p.nome),'[]'::json)
 from public.bb_struttura_prodotti p where p.struttura_id=sid
$$;
revoke all on function public.bb_prodotti_struttura_json(uuid) from public, anon, authenticated;

create or replace function public.bb_tit_prodotti_struttura(p text, sid uuid) returns json
language plpgsql security definer set search_path='' as $$
begin
 perform public.bb_check_tit(p);
 if not exists(select 1 from public.bb_strutture where id=sid) then raise exception 'Struttura non trovata'; end if;
 return public.bb_prodotti_struttura_json(sid);
end $$;
revoke all on function public.bb_tit_prodotti_struttura(text,uuid) from public, anon, authenticated;
grant execute on function public.bb_tit_prodotti_struttura(text,uuid) to anon, authenticated;

create or replace function public.bb_tit_prodotti_salva(p text, sid uuid, righe jsonb) returns json
language plpgsql security definer set search_path='' as $$
declare r jsonb; i int:=0; chiave text; ori text; nm text; pr numeric; keep text[]:='{}';
begin
 perform public.bb_check_tit(p);
 if not exists(select 1 from public.bb_strutture where id=sid) then raise exception 'Struttura non trovata'; end if;
 if jsonb_typeof(righe)<>'array' or jsonb_array_length(righe)>500 then
  raise exception 'Elenco prodotti non valido (massimo 500)';
 end if;
 for r in select * from jsonb_array_elements(righe) loop
  i:=i+1;
  chiave:=left(trim(coalesce(r->>'chiave','')),180);
  ori:=trim(coalesce(r->>'origine',''));
  nm:=left(trim(coalesce(r->>'nome','')),160);
  pr:=nullif(r->>'prezzo','')::numeric;
  if chiave='' or nm='' then raise exception 'Ogni prodotto deve avere identita e nome'; end if;
  if ori not in ('vandemoortele','produzione_interna','senza_glutine') then raise exception 'Origine prodotto non valida'; end if;
  if pr is null or pr<=0 or pr>9999 then raise exception 'Inserisci un prezzo di vendita valido per %',nm; end if;
  if chiave=any(keep) then raise exception 'Prodotto duplicato: %',nm; end if;
  keep:=array_append(keep,chiave);
  insert into public.bb_struttura_prodotti(
   struttura_id,prodotto_chiave,origine,nome,descrizione,allergeni,immagine,prezzo,categoria,ordine,aggiornato)
  values (
   sid,chiave,ori,nm,left(trim(coalesce(r->>'descrizione','')),1000),
   coalesce(array(select left(trim(x),80) from jsonb_array_elements_text(coalesce(r->'allergeni','[]')) x where trim(x)<>''),'{}'),
   nullif(left(trim(coalesce(r->>'immagine','')),1000),''),pr,
   left(trim(coalesce(r->>'categoria','')),100),i,now())
  on conflict (struttura_id,prodotto_chiave) do update set
   origine=excluded.origine,nome=excluded.nome,descrizione=excluded.descrizione,
   allergeni=excluded.allergeni,immagine=excluded.immagine,prezzo=excluded.prezzo,
   categoria=excluded.categoria,ordine=excluded.ordine,aggiornato=now();
 end loop;
 delete from public.bb_struttura_prodotti x
  where x.struttura_id=sid and not (x.prodotto_chiave=any(keep));
 return public.bb_prodotti_struttura_json(sid);
end $$;
revoke all on function public.bb_tit_prodotti_salva(text,uuid,jsonb) from public, anon, authenticated;
grant execute on function public.bb_tit_prodotti_salva(text,uuid,jsonb) to anon, authenticated;

create or replace function public.bb_alb_prodotti(sid uuid, p text) returns json
language plpgsql security definer set search_path='' as $$
begin
 perform public.bb_check_alb(sid,p);
 return public.bb_prodotti_struttura_json(sid);
end $$;
revoke all on function public.bb_alb_prodotti(uuid,text) from public, anon, authenticated;
grant execute on function public.bb_alb_prodotti(uuid,text) to anon, authenticated;

