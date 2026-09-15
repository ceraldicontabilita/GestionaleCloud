-- Modelli e quietanze F24: Drive e' l'unico archivio dell'originale.
-- La migrazione rimuove il Base64 solo quando il protocollo Drive offre una
-- corrispondenza MD5 attiva, canonica e univoca. In caso contrario si ferma.

do $$
begin
  if exists (
    with embedded as (
      select d.collection, d.id,
             gestionale.md5_base64_sicuro(d.data->>'pdf_data') as md5
      from gestionale.documents d
      where d.collection in ('f24_unificato', 'quietanze_f24')
        and coalesce(d.data->>'pdf_data', '') <> ''
    ), matches as (
      select e.collection, e.id, count(p.drive_id) as n
      from embedded e
      left join gestionale.protocollo_drive p
        on p.md5 = e.md5
       and p.stato = 'attivo'
       and p.duplicato_di is null
      group by e.collection, e.id
    )
    select 1 from matches where n <> 1
  ) then
    raise exception 'Migrazione F24 bloccata: originale Drive canonico mancante o ambiguo';
  end if;

  if exists (
    select 1
    from gestionale.documents d
    where d.collection in ('f24_unificato', 'quietanze_f24')
      and coalesce(d.data->>'pdf_hash', '') <> ''
    group by d.collection, d.data->>'pdf_hash'
    having count(*) > 1
  ) then
    raise exception 'Migrazione F24 bloccata: hash duplicati ancora presenti';
  end if;
end $$;

with embedded as (
  select d.collection, d.id,
         gestionale.md5_base64_sicuro(d.data->>'pdf_data') as md5
  from gestionale.documents d
  where d.collection in ('f24_unificato', 'quietanze_f24')
    and coalesce(d.data->>'pdf_data', '') <> ''
), canonical as (
  select e.collection, e.id, e.md5,
         min(p.drive_id) as drive_id,
         min(p.parent_id) as parent_id,
         min(p.percorso) as percorso
  from embedded e
  join gestionale.protocollo_drive p
    on p.md5 = e.md5
   and p.stato = 'attivo'
   and p.duplicato_di is null
  group by e.collection, e.id, e.md5
  having count(*) = 1
), prepared as (
  select d.collection, d.id,
         case
           when d.collection = 'quietanze_f24'
             then 'quietanza_f24:' || (d.data->>'pdf_hash')
           else 'f24:' || coalesce(
             nullif(d.data->>'f24_dedup_key', ''),
             nullif(d.data->>'pdf_hash', ''),
             c.md5
           )
         end as idem,
         c.drive_id, c.parent_id, c.percorso, c.md5
  from gestionale.documents d
  join canonical c on c.collection = d.collection and c.id = d.id
)
update gestionale.documents d
set data = (d.data - 'pdf_data') || jsonb_build_object(
      'drive_file_id', p.drive_id,
      'drive_parent_id', p.parent_id,
      'drive_path', p.percorso,
      'drive_md5', p.md5,
      'original_storage', 'google_drive',
      'idempotency_key', p.idem
    ),
    idempotency_key = p.idem,
    updated_at = now()
from prepared p
where d.collection = p.collection and d.id = p.id;

update gestionale.protocollo_drive p
set collegamento_tipo = d.collection,
    collegamento_id = d.id,
    aggiornato_il = now()
from gestionale.documents d
where d.collection in ('f24_unificato', 'quietanze_f24')
  and d.data->>'drive_file_id' = p.drive_id
  and p.stato = 'attivo';
