# bot.py — красивая кнопочная версия (без Web App)
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
import sqlite3

TOKEN = "8219762029:AAE4AxNp_lDl-nsmobWcMjeMdtYRFTRFanE"  # ← твой токен

logging.basicConfig(level=logging.INFO)

conn = sqlite3.connect("archive.db", check_same_thread=False)
c = conn.cursor()
c.execute("""CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE)""")
c.execute("""CREATE TABLE IF NOT EXISTS media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cat_id INTEGER, file_id TEXT, type TEXT, caption TEXT)""")
conn.commit()

# === ГЛАВНОЕ МЕНЮ ===
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Добавить медиа", callback_data="add_media")],
        [InlineKeyboardButton("Мои жанры", callback_data="genres_1")],
        [InlineKeyboardButton("Создать жанр", callback_data="create_genre")],
    ])

# === СТАРТ ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "Привет! Это твой личный архив фильмов и мемов\n\nВыбери действие:"
    await update.message.reply_text(text, reply_markup=main_menu())

# === КНОПКИ ===
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data

    if data == "main":
        await q.edit_message_text("Главное меню:", reply_markup=main_menu())

    elif data == "create_genre":
        await q.edit_message_text("Напиши название нового жанра (например: Комедии, Ужасы, Мемы):",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Отмена", callback_data="main")]]))
        context.user_data["action"] = "new_genre"

    elif data == "add_media":
        c.execute("SELECT id, name FROM categories")
        cats = c.fetchall()
        if not cats:
            await q.edit_message_text("У тебя ещё нет жанров!\nСначала создай один ↓",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Создать жанр", callback_data="create_genre")]]))
            return
        kb = [[InlineKeyboardButton(name, callback_data=f"to_{id}")] for id, name in cats]
        kb.append([InlineKeyboardButton("Отмена", callback_data="main")])
        await q.edit_message_text("В какой жанр добавить фото/видео?", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("to_"):
        cat_id = int(data.split("_")[1])
        c.execute("SELECT name FROM categories WHERE id=?", (cat_id,))
        name = c.fetchone()[0]
        context.user_data["target_cat"] = cat_id
        await q.edit_message_text(f"Кидай фото или видео — добавится в жанр «{name}»\n(можно с подписью)",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Готово", callback_data="main")]]))

    elif data.startswith("genre_"):
        cat_id = int(data.split("_")[1])
        context.user_data["current_genre"] = cat_id
        c.execute("SELECT name FROM categories WHERE id=?", (cat_id,))
        name = c.fetchone()[0]
        keyboard = [
            [InlineKeyboardButton("Смотреть всё", callback_data=f"view_{cat_id}_1")],
            [InlineKeyboardButton("Добавить сюда", callback_data=f"to_{cat_id}")],
            [InlineKeyboardButton("Назад к списку", callback_data="genres_1")],
            [InlineKeyboardButton("Главное меню", callback_data="main")]
        ]
        await q.edit_message_text(f"Жанр: {name}", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("view_"):
        await view_genre(q, int(data.split("_")[1]), int(data.split("_")[2]) if "_" in data[5:] else 1)

    elif data.startswith("media_del_"):
        mid = int(data.split("_")[2])
        c.execute("DELETE FROM media WHERE id=?", (mid,))
        conn.commit()
        await q.edit_message_text("Удалено!", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Назад", callback_data=f"view_{context.user_data['current_genre']}_1")]
        ]))

    elif data.startswith("media_cap_"):
        mid = int(data.split("_")[2])
        context.user_data["edit_caption"] = mid
        await q.edit_message_text("Напиши новую подпись (или оставь пустым):",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Отмена", callback_data="main")]]))

    elif data.startswith("genres_"):
        await show_genres(q, int(data.split("_")[1]))

# === СПИСОК ЖАНРОВ ===
async def show_genres(query, page=1):
    per_page = 8
    offset = (page-1)*per_page
    c.execute("SELECT id, name FROM categories ORDER BY name LIMIT ? OFFSET ?", (per_page+1, offset))
    genres = c.fetchall()
    kb = [[InlineKeyboardButton(name, callback_data=f"genre_{id}")] for id, name in genres[:per_page]]
    nav = []
    if page > 1: nav.append(InlineKeyboardButton("Назад", callback_data=f"genres_{page-1}"))
    if len(genres) > per_page: nav.append(InlineKeyboardButton("Вперёд", callback_data=f"genres_{page+1}"))
    if nav: kb.append(nav)
    kb.append([InlineKeyboardButton("Главное меню", callback_data="main")])
    await query.edit_message_text("Твои жанры:", reply_markup=InlineKeyboardMarkup(kb))

# === ПРОСМОТР ЖАНРА ===
# === ПРОСМОТР ЖАНРА — РАБОЧАЯ ВЕРСИЯ ДЛЯ СЕРВЕРА ===
async def view_genre(query, cat_id, page=1):
    per_page = 5
    offset = (page-1)*per_page
    c.execute("SELECT id, file_id, type, caption FROM media WHERE cat_id=? ORDER BY id DESC LIMIT ? OFFSET ?",
              (cat_id, per_page+1, offset))
    items = c.fetchall()
    c.execute("SELECT name FROM categories WHERE id=?", (cat_id,))
    name = c.fetchone()[0]

    if not items:
        await query.edit_message_text(f"«{name}» пока пусто :(", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Добавить сюда", callback_data=f"to_{cat_id}")],
            [InlineKeyboardButton("Назад", callback_data="genres_1")]
        ]))
        return

    for mid, file_id, typ, cap in items[:per_page]:
        kb = [
            [InlineKeyboardButton("Изменить подпись", callback_data=f"media_cap_{mid}")],
            [InlineKeyboardButton("Удалить", callback_data=f"media_del_{mid}")],
        ]
        caption = cap or "Без подписи"

        try:
            # Скачиваем файл и отправляем заново — работает везде!
            if typ == "photo":
                file = await query.bot.get_file(file_id)
                await query.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=file.file_path,
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup(kb)
                )
            else:  # video
                file = await query.bot.get_file(file_id)
                await query.bot.send_video(
                    chat_id=query.message.chat_id,
                    video=file.file_path,
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup(kb)
                )
        except Exception as e:
            await query.bot.send_message(query.message.chat_id, f"Ошибка при загрузке файла (ID: {mid})")

    # Навигация
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("Назад", callback_data=f"view_{cat_id}_{page-1}"))
    if len(items) > per_page:
        nav.append(InlineKeyboardButton("Вперёд", callback_data=f"view_{cat_id}_{page+1}"))
    nav.append(InlineKeyboardButton("К жанру", callback_data=f"genre_{cat_id}"))
    await query.bot.send_message(query.message.chat_id, "Навигация:", reply_markup=InlineKeyboardMarkup([nav]))

# === ТЕКСТ ===
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("action") == "new_genre":
        name = update.message.text.strip()
        if len(name) > 50:
            await update.message.reply_text("Слишком длинное название!")
            return
        try:
            c.execute("INSERT INTO categories (name) VALUES (?)", (name,))
            conn.commit()
            await update.message.reply_text(f"Жанр «{name}» создан!", reply_markup=main_menu())
        except sqlite3.IntegrityError:
            await update.message.reply_text("Такой жанр уже есть!")
        context.user_data.clear()

    elif context.user_data.get("edit_caption"):
        mid = context.user_data["edit_caption"]
        c.execute("UPDATE media SET caption=? WHERE id=?", (update.message.text or None, mid))
        conn.commit()
        await update.message.reply_text("Подпись обновлена!", reply_markup=main_menu())
        context.user_data.pop("edit_caption")

# === МЕДИА ===
async def media_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("target_cat"):
        return
    cat_id = context.user_data["target_cat"]
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
    await update.message.reply_text(f"Добавлено в «{name}»!", reply_markup=main_menu())
    context.user_data.pop("target_cat")

# === ЗАПУСК ===
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO, media_handler))
    print("Бот запущен! Пиши /start")
    app.run_polling()

if __name__ == "__main__":
    main()
