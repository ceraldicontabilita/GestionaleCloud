-- Trigger RIMOSSO dalla produzione il 19/09/2026 (audit sui sistemi paralleli).
-- Conservato qui per intero perche' la rimozione resti reversibile e perche'
-- nessuna logica contabile deve esistere solo dentro al database.
--
-- Il motivo della rimozione e le verifiche fatte prima stanno in
-- database/README.md. Il motore canonico che copre gli stessi due casi e'
-- app/services/proiezione_bancaria.py.
--
-- Per ripristinarlo: eseguire questo file e poi
--   CREATE TRIGGER trg_bank_ec_before_write
--     BEFORE INSERT OR UPDATE ON gestionale.documents
--     FOR EACH ROW WHEN (new.collection = 'estratto_conto_movimenti')
--     EXECUTE FUNCTION gestionale.bank_ec_before_write();

CREATE OR REPLACE FUNCTION gestionale.bank_ec_before_write()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog'
AS $function$
declare
  descr text;
  cat text;
  imp numeric;
  dt date;
  pending_id text;
  pending_count integer;
begin
  if new.collection <> 'estratto_conto_movimenti' then return new; end if;
  descr := upper(coalesce(new.data->>'descrizione_originale', new.data->>'descrizione', ''));
  cat := coalesce(new.data->>'categoria','');
  begin imp := abs(coalesce((new.data->>'importo')::numeric,0)); exception when others then imp := 0; end;
  begin dt := nullif(left(coalesce(new.data->>'data', new.data->>'data_contabile',''),10),'')::date; exception when others then dt := null; end;

  if cat ~ '^[0-9]{4}$' then
    new.data := jsonb_set(new.data, '{categoria_originale}', to_jsonb(cat), true);
    new.data := jsonb_set(new.data, '{mcc}', to_jsonb(cat), true);
    new.data := jsonb_set(new.data, '{categoria}', to_jsonb('Carta aziendale'::text), true);
    new.data := jsonb_set(new.data, '{categoria_canonica}', to_jsonb('Carta aziendale'::text), true);
  end if;

  if coalesce(new.data->>'tipo','') = 'uscita'
     and descr ~ '(COMMISSION|CANONE|SPESE (DI |TENUTA|CONTO)|IMPOSTA (DI )?BOLLO|BOLLO CONTO|INTERESSI PASSIV|COSTO BONIFICO|DIRITTI DI SCRITTURA)'
     and descr !~ '(PAYPAL|NUMIA|NEXI|SUMUP|POS )'
  then
    new.data := new.data || jsonb_build_object(
      'categoria_canonica','Commissioni bancarie','riconciliato',true,
      'stato_riconciliazione','riconciliato','tipo_riconciliazione','spesa_bancaria_autonoma',
      'documento_collection','estratto_conto_movimenti','documento_id',new.id
    );
    insert into gestionale.documents(collection,id,data,created_at,updated_at)
    values(
      'prima_nota_banca','ec-expense:'||new.id,
      jsonb_build_object(
        'id','ec-expense:'||new.id,'idempotency_key','ec-expense:'||new.id,
        'data',coalesce(new.data->>'data',new.data->>'data_contabile'),'tipo','uscita','importo',imp,
        'descrizione',coalesce(new.data->>'descrizione_originale',new.data->>'descrizione','Spesa bancaria'),
        'categoria','Commissioni bancarie','estratto_conto_id',new.id,'movimento_estratto_conto_id',new.id,
        'source','estratto_conto_hub','riconciliato',true,'stato_riconciliazione','riconciliato',
        'documento_collection','estratto_conto_movimenti','documento_id',new.id,
        'created_at',now(),'updated_at',now()
      ), now(), now()
    ) on conflict (collection,id) do update set data=excluded.data, updated_at=now();
  end if;

  if coalesce(new.data->>'tipo','') = 'entrata'
     and descr ~ '(RIMBORS|REFUND|REVERSAL|STORNO)'
     and coalesce(new.data->>'riconciliato','false') <> 'true'
  then
    new.data := jsonb_set(new.data, '{categoria_canonica}', to_jsonb('Rimborso'::text), true);
    new.data := jsonb_set(new.data, '{stato_riconciliazione}', to_jsonb('da_verificare'::text), true);
  end if;

  if coalesce(new.data->>'tipo','') = 'entrata'
     and descr ~ '(FINANZIAMENTO SOC|APPORTO SOC|VERSAMENTO SOC|SOCIO )'
     and imp > 0 and dt is not null
  then
    select count(*), min(id) into pending_count, pending_id
    from gestionale.documents d
    where d.collection='prima_nota_banca'
      and coalesce(d.data->>'source','')='rapido_apporto_soci'
      and coalesce(d.data->>'in_attesa_estratto_ufficiale','false')='true'
      and abs(coalesce((d.data->>'importo')::numeric,0)-imp) < 0.005
      and nullif(left(coalesce(d.data->>'data',''),10),'')::date between dt-7 and dt+7;
    if pending_count = 1 and pending_id is not null then
      update gestionale.documents d
      set data = d.data || jsonb_build_object(
          'estratto_conto_id',new.id,'movimento_estratto_conto_id',new.id,'riconciliato',true,
          'in_attesa_estratto_ufficiale',false,'stato_riconciliazione','riconciliato',
          'data_riconciliazione',now(),'updated_at',now()
        ), updated_at=now()
      where d.collection='prima_nota_banca' and d.id=pending_id;
      new.data := new.data || jsonb_build_object(
        'riconciliato',true,'stato_riconciliazione','riconciliato','tipo_riconciliazione','finanziamento_soci',
        'prima_nota_banca_id',pending_id,'documento_collection','prima_nota_banca','documento_id',pending_id
      );
    elsif pending_count > 1 then
      new.data := jsonb_set(new.data, '{stato_riconciliazione}', to_jsonb('da_verificare'::text), true);
      new.data := jsonb_set(new.data, '{riconciliazione_warning}', to_jsonb('piu_attese_finanziamento_soci_compatibili'::text), true);
    end if;
  end if;
  return new;
end;
$function$;
