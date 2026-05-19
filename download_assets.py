"""
DRG Dashboard — Téléchargeur et organisateur d'assets wiki
===========================================================
Utilise l'API MediaWiki de deeprockgalactic.wiki.gg pour télécharger
toutes les icônes utiles au dashboard, puis les renomme proprement.

Utilisation :
    python download_assets.py

Structure créée :
    assets/
    └── icons/
        ├── classes/
        │   ├── scout.png
        │   ├── driller.png
        │   ├── gunner.png
        │   └── engineer.png
        ├── perks/
        │   ├── born_ready.png
        │   └── ...
        ├── weapons/
        │   ├── deepcore_gk2.png
        │   └── ...
        ├── resources/
        │   ├── bismor.png
        │   ├── croppa.png
        │   └── ...
        ├── missions/
        │   └── ...
        └── manifest.json   ← index de tous les fichiers (utile pour React)
"""

import os
import re
import time
import json
import urllib.request
import urllib.parse
from pathlib import Path

# ── Configuration ─────────────────────────────────────────────────────────────

API_BASE = "https://deeprockgalactic.wiki.gg/api.php"

# Catégories wiki → sous-dossier de destination
CATEGORIES = {
    "Class_icons":         "classes",
    "Perk_icons":          "perks",
    "Equipment_icons":     "weapons",
    "Resource_icons":      "resources",
    "Mission_type_icons":  "missions",
    "Miscellaneous_icons": "misc",
}

OUTPUT_DIR = Path(__file__).parent / "assets" / "icons"

# Pause entre chaque téléchargement (politesse envers le serveur wiki)
DELAY_SECONDS = 0.4

# ── Nettoyage des noms de fichiers ────────────────────────────────────────────
#
# Le wiki nomme ses fichiers comme : "File:Icon_Perk_BornReady.png"
# On veut :                                     "born_ready.png"
#
# Analogie : c'est un traducteur entre le langage du wiki (verbeux, préfixé)
# et le langage du frontend (court, prévisible, snake_case).

PREFIXES_TO_STRIP = [
    "Icon_Perk_",
    "Icon_Resource_",
    "Icon_Mission_",
    "Icon_Armor_",
    "Icon_Damage_",
    "Icon_Accessory_",
    "Icon_Equipment_",
    "Icon_Weapon_",
    "Icon_Class_",
    "Icon_",
]

SUFFIXES_TO_STRIP = ["_icon", "_Icon"]


def clean_filename(wiki_title: str) -> str:
    """
    Convertit un titre wiki en nom de fichier propre en snake_case.

    Exemples :
        "File:Scout_icon.png"           → "scout.png"
        "File:Icon_Perk_BornReady.png"  → "born_ready.png"
        "File:Bismor.png"               → "bismor.png"
        "File:Mining_Expedition.png"    → "mining_expedition.png"
    """
    # 1. Enlever le préfixe "File:"
    name = wiki_title.removeprefix("File:")

    # 2. Séparer l'extension
    stem, ext = os.path.splitext(name)
    ext = ext.lower()  # .PNG → .png

    # 3. Supprimer les préfixes wiki connus
    for prefix in PREFIXES_TO_STRIP:
        if stem.startswith(prefix):
            stem = stem[len(prefix):]
            break

    # 4. Supprimer les suffixes wiki connus
    for suffix in SUFFIXES_TO_STRIP:
        if stem.lower().endswith(suffix.lower()):
            stem = stem[: -len(suffix)]
            break

    # 5. Convertir CamelCase → snake_case  ("BornReady" → "Born_Ready")
    stem = re.sub(r"([a-z])([A-Z])", r"\1_\2", stem)

    # 6. Tout en minuscules, espaces et tirets → underscores
    stem = stem.lower().replace(" ", "_").replace("-", "_")

    # 7. Nettoyer les underscores multiples et les bords
    stem = re.sub(r"_+", "_", stem).strip("_")

    return stem + ext


# ── Appels API MediaWiki ──────────────────────────────────────────────────────

def api_get(params: dict) -> dict:
    """Appelle l'API MediaWiki et retourne le JSON parsé."""
    params["format"] = "json"
    url = API_BASE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "DRG-Dashboard-Downloader/1.0 (fan project, non-commercial)"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def get_files_in_category(category_name: str) -> list:
    """Retourne tous les fichiers d'une catégorie, avec pagination automatique."""
    files = []
    params = {
        "action": "query",
        "list": "categorymembers",
        "cmtitle": f"Category:{category_name}",
        "cmtype": "file",
        "cmlimit": "500",
    }
    while True:
        data = api_get(params)
        members = data.get("query", {}).get("categorymembers", [])
        files.extend(members)
        if "continue" not in data:
            break
        params["cmcontinue"] = data["continue"]["cmcontinue"]
    return files


def get_image_urls_batch(file_titles: list) -> dict:
    """
    Résout les URLs directes de plusieurs fichiers en lots de 50 (limite API).
    Retourne { "File:Scout_icon.png": "https://static.wiki.gg/..." }

    Analogie : plutôt que d'aller chercher chaque livre un par un à la
    bibliothèque, on envoie une liste de 50 titres d'un coup. Bien plus rapide.
    """
    result = {}
    batch_size = 50
    for i in range(0, len(file_titles), batch_size):
        batch = file_titles[i: i + batch_size]
        try:
            data = api_get({
                "action": "query",
                "titles": "|".join(batch),
                "prop": "imageinfo",
                "iiprop": "url",
            })
            for page in data.get("query", {}).get("pages", {}).values():
                title = page.get("title", "")
                imageinfo = page.get("imageinfo", [])
                if imageinfo and imageinfo[0].get("url"):
                    result[title] = imageinfo[0]["url"]
        except Exception as e:
            print(f"  ⚠️  Erreur batch URLs : {e}")
    return result


def download_file(url: str, dest_path: Path) -> bool:
    """Télécharge un fichier depuis une URL vers dest_path."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "DRG-Dashboard-Downloader/1.0 (fan project, non-commercial)"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            dest_path.write_bytes(resp.read())
        return True
    except Exception as e:
        print(f"    ⚠️  Erreur : {e}")
        return False


# ── Programme principal ───────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("DRG Dashboard — Téléchargeur d'assets wiki")
    print("=" * 60)
    print(f"Destination : {OUTPUT_DIR}\n")

    total_downloaded = 0
    total_skipped = 0
    total_errors = 0
    manifest = {}

    for category, subfolder in CATEGORIES.items():
        print(f"\n📁  {category}  →  assets/icons/{subfolder}/")
        dest_dir = OUTPUT_DIR / subfolder

        # 1. Lister les fichiers de la catégorie
        try:
            files = get_files_in_category(category)
        except Exception as e:
            print(f"  ❌ Impossible de lister : {e}")
            continue

        if not files:
            print("  (catégorie vide)")
            continue

        print(f"  {len(files)} fichier(s) — résolution des URLs...")

        # 2. Résoudre toutes les URLs en une fois
        titles = [f["title"] for f in files]
        try:
            url_map = get_image_urls_batch(titles)
        except Exception as e:
            print(f"  ❌ Impossible de résoudre les URLs : {e}")
            continue

        manifest[subfolder] = []

        # 3. Télécharger chaque fichier avec son nom nettoyé
        for file_info in files:
            wiki_title = file_info["title"]          # "File:Scout_icon.png"
            clean_name = clean_filename(wiki_title)  # "scout.png"
            dest_path  = dest_dir / clean_name

            # Enregistrer dans le manifest (même si déjà présent)
            manifest[subfolder].append({
                "wiki_name":  wiki_title.removeprefix("File:"),
                "clean_name": clean_name,
                "path":       f"assets/icons/{subfolder}/{clean_name}",
            })

            # Sauter si déjà téléchargé
            if dest_path.exists():
                print(f"  ✓  {clean_name}")
                total_skipped += 1
                continue

            url = url_map.get(wiki_title)
            if not url:
                print(f"  ❌ URL introuvable : {wiki_title}")
                total_errors += 1
                continue

            print(f"  ⬇️   {clean_name}  ←  {wiki_title.removeprefix('File:')}")
            success = download_file(url, dest_path)
            if success:
                total_downloaded += 1
            else:
                total_errors += 1

            time.sleep(DELAY_SECONDS)

    # 4. Sauvegarder le manifest JSON
    #    Ce fichier permet au frontend React de savoir exactement
    #    quelles icônes sont disponibles et comment les nommer.
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = OUTPUT_DIR / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    # 5. Résumé final
    print("\n" + "=" * 60)
    print("✅  Terminé !")
    print(f"   ⬇️   Téléchargés   : {total_downloaded}")
    print(f"   ✓   Déjà présents : {total_skipped}")
    print(f"   ❌  Erreurs       : {total_errors}")
    print(f"\n   📄  Manifest : {manifest_path}")
    print("\nStructure créée :")
    for subfolder in CATEGORIES.values():
        folder = OUTPUT_DIR / subfolder
        if folder.exists():
            count = len(list(folder.glob("*.*")))
            print(f"   assets/icons/{subfolder}/  ({count} fichiers)")
    print("=" * 60)


if __name__ == "__main__":
    main()
