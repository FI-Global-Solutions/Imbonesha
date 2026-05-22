#!/usr/bin/env python3
"""Update ImageScene.cog_path from MinIO paths to Supabase Storage public URLs.

Usage:
    SUPABASE_URL=https://xxxx.supabase.co \
    SUPABASE_BUCKET=imbonesha-imagery \
    DATABASE_URL=postgis://... \
    python scripts/update_imagery_urls.py

Run this after uploading all imagery to Supabase Storage.
"""

import os
import sys

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))

django.setup()

from imagery.models import ImageScene  # noqa: E402

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
BUCKET = os.environ.get("SUPABASE_BUCKET", "imbonesha-imagery")

base = f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}"

updated = 0
for scene in ImageScene.objects.all():
    old = scene.cog_path
    if old.startswith("levir-demo/"):
        scene.cog_path = f"{base}/{old}"
        scene.save(update_fields=["cog_path"])
        print(f"  {old} → {scene.cog_path}")
        updated += 1

print(f"\nUpdated {updated} ImageScene rows.")
