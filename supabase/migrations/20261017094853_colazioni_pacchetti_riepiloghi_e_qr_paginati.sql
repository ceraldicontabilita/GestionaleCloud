-- Riepiloghi senza QR né copie dell'offerta. I contatori continuano a derivare
-- dall'unico registro dei consumi; nessun acquisto, ricarica o consumo è creato.
-- I nuovi ingressi di dettaglio richiedono la stessa sessione dei riepiloghi e
-- leggono i QR soltanto per il pacchetto richiesto, con cursore e limite finito.

create index bb_vouchers_pacchetto_pagina
 on public.bb_vouchers(pacchetto_id,id) where pacchetto_id is not null;

-- Anche le risposte di acquisto/retry e riscatto usano questa proiezione:
-- sottrarre la chiave "vouchers" dopo averla aggregata era comunque costoso.
create or replace function public.bb_pacchetto_json(pid uuid) returns jsonb
language sql stable security definer set search_path='' as $$
 select jsonb_build_object('id',k.id,'struttura_id',k.struttura_id,'struttura',s.nome,
  'qta',k.qta,'consumate',coalesce(sum(v.usate),0),
  'residue',k.qta-coalesce(sum(v.usate),0),'prezzo_unitario',k.prezzo_unitario,
  'totale',k.qta*k.prezzo_unitario,'creato',k.creato)
 from public.bb_pacchetti k join public.bb_strutture s on s.id=k.struttura_id
 left join public.bb_vouchers v on v.pacchetto_id=k.id
 where k.id=pid group by k.id,s.nome
$$;
revoke all on function public.bb_pacchetto_json(uuid) from public,anon,authenticated;

create or replace function public.bb_pacchetti_json(sid uuid default null) returns jsonb
language plpgsql security definer set search_path='' as $$
declare offerta jsonb; abilitata boolean;
begin
 begin
  offerta:=public.bb_pacchetto_offerta()||jsonb_build_object('acquistabile',true);
 exception when sqlstate 'PBB01' then
  offerta:=jsonb_build_object('codice','COLAZIONE_BB_4_20261015',
   'nome','Colazione B&B €4','prezzo',4,'acquistabile',false,
   'motivo',sqlerrm,'formule','[]'::jsonb,'bevande','[]'::jsonb);
 end;
 if sid is not null then
  select s.pacchetti_offerta_attiva and s.disattivata_il is null into abilitata
   from public.bb_strutture s where s.id=sid;
  abilitata:=coalesce(abilitata,false);
  offerta:=offerta||jsonb_build_object('abilitata',abilitata,
   'acquistabile',abilitata and (offerta->>'acquistabile')::boolean);
  if not abilitata then
   offerta:=offerta||jsonb_build_object('motivo','Offerta non attiva per questa struttura: contatta il bar');
  end if;
 end if;
 return jsonb_build_object('offerta',offerta,
  'strutture_abilitate',coalesce((select jsonb_agg(s.id) from public.bb_strutture s
   where (sid is null or s.id=sid) and s.pacchetti_offerta_attiva and s.disattivata_il is null),'[]'::jsonb),
  'pacchetti',coalesce((select jsonb_agg(x.riepilogo order by x.creato desc,x.id)
   from (
    select k.id,k.creato,jsonb_build_object('id',k.id,'struttura_id',k.struttura_id,
     'struttura',s.nome,'qta',k.qta,'consumate',coalesce(sum(v.usate),0),
     'residue',k.qta-coalesce(sum(v.usate),0),'prezzo_unitario',k.prezzo_unitario,
     'totale',k.qta*k.prezzo_unitario,'creato',k.creato) as riepilogo
    from public.bb_pacchetti k join public.bb_strutture s on s.id=k.struttura_id
    left join public.bb_vouchers v on v.pacchetto_id=k.id
    where sid is null or k.struttura_id=sid
    group by k.id,s.nome
   ) x),'[]'::jsonb));
end $$;
revoke all on function public.bb_pacchetti_json(uuid) from public,anon,authenticated;

-- La home riceve soltanto tre numeri, indipendenti dal numero di pacchetti.
create function public.bb_pacchetti_totali_json(sid uuid default null) returns jsonb
language sql stable security definer set search_path='' as $$
 with pacchetti as materialized (
  select k.id,k.qta from public.bb_pacchetti k where sid is null or k.struttura_id=sid
 ), conteggi as (
  select coalesce((select sum(k.qta) from pacchetti k),0) as acquistate,
   coalesce((select sum(v.usate) from public.bb_vouchers v
    join pacchetti k on k.id=v.pacchetto_id),0) as consumate
 )
 select jsonb_build_object('qta',acquistate,'consumate',consumate,'residue',acquistate-consumate)
 from conteggi
$$;
revoke all on function public.bb_pacchetti_totali_json(uuid) from public,anon,authenticated;

create function public.bb_alb_pacchetti_totali(sid uuid,p text) returns jsonb
language plpgsql security definer set search_path='' as $$
begin
 perform public.bb_check_alb(sid,p);
 return public.bb_pacchetti_totali_json(sid);
end $$;
create function public.bb_tit_pacchetti_totali(p text) returns jsonb
language plpgsql security definer set search_path='' as $$
begin
 perform public.bb_check_tit(p);
 return public.bb_pacchetti_totali_json();
end $$;
revoke all on function public.bb_alb_pacchetti_totali(uuid,text),
 public.bb_tit_pacchetti_totali(text) from public,anon,authenticated;
grant execute on function public.bb_alb_pacchetti_totali(uuid,text),
 public.bb_tit_pacchetti_totali(text) to anon,authenticated;

create function public.bb_pacchetto_dettaglio_json(pid uuid,pdopo text default null,plimite integer default 50)
 returns jsonb language plpgsql stable security definer set search_path='' as $$
declare riepilogo jsonb; offerta jsonb; pagina jsonb;
begin
 if plimite is null or plimite not between 1 and 100 then
  raise exception 'Pagina QR: da 1 a 100 buoni';
 end if;
 riepilogo:=public.bb_pacchetto_json(pid);
 if riepilogo is null then raise exception 'Pacchetto non disponibile'; end if;
 if pdopo is not null and not exists(
  select 1 from public.bb_vouchers v where v.pacchetto_id=pid and v.id=pdopo
 ) then raise exception 'Cursore pagina QR non valido'; end if;
 select k.offerta into offerta from public.bb_pacchetti k where k.id=pid;
 -- Si legge al più un elemento aggiuntivo per sapere se esiste un'altra pagina;
 -- il JSON viene costruito esclusivamente sui buoni della pagina visibile.
 with candidati as materialized (
  select v.id,v.qta,v.usate,v.annullato,v.pacchetto_scelta,v.riscatti,v.creato
  from public.bb_vouchers v where v.pacchetto_id=pid and (pdopo is null or v.id>pdopo)
  order by v.id limit plimite+1
 ), visibili as (
  select * from candidati order by id limit plimite
 )
 select jsonb_build_object('vouchers',coalesce(jsonb_agg(jsonb_build_object(
  'id',v.id,'qta',v.qta,'usate',v.usate,'annullato',v.annullato,
  'scelta',v.pacchetto_scelta,'riscatti',v.riscatti,'creato',v.creato) order by v.id),'[]'::jsonb),
  'prossimo',case when (select count(*) from candidati)>plimite then max(v.id) end,
  'limite',plimite) into pagina from visibili v;
 return riepilogo||jsonb_build_object('offerta',offerta)||pagina;
end $$;
revoke all on function public.bb_pacchetto_dettaglio_json(uuid,text,integer)
 from public,anon,authenticated;

create function public.bb_alb_pacchetto_dettaglio(sid uuid,p text,pid uuid,
 pdopo text default null,plimite integer default 50) returns jsonb
language plpgsql security definer set search_path='' as $$
begin
 perform public.bb_check_alb(sid,p);
 if not exists(select 1 from public.bb_pacchetti k where k.id=pid and k.struttura_id=sid) then
  raise exception 'Pacchetto non disponibile';
 end if;
 return public.bb_pacchetto_dettaglio_json(pid,pdopo,plimite);
end $$;
create function public.bb_tit_pacchetto_dettaglio(p text,pid uuid,
 pdopo text default null,plimite integer default 50) returns jsonb
language plpgsql security definer set search_path='' as $$
begin
 perform public.bb_check_tit(p);
 return public.bb_pacchetto_dettaglio_json(pid,pdopo,plimite);
end $$;
revoke all on function public.bb_alb_pacchetto_dettaglio(uuid,text,uuid,text,integer),
 public.bb_tit_pacchetto_dettaglio(text,uuid,text,integer) from public,anon,authenticated;
grant execute on function public.bb_alb_pacchetto_dettaglio(uuid,text,uuid,text,integer),
 public.bb_tit_pacchetto_dettaglio(text,uuid,text,integer) to anon,authenticated;

notify pgrst,'reload schema';
