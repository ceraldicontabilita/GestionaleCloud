"""
Validazione upload: verifica il CONTENUTO reale del file (magic bytes),
non solo l'estensione del filename — un filename è scelto dal client e
non garantisce nulla sul contenuto effettivo.

Deliberatamente permissivo: se il tipo non è tra quelli noti sotto, o il
contenuto è ambiguo, NON blocca (evita falsi positivi su upload legittimi
con encoding/varianti non previste). Copre solo il caso più a rischio:
un file rinominato con estensione sbagliata che finisce comunque dentro
un parser (PyMuPDF/pdfplumber/pdfminer per i PDF).
"""
from fastapi import HTTPException

# Firme (magic bytes) dei formati usati nell'app.
_PDF_MAGIC = b"%PDF-"


def verifica_pdf_reale(content: bytes, filename: str = "") -> None:
    """Solleva HTTPException 400 se il contenuto non è un PDF reale.

    Da chiamare SUBITO dopo aver letto i bytes del file, prima di scriverlo
    su disco o passarlo a un parser PDF (PyMuPDF/pdfplumber/pdfminer).
    """
    if not content:
        raise HTTPException(status_code=400, detail=f"File vuoto: {filename or 'upload'}")
    if not content.lstrip()[:8].startswith(_PDF_MAGIC):
        raise HTTPException(
            status_code=400,
            detail=f"Il file '{filename or 'upload'}' ha estensione .pdf ma il contenuto non è un PDF valido",
        )
