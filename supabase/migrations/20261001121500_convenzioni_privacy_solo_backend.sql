-- La pagina ospite legge lo stato privacy tramite il backend, che presenta
-- il segreto runtime. Il browser non deve poter enumerare voucher e consensi.
revoke all on function public.bb_ospite_privacy_stato(text)
 from public, anon, authenticated;
grant execute on function public.bb_ospite_privacy_stato(text) to service_role;
