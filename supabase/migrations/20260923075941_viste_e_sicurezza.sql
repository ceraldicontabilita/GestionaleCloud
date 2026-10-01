-- Le due viste che servono a ogni pagina, e la sicurezza.

-- Saldo di ogni conto: saldo iniziale + entrate - uscite + giroconti in - giroconti out.
-- Un documento già abbinato a un movimento di banca non conta due volte.
create view saldi_conti
with (security_invoker = true) as
select c.id, c.nome, c.tipo, c.saldo_iniziale,
       coalesce(m.entrate,0)   as entrate,
       coalesce(m.uscite,0)    as uscite,
       coalesce(gi.dentro,0)   as giroconti_in,
       coalesce(go.fuori,0)    as giroconti_out,
       c.saldo_iniziale + coalesce(m.entrate,0) - coalesce(m.uscite,0)
         + coalesce(gi.dentro,0) - coalesce(go.fuori,0) as saldo
from conti c
left join (
  select conto_id,
         sum(importo) filter (where tipo='E') as entrate,
         sum(importo) filter (where tipo='U') as uscite
  from movimenti
  where pagata = true
    and id not in (select pagamento_id from abbinamenti)
  group by conto_id
) m on m.conto_id = c.id
left join (select verso_conto_id cid, sum(importo) dentro from giroconti group by 1) gi on gi.cid = c.id
left join (select da_conto_id cid, sum(importo) fuori from giroconti group by 1) go on go.cid = c.id;

-- Che cosa resta da riconciliare.
create view riconciliazione_aperta
with (security_invoker = true) as
select m.id, m.data, m.tipo, m.origine, m.descrizione, m.importo, m.conto_id,
       f.nome as fornitore, m.numero_doc, m.mezzo_canonico,
       case when m.origine = 'banca' then 'riga di banca senza documento'
            else 'documento senza pagamento collegato' end as manca
from movimenti m
left join fornitori f on f.id = m.fornitore_id
where m.tipo = 'U'
  and m.id not in (select documento_id from abbinamenti)
  and m.id not in (select pagamento_id from abbinamenti);

-- Sicurezza: tutto chiuso, apre solo chi ha fatto l'accesso.
do $$
declare t text;
begin
  foreach t in array array['conti','centri_costo','fornitori','dipendenti','aliquote_iva',
                           'aliquote_detrazione','movimenti','giroconti','abbinamenti',
                           'righe_documento','corrispettivi','chiusure','cedolini','f24',
                           'f24_righe','obbligazioni','dichiarazioni','codici_tributo',
                           'importazioni','posta']
  loop
    execute format('alter table %I enable row level security', t);
    execute format(
      'create policy %I on %I for all to authenticated using (true) with check (true)',
      t || '_authenticated', t);
  end loop;
end $$;

