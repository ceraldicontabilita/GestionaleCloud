-- Le tabelle B&B sono RPC-only: nessuna funzione deve ereditare EXECUTE da
-- PUBLIC. I grant espliciti ad anon/authenticated restano invariati.
do $$
declare
  funzione regprocedure;
begin
  for funzione in
    select p.oid::regprocedure
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'public'
      and p.proname like 'bb\_%' escape '\'
  loop
    execute format('revoke execute on function %s from public', funzione);
  end loop;
end
$$;

-- Il logout del titolare deve revocare la sessione nel database, non soltanto
-- rimuovere il token da sessionStorage.
create or replace function public.bb_tit_logout(p text)
returns void
language sql
security definer
set search_path = public, extensions
as $$
  delete from public.bb_sessioni
  where ruolo = 'tit'
    and token_hash = public.bb_tok_hash(p)
$$;

revoke all on function public.bb_tit_logout(text) from public, anon, authenticated;
grant execute on function public.bb_tit_logout(text) to anon, authenticated;
