"""
One-off script: scarica le immagini attualmente ospitate su servizi esterni
(Qromo, sito ceraldicaffe.it) e le ricarica nel bucket Supabase Storage
"menu-images", aggiornando i riferimenti nelle tabelle menu_categories,
menu_subcategories, menu_products.

Va eseguito una sola volta (localmente, con le credenziali giuste in .env).
"""
import hashlib
import mimetypes
import sys
from pathlib import Path


import httpx
from app.menu.supabase_client import supabase

TABLES = ["menu_categories", "menu_subcategories", "menu_products"]
BUCKET = "menu-images"


def fetch_external_urls():
    urls = set()
    for t in TABLES:
        res = supabase.table(t).select("image").execute()
        for row in res.data:
            img = row.get("image")
            if img and img.startswith("http") and "/storage/v1/object/public/menu-images/" not in img:
                urls.add(img)
    return sorted(urls)


def storage_path_for(url: str) -> str:
    ext = Path(url.split("?")[0]).suffix or ".jpg"
    h = hashlib.sha1(url.encode()).hexdigest()[:16]
    return f"migrated/{h}{ext}"


def download(url: str) -> tuple[bytes, str]:
    with httpx.Client(follow_redirects=True, timeout=30) as client:
        r = client.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; MenuImageMigration/1.0)"})
        r.raise_for_status()
        content_type = r.headers.get("content-type", "").split(";")[0].strip()
        if not content_type or content_type == "application/octet-stream":
            guessed, _ = mimetypes.guess_type(url)
            content_type = guessed or "image/jpeg"
        return r.content, content_type


def main():
    urls = fetch_external_urls()
    print(f"Trovate {len(urls)} immagini esterne da migrare.")
    mapping = {}
    failures = []

    for i, url in enumerate(urls, 1):
        path = storage_path_for(url)
        print(f"[{i}/{len(urls)}] {url}")
        try:
            content, content_type = download(url)
            supabase.storage.from_(BUCKET).upload(
                path, content,
                {"content-type": content_type, "upsert": "true"}
            )
            new_url = supabase.storage.from_(BUCKET).get_public_url(path)
            mapping[url] = new_url
            print(f"    -> {new_url} ({len(content)} bytes)")
        except Exception as e:
            print(f"    ERRORE: {e}")
            failures.append((url, str(e)))

    print(f"\nMigrate {len(mapping)}/{len(urls)} immagini. Aggiorno i riferimenti nel database...")

    total_updated = 0
    for t in TABLES:
        for old_url, new_url in mapping.items():
            res = supabase.table(t).update({"image": new_url}).eq("image", old_url).execute()
            total_updated += len(res.data)

    print(f"Righe aggiornate: {total_updated}")

    if failures:
        print(f"\n{len(failures)} immagini NON migrate (riferimento originale lasciato invariato):")
        for url, err in failures:
            print(f"  - {url}: {err}")

    return mapping, failures


if __name__ == "__main__":
    main()
