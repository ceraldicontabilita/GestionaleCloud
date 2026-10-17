/** Proiezioni e paginazione sulla migrazione reale, in PostgreSQL PGlite locale. */
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { after, before, beforeEach, test } from 'node:test';
import { pathToFileURL } from 'node:url';

const moduleName = process.env.BB_QA_PGLITE_MODULE || '@electric-sql/pglite';
const moduleUrl = moduleName.startsWith('/') ? pathToFileURL(moduleName).href : moduleName;
const { PGlite } = await import(moduleUrl);
const { pgcrypto } = await import(process.env.BB_QA_PGCRYPTO_MODULE || (moduleName.startsWith('/')
  ? new URL('./contrib/pgcrypto.js', moduleUrl).href : '@electric-sql/pglite/contrib/pgcrypto'));
const db = new PGlite({ extensions: { pgcrypto } });
const A = '11111111-1111-1111-1111-111111111111';
const B = '22222222-2222-2222-2222-222222222222';
const scalar = async (sql, args = []) => Object.values((await db.query(sql, args)).rows[0])[0];
async function anon(sql, args = []) {
  await db.exec('set role anon');
  try { return await scalar(sql, args); } finally { await db.exec('reset role'); }
}
const buy = (qta = 3, key = 'riepilogo-acquisto-001', sid = A) => anon(
  'select public.bb_alb_pacchetto_acquista($1,$2,$3,$4)', [sid, `tk:${sid}`, qta, key]);
const list = (sid = A) => anon('select public.bb_alb_pacchetti($1,$2)', [sid, `tk:${sid}`]);
const totals = (sid = A) => anon('select public.bb_alb_pacchetti_totali($1,$2)', [sid, `tk:${sid}`]);
const detail = (pid, sid = A, cursor = null, limit = 50) => anon(
  'select public.bb_alb_pacchetto_dettaglio($1,$2,$3,$4,$5)', [sid, `tk:${sid}`, pid, cursor, limit]);
const summaryKeys = ['id', 'struttura_id', 'struttura', 'qta', 'consumate', 'residue',
  'prezzo_unitario', 'totale', 'creato'].sort();

before(async () => {
  await db.exec(readFileSync(new URL('./fixture_pacchetti.sql', import.meta.url), 'utf8'));
  const directory = new URL('../../supabase/migrations/', import.meta.url);
  for (const filename of readdirSync(directory).filter(name => /^\d+_colazioni_pacchetti.*\.sql$/.test(name)).sort()) {
    await db.exec(readFileSync(new URL(filename, directory), 'utf8'));
  }
});
after(async () => { await db.close(); });
beforeEach(async () => {
  await db.exec(`truncate public.qa_notifiche,public.bb_vouchers,public.bb_pacchetti,
   public.bb_movimenti,public.bb_strutture cascade;
   update public.qa_ospite_limite set n=0;
   update menu.menu_products set visible=true;
   insert into public.bb_strutture(id,nome,pacchetti_offerta_attiva)
    values ('${A}','B&B Alba',true),('${B}','B&B Tramonto',true);
   insert into public.bb_movimenti(struttura_id,tipo,importo)
    values ('${A}','ricarica',40000),('${B}','ricarica',4000);`);
});

test('acquisto e retry restituiscono solo il riepilogo, anche per 1000 QR, e non duplicano l’addebito', async () => {
  const first = await buy(1000);
  const retry = await buy(1000);
  assert.deepEqual(Object.keys(first.pacchetto).sort(), summaryKeys);
  assert.deepEqual(first.pacchetto, retry.pacchetto);
  assert.equal(retry.ripetuta, true);
  assert.deepEqual([first.pacchetto.qta, first.pacchetto.consumate, first.pacchetto.residue], [1000, 0, 1000]);
  assert.equal(await scalar("select count(*)::int from public.bb_movimenti where tipo='prenotazione'"), 1);
  assert.equal(await scalar('select count(*)::int from public.bb_vouchers'), 1000);
  assert.equal(first.saldo, 36000);
  assert.ok(JSON.stringify(first).length < 1000);
});

test('1000 QR si leggono in pagine da 50 senza ripetizioni o omissioni e senza consumi', async () => {
  const pid = (await buy(1000)).pacchetto.id;
  const expected = (await db.query('select id from public.bb_vouchers where pacchetto_id=$1 order by id', [pid])).rows.map(v => v.id);
  const received = [];
  let cursor = null, pages = 0;
  do {
    const page = await detail(pid, A, cursor);
    assert.equal(page.limite, 50);
    assert.equal(page.vouchers.length, 50);
    assert.deepEqual([page.qta, page.consumate, page.residue], [1000, 0, 1000]);
    assert.ok(page.offerta.formule.length);
    assert.ok(JSON.stringify(page).length < 25000);
    received.push(...page.vouchers.map(v => v.id));
    cursor = page.prossimo;
    if (cursor) assert.equal(cursor, received.at(-1));
    pages++;
  } while (cursor);
  assert.equal(pages, 20);
  assert.deepEqual(received, expected);
  assert.equal(new Set(received).size, 1000);
  const end = await detail(pid, A, received.at(-1));
  assert.deepEqual(end.vouchers, []);
  assert.equal(end.prossimo, null);
  assert.equal(await scalar('select sum(usate)::int from public.bb_vouchers'), 0);
  assert.equal(await scalar('select n from public.qa_ospite_limite'), 0);
});

test('limiti e cursori non validi vengono rifiutati; il titolare usa la stessa pagina autorizzata', async () => {
  const pid = (await buy(101)).pacchetto.id;
  const first = await detail(pid, A, null, 100);
  assert.equal(first.vouchers.length, 100);
  assert.ok(first.prossimo);
  const last = await detail(pid, A, first.prossimo, 100);
  assert.equal(last.vouchers.length, 1);
  assert.equal(last.prossimo, null);
  const bar = await anon("select public.bb_tit_pacchetto_dettaglio('tk:bar-test',$1,null,100)", [pid]);
  assert.deepEqual(bar, first);
  for (const limit of [0, -1, 101, 10000, null]) {
    await assert.rejects(detail(pid, A, null, limit), /Pagina QR: da 1 a 100/);
  }
  await assert.rejects(detail(pid, A, 'codice-non-esistente'), /Cursore pagina QR non valido/);
  const other = (await buy(1, 'altro-pacchetto-001')).pacchetto.id;
  const wrongCursor = (await detail(other)).vouchers[0].id;
  await assert.rejects(detail(pid, A, wrongCursor), /Cursore pagina QR non valido/);
});

test('un altro albergatore non legge dettaglio o conteggi e gli helper non sono RPC pubblici', async () => {
  const pid = (await buy()).pacchetto.id;
  const b = (await buy(7, 'acquisto-hotel-b-001', B)).pacchetto.id;
  await assert.rejects(detail(b), /Pacchetto non disponibile/);
  await assert.rejects(anon('select public.bb_alb_pacchetto_dettaglio($1,$2,$3)', [B, `tk:${A}`, b]), /Sessione albergatore/);
  await assert.rejects(anon('select public.bb_alb_pacchetti_totali($1,$2)', [B, `tk:${A}`]), /Sessione albergatore/);
  await assert.rejects(anon("select public.bb_tit_pacchetto_dettaglio('falso',$1)", [pid]), /Sessione titolare/);
  await assert.rejects(anon("select public.bb_tit_pacchetti_totali('falso')"), /Sessione titolare/);
  await assert.rejects(anon('select public.bb_pacchetto_dettaglio_json($1)', [pid]), /permission denied/);
  await assert.rejects(anon('select public.bb_pacchetti_totali_json($1)', [A]), /permission denied/);
  assert.deepEqual(await totals(), { qta: 3, consumate: 0, residue: 3 });
  assert.deepEqual(await totals(B), { qta: 7, consumate: 0, residue: 7 });
});

test('riepiloghi e totali non invocano i lettori di dettaglio e restano leggeri su molti pacchetti', async () => {
  // Dati sintetici locali: 24 pacchetti da 1000 QR. Nessuna chiamata cloud.
  await db.query(`with movimenti as (
   insert into public.bb_movimenti(struttura_id,tipo,importo)
   select $1,'prenotazione',-4000 from generate_series(1,24) returning id
  ), pacchetti as (
   insert into public.bb_pacchetti(struttura_id,qta,prezzo_unitario,idempotenza,offerta,movimento_id)
   select $1,1000,4,'grande-'||id::text,public.bb_pacchetto_offerta(),id from movimenti returning id
  )
  insert into public.bb_vouchers(id,struttura_id,fascia,qta,usate,data,data_fine,pacchetto_id)
  select upper(encode(extensions.gen_random_bytes(16),'hex')),$1,4,1,0,current_date,'infinity',k.id
  from pacchetti k cross join generate_series(1,1000)`, [A]);
  await db.query('update public.bb_vouchers set usate=1 where id in (select id from public.bb_vouchers order by id limit 123)');
  const originals = await db.query(`select pg_get_functiondef(oid) as ddl from pg_proc
   where oid in ('public.bb_pacchetto_json(uuid)'::regprocedure,
    'public.bb_pacchetto_dettaglio_json(uuid,text,integer)'::regprocedure)`);
  try {
    // Una regressione che torni al lettore per-pacchetto fallirebbe, anche se
    // cancellasse la chiave "vouchers" dal JSON dopo averla materializzata.
    await db.exec(`create or replace function public.bb_pacchetto_json(pid uuid) returns jsonb
     language plpgsql as $$ begin raise exception 'lettore pacchetto invocato dal riepilogo'; end $$;
     create or replace function public.bb_pacchetto_dettaglio_json(pid uuid,pdopo text default null,plimite integer default 50)
     returns jsonb language plpgsql as $$ begin raise exception 'QR invocati dal riepilogo'; end $$;`);
    const hotel = await list();
    assert.equal(hotel.pacchetti.length, 24);
    for (const p of hotel.pacchetti) assert.deepEqual(Object.keys(p).sort(), summaryKeys);
    assert.ok(JSON.stringify(hotel).length < 15000);
    const bar = await anon("select public.bb_tit_pacchetti('tk:bar-test',$1)", [A]);
    assert.deepEqual(hotel, bar);
    const expected = { qta: 24000, consumate: 123, residue: 23877 };
    assert.deepEqual(await totals(), expected);
    assert.deepEqual(await anon("select public.bb_tit_pacchetti_totali('tk:bar-test')"), expected);
    assert.deepEqual(Object.keys(await totals()).sort(), ['consumate', 'qta', 'residue']);
    assert.equal(await scalar('select sum(usate)::int from public.bb_vouchers'), 123);
  } finally {
    for (const { ddl } of originals.rows) await db.exec(ddl);
  }
});

test('un consumo aggiorna gli stessi conteggi in dettaglio, elenco e home per hotel e bar', async () => {
  const pid = (await buy(1000)).pacchetto.id;
  const first = await detail(pid);
  await anon("select public.bb_tit_pacchetto_consegna('tk:bar-test',$1,'classica',152788,153756)", [first.vouchers[0].id]);
  assert.deepEqual(await totals(), { qta: 1000, consumate: 1, residue: 999 });
  assert.deepEqual(await anon("select public.bb_tit_pacchetti_totali('tk:bar-test')"), await totals());
  const p = (await list()).pacchetti[0];
  assert.deepEqual([p.qta, p.consumate, p.residue], [1000, 1, 999]);
  assert.deepEqual([...(Object.values(await totals()))].sort((a, b) => a - b), [1, 999, 1000]);
  assert.equal((await detail(pid)).consumate, 1);
  assert.equal(await scalar("select count(*)::int from public.bb_movimenti where tipo='prenotazione'"), 1);
});

test('catalogo cambiato e offerta revocata non cancellano il dettaglio dell’acquisto', async () => {
  const pid = (await buy()).pacchetto.id;
  const original = (await detail(pid)).offerta;
  await db.exec(`update menu.menu_products set visible=false;
   update public.bb_strutture set pacchetti_offerta_attiva=false;`);
  assert.equal((await list()).offerta.acquistabile, false);
  assert.deepEqual((await detail(pid)).offerta, original);
  assert.deepEqual(await totals(), { qta: 3, consumate: 0, residue: 3 });
});

test('nessun pacchetto produce zero conteggi senza addebiti, consumi o richieste ospite', async () => {
  assert.deepEqual(await totals(), { qta: 0, consumate: 0, residue: 0 });
  assert.deepEqual(await anon("select public.bb_tit_pacchetti_totali('tk:bar-test')"), await totals());
  assert.deepEqual((await list()).pacchetti, []);
  assert.equal(await scalar("select count(*)::int from public.bb_movimenti where tipo='prenotazione'"), 0);
  assert.equal(await scalar('select count(*)::int from public.bb_vouchers'), 0);
  assert.equal(await scalar('select n from public.qa_ospite_limite'), 0);
});
