create or replace view verifica.tabulato_tributi_termini with (security_invoker = on) as
with b as (
  select t.*,
    substring(t.periodo from '(\d{4})')::int anno_per,
    extract(year from t.scadenza)::int anno_scad
  from verifica.tabulato_tributi t
),
c as (
  select b.*,
    case
      when codice in ('1001','1012','3847','1712','1713') then anno_per
      when codice in ('3802','3848') then anno_per + 1
    end anno_770
  from b
)
select c.tributo, c.codice, c.tipo, c.periodo, c.scadenza, c.stato, c.esito, c.pagato, c.date_pagamento, c.protocolli, c.ha_f24,
  case
    when c.codice in ('1001','1012','3847','1712','1713','3802','3848') then make_date(c.anno_770 + 4, 12, 31)
    when c.codice in ('INPS_DIP','CXX','INAIL') then (c.scadenza + interval '5 years')::date
    when c.codice = '3918' then make_date(c.anno_scad + 5, 12, 31)
    when c.codice = '3850' then (c.scadenza + interval '10 years')::date
    when c.codice = '7085' then make_date(c.anno_scad + 5, 12, 31)
  end recuperabile_entro,
  case
    when c.codice in ('1001','1012','3847','1712','1713','3802','3848') then
      'Ritenuta del sostituto (770 dell''anno ' || c.anno_770 || ', da presentare entro il 31/10/' || (c.anno_770 + 1) || '). '
      || 'Se il 770 riporta la ritenuta: cartella da controllo automatizzato (art. 36-bis DPR 600/73, art. 25 DPR 602/73) entro il 31/12/' || (c.anno_770 + 4) || '. '
      || 'Se il 770 non la riporta: accertamento entro il 31/12/' || (c.anno_770 + 6) || ' (art. 43 DPR 600/73); 770 omesso: entro il 31/12/' || (c.anno_770 + 8) || '.'
    when c.codice in ('INPS_DIP','CXX') then
      'Contributi INPS: prescrizione 5 anni dalla scadenza (art. 3 c. 9 L. 335/1995), 10 anni se il lavoratore denuncia l''omissione entro i 5 anni. Ogni atto interruttivo INPS fa ripartire il termine.'
    when c.codice = 'INAIL' then
      'Premi INAIL: prescrizione 5 anni dalla scadenza (da confermare con il consulente del lavoro). Ogni atto interruttivo fa ripartire il termine.'
    when c.codice = '3918' then
      'IMU: avviso di accertamento esecutivo del Comune entro il 31/12/' || (c.anno_scad + 5) || ' (art. 1 c. 161 L. 296/2006). Dal 2020 l''avviso vale già come titolo esecutivo (L. 160/2019 c. 792): dopo 60 gg dalla notifica si passa alla riscossione coattiva.'
    when c.codice = '3850' then
      'Diritto camerale: il diritto si prescrive in 10 anni; la sanzione va irrogata entro il 31/12/' || (c.anno_scad + 5) || '.'
    when c.codice = '7085' then
      'Tassa concessione governativa libri sociali: termine indicativo, da confermare con il commercialista.'
  end base_normativa,
  case
    when c.stato not in ('MANCANTE','F24_SENZA_QUIETANZA') then null
    when (case
            when c.codice in ('1001','1012','3847','1712','1713','3802','3848') then make_date(c.anno_770 + 4, 12, 31)
            when c.codice in ('INPS_DIP','CXX','INAIL') then (c.scadenza + interval '5 years')::date
            when c.codice = '3918' then make_date(c.anno_scad + 5, 12, 31)
            when c.codice = '3850' then (c.scadenza + interval '10 years')::date
            when c.codice = '7085' then make_date(c.anno_scad + 5, 12, 31)
          end) < current_date
      then 'TERMINE PRINCIPALE SCADUTO (salvo atti già notificati o termini più lunghi indicati nella nota)'
    else 'ANCORA RECUPERABILE dall''ente'
  end situazione_termini
from c;

comment on view verifica.tabulato_tributi_termini is
'Tabulato tributi con il termine entro cui Agenzia/INPS/Comune possono ancora richiedere il versamento mancante (avviso bonario, cartella, accertamento). Termini da verificare con il commercialista: sospensioni Covid 2020, atti interruttivi e 770 effettivamente presentati possono spostarli.';
