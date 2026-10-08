"""
Motori centralizzati del gestionale.

Un "motore" e' il punto unico di verita' per una decisione o un processo
che prima veniva reimplementato in piu' punti del monolite (spesso con
piccole differenze non intenzionali). Ogni nuova feature che tocca una
decisione gia' coperta da un motore deve richiamarlo, non duplicarlo.
"""
