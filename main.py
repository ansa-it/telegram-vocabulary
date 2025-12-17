import sqlite3
import random
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
import os
from dotenv import load_dotenv
import httpx

# Datenbank initialisieren
def init_db():
    conn = sqlite3.connect("/app/data/vocab.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vocab (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            english TEXT NOT NULL,
            german TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

# Interaktives Hinzufügen von Vokabeln
async def add_vocab(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 1:
        await update.message.reply_text("Bitte gib ein englisches Wort an: /add <Englisches Wort>")
        return

    english_word = " ".join(context.args)
    context.user_data['mode'] = 'add_vocab'
    context.user_data['english_word'] = english_word
    try:
        german_suggestion = await translate_text(english_word, "DE")
    except Exception as e:
        german_suggestion = "(Übersetzung fehlgeschlagen)"

    context.user_data['german_suggestion'] = german_suggestion

    await update.message.reply_text(
        f"Englisches Wort: '{english_word}' gespeichert.\n"
        f"Vorgeschlagene Übersetzung: {german_suggestion}\n"
        f"✅ = übernehmen, oder eigene deutsche Übersetzung eingeben."
    )
    

async def handle_translation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('mode') != 'add_vocab':
        return  # Ignoriere Nachrichten, die nicht im Hinzufügemodus sind

    user_input = update.message.text.strip()
    english_word = context.user_data.pop('english_word', None)
    german_suggestion = context.user_data.pop('german_suggestion', None)
    context.user_data.pop('mode', None)

    if user_input.lower() in ["✅", "ja", "ok", "passt", "bestätige", "👍", "✔️"]:
        german_word = german_suggestion
    else:
        german_word = user_input
    
    if not english_word:
        await update.message.reply_text("Fehler: Es wurde kein englisches Wort gefunden. Bitte starte erneut mit /add.")
        return

    conn = sqlite3.connect("/app/data/vocab.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO vocab (english, german) VALUES (?, ?)", (english_word, german_word))
    conn.commit()
    conn.close()

    await update.message.reply_text(f"Vokabel hinzugefügt: {english_word} - {german_word}")

# Training starten
async def train(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        num_questions = int(context.args[0]) if context.args else 20
    except ValueError:
        await update.message.reply_text("Bitte gib eine gültige Anzahl von Fragen ein: /train [ANZAHL]")
        return

    conn = sqlite3.connect("/app/data/vocab.db")
    cursor = conn.cursor()
    cursor.execute("SELECT english, german FROM vocab")
    vocabs = cursor.fetchall()
    conn.close()

    if not vocabs:
        await update.message.reply_text("Es sind keine Vokabeln gespeichert. Füge zuerst welche hinzu!")
        return

    context.user_data['mode'] = 'training'
    context.user_data['training'] = {
        'questions': random.sample(vocabs, min(num_questions, len(vocabs))),
        'current': 0,
        'correct': 0
    }

    await ask_question(update, context)

async def ask_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print( context.user_data.get('training') )
    print( context.user_data.get('mode') )
    training = context.user_data.get('training')
    if not training:
        await update.message.reply_text("Kein Training aktiv. Starte eins mit /train [ANZAHL].")
        return

    if training['current'] >= len(training['questions']):
        correct = training['correct']
        total = len(training['questions'])
        await update.message.reply_text(f"Training beendet! Du hast {correct} von {total} richtig!")
        context.user_data.pop('training', None)
        context.user_data.pop('mode', None)
        return

    english, german = training['questions'][training['current']]
    if random.choice([True, False]):
        context.user_data['current_question'] = (english, german, 'english')
        await update.message.reply_text(f"Was ist die deutsche Übersetzung von: {english}?")
    else:
        context.user_data['current_question'] = (english, german, 'german')
        await update.message.reply_text(f"Was ist die englische Übersetzung von: {german}?")

async def handle_training_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print( context.user_data.get('training') )
    print( context.user_data.get('mode') )
    if context.user_data.get('mode') != 'training':
        return  # Ignoriere Nachrichten, die nicht im Trainingsmodus sind

    training = context.user_data.get('training')
    if not training or 'current_question' not in context.user_data:
        return

    answer = update.message.text.strip().lower()
    english, german, lang = context.user_data.pop('current_question')
    correct_answer = german if lang == 'english' else english

    if answer == correct_answer.lower():
        training['correct'] += 1
        await update.message.reply_text("Richtig!")
    else:
        await update.message.reply_text(f"Falsch! Die richtige Antwort ist: {correct_answer}")

    training['current'] += 1
    await ask_question(update, context)

# Training abbrechen
async def cancel_training(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('mode') == 'training':
        context.user_data.pop('training', None)
        context.user_data.pop('mode', None)
        await update.message.reply_text("Training abgebrochen.")
    else:
        await update.message.reply_text("Kein aktives Training zum Abbrechen.")

# Liste anzeigen
async def list_vocabs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect("/app/data/vocab.db")
    cursor = conn.cursor()
    cursor.execute("SELECT english, german FROM vocab LIMIT 100")
    vocabs = cursor.fetchall()
    conn.close()

    if vocabs:
        vocab_list = "\n".join([f"{english} - {german}" for english, german in vocabs])
        await update.message.reply_text(f"Gespeicherte Vokabeln:\n{vocab_list}")
    else:
        await update.message.reply_text("Es sind keine Vokabeln gespeichert.")

# Nach Vokabel suchen
async def search_vocab(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 1:
        await update.message.reply_text("Bitte gib ein Wort zum Suchen ein: /search <Wort>")
        return

    search_term = " ".join(context.args).lower()
    conn = sqlite3.connect("/app/data/vocab.db")
    cursor = conn.cursor()
    cursor.execute("SELECT english, german FROM vocab WHERE english LIKE ? OR german LIKE ?", (f"%{search_term}%", f"%{search_term}%"))
    results = cursor.fetchall()
    conn.close()

    if results:
        result_list = "\n".join([f"{english} - {german}" for english, german in results])
        await update.message.reply_text(f"Gefundene Vokabeln:\n{result_list}")
    else:
        await update.message.reply_text("Keine Vokabeln gefunden.")

# Start-Befehl
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Willkommen beim Vokabeltrainer! Befehle:\n"
                                    "/add <Englisches Wort> - Neue Vokabel interaktiv hinzufügen\n"
                                    "/train [ANZAHL] - Training starten\n"
                                    "/cancel - Training abbrechen\n"
                                    "/list - Alle Vokabeln anzeigen\n"
                                    "/search <Wort> - Nach einer Vokabel suchen")

# Übersetzung mit DeepL API
async def translate_text(text: str, target_lang: str) -> str:
    url = "https://api-free.deepl.com/v2/translate"
    headers = {
        "Authorization": f"DeepL-Auth-Key {os.getenv('DEEPL_API_KEY')}"
    }
    data = {
        "text": text,
        "target_lang": target_lang
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, data=data)
        if response.status_code == 200:
            return response.json()["translations"][0]["text"]
        else:
            return "Übersetzung fehlgeschlagen."

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get('mode')

    if mode == 'add_vocab':
        # Falls der Benutzer sich im Hinzufügemodus befindet
        await handle_translation(update, context)
    elif mode == 'training':
        # Falls der Benutzer sich im Trainingsmodus befindet
        await handle_training_answer(update, context)
    else:
        # Standardantwort, wenn kein Modus aktiv ist
        await update.message.reply_text("Ich bin mir nicht sicher, was du meinst. Verwende /start für Hilfe.")


# Hauptfunktion
def main():
    load_dotenv()
    TOKEN = os.getenv("TELEGRAM_TOKEN")
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("add", add_vocab))
    application.add_handler(CommandHandler("list", list_vocabs))
    application.add_handler(CommandHandler("search", search_vocab))
    application.add_handler(CommandHandler("train", train))
    application.add_handler(CommandHandler("cancel", cancel_training))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    init_db()
    application.run_polling()

if __name__ == "__main__":
    main()

