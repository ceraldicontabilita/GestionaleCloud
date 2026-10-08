drop view if exists verifica.tabulato_tributi_termini;
create view verifica.tabulato_tributi_termini with (security_invoker = on) as
with b as (
  select t.*, substring(t.periodo from '(\d{4})')::int anno_per, extract(year from t.scadenza)::int anno_scad
  from verifica.tabulato_tributi t
), c as (
  select b.*,
    case when codice in ('1001','1012','3847','1712','1713') then anno_per
         when codice in ('3802','3848') then anno_per + 1 end anno_770,
    case when codice in ('1001','1012','3847','1712','1713','3802','3848') then 'sost'
         when codice in ('INPS_DIP','CXX','INAIL') then 'contrib'
         else codice end gruppo
  from b
), d as (
  select c.*,
    case gruppo
      when 'sost' then make_date(anno_770 + 4, 12, 31)
      when 'contrib' then (scadenza + interval '5 years')::date
      when '3918' then make_date(anno_scad + 5, 12, 31)
      when '3850' then (scadenza + interval '10 years')::date
      when '7085' then make_date(anno_scad + 5, 12, 31)
    end termine_ordinario,
    case when gruppo = 'contrib' then
      greatest(0, date '2020-06-30' - greatest(scadenza, date '2020-02-23') + 1)
      + greatest(0, date '2021-06-30' - greatest(scadenza, date '2020-12-31') + 1)
    else 0 end giorni_sosp_inps
  from c
), e as (
  select d.*,
    case
      when gruppo = 'sost' and anno_770 in (2017, 2018, 2019) then (termine_ordinario + interval '1 year')::date
      when gruppo = 'contrib' then termine_ordinario + giorni_sosp_inps
      when gruppo in ('3918','3850','7085') and scadenza < date '2020-03-08' then termine_ordinario + 85
      else termine_ordinario
    end recuperabile_entro,
    case
      when gruppo = 'sost' and anno_770 = 2017 then 'Covid: +1 anno (art. 157 c. 3 DL 34/2020, 770 presentato nel 2018)'
      when gruppo = 'sost' and anno_770 = 2018 then 'Covid: +1 anno (DL 41/2021, 770 presentato nel 2019)'
      when gruppo = 'sost' and anno_770 = 2019 then 'Covid: +1 anno (art. 1 c. 158 L. 197/2022, 770 presentato nel 2020)'
      when gruppo = 'contrib' and giorni_sosp_inps > 0 then 'Covid: prescrizione sospesa ' || giorni_sosp_inps || ' giorni (art. 37 c. 2 DL 18/2020 e art. 11 c. 9 DL 183/2020)'
      when gruppo in ('3918','3850','7085') and scadenza < date '2020-03-08' then 'Covid: +85 giorni (sospensione 8/3–31/5/2020, art. 67 DL 18/2020)'
      else 'Nessuno slittamento Covid'
    end slittamento_covid
  from d
)
select tributo, codice, tipo, periodo, scadenza, stato, esito, pagato, date_pagamento, protocolli, ha_f24,
  termine_ordinario, slittamento_covid, recuperabile_entro,
  case
    when stato not in ('MANCANTE','F24_SENZA_QUIETANZA') then null
    when recuperabile_entro < current_date then 'TERMINE SCADUTO (salvo atti già notificati)'
    else 'ANCORA RECUPERABILE dall''ente'
  end situazione_termini
from e;

comment on view verifica.tabulato_tributi_termini is
'Tabulato tributi con termine ordinario, slittamento Covid e termine aggiornato entro cui l''ente può ancora chiedere il versamento. Per i ruoli affidati ad AdER tra l''8/3/2020 e il 31/12/2021 può valere un ulteriore +24 mesi (art. 68 c. 4-bis DL 18/2020). Termini indicativi, da confermare con il commercialista.';
