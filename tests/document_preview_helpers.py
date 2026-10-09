import hashlib

from app.services.document_import_preview import create_confirmation_token


def confirmed_preview_headers(content: bytes, document_type: str) -> dict[str, str]:
    digest = hashlib.sha256(content).hexdigest()
    return {
        "X-Document-Preview-Token": create_confirmation_token(digest, document_type)
    }
