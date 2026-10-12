"""LIPE trimestrale, distinta dalle scadenze dei versamenti IVA mensili.

Art. 21-bis DL 78/2010, Q2 al 30/09 (DL 73/2022), Q4 entro fine febbraio.
Calendario nazionale condiviso; la richiesta documentale inizia DOPO il termine.
"""
from calendar import monthrange
from datetime import date, timedelta
from app.services.calendario_lavorativo import e_festivo

FONTE = 'https://www1.agenziaentrate.gov.it/servizi/scadenzario/main.php'


def scadenza_lipe(anno, trimestre):
    if trimestre not in (1, 2, 3, 4):
        raise ValueError('Trimestre LIPE non valido')
    nominale = {1: date(anno, 5, 31), 2: date(anno, 9, 30),
                3: date(anno, 11, 30),
                4: date(anno+1, 2, monthrange(anno+1, 2)[1])}[trimestre]
    effettiva = nominale
    while e_festivo(effettiva):
        effettiva += timedelta(days=1)
    return nominale, effettiva


def attesa_lipe(anno, mese, oggi, *, presente=False):
    trimestre = (mese-1)//3+1
    nominale, effettiva = scadenza_lipe(anno, trimestre)
    dopo_termine = oggi > effettiva
    stato = 'presente' if presente else ('scaricabile' if dopo_termine else 'in_attesa_scadenza')
    return {'anno': anno, 'trimestre': trimestre,
            'scadenza_nominale': nominale.isoformat(), 'scadenza': effettiva.isoformat(),
            'dal': (effettiva+timedelta(days=1)).isoformat(),
            'stato': stato, 'puoi_scaricare': dopo_termine and not presente,
            'confronto_abilitato': dopo_termine and presente,
            'fonte_url': FONTE,
            'messaggio': ('LIPE disponibile' if presente else
                          'Ora puoi scaricare la LIPE e controllare la coerenza' if dopo_termine else
                          'LIPE trimestrale: attesa fino alla scadenza di presentazione'),
            'alternativa_quadro_vp': trimestre == 4}
