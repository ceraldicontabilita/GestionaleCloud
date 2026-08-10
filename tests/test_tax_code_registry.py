from app.services.tax_code_registry import parse_tax_codes


def test_parse_tax_codes_from_official_table_shape():
    payload = """
    <table>
      <tr><th>Descrizione</th><th>Codice Tributo</th><th>Modalita</th></tr>
      <tr><td>IRPEF saldo</td><td>4001</td><td>F24</td></tr>
      <tr><td>Ritenute su redditi di lavoro autonomo</td><td>1040</td><td>F24</td></tr>
      <tr><td>Interessi ravvedimento</td><td>1989</td><td>F24</td></tr>
    </table>
    """
    result = parse_tax_codes(payload)
    assert [item["code"] for item in result] == ["1040", "1989", "4001"]
    assert result[0]["description"] == "Ritenute su redditi di lavoro autonomo"


def test_parser_deduplicates_same_code():
    payload = "<table><tr><td>Prima descrizione valida</td><td>4001</td></tr>" \
              "<tr><td>Descrizione aggiornata valida</td><td>4001</td></tr></table>"
    assert parse_tax_codes(payload) == [{"code": "4001", "description": "Descrizione aggiornata valida"}]
