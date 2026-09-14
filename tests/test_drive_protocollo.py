"""Protocollo-indice vivo dei documenti Drive (app/services/drive_protocollo.py).

Nessuna rete: il client Drive e la connessione Postgres sono finti. Si
verificano le derivazioni pure (percorso, area, anno, canonico, forma
pubblica), la visita ricorsiva con paginazione e il giro completo: righe
nuove/aggiornate, marcatura 'rimosso' delle sparite, ordine delle query.
"""
import asyncio
from datetime import datetime, timezone

import pytest

from app.config import settings
from app.services import drive_protocollo as modulo
from app.services import postgres_diretto

CARTELLA = modulo.CARTELLA_MIME


def _run(coro):
    return asyncio.run(coro)


# ── finti ────────────────────────────────────────────────────────────────────

class _Lista:
    def __init__(self, drive, kw):
        self.drive, self.kw = drive, kw

    def execute(self):
        parent = self.kw["q"].split("'")[1]
        pagina = self.kw.get("pageToken") or "0"
        pagine = self.drive.pagine(parent)
        idx = int(pagina)
        out = {"files": pagine[idx]}
        if idx + 1 < len(pagine):
            out["nextPageToken"] = str(idx + 1)
        return out


class _Files:
    def __init__(self, drive):
        self.drive = drive
        self.aggiornati = []

    def list(self, **kw):
        return _Lista(self.drive, kw)

    def update(self, **kw):
        self.aggiornati.append(kw)
        class _E:
            def execute(_self):
                return {"id": kw["fileId"], "parents": [kw["addParents"]]}
        return _E()


class DriveFinto:
    """Albero in memoria: parent_id -> lista di pagine di elementi."""

    def __init__(self, albero):
        self.albero = albero
        self._files = _Files(self)

    def files(self):
        return self._files

    def pagine(self, parent):
        elementi = self.albero.get(parent, [])
        if parent == "ROOT" and len(elementi) > 2:
            return [elementi[:2], elementi[2:]]  # paginazione su due pagine
        return [elementi]


def _cartella(id_, nome, parent):
    return {"id": id_, "name": nome, "mimeType": CARTELLA, "parents": [parent]}


def _file(id_, nome, parent, md5="aa", size="1000", creato="2026-01-02T10:00:00Z"):
    return {"id": id_, "name": nome, "mimeType": "application/pdf", "parents": [parent],
            "size": size, "md5Checksum": md5, "createdTime": creato,
            "modifiedTime": "2026-09-01T08:00:00Z", "webViewLink": f"https://drive/{id_}"}


ALBERO = {
    "ROOT": [
        _cartella("A05", "05_PERSONALE_E_CEDOLINI", "ROOT"),
        _cartella("A90", "90_ARCHIVIO_STORICO", "ROOT"),
        _file("F0", "INDICE.xlsx", "ROOT", md5="idx", size="50"),
    ],
    "A05": [_cartella("C1", "CEDOLINI PAGA", "A05")],
    "C1": [_cartella("P1", "ROSSI MARIO", "C1")],
    "P1": [_cartella("Y24", "2024", "P1"), _file("F1", "Busta paga Marzo 2025.pdf", "P1", md5="m1")],
    "Y24": [_file("F2", "cedolino_03.pdf", "Y24", md5="m2")],
    "A90": [_file("F3", "Busta paga Marzo 2025.pdf", "A90", md5="m1", creato="2025-01-01T00:00:00Z")],
}


class ConnFinta:
    def __init__(self, esistenti=()):
        self.esistenti = set(esistenti)
        self.sql = []
        self.upsert_righe = []
        self.chiusa = False

    async def fetchval(self, sql, *args):
        self.sql.append(sql)
        if "protocollo_drive_giri" in sql:
            return 7
        if "count(*)" in sql:
            return 3
        return None

    async def fetch(self, sql, *args):
        self.sql.append(sql)
        if sql.startswith("insert into gestionale.protocollo_drive ("):
            ids = args[0]
            self.upsert_righe.extend(zip(*args[:len(modulo._COLONNE)]))
            return [{"inserito": i not in self.esistenti} for i in ids]
        if "from gestionale.protocollo_drive" in sql and "select *" in sql:
            return [{
                "drive_id": "F1", "nome": "Busta paga Marzo 2025.pdf", "mime": "application/pdf",
                "estensione": "pdf", "dimensione": 1000, "md5": "m1", "parent_id": "P1",
                "percorso": "05_PERSONALE_E_CEDOLINI/CEDOLINI PAGA/ROSSI MARIO/Busta paga Marzo 2025.pdf",
                "area": "05_PERSONALE_E_CEDOLINI", "categoria": "CEDOLINI PAGA", "anno": 2025,
                "creato_drive": None, "modificato_drive": datetime(2026, 9, 1, tzinfo=timezone.utc),
                "link": "https://drive/F1", "stato": "attivo", "visto_il": None, "rimosso_il": None,
                "duplicato_di": None, "collegamento_tipo": "hr_cedolino", "collegamento_id": "ced-1",
                "aggiornato_il": None,
            }]
        return []

    async def execute(self, sql, *args):
        self.sql.append(sql)
        if sql.startswith("update gestionale.protocollo_drive set stato = 'rimosso'"):
            return "UPDATE 1"
        if "duplicato_di = case" in sql:
            return "UPDATE 2"
        if "set collegamento_tipo" in sql:
            return "UPDATE 1"
        return "INSERT 0 0"

    async def fetchrow(self, sql, *args):
        self.sql.append(sql)
        return None

    async def close(self):
        self.chiusa = True


# ── funzioni pure ─────────────────────────────────────────────────────────────

def test_anno_preferisce_la_cartella_anno_poi_il_nome():
    assert modulo.anno_da("cedolino_03.pdf", ["05", "CEDOLINI", "2024"]) == 2024
    assert modulo.anno_da("Busta paga Marzo 2025.pdf", ["05", "CEDOLINI", "ROSSI"]) == 2025
    assert modulo.anno_da("scan.pdf", ["05", "F24 2023 acconti"]) == 2023
    assert modulo.anno_da("scan.pdf", ["05"]) is None
    assert modulo.anno_da("fattura 12345678.pdf", []) is None  # 8 cifre non e' un anno


def test_deriva_riga_percorso_area_categoria_link():
    riga = modulo.deriva_riga(_file("F2", "cedolino_03.pdf", "Y24", md5="m2"),
                              ["05_PERSONALE_E_CEDOLINI", "CEDOLINI PAGA", "ROSSI MARIO", "2024"])
    assert riga["percorso"] == "05_PERSONALE_E_CEDOLINI/CEDOLINI PAGA/ROSSI MARIO/2024/cedolino_03.pdf"
    assert riga["area"] == "05_PERSONALE_E_CEDOLINI"
    assert riga["categoria"] == "CEDOLINI PAGA"
    assert riga["anno"] == 2024
    assert riga["estensione"] == "pdf"
    assert riga["dimensione"] == 1000
    assert riga["md5"] == "m2"
    assert riga["parent_id"] == "Y24"
    assert riga["link"] == "https://drive/F2"
    assert riga["creato_drive"].tzinfo is not None


def test_canonico_evita_archivio_storico_e_quarantena():
    a = {"drive_id": "A", "percorso": "90_ARCHIVIO_STORICO/x.pdf", "creato_drive": datetime(2020, 1, 1, tzinfo=timezone.utc)}
    b = {"drive_id": "B", "percorso": "01_FATTURE/x.pdf", "creato_drive": datetime(2026, 1, 1, tzinfo=timezone.utc)}
    c = {"drive_id": "C", "percorso": "_QUARANTENA_DUPLICATI/x.pdf", "creato_drive": datetime(2019, 1, 1, tzinfo=timezone.utc)}
    assert modulo.scegli_canonico([a, b, c]) == "B"
    # a parita' di collocazione vince la piu' vecchia, poi il percorso piu' corto
    d = {"drive_id": "D", "percorso": "01_FATTURE/sub/x.pdf", "creato_drive": datetime(2026, 1, 1, tzinfo=timezone.utc)}
    assert modulo.scegli_canonico([b, d]) == "B"
    assert modulo.scegli_canonico([d, b]) == "B"


def test_riga_pubblica_ha_la_forma_del_tab_indice_drive():
    pub = modulo.riga_pubblica({
        "drive_id": "F1", "nome": "Busta paga Marzo 2025.pdf", "percorso": "05/CEDOLINI PAGA/ROSSI MARIO/Busta paga Marzo 2025.pdf",
        "area": "05", "categoria": "CEDOLINI PAGA", "anno": 2025, "dimensione": 2048,
        "modificato_drive": datetime(2026, 9, 1, tzinfo=timezone.utc), "link": "https://drive/F1",
        "stato": "attivo", "duplicato_di": "F3", "collegamento_tipo": "hr_cedolino", "collegamento_id": "c1",
    })
    assert pub["document_id"] == "F1"
    assert pub["subject"] == "ROSSI MARIO"
    assert pub["domain"] == "05"
    assert pub["display_title"] == "Busta paga Marzo 2025"
    assert pub["status"] == "DUPLICATO"
    assert pub["drive_url"] == "https://drive/F1"
    assert "2 KB" in pub["summary"] and "hr_cedolino" in pub["summary"]
    rimossa = modulo.riga_pubblica({"drive_id": "X", "nome": "a.pdf", "percorso": "a.pdf", "stato": "rimosso",
                                    "rimosso_il": datetime(2026, 9, 14, tzinfo=timezone.utc)})
    assert rimossa["status"] == "RIMOSSO" and rimossa["removed_at"].startswith("2026-09-14")


# ── visita Drive ─────────────────────────────────────────────────────────────

def test_percorri_drive_visita_tutto_con_paginazione_e_non_indicizza_le_cartelle():
    righe = modulo.percorri_drive(DriveFinto(ALBERO), "ROOT")
    per_id = {r["drive_id"]: r for r in righe}
    assert set(per_id) == {"F0", "F1", "F2", "F3"}
    assert per_id["F0"]["percorso"] == "INDICE.xlsx" and per_id["F0"]["area"] is None
    assert per_id["F2"]["percorso"] == "05_PERSONALE_E_CEDOLINI/CEDOLINI PAGA/ROSSI MARIO/2024/cedolino_03.pdf"
    assert per_id["F3"]["area"] == "90_ARCHIVIO_STORICO"


# ── giro completo ─────────────────────────────────────────────────────────────

def _configura(monkeypatch, conn):
    monkeypatch.setattr(settings, "GOOGLE_DRIVE_GESTIONALE_ROOT_FOLDER_ID", "ROOT")
    monkeypatch.setattr(settings, "PROTOCOLLO_DRIVE_ENABLED", True)
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://finto:finto@localhost/gc")

    async def connetti(dsn):
        return conn

    monkeypatch.setattr(postgres_diretto, "connetti", connetti)


def test_sincronizza_conta_nuovi_aggiornati_rimossi_e_registra_il_giro(monkeypatch):
    conn = ConnFinta(esistenti={"F1"})
    _configura(monkeypatch, conn)
    esito = _run(modulo.sincronizza(service=DriveFinto(ALBERO), conn=conn))
    assert esito["esito"] == "ok"
    assert esito["file_visti"] == 4
    assert esito["nuovi"] == 3 and esito["aggiornati"] == 1
    assert esito["rimossi"] == 1            # dall'UPDATE ... stato='rimosso'
    assert esito["duplicati_marcati"] == 2
    assert esito["collegati"] == 1
    assert esito["giro_id"] == 7
    # ordine: apertura giro, upsert, rimossi, duplicati, impronte, collegamento, chiusura giro
    testi = " || ".join(conn.sql)
    assert testi.index("insert into gestionale.protocollo_drive_giri") < testi.index("insert into gestionale.protocollo_drive (")
    assert testi.index("stato = 'rimosso'") < testi.index("duplicato_di = case")
    assert testi.index("duplicato_di = case") < testi.index("set collegamento_tipo")
    assert "esito='ok'" in testi
    assert not conn.chiusa  # connessione passata dal chiamante: non la chiude lui


def test_sincronizza_senza_radice_non_tocca_il_database(monkeypatch):
    conn = ConnFinta()
    _configura(monkeypatch, conn)
    monkeypatch.setattr(settings, "GOOGLE_DRIVE_GESTIONALE_ROOT_FOLDER_ID", None)
    esito = _run(modulo.sincronizza(service=DriveFinto(ALBERO), conn=conn))
    assert esito["esito"] == "non_configurato"
    assert conn.sql == []


def test_sincronizza_disattivato(monkeypatch):
    conn = ConnFinta()
    _configura(monkeypatch, conn)
    monkeypatch.setattr(settings, "PROTOCOLLO_DRIVE_ENABLED", False)
    assert _run(modulo.sincronizza(service=DriveFinto(ALBERO), conn=conn))["esito"] == "disattivato"
    assert conn.sql == []


def test_errore_durante_il_giro_viene_registrato_e_rilanciato(monkeypatch):
    class DriveRotto:
        def files(self):
            raise RuntimeError("Drive non raggiungibile")

    conn = ConnFinta()
    _configura(monkeypatch, conn)
    with pytest.raises(RuntimeError):
        _run(modulo.sincronizza(service=DriveRotto(), conn=conn))
    assert any("esito='errore'" in s for s in conn.sql)


# ── letture ───────────────────────────────────────────────────────────────────

def test_cerca_costruisce_il_filtro_e_restituisce_la_forma_pubblica(monkeypatch):
    conn = ConnFinta()
    _configura(monkeypatch, conn)
    esito = _run(modulo.cerca(q="Marzo", area="05_PERSONALE_E_CEDOLINI", anno=2025, limit=50))
    assert esito["returned"] == 1 and esito["total_indexed"] == 3
    riga = esito["results"][0]
    assert riga["document_id"] == "F1" and riga["status"] == "ATTIVO" and riga["linked_type"] == "hr_cedolino"
    sql_ricerca = next(s for s in conn.sql if s.startswith("select * from gestionale.protocollo_drive"))
    assert "stato = 'attivo'" in sql_ricerca and "nome ilike" in sql_ricerca and "area = $" in sql_ricerca and "anno = $" in sql_ricerca
    assert conn.chiusa


def test_cerca_con_rimossi_e_solo_duplicati(monkeypatch):
    conn = ConnFinta()
    _configura(monkeypatch, conn)
    _run(modulo.cerca(includi_rimossi=True, solo_duplicati=True))
    sql_ricerca = next(s for s in conn.sql if s.startswith("select * from gestionale.protocollo_drive"))
    assert "stato = 'attivo'" not in sql_ricerca and "duplicato_di is not null" in sql_ricerca


def test_quarantena_sposta_solo_le_copie_duplicate(monkeypatch):
    class ConnQuarantena(ConnFinta):
        async def fetch(self, sql, *args):
            self.sql.append(sql)
            return [
                {"drive_id": "F3", "parent_id": "A90", "percorso": "90/x.pdf", "duplicato_di": "F1"},
                {"drive_id": "F1", "parent_id": "P1", "percorso": "05/x.pdf", "duplicato_di": None},
            ]

    conn = ConnQuarantena()
    _configura(monkeypatch, conn)
    monkeypatch.setattr(settings, "GOOGLE_DRIVE_QUARANTENA_FOLDER_ID", "QUAR")
    drive = DriveFinto(ALBERO)
    esito = _run(modulo.sposta_in_quarantena(["F3", "F1"], service=drive))
    assert esito["spostati"] == ["F3"]
    assert esito["rifiutati"][0]["drive_id"] == "F1"
    assert drive.files().aggiornati[0]["addParents"] == "QUAR" and drive.files().aggiornati[0]["removeParents"] == "A90"


def test_quarantena_senza_cartella_configurata(monkeypatch):
    conn = ConnFinta()
    _configura(monkeypatch, conn)
    monkeypatch.setattr(settings, "GOOGLE_DRIVE_QUARANTENA_FOLDER_ID", None)
    with pytest.raises(RuntimeError):
        _run(modulo.sposta_in_quarantena(["F3"], service=DriveFinto(ALBERO)))
