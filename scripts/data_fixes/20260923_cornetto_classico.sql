-- RST-0508BB: formula confermata dal titolare il 23/09/2026.
-- Eseguire una sola volta dopo merge e verifica del deploy. La copia originale
-- e' recuperabile nella collection indicata sotto; nessun'altra ricetta cambia.
begin;

do $$
declare
  current_data jsonb;
  changed integer;
begin
  select data into current_data
  from lotti.lotti_documents
  where collection = 'ricette'
    and doc_id = '6a94e23150a46cbd4aca7cb6'
  for update;

  if current_data is null
     or current_data->>'id' <> '6d114c3a-1b0c-582b-981f-c26d25976eea'
     or current_data->>'nome' <> 'Cornetto Classico' then
    raise exception 'Cornetto Classico non identificato esattamente';
  end if;

  if current_data->>'correzione_formula' = 'RST-0508BB' then
    return;
  end if;

  -- Una modifica concorrente alla formula richiede nuova revisione umana.
  if current_data->'ingredienti_dettaglio' <> '[{"nome":"Farina 00","quantita":1000,"unita_misura":"g"},{"nome":"Burro","quantita":150,"unita_misura":"g"},{"nome":"Zucchero","quantita":150,"unita_misura":"g"},{"nome":"Uova","quantita":3,"unita_misura":"pz"},{"nome":"Lievito di birra","quantita":10,"unita_misura":"g"},{"nome":"Latte","quantita":200,"unita_misura":"ml"},{"nome":"zuppa inglese","quantita":10,"unita_misura":"ml"},{"nome":"sale","quantita":20,"unita_misura":"g"},{"nome":"miglioratore","quantita":20,"unita_misura":"g"},{"nome":"aroma croissant","quantita":5,"unita_misura":"g"},{"nome":"Burro freddo per sfogliatura","quantita":300,"unita_misura":"g"},{"nome":"Tuorlo per spennellare","quantita":2,"unita_misura":"pz"}]'::jsonb then
    raise exception 'La formula e cambiata: riesaminare Cornetto Classico';
  end if;

  insert into lotti.lotti_documents (collection, doc_id, data, created_at, updated_at)
  select 'ricette_backup_20260923_rst0508bb', doc_id, data, now(), now()
  from lotti.lotti_documents
  where collection = 'ricette' and doc_id = '6a94e23150a46cbd4aca7cb6';

  update lotti.lotti_documents
  set data = data || jsonb_build_object(
    'ingredienti', jsonb_build_array('Farina 00', 'Zucchero', 'Burro', 'Uova intere', 'Sale', 'Miglioratore', 'Acqua', 'Lievito di birra', 'Burro per pieghe'),
    'ingredienti_dettaglio', '[
      {"nome":"Farina 00","quantita":1000,"unita_misura":"g","fase":"impasto"},
      {"nome":"Zucchero","quantita":150,"unita_misura":"g","fase":"impasto"},
      {"nome":"Burro","quantita":150,"unita_misura":"g","fase":"impasto"},
      {"nome":"Uova intere","quantita":3,"unita_misura":"pz","fase":"impasto","peso_unitario_g":50},
      {"nome":"Sale","quantita":20,"unita_misura":"g","fase":"impasto"},
      {"nome":"Miglioratore","quantita":20,"unita_misura":"g","fase":"impasto"},
      {"nome":"Acqua","quantita":300,"unita_misura":"g","fase":"impasto"},
      {"nome":"Lievito di birra","quantita":10,"unita_misura":"g","fase":"impasto"},
      {"nome":"Burro per pieghe","quantita":540,"unita_misura":"g","fase":"pieghe"}
    ]'::jsonb,
    'ingrediente_base_nome', 'Farina 00',
    'peso_uovo_g', 50,
    'peso_pezzo_g', 80,
    'porzioni', 29,
    'pezzi_ricetta_base', 29,
    'resa_verificata', false,
    'descrizione', 'Cornetto sfogliato al burro con farina 00 e uova.',
    'descrizione_origine', 'formula_titolare_2026-09-23',
    'procedimento_testo', E'1. Pesare gli ingredienti dell\'impasto e tenere separati 540 g di burro per le pieghe.\n2. Impastare farina, acqua, lievito, uova e miglioratore; incorporare zucchero, 150 g di burro e sale fino a ottenere un impasto omogeneo. Regolare la temperatura dell\'acqua in base all\'ambiente: controllare che l\'impasto finito sia circa 24-25 °C, senza assumere una temperatura fissa dell\'acqua.\n3. Coprire e raffreddare l\'impasto prima della laminazione. Pesare: impasto teorico 1.800 g, burro per pieghe 540 g.\n4. Incassare il burro freddo; eseguire due pieghe a tre, riposare 30 minuti a +4 °C, fare una terza piega a tre e riposare altri 30 minuti a +4 °C.\n5. Stendere a circa 3 mm; tagliare e arrotolare pezzi da 80 g. La massa teorica totale e 2.340 g: 29 pezzi, con 20 g residui teorici prima degli sfridi effettivi.\n6. Lasciar lievitare circa 2-3 ore, verificando sviluppo e consistenza dei pezzi.\n7. Cuocere secondo il forno operativo: il procedimento precedente indicava 200 °C per 15-18 minuti; verificare colore e cottura reale prima di fissare il parametro di produzione.',
    'procedimento_fonti', jsonb_build_array(
      jsonb_build_object('tipo', 'formula_titolare', 'data', '2026-09-23', 'nota', 'Ingredienti, dose di burro per pieghe e peso del pezzo forniti dal titolare.'),
      jsonb_build_object('tipo', 'tecnica_web', 'url', 'https://www.molinograssi.it/recipe-author/pierluigi-sapiente/page/2/', 'nota', 'Temperatura impasto e sequenza pieghe/riposi; formula diversa.'),
      jsonb_build_object('tipo', 'tecnica_web', 'url', 'https://lesaffre.it/lesaffre-ricette/livendo-cornetto-all-italiana/', 'nota', 'Riferimento per impasto, sfogliatura, lievitazione e cottura; formula diversa.')
    ),
    'correzione_formula', 'RST-0508BB'
  ), updated_at = now()
  where collection = 'ricette' and doc_id = '6a94e23150a46cbd4aca7cb6';

  get diagnostics changed = row_count;
  if changed <> 1 or not exists (
    select 1 from lotti.lotti_documents
    where collection = 'ricette_backup_20260923_rst0508bb'
      and doc_id = '6a94e23150a46cbd4aca7cb6'
  ) then
    raise exception 'Correzione Cornetto non verificata';
  end if;
end $$;

commit;
