-- Ordini prodotti dell'hotel pagati dal borsellino (solo backend, segreto di runtime).
-- Addebito e rimborso sono idempotenti per riferimento ordine e serializzati sulla struttura,
-- cosi' due ordini insieme non possono spendere due volte lo stesso saldo.

create or replace function public.bb_ordine_prodotti_addebita(psid uuid, pimporto numeric, priferimento text)
returns json language plpgsql security definer set search_path='' as $$
declare v_nota text:='Ordine prodotti '||priferimento; disp numeric;
begin
 perform public.gc_assert_runtime_secret();
 if pimporto is null or pimporto<=0 then return json_build_object('errore','Importo non valido'); end if;
 perform 1 from public.bb_strutture where id=psid for update;
 if not found then return json_build_object('errore','Struttura non trovata'); end if;
 if exists(select 1 from public.bb_movimenti m where m.struttura_id=psid and m.tipo='prenotazione' and m.nota=v_nota) then
  return json_build_object('ok',true,'gia',true,'saldo',public.bb_saldo(psid));
 end if;
 disp:=public.bb_saldo(psid);
 if disp<pimporto then
  return json_build_object('errore','Saldo insufficiente: servono '||pimporto||' €, disponibili '||disp||' €');
 end if;
 insert into public.bb_movimenti(struttura_id,tipo,importo,nota) values(psid,'prenotazione',-pimporto,v_nota);
 return json_build_object('ok',true,'gia',false,'saldo',public.bb_saldo(psid));
end $$;

create or replace function public.bb_ordine_prodotti_rimborsa(psid uuid, pimporto numeric, priferimento text)
returns json language plpgsql security definer set search_path='' as $$
declare nota_add text:='Ordine prodotti '||priferimento; nota_rimb text:='Rimborso ordine prodotti '||priferimento;
begin
 perform public.gc_assert_runtime_secret();
 perform 1 from public.bb_strutture where id=psid for update;
 if not found then return json_build_object('errore','Struttura non trovata'); end if;
 if not exists(select 1 from public.bb_movimenti m where m.struttura_id=psid and m.tipo='prenotazione' and m.nota=nota_add) then
  return json_build_object('ok',true,'niente_da_rimborsare',true,'saldo',public.bb_saldo(psid));
 end if;
 if exists(select 1 from public.bb_movimenti m where m.struttura_id=psid and m.tipo='rimborso' and m.nota=nota_rimb) then
  return json_build_object('ok',true,'gia',true,'saldo',public.bb_saldo(psid));
 end if;
 insert into public.bb_movimenti(struttura_id,tipo,importo,nota) values(psid,'rimborso',pimporto,nota_rimb);
 return json_build_object('ok',true,'gia',false,'saldo',public.bb_saldo(psid));
end $$;

revoke all on function public.bb_ordine_prodotti_addebita(uuid,numeric,text) from public, anon, authenticated;
revoke all on function public.bb_ordine_prodotti_rimborsa(uuid,numeric,text) from public, anon, authenticated;
grant execute on function public.bb_ordine_prodotti_addebita(uuid,numeric,text) to anon;
grant execute on function public.bb_ordine_prodotti_rimborsa(uuid,numeric,text) to anon;


-- ===================== fasce orarie di ritiro configurabili dal titolare =====================
create or replace function public.bb_tit_config_set(p text, pk text, pv text) returns void language plpgsql security definer set search_path=public,extensions as $$
begin
 perform public.bb_check_tit(p);
 pv := trim(coalesce(pv,''));
 if pk not in ('bar_nome','bar_indirizzo','bar_tel','bar_orari','bar_maps','bar_email','bar_whatsapp','ricarica_min','ricarica_max','anticipo_max_giorni','ordini_limite_ora','msg_ospite','msg_invito','sumup_merchant_code','supplemento_tavolo','bar_lat','bar_lon','bar_raggio_m','ordini_fasce_ritiro') then raise exception 'Impostazione non valida'; end if;
 if pk='ricarica_min' and (pv !~ '^\d+$' or pv::int not between 1 and 1000) then raise exception 'Ricarica minima: numero tra 1 e 1000'; end if;
 if pk='ricarica_max' and (pv !~ '^\d+$' or pv::int not between 5 and 10000) then raise exception 'Ricarica massima: numero tra 5 e 10000'; end if;
 if pk='anticipo_max_giorni' and (pv !~ '^\d+$' or pv::int not between 1 and 365) then raise exception 'Giorni di anticipo: numero tra 1 e 365'; end if;
 if pk='ordini_limite_ora' and pv<>'' and pv !~ '^([01]\d|2[0-3]):[0-5]\d$' then raise exception 'Orario nel formato 20:00 (oppure vuoto)'; end if;
 if pk='supplemento_tavolo' then pv:=replace(pv,',','.'); if pv !~ '^\d{1,3}(\.\d{1,2})?$' then raise exception 'Supplemento: importo in euro, es. 1,50'; end if; end if;
 if pk='bar_maps' and pv<>'' and pv !~ '^https://' then raise exception 'Il link deve iniziare con https://'; end if;
 if pk in ('bar_lat','bar_lon') and pv<>'' then
  pv:=replace(pv,',','.');
  if pv !~ '^-?\d{1,3}(\.\d{1,8})?$' then raise exception 'Coordinata non valida: usa i gradi decimali, es. 40.842949'; end if;
  if pk='bar_lat' and abs(pv::numeric)>90 then raise exception 'Latitudine fuori intervallo'; end if;
  if pk='bar_lon' and abs(pv::numeric)>180 then raise exception 'Longitudine fuori intervallo'; end if;
 end if;
 if pk='bar_raggio_m' and (pv !~ '^\d+$' or pv::int not between 10 and 5000) then raise exception 'Raggio in metri: numero tra 10 e 5000'; end if;
 if pk='ordini_fasce_ritiro' and pv<>'' then
  select string_agg(h,',' order by h) into pv from (select distinct trim(x) h from unnest(string_to_array(pv,',')) x) t;
  if exists(select 1 from unnest(string_to_array(pv,',')) h where h !~ '^([01]\d|2[0-3]):[0-5]\d$') then raise exception 'Fasce di ritiro: orari nel formato 07:30, separati da virgola'; end if;
  if array_length(string_to_array(pv,','),1)>24 then raise exception 'Fasce di ritiro: al massimo 24 orari'; end if;
 end if;
 insert into public.bb_config values (pk,pv) on conflict (k) do update set v=excluded.v;
end $$;
revoke all on function public.bb_tit_config_set(text,text,text) from public;
grant execute on function public.bb_tit_config_set(text,text,text) to anon, authenticated;

-- Lettura delle fasce per il backend (nessun dato riservato): vuoto = predefinite del backend.
create or replace function public.bb_ordini_fasce_ritiro() returns json
language sql stable security definer set search_path='' as $$
 select coalesce(
  (select json_agg(h order by h) from (
    select trim(x) h from unnest(string_to_array((select v from public.bb_config where k='ordini_fasce_ritiro'),',')) x
  ) t where h ~ '^([01]\d|2[0-3]):[0-5]\d$'),
  '[]'::json)
$$;
revoke all on function public.bb_ordini_fasce_ritiro() from public;
grant execute on function public.bb_ordini_fasce_ritiro() to anon, authenticated;
