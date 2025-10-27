import os
import telebot
from flask import Flask, request
import yt_dlp

# إعدادات البوت
BOT_TOKEN = "6219694069:AAGQ6J0nDTW-9jO4VNp2mZo9paZvwQMlk5E"
CHANNEL_ID = "-1003203955147"

bot = telebot.TeleBot(BOT_TOKEN)
server = Flask(__name__)

# إعدادات التحميل
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# إعدادات ضغط الصوت (جودة منخفضة جداً)
AUDIO_OPTS = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '16',  # جودة منخفضة جدًا
    }],
    'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s'),
    'quiet': True,
}

# استقبال الرابط من المستخدم
@bot.message_handler(commands=['start'])
def start(msg):
    bot.reply_to(msg, "🎧 أرسل لي رابط فيديو من YouTube وسأحوله إلى صوت مضغوط جدًا (≤ 3 ميجا تقريبًا).")

@bot.message_handler(func=lambda m: 'youtube.com' in m.text or 'youtu.be' in m.text)
def handle_youtube(msg):
    url = msg.text.strip()
    bot.reply_to(msg, "⏳ جارِ تحميل الصوت وضغطه، انتظر قليلاً...")

    try:
        with yt_dlp.YoutubeDL(AUDIO_OPTS) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            audio_path = os.path.splitext(filename)[0] + ".mp3"

        if os.path.exists(audio_path):
            with open(audio_path, "rb") as f:
                bot.send_audio(CHANNEL_ID, f, caption=f"🎶 {info.get('title', 'Audio')}")
            os.remove(audio_path)
            bot.reply_to(msg, "✅ تم نشر الصوت في القناة بنجاح.")
        else:
            bot.reply_to(msg, "❌ فشل العثور على الملف الصوتي.")
    except Exception as e:
        bot.reply_to(msg, f"⚠️ حدث خطأ أثناء المعالجة: {e}")

# إعداد Flask لـ Render
@server.route("/" + BOT_TOKEN, methods=["POST"])
def getMessage():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "OK", 200

@server.route("/")
def webhook():
    bot.remove_webhook()
    bot.set_webhook(url="https://juzif_bot.onrender.com/" + BOT_TOKEN)
    return "Webhook set", 200

if __name__ == "__main__":
    server.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
