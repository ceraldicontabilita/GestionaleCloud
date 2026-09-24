"""L'admin del Menu lavora sul database, non su dati finti.

`ProductManager` leggeva `mockData.js` e il suo «Salva» scriveva solo nella
console del browser, con la nota «aggiorna manualmente mockData.js»: nessuna
modifica arrivava al menu. Il filtro allergeni pubblico e il suggerimento
immagini usavano la stessa copia finta.
"""
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "frontend_menu" / "src"


def test_nessun_dato_finto_nel_menu():
    assert not (SRC / "mockData.js").exists()
    assert not (SRC / "mockDataComplete.js").exists()
    for f in SRC.rglob("*.js*"):
        testo = f.read_text(encoding="utf-8")
        assert "from '../mockData'" not in testo and "from '../../mockData'" not in testo, f


def test_gestione_prodotti_salva_sulle_api_vere():
    testo = (SRC / "components" / "admin" / "ProductManager.jsx").read_text(encoding="utf-8")
    assert "/api/menu/admin/products/all" in testo
    assert "axios.put(" in testo and "/api/menu/admin/products/${id}" in testo
    assert "console.log('Product to save'" not in testo
