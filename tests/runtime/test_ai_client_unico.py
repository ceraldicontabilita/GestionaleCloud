"""Un solo client Anthropic: ``anthropic_llm_client.LlmChat``.

Nessun altro modulo importa l'SDK, chiama ``api.anthropic.com`` o cabla uno
snapshot datato del modello; il registro delle chiamate e il tetto
giornaliero stanno nel client. Nessuna rete: l'SDK e' finto."""
import asyncio
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import anthropic_llm_client as llm
from app.services.anthropic_llm_client import LlmChat, TettoRaggiunto, UserMessage
from app.services.archivio_documenti_memoria import ArchivioDocumenti

RADICE = Path(__file__).resolve().parents[2]
CLIENT = RADICE / "app" / "services" / "anthropic_llm_client.py"


def _sorgenti():
    for f in (RADICE / "app").rglob("*.py"):
        if f != CLIENT and "__pycache__" not in f.parts:
            yield f, f.read_text("utf-8")


def test_nessun_altro_modulo_parla_con_anthropic():
    vietati = re.compile(r"import anthropic|from anthropic import|AsyncAnthropic\(|api\.anthropic\.com|"
                         r"anthropic-version|x-api-key")
    colpevoli = [str(f.relative_to(RADICE)) for f, testo in _sorgenti() if vietati.search(testo)]
    assert colpevoli == [], colpevoli


def test_nessuno_snapshot_datato_ne_modello_cablato():
    datato = re.compile(r"claude-[a-z]+-\d(?:-\d)?-\d{8}|claude-sonnet-4\.5")
    colpevoli = [str(f.relative_to(RADICE)) for f, testo in _sorgenti() if datato.search(testo)]
    assert colpevoli == [], colpevoli
    # un modello si legge dal client (configurabile), non si scrive nel modulo
    cablati = [str(f.relative_to(RADICE)) for f, testo in _sorgenti()
               if re.search(r'["\']claude-(?:haiku|sonnet|opus)-\d', testo)]
    assert cablati == [], cablati


def test_modelli_configurabili(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_MODEL_VELOCE", raising=False)
    assert llm.modello_veloce() == llm.DEFAULT_FAST_MODEL
    monkeypatch.setenv("ANTHROPIC_MODEL_VELOCE", "claude-haiku-prova")
    assert llm.modello_veloce() == "claude-haiku-prova"
    assert LlmChat("k").model == llm.document_model_name()


class _Blocco:
    """Un blocco dell'SDK: ha ``model_dump`` come i modelli pydantic."""

    def __init__(self, **campi):
        self.campi = campi

    def model_dump(self, exclude_none=False):
        return {k: v for k, v in self.campi.items() if not (exclude_none and v is None)}


def _sdk_finto(*blocchi, stop="end_turn"):
    chiamate = []

    def crea(**kwargs):
        chiamate.append(kwargs)
        return SimpleNamespace(content=list(blocchi), stop_reason=stop, model="modello-servito",
                               usage=SimpleNamespace(input_tokens=12, output_tokens=5))

    return SimpleNamespace(messages=SimpleNamespace(create=crea)), chiamate


def test_crea_messaggio_torna_blocchi_dizionario_testo_e_fonti(monkeypatch):
    sdk, chiamate = _sdk_finto(
        _Blocco(type="web_search_tool_result", content=[_Blocco(type="web_search_result", url="https://a.it/p")]),
        _Blocco(type="text", text="Ecco ", citations=None),
        _Blocco(type="tool_use", id="tu_1", name="cerca", input={"q": "x"}),
    )
    monkeypatch.setattr(LlmChat, "_cliente", lambda self: sdk)
    chat = LlmChat("k", system_prompt="sistema", model="m", max_tokens=99)
    esito = asyncio.run(chat.crea_messaggio([{"role": "user", "content": "ciao"}],
                                            tools=[{"name": "cerca"}], temperature=0.3))
    assert esito["testo"] == "Ecco " and esito["fonti_web"] == ["https://a.it/p"]
    assert esito["content"][1] == {"type": "text", "text": "Ecco "}          # senza `citations: null`
    assert esito["content"][2]["name"] == "cerca" and esito["usage"] == {"input_tokens": 12, "output_tokens": 5}
    assert esito["modello"] == "modello-servito" and esito["stop_reason"] == "end_turn"
    (kw,) = chiamate
    assert kw["model"] == "m" and kw["system"] == "sistema" and kw["tools"] == [{"name": "cerca"}]
    assert kw["temperature"] == 0.3 and kw["max_tokens"] == 99


def test_cerca_sul_web_usa_lo_strumento_server_side(monkeypatch):
    sdk, chiamate = _sdk_finto(_Blocco(type="text", text="{}"))
    monkeypatch.setattr(LlmChat, "_cliente", lambda self: sdk)
    esito = asyncio.run(LlmChat("k").cerca_sul_web("che prodotto e'?", max_uses=2))
    assert esito == {"testo": "{}", "fonti": []}
    assert chiamate[0]["tools"] == [{"type": llm.WEB_SEARCH_TOOL, "name": "web_search", "max_uses": 2}]


def test_ogni_chiamata_vera_va_nel_registro_con_lo_scopo(monkeypatch):
    db = ArchivioDocumenti()
    sdk, _ = _sdk_finto(_Blocco(type="text", text="ok"))
    monkeypatch.setattr(LlmChat, "_cliente", lambda self: sdk)
    chat = LlmChat("k", model="m", scopo="prova", db=db)
    assert asyncio.run(chat.send_message(UserMessage(content="ciao"))) == "ok"
    righe = asyncio.run(db[llm.COLL_CHIAMATE].find({}, {"_id": 0}).to_list(None))
    assert len(righe) == 1
    riga = righe[0]
    assert riga["scopo"] == "prova" and riga["esito"] == "ok" and riga["giorno"] == llm.oggi_roma()
    assert riga["input_tokens"] == 12 and riga["output_tokens"] == 5 and riga["modello"] == "modello-servito"
    assert asyncio.run(llm.chiamate_oggi(db, scopo="prova")) == 1 and asyncio.run(llm.chiamate_oggi(db, scopo="altro")) == 0


def test_un_errore_di_contenuto_finisce_nel_registro_e_si_rilancia(monkeypatch):
    db = ArchivioDocumenti()

    def esplode(**_kw):
        raise ValueError("richiesta rifiutata")

    monkeypatch.setattr(LlmChat, "_cliente",
                        lambda self: SimpleNamespace(messages=SimpleNamespace(create=esplode)))
    with pytest.raises(ValueError):
        asyncio.run(LlmChat("k", scopo="prova", db=db).send_message(UserMessage(content="x")))
    (riga,) = asyncio.run(db[llm.COLL_CHIAMATE].find({}, {"_id": 0}).to_list(None))
    assert riga["esito"] == "errore" and "ValueError" in riga["errore"] and riga["tentativi"] == 1


def test_il_tetto_giornaliero_ferma_la_chiamata_prima_di_partire(monkeypatch):
    db = ArchivioDocumenti()
    monkeypatch.setenv("AI_TETTO_GIORNALIERO", "1")
    sdk, chiamate = _sdk_finto(_Blocco(type="text", text="ok"))
    monkeypatch.setattr(LlmChat, "_cliente", lambda self: sdk)
    chat = LlmChat("k", scopo="a", db=db)
    asyncio.run(chat.send_message(UserMessage(content="1")))
    with pytest.raises(TettoRaggiunto):
        asyncio.run(LlmChat("k", scopo="b", db=db).send_message(UserMessage(content="2")))
    assert len(chiamate) == 1                        # la seconda non e' partita
    monkeypatch.setenv("AI_TETTO_GIORNALIERO", "0")  # 0 = nessun tetto
    asyncio.run(LlmChat("k", scopo="b", db=db).send_message(UserMessage(content="3")))
    assert len(chiamate) == 2


def test_registra_false_lascia_il_registro_al_chiamante(monkeypatch):
    db = ArchivioDocumenti()
    sdk, _ = _sdk_finto(_Blocco(type="text", text="ok"))
    monkeypatch.setattr(LlmChat, "_cliente", lambda self: sdk)
    asyncio.run(LlmChat("k", scopo="agenti", db=db, registra=False).send_message(UserMessage(content="x")))
    assert asyncio.run(db[llm.COLL_CHIAMATE].count_documents({})) == 0
    asyncio.run(llm.registra_chiamata(db, scopo="agenti", esito="ok", sha256="abc"))
    (riga,) = asyncio.run(db[llm.COLL_CHIAMATE].find({}, {"_id": 0}).to_list(None))
    assert riga["sha256"] == "abc" and riga["scopo"] == "agenti"
