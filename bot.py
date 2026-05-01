import os
import sys
import asyncio
import logging
import re
from aiohttp import web
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from mega import Mega
from config import *
from database import *
from video_utils import convert_video

# Professional Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)
logging.getLogger("pyrogram").setLevel(logging.WARNING)

app = Client("MegaBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
mega = Mega()
m = mega.login()

# --- USER COMMANDS ---

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    await add_user(message.from_user.id, message.from_user.username)
    if await is_banned(message.from_user.id):
        return await message.reply("🚫 You are banned from using this bot.")

    text = (f"✨ **Welcome {message.from_user.first_name}!** ✨\n\n"
            f"I am a powerful Mega.nz Downloader Bot. Send me a Mega file or folder link to start.\n\n"
            f"🔹 Default Video Quality: **360p**\n"
            f"🔹 Target Channel Support\n"
            f"🔹 Folder & Single File Extraction")
    
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛠 Help & Commands", callback_data="help")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="settings")]
    ])
    await message.reply(text, reply_markup=buttons)

@app.on_callback_query(filters.regex("help"))
async def help_cb(client, callback_query):
    text = ("**📖 Bot Help & Commands**\n\n"
            "**User Commands:**\n"
            "• `/start` - Start the bot\n"
            "• Send any `mega.nz` link to download.\n\n"
            "**Admin Commands:**\n"
            "• `/users` - Get list of all users\n"
            "• `/ban [user_id]` - Ban a user\n"
            "• `/unban [user_id]` - Unban a user\n"
            "• `/restart` - Restart the bot server\n\n"
            "**Features:**\n"
            "Use the settings menu to bind a custom target channel where your files will be forwarded.")
    await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔙 Back", callback_data="start")]]))

@app.on_callback_query(filters.regex("settings"))
async def settings_cb(client, callback_query):
    user = await get_user(callback_query.from_user.id)
    quality = user.get("quality", "360p")
    target = user.get("target_channel", "Not Set")
    
    text = f"**⚙️ User Settings**\n\nCurrent Quality: `{quality}`\nTarget Channel: `{target}`\n\n_To set a target channel, add me as admin to your channel and send me the channel ID._"
    
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("360p", callback_data="q_360p"),
         InlineKeyboardButton("480p", callback_data="q_480p"),
         InlineKeyboardButton("720p", callback_data="q_720p")],
        [InlineKeyboardButton("🔙 Back", callback_data="start")]
    ])
    await callback_query.message.edit_text(text, reply_markup=buttons)

@app.on_callback_query(filters.regex(r"^q_"))
async def set_quality(client, callback_query):
    new_quality = callback_query.data.split("_") # Fixed bug here
    await update_settings(callback_query.from_user.id, "quality", new_quality)
    await callback_query.answer(f"Quality set to {new_quality}", show_alert=True)
    await settings_cb(client, callback_query)

# --- ADMIN COMMANDS ---

@app.on_message(filters.command("users") & filters.user(ADMINS))
async def list_users(client, message):
    users = await get_all_users()
    file_path = "users_list.txt"
    with open(file_path, "w") as f:
        f.write(f"Total Users: {len(users)}\n\n")
        for u in users:
            f.write(f"ID: {u['_id']} | @{u['username']} | Banned: {u['is_banned']}\n")
    await message.reply_document(file_path)
    if os.path.exists(file_path):
        os.remove(file_path)

@app.on_message(filters.command("ban") & filters.user(ADMINS))
async def ban_cmd(client, message):
    try:
        user_id = int(message.command) # Fixed bug here
        await ban_user(user_id, True)
        await message.reply(f"✅ User `{user_id}` banned.")
    except IndexError:
        await message.reply("Usage: `/ban [user_id]`")

@app.on_message(filters.command("unban") & filters.user(ADMINS))
async def unban_cmd(client, message):
    try:
        user_id = int(message.command) # Fixed bug here
        await ban_user(user_id, False)
        await message.reply(f"✅ User `{user_id}` unbanned.")
    except IndexError:
        await message.reply("Usage: `/unban [user_id]`")

@app.on_message(filters.command("restart") & filters.user(ADMINS))
async def restart_bot(client, message):
    await message.reply("🔄 Restarting bot... Please wait.")
    os.execl(sys.executable, sys.executable, *sys.argv)

# --- TARGET CHANNEL SETUP ---

@app.on_message(filters.text & filters.private & ~filters.regex(r"mega\.nz") & ~filters.command(["start", "users", "ban", "unban", "restart"]))
async def set_target_channel(client, message):
    if message.text.startswith("-100"):
        try:
            channel_id = int(message.text)
            # Verify bot can post
            test_msg = await client.send_message(channel_id, "Test connection...")
            await test_msg.delete()
            
            await update_settings(message.from_user.id, "target_channel", channel_id)
            await message.reply("✅ Target channel configured successfully!")
        except Exception as e:
            await message.reply(f"❌ Could not access channel. Make sure I am an admin. Error: {e}")

# --- MAIN DOWNLOAD LOGIC ---

async def process_file(client, message, file_path, status_msg, user):
    quality = user.get("quality", "360p")
    target_channel = user.get("target_channel")
    upload_path = file_path

    # Video Transcoding Logic
    if file_path.lower().endswith(('.mp4', '.mkv', '.avi', '.webm')):
        await status_msg.edit(f"⚙️ Transcoding video to **{quality}** via FFmpeg...")
        converted_path = os.path.join(DOWNLOAD_DIR, f"conv_{os.path.basename(file_path)}")
        res = await convert_video(file_path, converted_path, quality)
        if res:
            os.remove(file_path) # Remove original
            upload_path = converted_path

    await status_msg.edit(f"📤 Uploading `{os.path.basename(upload_path)}` to Telegram...")
    
    # Upload to Dump Channel
    dump_msg = await client.send_document(
        chat_id=DUMP_CHANNEL, 
        document=upload_path,
        caption=f"📁 **File:** `{os.path.basename(upload_path)}`\n👤 **User:** `{message.from_user.id}`{CREDIT_TEXT}"
    )
    
    # Forward to Target Channel if set, otherwise to User
    if target_channel:
        try:
            await dump_msg.copy(chat_id=target_channel)
        except Exception as e:
            await message.reply(f"⚠️ Failed to forward to target channel: {e}")
            await dump_msg.copy(chat_id=message.chat.id)
    else:
        await dump_msg.copy(chat_id=message.chat.id)

    if os.path.exists(upload_path):
        os.remove(upload_path) # Cleanup

@app.on_message(filters.regex(r"mega\.nz") & filters.private)
async def handle_mega(client, message):
    if await is_banned(message.from_user.id):
        return
    
    # 1. Extract ONLY the Mega URL from the message
    url_match = re.search(r"(https?://(?:www\.)?mega\.nz/[^\s]+)", message.text)
    if not url_match:
        return await message.reply("❌ Could not find a valid Mega link in your message.")
    
    url = url_match.group(1)
    
    # 2. Check if the link has a decryption key
    if "#" not in url:
        return await message.reply("❌ **Url key missing!**\nYour Mega link must include the decryption key (the part after the `#`).\n\nExample: `https://mega.nz/file/xxxxx#yyyyyyy`")

    status_msg = await message.reply("⏳ Connecting to Mega...")
    user = await get_user(message.from_user.id)
    
    try:
        await status_msg.edit("📥 Downloading from Mega to Server...")
        
        # Run synchronous mega download in a thread pool so bot doesn't freeze
        loop = asyncio.get_event_loop()
        file_path = await loop.run_in_executor(None, m.download_url, url, DOWNLOAD_DIR)
        
        # If it's a single file (returns string)
        if isinstance(file_path, str):
            await process_file(client, message, file_path, status_msg, user)
            await status_msg.delete()
            
        # If it's a folder
        else:
            await status_msg.edit("⚠️ Folder detected. Processing downloaded contents...")
            for root, dirs, files in os.walk(DOWNLOAD_DIR):
                for file in files:
                    full_path = os.path.join(root, file)
                    await process_file(client, message, full_path, status_msg, user)
            await status_msg.delete()
            
    except Exception as e:
        logger.error(f"Mega Error: {str(e)}")
        await status_msg.edit(f"❌ Error processing link:\n`{str(e)}`")


# --- WEB SERVER FOR CLOUD HEALTH CHECKS ---

async def web_handler(request):
    return web.Response(text="Mega Bot is running successfully!")

async def start_webserver():
    web_app = web.Application()
    web_app.add_routes([web.get('/', web_handler)])
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"🌐 Web server started on port {PORT}")


# --- STARTUP LOGIC ---

async def main():
    # Start web server
    await start_webserver()
    
    # Start Pyrogram bot
    await app.start()
    logger.info("🤖 Bot Started!")
    
    # Keep the bot running
    await idle()
    
    # Stop the bot gracefully
    await app.stop()

if __name__ == "__main__":
    # Fix event loop for Windows/Linux compatibility
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
