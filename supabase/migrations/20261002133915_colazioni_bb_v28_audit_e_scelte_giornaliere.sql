-- Ripristina i controlli dell'audit 02/10 e salva le modifiche della colazione per singola giornata.
-- Gli extra restano nel formato giornaliero autorevole di bb_vouchers.extra.

alter function public.bb_ospite_salva(text,jsonb,jsonb) rename to bb_ospite_salva_v27;
revoke all on function public.bb_ospite_salva_v27(text,jsonb,jsonb) from public,anon,authenticated;
alter function public.bb_ospite_salva_giorno(text,date,jsonb,jsonb) rename to bb_ospite_salva_giorno_v27;
revoke all on function public.bb_ospite_salva_giorno_v27(text,date,jsonb,jsonb) from public,anon,authenticated;
alter function public.bb_tit_extra_incassato(text,text) rename to bb_tit_extra_incassato_v27;
revoke all on function public.bb_tit_extra_incassato_v27(text,text) from public,anon,authenticated;

create or replace function public.bb_scelta_giorno(pvid text,pgiorno date) returns json
language sql stable security definer set search_path='' as $$
 select json_build_object(
  'giorno',pgiorno,
  'richieste',jsonb_build_object(
   'allergie',coalesce(v.richieste->'allergie','[]'::jsonb),
   'nota',coalesce(v.richieste->>'nota',''),
   'modifiche',coalesce(g.modifiche,'[]'::jsonb)),
  'extra',coalesce(public.bb_extra_del_giorno(v,pgiorno),'{}'::jsonb))
 from public.bb_vouchers v
 left join public.bb_voucher_giorni g on g.voucher_id=v.id and g.giorno=pgiorno
 where v.id=upper(trim(pvid))
$$;
revoke all on function public.bb_scelta_giorno(text,date) from public,anon,authenticated;

create or replace function public.bb_ospite_json(vid text) returns json
language sql security definer set search_path='' as $$
 select json_build_object(
  'id',v.id,'qta',v.qta,'usate',v.usate,'data',v.data,'data_fine',v.data_fine,
  'ospite',v.ospite,'camera',v.camera,'ospiti',v.ospiti,'annullato',v.annullato,
  'struttura',s.nome,'indirizzo',s.indirizzo,'sfondo',s.sfondo,'benvenuto',s.benvenuto,
  'tavolo',v.servizio_tavolo,'colazione',v.colazione_nome,
  'menu',coalesce((select descrizione from public.bb_colazioni where id=v.colazione_id),(select descrizione from public.bb_menu where fascia=v.fascia)),
  'voci',case when v.colazione_id is not null then public.bb_voci_col_json(v.colazione_id) else public.bb_voci_json(v.fascia::int) end,
  'richieste',v.richieste,
  'extra',public.bb_extra_json(v),'extra_totale',v.extra_totale,'extra_da_pagare',public.bb_extra_da_pagare(v),
  'extra_pagati_giorni',to_jsonb(v.extra_pagati_giorni),
  'scelte',(select coalesce(json_object_agg(x.g::text,public.bb_scelta_giorno(v.id,x.g)),'{}'::json)
   from (select generate_series(v.data,v.data_fine,interval '1 day')::date g) x),
  'glutine',public.bb_glutine_pubblico(),'allergeni_elenco',public.bb_allergeni_elenco(),
  'bar',public.bb_bar_pubblico(),'oggi',public.bb_oggi())
 from public.bb_vouchers v join public.bb_strutture s on s.id=v.struttura_id
 where v.id=upper(trim(vid))
$$;
revoke all on function public.bb_ospite_json(text) from public,anon,authenticated;

create or replace function public.bb_ospite(vid text) returns json
language plpgsql security definer set search_path=public as $$
begin
 perform public.bb_limite_ospite();
 return public.bb_ospite_json(vid);
end $$;
revoke all on function public.bb_ospite(text) from public,anon,authenticated;
grant execute on function public.bb_ospite(text) to anon,authenticated;

create or replace function public.bb_ospite_salva(vid text,prichieste jsonb,pextra jsonb,pgiorno date default null) returns json
language plpgsql security definer set search_path=public as $$
declare v public.bb_vouchers; g date; ric jsonb; e jsonb; m jsonb; d jsonb; pr record; gl record; n int:=0;
 voci jsonb:='[]';tot numeric:=0;nuovo jsonb:='[]';alg jsonb:='[]';mod jsonb:='[]';nota text;tipo text;corrente public.bb_voucher_giorni;
 nuovi_glutine text[];vecchi_glutine text[];
begin
 perform public.bb_limite_ospite();
 select * into v from public.bb_vouchers where id=upper(trim(vid)) for update;
 if not found then return json_build_object('errore','Codice non trovato');end if;
 if v.annullato then raise exception 'Questa colazione è stata annullata';end if;
 if v.data_fine<public.bb_oggi() then raise exception 'Il soggiorno è terminato: non è più possibile modificare';end if;
 g:=coalesce(pgiorno,greatest(public.bb_oggi(),v.data));
 if g<v.data or g>v.data_fine then raise exception 'Il giorno scelto è fuori dal soggiorno (%–%)',to_char(v.data,'DD/MM'),to_char(v.data_fine,'DD/MM');end if;
 if g<public.bb_oggi() then raise exception 'Non si modificano colazioni di un giorno passato';end if;

 prichieste:=coalesce(prichieste,'{}'::jsonb);
 if jsonb_typeof(prichieste)<>'object' or length(prichieste::text)>6000 then raise exception 'Richiesta non valida o troppo lunga';end if;
 if exists(select 1 from jsonb_object_keys(prichieste) k where k not in ('allergie','nota','modifiche')) then raise exception 'Richiesta con campi non ammessi';end if;
 if prichieste?'allergie' then
  if jsonb_typeof(prichieste->'allergie')<>'array' then raise exception 'Allergie non valide';end if;
  select coalesce(jsonb_agg(distinct x),'[]'::jsonb) into alg from jsonb_array_elements_text(prichieste->'allergie') x
   where exists(select 1 from menu.menu_allergens al where al.id=x);
 end if;
 if prichieste?'nota' and jsonb_typeof(prichieste->'nota') not in ('string','null') then raise exception 'Nota non valida';end if;
 nota:=left(coalesce(prichieste->>'nota',''),500);
 if prichieste?'modifiche' then
  if jsonb_typeof(prichieste->'modifiche')<>'array' or jsonb_array_length(prichieste->'modifiche')>30 then raise exception 'Modifiche non valide';end if;
  for m in select * from jsonb_array_elements(prichieste->'modifiche') loop
   if jsonb_typeof(m)<>'object' then raise exception 'Modifica non valida';end if;
   if exists(select 1 from jsonb_object_keys(m) k where k not in ('voce','tipo','testo','chi','variante','diff')) then raise exception 'Modifica con campi non ammessi';end if;
   tipo:=m->>'tipo';
   if tipo is null or tipo not in ('senza','senza_glutine','nota') then raise exception 'Tipo di modifica non valido';end if;
   if coalesce(trim(m->>'voce'),'')='' then raise exception 'Modifica senza voce';end if;
   d:=jsonb_build_object('voce',left(m->>'voce',120),'tipo',tipo,'testo',left(coalesce(m->>'testo',''),120),'chi',left(coalesce(nullif(m->>'chi',''),'Tutti'),40));
   if tipo='senza_glutine' and coalesce(m->>'variante','')~'^[0-9a-fA-F-]{36}$' then
    select nome,differenza,id into gl from public.bb_senza_glutine where id=(m->>'variante')::uuid;
    if found then d:=d||jsonb_build_object('variante',gl.id,'diff',gl.differenza,'testo',gl.nome);end if;
   end if;
   mod:=mod||d;
  end loop;
 end if;
 ric:=jsonb_build_object('allergie',alg,'nota',nota,'modifiche','[]'::jsonb);
 select * into corrente from public.bb_voucher_giorni where voucher_id=v.id and giorno=g;

 if g=any(v.extra_pagati_giorni) then
  select coalesce(array_agg(x->>'variante' order by x->>'variante'),'{}') into nuovi_glutine
   from jsonb_array_elements(mod)x where x->>'tipo'='senza_glutine' and x?'variante';
  select coalesce(array_agg(x->>'variante' order by x->>'variante'),'{}') into vecchi_glutine
   from jsonb_array_elements(coalesce(corrente.modifiche,'[]'::jsonb))x where x->>'tipo'='senza_glutine' and x?'variante';
  if nuovi_glutine is distinct from vecchi_glutine then raise exception 'Gli extra del % sono già stati incassati: per cambiare il senza glutine rivolgiti al bar',to_char(g,'DD/MM');end if;
  if jsonb_typeof(coalesce(pextra,'[]'::jsonb))='array' and jsonb_array_length(coalesce(pextra,'[]'::jsonb))>0 then
   raise exception 'Gli extra del % sono già stati incassati: per cambiarli rivolgiti al bar',to_char(g,'DD/MM');end if;
  update public.bb_vouchers set richieste=ric,richieste_agg=now() where id=v.id;
  insert into public.bb_voucher_giorni(voucher_id,giorno,modifiche,extra,extra_totale,extra_pagato,aggiornato)
   values(v.id,g,mod,'[]'::jsonb,0,true,now())
   on conflict(voucher_id,giorno) do update set modifiche=excluded.modifiche,aggiornato=now();
  return public.bb_ospite_json(v.id);
 end if;

 if jsonb_typeof(coalesce(pextra,'[]'::jsonb))<>'array' then raise exception 'Ordine non valido';end if;
 for e in select * from jsonb_array_elements(coalesce(pextra,'[]'::jsonb)) loop
  n:=n+1;exit when n>40;
  if jsonb_typeof(e)<>'object' or coalesce(e->>'id','')!~'^\d{1,9}$' or coalesce(e->>'qta','')!~'^\d{1,2}$' then continue;end if;
  select p.id,p.nome,p.prezzo pz into pr from public.bb_prodotti p join public.bb_prod_cat c on c.id=p.cat_id
   where p.id=(e->>'id')::int and p.visibile and c.attivo and c.ospiti;
  if found and pr.pz>0 and (e->>'qta')::int between 1 and 20 then
   voci:=voci||jsonb_build_object('id',pr.id,'nome',pr.nome,'qta',(e->>'qta')::int,'prezzo',pr.pz);
   tot:=tot+pr.pz*(e->>'qta')::int;
  end if;
 end loop;
 for m in select * from jsonb_array_elements(mod) loop
  if m->>'tipo'='senza_glutine' and m?'variante' then
   voci:=voci||jsonb_build_object('glutine',true,'nome','Senza glutine: '||(m->>'testo'),'qta',1,'prezzo',(m->>'diff')::numeric);
   tot:=tot+(m->>'diff')::numeric;
  end if;
 end loop;
 select coalesce(jsonb_agg(ex order by ex->>'giorno'),'[]'::jsonb) into nuovo
  from jsonb_array_elements(coalesce(v.extra,'[]'::jsonb))ex where ex?'giorno' and (ex->>'giorno')::date<>g;
 if jsonb_array_length(voci)>0 then nuovo:=nuovo||jsonb_build_object('giorno',g,'voci',voci,'totale',tot);end if;
 update public.bb_vouchers set richieste=ric,extra=nuovo,
  extra_totale=(select coalesce(sum(coalesce((ex->>'totale')::numeric,0)),0) from jsonb_array_elements(nuovo)ex),richieste_agg=now() where id=v.id;
 insert into public.bb_voucher_giorni(voucher_id,giorno,modifiche,extra,extra_totale,extra_pagato,aggiornato)
  values(v.id,g,mod,'[]'::jsonb,0,false,now())
  on conflict(voucher_id,giorno) do update set modifiche=excluded.modifiche,aggiornato=now();
 return public.bb_ospite_json(v.id);
end $$;
revoke all on function public.bb_ospite_salva(text,jsonb,jsonb,date) from public,anon,authenticated;
grant execute on function public.bb_ospite_salva(text,jsonb,jsonb,date) to anon,authenticated;

create or replace function public.bb_tit_extra_incassato(p text,vid text,pgiorno date default null) returns json
language plpgsql security definer set search_path=public,extensions as $$
declare v public.bb_vouchers;g date;imp numeric;
begin
 perform public.bb_check_tit(p);g:=coalesce(pgiorno,public.bb_oggi());
 select * into v from public.bb_vouchers where id=upper(trim(vid)) for update;
 if not found then raise exception 'Codice non trovato';end if;
 select coalesce((d->>'totale')::numeric,0) into imp from jsonb_array_elements(coalesce(v.extra,'[]'::jsonb))d where (d->>'giorno')::date=g limit 1;
 if imp is null or imp<=0 then raise exception 'Nessun extra da incassare per il %',to_char(g,'DD/MM');end if;
 if g=any(v.extra_pagati_giorni) then raise exception 'Extra del % già incassati',to_char(g,'DD/MM');end if;
 update public.bb_vouchers set extra_pagati_giorni=array_append(extra_pagati_giorni,g) where id=v.id;
 update public.bb_voucher_giorni set extra_pagato=true,aggiornato=now() where voucher_id=v.id and giorno=g;
 return json_build_object('giorno',g,'incassato',imp);
end $$;
revoke all on function public.bb_tit_extra_incassato(text,text,date) from public,anon,authenticated;
grant execute on function public.bb_tit_extra_incassato(text,text,date) to anon,authenticated;

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
     exists(select 1 from public.bb_voucher_giorni g where g.voucher_id=x.id and g.modifiche<>'[]'::jsonb)) has_richieste,x.extra_totale,
    public.bb_extra_da_pagare(x) extra_da_pagare,x.servizio_tavolo,x.supplemento_tavolo
   from public.bb_vouchers x where x.struttura_id=sid) v));
end $$;
revoke all on function public.bb_alb_stato(uuid,text) from public, anon, authenticated;
grant execute on function public.bb_alb_stato(uuid,text) to anon, authenticated;

create or replace function public.bb_tit_stato(p text) returns json
language plpgsql security definer set search_path='' as $$
begin
 perform public.bb_check_tit(p);
 return json_build_object(
  'oggi',public.bb_oggi(),'bar',public.bb_bar_pubblico(),'menu',public.bb_menu_pubblico(),
  'allergeni',public.bb_menu_allergeni(),'sumup',public.bb_sumup_attivo(),
  'config',(select coalesce(json_object_agg(k,v),'{}'::json) from public.bb_config where k<>'tit_pin'),
  'voci',(select coalesce(json_object_agg(fascia::text,public.bb_voci_json(fascia)),'{}'::json) from public.bb_menu),
  'standard',public.bb_colazioni_json(null,false),
  'colazioni',(select coalesce(json_object_agg(id::text,public.bb_colazioni_json(id,false)),'{}'::json) from public.bb_strutture),
  'allergeni_elenco',public.bb_allergeni_elenco(),
  'camere',(select coalesce(json_object_agg(sid::text,cj),'{}'::json) from (
   select c.struttura_id sid,json_agg(json_build_object(
    'nome',c.nome,'ospiti',c.ospiti,'servizio_tavolo',c.servizio_tavolo) order by c.ordine) cj
   from public.bb_camere c group by c.struttura_id) x),
  'strutture',(select coalesce(json_agg(x order by x.nome),'[]'::json) from (
   select id,nome,indirizzo,telefono,email,demo,servizio_tavolo,accesso,invito_token,
    (pin_hash is not null and disattivata_il is null) attivo,disattivata_il,disattivata_motivo,
    public.bb_saldo(id) saldo from public.bb_strutture) x),
  'attesa',(select coalesce(json_agg(x order by x.t),'[]'::json) from (
   select m.id,m.t,m.importo,s.nome from public.bb_movimenti m
   join public.bb_strutture s on s.id=m.struttura_id
   where not m.confermato and m.sumup_id is null) x),
  'movimenti',(select coalesce(json_agg(x order by x.t desc),'[]'::json) from (
   select m.id,m.struttura_id,s.nome struttura,m.t,m.tipo,m.importo,m.nota,m.confermato
   from public.bb_movimenti m join public.bb_strutture s on s.id=m.struttura_id) x),
  'vouchers',(select coalesce(json_agg(x order by x.creato desc),'[]'::json) from (
   select v.id,v.struttura_id,s.nome struttura,v.fascia,v.qta,v.usate,v.data,v.data_fine,
    v.ospite,v.camera,v.ospiti,v.colazione_id,v.colazione_nome,v.creato,v.annullato,v.annullo_motivo,v.annullato_da,
    v.richieste,public.bb_extra_json(v) extra,v.extra_totale,public.bb_extra_da_pagare(v) extra_da_pagare,
    to_jsonb(v.extra_pagati_giorni) extra_pagati_giorni,v.servizio_tavolo,v.supplemento_tavolo,
    (select coalesce(json_object_agg(g.giorno::text,g.modifiche),'{}'::json) from public.bb_voucher_giorni g where g.voucher_id=v.id) modifiche_giorni,
    (select coalesce(json_agg((t at time zone 'Europe/Rome')::date),'[]'::json)
     from unnest(v.riscatti) t) riscatti
   from public.bb_vouchers v join public.bb_strutture s on s.id=v.struttura_id) x));
end $$;
revoke all on function public.bb_tit_stato(text) from public, anon, authenticated;
grant execute on function public.bb_tit_stato(text) to anon, authenticated;

create or replace function public.bb_tit_riscatta(p text,vid text) returns json language plpgsql security definer set search_path=public,extensions as $$
declare v public.bb_vouchers; s text; msg text; ok boolean:=false; oggi_n int; sc json;
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
 else update public.bb_vouchers set usate=usate+1, riscatti=riscatti||now() where id=v.id returning * into v; oggi_n:=oggi_n+1; ok:=true; msg:='Colazione consegnata ('||oggi_n||' di '||v.ospiti||' oggi)'; end if;
 select nome into s from public.bb_strutture where id=v.struttura_id;
 sc:=public.bb_scelta_giorno(v.id,public.bb_oggi());
 return json_build_object('ok',ok,'msg',msg,'voucher',json_build_object('id',v.id,'fascia',v.fascia,'qta',v.qta,'usate',v.usate,'ospite',v.ospite,'camera',v.camera,'ospiti',v.ospiti,'struttura',s,
   'data',v.data,'data_fine',v.data_fine,'colazione',v.colazione_nome,'tavolo',v.servizio_tavolo,
   'menu',coalesce((select descrizione from public.bb_colazioni where id=v.colazione_id),(select descrizione from public.bb_menu where fascia=v.fascia)),
   'voci',case when v.colazione_id is not null then public.bb_voci_col_json(v.colazione_id) else public.bb_voci_json(v.fascia::int) end,
   'richieste',sc->'richieste','extra',public.bb_extra_json(v),'extra_oggi',public.bb_extra_del_giorno(v,public.bb_oggi()),
   'extra_totale',v.extra_totale,'extra_da_pagare',public.bb_extra_da_pagare(v)));
end $$;
revoke all on function public.bb_tit_riscatta(text,text) from public;
grant execute on function public.bb_tit_riscatta(text,text) to anon, authenticated;

create or replace function public.bb_accoda_notifica_voucher() returns trigger
language plpgsql security definer set search_path='' as $$
declare nome_struttura text;periodo text;giorno_extra jsonb;
begin
 select s.nome into nome_struttura from public.bb_strutture s where s.id=new.struttura_id;
 periodo:=to_char(new.data,'DD/MM/YYYY')||case when new.data_fine is not null and new.data_fine<>new.data then ' - '||to_char(new.data_fine,'DD/MM/YYYY') else '' end;
 if tg_op='INSERT' then
  insert into public.bb_notifiche_operative(tipo,chiave,payload)
  values('prenotazione_hotel','prenotazione:'||new.id,jsonb_build_object(
   'voucher_id',new.id,'struttura',coalesce(nome_struttura,'Struttura'),'camera',coalesce(nullif(new.camera,''),'non indicata'),
   'periodo',periodo,'quantita',new.qta,'colazione',coalesce(new.colazione_nome,'Colazione'),
   'servizio_tavolo',coalesce(new.servizio_tavolo,false),'totale',round(coalesce(new.fascia,0)*coalesce(new.qta,0),2)))
  on conflict(chiave) do nothing;
 elsif new.extra is distinct from old.extra then
  select e into giorno_extra from jsonb_array_elements(coalesce(new.extra,'[]'::jsonb)) e
   where not exists(select 1 from jsonb_array_elements(coalesce(old.extra,'[]'::jsonb)) o where o=e) order by e->>'giorno' limit 1;
  if giorno_extra is not null and jsonb_array_length(coalesce(giorno_extra->'voci','[]'::jsonb))>0 then
   insert into public.bb_notifiche_operative(tipo,chiave,payload)
   values('extra_ospite','extra:'||new.id||':'||(giorno_extra->>'giorno')||':'||public.bb_tok_hash(giorno_extra::text),jsonb_build_object(
    'voucher_id',new.id,'struttura',coalesce(nome_struttura,'Struttura'),'camera',coalesce(nullif(new.camera,''),'non indicata'),
    'periodo',to_char((giorno_extra->>'giorno')::date,'DD/MM/YYYY'),'extra',giorno_extra->'voci','totale',coalesce((giorno_extra->>'totale')::numeric,0)))
   on conflict(chiave) do nothing;
  end if;
 end if;
 return new;
end $$;
revoke all on function public.bb_accoda_notifica_voucher() from public,anon,authenticated;
drop trigger if exists bb_voucher_giorni_notifica_extra on public.bb_voucher_giorni;
drop trigger if exists bb_vouchers_notifica_prenotazione on public.bb_vouchers;
create trigger bb_vouchers_notifica_prenotazione after insert on public.bb_vouchers
for each row execute function public.bb_accoda_notifica_voucher();
drop trigger if exists bb_vouchers_notifica_extra on public.bb_vouchers;
create trigger bb_vouchers_notifica_extra after update of extra on public.bb_vouchers
for each row when(old.extra is distinct from new.extra) execute function public.bb_accoda_notifica_voucher();
