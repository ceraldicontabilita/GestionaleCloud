-- v22: dati fiscali degli albergatori e lista «fatture da emettere» per ogni ricarica pagata.
-- La fattura si emette a mano da SumUp Fatture (nessuna API pubblica): qui si prepara e si tiene l'archivio.

alter table bb_strutture
  add column if not exists ragione_sociale text not null default '',
  add column if not exists piva text not null default '',
  add column if not exists codice_fiscale text not null default '',
  add column if not exists fatt_indirizzo text not null default '',
  add column if not exists fatt_cap text not null default '',
  add column if not exists fatt_comune text not null default '',
  add column if not exists fatt_provincia text not null default '',
  add column if not exists codice_destinatario text not null default '0000000',
  add column if not exists pec text not null default '';

create table if not exists bb_fatture_da_emettere (
  id uuid primary key default gen_random_uuid(),
  struttura_id uuid not null references bb_strutture(id) on delete cascade,
  movimento_id uuid not null unique references bb_movimenti(id) on delete cascade,
  importo numeric(10,2) not null,
  metodo text not null default 'bar',
  pagata_il timestamptz not null default now(),
  stato text not null default 'da_emettere' check (stato in ('da_emettere','emessa','non_dovuta')),
  numero text not null default '',
  data_emissione date,
  nota text not null default '',
  creato timestamptz not null default now());
create index if not exists bb_fatture_stato on bb_fatture_da_emettere(stato, pagata_il);
alter table bb_fatture_da_emettere enable row level security;

-- ogni ricarica che diventa confermata genera la riga «da emettere» (SumUp, contanti al bar, ricarica registrata a mano)
create or replace function bb_trg_fattura_ricarica() returns trigger language plpgsql security definer set search_path=public as $$
begin
 if NEW.tipo='ricarica' and NEW.confermato and NEW.importo>0 and (TG_OP='INSERT' or not coalesce(OLD.confermato,false)) then
  insert into bb_fatture_da_emettere(struttura_id,movimento_id,importo,metodo,pagata_il)
  values (NEW.struttura_id,NEW.id,NEW.importo,case when NEW.sumup_id is not null then 'carta SumUp' else 'bar' end,NEW.t)
  on conflict (movimento_id) do nothing;
 end if;
 return NEW;
end $$;
drop trigger if exists bb_trg_fattura_ricarica on bb_movimenti;
create trigger bb_trg_fattura_ricarica after insert or update of confermato on bb_movimenti
  for each row execute function bb_trg_fattura_ricarica();

-- ricariche già confermate prima di oggi
insert into bb_fatture_da_emettere(struttura_id,movimento_id,importo,metodo,pagata_il)
select m.struttura_id,m.id,m.importo,case when m.sumup_id is not null then 'carta SumUp' else 'bar' end,m.t
from bb_movimenti m where m.tipo='ricarica' and m.confermato and m.importo>0
on conflict (movimento_id) do nothing;

-- dati fiscali completi?
create or replace function bb_fiscali_ok(s bb_strutture) returns boolean language sql immutable as $$
 select s.ragione_sociale<>'' and (s.piva<>'' or s.codice_fiscale<>'') and s.fatt_indirizzo<>'' and s.fatt_cap<>'' and s.fatt_comune<>'' and s.fatt_provincia<>'' $$;

create or replace function bb_fiscali_json(s bb_strutture) returns json language sql immutable as $$
 select json_build_object('ragione_sociale',s.ragione_sociale,'piva',s.piva,'codice_fiscale',s.codice_fiscale,'indirizzo',s.fatt_indirizzo,'cap',s.fatt_cap,
   'comune',s.fatt_comune,'provincia',s.fatt_provincia,'codice_destinatario',s.codice_destinatario,'pec',s.pec,'completi',bb_fiscali_ok(s)) $$;

-- l'albergatore salva i suoi dati fiscali
create or replace function bb_alb_fiscali_salva(sid uuid, p text, pdati jsonb) returns json language plpgsql security definer set search_path=public,extensions as $$
declare rs text; iva text; cf text; ind text; cap text; com text; prov text; cd text; pc text;
begin
 perform bb_check_alb(sid,p);
 rs := left(trim(coalesce(pdati->>'ragione_sociale','')),100);
 iva := regexp_replace(coalesce(pdati->>'piva',''),'\s','','g');
 cf := upper(regexp_replace(coalesce(pdati->>'codice_fiscale',''),'\s','','g'));
 ind := left(trim(coalesce(pdati->>'indirizzo','')),120);
 cap := trim(coalesce(pdati->>'cap',''));
 com := left(trim(coalesce(pdati->>'comune','')),60);
 prov := upper(trim(coalesce(pdati->>'provincia','')));
 cd := upper(trim(coalesce(nullif(pdati->>'codice_destinatario',''),'0000000')));
 pc := lower(trim(coalesce(pdati->>'pec','')));
 if rs='' then return json_build_object('ok',false,'msg','Scrivi la ragione sociale'); end if;
 if iva='' and cf='' then return json_build_object('ok',false,'msg','Scrivi la partita IVA o il codice fiscale'); end if;
 if iva<>'' and iva !~ '^[0-9]{11}$' then return json_build_object('ok',false,'msg','La partita IVA ha 11 cifre'); end if;
 if cf<>'' and cf !~ '^([A-Z0-9]{16}|[0-9]{11})$' then return json_build_object('ok',false,'msg','Il codice fiscale non è valido (16 caratteri, oppure 11 cifre per una società)'); end if;
 if ind='' or com='' then return json_build_object('ok',false,'msg','Scrivi indirizzo e comune di fatturazione'); end if;
 if cap !~ '^[0-9]{5}$' then return json_build_object('ok',false,'msg','Il CAP ha 5 cifre'); end if;
 if prov !~ '^[A-Z]{2}$' then return json_build_object('ok',false,'msg','La provincia ha 2 lettere (es. NA)'); end if;
 if cd !~ '^[A-Z0-9]{7}$' then return json_build_object('ok',false,'msg','Il codice destinatario ha 7 caratteri (oppure lascia vuoto)'); end if;
 if pc<>'' and pc !~ '^[^@\s]+@[^@\s]+\.[^@\s]+$' then return json_build_object('ok',false,'msg','La PEC non è valida'); end if;
 update bb_strutture set ragione_sociale=rs,piva=iva,codice_fiscale=cf,fatt_indirizzo=ind,fatt_cap=cap,fatt_comune=com,fatt_provincia=prov,codice_destinatario=cd,pec=pc where id=sid;
 return json_build_object('ok',true);
end $$;
grant execute on function bb_alb_fiscali_salva(uuid,text,jsonb) to anon, authenticated;

-- stato dell'albergatore: dati fiscali e sue fatture
create or replace function bb_alb_stato(sid uuid, p text) returns json language plpgsql security definer set search_path=public,extensions as $$
begin
 perform bb_check_alb(sid,p);
 perform bb_sumup_verifica(sid);
 return json_build_object(
  'struttura',(select json_build_object('id',id,'nome',nome,'indirizzo',indirizzo,'telefono',telefono,'benvenuto',benvenuto,'accesso',accesso,'saldo',bb_saldo(id),'tavolo',servizio_tavolo,'supp_tavolo',bb_supp_tavolo(id)) from bb_strutture where id=sid),
  'fiscali',(select bb_fiscali_json(s) from bb_strutture s where s.id=sid),
  'fatture',(select coalesce(json_agg(f order by f.pagata_il desc),'[]'::json) from (select id,importo,pagata_il,stato,numero,data_emissione from bb_fatture_da_emettere where struttura_id=sid order by pagata_il desc limit 50) f),
  'oggi',bb_oggi(),'bar',bb_bar_pubblico(),'sumup',bb_sumup_attivo(),
  'config',json_build_object('ricarica_min',bb_cfg('ricarica_min','5')::numeric,'ricarica_max',bb_cfg('ricarica_max','2000')::numeric,'anticipo',bb_cfg('anticipo_max_giorni','60')::int,'limite_ora',bb_cfg('ordini_limite_ora',''),'msg',bb_cfg('msg_ospite','{link}')),
  'colazioni',bb_colazioni_json(sid,true),
  'camere',(select coalesce(json_agg(json_build_object('id',c.id,'nome',c.nome,'ospiti',c.ospiti) order by c.ordine),'[]'::json) from bb_camere c where c.struttura_id=sid),
  'movimenti',(select coalesce(json_agg(m order by m.t desc),'[]'::json) from (select id,t,tipo,importo,nota,confermato,sumup_url from bb_movimenti where struttura_id=sid) m),
  'vouchers',(select coalesce(json_agg(v order by v.creato desc),'[]'::json) from (select id,fascia,qta,usate,data,data_fine,ospite,camera,ospiti,colazione_nome,creato,annullato,(richieste<>'{}'::jsonb) has_richieste,extra_totale,extra_pagato from bb_vouchers where struttura_id=sid) v));
end $$;

-- titolare: elenco delle fatture da emettere e già emesse
create or replace function bb_tit_fatture(p text) returns json language plpgsql security definer set search_path=public,extensions as $$
begin
 perform bb_check_tit(p);
 return (select coalesce(json_agg(x order by x.pagata_il desc),'[]'::json) from (
   select f.id,f.struttura_id,s.nome struttura,s.demo,s.telefono,s.email,f.importo,f.metodo,f.pagata_il,f.stato,f.numero,f.data_emissione,f.nota,
          bb_fiscali_json(s) fiscali
   from bb_fatture_da_emettere f join bb_strutture s on s.id=f.struttura_id
   order by (f.stato='da_emettere') desc, f.pagata_il desc limit 500) x);
end $$;
grant execute on function bb_tit_fatture(text) to anon, authenticated;

create or replace function bb_tit_fattura_stato(p text, pid uuid, pstato text, pnumero text, pdata date, pnota text) returns void language plpgsql security definer set search_path=public,extensions as $$
begin
 perform bb_check_tit(p);
 if pstato not in ('da_emettere','emessa','non_dovuta') then raise exception 'Stato non valido'; end if;
 if pstato='emessa' and coalesce(trim(pnumero),'')='' then raise exception 'Scrivi il numero della fattura'; end if;
 update bb_fatture_da_emettere set stato=pstato,
   numero=case when pstato='emessa' then left(trim(pnumero),40) else '' end,
   data_emissione=case when pstato='emessa' then coalesce(pdata,current_date) else null end,
   nota=left(coalesce(pnota,''),200) where id=pid;
 if not found then raise exception 'Fattura non trovata'; end if;
end $$;
grant execute on function bb_tit_fattura_stato(text,uuid,text,text,date,text) to anon, authenticated;
