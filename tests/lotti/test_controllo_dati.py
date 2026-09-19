from app.lotti.routers.controllo_dati import (
    _all_link_fields_missing,
    _build_issue,
    _calcola_score,
    _issue_status,
    _missing_or_empty,
)


def test_missing_or_empty_builds_legacy_safe_query():
    query = _missing_or_empty("prodotti.prodotto_master_id")

    assert "$or" in query
    assert {"prodotti.prodotto_master_id": {"$exists": False}} in query["$or"]
    assert {"prodotti.prodotto_master_id": ""} in query["$or"]
    assert {"prodotti.prodotto_master_id": []} in query["$or"]


def test_all_link_fields_missing_uses_nested_prefix():
    conditions = _all_link_fields_missing("ingredienti")
    rendered = str(conditions)

    assert "ingredienti.prodotto_master_id" in rendered
    assert "ingredienti.prodotto_id" in rendered
    assert "ingredienti.nome_canonico" in rendered


def test_issue_status_depends_on_count_and_severity():
    assert _issue_status(0, "critica") == "ok"
    assert _issue_status(3, "critica") == "critico"
    assert _issue_status(3, "media") == "attenzione"


def test_build_issue_exposes_actionable_shape():
    issue = _build_issue(
        issue_id="righe_fattura_senza_link",
        title="Righe fattura senza link prodotto",
        description="Righe prive di id prodotto.",
        count=2,
        severity="critica",
        owner="Fatture",
        action="Mappare le righe.",
        route="#fatture",
        samples=[{"numero_fattura": "1"}],
    )

    assert issue["stato"] == "critico"
    assert issue["conteggio"] == 2
    assert issue["area"] == "Fatture"
    assert issue["campioni"] == [{"numero_fattura": "1"}]


def test_score_penalizes_only_open_issues():
    issues = [
        {"conteggio": 0, "severita": "critica"},
        {"conteggio": 5, "severita": "critica"},
        {"conteggio": 1, "severita": "media"},
    ]

    assert _calcola_score(issues) == 74
