"""Scaricare i byte di un file Drive: una funzione sola, per tutti.

Stava dentro `drive_invoice_ingest` come helper privato, ma non ha niente di
specifico delle fatture: la usa anche chi legge le LIPE archiviate. Una
seconda copia sarebbe l'ennesimo doppione.
"""
import io

__all__ = ["scarica_bytes"]


def scarica_bytes(service, file_id: str) -> bytes:
    """Il contenuto del file Drive, per intero."""
    from googleapiclient.http import MediaIoBaseDownload

    buffer = io.BytesIO()
    richiesta = service.files().get_media(fileId=file_id, supportsAllDrives=True)
    downloader = MediaIoBaseDownload(buffer, richiesta)
    finito = False
    while not finito:
        _, finito = downloader.next_chunk()
    return buffer.getvalue()
