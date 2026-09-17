import os
import re
import asyncio
from pyrogram import Client, filters, idle, enums
from pyrogram.types import Message
from pyrogram.errors import FloodWait, ChatForwardsRestricted, RPCError
from aiohttp import web

# ----------------- CONFIG -----------------
API_ID = int(os.environ.get("API_ID", "11271546"))
API_HASH = os.environ.get("API_HASH", "1f1f4621cde774fef16b39dd8274e982")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

bot = Client("SaveForwBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)

user_data = {
    "session": None,
    "caption": None,
    "remwords": [],
    "replace": {},
    "target_chat": None,
    "target_topic": None
}

# ----------------- HEALTH CHECK SERVER -----------------
async def handle_ping(request):
    return web.Response(text="Bot is Alive!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Web Server started on port {port}")

# ----------------- LINK PARSERS -----------------
def parse_source_link(link: str):
    m_topic = re.match(r"https?://t\.me/c/(\d+)/(\d+)/(\d+)", link)
    if m_topic: return int("-100" + m_topic.group(1)), int(m_topic.group(3))
    m_priv = re.match(r"https?://t\.me/c/(\d+)/(\d+)", link)
    if m_priv: return int("-100" + m_priv.group(1)), int(m_priv.group(2))
    m_pub = re.match(r"https?://t\.me/([^/]+)/(\d+)", link)
    if m_pub: return m_pub.group(1), int(m_pub.group(2))
    return None, None

def parse_target_link(link: str):
    m_topic = re.match(r"https?://t\.me/c/(\d+)/(\d+)/(\d+)", link)
    if m_topic: return int("-100" + m_topic.group(1)), int(m_topic.group(2))
    m_std = re.match(r"https?://t\.me/c/(\d+)/(\d+)", link)
    if m_std: return int("-100" + m_std.group(1)), None
    m_pub = re.match(r"https?://t\.me/([^/]+)", link)
    if m_pub: return m_pub.group(1), None
    return None, None

def process_caption(orig_caption: str) -> str:
    caption = orig_caption or ""
    for old, new in user_data["replace"].items(): caption = caption.replace(old, new)
    for word in user_data["remwords"]: caption = caption.replace(word, "")
    if user_data["caption"]: caption = user_data["caption"]
    return caption.strip()

# ----------------- COMMANDS -----------------
@bot.on_message(filters.command("start"))
async def start_cmd(client, message: Message):
    text = (
        "⚡ Bot Active on Render!\n\n"
        "🔹 /setsession [StringSession]\n"
        "🔹 /settarget [Link]\n"
        "🔹 /deltarget\n"
        "🔹 /batch [link] [count]\n"
        "🔹 /setcaption [text] | /delcaption\n"
        "🔹 /remword [word] | /replace [old] [new]"
    )
    await message.reply(text, parse_mode=enums.ParseMode.DISABLED)

@bot.on_message(filters.command("setsession"))
async def set_session(client, message: Message):
    try:
        user_data["session"] = message.text.split(" ", 1)[1].strip()
        await message.reply("✅ Session Saved!")
    except IndexError:
        await message.reply("❌ Usage: `/setsession [StringSession]`", parse_mode=enums.ParseMode.DISABLED)

@bot.on_message(filters.command("settarget"))
async def set_target_topic(client, message: Message):
    try:
        link = message.text.split(" ", 1)[1].strip()
        chat_id, topic_id = parse_target_link(link)
        if not chat_id: return await message.reply("❌ Invalid Target Link!")
        user_data["target_chat"], user_data["target_topic"] = chat_id, topic_id
        await message.reply(f"🎯 Target Saved! Chat: {chat_id} | Topic: {topic_id}", parse_mode=enums.ParseMode.DISABLED)
    except IndexError:
        await message.reply("❌ Usage: `/settarget [Link]`", parse_mode=enums.ParseMode.DISABLED)

@bot.on_message(filters.command("deltarget"))
async def del_target_topic(client, message: Message):
    user_data["target_chat"], user_data["target_topic"] = None, None
    await message.reply("🗑️ Target Reset to DM!")

@bot.on_message(filters.command("setcaption"))
async def set_caption(client, message: Message):
    try:
        user_data["caption"] = message.text.split(" ", 1)[1]
        await message.reply("✅ Custom Caption Saved!")
    except IndexError:
        await message.reply("❌ Usage: `/setcaption [text]`", parse_mode=enums.ParseMode.DISABLED)

@bot.on_message(filters.command("delcaption"))
async def del_caption(client, message: Message):
    user_data["caption"] = None
    await message.reply("🗑️ Custom Caption Removed!")

@bot.on_message(filters.command("remword"))
async def rem_word(client, message: Message):
    try:
        word = message.text.split(" ", 1)[1]
        user_data["remwords"].append(word)
        await message.reply(f"✅ Word Removed: {word}", parse_mode=enums.ParseMode.DISABLED)
    except IndexError:
        await message.reply("❌ Usage: `/remword [word]`", parse_mode=enums.ParseMode.DISABLED)

@bot.on_message(filters.command("replace"))
async def replace_word(client, message: Message):
    try:
        _, old_word, new_word = message.text.split(" ", 2)
        user_data["replace"][old_word] = new_word
        await message.reply(f"✅ Replacement Saved: {old_word} ➔ {new_word}", parse_mode=enums.ParseMode.DISABLED)
    except ValueError:
        await message.reply("❌ Usage: `/replace [old] [new]`", parse_mode=enums.ParseMode.DISABLED)

# ----------------- BATCH LOGIC -----------------
@bot.on_message(filters.command("batch"))
async def batch_process(client: Client, message: Message):
    if not user_data["session"]: return await message.reply("❌ Set session first via `/setsession`!")
    args = message.text.split()
    if len(args) < 3: return await message.reply("❌ Usage: `/batch [link] [count]`", parse_mode=enums.ParseMode.DISABLED)
    
    start_link, count = args[1], int(args[2])
    chat_id, start_msg_id = parse_source_link(start_link)
    if not chat_id or not start_msg_id: return await message.reply("❌ Invalid Source Link!")

    status_msg = await message.reply("⏳ Connecting User Session & Fetching Dialogs...")
    user_app = Client("UserSession", api_id=API_ID, api_hash=API_HASH, session_string=user_data["session"], in_memory=True)
    
    try:
        await user_app.start()
        # 🔥 PRIVATE CHANNEL FIX: Populate peer cache in memory
        async for _ in user_app.get_dialogs(limit=200):
            pass
    except Exception as e:
        return await status_msg.edit_text(f"❌ Session Error: {e}", parse_mode=enums.ParseMode.DISABLED)

    dest_chat = user_data["target_chat"] or message.chat.id
    dest_topic = user_data["target_topic"] if user_data["target_chat"] else None

    await status_msg.edit_text(f"🚀 Processing ({count} items)...")

    success, failed = 0, 0
    for i in range(count):
        msg_id = start_msg_id + i
        try:
            msg = await user_app.get_messages(chat_id, msg_id)
            if not msg or msg.empty:
                failed += 1
                continue
            
            caption = process_caption(msg.caption or msg.text)
            kwargs = {"chat_id": dest_chat}
            if dest_topic: kwargs["reply_to_message_id"] = dest_topic

            try:
                if msg.media:
                    await msg.copy(**kwargs, caption=caption, parse_mode=enums.ParseMode.DISABLED)
                elif msg.text:
                    await user_app.send_message(**kwargs, text=caption, parse_mode=enums.ParseMode.DISABLED)
                success += 1
            except (ChatForwardsRestricted, RPCError):
                file_path = None
                try:
                    if msg.media:
                        file_path = await user_app.download_media(msg)
                        if file_path and os.path.exists(file_path):
                            if msg.video:
                                await bot.send_video(video=file_path, duration=msg.video.duration or 0, width=msg.video.width or 0, height=msg.video.height or 0, supports_streaming=True, caption=caption, parse_mode=enums.ParseMode.DISABLED, **kwargs)
                            elif msg.photo:
                                await bot.send_photo(photo=file_path, caption=caption, parse_mode=enums.ParseMode.DISABLED, **kwargs)
                            elif msg.document:
                                await bot.send_document(document=file_path, caption=caption, parse_mode=enums.ParseMode.DISABLED, **kwargs)
                            elif msg.audio:
                                await bot.send_audio(audio=file_path, duration=msg.audio.duration or 0, caption=caption, parse_mode=enums.ParseMode.DISABLED, **kwargs)
                            success += 1
                    elif msg.text:
                        await bot.send_message(text=caption, parse_mode=enums.ParseMode.DISABLED, **kwargs)
                        success += 1
                except Exception as ex:
                    print(f"Fallback Exception: {ex}")
                    failed += 1
                finally:
                    if file_path and os.path.exists(file_path): os.remove(file_path)

        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception as e:
            print(f"General Error: {e}")
            failed += 1

        if (i + 1) % 5 == 0 or (i + 1) == count:
            await status_msg.edit_text(f"📊 Progress: {i+1}/{count}\n✅ Success: {success} | ❌ Failed: {failed}", parse_mode=enums.ParseMode.DISABLED)
        await asyncio.sleep(0.5)

    try: await user_app.stop()
    except Exception: pass
    await status_msg.edit_text(f"🏁 Processing Completed!\n✅ Success: {success} | ❌ Failed: {failed}", parse_mode=enums.ParseMode.DISABLED)

# ----------------- PROPER ASYNC RUNNER -----------------
async def main():
    await start_web_server()
    await bot.start()
    print("Bot is running and connected!")
    await idle()
    await bot.stop()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
