"""Normalizzazione delle immagini destinate alle interfacce web."""

from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError


MAX_WEB_EDGE = 1600
WEBP_QUALITY = 82


def ottimizza_immagine_web(contenuto: bytes) -> bytes:
    """Ridimensiona e converte in WebP, senza metadati non necessari."""
    try:
        with Image.open(BytesIO(contenuto)) as originale:
            immagine = ImageOps.exif_transpose(originale)
            immagine.thumbnail((MAX_WEB_EDGE, MAX_WEB_EDGE), Image.Resampling.LANCZOS)
            ha_alpha = "A" in immagine.getbands()
            immagine = immagine.convert("RGBA" if ha_alpha else "RGB")
            uscita = BytesIO()
            immagine.save(
                uscita,
                format="WEBP",
                quality=WEBP_QUALITY,
                method=4,
                exact=ha_alpha,
            )
            return uscita.getvalue()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError("Immagine non valida o non supportata") from exc
