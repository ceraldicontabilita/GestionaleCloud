create or replace function bb_tit_sumup_configura(p text,chiave text) returns json language plpgsql security definer set search_path=public,extensions,vault as $$
declare r extensions.http_response; j jsonb; m text; sid uuid;
begin
 perform bb_check_tit(p);
 chiave := trim(coalesce(chiave,''));
 if length(chiave)<20 or chiave ~ '\s' then raise exception 'La chiave non sembra valida: controlla di averla copiata tutta'; end if;
 perform http_set_curlopt('CURLOPT_TIMEOUT','15');
 r := http(('GET','https://api.sumup.com/v0.1/me',array[http_header('Authorization','Bearer '||chiave)],null,null)::http_request);
 if r.status<>200 then raise exception 'SumUp non accetta questa chiave (errore %)',r.status; end if;
 j := r.content::jsonb;
 m := j->'merchant_profile'->>'merchant_code';
 if m is null then raise exception 'Chiave valida ma senza codice esercente: serve la chiave del conto commerciante'; end if;
 select id into sid from vault.secrets where name='sumup_api_key';
 if sid is null then perform vault.create_secret(chiave,'sumup_api_key','Chiave API SumUp per ricariche colazioni B&B');
 else perform vault.update_secret(sid,chiave); end if;
 insert into bb_config values ('sumup_merchant_code',m) on conflict (k) do update set v=excluded.v;
 return json_build_object('ok',true,'merchant',m,'nome',coalesce(j->'merchant_profile'->>'company_name',j->'merchant_profile'->>'doing_business_as'));
end $$;

create or replace function bb_tit_sumup_rimuovi(p text) returns void language plpgsql security definer set search_path=public,extensions,vault as $$
begin
 perform bb_check_tit(p);
 delete from vault.secrets where name='sumup_api_key';
 delete from bb_config where k='sumup_merchant_code';
end $$;

revoke all on function bb_tit_sumup_configura(text,text), bb_tit_sumup_rimuovi(text) from public;
grant execute on function bb_tit_sumup_configura(text,text), bb_tit_sumup_rimuovi(text) to anon;

