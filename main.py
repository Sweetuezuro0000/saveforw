import os
import re
import asyncio
import subprocess
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait, RPCError
from aiohttp import web

# ----------------- CONFIGURATION -----------------
API_ID = int(os.environ.get("API_ID", "11271546"))
API_HASH = os.environ.get("API_HASH", "1f1f4621cde774fef16b39dd8274e982")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
OWNER_ID = int(os.environ.get("OWNER_ID", "5787360401"))

bot = Client("SaveForwBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# In-Memory Storage
user_data = {
    "session": None,
    "thumb": None,
    "caption": None,
    "remwords": [],
    "replace": {},
    "watermark": None
}

# ----------------- HEALTH CHECK SERVER FOR RENDER -----------------
async def handle_ping(request):
    return web.Response(text="Bot is running 24/7!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8088))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

# ----------------- LINK PARSER (TOPIC & PRIVATE SUPPORT) -----------------
def parse_telegram_link(link: str):
    # Matches:
    # 1. Private Topic: t.me/c/chat_id/topic_id/msg_id
    # 2. Private Standard: t.me/c/chat_id/msg_id
    # 3. Public Topic: t.me/channel/topic_id/msg_id
    # 4. Public Standard: t.me/channel/msg_id
    
    priv_topic = re.match(r"https?://t\.me/c/(\d+)/(\d+)/(\d+)", link)
    if priv_topic:
        return int("-100" + priv_topic.group(1)), int(priv_topic.group(3))
        
    priv_std = re.match(r"https?://t\.me/c/(\d+)/(\d+)", link)
    if priv_std:
        return int("-100" + priv_std.group(1)), int(priv_std.group(2))
        
    pub_topic = re.match(r"https?://t\.me/([^/]+)/(\d+)/(\d+)", link)
    if pub_topic:
        return pub_topic.group(1), int(pub_topic.group(3))
        
    pub_std = re.match(r"https?://t\.me/([^/]+)/(\d+)", link)
    if pub_std:
        return pub_std.group(1), int(pub_std.group(2))
        
    return None, None

# ----------------- CAPTION PROCESSOR -----------------
def process_caption(orig_caption: str) -> str:
    caption = orig_caption or ""
    
    # 1. Replace words
    for old, new in user_data["replace"].items():
        caption = caption.replace(old, new)
        
    # 2. Remove words
    for word in user_data["remwords"]:
        caption = caption.replace(word, "")
        
    # 3. Custom caption override
    if user_data["caption"]:
        caption = user_data["caption"]
        
    return caption.strip()

# ----------------- WATERMARK (ONLY FOR FILES <= 100MB) -----------------
def apply_watermark(input_path, output_path, text):
    if not text:
        return input_path
    
    file_size = os.path.getsize(input_path)
    # Strict Limit: 100 MB (100 * 1024 * 1024 bytes)
    if file_size > 100 * 1024 * 1024:
        return input_path
        
    ext = os.path.splitext(input_path)[1].lower()
    
    if ext in ['.mp4', '.mkv', '.avi', '.mov']:
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-vf", f"drawtext=text='{text}':x=(w-text_w)/2:y=h-th-30:fontsize=24:fontcolor=white:box=1:boxcolor=black@0.5",
            "-c:a", "copy", output_path
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return output_path if os.path.exists(output_path) else input_path

    return input_path

# ----------------- COMMAND HANDLERS -----------------
@bot.on_message(filters.command("start"))
async def start_cmd(client, message: Message):
    if message.from_user.id != OWNER_ID:
        return await message.reply("⚠️ Unauthorized user!")
    
    msg = (
        "🤖 **Save Restricted Content Bot Loaded!**\n\n"
        "**Commands List:**\n"
        "🔹 `/setsession <StringSession>` - Login for 4GB & Restricted files\n"
        "🔹 `/batch <link> <count>` - Extract up to 1000 files in 1 click\n"
        "🔹 `/setcaption <text>` / `/delcaption` - Manage Custom Caption\n"
        "🔹 `/remword <word>` - Remove specific words from caption\n"
        "🔹 `/replace <old> <new>` - Replace words in caption\n"
        "🔹 `/setthumb` - Reply to image to set Custom Thumbnail\n"
        "🔹 `/delthumb` - Remove Custom Thumbnail\n"
        "🔹 `/watermark <text>` - Watermark Video/PDF (Files <= 100MB only)\n"
        "🔹 `/logout` - Clear current session"
    )
    await message.reply(msg)

@bot.on_message(filters.command("setsession"))
async def set_session(client, message: Message):
    if message.from_user.id != OWNER_ID: return
    try:
        session_str = message.text.split(" ", 1)[1].strip()
        user_data["session"] = session_str
        await message.reply("✅ **Pyrogram String Session saved successfully!**")
    except IndexError:
        await message.reply("❌ **Usage:** `/setsession StringSessionHere`")
        
@bot.on_message(filters.command("setcaption"))
async def set_caption(client, message: Message):
    if message.from_user.id != OWNER_ID: return
    try:
        user_data["caption"] = message.text.split(" ", 1)[1]
        await message.reply("✅ **Custom Caption saved!**")
    except IndexError:
        await message.reply("❌ **Usage:** `/setcaption <your_caption_text>`")

@bot.on_message(filters.command("delcaption"))
async def del_caption(client, message: Message):
    if message.from_user.id != OWNER_ID: return
    user_data["caption"] = None
    await message.reply("🗑️ **Custom Caption removed.**")

@bot.on_message(filters.command("remword"))
async def rem_word(client, message: Message):
    if message.from_user.id != OWNER_ID: return
    try:
        word = message.text.split(" ", 1)[1]
        user_data["remwords"].append(word)
        await message.reply(f"✅ **Word '{word}' added to removal list.**")
    except IndexError:
        await message.reply("❌ **Usage:** `/remword <word_to_remove>`")

@bot.on_message(filters.command("replace"))
async def replace_word(client, message: Message):
    if message.from_user.id != OWNER_ID: return
    try:
        _, old_word, new_word = message.text.split(" ", 2)
        user_data["replace"][old_word] = new_word
        await message.reply(f"✅ **Replacement set:** `{old_word}` ➔ `{new_word}`")
    except ValueError:
        await message.reply("❌ **Usage:** `/replace <old_word> <new_word>`")

@bot.on_message(filters.command("setthumb"))
async def set_thumb(client, message: Message):
    if message.from_user.id != OWNER_ID: return
    if not message.reply_to_message or not message.reply_to_message.photo:
        return await message.reply("❌ Reply to a photo with `/setthumb` to set it.")
    
    path = await message.reply_to_message.download("./thumb.jpg")
    user_data["thumb"] = path
    await message.reply("✅ **Custom Thumbnail Saved!**")

@bot.on_message(filters.command("delthumb"))
async def del_thumb(client, message: Message):
    if message.from_user.id != OWNER_ID: return
    if user_data["thumb"] and os.path.exists(user_data["thumb"]):
        os.remove(user_data["thumb"])
    user_data["thumb"] = None
    await message.reply("🗑️ **Custom Thumbnail Removed.**")

@bot.on_message(filters.command("watermark"))
async def set_watermark(client, message: Message):
    if message.from_user.id != OWNER_ID: return
    try:
        user_data["watermark"] = message.text.split(" ", 1)[1]
        await message.reply(f"✅ **Watermark set to:** `{user_data['watermark']}`\n*(Note: Will apply only to files <= 100MB)*")
    except IndexError:
        user_data["watermark"] = None
        await message.reply("🗑️ **Watermark disabled.**")

# ----------------- BATCH PROCESSING CORE LOGIC -----------------
@bot.on_message(filters.command("batch"))
async def batch_process(client, message: Message):
    if message.from_user.id != OWNER_ID: return
    if not user_data["session"]:
        return await message.reply("❌ **Please set Pyrogram session first using `/setsession`**")
    
    args = message.text.split()
    if len(args) < 3:
        return await message.reply("❌ **Usage:** `/batch Link 500`\nExample: `/batch https://t.me/c/12345/10 500`")
        
    start_link = args[1]
    try:
        count = int(args[2])
    except ValueError:
        return await message.reply("❌ **Count must be a valid number.**")
        
    chat_id, start_msg_id = parse_telegram_link(start_link)
    if not chat_id or not start_msg_id:
        return await message.reply("❌ **Invalid Telegram Link/Topic Format!**")
        
    status_msg = await message.reply(f"⏳ **Starting Batch Processing ({count} items)...**")
    
    # Initialize User Session Client (Supports 4GB & Restricted files)
    user_app = Client("UserSession", api_id=API_ID, api_hash=API_HASH, session_string=user_data["session"])
    await user_app.start()
    
    success, failed = 0, 0
    
    for i in range(count):
        current_msg_id = start_msg_id + i
        try:
            msg = await user_app.get_messages(chat_id, current_msg_id)
            if not msg or msg.empty:
                failed += 1
                continue
                
            # If message is media (Video, PDF, APKG, HTML, Document, Photo, Audio)
            if msg.media:
                caption = process_caption(msg.caption)
                
                # Direct Server Copy Try (0% Load)
                try:
                    await msg.copy(message.chat.id, caption=caption)
                    success += 1
                    continue
                except RPCError:
                    pass # Fallback to download-upload if restricted
                    
                # Download File (Supports up to 4GB)
                dl_msg = await message.reply_text(f"⬇️ Downloading message `{current_msg_id}`...")
                file_path = await user_app.download_media(msg)
                await dl_msg.delete()
                
                if not file_path:
                    failed += 1
                    continue
                    
                # Apply Watermark (If <= 100MB)
                wm_path = file_path + "_wm.mp4"
                final_path = apply_watermark(file_path, wm_path, user_data["watermark"])
                
                # Thumbnail Setup
                thumb = user_data["thumb"] if user_data["thumb"] and os.path.exists(user_data["thumb"]) else None
                
                # Upload back to User Chat
                up_msg = await message.reply_text(f"⬆️ Uploading message `{current_msg_id}`...")
                await user_app.send_document(
                    chat_id=message.chat.id,
                    document=final_path,
                    caption=caption,
                    thumb=thumb
                )
                await up_msg.delete()
                
                # Cleanup temp files
                if os.path.exists(file_path): os.remove(file_path)
                if os.path.exists(wm_path): os.remove(wm_path)
                
                success += 1
            else:
                # Text message copy
                if msg.text:
                    await message.reply_text(process_caption(msg.text))
                    success += 1

        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception as e:
            failed += 1
            
        if (i + 1) % 10 == 0:
            await status_msg.edit_text(f"📊 **Progress:** `{i+1}/{count}`\n✅ **Success:** `{success}` | ❌ **Failed:** `{failed}`")
            
    await user_app.stop()
    await status_msg.edit_text(f"🏁 **Batch Completed!**\n✅ **Total Sent:** `{success}`\n❌ **Failed:** `{failed}`")

# ----------------- MAIN EXECUTION -----------------
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(start_web_server())
    bot.run()
