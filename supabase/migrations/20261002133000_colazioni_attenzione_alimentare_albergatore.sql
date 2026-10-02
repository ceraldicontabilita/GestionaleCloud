-- L'albergatore puo' segnalare allergie o intolleranze per la camera.
-- E' una nota di attenzione: non modifica ingredienti, allergeni o tracciabilita'.
create or replace function public.bb_alb_crea_soggiorni(sid uuid,p text,righe jsonb) returns json
language plpgsql security definer set search_path='' as $$
declare s public.bb_strutture; r jsonb; vid text; oc int; cam text; dal date; al date;
 gg int; c public.bb_colazioni; tot numeric:=0; supp numeric; tav boolean; ids jsonb:='[]';
 lim text; ora_lim timestamptz; mx int; attenzione text;
begin
 perform public.bb_check_alb(sid,p);
 select * into s from public.bb_strutture where id=sid for update;
 if jsonb_typeof(righe)<>'array' or jsonb_array_length(righe)=0 or jsonb_array_length(righe)>150 then
  raise exception 'Seleziona almeno una camera';
 end if;
 lim:=public.bb_cfg('ordini_limite_ora','');
 mx:=public.bb_cfg('anticipo_max_giorni','60')::int;
 for r in select * from jsonb_array_elements(righe) loop
  oc:=coalesce((r->>'ospiti')::int,1);
  if oc<1 or oc>10 then raise exception 'Ospiti per camera: da 1 a 10'; end if;
  attenzione:=trim(coalesce(r->>'attenzione_alimentare',''));
  if length(attenzione)>500 then raise exception 'Segnalazione alimentare troppo lunga'; end if;
  dal:=(r->>'dal')::date; al:=coalesce((r->>'al')::date,dal);
  if dal<public.bb_oggi() then raise exception 'La data di arrivo è nel passato'; end if;
  if al<dal then raise exception 'La data di partenza è prima dell''arrivo'; end if;
  gg:=al-dal+1;
  if gg>31 then raise exception 'Soggiorno massimo 31 giorni'; end if;
  if al>public.bb_oggi()+mx then raise exception 'Puoi prenotare al massimo % giorni prima',mx; end if;
  if lim<>'' then
   ora_lim:=((dal-1)::text||' '||lim)::timestamp at time zone 'Europe/Rome';
   if now()>ora_lim then
    raise exception 'Le colazioni dal % vanno ordinate entro le % del giorno prima',to_char(dal,'DD/MM'),lim;
   end if;
  end if;
  select * into c from public.bb_colazioni
   where id=nullif(r->>'colazione_id','')::uuid and struttura_id=sid and attiva;
  if not found then raise exception 'Scegli una colazione disponibile per ogni camera'; end if;
  tav:=coalesce((r->>'servizio_tavolo')::boolean,false);
  supp:=case when tav then public.bb_supplemento_tavolo() else 0 end;
  tot:=tot+(c.prezzo+supp)*oc*gg;
 end loop;
 if public.bb_saldo(sid)<tot then
  raise exception 'Saldo insufficiente: servono % €, disponibili % €',tot,public.bb_saldo(sid);
 end if;
 for r in select * from jsonb_array_elements(righe) loop
  oc:=(r->>'ospiti')::int; dal:=(r->>'dal')::date; al:=coalesce((r->>'al')::date,dal); gg:=al-dal+1;
  select * into c from public.bb_colazioni where id=(r->>'colazione_id')::uuid and struttura_id=sid;
  tav:=coalesce((r->>'servizio_tavolo')::boolean,false);
  supp:=case when tav then public.bb_supplemento_tavolo() else 0 end;
  cam:=left(trim(coalesce(r->>'camera','')),40);
  attenzione:=left(trim(coalesce(r->>'attenzione_alimentare','')),500);
  vid:=upper(substr(encode(extensions.gen_random_bytes(8),'hex'),1,10));
  insert into public.bb_vouchers(
   id,struttura_id,fascia,qta,data,data_fine,ospite,camera,ospiti,colazione_id,
   colazione_nome,servizio_tavolo,supplemento_tavolo,richieste)
  values (
   vid,sid,c.prezzo+supp,oc*gg,dal,al,coalesce(nullif(cam,''),'Ospite'),cam,oc,c.id,
   c.nome,tav,supp,case when attenzione='' then '{}'::jsonb else jsonb_build_object('nota',attenzione) end);
  insert into public.bb_movimenti(struttura_id,tipo,importo,nota)
  values (
   sid,'prenotazione',-(c.prezzo+supp)*oc*gg,
   coalesce(nullif(cam,'')||' · ','')||oc||' ospiti × '||gg||' giorni · '||c.nome||
   case when tav then ' (tavolo +'||supp||' €)' else ' (banco)' end);
  ids:=ids||jsonb_build_object('id',vid,'camera',cam,'nome',coalesce(nullif(cam,''),'Ospite'));
 end loop;
 return json_build_object('creati',ids,'totale',tot);
end $$;

revoke all on function public.bb_alb_crea_soggiorni(uuid,text,jsonb) from public, anon, authenticated;
grant execute on function public.bb_alb_crea_soggiorni(uuid,text,jsonb) to anon, authenticated;

