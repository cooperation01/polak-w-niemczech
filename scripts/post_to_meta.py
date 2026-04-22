"""
post_to_meta.py
Postet den neuesten Blog-Artikel automatisch auf Facebook, Instagram und Threads.
Liest Artikel-Metadaten aus last_post.json (wird von generate_post.py erstellt).

Benötigte Umgebungsvariablen (GitHub Secrets):
  META_SYSTEM_USER_TOKEN   — Meta System-User-Token (läuft nie ab)
  FACEBOOK_PAGE_ID         — Numerische ID der Facebook Business Page
  INSTAGRAM_USER_ID        — Instagram Business Account ID
  THREADS_USER_ID          — Threads User ID
  THREADS_ACCESS_TOKEN     — Separater Threads API Token (optional, sonst META_SYSTEM_USER_TOKEN)
  META_DEFAULT_IMAGE_URL   — Fallback-Bild für Instagram (optional)
"""

import json
import os
import sys
from pathlib import Path

import requests

# ── Konfiguration ──────────────────────────────────────────────────────────────
LAST_POST = Path(__file__).parent.parent / "last_post.json"

META_TOKEN         = os.environ.get("META_SYSTEM_USER_TOKEN", "")
FACEBOOK_PAGE_ID   = os.environ.get("FACEBOOK_PAGE_ID", "")
INSTAGRAM_USER_ID  = os.environ.get("INSTAGRAM_USER_ID", "")
THREADS_USER_ID    = os.environ.get("THREADS_USER_ID", "")
THREADS_TOKEN      = os.environ.get("THREADS_ACCESS_TOKEN", META_TOKEN)

GRAPH_URL   = "https://graph.facebook.com/v19.0"
THREADS_URL = "https://graph.threads.net/v1.0"


def load_last_post() -> dict:
    if not LAST_POST.exists():
        print("[SKIP] last_post.json nicht gefunden – kein neuer Artikel heute.")
        sys.exit(0)
    return json.loads(LAST_POST.read_text(encoding="utf-8"))


def post_facebook(post: dict) -> bool:
    if not FACEBOOK_PAGE_ID or not META_TOKEN:
        print("[SKIP] Facebook: PAGE_ID oder TOKEN fehlt.")
        return False

    message = f"{post['title']}\n\n{post['description']}\n\n🔗 {post['url']}"
    resp = requests.post(
        f"{GRAPH_URL}/{FACEBOOK_PAGE_ID}/feed",
        data={
            "message":      message,
            "link":         post["url"],
            "access_token": META_TOKEN,
        },
        timeout=30,
    )
    if resp.ok:
        post_id = resp.json().get("id", "?")
        print(f"[OK] Facebook Post erstellt: {post_id}")
        return True
    else:
        print(f"[FEHLER] Facebook: {resp.status_code} – {resp.text}", file=sys.stderr)
        return False


def post_instagram(post: dict) -> bool:
    if not INSTAGRAM_USER_ID or not META_TOKEN:
        print("[SKIP] Instagram: USER_ID oder TOKEN fehlt.")
        return False

    image_url = post.get("image_url", "")
    if not image_url:
        print("[SKIP] Instagram: Kein Bild vorhanden – Post übersprungen.")
        return False

    caption = (
        f"{post['title']}\n\n"
        f"{post['description']}\n\n"
        f"🔗 Link in Bio\n\n"
        f"#PolakwNiemczech #Versicherung #Finanzen #PolacywNiemczech"
    )

    # Schritt 1: Media-Container erstellen
    resp1 = requests.post(
        f"{GRAPH_URL}/{INSTAGRAM_USER_ID}/media",
        data={
            "image_url":    image_url,
            "caption":      caption,
            "access_token": META_TOKEN,
        },
        timeout=30,
    )
    if not resp1.ok:
        print(f"[FEHLER] Instagram Container: {resp1.status_code} – {resp1.text}", file=sys.stderr)
        return False

    container_id = resp1.json().get("id")
    if not container_id:
        print("[FEHLER] Instagram: Keine Container-ID erhalten.", file=sys.stderr)
        return False

    # Schritt 2: Container publizieren
    resp2 = requests.post(
        f"{GRAPH_URL}/{INSTAGRAM_USER_ID}/media_publish",
        data={
            "creation_id":  container_id,
            "access_token": META_TOKEN,
        },
        timeout=30,
    )
    if resp2.ok:
        media_id = resp2.json().get("id", "?")
        print(f"[OK] Instagram Post publiziert: {media_id}")
        return True
    else:
        print(f"[FEHLER] Instagram Publish: {resp2.status_code} – {resp2.text}", file=sys.stderr)
        return False


def post_threads(post: dict) -> bool:
    if not THREADS_USER_ID or not THREADS_TOKEN:
        print("[SKIP] Threads: USER_ID oder TOKEN fehlt.")
        return False

    text = (
        f"{post['title']}\n\n"
        f"{post['description']}\n\n"
        f"🔗 {post['url']}"
    )

    # Schritt 1: Threads-Container erstellen
    resp1 = requests.post(
        f"{THREADS_URL}/{THREADS_USER_ID}/threads",
        params={
            "media_type":   "TEXT",
            "text":         text,
            "access_token": THREADS_TOKEN,
        },
        timeout=30,
    )
    if not resp1.ok:
        print(f"[FEHLER] Threads Container: {resp1.status_code} – {resp1.text}", file=sys.stderr)
        return False

    creation_id = resp1.json().get("id")
    if not creation_id:
        print("[FEHLER] Threads: Keine Creation-ID erhalten.", file=sys.stderr)
        return False

    # Schritt 2: Publizieren
    resp2 = requests.post(
        f"{THREADS_URL}/{THREADS_USER_ID}/threads_publish",
        params={
            "creation_id":  creation_id,
            "access_token": THREADS_TOKEN,
        },
        timeout=30,
    )
    if resp2.ok:
        thread_id = resp2.json().get("id", "?")
        print(f"[OK] Threads Post publiziert: {thread_id}")
        return True
    else:
        print(f"[FEHLER] Threads Publish: {resp2.status_code} – {resp2.text}", file=sys.stderr)
        return False


def main():
    post = load_last_post()
    print(f"[INFO] Poste: {post['title']}")
    print(f"[INFO] URL:   {post['url']}")

    results = {
        "facebook":  post_facebook(post),
        "instagram": post_instagram(post),
        "threads":   post_threads(post),
    }

    errors = [p for p, ok in results.items() if ok is False]
    if errors:
        print(f"[WARNUNG] Fehler bei: {', '.join(errors)}", file=sys.stderr)
        sys.exit(1)

    print("[FERTIG] Alle Plattformen bespielt.")


if __name__ == "__main__":
    main()
