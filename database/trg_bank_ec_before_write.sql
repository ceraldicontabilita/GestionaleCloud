-- ===========================================================================
-- LOGICA CHE VIVEVA SOLO DENTRO AL DATABASE
-- ===========================================================================
-- Su Supabase ci sono trigger PL/pgSQL che scrivono dati contabili. Fino al
-- 19/09/2026 non comparivano da nessuna parte in questo repository: si poteva
-- leggere tutto il progetto senza sapere che esistevano.
--
-- Per vedere quelli vivi adesso:
--   select tgname, pg_get_triggerdef(t.oid)
--   from pg_trigger t
--     join pg_class c on c.oid = t.tgrelid
--     join pg_namespace n on n.oid = c.relnamespace
--   where n.nspname = 'gestionale' and not t.tgisinternal;
--
-- SI TENGONO
--   trg_guardia_delete / trg_guardia_truncate  su documents, blobs,
--     protocollo_drive, protocollo_impronte, protocollo_drive_giri: bloccano
--     cancellazioni e troncamenti non autorizzati. Sono la rete del §6.
--   documents_touch_updated_at / documents_collection_versions: tengono
--     updated_at e le versioni per collezione, su cui poggia la cache
--     incrementale del runtime.
--   trg_bank_ec_after_write: rigenera bank_reconciliation_hub (2.017 righe,
--     che NESSUN file di questo repository legge) e scrive entity_relations
--     (468 righe, che invece il codice legge davvero, in
--     app/services/entity_relations_audit.py). Resta per quelle relazioni.
--
-- RIMOSSO IL 19/09/2026: trg_bank_ec_before_write, definito qui sotto.
--
-- Era un SECONDO motore di riconciliazione. Prima di ogni scrittura
-- sull'estratto conto: riscriveva categoria quando sembrava un codice MCC,
-- riconosceva le spese bancarie e INSERIVA una riga in prima_nota_banca
-- (source: estratto_conto_hub), agganciava i finanziamenti soci alle attese
-- rapido_apporto_soci.
--
-- Gli ultimi due sono esattamente i due casi di
-- app/services/proiezione_bancaria.classifica_movimento_ec, che gira da solo
-- all'import dell'estratto conto
-- (reconciliation_orchestrator.on_estratto_conto_importato_riprocessa) ed e'
-- quello canonico: versionato, testato, con rule_id e rule_version che
-- lasciano una traccia verificabile. Il trigger girava PRIMA e vinceva, quindi
-- per quei movimenti le regole controllabili non parlavano mai — e due
-- implementazioni delle stesse regole, una in Python e una in SQL, possono
-- divergere senza che nessuno se ne accorga.
--
-- Verificato prima di rimuoverlo:
--   - le due sorgenti NON si sovrapponevano: nessun movimento dell'estratto
--     conto risultava proiettato due volte in Prima Nota, quindi i saldi non
--     erano gonfiati;
--   - proiezione_bancaria cerca le righe esistenti per estratto_conto_id /
--     movimento_estratto_conto_id, che il trigger scriveva entrambi: NON
--     ricreera' le 82 righe gia' presenti;
--   - quelle 82 righe (source estratto_conto_hub, 129,50 EUR, dal 16/01 al
--     24/08/2026) sono spese bancarie corrette e restano dove sono. Una
--     registrazione sbagliata si storna, e queste non sono nemmeno sbagliate.
--
-- La definizione integrale resta qui perche' la rimozione sia reversibile e
-- perche' nessuna logica contabile deve esistere solo dentro al database.
-- Per ripristinarlo: eseguire questo file e poi
--   CREATE TRIGGER trg_bank_ec_before_write
--     BEFORE INSERT OR UPDATE ON gestionale.documents
--     FOR EACH ROW WHEN (new.collection = 'estratto_conto_movimenti')
--     EXECUTE FUNCTION gestionale.bank_ec_before_write();
-- ===========================================================================

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
