"""Verifica senza scritture delle fonti pubblicate da Menu e Lotti."""

from app.lotti.servizi.menu_bridge import (
    allergeni_da_pubblicare,
    mappa_allergeni,
    prezzo_per_menu,
)
from app.menu.routes.menu_routes import prezzo_centesimi


def verifica_catalogo(prodotti, ricette, codici_allergeni):
    by_id = {str(r.get("id") or r.get("_id")): r for r in ricette}
    anomalie = []
    for p in prodotti:
        problemi = []
        ref = str(p.get("lotti_ref") or "")
        actual = set(p.get("allergens") or [])
        if actual - set(codici_allergeni):
            problemi.append("Allergeni non riconosciuti")
        if prezzo_centesimi(p.get("price")) is None:
            problemi.append("Prezzo da definire")
        if ref.startswith("ricetta:"):
            r = by_id.get(ref[8:])
            if r is None:
                problemi.append("Ricetta collegata non trovata")
            else:
                expected = set(mappa_allergeni(allergeni_da_pubblicare(r)))
                if expected != actual:
                    problemi.append("Allergeni diversi dalla ricetta")
                expected_price, _ = prezzo_per_menu(r)
                if prezzo_centesimi(expected_price) != prezzo_centesimi(p.get("price")):
                    problemi.append("Prezzo diverso dalla ricetta")
                if isinstance(r.get("menu_pubblico"), bool) and r["menu_pubblico"] != (
                    p.get("visible") is not False
                ):
                    problemi.append("Visibilita diversa dalla ricetta")
        elif p.get("origine") == "lotti":
            problemi.append("Ricetta non collegata")
        if problemi:
            anomalie.append(
                {
                    "id": p["id"],
                    "nome": p.get("name_it") or p.get("name"),
                    "visibile": p.get("visible") is not False,
                    "lotti_ref": ref or None,
                    "problemi": problemi,
                }
            )
    return {
        "totale_prodotti": len(prodotti),
        "prodotti_da_verificare": len(anomalie),
        "pubblicati_da_verificare": sum(p["visibile"] for p in anomalie),
        "prodotti": anomalie,
    }
