import os
import requests
import telebot
from flask import Flask, request

BOT_TOKEN = "6219694069:AAGQ6J0nDTW-9jO4VNp2mZo9paZvwQMlk5E"
CHANNEL_ID = "-1003203955147"

bot = telebot.TeleBot(BOT_TOKEN)
server = Flask(__name__)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# --------------------------
# دالة لتحويل رابط يوتيوب إلى mp3 مضغوط
# --------------------------
def download_youtube_audio(url):
    try:
        # واجهة بديلة لتحويل الفيديو إلى mp3
        api_url = "https://api.snaptik.app/api/ytmp3"
        params = {"url": url}
        r = requests.get(api_url, params=params, timeout=60)
        r.raise_for_status()
        data = r.json()

        if data.get("success") and data.get("audio_url"):
            audio_response = requests.get(data["audio_url"], timeout=60)
            title = data.get("title", "audio")
            safe_title = "".join([c if c.isalnum() else "_" for c in title])
            path = os.path.join(DOWNLOAD_DIR, f"{safe_title}.mp3")
            with open(path, "wb") as f:
                f.write(audio_response.content)
            return path, title
        else:
            return None, None
    except Exception as e:
        print("⚠️ خطأ أثناء التحويل:", e)
        return None, None

# --------------------------
# استقبال الرسائل
# --------------------------
@bot.message_handler(commands=['start'])
def start(msg):
    bot.reply_to(msg, "🎧 أرسل رابط فيديو YouTube وسأرسله كصوت مضغوط جدًا ≤3 ميجا إلى القناة.")

@bot.message_handler(func=lambda m: 'youtube.com' in m.text or 'youtu.be' in m.text)
def handle_youtube(msg):
    url = msg.text.strip()
    bot.reply_to(msg, "⏳ جارِ تحميل الصوت وضغطه، انتظر قليلاً...")

    path, title = download_youtube_audio(url)
    if path and os.path.exists(path):
        try:
            with open(path, "rb") as f:
                bot.send_audio(CHANNEL_ID, f, caption=f"🎶 {title} | © قناتي 🌙")
            bot.reply_to(msg, "✅ تم نشر الصوت في القناة بنجاح.")
        except Exception as e:
            bot.reply_to(msg, f"❌ خطأ أثناء الإرسال: {e}")
        finally:
            os.remove(path)
    else:
        bot.reply_to(msg, "⚠️ فشل التحميل أو التحويل.")

# --------------------------
# إعداد Flask لـ Render
# --------------------------
@server.route("/" + BOT_TOKEN, methods=["POST"])
def getMessage():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "OK", 200

@server.route("/")
def webhook():
    bot.remove_webhook()
    bot.set_webhook(url="https://juzif-bot.onrender.com/" + BOT_TOKEN)
    return "Webhook set", 200

if __name__ == "__main__":
    server.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
