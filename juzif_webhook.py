import telebot
import yt_dlp
import os
from flask import Flask, request

# 🔹 ضع هنا توكن البوت الحقيقي (استبدل النص أدناه بتوكنك)
BOT_TOKEN = "6219694069:AAGQ6J0nDTW-9jO4VNp2mZo9paZvwQMlk5E"
bot = telebot.TeleBot(BOT_TOKEN)

# 🔹 رابط تطبيقك في Render
WEBHOOK_URL = f"https://juzif-bot.onrender.com/{BOT_TOKEN}"

app = Flask(__name__)

# ✅ اضبط Webhook عند بدء التشغيل
@app.before_first_request
def set_webhook():
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    print(f"✅ Webhook set to {WEBHOOK_URL}")

@app.route(f"/{BOT_TOKEN}", methods=['POST'])
def webhook():
    update = request.stream.read().decode("utf-8")
    bot.process_new_updates([telebot.types.Update.de_json(update)])
    return "OK", 200

# 🎧 عند إرسال رابط يوتيوب
@bot.message_handler(func=lambda msg: msg.text and "youtube.com" in msg.text or "youtu.be" in msg.text)
def handle_youtube_link(message):
    url = message.text.strip()
    bot.reply_to(message, "⏳ جاري التحميل بجودة منخفضة جدًا...")
    try:
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": "audio.%(ext)s",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "m4a",
                "preferredquality": "16",  # جودة منخفضة جدًا
            }],
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "بدون عنوان")
            file = "audio.m4a"

        with open(file, "rb") as audio:
            bot.send_audio(message.chat.id, audio, caption=f"🎵 {title}")

        os.remove(file)
    except Exception as e:
        bot.reply_to(message, f"❌ حدث خطأ أثناء التحميل: {e}")

@app.route("/", methods=["GET"])
def home():
    return "🤖 juzif-bot is running!", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
