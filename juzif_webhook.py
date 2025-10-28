import os
import telebot
from flask import Flask, request
import requests
import subprocess
from io import BytesIO

BOT_TOKEN = "6219694069:AAGQ6J0nDTW-9jO4VNp2mZo9paZvwQMlk5E"
CHANNEL_ID = "-1003203955147"

bot = telebot.TeleBot(BOT_TOKEN)
server = Flask(__name__)

@bot.message_handler(commands=['start'])
def start(msg):
    bot.reply_to(msg, "🎧 أرسل لي رابط فيديو من YouTube وسأحوله إلى صوت مضغوط جدًا (≤ 3 ميجا).")

@bot.message_handler(func=lambda m: 'youtube.com' in m.text or 'youtu.be' in m.text)
def handle_youtube(msg):
    url = msg.text.strip()
    bot.reply_to(msg, "⏳ جارِ تحميل الصوت ومعالجته...")

    try:
        # جلب رابط الصوت من واجهة خارجية (بدون yt-dlp)
        api_url = f"https://api.vevioz.com/api/button/mp3/{url}"
        response = requests.get(api_url, timeout=20)
        response.raise_for_status()

        import re
        match = re.search(r'href="(https://.*?\.mp3)"', response.text)
        if not match:
            bot.reply_to(msg, "❌ لم أتمكن من الحصول على ملف الصوت، ربما الفيديو محظور أو خاص.")
            return

        audio_url = match.group(1)
        r = requests.get(audio_url, stream=True)
        temp_input = "input.mp3"
        temp_output = "output_low.mp3"

        with open(temp_input, "wb") as f:
            f.write(r.content)

        # تحويل الصوت إلى جودة منخفضة جداً باستخدام ffmpeg
        subprocess.run([
            "ffmpeg", "-y", "-i", temp_input,
            "-b:a", "16k",  # 16kbps
            "-ac", "1",     # قناة واحدة
            "-ar", "16000", # تردد منخفض
            temp_output
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # إرسال الصوت للقناة
        with open(temp_output, "rb") as f:
            bot.send_audio(CHANNEL_ID, f, caption=f"🎶 {url}")

        bot.reply_to(msg, "✅ تم تحميل الصوت وإرساله بنجاح 🎵")

        # تنظيف الملفات المؤقتة
        os.remove(temp_input)
        os.remove(temp_output)

    except Exception as e:
        bot.reply_to(msg, f"⚠️ حدث خطأ أثناء التحميل أو التحويل:\n{e}")

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
