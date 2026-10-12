select
public.gc_payload_stato('{"pdf_data":"JVBERi0x"}'::jsonb,ARRAY['pdf_data']) = '{"pdf_data":"pieno"}'::jsonb AS inline_ok,
public.gc_payload_stato('{"pdf_data":""}'::jsonb,ARRAY['pdf_data']) = '{"pdf_data":"vuoto"}'::jsonb AS empty_ok,
public.gc_payload_stato('{"pdf_data":null}'::jsonb,ARRAY['pdf_data']) = '{"pdf_data":"nullo"}'::jsonb AS null_ok,
public.gc_payload_stato('{}'::jsonb,ARRAY['pdf_data']) = '{"pdf_data":"assente"}'::jsonb AS absent_ok,
public.gc_payload_stato('{"_drive_payloads":{"pdf_data":{"drive_file_id":"fixture_id","md5":"00000000000000000000000000000000"}}}'::jsonb,ARRAY['pdf_data']) = '{"pdf_data":"pieno"}'::jsonb AS drive_ok,
public.gc_payload_stato('{"_drive_payloads":{"pdf_data":{"drive_file_id":"fixture_id"}}}'::jsonb,ARRAY['pdf_data']) = '{"pdf_data":"assente"}'::jsonb AS incomplete_reference_ok,
public.gc_payload_stato('{"_payload_stato":{"pdf_data":"pieno"}}'::jsonb,ARRAY['pdf_data']) = '{"pdf_data":"assente"}'::jsonb AS unsupported_flag_ok;
