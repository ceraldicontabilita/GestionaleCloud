-- L'albergatore condivide il link recensioni della propria struttura; alla
-- revoca i dati facoltativi sono rimossi, non soltanto marcati come revocati.

alter table public.bb_recensioni_visite
 drop constraint if exists bb_recensioni_visite_fonte_check;
alter table public.bb_recensioni_visite
 add constraint bb_recensioni_visite_fonte_check
 check (fonte in ('qr','nfc','wifi','link','whatsapp'));

create or replace function public.bb_recensioni_visita_apri(ptoken uuid, pfonte text) returns json
language plpgsql security definer set search_path=public,extensions as $$
declare l public.bb_recensioni_link; v public.bb_recensioni_visite;
begin
 select * into l from public.bb_recensioni_link where token=ptoken and attivo;
 if not found then raise exception 'Link non valido o disattivato'; end if;
 if pfonte not in ('qr','nfc','wifi','link','whatsapp') then pfonte:='link'; end if;
 if (select count(*) from public.bb_recensioni_visite where struttura_id=l.struttura_id and creato>now()-interval '1 hour')>=120 then
  raise exception 'Troppe richieste: riprova piu tardi';
 end if;
 insert into public.bb_recensioni_visite(struttura_id,fonte,informativa_versione,informativa_url)
 values(l.struttura_id,pfonte,public.bb_cfg('recensioni_informativa_versione','2026-10-01-v1'),public.bb_cfg('recensioni_informativa_url','')) returning * into v;
 return json_build_object('sessione',v.sessione,'creato',v.creato);
end $$;
revoke all on function public.bb_recensioni_visita_apri(uuid,text) from public,anon,authenticated;
grant execute on function public.bb_recensioni_visita_apri(uuid,text) to anon,authenticated;

create or replace function public.bb_alb_recensioni_link(sid uuid,p text) returns uuid
language plpgsql security definer set search_path=public,extensions as $$
declare l public.bb_recensioni_link;
begin
 perform public.bb_check_alb(sid,p);
 insert into public.bb_recensioni_link(struttura_id) values(sid) on conflict(struttura_id) do nothing;
 select * into l from public.bb_recensioni_link where struttura_id=sid and attivo;
 if not found then raise exception 'Inviti recensione disattivati per questa struttura'; end if;
 return l.token;
end $$;
revoke all on function public.bb_alb_recensioni_link(uuid,text) from public,anon,authenticated;
grant execute on function public.bb_alb_recensioni_link(uuid,text) to anon,authenticated;

create or replace function public.bb_recensioni_revoca(psessione uuid, pfinalita text, pclient text default '') returns json
language plpgsql security definer set search_path=public,extensions as $$
declare v public.bb_recensioni_visite;
begin
 select * into v from public.bb_recensioni_visite where sessione=psessione and scade>now();
 if not found then raise exception 'Sessione non valida o scaduta'; end if;
 if pfinalita not in ('geolocalizzazione','whatsapp') then raise exception 'Finalita non valida'; end if;
 insert into public.bb_recensioni_consensi(visita_id,finalita,azione,informativa_versione,fonte,ip,client,dettagli)
 values(v.id,pfinalita,'revocato',v.informativa_versione,'pagina_colazione',public.bb_ip(),left(coalesce(pclient,''),300),jsonb_build_object('azione_esplicita',true));
 if pfinalita='whatsapp' then
  update public.bb_recensioni_inviti set stato='annullato',aggiornato=now() where visita_id=v.id and stato in ('in_attesa','errore');
  update public.bb_recensioni_visite set telefono=null where id=v.id;
 else
  delete from public.bb_recensioni_posizioni where visita_id=v.id;
 end if;
 return json_build_object('revocato',true,'avvenuto',now());
end $$;
revoke all on function public.bb_recensioni_revoca(uuid,text,text) from public,anon,authenticated;
grant execute on function public.bb_recensioni_revoca(uuid,text,text) to anon,authenticated;
