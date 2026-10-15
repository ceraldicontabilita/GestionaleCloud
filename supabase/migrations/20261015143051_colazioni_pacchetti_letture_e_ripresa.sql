-- Correzioni additive dei pacchetti: la prima migrazione è già applicata.
-- Una sola quota per apertura ospite; nessun QR pacchetto viene serializzato
-- nei riepiloghi soggiorno; rifiuti di acquisto definitivi riconoscibili dal client.

create or replace function public.bb_ospite(vid text) returns json
language plpgsql security definer set search_path='' as $$
declare pacchetto jsonb;
begin
 perform public.bb_limite_ospite();
 pacchetto:=public.bb_pacchetto_voucher_json(vid);
 if pacchetto is not null then return pacchetto::json; end if;
 return public.bb_ospite_json(vid);
end $$;
revoke all on function public.bb_ospite(text) from public,anon,authenticated;
grant execute on function public.bb_ospite(text) to anon,authenticated;

-- Gli alias privati sono le definizioni legacy congelate dalla prima migrazione.
-- Ripristiniamo gli ingressi diretti cambiando SOLO il predicato dei voucher.
-- La precondizione esatta interrompe la migrazione su una base non riconosciuta:
-- nessuna approssimazione e nessuna trasformazione durante le richieste runtime.
do $migrazione$
declare ddl text; marker text;
begin
 ddl:=pg_get_functiondef('public.bb_alb_stato_prima_pacchetti(uuid,text)'::regprocedure);
 marker:='from public.bb_vouchers x where x.struttura_id=sid';
 if strpos(ddl,marker)=0 or strpos(ddl,'FUNCTION public.bb_alb_stato_prima_pacchetti(')=0 then
  raise exception 'Definizione bb_alb_stato precedente non riconosciuta';
 end if;
 ddl:=replace(ddl,'FUNCTION public.bb_alb_stato_prima_pacchetti(','FUNCTION public.bb_alb_stato(');
 ddl:=replace(ddl,marker,marker||' and x.pacchetto_id is null');
 execute ddl;

 ddl:=pg_get_functiondef('public.bb_tit_stato_prima_pacchetti(text)'::regprocedure);
 marker:='from public.bb_vouchers v join public.bb_strutture s on s.id=v.struttura_id';
 if strpos(ddl,marker)=0 or strpos(ddl,'FUNCTION public.bb_tit_stato_prima_pacchetti(')=0 then
  raise exception 'Definizione bb_tit_stato precedente non riconosciuta';
 end if;
 ddl:=replace(ddl,'FUNCTION public.bb_tit_stato_prima_pacchetti(','FUNCTION public.bb_tit_stato(');
 ddl:=replace(ddl,marker,marker||' where v.pacchetto_id is null');
 execute ddl;
end $migrazione$;
revoke all on function public.bb_alb_stato(uuid,text),public.bb_tit_stato(text) from public,anon,authenticated;
grant execute on function public.bb_alb_stato(uuid,text),public.bb_tit_stato(text) to anon,authenticated;

-- Questi codici significano: identità verificata e nessun acquisto con quella
-- richiesta. La verifica di idempotenza rimane PRIMA di abilitazione/catalogo/saldo.
-- Errori di sessione o di trasporto non autorizzano invece a scartare il token.
do $migrazione$
declare ddl text; marker text;
begin
 ddl:=pg_get_functiondef('public.bb_pacchetto_acquista(uuid,integer,text)'::regprocedure);
 marker:='raise exception ''Offerta non attiva per questa struttura: contatta il bar'';';
 if strpos(ddl,marker)=0 then raise exception 'Controllo abilitazione pacchetto non riconosciuto'; end if;
 ddl:=replace(ddl,marker,'raise exception ''Offerta non attiva per questa struttura: contatta il bar'' using errcode=''PBB03'';');
 marker:='raise exception ''Saldo insufficiente: servono % €, disponibili % €'',totale,public.bb_saldo(sid);';
 if strpos(ddl,marker)=0 then raise exception 'Controllo saldo pacchetto non riconosciuto'; end if;
 ddl:=replace(ddl,marker,'raise exception ''Saldo insufficiente: servono % €, disponibili % €'',totale,public.bb_saldo(sid) using errcode=''PBB02'';');
 execute ddl;
end $migrazione$;
revoke all on function public.bb_pacchetto_acquista(uuid,integer,text) from public,anon,authenticated;

notify pgrst,'reload schema';
