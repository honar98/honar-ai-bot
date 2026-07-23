import asyncio
import sqlite3
import requests
import logging
from datetime import datetime

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

asyncio.set_event_loop(asyncio.new_event_loop())

# ==========================================
# SETTINGS & API CREDENTIALS
# ==========================================

TELEGRAM_TOKEN = "8401739007:AAEhG6fOwUv2g7MKYdad2zo7PmB8YyxGnVI"
GROQ_API_KEY = "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"

# TikTok Developer Credentials (OAuth 2.0)
TIKTOK_CLIENT_KEY = "awqrbi9dy0xtcx1i"
TIKTOK_CLIENT_SECRET = "hzXZh848hGhzpRQljZJM4XVW1cOCUZHL"
TIKTOK_REDIRECT_URI = "https://honar98.github.io/honar-ai-bot/callback.html"

MODEL = "llama-3.3-70b-versatile"
API_URL = "https://api.groq.com/openai/v1/chat/completions"
DATABASE_NAME = "honar_ai.db"
MAX_HISTORY = 300

SYSTEM_PROMPT = """
You are HONAR AI Version 200.
You are a professional AI assistant.
Rules:
- Speak naturally in Kurdish Badini.
- Understand Kurdish, Arabic, Turkish and English.
- Answer in another language only if the user requests it.
- Never invent facts.
- If you don't know something, say you don't know.
- Give clear and useful answers.
- Remember previous conversation.
- Write clean and optimized code.
"""

HEADERS = {
    "Authorization": f"Bearer {GROQ_API_KEY}",
    "Content-Type": "application/json"
}

# ==========================================
# TIKTOK OAUTH BACKEND LOGIC
# ==========================================

def exchange_tiktok_code_for_token(auth_code):
    token_url = "https://open.tiktokapis.com/v2/oauth/token/"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Cache-Control": "no-cache"
    }
    payload = {
        "client_key": TIKTOK_CLIENT_KEY,
        "client_secret": TIKTOK_CLIENT_SECRET,
        "code": auth_code,
        "grant_type": "authorization_code",
        "redirect_uri": TIKTOK_REDIRECT_URI
    }
    
    try:
        response = requests.post(token_url, headers=headers, data=payload, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logging.exception("TikTok OAuth Token Exchange Error")
        return {"error": str(e)}

def fetch_tiktok_user_info(access_token, open_id):
    user_info_url = f"https://open.tiktokapis.com/v2/user/info/?fields=open_id,union_id,avatar_url,display_name"
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    
    try:
        response = requests.get(user_info_url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logging.exception("TikTok Fetch User Info Error")
        return {"error": str(e)}

# ==========================================
# SQLITE DATABASE
# ==========================================

db = sqlite3.connect(
    DATABASE_NAME,
    check_same_thread=False
)

cursor = db.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users(
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    joined_at TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS chat_history(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    role TEXT,
    message TEXT,
    created_at TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS bot_settings(
    setting_key TEXT PRIMARY KEY,
    setting_value TEXT
)
""")

db.commit()

# ==========================================
# MEMORY MANAGER
# ==========================================

def add_user(user):
    cursor.execute("""
        INSERT OR IGNORE INTO users
        (user_id, username, first_name, joined_at)
        VALUES (?, ?, ?, ?)
    """, (
        user.id,
        user.username,
        user.first_name,
        datetime.now().isoformat()
    ))
    db.commit()


def save_message(user_id, role, message):
    cursor.execute("""
        INSERT INTO chat_history
        (user_id, role, message, created_at)
        VALUES (?, ?, ?, ?)
    """, (
        user_id,
        role,
        message,
        datetime.now().isoformat()
    ))
    db.commit()


def load_history(user_id):
    cursor.execute("""
        SELECT role, message
        FROM chat_history
        WHERE user_id=?
        ORDER BY id DESC
        LIMIT ?
    """, (user_id, MAX_HISTORY))

    rows = cursor.fetchall()
    rows.reverse()

    history = []

    for role, message in rows:
        history.append({
            "role": role,
            "content": message
        })

    return history


def clear_history(user_id):
    cursor.execute(
        "DELETE FROM chat_history WHERE user_id=?",
        (user_id,)
    )
    db.commit()


def get_total_users():
    cursor.execute("SELECT COUNT(*) FROM users")
    return cursor.fetchone()[0]

# ==========================================
# COMMANDS
# ==========================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user)

    await update.message.reply_text(
        f"👋 سلاڤ {user.first_name}!\n\n"
        "بەخێربێیت بۆ HONAR AI Version 200 (TikTok Integrated).\n"
        "هەر پرسیارێکت هەیە بنێرە."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📚 فەرمانەکان:\n\n"
        "/start - دەستپێکردن\n"
        "/help - یارمەتی\n"
        "/about - دەربارەی بۆت\n"
        "/stats - ئامار\n"
        "/reset - سڕینەوەی مێژووی گفتوگۆ"
    )


async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 HONAR AI Version 200\n"
        "Powered by Groq AI & TikTok Login Kit\n"
        "Database: SQLite\n"
        "Language: Kurdish Badini"
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = get_total_users()
    await update.message.reply_text(
        f"📊 ئاماری بۆت\n\n"
        f"👥 کۆی بەکارهێنەران: {users}"
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_history(update.effective_user.id)
    await update.message.reply_text(
        "✅ مێژووی گفتوگۆ سڕایەوە."
    )

# ==========================================
# AI CHAT
# ==========================================

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    user_text = update.message.text.strip()

    add_user(user)

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING
    )

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        }
    ]

    history = load_history(user_id)
    messages.extend(history)

    messages.append(
        {
            "role": "user",
            "content": user_text
        }
    )

    data = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.2,
        "top_p": 0.9,
        "max_tokens": 2048
    }

    try:
        response = requests.post(
            API_URL,
            headers=HEADERS,
            json=data,
            timeout=60
        )

        response.raise_for_status()
        result = response.json()
        ai_reply = result["choices"][0]["message"]["content"]

        save_message(user_id, "user", user_text)
        save_message(user_id, "assistant", ai_reply)

        await update.message.reply_text(ai_reply)

    except requests.exceptions.RequestException as e:
        logging.exception("Groq API Error")
        await update.message.reply_text(
            f"❌ هەڵە لە پەیوەندی بە Groq API.\n\n{e}"
        )
    except KeyError:
        logging.exception("Invalid API Response")
        await update.message.reply_text(
            "❌ وەڵامی API دروست نەبوو."
        )
    except Exception as e:
        logging.exception("Unexpected Error")
        await update.message.reply_text(
            f"❌ هەڵەیەکی نەناسراو ڕوویدا.\n\n{e}"
        )

# ==========================================
# ERROR HANDLER
# ==========================================

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logging.exception(
        "Exception while handling update:",
        exc_info=context.error
    )

# ==========================================
# HELPER FUNCTIONS
# ==========================================

def get_chat_count(user_id):
    cursor.execute(
        "SELECT COUNT(*) FROM chat_history WHERE user_id=?",
        (user_id,)
    )
    row = cursor.fetchone()
    return row[0] if row else 0


def delete_old_messages(user_id):
    cursor.execute("""
        DELETE FROM chat_history
        WHERE user_id=?
        AND id NOT IN (
            SELECT id FROM (
                SELECT id
                FROM chat_history
                WHERE user_id=?
                ORDER BY id DESC
                LIMIT ?
            )
        )
    """, (user_id, user_id, MAX_HISTORY))
    db.commit()


def get_database_size():
    cursor.execute("SELECT COUNT(*) FROM chat_history")
    row = cursor.fetchone()
    return row[0] if row else 0

# ==========================================
# ADMIN SETTINGS & COMMANDS
# ==========================================

ADMIN_IDS = [
    1261068654
]

def is_admin(user_id):
    return user_id in ADMIN_IDS


async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ تۆ دەسەڵاتی ئەدمینت نییە.")
        return

    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM chat_history")
    total_messages = cursor.fetchone()[0]

    await update.message.reply_text(
        f"""📊 HONAR AI Admin

👥 Users: {total_users}
💬 Messages: {total_messages}
"""
    )


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ تۆ دەسەڵاتی ئەدمینت نییە.")
        return

    if not context.args:
        await update.message.reply_text("نمونە:\n/broadcast سلاڤ هەمووان")
        return

    message = " ".join(context.args)
    cursor.execute("SELECT user_id FROM users")
    users_list = cursor.fetchall()
    sent = 0

    for uid in users_list:
        try:
            await context.bot.send_message(chat_id=uid[0], text=message)
            sent += 1
        except Exception:
            pass

    await update.message.reply_text(f"✅ پەیام نێردرا بۆ {sent} بەکارهێنەر.")


async def cleardatabase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ تۆ ئەدمین نیت.")
        return

    cursor.execute("DELETE FROM chat_history")
    db.commit()
    await update.message.reply_text("✅ هەموو chat_history سڕایەوە.")

# ==========================================
# EXTRA COMMANDS
# ==========================================

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    stats_count = get_chat_count(user.id)
    await update.message.reply_text(
        f"""👤 HONAR AI Profile

🆔 ID: {user.id}
👤 Name: {user.first_name}
📛 Username: @{user.username if user.username else 'None'}

💬 Total Messages: {stats_count}
"""
    )


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏓 Pong!\n\nHONAR AI Online ✅")


async def botinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total_users = get_total_users()
    total_messages = get_database_size()
    await update.message.reply_text(
        f"""🤖 HONAR AI\n\n📦 Version : 200\n🧠 AI : Groq\n💾 Database : SQLite\n\n👥 Users : {total_users}\n💬 Messages : {total_messages}\n\n✅ Status : Online"""
    )


START_TIME = datetime.now()

async def uptime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    delta = datetime.now() - START_TIME
    await update.message.reply_text(f"⏱ Uptime:\n{delta}")


async def exportchat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cursor.execute("SELECT role, message, created_at FROM chat_history WHERE user_id=? ORDER BY id ASC", (user_id,))
    rows = cursor.fetchall()

    if not rows:
        await update.message.reply_text("📭 هیچ مێژوویەک نەدۆزرایەوە.")
        return

    filename = f"chat_{user_id}.txt"
    with open(filename, "w", encoding="utf-8") as f:
        for role, message, created_at in rows:
            f.write(f"[{created_at}] {role.upper()}:\n{message}\n\n")

    await update.message.reply_document(document=open(filename, "rb"), filename=filename)


async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("نمونە:\n/search python")
        return

    keyword = " ".join(context.args)
    cursor.execute("SELECT role, message FROM chat_history WHERE user_id=? AND message LIKE ? ORDER BY id DESC LIMIT 10", (update.effective_user.id, f"%{keyword}%"))
    rows = cursor.fetchall()

    if not rows:
        await update.message.reply_text("❌ هیچ ئەنجامێک نەدۆزرایەوە.")
        return

    text = "🔍 ئەنجامەکان:\n\n"
    for role, message in rows:
        text += f"{role}: {message[:150]}\n\n"

    await update.message.reply_text(text)


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 فەرمانەکان:\n/start\n/help\n/about\n/stats\n/reset\n/profile\n/ping\n/botinfo\n/uptime\n/exportchat\n/search"
    )

# ==========================================
# BUILD APPLICATION
# ==========================================

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

app.add_error_handler(error_handler)

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CommandHandler("about", about))
app.add_handler(CommandHandler("stats", stats))
app.add_handler(CommandHandler("reset", reset))
app.add_handler(CommandHandler("profile", profile))
app.add_handler(CommandHandler("ping", ping))
app.add_handler(CommandHandler("botinfo", botinfo))
app.add_handler(CommandHandler("uptime", uptime))
app.add_handler(CommandHandler("exportchat", exportchat))
app.add_handler(CommandHandler("search", search))
app.add_handler(CommandHandler("menu", menu))
app.add_handler(CommandHandler("users", users_command))
app.add_handler(CommandHandler("broadcast", broadcast))
app.add_handler(CommandHandler("cleardatabase", cleardatabase))

app.add_handler(
    MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        chat
    )
)

print("====================================")
print(" HONAR AI Version 200 Started")
print(" Powered by Groq & TikTok OAuth")
print("====================================")

app.run_polling(drop_pending_updates=True)
