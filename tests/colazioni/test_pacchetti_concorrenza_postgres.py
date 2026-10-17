"""Contesa vera fra due connessioni PostgreSQL, distinta dai test PGlite.

Solo database locale usa e getta: avviare con il runner dedicato.
Senza PostgreSQL nativo questi test sono esplicitamente saltati.
"""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
HOTEL = "11111111-1111-1111-1111-111111111111"


@unittest.skipUnless(os.environ.get("BB_QA_PG_READY") == "1", "richiede PostgreSQL nativo locale: usare scripts/collaudo_colazioni_pacchetti.py")
class PacchettiConcorrenzaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.psql = os.environ["BB_QA_PSQL"]
        cls.database = os.environ["BB_QA_NAME"]
        if not cls.database.startswith("qa_colazioni_"):
            raise RuntimeError("Serve un database usa e getta qa_colazioni_*")
        cls.connection = ["-h", os.environ["BB_QA_HOST"], "-p", os.environ["BB_QA_PORT"],
                          "-U", os.environ["BB_QA_USER"], "-d", cls.database]
        migrations = sorted(Path(os.environ["BB_QA_MIGRATIONS_DIR"]).glob("*_colazioni_pacchetti*.sql"))
        for file in (ROOT / "tests/colazioni/fixture_pacchetti.sql", *migrations):
            result = cls.execute(file.read_text(encoding="utf-8"))
            if result.returncode:
                raise RuntimeError(result.stderr)

    @classmethod
    def execute(cls, sql, anon=False, trattieni_lock=False):
        if trattieni_lock:
            sql = "begin;\n" + sql + ";select pg_sleep(0.1);commit;"
        return subprocess.run([cls.psql, "-X", "-qAt", "-v", "ON_ERROR_STOP=1", *cls.connection],
                              input=("set role anon;\n" if anon else "") + sql,
                              text=True, capture_output=True, timeout=25)

    def sql(self, sql, anon=False):
        result = self.execute(sql, anon=anon)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def setUp(self):
        self.sql("""
            truncate public.qa_notifiche,public.bb_vouchers,public.bb_pacchetti,public.bb_movimenti,public.bb_strutture cascade;
            update public.qa_ospite_limite set n=0;
            insert into public.bb_strutture(id,nome) values ('%s','B&B test');
            insert into public.bb_movimenti(struttura_id,tipo,importo) values ('%s','ricarica',400);
        """ % (HOTEL, HOTEL))
        self.sql("select public.bb_tit_pacchetto_abilita('tk:bar-test','%s',true)" % HOTEL, anon=True)

    def parallelo(self, queries):
        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(lambda query: self.execute(query, anon=True, trattieni_lock=True), queries))

    def dettaglio(self, pid):
        return json.loads(self.sql(
            "select public.bb_alb_pacchetto_dettaglio('%s','tk:%s','%s')" % (HOTEL, HOTEL, pid),
            anon=True))

    def test_due_acquisti_con_stessa_richiesta_creano_un_solo_addebito_e_gli_stessi_qr(self):
        query = "select public.bb_alb_pacchetto_acquista('%s','tk:%s',3,'concorrenza-idem-001')" % (HOTEL, HOTEL)
        results = self.parallelo([query, query])
        self.assertTrue(all(r.returncode == 0 for r in results), [r.stderr for r in results])
        packages = [json.loads(r.stdout)["pacchetto"] for r in results]
        self.assertEqual(packages[0]["id"], packages[1]["id"])
        self.assertNotIn("vouchers", packages[0])
        self.assertEqual(self.dettaglio(packages[0]["id"])["vouchers"],
                         self.dettaglio(packages[1]["id"])["vouchers"])
        self.assertEqual(self.sql("select count(*) from public.bb_movimenti where tipo='prenotazione'"), "1")
        self.assertEqual(self.sql("select count(*) from public.bb_vouchers"), "3")

    def test_due_acquisti_sull_ultimo_saldo_non_possono_spenderlo_due_volte(self):
        self.sql("update public.bb_movimenti set importo=4 where struttura_id='%s'" % HOTEL)
        queries = ["select public.bb_alb_pacchetto_acquista('%s','tk:%s',1,'ultimo-saldo-%03d')" % (HOTEL, HOTEL, i)
                   for i in range(2)]
        results = self.parallelo(queries)
        self.assertEqual(sum(r.returncode == 0 for r in results), 1, [r.stderr for r in results])
        self.assertTrue(any("Saldo insufficiente" in r.stderr for r in results))
        self.assertEqual(self.sql("select public.bb_saldo('%s')" % HOTEL), "0.00")
        self.assertEqual(self.sql("select count(*) from public.bb_vouchers"), "1")

    def test_due_consegne_dello_stesso_qr_consumano_una_colazione_e_conservano_una_scelta(self):
        package = json.loads(self.sql("select public.bb_alb_pacchetto_acquista('%s','tk:%s',2,'consegna-concorrente-001')" % (HOTEL, HOTEL), anon=True))["pacchetto"]
        vid = self.dettaglio(package["id"])["vouchers"][0]["id"]
        queries = ["select public.bb_tit_pacchetto_consegna('tk:bar-test','%s','classica',152788,%d)" % (vid, bevanda)
                   for bevanda in (153756, 153754)]
        results = self.parallelo(queries)
        self.assertTrue(all(r.returncode == 0 for r in results), [r.stderr for r in results])
        responses = [json.loads(r.stdout) for r in results]
        self.assertEqual(sum(r["ok"] for r in responses), 1)
        self.assertEqual(responses[0]["voucher"]["scelta"], responses[1]["voucher"]["scelta"])
        state = json.loads(self.sql("select public.bb_alb_pacchetti('%s','tk:%s')" % (HOTEL, HOTEL), anon=True))
        self.assertEqual(state["pacchetti"][0]["consumate"], 1)
        self.assertEqual(state["pacchetti"][0]["residue"], 1)
        self.assertEqual(self.sql("select cardinality(riscatti) from public.bb_vouchers where id='%s'" % vid), "1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
