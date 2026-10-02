-- Indice di supporto alla FK usata dai movimenti di accredito/storno SumUp.
create index if not exists bb_movimenti_ricarica_sumup
  on public.bb_movimenti(ricarica_sumup_id)
  where ricarica_sumup_id is not null;
