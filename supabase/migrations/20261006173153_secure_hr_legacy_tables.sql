-- Chiude gli archivi HR storici alla Data API preservando l'accesso del solo
-- ruolo applicativo diretto. Nessun dato viene cancellato o trasformato.

alter table hr.app_pagamenti_storico enable row level security;
alter table hr.app_bonifici_duplicati_20260914 enable row level security;
alter table hr.app_paghe_mensili_rimosse_20260914 enable row level security;
alter table hr.app_dipendenti_modifiche_20260914 enable row level security;
alter table hr.app_bonifici_modifiche_20260914 enable row level security;
alter table hr.app_dipendenti_prima_20260914b enable row level security;
alter table hr.app_dipendenti_prima_20260914c enable row level security;
alter table hr.app_cedolini_prima_prova_20260930 enable row level security;

do $$
declare v_table text;
begin
  foreach v_table in array array[
    'app_pagamenti_storico',
    'app_bonifici_duplicati_20260914',
    'app_paghe_mensili_rimosse_20260914',
    'app_dipendenti_modifiche_20260914',
    'app_bonifici_modifiche_20260914',
    'app_dipendenti_prima_20260914b',
    'app_dipendenti_prima_20260914c',
    'app_cedolini_prima_prova_20260930'
  ]
  loop
    execute format('drop policy if exists hr_app_internal_access on hr.%I', v_table);
    execute format(
      'create policy hr_app_internal_access on hr.%I for all to hr_app using (true) with check (true)',
      v_table
    );
  end loop;
end $$;
