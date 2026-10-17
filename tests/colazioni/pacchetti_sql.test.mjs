/**
 * Esegue la migrazione reale sul motore PostgreSQL WASM PGlite, in memoria.
 * Dipendenza esatta @electric-sql/pglite 0.5.10, con pgcrypto; nessun servizio cloud.
 * Preparazione una tantum: npm ci --prefix tests/colazioni
 * Esecuzione: npm test --prefix tests/colazioni
 *
 * Questa suite verifica transazioni e vincoli SQL. PGlite usa una sola
 * connessione: non certifica la contesa tra processi PostgreSQL distinti.
 */
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { after, before, beforeEach, test } from 'node:test';
import { pathToFileURL } from 'node:url';

const moduleName = process.env.BB_QA_PGLITE_MODULE || '@electric-sql/pglite';
const moduleUrl = moduleName.startsWith('/') ? pathToFileURL(moduleName).href : moduleName;
const { PGlite } = await import(moduleUrl);
const cryptoModule = process.env.BB_QA_PGCRYPTO_MODULE || (moduleName.startsWith('/')
  ? new URL('./contrib/pgcrypto.js', moduleUrl).href : '@electric-sql/pglite/contrib/pgcrypto');
const { pgcrypto } = await import(cryptoModule);
const migrationsDir = new URL('../../supabase/migrations/', import.meta.url);
const migrations = readdirSync(migrationsDir)
  .filter(name => /^\d+_colazioni_pacchetti.*\.sql$/.test(name)).sort()
  .map(name => new URL(name, migrationsDir));
const A = '11111111-1111-1111-1111-111111111111';
const B = '22222222-2222-2222-2222-222222222222';
const db = new PGlite({ extensions: { pgcrypto } });
const raw = async (sql, args = []) => (await db.query(sql, args)).rows;
const scalar = async (sql, args = []) => Object.values((await raw(sql, args))[0])[0];
async function anon(sql, args = []) {
  await db.exec('set role anon');
  try { return await scalar(sql, args); }
  finally { await db.exec('reset role'); }
}
const purchase = (qta = 3, request = 'acquisto-test-0001', hotel = A) =>
  anon('select public.bb_alb_pacchetto_acquista($1,$2,$3,$4)', [hotel, `tk:${hotel}`, qta, request]);
const detail = (pid, hotel = A, after = null) => anon(
  'select public.bb_alb_pacchetto_dettaglio($1,$2,$3,$4,100)', [hotel, `tk:${hotel}`, pid, after]);
// I test storici verificano anche i singoli buoni: li chiedono esplicitamente,
// una pagina alla volta, anziché dipendere dal vecchio acquisto con tutti i QR.
async function buy(qta = 3, request = 'acquisto-test-0001', hotel = A) {
  const result = await purchase(qta, request, hotel);
  const pacchetto = await detail(result.pacchetto.id, hotel);
  let cursor = pacchetto.prossimo;
  while (cursor) {
    const page = await detail(result.pacchetto.id, hotel, cursor);
    pacchetto.vouchers.push(...page.vouchers);
    cursor = page.prossimo;
  }
  return { ...result, pacchetto };
}
const choose = (vid, formula = 'classica', prodotto = 152788, bevanda = 153756) =>
  anon('select public.bb_pacchetto_scelta($1,$2,$3,$4)', [vid, formula, prodotto, bevanda]);
const redeem = vid => anon("select public.bb_tit_riscatta('tk:bar-test',$1)", [vid]);
const hotelState = (hotel = A) => anon('select public.bb_alb_pacchetti($1,$2)', [hotel, `tk:${hotel}`]);

before(async () => {
  await db.exec(readFileSync(new URL('./fixture_pacchetti.sql', import.meta.url), 'utf8'));
  for (const migration of migrations) await db.exec(readFileSync(migration, 'utf8'));
});
after(async () => { await db.close(); });
beforeEach(async () => {
  await db.exec(`truncate public.qa_notifiche,public.bb_vouchers,public.bb_pacchetti,
    public.bb_movimenti,public.bb_strutture cascade;
    update public.qa_ospite_limite set n=0;
    update menu.menu_products set visible=true;
    insert into public.bb_strutture(id,nome) values ('${A}','B&B Alba'),('${B}','B&B Tramonto');
    insert into public.bb_movimenti(struttura_id,tipo,importo) values ('${A}','ricarica',400),('${B}','ricarica',40);`);
  await anon("select public.bb_tit_pacchetto_abilita('tk:bar-test',$1,true)", [A]);
  await anon("select public.bb_tit_pacchetto_abilita('tk:bar-test',$1,true)", [B]);
});

test('100 colazioni generano 100 QR distinti e un solo addebito; il retry restituisce lo stesso acquisto', async () => {
  const first = await buy(100);
  const p = first.pacchetto;
  assert.deepEqual([p.qta, p.consumate, p.residue, p.totale, first.saldo], [100, 0, 100, 400, 0]);
  assert.equal(new Set(p.vouchers.map(v => v.id)).size, 100);
  assert.ok(p.vouchers.every(v => v.qta === 1 && v.usate === 0 && v.id.length >= 32));
  const retry = await buy(100);
  assert.equal(retry.ripetuta, true);
  assert.deepEqual(retry.pacchetto, p);
  assert.equal(await scalar("select count(*)::int from public.bb_movimenti where tipo='prenotazione'"), 1);
  await assert.rejects(buy(99), /quantità diversa/);
  assert.equal(await scalar('select count(*)::int from public.bb_pacchetti'), 1);
});

test('la ricarica in attesa non compra: nessun addebito, pacchetto o QR parziale', async () => {
  await db.query('update public.bb_movimenti set confermato=false where struttura_id=$1', [A]);
  await assert.rejects(buy(1), /Saldo insufficiente/);
  assert.equal(await scalar('select count(*)::int from public.bb_pacchetti'), 0);
  assert.equal(await scalar('select count(*)::int from public.bb_vouchers'), 0);
  assert.equal(await scalar("select count(*)::int from public.bb_movimenti where tipo='prenotazione'"), 0);
});

test('i codici business risolvono il rifiuto solo dopo il controllo della richiesta già acquistata', async () => {
  const first = await buy(100, 'acquisto-da-verificare');
  assert.equal(first.saldo, 0);
  const replay = await buy(100, 'acquisto-da-verificare');
  assert.equal(replay.ripetuta, true);
  assert.equal(replay.pacchetto.id, first.pacchetto.id);
  await assert.rejects(buy(1, 'rifiuto-saldo-001'), error => error.code === 'PBB02');
  await anon("select public.bb_tit_pacchetto_abilita('tk:bar-test',$1,false)", [A]);
  assert.equal((await buy(100, 'acquisto-da-verificare')).pacchetto.id, first.pacchetto.id);
  await assert.rejects(buy(1, 'rifiuto-offerta-001'), error => error.code === 'PBB03');
  await anon("select public.bb_tit_pacchetto_abilita('tk:bar-test',$1,true)", [A]);
  await db.query('update menu.menu_products set visible=false where id=152788');
  assert.equal((await buy(100, 'acquisto-da-verificare')).pacchetto.id, first.pacchetto.id);
  await assert.rejects(buy(1, 'rifiuto-catalogo-001'), error => error.code === 'PBB01');
  assert.equal(await scalar("select count(*)::int from public.bb_movimenti where tipo='prenotazione'"), 1);
  assert.equal(await scalar('select count(*)::int from public.bb_pacchetti'), 1);
});

test('un errore dopo la creazione del pacchetto annulla anche addebito e QR precedenti', async () => {
  await db.exec(`create function public.qa_fallimento_voucher() returns trigger language plpgsql as $$
    begin
     if (select count(*) from public.bb_vouchers)>1 then raise exception 'guasto simulato voucher'; end if;
     return new;
    end $$;
    create trigger qa_fallimento before insert on public.bb_vouchers for each row execute function public.qa_fallimento_voucher();`);
  try { await assert.rejects(buy(4), /guasto simulato voucher/); }
  finally { await db.exec('drop trigger qa_fallimento on public.bb_vouchers; drop function public.qa_fallimento_voucher()'); }
  assert.equal(await scalar('select public.bb_saldo($1)', [A]), '400.00');
  assert.equal(await scalar('select count(*)::int from public.bb_pacchetti'), 0);
  assert.equal(await scalar('select count(*)::int from public.bb_vouchers'), 0);
  assert.equal(await scalar("select count(*)::int from public.bb_movimenti where tipo='prenotazione'"), 0);
});

test('quantità, identificativo richiesta e autenticazione vengono verificati dal server', async () => {
  for (const n of [0, -1, 1001, null]) await assert.rejects(buy(n), /Colazioni: da 1 a 1000/);
  await assert.rejects(buy(1, 'breve'), /Identificativo richiesta non valido/);
  await assert.rejects(anon("select public.bb_tit_pacchetto_crea('falso',$1,1,'titolare-falso')", [A]), /Sessione titolare/);
  await assert.rejects(anon('select public.bb_alb_pacchetto_acquista($1,$2,1,\'hotel-falso-001\')', [B, `tk:${A}`]), /Sessione albergatore/);
  assert.equal(await scalar('select count(*)::int from public.bb_pacchetti'), 0);
});

test('l’apertura pubblica del QR non consuma e non rivela altri QR o il saldo del B&B', async () => {
  const p = (await buy(3)).pacchetto;
  await buy(1, 'hotel-b-001', B);
  const v = await anon('select public.bb_pacchetto_voucher($1)', [p.vouchers[0].id]);
  assert.deepEqual([v.qta, v.usate, v.stato], [1, 0, 'da_scegliere']);
  for (const key of ['saldo', 'vouchers', 'pacchetti', 'struttura_id', 'consumate', 'residue']) assert.equal(key in v, false);
  assert.equal(JSON.stringify(v).includes('Tramonto'), false);
  assert.equal((await hotelState()).pacchetti[0].consumate, 0);
  assert.equal(await anon("select public.bb_pacchetto_voucher('SCONOSCIUTO')"), null);
  assert.equal((await anon('select public.bb_ospite($1)', [v.id])).id, v.id);
});

test('un unico dispatch ospite addebita una sola richiesta alla quota sia per soggiorni sia per pacchetti', async () => {
  const id = (await buy(1)).pacchetto.vouchers[0].id;
  for (let i = 0; i < 30; i++) {
    assert.equal((await anon("select public.bb_ospite('LEGACY')")).legacy, 'ospite');
  }
  assert.equal(await scalar('select n from public.qa_ospite_limite'), 30);
  for (let i = 0; i < 30; i++) {
    assert.equal((await anon('select public.bb_ospite($1)', [id])).id, id);
  }
  assert.equal(await scalar('select n from public.qa_ospite_limite'), 60);
  await assert.rejects(anon("select public.bb_ospite('LEGACY')"), /Limite ospite raggiunto/);
});

test('il prodotto deve appartenere alla formula, una sola bevanda è ammessa e la parigina consente solo acqua', async () => {
  const id = (await buy(1)).pacchetto.vouchers[0].id;
  await assert.rejects(choose(id, 'inesistente'), /Formula non prevista/);
  await assert.rejects(choose(id, 'classica', 153886), /Scegli un prodotto/);
  await assert.rejects(choose(id, 'classica', 152788, 999999), /Scegli un prodotto/);
  await assert.rejects(choose(id, 'salata', 153886, 153898), /parigina è abbinabile soltanto/);
  const chosen = await choose(id, 'salata', 153886, 153895);
  assert.deepEqual([chosen.scelta.prodotto_id, chosen.scelta.bevanda_id, chosen.stato], [153886, 153895, 'da_ritirare']);
  const delivered = await redeem(id);
  assert.equal(delivered.ok, true);
  assert.equal(delivered.voucher.voci.length, 2);
});

test('consegna monouso, contatori immediati uguali per hotel e bar, nessun altro addebito', async () => {
  const id = (await buy(3)).pacchetto.vouchers[0].id;
  assert.equal((await redeem(id)).ok, false);
  await choose(id);
  const delivery = await redeem(id);
  assert.equal(delivery.ok, true);
  assert.deepEqual([delivery.pacchetto.consumate, delivery.pacchetto.residue], [1, 2]);
  assert.equal((await redeem(id)).ok, false);
  const hotel = (await hotelState()).pacchetti[0];
  const bar = (await anon("select public.bb_tit_pacchetti('tk:bar-test',$1)", [A])).pacchetti[0];
  assert.deepEqual(hotel, bar);
  assert.deepEqual([hotel.qta, hotel.consumate, hotel.residue], [3, 1, 2]);
  assert.equal(await scalar('select cardinality(riscatti) from public.bb_vouchers where id=$1', [id]), 1);
  await assert.rejects(choose(id), /Buono già utilizzato/);
  assert.equal(await scalar("select count(*)::int from public.bb_movimenti where tipo='prenotazione'"), 1);
});

test('il saldo insufficiente successivo non può creare un secondo pacchetto o saldo negativo', async () => {
  await db.query('update public.bb_movimenti set importo=4 where struttura_id=$1', [A]);
  await buy(1);
  await assert.rejects(buy(1, 'secondo-acquisto-001'), /Saldo insufficiente/);
  assert.equal(await scalar('select public.bb_saldo($1)', [A]), '0.00');
  assert.equal(await scalar('select count(*)::int from public.bb_vouchers'), 1);
});

test('hotel A non legge B, nessuna lettura diretta delle tabelle o esecuzione helper privati', async () => {
  await buy(2);
  await buy(1, 'hotel-b-isolato-001', B);
  const onlyA = (await hotelState()).pacchetti;
  assert.equal(onlyA.length, 1);
  assert.equal(onlyA[0].struttura_id, A);
  await assert.rejects(anon('select public.bb_alb_pacchetti($1,$2)', [B, `tk:${A}`]), /Sessione albergatore/);
  await assert.rejects(anon('select * from public.bb_pacchetti'), /permission denied/);
  await assert.rejects(anon("select public.bb_pacchetto_acquista($1,1,'helper-privato-001')", [A]), /permission denied/);
});

test('i mutatori soggiorno non possono rimborsare o modificare i buoni del pacchetto', async () => {
  const id = (await buy(1)).pacchetto.vouchers[0].id;
  await assert.rejects(scalar("select public.bb_annulla($1,'test','titolare')", [id]), /non si annullano dal soggiorno/);
  await assert.rejects(anon("select public.bb_ospite_salva($1,'{}','[]',current_date)", [id]), /Usa la scelta del buono/);
  await assert.rejects(anon("select public.bb_ospite_menu_salva($1,current_date,'[]')", [id]), /Usa la scelta del buono/);
  assert.equal(await scalar("select count(*)::int from public.bb_movimenti where tipo='rimborso'"), 0);
  assert.equal((await hotelState()).pacchetti[0].residue, 1);
});

test('la scomparsa dal catalogo blocca nuovi acquisti ma conserva offerta e consumi già acquistati', async () => {
  const id = (await buy(2)).pacchetto.vouchers[0].id;
  await db.query('update menu.menu_products set visible=false where id=152788');
  const state = await hotelState();
  assert.equal(state.offerta.acquistabile, false);
  assert.equal(state.pacchetti.length, 1);
  assert.equal(state.pacchetti[0].residue, 2);
  assert.equal('offerta' in state.pacchetti[0], false);
  assert.ok((await detail(state.pacchetti[0].id)).offerta.formule.length);
  const before = await scalar('select count(*)::int from public.bb_movimenti');
  await assert.rejects(buy(1, 'catalogo-invalido-001'), /Offerta colazione non disponibile/);
  assert.equal(await scalar('select count(*)::int from public.bb_movimenti'), before);
  await choose(id);
  assert.equal((await redeem(id)).ok, true);
});

test('i pacchetti non impongono date di soggiorno e non entrano in produzione o notifiche dei soggiorni', async () => {
  const id = (await buy(2)).pacchetto.vouchers[0].id;
  await db.query("update public.bb_vouchers set data='2000-01-01',data_fine='2000-01-02' where id=$1", [id]);
  await choose(id);
  assert.equal((await redeem(id)).ok, true);
  assert.equal(await scalar('select count(*)::int from public.qa_notifiche'), 0);
  await db.query(`insert into public.bb_vouchers(id,struttura_id,fascia,qta,data,data_fine)
    values('LEGACY',$1,4,1,current_date,current_date)`, [A]);
  const hotel = await anon('select public.bb_alb_stato($1,$2)', [A, `tk:${A}`]);
  const bar = await anon("select public.bb_tit_stato('tk:bar-test')");
  assert.equal(hotel.legacy, 'stato_alb');
  assert.equal(bar.legacy, 'stato_tit');
  assert.deepEqual(hotel.vouchers, [{ id: 'LEGACY' }]);
  assert.deepEqual(bar.vouchers, [{ id: 'LEGACY' }]);
  assert.equal(await scalar('select count(*)::int from public.qa_notifiche'), 1);
  assert.equal((await anon("select public.bb_ospite('LEGACY')")).legacy, 'ospite');
});

test('soltanto il bar abilita la singola struttura; revocare nuovi acquisti conserva tutti i QR acquistati', async () => {
  const C = '33333333-3333-3333-3333-333333333333';
  await db.query("insert into public.bb_strutture(id,nome) values($1,'Nuovo B&B')", [C]);
  await db.query("insert into public.bb_movimenti(struttura_id,tipo,importo) values($1,'ricarica',40)", [C]);
  assert.equal(await scalar('select pacchetti_offerta_attiva from public.bb_strutture where id=$1', [C]), false);
  await assert.rejects(buy(2, 'hotel-c-default-001', C), /Offerta non attiva/);
  assert.equal(await scalar('select public.bb_saldo($1)', [C]), '40.00');
  await assert.rejects(anon('select public.bb_tit_pacchetto_abilita($1,$2,true)', [`tk:${C}`, C]), /Sessione titolare/);
  assert.deepEqual((await hotelState(C)).strutture_abilitate, []);
  await anon("select public.bb_tit_pacchetto_abilita('tk:bar-test',$1,true)", [C]);
  assert.deepEqual((await hotelState(C)).strutture_abilitate, [C]);
  const first = await buy(2, 'hotel-c-attivo-001', C);
  await anon("select public.bb_tit_pacchetto_abilita('tk:bar-test',$1,false)", [C]);
  await assert.rejects(buy(1, 'hotel-c-dopo-revoca', C), /Offerta non attiva/);
  const retry = await buy(2, 'hotel-c-attivo-001', C);
  assert.equal(retry.ripetuta, true);
  assert.equal(retry.pacchetto.id, first.pacchetto.id);
  assert.equal(retry.saldo, 32);
  const vid = first.pacchetto.vouchers[0].id;
  await choose(vid);
  assert.equal((await redeem(vid)).ok, true);
  assert.equal((await hotelState(C)).pacchetti[0].residue, 1);
});

test('il banco autenticato non consuma la quota degli ospiti, che resta applicata ai link pubblici', async () => {
  const pack = (await buy(65)).pacchetto;
  const id = pack.vouchers[0].id;
  for (const voucher of pack.vouchers) {
    assert.equal((await anon("select public.bb_tit_pacchetto_voucher('tk:bar-test',$1)", [voucher.id])).id, voucher.id);
    const result = await anon("select public.bb_tit_pacchetto_consegna('tk:bar-test',$1,'classica',152788,153756)", [voucher.id]);
    assert.equal(result.ok, true);
  }
  assert.equal(await scalar('select n from public.qa_ospite_limite'), 0);
  assert.equal((await hotelState()).pacchetti[0].consumate, 65);
  await assert.rejects(anon("select public.bb_tit_pacchetto_voucher('falso',$1)", [id]), /Sessione titolare/);
  await assert.rejects(anon("select public.bb_tit_pacchetto_consegna('falso',$1,'classica',152788,153756)", [id]), /Sessione titolare/);
  await assert.rejects(anon("select public.bb_pacchetto_scelta_salva($1,'classica',152788,153756)", [id]), /permission denied/);
  for (let i = 0; i < 60; i++) await anon('select public.bb_pacchetto_voucher($1)', [id]);
  await assert.rejects(anon('select public.bb_pacchetto_voucher($1)', [id]), /Limite ospite raggiunto/);
  assert.equal((await anon("select public.bb_tit_pacchetto_voucher('tk:bar-test',$1)", [id])).id, id);
});

test('la consegna del bar salva scelta e consumo nella stessa transazione; il replay conserva la prima scelta', async () => {
  const id = (await buy(1)).pacchetto.vouchers[0].id;
  await choose(id);
  await assert.rejects(anon("select public.bb_tit_pacchetto_consegna('tk:bar-test',$1,'salata',153886,153898)", [id]),
    /parigina è abbinabile soltanto/);
  const before = await anon('select public.bb_pacchetto_voucher($1)', [id]);
  assert.deepEqual([before.usate, before.scelta.bevanda_id], [0, 153756]);
  const delivery = await anon("select public.bb_tit_pacchetto_consegna('tk:bar-test',$1,'classica',152788,153754)", [id]);
  assert.equal(delivery.ok, true);
  assert.deepEqual([delivery.voucher.usate, delivery.voucher.scelta.bevanda_id], [1, 153754]);
  const retry = await anon("select public.bb_tit_pacchetto_consegna('tk:bar-test',$1,'salata',153886,153895)", [id]);
  assert.equal(retry.ok, false);
  assert.equal(retry.voucher.scelta.bevanda_id, 153754);
  assert.equal(retry.pacchetto.consumate, 1);
  assert.equal(await scalar('select cardinality(riscatti) from public.bb_vouchers where id=$1', [id]), 1);
});
