"""
generate_post.py
Holt ein pending Topic aus Supabase, generiert einen Artikel
via DeepSeek API und speichert ihn als Hugo-Markdown-Datei.
KEIN automatischer Git-Push – nur lokale Datei erstellen.
Für GitHub Actions: GH_TOKEN gesetzt → automatischer Push.
"""

import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from slugify import slugify
from supabase import create_client

# ── Umgebungsvariablen laden ──────────────────────────────────────────────────
load_dotenv(Path(__file__).parent / ".env")

DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"]
SUPABASE_URL     = os.environ["SUPABASE_URL"]
SUPABASE_KEY     = os.environ["SUPABASE_KEY"]
GH_TOKEN         = os.environ.get("GH_TOKEN", "")
GITHUB_REPO      = os.environ.get("GITHUB_REPO", "cooperation01/polak-w-niemczech")

BLOG_DIR     = Path(__file__).parent.parent / "content" / "blog"
LAST_POST    = Path(__file__).parent.parent / "last_post.json"
SITE_URL     = "https://polak-w-niemczech.netlify.app"
DEFAULT_IMG  = os.environ.get("META_DEFAULT_IMAGE_URL", f"{SITE_URL}/images/og-default.jpg")

# ── Clients ───────────────────────────────────────────────────────────────────
deepseek = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com",
)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


SYSTEM_PROMPT = """Jesteś doświadczonym redaktorem bloga 'Polak w Niemczech'.
Piszesz wyłącznie PO POLSKU. Twoje artykuły są praktyczne, przyjazne i pomocne
dla Polaków mieszkających w Niemczech. Unikasz żargonu prawnego.
Zawsze kończysz artykuł krótką informacją, że treść ma charakter informacyjny.

OBOWIĄZKOWE ZASADY NAZEWNICTWA – nigdy nie zmieniaj tych nazw:
- Firma ubezpieczeniowa: zawsze "Continentale" – NIGDY "Kontinentale", "Continental" ani żadne polskie tłumaczenie
- Produkt: "Continentale Führerschein Regelung" – skrót wyłącznie "CFR", nigdy "SFR" ani inne warianty
- NIE tłumacz na polski nazw własnych firm, produktów ani ustaw
- NIE wymyślaj skrótów – używaj wyłącznie tych, które pojawiają się w temacie lub kontekście źródłowym"""

def fetch_url_text(url: str) -> str:
    """Lädt eine Webseite und gibt bereinigten Plaintext zurück (max 4000 Zeichen)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        # HTML-Tags entfernen
        text = re.sub(r"<[^>]+>", " ", html)
        # Mehrfache Leerzeichen/Zeilenumbrüche zusammenfassen
        text = re.sub(r"\s+", " ", text).strip()
        return text[:4000]
    except Exception as e:
        print(f"[WARN] URL konnte nicht geladen werden: {e}")
        return ""


def build_user_prompt(topic: str, category: str, tags_hint: str, context_text: str = "") -> str:
    tags_line = f"Sugerowane tagi: {tags_hint}" if tags_hint else ""
    context_block = (
        f"\n\nKONTEKST ŹRÓDŁOWY (użyj jako podstawy faktycznej, zachowaj oryginalne nazwy):\n{context_text}\n"
        if context_text else ""
    )
    return f"""Napisz artykuł informacyjny (900–1200 słów) na temat:
Temat: {topic}
Kategoria: {category}
{tags_line}{context_block}
Odpowiedz WYŁĄCZNIE w tym formacie (bez żadnego tekstu przed ani po):

---
title: "TUTAJ TYTUŁ"
description: "TUTAJ OPIS SEO (max 160 znaków)"
tags: [tag1, tag2, tag3, tag4]
---

TREŚĆ ARTYKUŁU TUTAJ

Wymagania dotyczące treści:
- Min. 4 nagłówki H2 (##)
- Przynajmniej jedna lista wypunktowana
- Praktyczne wskazówki krok po kroku
- Ostatni nagłówek: ## Podsumowanie
- Zakończ zdaniem: "Pamiętaj, że powyższe informacje mają charakter wyłącznie informacyjny."
"""


def generate_article(topic: str, category: str, tags_hint: str, context_text: str = "") -> dict:
    """Ruft DeepSeek auf und gibt parsed frontmatter + content zurück."""
    response = deepseek.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": build_user_prompt(topic, category, tags_hint, context_text)},
        ],
        temperature=0.7,
        max_tokens=2000,
    )
    raw = response.choices[0].message.content.strip()

    # Frontmatter + Body trennen
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.DOTALL)
    if not match:
        raise ValueError(f"Unerwartetes Format von DeepSeek:\n{raw[:300]}")

    frontmatter_raw, body = match.group(1), match.group(2).strip()

    # Titel und Description extrahieren
    title_m = re.search(r'^title:\s*"(.+)"', frontmatter_raw, re.MULTILINE)
    desc_m  = re.search(r'^description:\s*"(.+)"', frontmatter_raw, re.MULTILINE)
    tags_m  = re.search(r'^tags:\s*\[(.+)\]', frontmatter_raw, re.MULTILINE)

    title = title_m.group(1) if title_m else topic
    desc  = desc_m.group(1)  if desc_m  else ""
    tags  = tags_m.group(1)  if tags_m  else ""

    return {"title": title, "description": desc, "tags": tags, "body": body}


def save_markdown(topic_row: dict, article: dict) -> Path:
    """Erstellt die .md Datei im Hugo content/blog/ Ordner."""
    today   = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    slug    = slugify(article["title"], max_length=60)
    fname   = f"{today}-{slug}.md"
    fpath   = BLOG_DIR / fname

    category = topic_row["category"]
    tags_str = article["tags"]

    content = f"""---
title: "{article['title']}"
date: {today}
draft: false
description: "{article['description']}"
categories: ["{category}"]
tags: [{tags_str}]
author: "Redakcja Polak w Niemczech"
---

{article['body']}
"""
    fpath.write_text(content, encoding="utf-8")
    print(f"[OK] Datei gespeichert: {fpath}")
    return fpath, slug


def push_to_github(fpath: Path, title: str) -> None:
    """Committet und pusht die neue Datei via GitHub API (nur in Actions)."""
    if not GH_TOKEN:
        print("[SKIP] Kein GH_TOKEN – kein Push (lokal)")
        return

    from github import Github
    g    = Github(GH_TOKEN)
    repo = g.get_repo(GITHUB_REPO)
    path = f"content/blog/{fpath.name}"

    repo.create_file(
        path    = path,
        message = f"Auto-Post: {title}",
        content = fpath.read_text(encoding="utf-8"),
        branch  = "main",
    )
    print(f"[OK] Gepusht: {path}")


def main():
    # 0. Stuck "generating" Topics zurücksetzen (z.B. nach Absturz)
    supabase.table("topics").update({"status": "pending"}).eq("status", "generating").execute()

    # 1. Nächstes pending Topic holen
    res = (
        supabase.table("topics")
        .select("*")
        .eq("status", "pending")
        .lte("publish_at", datetime.now(timezone.utc).isoformat())
        .order("publish_at")
        .limit(1)
        .execute()
    )

    if not res.data:
        print("[INFO] Keine Topics in der Warteschlange.")
        return

    row = res.data[0]
    print(f"[INFO] Generiere: {row['topic']} ({row['category']})")

    # 2. Status → generating
    supabase.table("topics").update({"status": "generating"}).eq("id", row["id"]).execute()

    try:
        # 3. Kontext laden (falls URL angegeben)
        context_text = ""
        context_url = row.get("context_url", "")
        if context_url:
            print(f"[INFO] Lade Kontext von: {context_url}")
            context_text = fetch_url_text(context_url)

        # 4. Artikel generieren
        article = generate_article(row["topic"], row["category"], row.get("tags_hint", ""), context_text)

        # 5. Datei speichern
        fpath, slug = save_markdown(row, article)

        # 6. In Supabase articles-Tabelle speichern (upsert verhindert Duplikat-Fehler)
        supabase.table("articles").upsert({
            "topic_id":   row["id"],
            "title":      article["title"],
            "slug":       slug,
            "content_md": fpath.read_text(encoding="utf-8"),
            "status":     "generated",
        }, on_conflict="slug").execute()

        # 7. Push (nur wenn GH_TOKEN gesetzt)
        push_to_github(fpath, article["title"])

        # 8. Status → published
        supabase.table("topics").update({
            "status": "published",
        }).eq("id", row["id"]).execute()

        # 9. Metadaten für Social-Media-Post speichern
        LAST_POST.write_text(json.dumps({
            "title":       article["title"],
            "description": article["description"],
            "slug":        slug,
            "url":         f"{SITE_URL}/blog/{slug}/",
            "image_url":   DEFAULT_IMG,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[OK] last_post.json geschrieben")

        print(f"[FERTIG] Artikel: {article['title']}")

    except Exception as e:
        supabase.table("topics").update({"status": "failed"}).eq("id", row["id"]).execute()
        print(f"[FEHLER] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
