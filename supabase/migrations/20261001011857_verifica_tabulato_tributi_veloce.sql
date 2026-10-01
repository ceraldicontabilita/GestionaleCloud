create or replace view verifica.tabulato_tributi with (security_invoker = on) as
with qr as materialized (
  select *, case when codice in ('DM10','RC01') then 'INPS_DIP' else codice end chiave_codice
  from verifica.quietanze_righe where debito_cents > 0
),
fr as materialized (
  select distinct case when codice in ('DM10','RC01') then 'INPS_DIP' else codice end chiave_codice, periodo
  from verifica.f24_righe where debito_cents > 0
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
qk as materialized (  -- chiave periodo normalizzata per ogni riga di quietanza
  select q.chiave_codice,
    case when q.chiave_codice='INAIL' then (extract(year from q.data_pagamento)::int - 1)::text
         when q.chiave_codice='7085' then right(q.periodo,4)
         else q.periodo end periodo,
    q.debito_cents, q.data_pagamento, q.protocollo
  from qr q join regole r using (chiave_codice)
),
primi as (
  select r.chiave_codice,
    min(case when r.tipo='mensile' or r.chiave_codice in ('1712','1713') then to_date(k.periodo,'MM/YYYY')
             else make_date(k.periodo::int,1,1) end) primo
  from regole r join qk k using (chiave_codice)
  where (k.periodo ~ '^\d{2}/\d{4}$') or (k.periodo ~ '^\d{4}$' and r.tipo='annuale' and r.chiave_codice not in ('1712','1713'))
  group by 1
),
attesi as (
  select r.*, g::date rif
  from regole r join primi p using (chiave_codice)
  cross join lateral generate_series(date_trunc('year', p.primo), date_trunc('month', current_date),
                                     case when r.tipo='mensile' then interval '1 month' else interval '1 year' end) g
  where r.tipo='annuale' or extract(month from g) between r.mese_da and r.mese_a
),
chiavi as (
  select a.chiave_codice, a.etichetta, a.tipo,
    case when a.chiave_codice in ('INAIL','7085') then to_char(a.rif,'YYYY')
         when a.chiave_codice in ('1712','1713') then '12/'||to_char(a.rif,'YYYY')
         else to_char(a.rif,'MM/YYYY') end periodo,
    case when a.chiave_codice='INAIL' then make_date(extract(year from a.rif)::int + 1, 2, 16)
         when a.chiave_codice='1712' then make_date(extract(year from a.rif)::int, 12, 16)
         when a.chiave_codice='1713' then make_date(extract(year from a.rif)::int + 1, 2, 16)
         when a.chiave_codice='7085' then make_date(extract(year from a.rif)::int, 6, 30)
         else (a.rif + make_interval(years => a.ritardo_anni) + interval '1 month' + interval '15 days')::date end scadenza
  from attesi a
),
agg as (
  select chiave_codice, periodo, sum(debito_cents) pagato_cents,
    string_agg(distinct to_char(data_pagamento,'DD/MM/YYYY'), ', ') date_pagamento,
    string_agg(distinct protocollo, ', ') protocolli
  from qk group by 1,2
),
pag as (
  select c.*, a.pagato_cents, a.date_pagamento, a.protocolli,
    exists(select 1 from fr where fr.chiave_codice=c.chiave_codice
           and (fr.periodo=c.periodo or (c.chiave_codice='7085' and right(fr.periodo,4)=c.periodo))) ha_f24
  from chiavi c left join agg a using (chiave_codice, periodo)
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

