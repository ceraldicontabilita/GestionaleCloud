-- Pacchetti B&B prepagati: l'acquisto impegna il wallet canonico una sola
-- volta; ciascuna colazione usa un voucher monouso e il riscatto canonico.
-- Nessuna scadenza commerciale viene introdotta per i pacchetti.

alter table public.bb_strutture
 add column pacchetti_offerta_attiva boolean not null default false;

create table public.bb_pacchetti (
 id uuid primary key default extensions.gen_random_uuid(),
 struttura_id uuid not null references public.bb_strutture(id),
 qta integer not null check (qta between 1 and 1000),
 prezzo_unitario numeric(8,2) not null check (prezzo_unitario = 4),
 idempotenza text not null check (length(idempotenza) between 8 and 80),
 offerta jsonb not null,
 movimento_id uuid not null unique references public.bb_movimenti(id),
 creato timestamptz not null default now(),
 unique (struttura_id,idempotenza)
);
alter table public.bb_pacchetti enable row level security;
revoke all on public.bb_pacchetti from public,anon,authenticated;
create index bb_pacchetti_struttura on public.bb_pacchetti(struttura_id,creato desc);
alter table public.bb_vouchers
 add column pacchetto_id uuid references public.bb_pacchetti(id),
 add column pacchetto_scelta jsonb;
alter table public.bb_vouchers add constraint bb_vouchers_pacchetto_monouso
 check (pacchetto_id is null or (qta=1 and usate between 0 and 1 and not annullato));
create index bb_vouchers_pacchetto on public.bb_vouchers(pacchetto_id)
 where pacchetto_id is not null;

-- Un acquisto non è una prenotazione giornaliera: i QR non devono accodare
-- N notifiche di produzione né riportare il periodo tecnico "infinity".
drop trigger if exists bb_vouchers_notifica_prenotazione on public.bb_vouchers;
create trigger bb_vouchers_notifica_prenotazione after insert on public.bb_vouchers
 for each row when (new.pacchetto_id is null)
 execute function public.bb_accoda_notifica_voucher();

create function public.bb_pacchetto_offerta() returns jsonb
language plpgsql stable security definer set search_path='' as $$
declare formule jsonb; bevande jsonb; n integer;
begin
 select count(*) into n from menu.menu_products
 where id=any(array[152788,153797,153800,153801,153867,153868,
 153883,153887,153886,153756,153754,639287,153822,153895,
 153898,153901,153914,153915,153918,153928,153924,153925]) and visible;
 if n<>22 then
  raise exception 'Offerta colazione non disponibile: verificare i prodotti del menù' using errcode='PBB01';
 end if;
 select jsonb_agg(jsonb_build_object('codice',x.codice,'nome',x.nome,
  'prodotti',(select jsonb_agg(jsonb_build_object('id',p.id,'nome',p.name_it)
   order by array_position(x.ids,p.id)) from menu.menu_products p where p.id=any(x.ids)))
  order by x.ordine) into formule
 from (values
  (1,'classica','Italiana classica',array[152788,153797,153800,153801]),
  (2,'napoletana','Dolce napoletana',array[153868,153867]),
  (3,'salata','Colazione salata',array[153883,153887,153886])
 ) x(ordine,codice,nome,ids);
 select jsonb_agg(jsonb_build_object('id',p.id,'nome',p.name_it,
  'tipo',case when p.id=any(array[153756,153754,639287,153822]) then 'calda' else 'fredda' end)
  order by array_position(array[153756,153754,639287,153822,153895,153898,
   153901,153914,153915,153918,153928,153924,153925],p.id)) into bevande
 from menu.menu_products p where p.id=any(array[153756,153754,639287,153822,
 153895,153898,153901,153914,153915,153918,153928,153924,153925]);
 return jsonb_build_object('codice','COLAZIONE_BB_4_20261015',
  'nome','Colazione B&B €4','prezzo',4,'formule',formule,'bevande',bevande,
  'regole',jsonb_build_array('Un prodotto e una sola bevanda a scelta.',
   'Parigina abbinabile esclusivamente a una bottiglina di acqua da 33 cl.',
   'Ritiro al banco. Gli extra si pagano separatamente.'),
  'vincoli',jsonb_build_object('parigina_prodotto_id',153886,'parigina_bevanda_id',153895));
end $$;
revoke all on function public.bb_pacchetto_offerta() from public,anon,authenticated;

create function public.bb_pacchetto_json(pid uuid) returns jsonb
language sql stable security definer set search_path='' as $$
 select jsonb_build_object('id',k.id,'struttura_id',k.struttura_id,'struttura',s.nome,
  'qta',k.qta,'consumate',coalesce(sum(v.usate),0),
  'residue',k.qta-coalesce(sum(v.usate),0),'prezzo_unitario',k.prezzo_unitario,
  'totale',k.qta*k.prezzo_unitario,'creato',k.creato,'offerta',k.offerta,
  'vouchers',coalesce(jsonb_agg(jsonb_build_object('id',v.id,'qta',v.qta,
   'usate',v.usate,'annullato',v.annullato,'scelta',v.pacchetto_scelta,
   'riscatti',v.riscatti,'creato',v.creato) order by v.id)
   filter(where v.id is not null),'[]'::jsonb))
 from public.bb_pacchetti k join public.bb_strutture s on s.id=k.struttura_id
 left join public.bb_vouchers v on v.pacchetto_id=k.id
 where k.id=pid group by k.id,s.nome
$$;
revoke all on function public.bb_pacchetto_json(uuid) from public,anon,authenticated;

create function public.bb_pacchetti_json(sid uuid default null) returns jsonb
language plpgsql security definer set search_path='' as $$
declare offerta jsonb; abilitata boolean;
begin
 begin
  offerta:=public.bb_pacchetto_offerta()||jsonb_build_object('acquistabile',true);
 exception when sqlstate 'PBB01' then
  -- Il catalogo può cambiare, ma i buoni acquistati conservano la loro
  -- offerta e restano consultabili e utilizzabili con la scelta originaria.
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
  'pacchetti',coalesce((select jsonb_agg(public.bb_pacchetto_json(k.id) order by k.creato desc)
   from public.bb_pacchetti k where sid is null or k.struttura_id=sid),'[]'::jsonb));
end
$$;
revoke all on function public.bb_pacchetti_json(uuid) from public,anon,authenticated;

create function public.bb_pacchetto_acquista(sid uuid,pqta integer,pidempotenza text) returns jsonb
language plpgsql security definer set search_path='' as $$
declare s public.bb_strutture; k public.bb_pacchetti; kid uuid:=extensions.gen_random_uuid();
 mid uuid; vid text; i integer; offerta jsonb; totale numeric;
begin
 if pqta is null or pqta not between 1 and 1000 then raise exception 'Colazioni: da 1 a 1000'; end if;
 pidempotenza:=trim(coalesce(pidempotenza,''));
 if length(pidempotenza) not between 8 and 80 then raise exception 'Identificativo richiesta non valido'; end if;
 -- Lo stesso lock serializza con prenotazioni e altri acquisti dal wallet.
 select * into s from public.bb_strutture where id=sid and disattivata_il is null for update;
 if not found then raise exception 'Struttura non attiva'; end if;
 select * into k from public.bb_pacchetti where struttura_id=sid and idempotenza=pidempotenza;
 if found then
  if k.qta<>pqta then raise exception 'Richiesta già usata con quantità diversa'; end if;
  return jsonb_build_object('ok',true,'ripetuta',true,'pacchetto',public.bb_pacchetto_json(k.id),'saldo',public.bb_saldo(sid));
 end if;
 if not s.pacchetti_offerta_attiva then raise exception 'Offerta non attiva per questa struttura: contatta il bar'; end if;
 offerta:=public.bb_pacchetto_offerta(); totale:=4*pqta;
 if public.bb_saldo(sid)<totale then
  raise exception 'Saldo insufficiente: servono % €, disponibili % €',totale,public.bb_saldo(sid);
 end if;
 insert into public.bb_movimenti(struttura_id,tipo,importo,nota,confermato,riferimento_esterno)
 values(sid,'prenotazione',-totale,pqta||' colazioni B&B × €4 · pacchetto '||kid,true,'bb-pacchetto:'||kid)
 returning id into mid;
 insert into public.bb_pacchetti(id,struttura_id,qta,prezzo_unitario,idempotenza,offerta,movimento_id)
 values(kid,sid,pqta,4,pidempotenza,offerta,mid);
 for i in 1..pqta loop
  vid:=upper(encode(extensions.gen_random_bytes(16),'hex'));
  -- Le date tecniche soddisfano il vecchio schema, senza imporre una scadenza:
  -- i lettori e il riscatto dei pacchetti non applicano i limiti del soggiorno.
  insert into public.bb_vouchers(id,struttura_id,fascia,qta,usate,data,data_fine,
   ospite,camera,ospiti,colazione_nome,pacchetto_id)
  values(vid,sid,4,1,0,public.bb_oggi(),'infinity'::date,'Ospite','',1,offerta->>'nome',kid);
 end loop;
 return jsonb_build_object('ok',true,'ripetuta',false,'pacchetto',public.bb_pacchetto_json(kid),'saldo',public.bb_saldo(sid));
end $$;
revoke all on function public.bb_pacchetto_acquista(uuid,integer,text) from public,anon,authenticated;

create function public.bb_tit_pacchetto_crea(p text,sid uuid,pqta integer,pidempotenza text) returns jsonb
language plpgsql security definer set search_path='' as $$
begin
 perform public.bb_check_tit(p);
 return public.bb_pacchetto_acquista(sid,pqta,pidempotenza);
end $$;
create function public.bb_alb_pacchetto_acquista(sid uuid,p text,pqta integer,pidempotenza text) returns jsonb
language plpgsql security definer set search_path='' as $$
begin
 perform public.bb_check_alb(sid,p);
 return public.bb_pacchetto_acquista(sid,pqta,pidempotenza);
end $$;
create function public.bb_tit_pacchetti(p text,sid uuid default null) returns jsonb
language plpgsql security definer set search_path='' as $$
begin perform public.bb_check_tit(p); return public.bb_pacchetti_json(sid); end $$;
create function public.bb_alb_pacchetti(sid uuid,p text) returns jsonb
language plpgsql security definer set search_path='' as $$
begin perform public.bb_check_alb(sid,p); return public.bb_pacchetti_json(sid); end $$;

create function public.bb_tit_pacchetto_abilita(p text,sid uuid,pattiva boolean) returns jsonb
language plpgsql security definer set search_path='' as $$
begin
 perform public.bb_check_tit(p);
 if pattiva is null then raise exception 'Indica se attivare l''offerta'; end if;
 update public.bb_strutture set pacchetti_offerta_attiva=pattiva
  where id=sid and disattivata_il is null;
 if not found then raise exception 'Struttura non attiva'; end if;
 return jsonb_build_object('ok',true,'struttura_id',sid,'abilitata',pattiva);
end $$;

-- Il link ospite espone soltanto il singolo buono: nessun saldo o elenco hotel.
create function public.bb_pacchetto_voucher_json(vid text) returns jsonb
language sql stable security definer set search_path='' as $$
 select jsonb_build_object('id',v.id,'qta',v.qta,'usate',v.usate,'annullato',v.annullato,
  'struttura',s.nome,'pacchetto_id',k.id,'offerta',k.offerta,'scelta',v.pacchetto_scelta,
  'creato',v.creato,'bar',public.bb_bar_pubblico(),
  'stato',case when v.usate=1 then 'consumato' when v.pacchetto_scelta is null then 'da_scegliere' else 'da_ritirare' end)
 from public.bb_vouchers v join public.bb_pacchetti k on k.id=v.pacchetto_id
 join public.bb_strutture s on s.id=v.struttura_id where v.id=upper(trim(vid))
$$;
revoke all on function public.bb_pacchetto_voucher_json(text) from public,anon,authenticated;
create function public.bb_pacchetto_voucher(vid text) returns jsonb
language plpgsql security definer set search_path='' as $$
begin perform public.bb_limite_ospite(); return public.bb_pacchetto_voucher_json(vid); end $$;
create function public.bb_tit_pacchetto_voucher(p text,vid text) returns jsonb
language plpgsql security definer set search_path='' as $$
begin perform public.bb_check_tit(p); return public.bb_pacchetto_voucher_json(vid); end $$;

create function public.bb_pacchetto_scelta_salva(vid text,pformula text,pprodotto integer,pbevanda integer) returns jsonb
language plpgsql security definer set search_path='' as $$
declare v public.bb_vouchers; offerta jsonb; formula jsonb; prodotto jsonb; bevanda jsonb;
begin
 select * into v from public.bb_vouchers where id=upper(trim(vid)) and pacchetto_id is not null for update;
 if not found then raise exception 'Codice colazione non valido'; end if;
 if v.annullato or v.usate>0 then raise exception 'Buono già utilizzato o annullato'; end if;
 if exists(select 1 from public.bb_strutture where id=v.struttura_id and disattivata_il is not null) then raise exception 'Struttura non attiva'; end if;
 select k.offerta into offerta from public.bb_pacchetti k where k.id=v.pacchetto_id;
 select f into formula from jsonb_array_elements(offerta->'formule') f where f->>'codice'=pformula;
 if formula is null then raise exception 'Formula non prevista dall''offerta'; end if;
 select pr into prodotto from jsonb_array_elements(formula->'prodotti') pr where (pr->>'id')::integer=pprodotto;
 select b into bevanda from jsonb_array_elements(offerta->'bevande') b where (b->>'id')::integer=pbevanda;
 if prodotto is null or bevanda is null then raise exception 'Scegli un prodotto e una bevanda dell''offerta'; end if;
 if pprodotto=(offerta->'vincoli'->>'parigina_prodotto_id')::integer and pbevanda<>(offerta->'vincoli'->>'parigina_bevanda_id')::integer then
  raise exception 'La parigina è abbinabile soltanto all''acqua da 33 cl';
 end if;
 update public.bb_vouchers set pacchetto_scelta=jsonb_build_object('formula',pformula,
  'prodotto_id',pprodotto,'prodotto',prodotto->>'nome','bevanda_id',pbevanda,'bevanda',bevanda->>'nome'),
  richieste_agg=now() where id=v.id;
 return public.bb_pacchetto_voucher_json(v.id);
end $$;
revoke all on function public.bb_pacchetto_scelta_salva(text,text,integer,integer) from public,anon,authenticated;
create function public.bb_pacchetto_scelta(vid text,pformula text,pprodotto integer,pbevanda integer) returns jsonb
language plpgsql security definer set search_path='' as $$
begin
 perform public.bb_limite_ospite();
 return public.bb_pacchetto_scelta_salva(vid,pformula,pprodotto,pbevanda);
end $$;
create function public.bb_tit_pacchetto_consegna(p text,vid text,pformula text,pprodotto integer,pbevanda integer) returns json
language plpgsql security definer set search_path='' as $$
declare v public.bb_vouchers;
begin
 perform public.bb_check_tit(p);
 select * into v from public.bb_vouchers
  where id=upper(trim(vid)) and pacchetto_id is not null for update;
 if not found then raise exception 'Codice colazione non valido'; end if;
 if v.usate>=1 or v.annullato then return public.bb_tit_riscatta(p,v.id); end if;
 -- Scelta confermata al banco e consumo appartengono alla stessa transazione:
 -- nessuna modifica dell'ospite può inserirsi fra i due passaggi.
 perform public.bb_pacchetto_scelta_salva(v.id,pformula,pprodotto,pbevanda);
 return public.bb_tit_riscatta(p,v.id);
end $$;

-- Un solo writer dei consumi: per i buoni monouso si aggiorna la stessa riga
-- protetta da lock; una seconda scansione non può consumare un'altra colazione.
alter function public.bb_tit_riscatta(text,text) rename to bb_tit_riscatta_prima_pacchetti;
revoke all on function public.bb_tit_riscatta_prima_pacchetti(text,text) from public,anon,authenticated;
create function public.bb_tit_riscatta(p text,vid text) returns json
language plpgsql security definer set search_path='' as $$
declare v public.bb_vouchers; msg text; ok boolean:=false; conteggi jsonb; nome text;
begin
 perform public.bb_check_tit(p);
 select * into v from public.bb_vouchers where id=upper(trim(vid)) for update;
 if not found then return json_build_object('ok',false,'msg','Codice non trovato'); end if;
 if v.pacchetto_id is null then return public.bb_tit_riscatta_prima_pacchetti(p,vid); end if;
 if v.annullato then msg:='Buono annullato';
 elsif v.usate>=1 then msg:='Buono già utilizzato: nessuna colazione scalata';
 elsif exists(select 1 from public.bb_strutture where id=v.struttura_id and disattivata_il is not null) then msg:='Struttura non attiva';
 elsif v.pacchetto_scelta is null then msg:='Scegli formula, prodotto e bevanda prima della consegna';
 else
  update public.bb_vouchers set usate=1,riscatti=array_append(riscatti,now()) where id=v.id returning * into v;
  ok:=true;msg:='Colazione consegnata: buono utilizzato';
 end if;
 select s.nome into nome from public.bb_strutture s where s.id=v.struttura_id;
 conteggi:=public.bb_pacchetto_json(v.pacchetto_id)-'vouchers'-'offerta';
 return json_build_object('ok',ok,'msg',msg,'pacchetto',conteggi,
  'voucher',jsonb_build_object('id',v.id,'fascia',v.fascia,'qta',v.qta,'usate',v.usate,
   'ospite','Ospite','camera','','ospiti',1,'struttura',nome,'colazione',v.colazione_nome,
   'pacchetto_id',v.pacchetto_id,'pacchetto',conteggi,'scelta',v.pacchetto_scelta,
   'menu','Un prodotto e una sola bevanda a scelta',
   'voci',case when v.pacchetto_scelta is null then '[]'::jsonb else jsonb_build_array(
    jsonb_build_object('nome',v.pacchetto_scelta->>'prodotto','qta',1),
    jsonb_build_object('nome',v.pacchetto_scelta->>'bevanda','qta',1)) end));
end $$;

-- I mutatori dei soggiorni non possono annullare/rimborsare o modificare
-- questi buoni: l'acquisto e il numero di QR rimangono un unico fatto atomico.
alter function public.bb_annulla(text,text,text) rename to bb_annulla_prima_pacchetti;
revoke all on function public.bb_annulla_prima_pacchetti(text,text,text) from public,anon,authenticated;
create function public.bb_annulla(vid text,pmotivo text,pda text) returns json
language plpgsql security definer set search_path='' as $$
begin
 if exists(select 1 from public.bb_vouchers where id=upper(trim(vid)) and pacchetto_id is not null) then
  raise exception 'I buoni di un pacchetto non si annullano dal soggiorno: nessun rimborso eseguito';
 end if;
 return public.bb_annulla_prima_pacchetti(vid,pmotivo,pda);
end $$;
revoke all on function public.bb_annulla(text,text,text) from public,anon,authenticated;

alter function public.bb_ospite(text) rename to bb_ospite_prima_pacchetti;
revoke all on function public.bb_ospite_prima_pacchetti(text) from public,anon,authenticated;
create function public.bb_ospite(vid text) returns json
language plpgsql security definer set search_path='' as $$
begin
 if exists(select 1 from public.bb_vouchers where id=upper(trim(vid)) and pacchetto_id is not null) then
  return public.bb_pacchetto_voucher(vid)::json;
 end if;
 return public.bb_ospite_prima_pacchetti(vid);
end $$;

alter function public.bb_ospite_salva(text,jsonb,jsonb,date) rename to bb_ospite_salva_prima_pacchetti;
revoke all on function public.bb_ospite_salva_prima_pacchetti(text,jsonb,jsonb,date) from public,anon,authenticated;
create function public.bb_ospite_salva(vid text,prichieste jsonb,pextra jsonb,pgiorno date default null) returns json
language plpgsql security definer set search_path='' as $$
begin
 if exists(select 1 from public.bb_vouchers where id=upper(trim(vid)) and pacchetto_id is not null) then
  raise exception 'Usa la scelta del buono colazione per questo pacchetto';
 end if;
 return public.bb_ospite_salva_prima_pacchetti(vid,prichieste,pextra,pgiorno);
end $$;

alter function public.bb_ospite_menu_salva(text,date,jsonb) rename to bb_ospite_menu_salva_prima_pacchetti;
revoke all on function public.bb_ospite_menu_salva_prima_pacchetti(text,date,jsonb) from public,anon,authenticated;
create function public.bb_ospite_menu_salva(vid text,pgiorno date,righe jsonb) returns json
language plpgsql security definer set search_path='' as $$
begin
 if exists(select 1 from public.bb_vouchers where id=upper(trim(vid)) and pacchetto_id is not null) then
  raise exception 'Usa la scelta del buono colazione per questo pacchetto';
 end if;
 return public.bb_ospite_menu_salva_prima_pacchetti(vid,pgiorno,righe);
end $$;

-- Le viste del soggiorno e della produzione mantengono soltanto i soggiorni.
-- I pacchetti si leggono dalla proiezione dedicata, sempre sugli stessi voucher.
alter function public.bb_alb_stato(uuid,text) rename to bb_alb_stato_prima_pacchetti;
revoke all on function public.bb_alb_stato_prima_pacchetti(uuid,text) from public,anon,authenticated;
create function public.bb_alb_stato(sid uuid,p text) returns json
language plpgsql security definer set search_path='' as $$
declare stato jsonb;
begin
 stato:=public.bb_alb_stato_prima_pacchetti(sid,p)::jsonb;
 return (stato||jsonb_build_object('vouchers',coalesce((select jsonb_agg(x)
  from jsonb_array_elements(stato->'vouchers') x where not exists(
   select 1 from public.bb_vouchers v where v.id=x->>'id' and v.pacchetto_id is not null)),
  '[]'::jsonb)))::json;
end $$;
alter function public.bb_tit_stato(text) rename to bb_tit_stato_prima_pacchetti;
revoke all on function public.bb_tit_stato_prima_pacchetti(text) from public,anon,authenticated;
create function public.bb_tit_stato(p text) returns json
language plpgsql security definer set search_path='' as $$
declare stato jsonb;
begin
 stato:=public.bb_tit_stato_prima_pacchetti(p)::jsonb;
 return (stato||jsonb_build_object('vouchers',coalesce((select jsonb_agg(x)
  from jsonb_array_elements(stato->'vouchers') x where not exists(
   select 1 from public.bb_vouchers v where v.id=x->>'id' and v.pacchetto_id is not null)),
  '[]'::jsonb)))::json;
end $$;

revoke all on function public.bb_tit_pacchetto_crea(text,uuid,integer,text),
 public.bb_alb_pacchetto_acquista(uuid,text,integer,text),public.bb_tit_pacchetti(text,uuid),
 public.bb_tit_pacchetto_abilita(text,uuid,boolean),
 public.bb_tit_pacchetto_voucher(text,text),public.bb_tit_pacchetto_consegna(text,text,text,integer,integer),
 public.bb_alb_pacchetti(uuid,text),public.bb_pacchetto_voucher(text),
 public.bb_pacchetto_scelta(text,text,integer,integer),public.bb_tit_riscatta(text,text),
 public.bb_ospite(text),public.bb_ospite_salva(text,jsonb,jsonb,date),
 public.bb_ospite_menu_salva(text,date,jsonb),public.bb_alb_stato(uuid,text),
 public.bb_tit_stato(text) from public,anon,authenticated;
grant execute on function public.bb_tit_pacchetto_crea(text,uuid,integer,text),
 public.bb_alb_pacchetto_acquista(uuid,text,integer,text),public.bb_tit_pacchetti(text,uuid),
 public.bb_tit_pacchetto_abilita(text,uuid,boolean),
 public.bb_tit_pacchetto_voucher(text,text),public.bb_tit_pacchetto_consegna(text,text,text,integer,integer),
 public.bb_alb_pacchetti(uuid,text),public.bb_pacchetto_voucher(text),
 public.bb_pacchetto_scelta(text,text,integer,integer),public.bb_tit_riscatta(text,text),
 public.bb_ospite(text),public.bb_ospite_salva(text,jsonb,jsonb,date),
 public.bb_ospite_menu_salva(text,date,jsonb),public.bb_alb_stato(uuid,text),
 public.bb_tit_stato(text) to anon,authenticated;

notify pgrst,'reload schema';
