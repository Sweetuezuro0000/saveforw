import os
import re
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait, ChatForwardsRestricted, RPCError
from aiohttp import web

# ----------------- CONFIGURATION -----------------
API_ID = int(os.environ.get("API_ID", "11271546"))
API_HASH = os.environ.get("API_HASH", "1f1f4621cde774fef16b39dd8274e982")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
OWNER_ID = int(os.environ.get("OWNER_ID", "5787360401"))

bot = Client("SaveForwBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

user_data = {
    "session": None,
    "caption": None,
    "remwords": [],
    "replace": {},
    "target_chat": None,
    "target_topic": None
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

# ----------------- FIXED LINK PARSERS -----------------
def parse_source_link(link: str):
    """
    सॉर्स लिंक पार्सर (जहाँ से मैसेज उठाना है)
    """
    # 1. Topic link: https://t.me/c/123456789/2/100
    m_topic = re.match(r"https?://t\.me/c/(\d+)/(\d+)/(\d+)", link)
    if m_topic:
        return int("-100" + m_topic.group(1)), int(m_topic.group(3))
        
    # 2. Private standard link: https://t.me/c/123456789/100
    m_priv = re.match(r"https?://t\.me/c/(\d+)/(\d+)", link)
    if m_priv:
        return int("-100" + m_priv.group(1)), int(m_priv.group(2))
        
    # 3. Public standard link: https://t.me/channelname/100
    m_pub = re.match(r"https?://t\.me/([^/]+)/(\d+)", link)
    if m_pub:
        return m_pub.group(1), int(m_pub.group(2))
        
    return None, None

def parse_target_link(link: str):
    """
    टारगेट लिंक पार्सर (जहाँ मैसेज भेजना है)
    """
    # 1. Specific Topic Message Link: https://t.me/c/123456789/2/100 (Chat: -100123456789, Topic: 2)
    m_topic = re.match(r"https?://t\.me/c/(\d+)/(\d+)/(\d+)", link)
    if m_topic:
        return int("-100" + m_topic.group(1)), int(m_topic.group(2))
    
    # 2. Standard Channel/Group Link: https://t.me/c/123456789/100 (Chat: -100123456789, Topic: None)
    m_std = re.match(r"https?://t\.me/c/(\d+)/(\d+)", link)
    if m_std:
        return int("-100" + m_std.group(1)), None

    # 3. Public Channel Link: https://t.me/channelname
    m_pub = re.match(r"https?://t\.me/([^/]+)", link)
    if m_pub:
        return m_pub.group(1), None

    return None, None

def process_caption(orig_caption: str) -> str:
    caption = orig_caption or ""
    for old, new in user_data["replace"].items():
        caption = caption.replace(old, new)
    for word in user_data["remwords"]:
        caption = caption.replace(word, "")
    if user_data["caption"]:
        caption = user_data["caption"]
    return caption.strip()

def check_owner(user_id: int):
    return user_id == OWNER_ID

# ----------------- COMMAND HANDLERS -----------------
@bot.on_message(filters.command("start"))
async def start_cmd(client, message: Message):
    if not check_owner(message.from_user.id):
        return await message.reply(
            f"❌ **Unauthorized User!**\n\n"
            f"आपकी Telegram ID: `{message.from_user.id}`\n"
            f"Render के Env Variable में `OWNER_ID` को यह ID सेट करें।"
        )
    
    msg = (
        "⚡ **Fixed Save & Copy Bot Active!**\n\n"
        "🔹 `/setsession <StringSession>` - Pyrogram Session\n"
        "🔹 `/settarget <Link>` - Target Channel या Topic Link सेट करें\n"
        "🔹 `/deltarget` - Target Reset करें\n"
        "🔹 `/batch <start_link> <count>` - Batch Copy\n"
        "🔹 `/setcaption <text>` | `/delcaption`\n"
        "🔹 `/remword <word>` | `/replace <old> <new>`"
    )
    await message.reply(msg)

@bot.on_message(filters.command("setsession"))
async def set_session(client, message: Message):
    if not check_owner(message.from_user.id): return
    try:
        user_data["session"] = message.text.split(" ", 1)[1].strip()
        await message.reply("✅ Session Saved Successfully!")
    except IndexError:
        await message.reply("❌ Usage: `/setsession <StringSession>`")

@bot.on_message(filters.command("settarget"))
async def set_target_topic(client, message: Message):
    if not check_owner(message.from_user.id): return
    try:
        link = message.text.split(" ", 1)[1].strip()
        chat_id, topic_id = parse_target_link(link)
        
        if not chat_id:
            return await message.reply("❌ Invalid Target Link!")
            
        user_data["target_chat"] = chat_id
        user_data["target_topic"] = topic_id
        
        if topic_id:
            await message.reply(f"🎯 Target Set to **Topic**!\nChat ID: `{chat_id}`\nTopic ID: `{topic_id}`")
        else:
            await message.reply(f"🎯 Target Set to **Standard Chat**!\nChat ID: `{chat_id}`")
            
    except IndexError:
        await message.reply("❌ Usage: `/settarget <Topic_or_Chat_Link>`")

@bot.on_message(filters.command("deltarget"))
async def del_target_topic(client, message: Message):
    if not check_owner(message.from_user.id): return
    user_data["target_chat"], user_data["target_topic"] = None, None
    await message.reply("🗑️ Target Reset to Bot DM!")

@bot.on_message(filters.command("setcaption"))
async def set_caption(client, message: Message):
    if not check_owner(message.from_user.id): return
    try:
        user_data["caption"] = message.text.split(" ", 1)[1]
        await message.reply("✅ Custom Caption Saved!")
    except IndexError:
        await message.reply("❌ Usage: `/setcaption <text>`")

@bot.on_message(filters.command("delcaption"))
async def del_caption(client, message: Message):
    if not check_owner(message.from_user.id): return
    user_data["caption"] = None
    await message.reply("🗑️ Custom Caption Removed!")

@bot.on_message(filters.command("remword"))
async def rem_word(client, message: Message):
    if not check_owner(message.from_user.id): return
    try:
        word = message.text.split(" ", 1)[1]
        user_data["remwords"].append(word)
        await message.reply(f"✅ Word removed from captions: `{word}`")
    except IndexError:
        await message.reply("❌ Usage: `/remword <word>`")

@bot.on_message(filters.command("replace"))
async def replace_word(client, message: Message):
    if not check_owner(message.from_user.id): return
    try:
        _, old_word, new_word = message.text.split(" ", 2)
        user_data["replace"][old_word] = new_word
        await message.reply(f"✅ Replacement: `{old_word}` ➔ `{new_word}`")
    except ValueError:
        await message.reply("❌ Usage: `/replace <old> <new>`")

# ----------------- BATCH LOGIC -----------------
@bot.on_message(filters.command("batch"))
async def batch_process(client: Client, message: Message):
    if not check_owner(message.from_user.id): return
    if not user_data["session"]:
        return await message.reply("❌ Set session first via `/setsession`")
    
    args = message.text.split()
    if len(args) < 3:
        return await message.reply("❌ Usage: `/batch <link> <count>`")
    
    start_link = args[1]
    try:
        count = int(args[2])
    except ValueError:
        return await message.reply("❌ Count must be a number.")

    chat_id, start_msg_id = parse_source_link(start_link)
    if not chat_id or not start_msg_id:
        return await message.reply("❌ Invalid Source Link Format!")
        
    status_msg = await message.reply("⏳ Connecting User Session...")
    
    user_app = Client(
        "UserSession",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=user_data["session"],
        in_memory=True,
        no_updates=True
    )
    
    try:
        await user_app.start()
    except Exception as e:
        return await status_msg.edit_text(f"❌ Session Connection Failed: `{e}`")

    dest_chat = user_data["target_chat"] or message.chat.id
    dest_topic = user_data["target_topic"] if user_data["target_chat"] else None

    await status_msg.edit_text(f"🚀 Processing Batch ({count} items)...")
    
    success, failed = 0, 0
    chunk_size = 50

    for i in range(0, count, chunk_size):
        current_chunk_count = min(chunk_size, count - i)
        msg_ids = list(range(start_msg_id + i, start_msg_id + i + current_chunk_count))
        
        try:
            messages = await user_app.get_messages(chat_id, msg_ids)
        except FloodWait as e:
            await asyncio.sleep(e.value)
            messages = await user_app.get_messages(chat_id, msg_ids)
        except Exception as e:
            print(f"Fetch Error: {e}")
            failed += len(msg_ids)
            continue

        if not isinstance(messages, list):
            messages = [messages]

        for msg in messages:
            if not msg or msg.empty:
                failed += 1
                continue

            caption = process_caption(msg.caption or msg.text)

            try:
                # 1. FAST DIRECT SERVER COPY ATTEMPT
                if msg.media:
                    copy_kwargs = {"chat_id": dest_chat, "caption": caption}
                    if dest_topic: 
                        copy_kwargs["reply_to_message_id"] = dest_topic
                    
                    await msg.copy(**copy_kwargs)
                    success += 1

                elif msg.text:
                    send_kwargs = {"chat_id": dest_chat, "text": caption}
                    if dest_topic: 
                        send_kwargs["reply_to_message_id"] = dest_topic
                        
                    await user_app.send_message(**send_kwargs)
                    success += 1

            except (ChatForwardsRestricted, RPCError) as err:
                # 2. FALLBACK TO DOWNLOAD / UPLOAD (If Channel is Restricted or Copy Fails)
                file_path, thumb_path = None, None
                try:
                    if msg.media:
                        file_path = await user_app.download_media(msg)
                        if file_path and os.path.exists(file_path):
                            send_kwargs = {"chat_id": dest_chat, "caption": caption}
                            if dest_topic: 
                                send_kwargs["reply_to_message_id"] = dest_topic

                            if msg.video:
                                duration = msg.video.duration or 0
                                width = msg.video.width or 0
                                height = msg.video.height or 0
                                
                                if msg.video.thumbs:
                                    try:
                                        thumb_path = await user_app.download_media(msg.video.thumbs[0].file_id)
                                    except Exception: pass

                                await bot.send_video(
                                    video=file_path,
                                    duration=duration,
                                    width=width,
                                    height=height,
                                    thumb=thumb_path,
                                    supports_streaming=True,
                                    **send_kwargs
                                )

                            elif msg.photo:
                                await bot.send_photo(photo=file_path, **send_kwargs)

                            elif msg.document:
                                if msg.document.thumbs:
                                    try:
                                        thumb_path = await user_app.download_media(msg.document.thumbs[0].file_id)
                                    except Exception: pass

                                await bot.send_document(document=file_path, thumb=thumb_path, **send_kwargs)

                            elif msg.audio:
                                await bot.send_audio(audio=file_path, duration=msg.audio.duration or 0, **send_kwargs)

                            success += 1
                        else:
                            failed += 1
                    elif msg.text:
                        send_kwargs = {"chat_id": dest_chat, "text": caption}
                        if dest_topic: 
                            send_kwargs["reply_to_message_id"] = dest_topic
                        await bot.send_message(**send_kwargs)
                        success += 1

                except Exception as ex:
                    print(f"Fallback Error on msg {msg.id}: {ex}")
                    failed += 1
                finally:
                    if file_path and os.path.exists(file_path): os.remove(file_path)
                    if thumb_path and os.path.exists(thumb_path): os.remove(thumb_path)

            except FloodWait as e:
                await asyncio.sleep(e.value)
            except Exception as e:
                print(f"General Error on msg {msg.id}: {e}")
                failed += 1

            await asyncio.sleep(0.5)

        processed = min(i + chunk_size, count)
        await status_msg.edit_text(f"📊 **Progress:** `{processed}/{count}`\n✅ **Success:** `{success}` | ❌ **Failed:** `{failed}`")

    try:
        await user_app.stop()
    except Exception: pass

    await status_msg.edit_text(f"🏁 **Batch Processing Finished!**\n✅ **Success:** `{success}`\n❌ **Failed:** `{failed}`")

# ----------------- MAIN RUNNER -----------------
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(start_web_server())
    bot.run()
