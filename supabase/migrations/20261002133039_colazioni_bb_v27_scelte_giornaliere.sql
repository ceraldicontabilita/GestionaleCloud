-- Un solo QR per il soggiorno, ma richieste ed extra separati per giornata.
create table if not exists public.bb_voucher_giorni (
 voucher_id text not null references public.bb_vouchers(id) on delete cascade,
 giorno date not null,
 modifiche jsonb not null default '[]'::jsonb,
 extra jsonb not null default '[]'::jsonb,
 extra_totale numeric(10,2) not null default 0,
 extra_pagato boolean not null default false,
 aggiornato timestamptz not null default now(),
 primary key(voucher_id,giorno),
 check (jsonb_typeof(modifiche)='array'),
 check (jsonb_typeof(extra)='array'),
 check (extra_totale>=0)
);
alter table public.bb_voucher_giorni enable row level security;
revoke all on public.bb_voucher_giorni from public,anon,authenticated;

create or replace function public.bb_scelta_giorno(pvid text,pgiorno date) returns json
language sql stable security definer set search_path='' as $$
 select json_build_object(
  'giorno',pgiorno,
  'richieste',jsonb_build_object(
   'allergie',coalesce(v.richieste->'allergie','[]'::jsonb),
   'nota',coalesce(v.richieste->>'nota',''),
   'modifiche',coalesce(g.modifiche,case when pgiorno=greatest(v.data,least(public.bb_oggi(),coalesce(v.data_fine,v.data))) then v.richieste->'modifiche' else '[]'::jsonb end,'[]'::jsonb)),
  'extra',coalesce(g.extra,case when pgiorno=greatest(v.data,least(public.bb_oggi(),coalesce(v.data_fine,v.data))) then v.extra else '[]'::jsonb end,'[]'::jsonb),
  'extra_totale',coalesce(g.extra_totale,case when pgiorno=greatest(v.data,least(public.bb_oggi(),coalesce(v.data_fine,v.data))) then v.extra_totale else 0 end,0),
  'extra_pagato',coalesce(g.extra_pagato,case when pgiorno=greatest(v.data,least(public.bb_oggi(),coalesce(v.data_fine,v.data))) then v.extra_pagato else false end,false))
 from public.bb_vouchers v left join public.bb_voucher_giorni g on g.voucher_id=v.id and g.giorno=pgiorno
 where v.id=upper(trim(pvid))
$$;
revoke all on function public.bb_scelta_giorno(text,date) from public,anon,authenticated;

create or replace function public.bb_ospite(vid text) returns json
language sql security definer set search_path='' as $$
 select json_build_object(
  'id',v.id,'qta',v.qta,'usate',v.usate,'data',v.data,'data_fine',v.data_fine,
  'ospite',v.ospite,'camera',v.camera,'ospiti',v.ospiti,'annullato',v.annullato,
  'struttura',s.nome,'indirizzo',s.indirizzo,'sfondo',s.sfondo,'benvenuto',s.benvenuto,
  'tavolo',v.servizio_tavolo,'colazione',v.colazione_nome,
  'menu',coalesce((select descrizione from public.bb_colazioni where id=v.colazione_id),(select descrizione from public.bb_menu where fascia=v.fascia)),
  'voci',case when v.colazione_id is not null then public.bb_voci_col_json(v.colazione_id) else public.bb_voci_json(v.fascia::int) end,
  'richieste',v.richieste,'extra',v.extra,'extra_totale',v.extra_totale,'extra_pagato',v.extra_pagato,
  'scelte',(select coalesce(json_object_agg((x.g)::text,public.bb_scelta_giorno(v.id,x.g)),'{}'::json) from (
    select generate_series(v.data,coalesce(v.data_fine,v.data),interval '1 day')::date g) x),
  'glutine',public.bb_glutine_pubblico(),'allergeni_elenco',public.bb_allergeni_elenco(),
  'bar',public.bb_bar_pubblico(),'oggi',public.bb_oggi())
 from public.bb_vouchers v join public.bb_strutture s on s.id=v.struttura_id
 where v.id=upper(trim(vid))
$$;
revoke all on function public.bb_ospite(text) from public,anon,authenticated;
grant execute on function public.bb_ospite(text) to anon,authenticated;

create or replace function public.bb_ospite_salva_giorno(vid text,pgiorno date,prichieste jsonb,pextra jsonb) returns json
language plpgsql security definer set search_path='' as $$
declare v public.bb_vouchers; corrente public.bb_voucher_giorni; ex jsonb:='[]'; tot numeric:=0; e jsonb; pr record; g record; n int:=0; nuovi text[]; vecchi text[]; riscattate int;
begin
 select * into v from public.bb_vouchers where id=upper(trim(vid)) for update;
 if not found then raise exception 'Codice non trovato'; end if;
 if v.annullato then raise exception 'Questa colazione è stata annullata'; end if;
 if pgiorno is null or pgiorno<v.data or pgiorno>coalesce(v.data_fine,v.data) then raise exception 'Giorno non compreso nel soggiorno'; end if;
 if pgiorno<public.bb_oggi() then raise exception 'La colazione di questo giorno è già trascorsa'; end if;
 select count(*) into riscattate from unnest(v.riscatti) t where (t at time zone 'Europe/Rome')::date=pgiorno;
 if pgiorno=public.bb_oggi() and riscattate>=v.ospiti then raise exception 'La colazione di oggi è già stata ritirata'; end if;
 prichieste:=coalesce(prichieste,'{}'::jsonb);
 if jsonb_typeof(prichieste)<>'object' or length(prichieste::text)>6000 then raise exception 'Richiesta non valida o troppo lunga'; end if;
 if jsonb_typeof(coalesce(prichieste->'modifiche','[]'::jsonb))<>'array' then raise exception 'Modifiche non valide'; end if;
 select * into corrente from public.bb_voucher_giorni where voucher_id=v.id and giorno=pgiorno;
 select coalesce(array_agg(x->>'variante' order by x->>'variante'),'{}') into nuovi from jsonb_array_elements(coalesce(prichieste->'modifiche','[]'::jsonb)) x
  where x->>'tipo'='senza_glutine' and coalesce(x->>'variante','')<>'';
 if found and corrente.extra_pagato then
  select coalesce(array_agg(x->>'variante' order by x->>'variante'),'{}') into vecchi from jsonb_array_elements(coalesce(corrente.modifiche,'[]'::jsonb)) x
   where x->>'tipo'='senza_glutine' and coalesce(x->>'variante','')<>'';
  if nuovi is distinct from vecchi then raise exception 'Gli extra di questo giorno sono già pagati: rivolgiti al bar'; end if;
  ex:=corrente.extra;tot:=corrente.extra_totale;
 else
  if jsonb_typeof(coalesce(pextra,'[]'::jsonb))<>'array' then raise exception 'Ordine non valido'; end if;
  for e in select * from jsonb_array_elements(coalesce(pextra,'[]'::jsonb)) loop
   n:=n+1;exit when n>40;
   select p.id,p.nome,p.prezzo pz into pr from public.bb_prodotti p join public.bb_prod_cat c on c.id=p.cat_id
    where p.id=(e->>'id')::int and p.visibile and c.attivo and c.ospiti;
   if found and pr.pz>0 and coalesce((e->>'qta')::int,0) between 1 and 20 then
    ex:=ex||jsonb_build_object('id',pr.id,'nome',pr.nome,'qta',(e->>'qta')::int,'prezzo',pr.pz);
    tot:=tot+pr.pz*(e->>'qta')::int;
   end if;
  end loop;
  for e in select * from jsonb_array_elements(coalesce(prichieste->'modifiche','[]'::jsonb)) loop
   if e->>'tipo'='senza_glutine' and coalesce(e->>'variante','')<>'' then
    select nome,differenza into g from public.bb_senza_glutine where id=(e->>'variante')::uuid;
    if found then ex:=ex||jsonb_build_object('glutine',true,'nome','Senza glutine: '||g.nome,'qta',1,'prezzo',g.differenza);tot:=tot+g.differenza;end if;
   end if;
  end loop;
 end if;
 update public.bb_vouchers set richieste=jsonb_build_object(
  'allergie',coalesce(prichieste->'allergie','[]'::jsonb),'nota',left(coalesce(prichieste->>'nota',''),500),
  'modifiche',case when pgiorno=greatest(v.data,least(public.bb_oggi(),coalesce(v.data_fine,v.data))) then '[]'::jsonb else coalesce(v.richieste->'modifiche','[]'::jsonb) end),
  richieste_agg=now() where id=v.id;
 insert into public.bb_voucher_giorni(voucher_id,giorno,modifiche,extra,extra_totale,extra_pagato,aggiornato)
 values(v.id,pgiorno,coalesce(prichieste->'modifiche','[]'::jsonb),ex,tot,coalesce(corrente.extra_pagato,false),now())
 on conflict(voucher_id,giorno) do update set modifiche=excluded.modifiche,extra=excluded.extra,extra_totale=excluded.extra_totale,aggiornato=now();
 return public.bb_ospite(v.id);
end $$;
revoke all on function public.bb_ospite_salva_giorno(text,date,jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.bb_ospite_salva_giorno(text,date,jsonb,jsonb) to anon,authenticated;

create or replace function public.bb_ospite_salva(vid text,prichieste jsonb,pextra jsonb) returns json
language plpgsql security definer set search_path='' as $$
declare v public.bb_vouchers; g date;
begin
 select * into v from public.bb_vouchers where id=upper(trim(vid));
 if not found then raise exception 'Codice non trovato'; end if;
 g:=greatest(v.data,least(public.bb_oggi(),coalesce(v.data_fine,v.data)));
 return public.bb_ospite_salva_giorno(v.id,g,prichieste,pextra);
end $$;
revoke all on function public.bb_ospite_salva(text,jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.bb_ospite_salva(text,jsonb,jsonb) to anon,authenticated;

create or replace function public.bb_tit_riscatta(p text,vid text) returns json
language plpgsql security definer set search_path='' as $$
declare v public.bb_vouchers;s text;msg text;ok boolean:=false;oggi_n int;sc json;
begin
 perform public.bb_check_tit(p);
 select * into v from public.bb_vouchers where id=upper(trim(vid)) for update;
 if not found then return json_build_object('ok',false,'msg','Codice non trovato'); end if;
 select count(*) into oggi_n from unnest(v.riscatti) t where (t at time zone 'Europe/Rome')::date=public.bb_oggi();
 if v.annullato then msg:='Voucher annullato';
 elsif v.usate>=v.qta then msg:='Già utilizzato interamente';
 elsif public.bb_oggi()>v.data_fine then msg:='Voucher scaduto ('||to_char(v.data_fine,'DD/MM')||')';
 elsif public.bb_oggi()<v.data then msg:='Valido dal '||to_char(v.data,'DD/MM');
 elsif oggi_n>=v.ospiti then msg:='Oggi le '||v.ospiti||' colazioni di questa camera sono già state consegnate';
 else update public.bb_vouchers set usate=usate+1,riscatti=riscatti||now() where id=v.id returning * into v;oggi_n:=oggi_n+1;ok:=true;msg:='Colazione consegnata ('||oggi_n||' di '||v.ospiti||' oggi)';end if;
 select nome into s from public.bb_strutture where id=v.struttura_id;
 sc:=public.bb_scelta_giorno(v.id,public.bb_oggi());
 return json_build_object('ok',ok,'msg',msg,'voucher',json_build_object(
  'id',v.id,'fascia',v.fascia,'qta',v.qta,'usate',v.usate,'ospite',v.ospite,'camera',v.camera,'ospiti',v.ospiti,'struttura',s,
  'data',v.data,'data_fine',v.data_fine,'colazione',v.colazione_nome,'menu',coalesce((select descrizione from public.bb_colazioni where id=v.colazione_id),(select descrizione from public.bb_menu where fascia=v.fascia)),
  'voci',case when v.colazione_id is not null then public.bb_voci_col_json(v.colazione_id) else public.bb_voci_json(v.fascia::int) end,
  'richieste',sc->'richieste','extra',sc->'extra','extra_totale',sc->'extra_totale','extra_pagato',sc->'extra_pagato'));
end $$;
revoke all on function public.bb_tit_riscatta(text,text) from public,anon,authenticated;
grant execute on function public.bb_tit_riscatta(text,text) to anon,authenticated;

create or replace function public.bb_tit_extra_incassato(p text,vid text) returns void
language plpgsql security definer set search_path='' as $$
begin
 perform public.bb_check_tit(p);
 update public.bb_voucher_giorni set extra_pagato=true,aggiornato=now()
 where voucher_id=upper(trim(vid)) and giorno=public.bb_oggi() and extra_totale>0;
 if not found then update public.bb_vouchers set extra_pagato=true where id=upper(trim(vid)) and extra_totale>0;end if;
end $$;
revoke all on function public.bb_tit_extra_incassato(text,text) from public,anon,authenticated;
grant execute on function public.bb_tit_extra_incassato(text,text) to anon,authenticated;

create or replace function public.bb_alb_stato(sid uuid,p text) returns json
language plpgsql security definer set search_path='' as $$
begin
 perform public.bb_check_alb(sid,p);
 perform public.bb_sumup_verifica(sid);
 return json_build_object(
  'struttura',(select json_build_object(
   'id',id,'nome',nome,'indirizzo',indirizzo,'telefono',telefono,'benvenuto',benvenuto,
   'accesso',accesso,'saldo',public.bb_saldo(id),'tavolo',servizio_tavolo,
   'supp_tavolo',public.bb_supplemento_tavolo())
   from public.bb_strutture where id=sid),
  'fiscali',(select public.bb_fiscali_json(s) from public.bb_strutture s where s.id=sid),
  'fatture',(select coalesce(json_agg(f order by f.pagata_il desc),'[]'::json) from (
   select id,importo,pagata_il,stato,numero,data_emissione
   from public.bb_fatture_da_emettere where struttura_id=sid order by pagata_il desc limit 50) f),
  'oggi',public.bb_oggi(),'bar',public.bb_bar_pubblico(),'sumup',public.bb_sumup_attivo(),
  'config',json_build_object(
   'ricarica_min',public.bb_cfg('ricarica_min','5')::numeric,
   'ricarica_max',public.bb_cfg('ricarica_max','2000')::numeric,
   'anticipo',public.bb_cfg('anticipo_max_giorni','60')::int,
   'limite_ora',public.bb_cfg('ordini_limite_ora',''),
   'msg',public.bb_cfg('msg_ospite','{link}')),
  'colazioni',public.bb_colazioni_json(sid,true),
  'camere',(select coalesce(json_agg(json_build_object(
   'id',c.id,'nome',c.nome,'ospiti',c.ospiti,'servizio_tavolo',c.servizio_tavolo)
   order by c.ordine),'[]'::json) from public.bb_camere c where c.struttura_id=sid),
  'movimenti',(select coalesce(json_agg(m order by m.t desc),'[]'::json) from (
   select id,t,tipo,importo,nota,confermato,sumup_url
   from public.bb_movimenti where struttura_id=sid) m),
  'vouchers',(select coalesce(json_agg(v order by v.creato desc),'[]'::json) from (
   select x.id,x.fascia,x.qta,x.usate,x.data,x.data_fine,x.ospite,x.camera,x.ospiti,x.colazione_nome,x.creato,
    x.annullato,x.annullo_motivo,
    (coalesce(x.richieste->'allergie','[]'::jsonb)<>'[]'::jsonb or coalesce(x.richieste->>'nota','')<>'' or
     coalesce(x.richieste->'modifiche','[]'::jsonb)<>'[]'::jsonb or exists(select 1 from public.bb_voucher_giorni g where g.voucher_id=x.id and g.modifiche<>'[]'::jsonb)) has_richieste,
    case when exists(select 1 from public.bb_voucher_giorni g where g.voucher_id=x.id)
     then (select coalesce(sum(g.extra_totale),0) from public.bb_voucher_giorni g where g.voucher_id=x.id) else x.extra_totale end extra_totale,
    case when exists(select 1 from public.bb_voucher_giorni g where g.voucher_id=x.id)
     then (select coalesce(sum(g.extra_totale) filter(where not g.extra_pagato),0) from public.bb_voucher_giorni g where g.voucher_id=x.id)
     else public.bb_extra_da_pagare(x) end extra_da_pagare,
    x.servizio_tavolo,x.supplemento_tavolo
   from public.bb_vouchers x where x.struttura_id=sid) v));
end $$;
revoke all on function public.bb_alb_stato(uuid,text) from public,anon,authenticated;
grant execute on function public.bb_alb_stato(uuid,text) to anon,authenticated;

create or replace function public.bb_tit_stato(p text) returns json
language plpgsql security definer set search_path='' as $$
begin
 perform public.bb_check_tit(p);
 return json_build_object(
  'oggi',public.bb_oggi(),'bar',public.bb_bar_pubblico(),'menu',public.bb_menu_pubblico(),
  'allergeni',public.bb_menu_allergeni(),'sumup',public.bb_sumup_attivo(),'pin_off',public.bb_pin_stato(),
  'config',(select coalesce(json_object_agg(k,v),'{}'::json) from public.bb_config where k<>'tit_pin'),
  'voci',(select coalesce(json_object_agg(fascia::text,public.bb_voci_json(fascia)),'{}'::json) from public.bb_menu),
  'standard',public.bb_colazioni_json(null,false),
  'colazioni',(select coalesce(json_object_agg(id::text,public.bb_colazioni_json(id,false)),'{}'::json) from public.bb_strutture),
  'allergeni_elenco',public.bb_allergeni_elenco(),
  'camere',(select coalesce(json_object_agg(sid::text,cj),'{}'::json) from (select c.struttura_id sid,json_agg(json_build_object('nome',c.nome,'ospiti',c.ospiti,'servizio_tavolo',c.servizio_tavolo) order by c.ordine) cj from public.bb_camere c group by c.struttura_id)x),
  'strutture',(select coalesce(json_agg(x order by x.nome),'[]'::json) from (select id,nome,indirizzo,telefono,email,demo,servizio_tavolo,accesso,invito_token,(pin_hash is not null) attivo,public.bb_saldo(id) saldo from public.bb_strutture)x),
  'attesa',(select coalesce(json_agg(x order by x.t),'[]'::json) from (select m.id,m.t,m.importo,s.nome from public.bb_movimenti m join public.bb_strutture s on s.id=m.struttura_id where not m.confermato and m.sumup_id is null)x),
  'movimenti',(select coalesce(json_agg(x order by x.t desc),'[]'::json) from (select m.id,m.struttura_id,s.nome struttura,m.t,m.tipo,m.importo,m.nota,m.confermato from public.bb_movimenti m join public.bb_strutture s on s.id=m.struttura_id)x),
  'vouchers',(select coalesce(json_agg(x order by x.creato desc),'[]'::json) from (
   select v.id,v.struttura_id,s.nome struttura,v.fascia,v.qta,v.usate,v.data,v.data_fine,v.ospite,v.camera,v.ospiti,v.colazione_id,v.colazione_nome,v.creato,v.annullato,
    v.richieste,v.extra,v.extra_totale,v.extra_pagato,v.servizio_tavolo,v.supplemento_tavolo,
    (select coalesce(json_agg((t at time zone 'Europe/Rome')::date),'[]'::json) from unnest(v.riscatti)t) riscatti,
    (select coalesce(json_object_agg(g.giorno::text,json_build_object('richieste',jsonb_build_object('allergie',coalesce(v.richieste->'allergie','[]'::jsonb),'nota',coalesce(v.richieste->>'nota',''),'modifiche',g.modifiche),'extra',g.extra,'extra_totale',g.extra_totale,'extra_pagato',g.extra_pagato)),'{}'::json) from public.bb_voucher_giorni g where g.voucher_id=v.id) giorni
   from public.bb_vouchers v join public.bb_strutture s on s.id=v.struttura_id)x));
end $$;
revoke all on function public.bb_tit_stato(text) from public,anon,authenticated;
grant execute on function public.bb_tit_stato(text) to anon,authenticated;

create or replace function public.bb_accoda_notifica_voucher_giorno() returns trigger
language plpgsql security definer set search_path='' as $$
declare v public.bb_vouchers;nome_struttura text;
begin
 if jsonb_array_length(coalesce(new.extra,'[]'::jsonb))=0 or (tg_op='UPDATE' and new.extra is not distinct from old.extra) then return new;end if;
 select * into v from public.bb_vouchers x where x.id=new.voucher_id;
 select s.nome into nome_struttura from public.bb_strutture s where s.id=v.struttura_id;
 insert into public.bb_notifiche_operative(tipo,chiave,payload)
 values('extra_ospite','extra:'||new.voucher_id||':'||new.giorno||':'||public.bb_tok_hash(new.extra::text||':'||new.extra_totale::text),jsonb_build_object(
  'voucher_id',new.voucher_id,'struttura',coalesce(nome_struttura,'Struttura'),'camera',coalesce(nullif(v.camera,''),'non indicata'),
  'periodo',to_char(new.giorno,'DD/MM/YYYY'),'extra',new.extra,'totale',new.extra_totale))
 on conflict(chiave) do nothing;
 return new;
end $$;
revoke all on function public.bb_accoda_notifica_voucher_giorno() from public,anon,authenticated;
drop trigger if exists bb_vouchers_notifica_extra on public.bb_vouchers;
drop trigger if exists bb_voucher_giorni_notifica_extra on public.bb_voucher_giorni;
create trigger bb_voucher_giorni_notifica_extra after insert or update of extra on public.bb_voucher_giorni
for each row execute function public.bb_accoda_notifica_voucher_giorno();

revoke all on public.bb_voucher_giorni from anon,authenticated;
