#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import tempfile
import shutil
import threading
from urllib.parse import urlparse
from flask import Flask, request
import telebot
import yt_dlp

# --------- الإعدادات (تُضبط كمتغيرات بيئة في Render) ----------
BOT_TOKEN = os.getenv("BOT_TOKEN")            # ضع توكن البوت في Environment
TARGET_CHAT = os.getenv("TARGET_CHAT")        # مثال: "@mychannel" أو "-1001234567890"
WORKDIR = os.getenv("WORKDIR", "tmp_audio")
MAX_SIZE_MB = float(os.getenv("MAX_SIZE_MB", "2.0"))  # الهدف: ≤2 ميغا
ABR_LIST = [32, 24, 16, 8]  # محاولات معدل البت (kbps) للتقليل بالحجم

if not BOT_TOKEN or not TARGET_CHAT:
    raise SystemExit("Environment variables BOT_TOKEN and TARGET_CHAT must be set.")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# ---------- مساعدة ملفات ----------
def ensure_dir(path):
    os.makedirs(path, exist_ok=True)

def cleanup_dir(path):
    try:
        shutil.rmtree(path)
    except Exception:
        pass

def file_size_mb(path):
    try:
        return os.path.getsize(path) / (1024*1024)
    except Exception:
        return 9999.0

def safe_fname_from_url(url):
    p = urlparse(url)
    return os.path.basename(p.path) or "file"

# ---------- تحميل الصوت بجودة منخفضة (بدون ffmpeg) ----------
def download_with_abr(url, out_dir, abr_kbps):
    """
    يحاول yt-dlp تحميل صوت بصيغة m4a أو ما هو متاح وبمعدل بیت محدد قدر الإمكان.
    يعيد (filepath, title) أو (None, None)
    """
    # نحدد فورمات يطلب أفضل صوت بحد أقصى للـ abr إن أمكن
    format_selector = f"bestaudio[abr<={abr_kbps}][ext=m4a]/bestaudio/best"
    ydl_opts = {
        "format": format_selector,
        "outtmpl": os.path.join(out_dir, "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        # لا نستخدم postprocessors لأننا نريد تجنب اعتمادية ffmpeg
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            vid = info.get("id")
            title = info.get("title") or vid
            # نحاول إيجاد الملف الذي حفظه yt-dlp
            possible = []
            for f in os.listdir(out_dir):
                if f.startswith(vid):
                    possible.append(os.path.join(out_dir, f))
            if not possible:
                return None, None
            # اختَر الملف الأكبر احتمالاً به الصوت المطلوب أو الأول
            filepath = possible[0]
            return filepath, title
    except Exception as e:
        # طبع الخطأ في اللوق، لكن لا نوقف البوت
        print("yt-dlp error (abr={}): {}".format(abr_kbps, e))
        return None, None

def get_small_audio(url, session_dir):
    """
    يحاول تنزيل الملف بمعدلات bitrates مختلفة حتى يصبح حجمه ≤ MAX_SIZE_MB.
    يرجع (path, title) أو (None, None)
    """
    # نجرّب ABR_LIST تنازليًا
    for abr in ABR_LIST:
        fp, title = download_with_abr(url, session_dir, abr)
        if not fp:
            continue
        size = file_size_mb(fp)
        print(f"Downloaded abr<={abr} => {size:.2f} MB -> {fp}")
        if size <= MAX_SIZE_MB:
            return fp, title
        # لو الملف أكبر، نحاول تقليل أكثر (نجرب abr أدنى في الدورة القادمة)
        # نحافظ على أصغر ملف واجده كي نعود له إذا لم نصل للحد المطلوب
    # لو لم ننجح بجعل الملف ≤MAX_SIZE_MB، سنعيد أصغر ملف وجدناه
    files = [os.path.join(session_dir, f) for f in os.listdir(session_dir)]
    if not files:
        return None, None
    smallest = min(files, key=lambda p: os.path.getsize(p))
    return smallest, title if 'title' in locals() else "audio"

# ---------- منطق المعالجة والرفع ----------
def process_and_send(chat_id, message_id, url):
    """
    دالة تستدعى داخل Thread لمعالجة الرابط دون حجب السيرفر.
    """
    ensure_dir(WORKDIR)
    session_dir = tempfile.mkdtemp(dir=WORKDIR, prefix="job_")
    try:
        # رسالة رد للمستخدم (نستخدم send_message للتقليل من مشاكل التعديل)
        try:
            bot.send_message(chat_id, "⏳ جاري تحميل الصوت مع محاولة تقليل الحجم (بدون ffmpeg)...")
        except Exception:
            pass

        path, title = get_small_audio(url, session_dir)
        if not path:
            try:
                bot.send_message(chat_id, "❌ فشل تحميل الصوت من الرابط. جرّب رابطاً آخر.")
            except Exception:
                pass
            return

        size = file_size_mb(path)
        # إرسال المعلومة للمستخدم
        try:
            bot.send_message(chat_id, f"✅ تم تجهيز الملف: {title}\nالحجم: {size:.2f} MB\nجارٍ الرفع للقناة...")
        except Exception:
            pass

        # رُفع للصقحة الهدف (قناتك)
        try:
            with open(path, "rb") as f:
                bot.send_audio(TARGET_CHAT, f, caption=f"🎧 {title}\nمضغوط لأجل الحجم الصغير", title=title, performer="YouTube", timeout=600)
            bot.send_message(chat_id, "✅ تم نشر المقطع في القناة.")
        except Exception as e:
            print("Upload error:", e)
            try:
                bot.send_message(chat_id, f"❌ فشل رفع الملف إلى القناة: {e}")
            except Exception:
                pass

    finally:
        cleanup_dir(session_dir)

# ---------- مسارات Flask للتعامل مع Telegram webhook ----------
@app.route("/", methods=["GET"])
def index():
    return "Juzif bot webhook is running."

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def telegram_webhook():
    """
    Telegram سيرسل POST إلى هذا المسار. نقوم بتحويل JSON إلى Update ومعالجتها.
    """
    try:
        json_str = request.get_data().decode("utf-8")
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
    except Exception as e:
        print("Failed to process update:", e)
    return "OK", 200

# ---------- handlers البوت ----------
@bot.message_handler(commands=["start"])
def handle_start(msg):
    bot.reply_to(msg, "مرحباً! أرسل رابط YouTube وسأحاول تحويله إلى ملف صوتي صغير الحجم ونشره في القناة.")

@bot.message_handler(func=lambda m: m.text and ("youtube.com" in m.text or "youtu.be" in m.text))
def handle_youtube(msg):
    url = msg.text.strip()
    # شغّل المعالجة في Thread
    threading.Thread(target=process_and_send, args=(msg.chat.id, msg.message_id, url), daemon=True).start()
    # نردّ فوراً للمستخدم بأن الطلب قيد المعالجة
    try:
        bot.reply_to(msg, "تم استلام الرابط — سيتم معالجته وإعلامك عند الانتهاء.")
    except Exception:
        pass

# ---------- لا نقوم بضبط webhook هنا تلقائياً (سنفعل عبر curl بعد النشر) ----------
if __name__ == "__main__":
    ensure_dir(WORKDIR)
    # شغّل Flask (Render يعطي PORT عبر متغير البيئة PORT)
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
