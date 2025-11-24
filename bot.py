import logging
import sqlite3
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

TOKEN = "8219762029:AAE4AxNp_lDl-nsmobWcMjeMdtYRFTRFanE"  # ← твой токен

# На серверах файловая система временная → сохраняем БД в /tmp
DB_PATH = "/tmp/archive.db" if os.path.exists("/tmp") else "archive.db"

logging.basicConfig(level=logging.INFO)
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
c = conn.cursor()
c.execute("""CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE)""")
c.execute("""CREATE TABLE IF NOT EXISTS media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cat_id INTEGER, file_id TEXT, type TEXT, caption TEXT)""")
conn.commit()

def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Добавить медиа", callback_data="add_media")],
        [InlineKeyboardButton("Мои жанры", callback_data="genres_1")],
        [InlineKeyboardButton("Создать жанр", callback_data="create_genre")],
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Это твой личный архив видео и фото\n\nВыбери действие:",
        reply_markup=main_menu()
    )

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data

    if data == "main":
        await q.edit_message_text("Главное меню:", reply_markup=main_menu())

    elif data == "create_genre":
        await q.edit_message_text("Напиши название нового жанра:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Отмена", callback_data="main")]]))
        context.user_data["action"] = "new_genre"

    elif data == "add_media":
        c.execute("SELECT id, name FROM categories")
        cats = c.fetchall()
        if not cats:
            await q.edit_message_text("Нет жанров! Создай первый:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Создать жанр", callback_data="create_genre")]]))
            return
        kb = [[InlineKeyboardButton(n, callback_data=f"to_{i")] for i, n in cats]
        kb.append([InlineKeyboardButton("Отмена", callback_data="main")])
        await q.edit_message_text("Куда добавить?", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("to_"):
        cat_id = int(data.split("_")[1])
        c.execute("SELECT name FROM categories WHERE id=?", (cat_id,))
        name = c.fetchone()[0]
        context.user_data["cat"] = cat_id
        await q.edit_message_text(f"Кидай фото/видео → попадёт в «{name}»",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Готово", callback_data="main")]]))

    elif data.startswith("genre_"):
        cat_id = int(data.split("_")[1])
        context.user_data["cur"] = cat_id
        c.execute("SELECT name FROM categories WHERE id=?", (cat_id,))
        name = c.fetchone()[0]
        await q.edit_message_text(f"Жанр: {name}", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Смотреть всё", callback_data=f"view_{cat_id}_1")],
            [InlineKeyboardButton("Добавить сюда", callback_data=f"to_{cat_id}")],
            [InlineKeyboardButton("Назад", callback_data="genres_1")],
            [InlineKeyboardButton("Главное", callback_data="main")]
        ]))

    elif data.startswith("view_"):
        parts = data.split("_")
        cat_id = int(parts[1])
        page = int(parts[2]) if len(parts) > 2 else 1
        await view_genre(q, cat_id, page)

    elif data.startswith("del_"):
        mid = int(data.split("_")[1])
        c.execute("DELETE FROM media WHERE id=?", (mid,))
        conn.commit()
        await q.edit_message_text("Удалено!", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Назад", callback_data=f"view_{context.user_data.get('cur',1)}_1")]
        ]))

    elif data.startswith("genres_"):
        await show_genres(q, int(data.split("_")[1]))

async def show_genres(query, page=1):
    per_page = 8
    offset = (page-1)*per_page
    c.execute("SELECT id, name FROM categories ORDER BY name LIMIT ? OFFSET ?", (per_page+1, offset))
    rows = c.fetchall()
    kb = [[InlineKeyboardButton(n, callback_data=f"genre_{i}")] for i, n in rows[:per_page]]
    nav = []
    if page > 1: nav.append(InlineKeyboardButton("←", callback_data=f"genres_{page-1}"))
    if len(rows) > per_page: nav.append(InlineKeyboardButton("→", callback_data=f"genres_{page+1}"))
    if nav: kb.append(nav)
    kb.append([InlineKeyboardButton("Главное", callback_data="main")])
    await query.edit_message_text("Твои жанры:", reply_markup=InlineKeyboardMarkup(kb))

async def view_genre(query, cat_id, page=1):
    per_page = 5
    offset = (page-1)*per_page
    c.execute("""SELECT id, file_id, type, caption FROM media 
                 WHERE cat_id=? ORDER BY id DESC LIMIT ? OFFSET ?""", 
              (cat_id, per_page+1, offset))
    items = c.fetchall()
    c.execute("SELECT name FROM categories WHERE id=?", (cat_id,))
    name = c.fetchone()[0]

    if not items:
        await query.edit_message_text(f"«{name}» пусто :(", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Добавить", callback_data=f"to_{cat_id}")],
            [InlineKeyboardButton("Назад", callback_data="genres_1")]
        ]))
        return

    for mid, file_id, typ, cap in items[:per_page]:
        kb = [
            [InlineKeyboardButton("Удалить", callback_data=f"del_{mid}")],
        ]
        caption = cap or ""

        try:
            file = await query.bot.get_file(file_id)
            if typ == "photo":
                await query.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=file.file_path,
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup(kb)
                )
            else:
                await query.bot.send_video(
                    chat_id=query.message.chat_id,
                    video=file.file_path,
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup(kb)
                )
        except Exception as e:
            await query.bot.send_message(query.message.chat_id, f"Не удалось загрузить файл :(")

    # навигация
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("←", callback_data=f"view_{cat_id}_{page-1}"))
    if len(items) > per_page:
        nav.append(InlineKeyboardButton("→", callback_data=f"view_{cat_id}_{page+1}"))
    nav.append(InlineKeyboardButton("Назад к жанру", callback_data=f"genre_{cat_id}"))
    await query.bot.send_message(query.message.chat_id, "⬇ Навигация ⬇", reply_markup=InlineKeyboardMarkup([nav]))

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("action") == "new_genre":
        name = update.message.text.strip()
        try:
            c.execute("INSERT INTO categories (name) VALUES (?)", (name,))
            conn.commit()
            await update.message.reply_text(f"Жанр «{name}» создан!", reply_markup=main_menu())
        except:
            await update.message.reply_text("Такой жанр уже есть!")
        context.user_data.clear()

async def media_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cat_id = context.user_data.get("cat")
    if not cat_id:
        return
    c.execute("SELECT name FROM categories WHERE id=?", (cat_id,))
    name = c.fetchone()[0]
    caption = update.message.caption

    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        typ = "photo"
    elif update.message.video:
        file_id = update.message.video.file_id
        typ = "video"
    else:
        return

    c.execute("INSERT INTO media (cat_id, file_id, type, caption) VALUES (?, ?, ?, ?)",
              (cat_id, file_id, typ, caption))
    conn.commit()
    await update.message.reply_text(f"Добавлено в «{name}»", reply_markup=main_menu())
    context.user_data.pop("cat", None)

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO, media_handler))
    print("Бот запущен 24/7!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
