-- Bucket Storage "menu-images" (pubblico in lettura): le scritture dal backend
-- Menu e dal ponte Lotti->Menu (app/lotti/servizi/menu_bridge.py) usano la
-- chiave MENU_SUPABASE_KEY (ruolo anon, usata solo lato server, mai inviata
-- al browser), la stessa con cui le tabelle menu_* hanno gia' la policy
-- "menu app full access". Senza una policy su storage.objects ogni upload
-- falliva con "new row violates row-level security policy" (produzione,
-- 14/09/2026 15:03, 5 ricette non pubblicate). Stessa regola, limitata al
-- solo bucket del Menu.
drop policy if exists "menu app full access" on storage.objects;
create policy "menu app full access" on storage.objects
    for all to anon
    using (bucket_id = 'menu-images')
    with check (bucket_id = 'menu-images');
