from app.services.email_drive_archive import route_for_document_type
from app.services.email_monitor_service import _risolvi_tipo_documento_email
from app.services.mittenti import BUILTIN_MITTENTI


def test_enel_e_studio_marotta_sono_mittenti_builtin_canonici():
    per_email = {m["pattern"]: m for m in BUILTIN_MITTENTI}
    assert per_email["noreply.enelenergia@enel.com"]["tipo_documento"] == "bolletta_energia"
    assert per_email["rosaria.marotta@email.it"]["tipo_documento"] == "f24"


def test_bolletta_enel_viene_instradata_senza_essere_forzata_a_fattura():
    tipo = _risolvi_tipo_documento_email(
        {"filename": "bolletta.pdf"},
        {"tipo_documento": "bolletta_energia"},
    )
    assert tipo == "bolletta_energia"
    assert route_for_document_type(tipo) == ("utenze_energia", "Bollette energia")
