"""Guardie meccaniche permanenti (audit-codice 04/09/2026, metodo Ceraldi).

L'audit ha trovato 6 bug reali con pyflakes che nessun test del repo
intercettava (`scripts/audit_static.py` cerca solo pattern noti, non
`undefined name`/chiavi dict duplicate): due `except`/handler che chiamavano
`logger.x(...)` senza che `logger` fosse mai definito nel modulo (crash con
`NameError` proprio quando dovevano solo loggare un errore, mascherando la
causa reale), due dict letterali con la chiave `"$ne"` ripetuta due volte
(Python tiene solo l'ultimo valore: il primo filtro Mongo va perso in
silenzio), un `uuid4()` non importato nello scope e una chiamata a una
funzione (`sync_buste_paga`) mai definita nel file.

Le prime due classi (logger indefinito, chiave dict duplicata) sono bug
generici che possono ripresentarsi in qualsiasi file nuovo: qui restano
guardie permanenti su tutto `app/`. Le altre due erano specifiche del punto
in cui sono state trovate: restano test di non-regressione mirati.
"""
import ast
import os
import re

ROOT = os.path.join(os.path.dirname(__file__), "..")
APP_DIR = os.path.join(ROOT, "app")

# Cartelle con codice generato/di terze parti o script una-tantum: fuori
# perimetro per questa guardia (stesso criterio delle altre guardie del
# repo, es. test_drive_only_architecture.py).
ESCLUSE = ("__pycache__", "scripts")


def _file_python(root_dir):
    for cartella, dirs, files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d not in ESCLUSE]
        for nome in files:
            if nome.endswith(".py"):
                yield os.path.join(cartella, nome)


def test_nessuna_chiave_dict_letterale_duplicata_nel_backend():
    """Un dict letterale con la stessa chiave due volte perde il primo valore.

    Caso reale trovato: {"acconto_id": {"$exists": True, "$ne": None,
    "$ne": ""}} diventava silenziosamente {"$exists": True, "$ne": ""} — il
    controllo "$ne": None spariva e la query Mongo filtrava meno di quanto
    il codice sembrava dire.
    """
    problemi = []
    for path in _file_python(APP_DIR):
        with open(path, encoding="utf-8") as f:
            sorgente = f.read()
        try:
            albero = ast.parse(sorgente, filename=path)
        except SyntaxError:
            continue
        for nodo in ast.walk(albero):
            if not isinstance(nodo, ast.Dict):
                continue
            viste = {}
            for chiave in nodo.keys:
                if not isinstance(chiave, ast.Constant) or not isinstance(chiave.value, str):
                    continue
                if chiave.value in viste:
                    problemi.append(
                        f"{path}:{chiave.lineno}: chiave {chiave.value!r} ripetuta "
                        f"nello stesso dict letterale (righe {viste[chiave.value]} e {chiave.lineno})"
                    )
                viste[chiave.value] = chiave.lineno
    assert not problemi, (
        "Dict letterali con chiave duplicata (il primo valore va perso in "
        "silenzio):\n" + "\n".join(problemi)
    )


# File con un uso legittimo di "logger" fuori da un semplice binding di modulo
# (es. iniettato da un decoratore, o import indiretto verificato a mano):
# nessuno oggi. Tenere questa lista vuota è il segnale che la guardia
# funziona; un'eccezione va giustificata in un commento qui, non aggiunta
# in silenzio.
ECCEZIONI_LOGGER = set()

_LOGGER_USATO_RE = re.compile(r"(?<![.\w])logger\s*\.")

# Le istruzioni import possono essere su una riga o su piu' righe con le
# parentesi (`from .x import (\n    a,\n    logger,\n)`): un semplice
# "import ... logger" sulla stessa riga non basta, serve guardare l'intera
# istruzione.
_IMPORT_STATEMENT_RE = re.compile(
    r"(?:from\s+\S+\s+)?import\s*\((?:[^()])*?\)"   # forma con parentesi
    r"|(?:from\s+\S+\s+)?import\s+[^\n]+",           # forma su una riga
    re.DOTALL,
)
_LOGGER_DEFINITO_ALTROVE_RE = re.compile(
    r"(?:^|\n)\s*logger\s*=|"          # logger = logging.getLogger(...)
    r"\slogger\s*:.*=|"                # logger: Logger = ...
    r"self\.logger\b|"                  # attributo di classe
    r"def\s+\w+\([^)]*\blogger\b"      # parametro di funzione chiamato logger
)


def _logger_definito(sorgente: str) -> bool:
    if _LOGGER_DEFINITO_ALTROVE_RE.search(sorgente):
        return True
    for istruzione in _IMPORT_STATEMENT_RE.findall(sorgente):
        if re.search(r"\blogger\b", istruzione):
            return True
    return False


def test_nessun_modulo_chiama_logger_senza_definirlo():
    """`logger.warning(...)` in un except che deve solo registrare l'errore
    non deve MAI diventare un secondo errore (NameError) che nasconde il
    primo. Casi reali trovati: app/hr/routers/dimissioni.py e
    app/routers/fornitori_learning.py chiamavano `logger.x(...)` senza che
    `logger` fosse mai definito nel file.
    """
    problemi = []
    for path in _file_python(APP_DIR):
        rel = os.path.relpath(path, ROOT)
        if rel in ECCEZIONI_LOGGER:
            continue
        with open(path, encoding="utf-8") as f:
            sorgente = f.read()
        if not _LOGGER_USATO_RE.search(sorgente):
            continue
        if _logger_definito(sorgente):
            continue
        problemi.append(rel)
    assert not problemi, (
        "Moduli che chiamano logger.<metodo>(...) senza definire/importare "
        "mai 'logger' (NameError a runtime, di solito dentro un except che "
        "doveva solo loggare):\n" + "\n".join(problemi)
    )


def test_documenti_usa_uuid_del_modulo_non_uuid4_indefinito():
    """Non-regressione: app/routers/documenti.py importa `uuid` a livello di
    modulo (riga 18) ma un punto usava `uuid4()` nudo, mai importato in
    quello scope (NameError quando l'endpoint /processa-f24-scaricati
    trovava un F24 valido da importare)."""
    path = os.path.join(APP_DIR, "routers", "documenti.py")
    with open(path, encoding="utf-8") as f:
        sorgente = f.read()
    # uuid4() bare, non preceduto da "uuid." e non importato localmente
    # nella stessa funzione (import locale già presente altrove nel file).
    righe = sorgente.splitlines()
    for numero, riga in enumerate(righe, start=1):
        if re.search(r"(?<!uuid\.)(?<!import )\buuid4\(\)", riga):
            # è consentito solo se preceduto, nelle 5 righe precedenti,
            # da un `from uuid import uuid4` locale (pattern esistente
            # altrove nel file per un'altra funzione).
            contesto = "\n".join(righe[max(0, numero - 6):numero])
            assert "from uuid import uuid4" in contesto, (
                f"documenti.py:{numero}: uuid4() nudo senza import locale "
                "ne' uso di uuid.uuid4() del modulo"
            )


def test_processa_tutti_documenti_non_chiama_funzione_indefinita():
    """Non-regressione: sync_buste_paga() non è mai stata definita in
    documenti.py; l'endpoint /processa-tutti la chiamava comunque (il
    NameError finiva silenziosamente in risultati["buste_paga"]["error"],
    quindi il passo "buste paga" non ha MAI funzionato). I cedolini hanno
    un solo sistema di ingestione canonico (vedi CLAUDE.md); questo
    endpoint non deve reintrodurre una chiamata inventata."""
    path = os.path.join(APP_DIR, "routers", "documenti.py")
    with open(path, encoding="utf-8") as f:
        sorgente = f.read()
    assert "await sync_buste_paga(" not in sorgente


def test_tfr_e_associazioni_usano_nin_non_ne_duplicato():
    """Non-regressione sui due casi reali di `$ne` duplicato (bonifica
    04/09/2026): la forma corretta è `$nin: [None, ""]`."""
    for rel in (
        os.path.join("app", "hr", "routers", "tfr.py"),
        os.path.join("app", "routers", "bonifici_module", "associazioni.py"),
    ):
        path = os.path.join(ROOT, rel)
        with open(path, encoding="utf-8") as f:
            sorgente = f.read()
        assert '"$ne": None, "$ne": ""' not in sorgente, rel
        assert "$nin" in sorgente, rel
