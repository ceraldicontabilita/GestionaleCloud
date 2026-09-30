-- v14: servizio al tavolo / al banco per struttura
alter table bb_strutture add column if not exists servizio_tavolo boolean not null default false;

create or replace function bb_tit_tavolo_set(p text,sid uuid,val boolean) returns void language plpgsql security definer set search_path=public,extensions as $$
begin perform bb_check_tit(p); update bb_strutture set servizio_tavolo=coalesce(val,false) where id=sid; end $$;
grant execute on function bb_tit_tavolo_set(text,uuid,boolean) to anon,authenticated;

create or replace function bb_ospite(vid text) returns json language sql security definer set search_path=public as $$ select json_build_object('id',v.id,'qta',v.qta,'usate',v.usate,'data',v.data,'data_fine',v.data_fine,'ospite',v.ospite,'camera',v.camera,'ospiti',v.ospiti,'annullato',v.annullato,
   'struttura',s.nome,'indirizzo',s.indirizzo,'sfondo',s.sfondo,'benvenuto',s.benvenuto,'tavolo',s.servizio_tavolo,'colazione',v.colazione_nome,
   'menu',coalesce((select descrizione from bb_colazioni where id=v.colazione_id),(select descrizione from bb_menu where fascia=v.fascia)),
   'voci',case when v.colazione_id is not null then bb_voci_col_json(v.colazione_id) else bb_voci_json(v.fascia::int) end,
   'richieste',v.richieste,'extra',v.extra,'extra_totale',v.extra_totale,'extra_pagato',v.extra_pagato,'glutine',bb_glutine_pubblico(),
   'allergeni_elenco',bb_allergeni_elenco(),'bar',bb_bar_pubblico(),'oggi',bb_oggi())
   from bb_vouchers v join bb_strutture s on s.id=v.struttura_id where v.id=upper(trim(vid)) $$;

create or replace function bb_tit_stato(p text) returns json language plpgsql security definer set search_path=public,extensions as $$
begin
 perform bb_check_tit(p);
 return json_build_object(
  'oggi',bb_oggi(),'bar',bb_bar_pubblico(),'menu',bb_menu_pubblico(),'allergeni',bb_menu_allergeni(),'sumup',bb_sumup_attivo(),'pin_off',bb_pin_stato(),
  'config',(select coalesce(json_object_agg(k,v),'{}'::json) from bb_config where k<>'tit_pin'),
  'voci',(select coalesce(json_object_agg(fascia::text,bb_voci_json(fascia)),'{}'::json) from bb_menu),
  'colazioni',(select coalesce(json_object_agg(id::text,bb_colazioni_json(id,false)),'{}'::json) from bb_strutture),
  'allergeni_elenco',bb_allergeni_elenco(),
  'camere',(select coalesce(json_object_agg(sid::text,cj),'{}'::json) from (select c.struttura_id sid, json_agg(json_build_object('nome',c.nome,'ospiti',c.ospiti) order by c.ordine) cj from bb_camere c group by c.struttura_id) x),
  'strutture',(select coalesce(json_agg(x order by x.nome),'[]'::json) from (select id,nome,indirizzo,telefono,email,demo,servizio_tavolo,accesso,invito_token,(pin_hash is not null) attivo,bb_saldo(id) saldo from bb_strutture) x),
  'attesa',(select coalesce(json_agg(x order by x.t),'[]'::json) from (select m.id,m.t,m.importo,s.nome from bb_movimenti m join bb_strutture s on s.id=m.struttura_id where not m.confermato and m.sumup_id is null) x),
  'movimenti',(select coalesce(json_agg(x order by x.t desc),'[]'::json) from (select m.id,m.struttura_id,s.nome struttura,m.t,m.tipo,m.importo,m.nota,m.confermato from bb_movimenti m join bb_strutture s on s.id=m.struttura_id) x),
  'vouchers',(select coalesce(json_agg(x order by x.creato desc),'[]'::json) from (select v.id,v.struttura_id,s.nome struttura,v.fascia,v.qta,v.usate,v.data,v.data_fine,v.ospite,v.camera,v.ospiti,v.colazione_id,v.colazione_nome,v.creato,v.annullato,v.richieste,v.extra,v.extra_totale,v.extra_pagato,
     (select coalesce(json_agg((t at time zone 'Europe/Rome')::date),'[]'::json) from unnest(v.riscatti) t) riscatti
     from bb_vouchers v join bb_strutture s on s.id=v.struttura_id) x));
end $$;
