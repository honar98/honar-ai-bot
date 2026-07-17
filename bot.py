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
# SETTINGS
# ==========================================

TELEGRAM_TOKEN = "TELEGRAM_TOKEN"
GROQ_API_KEY = "GROQ_API_KEY"

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
        "بەخێربێیت بۆ HONAR AI Version 200.\n"
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
        "Powered by Groq AI\n"
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

def get_username(user):
    if user.username:
        return f"@{user.username}"
    return user.first_name or "Unknown"


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


def save_message_safe(user_id, role, message):
    if not message:
        return

    save_message(user_id, role, message)
    delete_old_messages(user_id)


def get_database_size():
    cursor.execute("SELECT COUNT(*) FROM chat_history")
    row = cursor.fetchone()
    return row[0] if row else 0


def database_commit():
    try:
        db.commit()
    except Exception as e:
        logging.exception(e)

# ==========================================
# ADMIN SETTINGS
# ==========================================

ADMIN_IDS = [
    123456789
]


def is_admin(user_id):
    return user_id in ADMIN_IDS


# ==========================================
# ADMIN COMMANDS
# ==========================================

async def users(update: Update, context: ContextTypes.DEFAULT_TYPE):

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
        await update.message.reply_text(
            "نمونە:\n/broadcast سلاڤ هەمووان"
        )
        return

    message = " ".join(context.args)

    cursor.execute("SELECT user_id FROM users")
    users_list = cursor.fetchall()

    sent = 0

    for uid in users_list:
        try:
            await context.bot.send_message(
                chat_id=uid[0],
                text=message
            )
            sent += 1
        except Exception:
            pass

    await update.message.reply_text(
        f"✅ پەیام نێردرا بۆ {sent} بەکارهێنەر."
    )

# ==========================================
# USER PROFILE
# ==========================================

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    stats = get_chat_count(user.id)

    await update.message.reply_text(
        f"""👤 HONAR AI Profile

🆔 ID: {user.id}
👤 Name: {user.first_name}
📛 Username: @{user.username if user.username else 'None'}

💬 Total Messages: {stats}
"""
    )


# ==========================================
# PING
# ==========================================

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "🏓 Pong!\n\nHONAR AI Online ✅"
    )

# ==========================================
# BOT INFO
# ==========================================

BOT_VERSION = "200"
BOT_NAME = "HONAR AI"


async def botinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):

    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM chat_history")
    total_messages = cursor.fetchone()[0]

    await update.message.reply_text(
        f"""
🤖 {BOT_NAME}

📦 Version : {BOT_VERSION}
🧠 AI : Groq
💾 Database : SQLite

👥 Users : {total_users}
💬 Messages : {total_messages}

✅ Status : Online
"""
    )


# ==========================================
# UPTIME
# ==========================================

START_TIME = datetime.now()


async def uptime(update: Update, context: ContextTypes.DEFAULT_TYPE):

    delta = datetime.now() - START_TIME

    await update.message.reply_text(
        f"⏱ Uptime:\n{delta}"
    )

# ==========================================
# EXPORT CHAT
# ==========================================

async def exportchat(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    cursor.execute("""
        SELECT role, message, created_at
        FROM chat_history
        WHERE user_id=?
        ORDER BY id ASC
    """, (user_id,))

    rows = cursor.fetchall()

    if not rows:
        await update.message.reply_text(
            "📭 هیچ مێژوویەک نەدۆزرایەوە."
        )
        return

    filename = f"chat_{user_id}.txt"

    with open(filename, "w", encoding="utf-8") as f:
        for role, message, created_at in rows:
            f.write(f"[{created_at}] {role.upper()}:\n")
            f.write(message)
            f.write("\n\n")

    await update.message.reply_document(
        document=open(filename, "rb"),
        filename=filename
    )


# ==========================================
# DELETE CHAT
# ==========================================

async def deletechat(update: Update, context: ContextTypes.DEFAULT_TYPE):

    clear_history(update.effective_user.id)

    await update.message.reply_text(
        "🗑 مێژووی گفتوگۆ سڕایەوە."
    )

# ==========================================
# SEARCH HISTORY
# ==========================================

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not context.args:
        await update.message.reply_text(
            "نمونە:\n/search python"
        )
        return

    keyword = " ".join(context.args)

    cursor.execute("""
        SELECT role, message
        FROM chat_history
        WHERE user_id=?
        AND message LIKE ?
        ORDER BY id DESC
        LIMIT 10
    """, (
        update.effective_user.id,
        f"%{keyword}%"
    ))

    rows = cursor.fetchall()

    if not rows:
        await update.message.reply_text(
            "❌ هیچ ئەنجامێک نەدۆزرایەوە."
        )
        return

    text = "🔍 ئەنجامەکان:\n\n"

    for role, message in rows:
        text += f"{role}: {message[:150]}\n\n"

    await update.message.reply_text(text)


# ==========================================
# CLEAR DATABASE (ADMIN)
# ==========================================

async def cleardatabase(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ تۆ ئەدمین نیت.")
        return

    cursor.execute("DELETE FROM chat_history")
    db.commit()

    await update.message.reply_text(
        "✅ هەموو chat_history سڕایەوە."
    )

# ==========================================
# SYSTEM STATUS
# ==========================================

async def system(update: Update, context: ContextTypes.DEFAULT_TYPE):

    total_users = get_total_users()
    total_messages = get_database_size()

    await update.message.reply_text(
        f"""
🖥 HONAR AI System

🤖 Version : 200
🧠 Model : {MODEL}

👥 Users : {total_users}
💬 Messages : {total_messages}

💾 Database : SQLite
🌐 API : Groq
✅ Status : Running
"""
    )


# ==========================================
# MEMORY INFO
# ==========================================

async def memory(update: Update, context: ContextTypes.DEFAULT_TYPE):

    count = get_chat_count(update.effective_user.id)

    await update.message.reply_text(
        f"""
🧠 Memory Information

💬 Saved Messages : {count}

📦 Maximum History : {MAX_HISTORY}
"""
    )

# ==========================================
# VERSION
# ==========================================

async def version(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        f"""
🤖 HONAR AI

📦 Version : 200
🧠 Model : {MODEL}
🌐 API : Groq
💾 Database : SQLite

Developer : HONAR
"""
    )


# ==========================================
# TIME
# ==========================================

async def time(update: Update, context: ContextTypes.DEFAULT_TYPE):

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    await update.message.reply_text(
        f"🕒 Current Time\n\n{now}"
    )

# ==========================================
# LANGUAGE
# ==========================================

LANGUAGE = "Badini Kurdish"


async def language(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        f"""
🌐 Language Settings

Default Language : {LANGUAGE}

Supported Languages:
• Kurdish (Badini)
• Arabic
• English
• Turkish
"""
    )


# ==========================================
# AI MODEL
# ==========================================

async def model(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        f"""
🧠 AI Model

Model : {MODEL}

Provider : Groq

Status : Online ✅
"""
    )

# ==========================================
# AI SETTINGS
# ==========================================

async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        f"""
⚙️ HONAR AI Settings

🤖 Version : 200
🧠 Model : {MODEL}
🌐 API : Groq
💾 Database : SQLite
📝 Memory : {MAX_HISTORY} Messages
🌍 Language : {LANGUAGE}

✅ Status : Running
"""
    )


# ==========================================
# ABOUT DEVELOPER
# ==========================================

async def developer(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        """
👨‍💻 Developer

Name : HONAR

Project :
HONAR AI Version 200

Powered by:
• Groq AI
• Python
• SQLite
• Telegram Bot API
"""
    )

# ==========================================
# USER INFO
# ==========================================

async def me(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    text = f"""
👤 User Information

🆔 ID : {user.id}
👤 Name : {user.first_name}
📛 Username : @{user.username if user.username else 'None'}
🌐 Language : {user.language_code}
"""

    await update.message.reply_text(text)


# ==========================================
# SERVER INFO
# ==========================================

async def server(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        f"""
🖥 HONAR AI Server

API : Groq
Database : SQLite
Model : {MODEL}

Status : 🟢 Online
"""
    )

# ==========================================
# DATABASE INFO
# ==========================================

async def database(update: Update, context: ContextTypes.DEFAULT_TYPE):

    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM chat_history")
    total_messages = cursor.fetchone()[0]

    await update.message.reply_text(
        f"""
💾 Database Information

👥 Users : {total_users}
💬 Messages : {total_messages}

Database : SQLite
Status : Connected ✅
"""
    )


# ==========================================
# HELP MENU
# ==========================================

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        """
📋 HONAR AI Commands

/start
/help
/about
/stats
/reset

/profile
/ping
/botinfo
/uptime

/exportchat
/deletechat
/search

/system
/memory
/version
/time

/language
/model
/settings
/developer

/me
/server
/database
"""
    )

# ==========================================
# BOT HEALTH
# ==========================================

async def health(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        """
❤️ HONAR AI Health

🟢 Bot Status : Online
🧠 AI : Working
💾 Database : Connected
🌐 API : Groq

Everything is running normally.
"""
    )


# ==========================================
# CHAT STATISTICS
# ==========================================

async def mystats(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    cursor.execute(
        "SELECT COUNT(*) FROM chat_history WHERE user_id=?",
        (user_id,)
    )

    total = cursor.fetchone()[0]

    await update.message.reply_text(
        f"""
📊 Your Statistics

💬 Saved Messages : {total}

🧠 Memory Limit : {MAX_HISTORY}

✅ Status : Active
"""
    )

# ==========================================
# BOT SETTINGS
# ==========================================

async def config(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = f"""
⚙️ HONAR AI Configuration

🤖 Version : 200
🧠 Model : {MODEL}
🌐 API : Groq
💾 Database : SQLite
📚 Memory Limit : {MAX_HISTORY}
🌍 Language : {LANGUAGE}
"""

    await update.message.reply_text(text)


# ==========================================
# CONTACT
# ==========================================

async def contact(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        """
📞 HONAR AI

Developer : HONAR

Thank you for using HONAR AI ❤️
"""
    )

# ==========================================
# CHAT TOOLS
# ==========================================

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    cursor.execute("""
        SELECT COUNT(*)
        FROM chat_history
        WHERE user_id=?
    """, (user_id,))

    total = cursor.fetchone()[0]

    await update.message.reply_text(
        f"""
📚 Chat History

💬 Saved Messages : {total}

Maximum Memory : {MAX_HISTORY}
"""
    )


async def clearall(update: Update, context: ContextTypes.DEFAULT_TYPE):

    clear_history(update.effective_user.id)

    await update.message.reply_text(
        "✅ هەموو مێژووی گفتوگۆ سڕایەوە."
    )

# ==========================================
# FILE INFORMATION
# ==========================================

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        f"""
📄 HONAR AI

🤖 Name : HONAR AI
📦 Version : 200
🧠 Model : {MODEL}
💾 Database : SQLite
🌐 API : Groq
👨‍💻 Developer : HONAR
"""
    )


# ==========================================
# TEST COMMAND
# ==========================================

async def test(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "✅ Test successful!\nHONAR AI is working correctly."
    )

# ==========================================
# BOT STARTUP
# ==========================================

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "🟢 HONAR AI Version 200\n\n"
        "Bot Status: Online\n"
        "API: Groq\n"
        "Database: SQLite\n"
        "Everything is working correctly."
    )


async def commands(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        """
📋 HONAR AI Commands

/start
/help
/about
/stats
/reset

/profile
/ping
/botinfo
/uptime

/exportchat
/deletechat
/search

/system
/memory
/version
/time

/language
/model
/settings
/developer

/me
/server
/database
/menu

/health
/mystats
/config
/contact

/history
/clearall

/info
/test

/status
/commands
"""
    )

# ==========================================
# BOT INFORMATION
# ==========================================

async def credits(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = f"""
🏆 HONAR AI

🤖 Name: HONAR AI
📦 Version: 200
🧠 AI Model: {MODEL}
💾 Database: SQLite
🌐 API: Groq

👨‍💻 Developer: HONAR
❤️ Thank you for using HONAR AI!
"""

    await update.message.reply_text(text)

# ==========================================
# AI INFORMATION
# ==========================================

async def ai(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = f"""
🤖 HONAR AI

🧠 Model: {MODEL}
🌐 API: Groq
💾 Memory Limit: {MAX_HISTORY}
📦 Version: 200

✅ AI Status: Online
"""

    await update.message.reply_text(text)

# ==========================================
# BOT LATENCY
# ==========================================

async def latency(update: Update, context: ContextTypes.DEFAULT_TYPE):

    start = datetime.now()

    msg = await update.message.reply_text("⏳ Checking...")

    end = datetime.now()

    ms = int((end - start).total_seconds() * 1000)

    await msg.edit_text(f"⚡ Latency: {ms} ms")


# ==========================================
# CREATE BOT
# ==========================================

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

app.add_error_handler(error_handler)

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CommandHandler("about", about))
app.add_handler(CommandHandler("stats", stats))
app.add_handler(CommandHandler("reset", reset))

app.add_handler(
    MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        chat
    )
)

print("====================================")
print(" HONAR AI Version 200 Started")
print(" Powered by Groq")
print("====================================")

app.run_polling(drop_pending_updates=True)

