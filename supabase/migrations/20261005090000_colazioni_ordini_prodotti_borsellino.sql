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
