import os
import re
import asyncio
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

# ----------------- LINK PARSERS -----------------
def parse_telegram_link(link: str):
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

def parse_target_topic_link(link: str):
    m = re.match(r"https?://t\.me/c/(\d+)/(\d+)", link)
    if m:
        return int("-100" + m.group(1)), int(m.group(2))
    return None, None

# ----------------- CAPTION PROCESSOR -----------------
def process_caption(orig_caption: str) -> str:
    caption = orig_caption or ""
    for old, new in user_data["replace"].items():
        caption = caption.replace(old, new)
    for word in user_data["remwords"]:
        caption = caption.replace(word, "")
    if user_data["caption"]:
        caption = user_data["caption"]
    return caption.strip()

# ----------------- COMMAND HANDLERS -----------------
@bot.on_message(filters.command("start"))
async def start_cmd(client, message: Message):
    if message.from_user.id != OWNER_ID:
        return await message.reply("⚠️ Unauthorized user!")
    
    msg = (
        "🤖 **Fast Direct-Copy Bot Loaded!**\n\n"
        "**Commands List:**\n"
        "🔹 `/setsession <StringSession>` - Save Pyrogram Session\n"
        "🔹 `/settarget <TopicLink>` - Set destination Group Topic\n"
        "🔹 `/deltarget` - Reset target back to Bot DM\n"
        "🔹 `/batch <link> <count>` - Copy files in batch (Instant)\n"
        "🔹 `/setcaption <text>` / `/delcaption` - Manage Custom Caption\n"
        "🔹 `/remword <word>` - Remove specific words\n"
        "🔹 `/replace <old> <new>` - Replace words\n"
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

@bot.on_message(filters.command("settarget"))
async def set_target_topic(client, message: Message):
    if message.from_user.id != OWNER_ID: return
    try:
        link = message.text.split(" ", 1)[1].strip()
        chat_id, topic_id = parse_target_topic_link(link)
        if not chat_id or not topic_id:
            return await message.reply("❌ **Invalid Target Link!**\nFormat: `/settarget https://t.me/c/1234567890/55`")
        
        user_data["target_chat"] = chat_id
        user_data["target_topic"] = topic_id
        await message.reply(
            f"🎯 **Target Topic Saved Successfully!**\n\n"
            f"📌 **Group ID:** `{chat_id}`\n"
            f"📌 **Topic ID:** `{topic_id}`\n\n"
            f"All extracted files will now be copied directly to this Topic."
        )
    except IndexError:
        await message.reply("❌ **Usage:** `/settarget https://t.me/c/1234567890/55`")

@bot.on_message(filters.command("deltarget"))
async def del_target_topic(client, message: Message):
    if message.from_user.id != OWNER_ID: return
    user_data["target_chat"] = None
    user_data["target_topic"] = None
    await message.reply("🗑️ **Target Topic Removed.** Files will now be copied to Bot DM.")

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

# ----------------- BATCH PROCESSING LOGIC (DIRECT SERVER COPY) -----------------
@bot.on_message(filters.command("batch"))
async def batch_process(client: Client, message: Message):
    if message.from_user.id != OWNER_ID: return
    if not user_data["session"]:
        return await message.reply("❌ **Please set Pyrogram session first using `/setsession`**")
    
    args = message.text.split()
    if len(args) < 3:
        return await message.reply("❌ **Usage:** `/batch <start_link> <count>`\nExample: `/batch https://t.me/c/12345/10/20 500`")
    
    start_link = args[1]
    try:
        count = int(args[2])
    except ValueError:
        return await message.reply("❌ **Count must be a valid number.**")
        
    chat_id, start_msg_id = parse_telegram_link(start_link)
    if not chat_id or not start_msg_id:
        return await message.reply("❌ **Invalid Telegram Link/Topic Format!**")
        
    status_msg = await message.reply("⏳ **Connecting User Session...**")
    
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
        return await status_msg.edit_text(f"❌ **Session Login Failed:** `{e}`\nPlease set your string session again using `/setsession`!")

    # Load Dialogs to build Peer Cache
    await status_msg.edit_text("⏳ **Loading Dialogs & Resolving Channel Access...**")
    try:
        async for _ in user_app.get_dialogs(limit=200):
            pass
    except Exception as e:
        print(f"Dialog load error: {e}")

    # Resolve Channel Access
    try:
        chat_obj = await user_app.get_chat(chat_id)
    except Exception as e:
        await user_app.stop()
        return await status_msg.edit_text(f"❌ **Channel Access Failed:** `{e}`\nCheck if your account is joined in the source channel.")

    # Determine Destination
    dest_chat = user_data["target_chat"] or message.chat.id
    dest_topic = user_data["target_topic"] if user_data["target_chat"] else None

    await status_msg.edit_text(f"🚀 **Fast Copying {count} items from `{chat_obj.title or chat_id}`...**")
    
    success, failed = 0, 0
    last_error = ""

    for current_id in range(start_msg_id, start_msg_id + count):
        try:
            msg = await user_app.get_messages(chat_id, current_id)
        except FloodWait as e:
            await asyncio.sleep(e.value)
            try:
                msg = await user_app.get_messages(chat_id, current_id)
            except Exception as ex:
                last_error = f"Fetch Error: {ex}"
                failed += 1
                continue
        except Exception as e:
            last_error = f"Fetch Error: {e}"
            failed += 1
            continue

        if not msg or msg.empty:
            last_error = "Empty or deleted message"
            failed += 1
            continue

        try:
            caption = process_caption(msg.caption or msg.text)

            if msg.media:
                copy_args = {
                    "chat_id": dest_chat,
                    "caption": caption
                }
                if dest_topic:
                    copy_args["reply_to_message_id"] = dest_topic

                await msg.copy(**copy_args)
                success += 1

            elif msg.text:
                send_args = {
                    "chat_id": dest_chat,
                    "text": caption
                }
                if dest_topic:
                    send_args["reply_to_message_id"] = dest_topic
                    
                await user_app.send_message(**send_args)
                success += 1

        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception as e:
            last_error = f"Copy Error: {e}"
            failed += 1

        await asyncio.sleep(0.5)

        # Update status
        processed = current_id - start_msg_id + 1
        if processed % 10 == 0 or processed == count:
            await status_msg.edit_text(f"📊 **Progress:** `{processed}/{count}`\n✅ **Success:** `{success}` | ❌ **Failed:** `{failed}`")

    try:
        await user_app.stop()
    except Exception:
        pass

    result_text = f"🏁 **Batch Completed!**\n✅ **Total Sent:** `{success}`\n❌ **Failed:** `{failed}`"
    if failed > 0 and last_error:
        result_text += f"\n\n⚠️ **Reason for Failure:** `{last_error}`"

    await status_msg.edit_text(result_text)

# ----------------- MAIN EXECUTION -----------------
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(start_web_server())
    bot.run()
