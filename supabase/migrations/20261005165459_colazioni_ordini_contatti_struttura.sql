-- Email della struttura per il PDF di consegna degli ordini prodotti (solo backend, segreto di runtime).
create or replace function public.bb_ordini_contatti_struttura(psid uuid) returns json
language plpgsql stable security definer set search_path='' as $$
begin
 perform public.gc_assert_runtime_secret();
 return (select json_build_object('email', coalesce(trim(s.email),''), 'nome', s.nome)
         from public.bb_strutture s where s.id=psid);
end $$;
revoke all on function public.bb_ordini_contatti_struttura(uuid) from public, anon, authenticated;
grant execute on function public.bb_ordini_contatti_struttura(uuid) to anon;
