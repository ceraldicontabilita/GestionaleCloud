"""La lettura AI non perde un blocco intero per una risposta imperfetta.

Il 30/09/2026 il primo giro reale ha letto 600 descrizioni su 3.000: 60 blocchi
su 75 tornavano con 200 ma senza letture, e nessun errore veniva registrato.
"""
import asyncio

from app.lotti.servizi import lettura_articoli_ai as ai

COMPLETA = (
    '[{"i":1,"nome":"Nutella 220 g","marca":"Ferrero","prodotto":"nutella","misura":220,"unita":"g"},'
    '{"i":2,"nome":"Tovaglioli","marca":"Fato","prodotto":"tovaglioli","misura":null,"unita":null}]'
)


def test_array_completo():
    assert [d["i"] for d in ai._estrai_array(COMPLETA)] == [1, 2]


def test_risposta_troncata_tiene_gli_oggetti_completi():
    tagliata = COMPLETA[:-40]  # il secondo oggetto e' a meta'
    assert [d["i"] for d in ai._estrai_array(tagliata)] == [1]


def test_frase_e_recinti_attorno_all_array():
    testo = "Ecco le letture [ordinate]:\n```json\n" + COMPLETA + "\n```\nFatto."
    assert [d["i"] for d in ai._estrai_array(testo)] == [1, 2]


def test_senza_array_niente():
    assert ai._estrai_array("Non posso aiutare.") == []
    assert ai._estrai_array("") == []


class _Client:
    """Un ``LlmChat`` finto: torna il testo scelto con lo ``stop_reason`` scelto."""

    def __init__(self, testo, stop="end_turn"):
        self.testo, self.stop = testo, stop

    async def crea_messaggio(self, messages, **kw):
        return {"content": [{"type": "text", "text": self.testo}], "stop_reason": self.stop,
                "testo": self.testo, "fonti_web": [], "usage": {"input_tokens": 1, "output_tokens": 1},
                "modello": "finto", "tentativi": 1}


def test_la_diagnosi_dice_perche_una_risposta_e_vuota(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "chiave-di-prova")
    diagnosi = {}
    out = asyncio.run(ai.leggi_con_ai(["NUTELLA GR.220 FERRERO"], client=_Client("Non posso.", "max_tokens"),
                                      diagnosi=diagnosi))
    assert out == {}
    assert diagnosi["stop_reason"] == "max_tokens" and diagnosi["inizio_risposta"] == "Non posso."


def test_una_risposta_tagliata_salva_le_letture_complete(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "chiave-di-prova")
    out = asyncio.run(ai.leggi_con_ai(["NUTELLA GR.220 FERRERO", "TOVAGL. FATO"],
                                      client=_Client(COMPLETA[:-40], "max_tokens")))
    assert list(out) == ["NUTELLA GR.220 FERRERO"]
    assert out["NUTELLA GR.220 FERRERO"]["misura"] == "220"


def test_i_blocchi_sono_piu_piccoli_del_limite_di_token():
    assert ai.PER_CHIAMATA <= 25 and ai.MAX_TOKEN >= 8000
