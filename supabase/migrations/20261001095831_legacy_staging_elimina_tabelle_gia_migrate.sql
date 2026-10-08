-- 01/10/2026, titolare: «migra i dati e cancella». Il confronto con l'archivio corrente ha mostrato che
-- fatture 2026, incassi, movimenti banca, presenze, chiusure, versamenti e Prima Nota del vecchio
-- archivio CeraldiFatture sono gia' nel gestionale. Restano solo le tabelle con dati non ancora
-- migrati: 29 fatture 2026 senza XML (residui_fatture_2026), 525 prodotti con prezzi per fornitore,
-- 34 movimenti carta con abbinamenti manuali, acconti e profili HR.
do $$
declare
  t record;
begin
  for t in
    select c.relname as tabella
    from pg_class c join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'legacy_staging' and c.relkind = 'r'
      and c.relname not in ('residui_fatture_2026', 'catalogo_ceraldi', 'movimenti_carta',
                            'presenze_acconti', 'presenze_profili')
  loop
    execute format('drop table legacy_staging.%I', t.tabella);
  end loop;
end $$;
