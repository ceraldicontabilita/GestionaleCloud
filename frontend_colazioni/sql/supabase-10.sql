-- Colazioni B&B · migrazione 10: versioni senza glutine con la sola differenza da pagare

create table if not exists bb_senza_glutine (
  id uuid primary key default gen_random_uuid(),
  nome text not null, differenza numeric(6,2) not null default 0 check (differenza>=0),
  per text not null default '', ordine int not null default 0);
alter table bb_senza_glutine enable row level security;
revoke all on bb_senza_glutine from anon, authenticated;

create or replace function bb_glutine_pubblico() returns json language sql security definer set search_path=public as
$$ select coalesce(json_agg(json_build_object('id',id,'nome',nome,'differenza',differenza,'per',per) order by ordine,nome),'[]'::json) from bb_senza_glutine $$;
revoke all on function bb_glutine_pubblico() from public; grant execute on function bb_glutine_pubblico() to anon;

create or replace function bb_tit_glutine_salva(p text,righe jsonb) returns int language plpgsql security definer set search_path=public,extensions as $$
declare r jsonb; i int:=0;
begin
 perform bb_check_tit(p);
 if jsonb_typeof(righe)<>'array' or jsonb_array_length(righe)>200 then raise exception 'Elenco non valido (max 200 voci)'; end if;
 delete from bb_senza_glutine;
 for r in select * from jsonb_array_elements(righe) loop
  if coalesce(trim(r->>'nome'),'')='' then continue; end if;
  i:=i+1;
  insert into bb_senza_glutine(nome,differenza,per,ordine) values (left(trim(r->>'nome'),80),least(999,greatest(0,coalesce((r->>'differenza')::numeric,0))),left(coalesce(trim(r->>'per'),''),40),i);
 end loop;
 return i;
end $$;
revoke all on function bb_tit_glutine_salva(text,jsonb) from public; grant execute on function bb_tit_glutine_salva(text,jsonb) to anon;

create or replace function bb_ospite(vid text) returns json language sql security definer set search_path=public as
$$ select json_build_object('id',v.id,'qta',v.qta,'usate',v.usate,'data',v.data,'ospite',v.ospite,'camera',v.camera,'ospiti',v.ospiti,'annullato',v.annullato,
   'struttura',s.nome,'indirizzo',s.indirizzo,'sfondo',s.sfondo,'benvenuto',s.benvenuto,'menu',(select descrizione from bb_menu where fascia=v.fascia),'voci',bb_voci_json(v.fascia),
   'richieste',v.richieste,'extra',v.extra,'extra_totale',v.extra_totale,'extra_pagato',v.extra_pagato,'glutine',bb_glutine_pubblico(),
   'allergeni_elenco',bb_allergeni_elenco(),'bar',bb_bar_pubblico(),'oggi',bb_oggi())
   from bb_vouchers v join bb_strutture s on s.id=v.struttura_id where v.id=upper(trim(vid)) $$;

create or replace function bb_ospite_salva(vid text,prichieste jsonb,pextra jsonb) returns json language plpgsql security definer set search_path=public,menu as $$
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
   select p.id, p.name_it nome, bb_prezzo(p.price) pz into pr from menu.menu_products p
     where p.id=(e->>'id')::int and p.visible and p.category_id in (5170,5181,19632,23110,1000000);
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
