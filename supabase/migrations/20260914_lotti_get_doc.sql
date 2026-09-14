create or replace function public.lotti_get_doc(
    p_secret text,
    p_collection text,
    p_doc_id text
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    result jsonb;
begin
    perform public.lotti_assert_secret(p_secret);

    select data
      into result
      from public.lotti_documents
     where collection = p_collection
       and doc_id = p_doc_id;

    return result;
end;
$$;

revoke all on function public.lotti_get_doc(text, text, text) from public;
grant execute on function public.lotti_get_doc(text, text, text) to anon, authenticated, service_role;
