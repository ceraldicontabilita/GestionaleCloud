"""Posta: scarico automatico con cursore per cartella.

- il primo giro parte dai piu' recenti e, giro dopo giro, arriva al primo
  messaggio della casella (storico completo);
- dopo, a ogni giro si leggono solo i messaggi nuovi;
- un messaggio senza allegati non si scarica per intero;
- la cartella si apre in sola lettura e si legge con BODY.PEEK: niente «letto»;
- un login rifiutato apre un alert e manda un Telegram, una volta sola.
"""
import asyncio

import pytest

from app.database import Database
from app.services import email_full_download as efd
from app.services.archivio_documenti_memoria import ClientArchivioMemoria


class FintaCasella:
    def __init__(self, cartelle):
        # cartelle: {nome: {uid: ha_allegato}}
        self.cartelle = cartelle
        self.aperta = None
        self.fetch_completi = []
        self.sola_lettura = []

    def list(self):
        return "OK", [f'(\\HasNoChildren) "/" "{n}"'.encode() for n in self.cartelle]

    def select(self, nome, readonly=False):
        self.aperta = nome.strip('"')
        self.sola_lettura.append(readonly)
        return "OK", [b"1"]

    def response(self, codice):
        return codice, [b"777"]

    def uid(self, comando, *args):
        messaggi = self.cartelle[self.aperta]
        if comando == "SEARCH":
            criterio = args[-1]
            if criterio == "ALL":
                uid = sorted(messaggi)
            else:
                da, a = criterio.split()[1].split(":")
                massimo = max(messaggi) if messaggi else 0
                a = massimo if a == "*" else int(a)
                uid = [u for u in sorted(messaggi) if int(da) <= u <= a]
                if args[-1].endswith(":*") and not uid and messaggi:
                    uid = [massimo]  # come IMAP: n:* torna sempre l'ultimo
            return "OK", [" ".join(str(u) for u in uid).encode()]
        uid, parti = int(args[0]), args[1]
        if parti in ("(BODYSTRUCTURE)", "(BODYSTRUCTURE BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)])"):
            corpo = b'("APPLICATION" "PDF" ("NAME" "f24.pdf"))' if messaggi[uid] else b'("TEXT" "PLAIN")'
            return "OK", [corpo]
        self.fetch_completi.append((self.aperta, uid, parti))
        return "OK", [(b"1 (BODY[] {10}", b"Subject: prova\r\n\r\nciao")]

    def logout(self):
        return "BYE", []


@pytest.fixture()
def db(monkeypatch):
    database = ClientArchivioMemoria()["test_posta_cursori"]
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: database))
    return database


def _collega(monkeypatch, casella, elaborati):
    def connect(self):
        self.connection = casella
        return True

    async def process_email(self, uid, msg, source_folder="INBOX"):
        elaborati.append((source_folder, int(uid)))
        return 1

    monkeypatch.setattr(efd.EmailFullDownloader, "connect", connect)
    monkeypatch.setattr(efd.EmailFullDownloader, "process_email", process_email)


def test_storico_a_giri_poi_solo_i_nuovi(db, monkeypatch):
    casella = FintaCasella({
        "INBOX": {1: True, 2: False, 3: True, 4: True},
        "Archivio F24": {10: True, 11: True},
    })
    elaborati = []
    _collega(monkeypatch, casella, elaborati)

    async def scenario():
        primo = await efd.scarica_posta_con_cursori(db, max_scaricati=2)
        secondo = await efd.scarica_posta_con_cursori(db, max_scaricati=100)
        casella.cartelle["INBOX"][5] = True  # arriva una mail nuova
        terzo = await efd.scarica_posta_con_cursori(db, max_scaricati=100)
        return primo, secondo, terzo

    primo, secondo, terzo = asyncio.run(scenario())
    # Primo giro: i due piu' recenti di INBOX, poi il tetto.
    assert elaborati[:2] == [("INBOX", 4), ("INBOX", 3)]
    assert primo["interrotto_per_tetto"] and not primo["storico_completo"]
    # Secondo giro: riprende lo storico, salta il messaggio senza allegati.
    assert ("INBOX", 2) not in elaborati
    assert set(elaborati) >= {("INBOX", 1), ("Archivio F24", 11), ("Archivio F24", 10)}
    assert secondo["storico_completo"]
    # Terzo giro: solo il nuovo, nessun messaggio riletto.
    assert elaborati[-1] == ("INBOX", 5) and terzo["pdf_salvati"] == 1
    assert len(elaborati) == len(set(elaborati))
    # Mai «letto»: cartella in sola lettura e BODY.PEEK.
    assert all(casella.sola_lettura)
    assert all(parti == "(BODY.PEEK[])" for _, _, parti in casella.fetch_completi)


def test_login_rifiutato_apre_alert_e_telegram_una_volta(db, monkeypatch):
    from app.services import telegram_notifications

    def connect(self):
        self.stats["errors"].append("Connessione: AUTHENTICATIONFAILED Invalid credentials")
        return False

    messaggi = []

    async def finto_invio(testo, **_):
        messaggi.append(testo)
        return {"success": True}

    monkeypatch.setattr(efd.EmailFullDownloader, "connect", connect)
    monkeypatch.setattr(telegram_notifications, "send_notification", finto_invio)

    async def scenario():
        await efd.scarica_posta_con_cursori(db)
        esito = await efd.scarica_posta_con_cursori(db)
        alerts = await db["alerts"].find({"codice": "POSTA_NON_RAGGIUNGIBILE"}, {"_id": 0}).to_list(5)
        stato = await db["sistema_stato"].find_one({"chiave": efd.CHIAVE_CURSORI_POSTA}, {"_id": 0})
        return esito, alerts, stato

    esito, alerts, stato = asyncio.run(scenario())
    assert esito["success"] is False and "AUTHENTICATIONFAILED" in esito["error"]
    assert len(alerts) == 1 and alerts[0]["stato"] == "aperto"
    assert len(messaggi) == 1
    assert "AUTHENTICATIONFAILED" in stato["ultimo_giro"]["errore"]


def test_credenziali_dalla_risoluzione_canonica(monkeypatch):
    from app.config import settings

    for nome in ("EMAIL_USER", "GMAIL_EMAIL", "EMAIL_ADDRESS", "EMAIL_PASSWORD",
                 "EMAIL_APP_PASSWORD", "GMAIL_APP_PASSWORD"):
        monkeypatch.setattr(settings, nome, None, raising=False)
    monkeypatch.setattr(settings, "IMAP_USER", "casella@example.com", raising=False)
    monkeypatch.setattr(settings, "IMAP_PASSWORD", "segreto-di-prova", raising=False)
    assert efd.get_email_credentials() == ("casella@example.com", "segreto-di-prova")


def test_password_per_app_incollata_con_gli_spazi(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "IMAP_USER", " casella@example.com ", raising=False)
    monkeypatch.setattr(settings, "IMAP_PASSWORD", "abcd efgh ijkl mnop\n", raising=False)
    assert efd.get_email_credentials() == ("casella@example.com", "abcdefghijklmnop")


def test_login_prova_la_password_per_app_anche_se_imap_password_e_vecchia(monkeypatch):
    """La nuova password per app sta in GMAIL_APP_PASSWORD, IMAP_PASSWORD e'
    la vecchia: il login le prova entrambe ed entra con quella giusta."""
    from app.config import settings
    from app.services import gmail_credentials

    for nome in ("EMAIL_USER", "EMAIL_ADDRESS", "GMAIL_EMAIL", "GMAIL_ACCOUNT_AMMINISTRATIVO",
                 "ADMIN_EMAIL", "EMAIL_APP_PASSWORD", "EMAIL_PASSWORD",
                 "GMAIL_APP_PASSWORD_AMMINISTRATIVO"):
        monkeypatch.setattr(settings, nome, None, raising=False)
    monkeypatch.setattr(settings, "IMAP_USER", "casella@example.com", raising=False)
    monkeypatch.setattr(settings, "IMAP_PASSWORD", "vecchiavecchiavv", raising=False)
    monkeypatch.setattr(settings, "GMAIL_APP_PASSWORD", "nuov anuo vanu ovan", raising=False)
    monkeypatch.setattr(gmail_credentials, "_coppia_riuscita", None)

    tentativi = []

    class FintoIMAP:
        def __init__(self, host, timeout=20):
            pass

        def login(self, utente, password):
            tentativi.append(password)
            if password != "nuovanuovanuovan":
                raise efd.imaplib.IMAP4.error("[AUTHENTICATIONFAILED] Invalid credentials")

    monkeypatch.setattr(efd.imaplib, "IMAP4_SSL", FintoIMAP)
    downloader = efd.EmailFullDownloader(db=None)
    assert downloader.connect() is True
    assert "nuovanuovanuovan" in tentativi
    # Al giro dopo la coppia buona si prova per prima.
    tentativi.clear()
    assert efd.EmailFullDownloader(db=None).connect() is True
    assert tentativi == ["nuovanuovanuovan"]


def test_mail_commercialista_senza_allegati_non_viene_saltata(db, monkeypatch):
    class CasellaCommercialista(FintaCasella):
        def uid(self, comando, *args):
            if comando=='FETCH' and 'BODYSTRUCTURE' in args[1]:
                return 'OK', [(b'1 BODYSTRUCTURE ("TEXT" "PLAIN")', b'From: studio@example.com\r\nSubject: IVA luglio 2026\r\n')]
            return super().uid(comando,*args)
    casella=CasellaCommercialista({'INBOX':{1:False}})
    elaborati=[]
    _collega(monkeypatch,casella,elaborati)
    async def scenario():
        await db['mittenti_email'].insert_one({'pattern':'studio@example.com','attivo':True,'tipo_documento':'f24'})
        return await efd.scarica_posta_con_cursori(db,max_scaricati=10)
    result=asyncio.run(scenario())
    assert elaborati==[('INBOX',1)] and result['scaricati']==1
    assert all(casella.sola_lettura)


def test_storico_non_scarica_corpi_non_attendibili_ma_legge_buste_pec(db, monkeypatch):
    class Casella(FintaCasella):
        def uid(self, command, *args):
            if command == 'FETCH' and 'BODYSTRUCTURE' in args[1]:
                uid=int(args[0])
                structure=b'("APPLICATION" "PDF" ("NAME" "file.pdf"))'
                if uid==2: structure=b'("MESSAGE" "RFC822" ("NAME" "postacert.eml"))'
                return 'OK',[(structure,b'From: esterno@example.com\r\nSubject: documento\r\n')]
            return super().uid(command,*args)
    casella=Casella({'INBOX':{1:True,2:True}});elaborati=[]
    _collega(monkeypatch,casella,elaborati)
    async def run():
        await db['mittenti_email'].insert_one({'pattern':'attendibile@example.com','attivo':True,'tipo_documento':'verbale'})
        return await efd.scarica_posta_con_cursori(db,data_inizio='2003-01-01',solo_storico=True,max_scaricati=10)
    result=asyncio.run(run())
    assert elaborati==[('INBOX',2)]
    assert result['controllati']==2 and result['storico_completo'] is True
