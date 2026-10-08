create or replace view verifica.f24_righe with (security_invoker = on) as
select d.id f24_id, s.sezione,
  case s.sezione when 'INPS' then coalesce(r->>'causale', r->>'codice_tributo') when 'INAIL' then 'INAIL' else r->>'codice_tributo' end codice,
  coalesce(r->>'periodo_riferimento', case when r->>'mese' is not null and r->>'anno' is not null then lpad(r->>'mese',2,'0')||'/'||(r->>'anno') else r->>'anno' end) periodo,
  coalesce((r->>'importo_debito_cents')::bigint,0) debito_cents
from gestionale.documents d
cross join lateral (values ('Erario','sezione_erario'),('INPS','sezione_inps'),('Regioni','sezione_regioni'),
                           ('Tributi locali','sezione_tributi_locali'),('Tributi locali','sezione_imu'),('INAIL','sezione_inail')) s(sezione, chiave)
cross join lateral jsonb_array_elements(coalesce(d.data->s.chiave,'[]')) r
where d.collection='f24_unificato' and coalesce(d.data->>'motivo_quarantena','')=''
  and d.data->>'doppione_di' is null and d.data->>'superato_da' is null;

create or replace view verifica.tabulato_tributi with (security_invoker = on) as
with qr as (
  select *, case when codice in ('DM10','RC01') then 'INPS_DIP' else codice end chiave_codice
  from verifica.quietanze_righe where debito_cents > 0
),
regole(chiave_codice, etichetta, tipo, mese_da, mese_a, ritardo_anni) as (values
  ('1001','Ritenute IRPEF lavoro dipendente','mensile',1,12,0),
  ('INPS_DIP','Contributi INPS dipendenti (DM10 / RC01)','mensile',1,12,0),
  ('CXX','Contributi INPS CXX','mensile',1,12,0),
  ('3802','Addizionale regionale IRPEF, rate del saldo','mensile',1,11,1),
  ('3848','Addizionale comunale IRPEF, rate del saldo','mensile',1,11,1),
  ('3847','Addizionale comunale IRPEF, acconto','mensile',3,11,0),
  ('1712','Acconto imposta sostitutiva rivalutazione TFR','annuale',12,12,0),
  ('1713','Saldo imposta sostitutiva rivalutazione TFR','annuale',12,12,1),
  ('7085','Diritto annuale Camera di commercio','annuale',6,6,0),
  ('INAIL','Autoliquidazione INAIL','annuale',1,1,1)
),
primi as (
  select r.chiave_codice, min(case when r.tipo='mensile' or r.chiave_codice in ('1712','1713') then to_date(q.periodo,'MM/YYYY')
                                   when r.chiave_codice='INAIL' then make_date(extract(year from q.data_pagamento)::int - 1, 1, 1)
                                   else make_date(right(q.periodo,4)::int,1,1) end) primo
  from regole r join qr q using (chiave_codice)
  where (r.tipo='mensile' and q.periodo ~ '^\d{2}/\d{4}$') or r.tipo='annuale'
  group by 1
),
attesi as (
  select r.*, g::date rif
  from regole r join primi p using (chiave_codice)
  cross join lateral generate_series(date_trunc('year', p.primo), date_trunc('month', current_date), case when r.tipo='mensile' then interval '1 month' else interval '1 year' end) g
  where r.tipo='annuale' or extract(month from g) between r.mese_da and r.mese_a
),
chiavi as (
  select a.chiave_codice, a.etichetta, a.tipo,
    case when a.chiave_codice='INAIL' then to_char(a.rif,'YYYY')
         when a.chiave_codice in ('1712','1713') then '12/'||to_char(a.rif,'YYYY')
         when a.chiave_codice='7085' then to_char(a.rif,'YYYY')
         else to_char(a.rif,'MM/YYYY') end periodo,
    case when a.chiave_codice='INAIL' then make_date(extract(year from a.rif)::int + 1, 2, 16)
         when a.chiave_codice='1712' then make_date(extract(year from a.rif)::int, 12, 16)
         when a.chiave_codice='1713' then make_date(extract(year from a.rif)::int + 1, 2, 16)
         when a.chiave_codice='7085' then make_date(extract(year from a.rif)::int, 6, 30)
         else (a.rif + make_interval(years => a.ritardo_anni) + interval '1 month' + interval '15 days')::date end scadenza
  from attesi a
),
pag as (
  select c.*,
    (select sum(q.debito_cents) from qr q where q.chiave_codice=c.chiave_codice and
        case when c.chiave_codice='INAIL' then extract(year from q.data_pagamento)::int = c.periodo::int + 1
             when c.chiave_codice='7085' then right(q.periodo,4)=c.periodo
             else q.periodo=c.periodo end) pagato_cents,
    (select string_agg(distinct to_char(q.data_pagamento,'DD/MM/YYYY'), ', ') from qr q where q.chiave_codice=c.chiave_codice and
        case when c.chiave_codice='INAIL' then extract(year from q.data_pagamento)::int = c.periodo::int + 1
             when c.chiave_codice='7085' then right(q.periodo,4)=c.periodo
             else q.periodo=c.periodo end) date_pagamento,
    (select string_agg(distinct q.protocollo, ', ') from qr q where q.chiave_codice=c.chiave_codice and
        case when c.chiave_codice='INAIL' then extract(year from q.data_pagamento)::int = c.periodo::int + 1
             when c.chiave_codice='7085' then right(q.periodo,4)=c.periodo
             else q.periodo=c.periodo end) protocolli,
    exists(select 1 from verifica.f24_righe f where (case when f.codice in ('DM10','RC01') then 'INPS_DIP' else f.codice end)=c.chiave_codice
           and f.debito_cents>0 and (f.periodo=c.periodo or (c.chiave_codice in ('7085') and right(f.periodo,4)=c.periodo))) ha_f24
  from chiavi c
)
select etichetta tributo, chiave_codice codice, tipo, periodo, scadenza,
  case when pagato_cents is null and scadenza > current_date then 'NON_SCADUTO'
       when pagato_cents is not null and ha_f24 then 'PAGATO'
       when pagato_cents is not null then 'PAGATO_SOLO_QUIETANZA'
       when ha_f24 then 'F24_SENZA_QUIETANZA'
       else 'MANCANTE' end stato,
  case when pagato_cents is null and scadenza > current_date then 'Non ancora scaduto'
       when pagato_cents is not null and ha_f24 then 'Pagato: F24 e quietanza presenti'
       when pagato_cents is not null then chiave_codice || ' pagato: F24 originale non trovato, ma la quietanza certifica il pagamento'
       when ha_f24 then 'F24 presente ma nessuna quietanza: pagamento NON certificato'
       else 'VERSAMENTO NON TROVATO' end esito,
  round(pagato_cents/100.0,2) pagato, date_pagamento, protocolli, ha_f24
from pag
union all
select 'IMU '||periodo, '3918', 'annuale', anno||' '||periodo, scadenza, stato, etichetta, pagato, date_pagamento, protocolli, ha_f24
from verifica.versamenti_tributi where sezione='IMU';

