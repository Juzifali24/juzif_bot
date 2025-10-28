import os, requests, telebot
from flask import Flask, request
from pydub import AudioSegment

BOT_TOKEN = "6219694069:AAGQ6J0nDTW-9jO4VNp2mZo9paZvwQMlk5E"
CHANNEL_ID = "-1003203955147"  # رقم قناتك
bot = telebot.TeleBot(BOT_TOKEN)
server = Flask(__name__)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def get_audio_link(youtube_url):
    try:
        api_url = f"https://api.vevioz.com/api/button/mp3/{youtube_url.split('?')[0]}"
        r = requests.get(api_url, timeout=10)
        if r.status_code == 200 and "href" in r.text:
            # استخراج أول رابط تحميل mp3
            import re
            m = re.search(r'href="([^"]+)"', r.text)
            if m:
                return m.group(1)
    except Exception as e:
        print("API error:", e)
    return None

def compress_audio(src_path):
    out_path = src_path.replace(".mp3", "_compressed.mp3")
    try:
        sound = AudioSegment.from_file(src_path)
        sound.export(out_path, format="mp3", bitrate="16k")
        return out_path
    except Exception as e:
        print("Compress error:", e)
        return src_path

@bot.message_handler(commands=['start'])
def start(msg):
    bot.reply_to(msg, "🎧 أرسل لي رابط YouTube وسأنشره كصوت مضغوط جدًا!")

@bot.message_handler(func=lambda m: 'youtube.com' in m.text or 'youtu.be' in m.text)
def handle(msg):
    url = msg.text.strip()
    bot.reply_to(msg, "⏳ جارِ التحميل من YouTube...")
    audio_link = get_audio_link(url)
    if not audio_link:
        bot.reply_to(msg, "⚠️ فشل الحصول على رابط الصوت من الفيديو.")
        return
    try:
        r = requests.get(audio_link, stream=True, timeout=30)
        file_path = os.path.join(DOWNLOAD_DIR, "audio.mp3")
        with open(file_path, "wb") as f:
            for chunk in r.iter_content(1024 * 128):
                f.write(chunk)
        compressed = compress_audio(file_path)
        with open(compressed, "rb") as f:
            bot.send_audio(CHANNEL_ID, f, caption=f"🎶 {url}")
        bot.reply_to(msg, "✅ تم نشر الصوت بنجاح!")
        os.remove(file_path)
        if compressed != file_path:
            os.remove(compressed)
    except Exception as e:
        bot.reply_to(msg, f"⚠️ حدث خطأ أثناء المعالجة: {e}")

# Flask webhook
@server.route("/" + BOT_TOKEN, methods=["POST"])
def webhook_post():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "OK", 200

@server.route("/")
def set_webhook():
    bot.remove_webhook()
    bot.set_webhook(url="https://juzif-bot.onrender.com/" + BOT_TOKEN)
    return "Webhook set!", 200

if __name__ == "__main__":
    server.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
