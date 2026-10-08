-- v29: un solo accesso cliente. Il QR/link del voucher apre anche il flusso
-- recensioni, mantenendo consensi separati e tracciando il voucher sorgente.

alter table bb_recensioni_visite
 add column if not exists voucher_id text references bb_vouchers(id) on delete set null;

create index if not exists bb_rec_visite_voucher
 on bb_recensioni_visite(voucher_id,creato desc)
 where voucher_id is not null;

create or replace function bb_recensioni_voucher_apri(vid text) returns json
language plpgsql security definer set search_path=public,extensions as $$
declare v bb_vouchers; s bb_strutture; r bb_recensioni_visite;
begin
 select * into v from bb_vouchers where id=upper(trim(vid));
 if not found then raise exception 'Codice colazione non valido'; end if;
 select * into s from bb_strutture where id=v.struttura_id;
 if not found then raise exception 'Struttura non disponibile'; end if;
 insert into bb_recensioni_visite(struttura_id,voucher_id,fonte,informativa_versione,informativa_url)
 values(v.struttura_id,v.id,'qr',bb_cfg('recensioni_informativa_versione','2026-10-01-v1'),bb_cfg('recensioni_informativa_url',''))
 returning * into r;
 return json_build_object('sessione',r.sessione,'creato',r.creato,'struttura',s.nome,
  'informativa_versione',r.informativa_versione,'informativa_url',r.informativa_url);
end $$;
revoke all on function bb_recensioni_voucher_apri(text) from public;
grant execute on function bb_recensioni_voucher_apri(text) to anon,authenticated;

create or replace function bb_recensioni_completa(psessione uuid) returns json
language plpgsql security definer set search_path=public,extensions as $$
declare v bb_recensioni_visite; rit int; pianificato boolean:=false; quando timestamptz;
begin
 select * into v from bb_recensioni_visite where sessione=psessione and scade>now();
 if not found then raise exception 'Sessione non valida o scaduta'; end if;
 if not exists(select 1 from bb_recensioni_consensi where visita_id=v.id and finalita='geolocalizzazione')
    or not exists(select 1 from bb_recensioni_consensi where visita_id=v.id and finalita='whatsapp') then
  raise exception 'Completa entrambe le scelte prima di proseguire';
 end if;
 update bb_recensioni_visite set completato=coalesce(completato,now()) where id=v.id;
 if bb_recensioni_consenso_attivo(v.id,'whatsapp') and v.telefono is not null then
  begin rit:=greatest(0,least(10080,bb_cfg('recensioni_ritardo_minuti','180')::int)); exception when others then rit:=180; end;
  quando:=now()+make_interval(mins=>rit);
  insert into bb_recensioni_inviti(visita_id,previsto) values(v.id,quando) on conflict(visita_id) do nothing;
  pianificato:=true;
 end if;
 return json_build_object('completato',true,'invito_pianificato',pianificato,'previsto',quando,
  'review_token',v.review_token,'google_url',bb_cfg('recensioni_google_url',''),
  'tripadvisor_url',bb_cfg('recensioni_tripadvisor_url',''));
end $$;
grant execute on function bb_recensioni_completa(uuid) to anon,authenticated;

