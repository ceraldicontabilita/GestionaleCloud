"""Da ogni sezione si passa alle altre, e l'elenco sta scritto una volta sola.

Le quattro app girano nello stesso servizio ma erano collegate a senso unico:
il gestionale aveva i link verso Menu, HR e Lotti; Lotti tornava al gestionale
e basta; **dal personale e dal menu non si usciva affatto**. Per passare da una
sezione all'altra bisognava riscrivere l'indirizzo a mano — dal di dentro
sembra un muro, ed e' un'assenza.

L'elenco delle sezioni ora e' uno solo, nel backend. Ogni interfaccia lo legge
e lo disegna con i propri stili: il dato e' condiviso, l'aspetto no.
"""
import pathlib

import pytest

from app.routers.sezioni import SEZIONI

RADICE = pathlib.Path(__file__).resolve().parents[2]


def test_ci_sono_tutte_e_quattro():
    assert {s["id"] for s in SEZIONI} == {"gestionale", "lotti", "hr", "menu"}


@pytest.mark.parametrize("sezione", SEZIONI, ids=lambda s: s["id"])
def test_ogni_sezione_ha_nome_percorso_e_icona(sezione):
    assert sezione["nome"] and sezione["descrizione"]
    assert sezione["percorso"].startswith("/")
    # Icona Lucide, mai un'emoji: su Android le emoji rendono con i colori di
    # sistema, che non si possono controllare.
    assert sezione["icona"].isalpha() and sezione["icona"][0].isupper()


@pytest.mark.parametrize("sezione", [s for s in SEZIONI if s["id"] != "gestionale"],
                         ids=lambda s: s["id"])
def test_i_percorsi_montati_finiscono_con_la_barra(sezione):
    """`Mount` di Starlette esige la barra finale.

    Il prefisso nudo cade nella SPA del gestionale: chi apre `/lotti` si
    ritrova nel contabile, che e' esattamente il salto che questo elenco
    deve evitare.
    """
    assert sezione["percorso"].endswith("/"), (
        f"{sezione['id']}: «{sezione['percorso']}» senza barra finale porta nel gestionale."
    )


def test_l_elenco_e_pubblico():
    """Le tre sezioni fuori dall'ERP firmano i token con altri segreti.

    Se l'elenco fosse protetto, da Lotti o dal portale la chiamata tornerebbe
    401 e il collegamento sparirebbe proprio dove serve. Non espone nulla:
    solo nomi e percorsi, gli stessi che si leggono nella barra degli indirizzi.
    """
    from app.middleware.authentication import PUBLIC_PATHS

    assert "/api/sezioni" in PUBLIC_PATHS
    assert "/api/sezioni/" in PUBLIC_PATHS


SELETTORI = [
    "frontend_hr/src/SelettoreSezioni.jsx",
    "frontend_lotti/src/components/shared/SelettoreSezioni.jsx",
    "frontend_menu/src/components/shared/SelettoreSezioni.jsx",
]


@pytest.mark.parametrize("percorso", SELETTORI)
def test_nessuna_interfaccia_si_riscrive_l_elenco(percorso):
    """I percorsi si leggono da `/api/sezioni`, non si cablano.

    Una copia per interfaccia andrebbe fuori sincrono al primo cambio di
    prefisso, e il collegamento porterebbe a un 404 senza che nessuno se ne
    accorga.
    """
    sorgente = (RADICE / percorso).read_text(encoding="utf-8")

    assert "/api/sezioni" in sorgente, f"{percorso}: non legge l'elenco condiviso"
    for sezione in SEZIONI:
        if sezione["id"] == "gestionale":
            continue
        assert f'"{sezione["percorso"]}"' not in sorgente, (
            f"{percorso}: il percorso «{sezione['percorso']}» e' scritto a mano."
        )


@pytest.mark.parametrize("percorso", SELETTORI)
def test_ogni_selettore_toglie_la_sezione_in_cui_si_trova(percorso):
    """Un collegamento alla pagina su cui sei gia' e' solo rumore."""
    sorgente = (RADICE / percorso).read_text(encoding="utf-8")

    assert "sezioneCorrente" in sorgente
    assert "filter" in sorgente


@pytest.mark.parametrize("percorso", SELETTORI)
def test_il_tocco_arriva_a_44px(percorso):
    """Si usa dal tablet, con le mani sporche."""
    sorgente = (RADICE / percorso).read_text(encoding="utf-8")

    assert "44" in sorgente, f"{percorso}: manca l'altezza minima del tocco"


AGGANCI = [
    ("frontend_hr/src/App.jsx", 'sezioneCorrente="hr"'),
    ("frontend_lotti/src/layouts/AppLayout.jsx", 'sezioneCorrente="lotti"'),
    ("frontend_menu/src/pages/AdminDashboard.jsx", 'sezioneCorrente="menu"'),
]


@pytest.mark.parametrize("percorso,atteso", AGGANCI, ids=[a[0].split("/")[0] for a in AGGANCI])
def test_il_selettore_e_davvero_agganciato(percorso, atteso):
    """Un componente che nessuno monta non collega niente."""
    sorgente = (RADICE / percorso).read_text(encoding="utf-8")

    assert "SelettoreSezioni" in sorgente and atteso in sorgente
