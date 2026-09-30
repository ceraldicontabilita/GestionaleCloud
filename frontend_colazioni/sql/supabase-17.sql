-- v17: fix "DELETE requires a WHERE clause" nel salvataggio dell'elenco senza glutine
create or replace function bb_tit_glutine_salva(p text, righe jsonb) returns int language plpgsql security definer set search_path=public,extensions as $$
declare r jsonb; i int:=0;
begin
 perform bb_check_tit(p);
 if jsonb_typeof(righe)<>'array' or jsonb_array_length(righe)>200 then raise exception 'Elenco non valido (max 200 voci)'; end if;
 delete from bb_senza_glutine where true;
 for r in select * from jsonb_array_elements(righe) loop
  if coalesce(trim(r->>'nome'),'')='' then continue; end if;
  i:=i+1;
  insert into bb_senza_glutine(nome,differenza,per,ordine) values (left(trim(r->>'nome'),80),least(999,greatest(0,coalesce((r->>'differenza')::numeric,0))),left(coalesce(trim(r->>'per'),''),40),i);
 end loop;
 return i;
end $$;
