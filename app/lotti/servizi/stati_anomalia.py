"""Stati canonici delle anomalie HACCP, condivisi da registro e gestione."""

STATI_APERTI = ("Aperta", "In corso")
STATI_CONCLUSI = ("Risolta", "Chiusa")
STATI_ANOMALIA = (*STATI_APERTI, *STATI_CONCLUSI)


async def conta_anomalie_aperte(collection):
    """Conta soltanto le anomalie su cui resta un'azione da completare."""
    return await collection.count_documents({"stato": {"$in": list(STATI_APERTI)}})
