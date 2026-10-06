-- 06/10/2026 — Gli originali PDF vivono su Drive; Supabase conserva solo
-- riferimenti verificati. I campi storici che contengono ZIP, CSV, immagini
-- o altro non-PDF non vengono toccati.

create temporary table _pdf_drive_verified on commit drop as
with pdf as (
  select d.id, d.collection,
         md5(decode(d.data->>'pdf_data', 'base64')) as md5,
         octet_length(decode(d.data->>'pdf_data', 'base64')) as bytes,
         d.data
  from gestionale.documents d
  where d.data->>'pdf_data' like 'JVBERi0%'
)
select p.id, p.collection, p.md5, p.bytes,
       coalesce(protocollo.drive_id, p.data->>'drive_file_id') as drive_id
from pdf p
left join lateral (
  select pd.drive_id
  from gestionale.protocollo_drive pd
  where pd.stato = 'attivo'
    and lower(pd.md5) = p.md5
    and pd.dimensione = p.bytes
  order by pd.percorso, pd.drive_id
  limit 1
) protocollo on true
where protocollo.drive_id is not null
   or (
     nullif(p.data->>'drive_file_id', '') is not null
     and lower(p.data->>'drive_md5') = p.md5
     and p.data->>'drive_archive_status' = 'verified'
   );

update gestionale.documents d
set data = (d.data - 'pdf_data') || jsonb_build_object(
  'drive_file_id', v.drive_id,
  'drive_md5', v.md5,
  'drive_archive_status', 'verified',
  'pdf_disponibile', true,
  '_drive_payloads', coalesce(d.data->'_drive_payloads', '{}'::jsonb)
    || jsonb_build_object('pdf_data', jsonb_build_object(
      'drive_file_id', v.drive_id, 'md5', v.md5, 'bytes', v.bytes
    )),
  '_payload_stato', coalesce(d.data->'_payload_stato', '{}'::jsonb)
    || jsonb_build_object('pdf_data', 'pieno')
)
from _pdf_drive_verified v
where d.id = v.id and d.collection = v.collection
  and md5(decode(d.data->>'pdf_data', 'base64')) = v.md5;

create temporary table _quietanza_drive_verified on commit drop as
with pdf as (
  select d.id, d.collection,
         md5(decode(d.data->>'pdf_quietanza', 'base64')) as md5,
         octet_length(decode(d.data->>'pdf_quietanza', 'base64')) as bytes
  from gestionale.documents d
  where d.data->>'pdf_quietanza' like 'JVBERi0%'
)
select p.id, p.collection, p.md5, p.bytes, protocollo.drive_id
from pdf p
join lateral (
  select pd.drive_id
  from gestionale.protocollo_drive pd
  where pd.stato = 'attivo'
    and lower(pd.md5) = p.md5
    and pd.dimensione = p.bytes
  order by pd.percorso, pd.drive_id
  limit 1
) protocollo on true;

update gestionale.documents d
set data = (d.data - 'pdf_quietanza') || jsonb_build_object(
  '_drive_payloads', coalesce(d.data->'_drive_payloads', '{}'::jsonb)
    || jsonb_build_object('pdf_quietanza', jsonb_build_object(
      'drive_file_id', v.drive_id, 'md5', v.md5, 'bytes', v.bytes
    )),
  '_payload_stato', coalesce(d.data->'_payload_stato', '{}'::jsonb)
    || jsonb_build_object('pdf_quietanza', 'pieno')
)
from _quietanza_drive_verified v
where d.id = v.id and d.collection = v.collection
  and md5(decode(d.data->>'pdf_quietanza', 'base64')) = v.md5;

create temporary table _blob_pdf_drive_verified on commit drop as
with pdf as (
  select b.key, md5(decode(b.data, 'base64')) as md5,
         octet_length(decode(b.data, 'base64')) as bytes
  from gestionale.blobs b
  where b.data like 'JVBERi0%'
)
select p.key, p.md5, p.bytes,
       coalesce(protocollo.drive_id, verificato.drive_id) as drive_id
from pdf p
left join lateral (
  select pd.drive_id
  from gestionale.protocollo_drive pd
  where pd.stato = 'attivo'
    and lower(pd.md5) = p.md5
    and pd.dimensione = p.bytes
  order by pd.percorso, pd.drive_id
  limit 1
) protocollo on true
left join lateral (
  select d.data->>'drive_file_id' as drive_id
  from gestionale.documents d
  where d.data->>'blob_key' = p.key
    and lower(d.data->>'drive_md5') = p.md5
    and d.data->>'drive_archive_status' = 'verified'
  order by d.id
  limit 1
) verificato on true
where coalesce(protocollo.drive_id, verificato.drive_id) is not null;

update gestionale.documents d
set data = (d.data - 'blob_key' - 'contenuto_b64') || jsonb_build_object(
  'drive_file_id', v.drive_id,
  'drive_md5', v.md5,
  'drive_archive_status', 'verified',
  '_drive_payloads', coalesce(d.data->'_drive_payloads', '{}'::jsonb)
    || jsonb_build_object('contenuto_b64', jsonb_build_object(
      'drive_file_id', v.drive_id, 'md5', v.md5, 'bytes', v.bytes
    )),
  '_payload_stato', coalesce(d.data->'_payload_stato', '{}'::jsonb)
    || jsonb_build_object('contenuto_b64', 'pieno')
)
from _blob_pdf_drive_verified v
where d.data->>'blob_key' = v.key;

delete from gestionale.blobs b
using _blob_pdf_drive_verified v
where b.key = v.key
  and md5(decode(b.data, 'base64')) = v.md5;
