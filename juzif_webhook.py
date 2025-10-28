#!/usr/bin/env python3
# juzif_compressor_ready.py
# Bot for Render: receives audio/video files, compresses them, posts to channel
# Author: prepared for Juzif
import os
import uuid
import shutil
import tempfile
import subprocess
from time import time
from flask import Flask, request
import telebot

# ------------------ Configuration (ENV first, fallback to provided values) ------------------
# It's safer to set BOT_TOKEN and CHANNEL_ID as environment variables in Render.
BOT_TOKEN = os.getenv("BOT_TOKEN") or "6219694069:AAGQ6J0nDTW-9jO4VNp2mZo9paZvwQMlk5E"
CHANNEL_ID = os.getenv("CHANNEL_ID") or "-1003203955147"
WEBHOOK_URL = os.getenv("WEBHOOK_URL") or "https://juzif-bot.onrender.com/" + BOT_TOKEN

if not BOT_TOKEN or not CHANNEL_ID:
    raise SystemExit("BOT_TOKEN and CHANNEL_ID must be provided via environment or in-file defaults.")

# ------------------ Init ------------------
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# pending dict for video items waiting for user choice
pending = {}  # token -> {"video": path, "audio": path, "orig": path, "title": str, "created": ts}

# ------------------ Helpers ------------------
def cleanup_pending(max_age_seconds=3600):
    """Remove pending items older than max_age_seconds and delete files."""
    now = time()
    for key, value in list(pending.items()):
        if now - value.get("created", 0) > max_age_seconds:
            try:
                base = os.path.dirname(value.get("orig", "")) or None
                if base and os.path.exists(base):
                    shutil.rmtree(base, ignore_errors=True)
            except Exception:
                pass
            pending.pop(key, None)

def file_size_mb(path):
    try:
        return os.path.getsize(path) / (1024.0*1024.0)
    except Exception:
        return 0.0

def ffmpeg_available():
    from shutil import which
    return which("ffmpeg") is not None

def download_telegram_file(file_id, dest_path):
    try:
        file_info = bot.get_file(file_id)
        data = bot.download_file(file_info.file_path)
        with open(dest_path, "wb") as f:
            f.write(data)
        return True
    except Exception as e:
        print("Download error:", e)
        return False

def run_ffmpeg_convert_to_audio(input_path, output_path, bitrate_k="16k", samplerate=16000, timeout=300):
    """Convert any input to low-bitrate mp3 (mono). Returns True if success."""
    if not ffmpeg_available():
        print("ffmpeg not available on system.")
        return False
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-ac", "1",
        "-ar", str(samplerate),
        "-b:a", str(bitrate_k),
        "-vn",
        output_path
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=timeout)
        return os.path.exists(output_path)
    except Exception as e:
        print("ffmpeg audio error:", e)
        return False

def run_ffmpeg_compress_video(input_path, output_path,
                              video_bitrate="200k", audio_bitrate="16k", scale_width=320, samplerate=16000, timeout=600):
    """Compress video to small resolution/bitrate. Returns True if success."""
    if not ffmpeg_available():
        print("ffmpeg not available on system.")
        return False
    vf = f"scale='min({scale_width},iw)':-2"
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-c:v", "libx264", "-preset", "veryfast",
        "-b:v", video_bitrate, "-maxrate", video_bitrate, "-bufsize", "2M",
        "-vf", vf,
        "-c:a", "aac", "-b:a", audio_bitrate, "-ac", "1", "-ar", str(samplerate),
        "-movflags", "+faststart",
        output_path
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=timeout)
        return os.path.exists(output_path)
    except Exception as e:
        print("ffmpeg video error:", e)
        return False

# ------------------ Bot handlers ------------------
@bot.message_handler(commands=["start"])
def cmd_start(m):
    bot.reply_to(m, "أرسل ملف صوتي أو فيديو. الصوت يُضغط وينشر فوراً، الفيديو يُضغط ثم تُختار نشره كفيديو أو كصوت.")

@bot.message_handler(content_types=['audio', 'voice', 'video', 'document', 'video_note'])
def handle_media(m):
    cleanup_pending()
    # determine file id and filename
    file_id = None
    filename = None
    mime = None
    content_type = m.content_type

    if content_type == 'audio':
        file_id = m.audio.file_id
        filename = m.audio.file_name or f"audio_{uuid.uuid4().hex}.ogg"
        mime = m.audio.mime_type
    elif content_type == 'voice':
        file_id = m.voice.file_id
        filename = f"voice_{uuid.uuid4().hex}.ogg"
        mime = "audio/ogg"
    elif content_type == 'video':
        file_id = m.video.file_id
        filename = m.video.file_name or f"video_{uuid.uuid4().hex}.mp4"
        mime = m.video.mime_type
    elif content_type == 'video_note':
        file_id = m.video_note.file_id
        filename = f"vidnote_{uuid.uuid4().hex}.mp4"
        mime = "video/mp4"
    elif content_type == 'document':
        file_id = m.document.file_id
        filename = m.document.file_name or f"file_{uuid.uuid4().hex}"
        mime = m.document.mime_type
    else:
        bot.reply_to(m, "نوع الملف غير مدعوم.")
        return

    bot.reply_to(m, "⏳ استلمت الملف، جاري ضغطه الآن... قد يستغرق بضع ثواني إلى دقائق حسب الحجم.")

    # create session dir
    session_dir = tempfile.mkdtemp(prefix="job_")
    orig_path = os.path.join(session_dir, filename)

    if not download_telegram_file(file_id, orig_path):
        bot.reply_to(m, "❌ فشل تنزيل الملف من تيليجرام.")
        shutil.rmtree(session_dir, ignore_errors=True)
        return

    title = os.path.splitext(filename)[0]
    is_audio = (content_type in ['audio', 'voice']) or (mime and mime.startswith("audio"))

    try:
        if is_audio:
            out_audio = os.path.join(session_dir, f"{title}_compressed.mp3")
            ok = run_ffmpeg_convert_to_audio(orig_path, out_audio, bitrate_k="16k", samplerate=16000)
            if not ok:
                bot.reply_to(m, "❌ فشل ضغط الملف الصوتي (ffmpeg ربما غير متاح).")
                shutil.rmtree(session_dir, ignore_errors=True)
                return
            size = file_size_mb(out_audio)
            # send to channel immediately
            with open(out_audio, "rb") as f:
                bot.send_audio(CHANNEL_ID, f, caption=f"🔊 {title} — مضغوط {size:.2f} MB", timeout=120)
            bot.reply_to(m, f"✅ تم ضغط الصوت ({size:.2f} MB) ونشره في القناة.")
            shutil.rmtree(session_dir, ignore_errors=True)
            return

        # For video (or other media) => produce compressed video and audio file, register pending token
        out_video = os.path.join(session_dir, f"{title}_compressed.mp4")
        out_audio_from_video = os.path.join(session_dir, f"{title}_audio.mp3")

        ok_video = run_ffmpeg_compress_video(orig_path, out_video, video_bitrate="200k", audio_bitrate="16k", scale_width=320)
        ok_audio = run_ffmpeg_convert_to_audio(orig_path, out_audio_from_video, bitrate_k="16k", samplerate=16000)

        token = uuid.uuid4().hex
        pending[token] = {
            "video": out_video if ok_video and os.path.exists(out_video) else None,
            "audio": out_audio_from_video if ok_audio and os.path.exists(out_audio_from_video) else None,
            "orig": orig_path,
            "title": title,
            "created": time()
        }

        # build message and buttons
        parts = [f"✅ الملف جاهز: {title}"]
        if pending[token]["video"]:
            parts.append(f"🔹 فيديو مضغوط ~ {file_size_mb(pending[token]['video']):.2f} MB")
        else:
            parts.append("⚠️ لم يتم إنشاء فيديو مضغوط صالح.")

        if pending[token]["audio"]:
            parts.append(f"🔹 صوت مضغوط ~ {file_size_mb(pending[token]['audio']):.2f} MB")
        else:
            parts.append("⚠️ لم يتم إنشاء صوت من الفيديو.")

        from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup()
        if pending[token]["video"]:
            kb.add(InlineKeyboardButton("📤 نشر كفيديو مضغوط", callback_data=f"post:video:{token}"))
        if pending[token]["audio"]:
            kb.add(InlineKeyboardButton("🎧 نشر كصوت مضغوط", callback_data=f"post:audio:{token}"))
        kb.add(InlineKeyboardButton("🗑️ إلغاء وحذف", callback_data=f"cancel:{token}"))

        bot.reply_to(m, "\n".join(parts), reply_markup=kb)

    except Exception as e:
        print("Processing error:", e)
        bot.reply_to(m, f"❌ حدث خطأ أثناء المعالجة: {e}")
        shutil.rmtree(session_dir, ignore_errors=True)
        pending.pop(token, None)

# ------------------ Callback handler ------------------
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    data = call.data
    try:
        action, typ, token = data.split(":")
    except Exception:
        bot.answer_callback_query(call.id, "بيانات غير مفهومة.")
        return

    entry = pending.get(token)
    if not entry:
        bot.answer_callback_query(call.id, "انتهت صلاحية هذا الطلب أو تم حذفه.")
        return

    try:
        if action == "post" and typ == "video":
            if not entry.get("video") or not os.path.exists(entry["video"]):
                bot.answer_callback_query(call.id, "لا يوجد ملف فيديو صالح للنشر.")
                return
            with open(entry["video"], "rb") as f:
                bot.send_video(CHANNEL_ID, f, caption=f"🎬 {entry.get('title')}", timeout=300)
            bot.edit_message_text("✅ تم نشر الفيديو المضغوط في القناة.", call.message.chat.id, call.message.message_id)
            bot.answer_callback_query(call.id, "تم النشر كفيديو.")
        elif action == "post" and typ == "audio":
            if not entry.get("audio") or not os.path.exists(entry["audio"]):
                bot.answer_callback_query(call.id, "لا يوجد ملف صوت صالح للنشر.")
                return
            with open(entry["audio"], "rb") as f:
                bot.send_audio(CHANNEL_ID, f, caption=f"🔊 {entry.get('title')}", timeout=300)
            bot.edit_message_text("✅ تم نشر الملف كصوت مضغوط في القناة.", call.message.chat.id, call.message.message_id)
            bot.answer_callback_query(call.id, "تم النشر كصوت.")
        elif action == "cancel":
            bot.edit_message_text("🗑️ تم الإلغاء وحذف الملفات.", call.message.chat.id, call.message.message_id)
            bot.answer_callback_query(call.id, "تم الإلغاء.")
        # cleanup files & pending
        base_dir = os.path.dirname(entry.get("orig")) if entry.get("orig") else None
        if base_dir and os.path.exists(base_dir):
            shutil.rmtree(base_dir, ignore_errors=True)
        pending.pop(token, None)
    except Exception as e:
        print("Callback handling error:", e)
        bot.answer_callback_query(call.id, f"حدث خطأ: {e}")

# ------------------ Webhook routes ------------------
@app.route("/" + BOT_TOKEN, methods=["POST"])
def webhook_receiver():
    try:
        update = request.get_data().decode("utf-8")
        bot.process_new_updates([telebot.types.Update.de_json(update)])
    except Exception as e:
        print("Webhook processing error:", e)
    return "OK", 200

@app.route("/", methods=["GET"])
def index():
    # try to set webhook automatically if WEBHOOK_URL provided
    try:
        bot.remove_webhook()
        bot.set_webhook(url=WEBHOOK_URL)
        return f"Webhook set to {WEBHOOK_URL}", 200
    except Exception as e:
        print("Set webhook error:", e)
        return f"Webhook set error: {e}", 500

# ------------------ Run Flask ------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
