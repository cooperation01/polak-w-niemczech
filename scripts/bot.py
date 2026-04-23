# -*- coding: utf-8 -*-
import sys
import os
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path

# Windows UTF-8 Fix
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
from supabase import create_client
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

load_dotenv(Path(__file__).parent / ".env")

BOT_TOKEN    = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID      = int(os.environ["TELEGRAM_CHAT_ID"])
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)

VALID_CATEGORIES = {"Versicherungen", "Finanzen", "Alltag"}


def authorized(update: Update) -> bool:
    return update.effective_chat.id == CHAT_ID


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return
    await update.message.reply_text(
        "Polak Blog Bot\n\n"
        "/add <Thema> <Kategorie> - Thema hinzufuegen\n"
        "/list - Warteschlange anzeigen\n"
        "/now <Thema> <Kategorie> - Sofort generieren\n"
        "/now <URL> <Thema> <Kategorie> - Mit Quell-URL generieren\n"
        "/status - Letzte Aktionen\n"
        "/delete <ID> - Thema loeschen\n\n"
        "Kategorien: Versicherungen | Finanzen | Alltag\n"
        "Tipp: URL als erstes Argument liefert Quelltext als Kontext."
    )


async def cmd_add(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return
    args = ctx.args
    if len(args) < 2:
        await update.message.reply_text(
            "Verwendung: /add <Thema> <Kategorie>\n"
            "Beispiel: /add Rentenversicherung Finanzen"
        )
        return

    category = args[-1].capitalize()
    topic    = " ".join(args[:-1])

    if category not in VALID_CATEGORIES:
        await update.message.reply_text(
            f"Ungueltige Kategorie: {category}\n"
            f"Erlaubt: {', '.join(VALID_CATEGORIES)}"
        )
        return

    res = supabase.table("topics").insert({
        "topic":    topic,
        "category": category,
        "status":   "pending",
    }).execute()

    row_id = res.data[0]["id"]
    await update.message.reply_text(
        f"Thema hinzugefuegt!\n"
        f"ID: {row_id}\n"
        f"Thema: {topic}\n"
        f"Kategorie: {category}\n"
        f"Erscheint beim naechsten Run (07:00 UTC)"
    )


async def cmd_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return
    res = (
        supabase.table("topics")
        .select("id, topic, category, status, publish_at")
        .in_("status", ["pending", "generating"])
        .order("publish_at")
        .limit(10)
        .execute()
    )
    if not res.data:
        await update.message.reply_text("Warteschlange ist leer.")
        return

    lines = ["Warteschlange:\n"]
    for r in res.data:
        dt = r["publish_at"][:10] if r["publish_at"] else "-"
        lines.append(f"[{r['id']}] {r['topic']} ({r['category']}) - {r['status']} - {dt}")
    await update.message.reply_text("\n".join(lines))


async def cmd_now(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return
    args = list(ctx.args)
    if len(args) < 2:
        await update.message.reply_text(
            "Verwendung: /now <Thema> <Kategorie>\n"
            "Mit URL:    /now <URL> <Thema> <Kategorie>\n"
            "Beispiel:   /now Hausratversicherung Versicherungen"
        )
        return

    # Optionale URL als erstes Argument erkennen
    context_url = ""
    if args[0].startswith("http"):
        context_url = args[0]
        args = args[1:]
        if len(args) < 2:
            await update.message.reply_text(
                "Nach der URL: /now <URL> <Thema> <Kategorie>"
            )
            return

    category = args[-1].capitalize()
    topic    = " ".join(args[:-1])

    if category not in VALID_CATEGORIES:
        await update.message.reply_text(f"Ungueltige Kategorie: {category}")
        return

    insert_data = {
        "topic":       topic,
        "category":    category,
        "status":      "pending",
        "publish_at":  datetime.now(timezone.utc).isoformat(),
    }
    if context_url:
        insert_data["context_url"] = context_url

    supabase.table("topics").insert(insert_data).execute()

    url_info = f"\nKontext-URL: {context_url}" if context_url else ""
    await update.message.reply_text(f"Generiere jetzt: {topic}...{url_info}")

    script = Path(__file__).parent / "generate_post.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ},
    )
    if result.returncode == 0:
        await update.message.reply_text(
            f"Artikel generiert und gepusht!\n"
            f"Thema: {topic}\n"
            f"Live in ~2 Min: https://polak-w-niemczech.netlify.app/blog/"
        )
    else:
        err = result.stderr[-400:] if result.stderr else "Unbekannter Fehler"
        await update.message.reply_text(f"Fehler:\n{err}")


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return
    res = (
        supabase.table("topics")
        .select("id, topic, category, status, created_at")
        .order("created_at", desc=True)
        .limit(5)
        .execute()
    )
    if not res.data:
        await update.message.reply_text("Keine Eintraege.")
        return

    lines = ["Letzte Aktionen:\n"]
    status_icon = {"pending": "[warte]", "generating": "[laeuft]", "published": "[fertig]", "failed": "[fehler]"}
    for r in res.data:
        icon = status_icon.get(r["status"], "-")
        lines.append(f"{icon} [{r['id']}] {r['topic']} ({r['category']})")
    await update.message.reply_text("\n".join(lines))


async def error_handler(update: object, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    from telegram.error import Conflict, NetworkError
    if isinstance(ctx.error, Conflict):
        logging.warning("409 Conflict: Zweite Bot-Instanz laeuft. Railway-Instanz beenden oder lokalen Start stoppen.")
        return
    if isinstance(ctx.error, NetworkError):
        logging.warning("Netzwerkfehler (wird ignoriert): %s", ctx.error)
        return
    logging.error("Unbehandelter Fehler: %s", ctx.error, exc_info=ctx.error)


async def cmd_delete(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return
    if not ctx.args:
        await update.message.reply_text("Verwendung: /delete <ID>")
        return
    try:
        row_id = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text("ID muss eine Zahl sein.")
        return

    res = supabase.table("topics").select("topic, status").eq("id", row_id).execute()
    if not res.data:
        await update.message.reply_text(f"ID {row_id} nicht gefunden.")
        return

    row = res.data[0]
    if row["status"] == "published":
        await update.message.reply_text("Bereits veroeffentlicht - nicht geloescht.")
        return

    supabase.table("topics").delete().eq("id", row_id).execute()
    await update.message.reply_text(f"Geloescht: [{row_id}] {row['topic']}")


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("help",   cmd_start))
    app.add_handler(CommandHandler("add",    cmd_add))
    app.add_handler(CommandHandler("list",   cmd_list))
    app.add_handler(CommandHandler("now",    cmd_now))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("delete", cmd_delete))
    app.add_error_handler(error_handler)

    print("Bot laeuft... (Ctrl+C zum Stoppen)")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
