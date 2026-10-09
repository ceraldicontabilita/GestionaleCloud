"""«Non ancora collegato» si scrive con `non_collegato`, non con `$in: [None, ""]`.

Nel motore dei filtri `$in` con None **non** prende il campo assente: 83 query
del gestionale sono scritte su questa semantica (fra cui il giro email, che
con un `$in` allargato elaborava documenti non suoi, e una `delete_many` di
Prima Nota Cassa). Chi vuole anche le righe senza il campo usa `non_collegato`:
senza, nessuna ricevuta PagoPA trovava il suo movimento mai collegato."""
from app.services.archivio_documenti_memoria import matches_filter, prepara_filtro
from app.services.pagopa_receipts import non_collegato


def test_non_collegato_comprende_il_campo_assente():
    filtro = non_collegato("collegato")
    assert matches_filter({"id": 1}, filtro)
    assert matches_filter({"id": 1, "collegato": None}, filtro)
    assert matches_filter({"id": 1, "collegato": ""}, filtro)
    assert not matches_filter({"id": 1, "collegato": "R-1"}, filtro)
    assert matches_filter({"id": 1}, prepara_filtro(filtro))


def test_in_con_none_resta_sul_campo_presente():
    # Semantica su cui poggiano le query esistenti: non allargarla.
    assert not matches_filter({"id": 1}, {"fonte": {"$in": ["gmail_monitor", None]}})
    assert matches_filter({"id": 1, "fonte": None}, {"fonte": {"$in": ["gmail_monitor", None]}})
    assert not matches_filter({"id": 1}, {"stato": {"$in": ["aperto", "parziale"]}})
