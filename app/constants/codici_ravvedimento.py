"""
Codici tributo di sanzioni/interessi da ravvedimento — costante condivisa.

Prima ogni modulo (tributi_engine, quietanze_import, f24_riconciliazione,
parser_f24, codici_tributo_db, fiscale_sentinella, f24_gestione_avanzata)
definiva la propria lista, con insiemi divergenti → classificazioni incoerenti
tra parsing, matching e analisi. Questa è la fonte unica.

Composizione:
- Sanzioni ravvedimento: famiglie 89xx verificate e usate dai parser
- Interessi ravvedimento (erario): 1989-1994
- Interessi ravvedimento IMU/TASI/tributi locali: 1507-1512
"""

CODICI_RAVVEDIMENTO = frozenset({
    # Sanzioni
    "8901", "8902", "8903", "8904", "8906", "8907", "8911",
    "8913", "8918", "8926", "8929",
    # Sanzioni da ravvedimento su ritenute e addizionali trattenute dai
    # sostituti (Ris. AdE 18/E del 28/04/2023): 8947-8949 erario, 8950-8951
    # regioni, 8952-8953 enti locali. Gli interessi si cumulano al tributo.
    "8947", "8948", "8949", "8950", "8951", "8952", "8953",
    # Interessi erario
    "1989", "1990", "1991", "1992", "1993", "1994",
    # Interessi IMU/TASI/tributi locali
    "1507", "1508", "1509", "1510", "1511", "1512",
})

# Codici specifici del sostituto: non basta una sanzione qualsiasi nella
# delega (es. 8904 IVA) per qualificare come ravveduta una ritenuta.
SANZIONI_RITENUTE_PER_CODICE = {
    "1001": frozenset({"8947", "8906"}), "1002": frozenset({"8947", "8906"}),
    "1012": frozenset({"8947", "8906"}), "1701": frozenset({"8947", "8906"}),
    "1040": frozenset({"8948", "8906"}), "3802": frozenset({"8950", "8902"}),
    "3847": frozenset({"8952", "8926"}), "3848": frozenset({"8952", "8926"}),
}
