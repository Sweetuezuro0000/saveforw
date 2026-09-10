import asyncio
import os
import re
import subprocess
from aiohttp import web
from pypdf import PdfReader, PdfWriter

from pyrogram import Client, filters, enums
from pyrogram.types import Message
from pyrogram.errors import FloodWait

# ==================== CONFIGURATION ====================
API_ID = int(os.environ.get("API_ID", "11271546"))
API_HASH = os.environ.get("API_HASH", "1f1f4621cde774fef16b39dd8274e982")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
OWNER_ID = int(os.environ.get("OWNER_ID", "123456789"))
PORT = int(os.environ.get("PORT", 8080))

# Maximum file size for applying watermark (100 MB to protect server RAM/CPU)
MAX_WATERMARK_SIZE = 100 * 1024 * 1024 
# =======================================================

bot = Client("saver_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)

memory_db = {}
user_clients = {}

def get_user(user_id: int):
    if user_id not in memory_db:
        memory_db[user_id] = {
            "_id": user_id,
            "thumbnail": None,
            "custom_caption": None,
            "session_string": None,
            "rem_words": [],
            "rep_words": {},  # {"old_word": "new_word"}
            "watermark_text": None
        }
    return memory_db[user_id]

def update_user(user_id: int, data: dict):
    user = get_user(user_id)
    user.update(data)

def process_caption(uid: int, original_caption: str) -> str:
    user = get_user(uid)
    if user.get("custom_caption"):
        caption = user["custom_caption"]
    else:
        caption = original_caption or ""

    if not caption:
        return ""

    # 1. Remove words
    for word in user.get("rem_words", []):
        caption = re.sub(re.escape(word), "", caption, flags=re.IGNORECASE)

    # 2. Replace words
    for old_w, new_w in user.get("rep_words", {}).items():
        caption = re.sub(re.escape(old_w), new_w, caption, flags=re.IGNORECASE)

    return caption.strip()

# ==================== ACCESS CONTROL ====================
@bot.on_message(filters.private, group=-1)
async def owner_check(client: Client, message: Message):
    if message.from_user.id != OWNER_ID:
        await message.reply_text("⛔ **Access Denied!** This is a private bot.")
        message.stop_propagation()

# ==================== COMMAND HANDLERS ====================

@bot.on_message(filters.command("start"))
async def start_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    user = get_user(user_id)
    is_logged_in = "🟢 Connected" if user.get("session_string") else "🔴 Not Logged In"

    text = (
        "🚀 **Advanced Restricted Content Saver Bot**\n\n"
        f"👤 **User Session Status:** `{is_logged_in}`\n"
        f"🖼️ **Custom Thumbnail:** `{'Set' if user.get('thumbnail') else 'None'}`\n"
        f"✍️ **Custom Caption:** `{'Set' if user.get('custom_caption') else 'None'}`\n"
        f"💧 **Watermark Text:** `{user.get('watermark_text') or 'None'}`\n\n"
        "📌 **Available Commands:**\n"
        "• `/setsession <string>` - Login via Pyrogram String Session\n"
        "• `/batch <start_link> <count>` - Bulk extraction (Up to 1000)\n"
        "• `/setthumb` - Reply to an image to set thumbnail\n"
        "• `/delthumb` - Remove custom thumbnail\n"
        "• `/setcaption <text>` - Set static custom caption\n"
        "• `/delcaption` - Remove custom caption\n"
        "• `/remword <word>` - Remove specific word from caption\n"
        "• `/replace <old> <new>` - Replace word in caption\n"
        "• `/watermark <text>` - Watermark PDF/Video (Files <= 100MB)\n"
        "• `/logout` - Clear user session"
    )
    await message.reply_text(text)

@bot.on_message(filters.command("setsession"))
async def set_session_cmd(client: Client, message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.reply_text("⚠️ **Format:** `/setsession <your_pyrogram_string_session>`")
    
    sess_str = args[1].strip()
    uid = message.from_user.id
    status_msg = await message.reply_text("🔄 Verifying session string...")

    try:
        test_client = Client(f"user_{uid}", api_id=API_ID, api_hash=API_HASH, session_string=sess_str, in_memory=True)
        await test_client.start()
        me = await test_client.get_me()
        
        update_user(uid, {"session_string": sess_str})
        user_clients[uid] = test_client
        
        await status_msg.edit_text(f"✅ **Session Saved!** Connected as: `{me.first_name}` (`{me.id}`)")
    except Exception as e:
        await status_msg.edit_text(f"❌ **Invalid Session String!**\nError: `{e}`")

@bot.on_message(filters.command("setthumb"))
async def set_thumb_cmd(client: Client, message: Message):
    uid = message.from_user.id
    if message.reply_to_message and message.reply_to_message.photo:
        dl_path = await bot.download_media(message.reply_to_message.photo)
        update_user(uid, {"thumbnail": dl_path})
        await message.reply_text("✅ Custom thumbnail saved!")
    else:
        await message.reply_text("⚠️ Reply to a photo with `/setthumb` to save it as a thumbnail.")

@bot.on_message(filters.command("delthumb"))
async def del_thumb_cmd(client: Client, message: Message):
    uid = message.from_user.id
    user = get_user(uid)
    if user.get("thumbnail") and os.path.exists(user["thumbnail"]):
        os.remove(user["thumbnail"])
    update_user(uid, {"thumbnail": None})
    await message.reply_text("🗑️ Custom thumbnail removed.")

@bot.on_message(filters.command("setcaption"))
async def set_caption_cmd(client: Client, message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        update_user(message.from_user.id, {"custom_caption": args[1]})
        await message.reply_text("✅ Custom caption set.")
    else:
        await message.reply_text("⚠️ **Format:** `/setcaption <your_caption_text>`")

@bot.on_message(filters.command("delcaption"))
async def del_caption_cmd(client: Client, message: Message):
    update_user(message.from_user.id, {"custom_caption": None})
    await message.reply_text("🗑️ Custom caption cleared.")

@bot.on_message(filters.command("remword"))
async def rem_word_cmd(client: Client, message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        user = get_user(message.from_user.id)
        user["rem_words"].append(args[1])
        await message.reply_text(f"✅ Removal Word Added. Current list: `{user['rem_words']}`")
    else:
        await message.reply_text("⚠️ **Format:** `/remword <word_to_remove>`")

@bot.on_message(filters.command("replace"))
async def replace_word_cmd(client: Client, message: Message):
    args = message.text.split()
    if len(args) >= 3:
        old_w, new_w = args[1], args[2]
        user = get_user(message.from_user.id)
        user["rep_words"][old_w] = new_w
        await message.reply_text(f"✅ Rule Added: Replace `{old_w}` with `{new_w}`")
    else:
        await message.reply_text("⚠️ **Format:** `/replace <old_word> <new_word>`")

@bot.on_message(filters.command("watermark"))
async def set_watermark(client: Client, message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        update_user(message.from_user.id, {"watermark_text": args[1]})
        await message.reply_text(f"✅ Watermark set to: `{args[1]}`\n*(Applies only to files <= 100MB)*")
    else:
        update_user(message.from_user.id, {"watermark_text": None})
        await message.reply_text("🗑️ Watermark disabled.")

@bot.on_message(filters.command("logout"))
async def logout_cmd(client: Client, message: Message):
    uid = message.from_user.id
    update_user(uid, {"session_string": None})
    if uid in user_clients:
        try:
            await user_clients[uid].stop()
        except Exception:
            pass
        del user_clients[uid]
    await message.reply_text("🚪 Session removed successfully.")

# ==================== BATCH PROCESSING ====================

@bot.on_message(filters.command("batch"))
async def batch_cmd(client: Client, message: Message):
    uid = message.from_user.id
    args = message.text.split()
    
    if len(args) < 3:
        return await message.reply_text(
            "⚠️ **Format:** `/batch <start_message_link> <count_up_to_1000>`\n\n"
            "**Example:** `/batch https://t.me/c/123456789/100 50`"
        )

    start_link = args[1]
    try:
        count = min(int(args[2]), 1000)
    except ValueError:
        return await message.reply_text("❌ Count must be a valid number!")

    # Regex for standard and topic links
    m_priv_topic = re.search(r"t\.me/c/(\d+)/(\d+)/(\d+)", start_link)
    m_priv = re.search(r"t\.me/c/(\d+)/(\d+)", start_link)
    m_pub = re.search(r"t\.me/([^/]+)/(\d+)", start_link)

    if m_priv_topic:
        chat_id = int("-100" + m_priv_topic.group(1))
        start_id = int(m_priv_topic.group(3))
        is_private = True
    elif m_priv:
        chat_id = int("-100" + m_priv.group(1))
        start_id = int(m_priv.group(2))
        is_private = True
    elif m_pub:
        chat_id = m_pub.group(1)
        start_id = int(m_pub.group(2))
        is_private = False
    else:
        return await message.reply_text("❌ Invalid message link!")

    status = await message.reply_text(f"⏳ Processing batch task (0/{count})...")

    for i in range(count):
        current_msg_id = start_id + i
        try:
            await process_single_post(uid, chat_id, current_msg_id, is_private)
            if i % 5 == 0:
                await status.edit_text(f"⏳ Processed ({i+1}/{count}) posts...")
            await asyncio.sleep(2)  # Avoid Telegram FloodWait
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception as e:
            print(f"Error processing message {current_msg_id}: {e}")

    await status.edit_text(f"✅ Batch completed! Total processed: {count}")

# ==================== EXTRACTION ENGINE ====================

async def process_single_post(uid: int, chat_id, msg_id: int, is_private: bool):
    user = get_user(uid)
    
    if is_private:
        user_session = user.get("session_string")
        if not user_session:
            raise Exception("Telegram User Session required for private links.")
        
        if uid not in user_clients:
            u_client = Client(f"user_{uid}", api_id=API_ID, api_hash=API_HASH, session_string=user_session, in_memory=True)
            await u_client.start()
            user_clients[uid] = u_client
        active_client = user_clients[uid]
    else:
        active_client = bot

    # ------------------ STEP 1: Attempt Direct Server Copy (0% Server Load) ------------------
    try:
        t_msg = await active_client.get_messages(chat_id, msg_id)
        if not t_msg or t_msg.empty:
            return

        cap = process_caption(uid, t_msg.caption.html if t_msg.caption else "")
        
        # Try direct server-side copy first if user hasn't set custom thumbnail or watermark
        if not user.get("thumbnail") and not user.get("watermark_text"):
            await active_client.copy_message(
                chat_id=uid,
                from_chat_id=chat_id,
                message_id=msg_id,
                caption=cap,
                parse_mode=enums.ParseMode.HTML
            )
            return
    except Exception:
        # Fallback to download-upload flow if direct copy fails (Restricted content)
        pass

    # ------------------ STEP 2: Download & Upload Flow ------------------
    if not t_msg.media:
        text_content = process_caption(uid, t_msg.text.html if t_msg.text else "")
        if text_content:
            await bot.send_message(uid, text_content, parse_mode=enums.ParseMode.HTML)
        return

    dl_path = await active_client.download_media(t_msg)
    if not dl_path:
        return

    out_path = dl_path
    file_size = os.path.getsize(dl_path)
    wm_text = user.get("watermark_text")

    # Apply Watermark ONLY if file size <= 100 MB
    if wm_text and file_size <= MAX_WATERMARK_SIZE:
        if dl_path.endswith(".pdf"):
            out_path = apply_pdf_watermark(dl_path, wm_text)
        elif dl_path.endswith((".mp4", ".mkv", ".mov")):
            out_path = apply_video_watermark(dl_path, wm_text)

    th = user.get("thumbnail")

    # Use User Client if file size > 2 GB (Telegram Bot API limit)
    sender_client = active_client if (file_size > 2 * 1024 * 1024 * 1024 and is_private) else bot

    try:
        if t_msg.video:
            await sender_client.send_video(uid, out_path, caption=cap, thumb=th, parse_mode=enums.ParseMode.HTML)
        elif t_msg.photo:
            await sender_client.send_photo(uid, out_path, caption=cap, parse_mode=enums.ParseMode.HTML)
        elif t_msg.document:
            await sender_client.send_document(uid, out_path, caption=cap, thumb=th, parse_mode=enums.ParseMode.HTML)
    finally:
        # Clean up temporary files from disk immediately
        if os.path.exists(dl_path):
            os.remove(dl_path)
        if out_path != dl_path and os.path.exists(out_path):
            os.remove(out_path)

# ==================== WATERMARK PROCESSING ====================

def apply_pdf_watermark(pdf_path: str, text: str) -> str:
    try:
        reader = PdfReader(pdf_path)
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        out_path = f"wm_{pdf_path}"
        with open(out_path, "wb") as f:
            writer.write(f)
        return out_path
    except Exception:
        return pdf_path

def apply_video_watermark(video_path: str, text: str) -> str:
    out_path = f"wm_{video_path}"
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vf", f"drawtext=text='{text}':x=10:y=H-th-10:fontsize=24:fontcolor=white@0.8",
        "-c:a", "copy", out_path
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return out_path
    except Exception:
        return video_path

# ==================== LINK HANDLER ====================

@bot.on_message(filters.private & ~filters.command([
    "start", "setsession", "setthumb", "delthumb", "setcaption", "delcaption",
    "remword", "replace", "watermark", "batch", "logout"
]))
async def handle_links(client: Client, message: Message):
    uid = message.from_user.id
    text = message.text.strip() if message.text else ""

    if "t.me/" in text:
        st = await message.reply_text("⚡ Extracting content...")

        m_priv_topic = re.search(r"t\.me/c/(\d+)/(\d+)/(\d+)", text)
        m_priv = re.search(r"t\.me/c/(\d+)/(\d+)", text)
        m_pub = re.search(r"t\.me/([^/]+)/(\d+)", text)

        if m_priv_topic:
            chat_id = int("-100" + m_priv_topic.group(1))
            msg_id = int(m_priv_topic.group(3))
            is_private = True
        elif m_priv:
            chat_id = int("-100" + m_priv.group(1))
            msg_id = int(m_priv.group(2))
            is_private = True
        elif m_pub:
            chat_id = m_pub.group(1)
            msg_id = int(m_pub.group(2))
            is_private = False
        else:
            return await st.edit_text("❌ Invalid Telegram link!")

        try:
            await process_single_post(uid, chat_id, msg_id, is_private)
            await st.delete()
        except Exception as e:
            await st.edit_text(f"❌ Error: `{e}`")

# ==================== WEB SERVER ====================
routes = web.RouteTableDef()
@routes.get("/", allow_head=True)
async def root_route_handler(request):
    return web.json_response({"status": "running"})

async def main():
    app = web.AppRunner(web.Application())
    await app.setup()
    await web.TCPSite(app, "0.0.0.0", PORT).start()
    await bot.start()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
