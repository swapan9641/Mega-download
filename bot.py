import os
import sys
import asyncio
import logging
import uuid
import shutil
from aiohttp import web
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import *
from database import *
from video_utils import convert_video
from mega_parser import extract_and_convert_mega_link

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)
logging.getLogger("pyrogram").setLevel(logging.WARNING)

app = Client("MegaBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- USER COMMANDS & CALLBACKS ---

def get_start_text(first_name):
    return (f"✨ **Welcome to the Mega Downloader Bot, {first_name}!** ✨\n\n"
            f"I am an advanced cloud-extraction bot designed to download high-volume files and complete folders directly from **Mega.nz**.\n\n"
            f"**💡 How to use me:**\n"
            f"Simply copy and paste any Mega link into this chat. I will automatically decrypt the link, extract the contents, process any videos to your preferred quality, and upload them to Telegram.\n\n"
            f"👇 **Use the buttons below to configure your preferences.**")

def get_start_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📖 Help & Commands", callback_data="help")],
        [InlineKeyboardButton("⚙️ Settings & Quality", callback_data="settings")]
    ])

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    await add_user(message.from_user.id, message.from_user.username)
    if await is_banned(message.from_user.id):
        return await message.reply("🚫 **Access Denied:** You have been banned from using this bot.")
    await message.reply(get_start_text(message.from_user.first_name), reply_markup=get_start_buttons())

@app.on_callback_query(filters.regex("^start$"))
async def start_cb(client, callback_query):
    # This fixes the broken "Back" button!
    await callback_query.message.edit_text(
        get_start_text(callback_query.from_user.first_name), 
        reply_markup=get_start_buttons()
    )

@app.on_callback_query(filters.regex("^help$"))
async def help_cb(client, callback_query):
    text = ("**📖 Comprehensive Help Guide**\n\n"
            "**📥 Downloading Files:**\n"
            "Paste any valid `mega.nz/file/` or `mega.nz/folder/` link. The bot supports recursive folder downloading.\n\n"
            "**⚙️ User Commands:**\n"
            "• `/start` - Reboot the bot interface.\n"
            "• `/set_channel [ID]` - Route downloads to a specific channel.\n\n"
            "**🛠 Admin Commands:**\n"
            "• `/users` - Export a text file of all database users.\n"
            "• `/ban [ID]` - Restrict a user.\n"
            "• `/unban [ID]` - Restore user access.\n"
            "• `/restart` - Force reboot the server application.")
    await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="start")]]))

@app.on_callback_query(filters.regex("^settings$"))
async def settings_cb(client, callback_query):
    user = await get_user(callback_query.from_user.id)
    quality = user.get("quality", "360p")
    target = user.get("target_channel", "Not Set")
    
    text = (f"**⚙️ Control Panel & Preferences**\n\n"
            f"**🎥 Current Video Quality:** `{quality}`\n"
            f"**🎯 Target Upload Channel:** `{target}`\n\n"
            f"_Note: If you want files sent directly to a group or channel, add me as an Admin there and use the command `/set_channel` followed by the chat ID._")
    
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("📺 Set 360p", callback_data="q_360p"), InlineKeyboardButton("📺 Set 480p", callback_data="q_480p")],
        [InlineKeyboardButton("📺 Set 720p", callback_data="q_720p"), InlineKeyboardButton("📺 Set 1080p", callback_data="q_1080p")],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="start")]
    ])
    await callback_query.message.edit_text(text, reply_markup=buttons)

@app.on_callback_query(filters.regex(r"^q_"))
async def set_quality_cb(client, callback_query):
    new_quality = callback_query.data.split("_")
    await update_settings(callback_query.from_user.id, "quality", new_quality)
    await callback_query.answer(f"✅ Default video quality updated to {new_quality}!", show_alert=True)
    await settings_cb(client, callback_query)

# --- CHANNEL SETTINGS ---

@app.on_message(filters.command("set_channel") & filters.private)
async def set_channel_cmd(client, message):
    if len(message.command) < 2:
        return await message.reply("⚠️ **Incorrect Usage**\n\nPlease provide the ID of the channel or group you want to route files to.\n\n**Example:** `/set_channel -1001234567890`")
    
    try:
        channel_id = int(message.command)
        # Test the connection to ensure the bot has permission
        test_msg = await client.send_message(channel_id, "🔗 **Connection Established:** Mega Bot is now linked to this channel.")
        await update_settings(message.from_user.id, "target_channel", channel_id)
        await message.reply(f"✅ **Target Channel Configured!**\n\nAll future files will be uploaded directly to `{channel_id}`.\n_Make sure I remain an admin, otherwise uploads will fail._")
    except ValueError:
        await message.reply("❌ **Error:** The channel ID must be a number (e.g., -100...)")
    except Exception as e:
        await message.reply(f"❌ **Connection Failed:**\nI cannot send messages to that channel. Make sure I am added as an Admin.\n\n`Error Details: {e}`")

# --- ADMIN COMMANDS ---

@app.on_message(filters.command("users") & filters.user(ADMINS))
async def list_users(client, message):
    users = await get_all_users()
    file_path = "users_list.txt"
    with open(file_path, "w") as f:
        f.write(f"--- Mega Bot Database Export ---\nTotal Active Users: {len(users)}\n\n")
        for u in users:
            f.write(f"ID: {u['_id']} | Username: @{u.get('username', 'Unknown')} | Banned Status: {u.get('is_banned', False)}\n")
    await message.reply_document(file_path, caption="📄 **Database Export Complete.**")
    os.remove(file_path)

@app.on_message(filters.command("ban") & filters.user(ADMINS))
async def ban_cmd(client, message):
    try:
        user_id = int(message.command)
        await ban_user(user_id, True)
        await message.reply(f"✅ **Action Successful:** User `{user_id}` has been permanently banned.")
    except (IndexError, ValueError):
        await message.reply("⚠️ **Usage:** `/ban [user_id]`")

@app.on_message(filters.command("unban") & filters.user(ADMINS))
async def unban_cmd(client, message):
    try:
        user_id = int(message.command)
        await ban_user(user_id, False)
        await message.reply(f"✅ **Action Successful:** User `{user_id}` has had their access restored.")
    except (IndexError, ValueError):
        await message.reply("⚠️ **Usage:** `/unban [user_id]`")

@app.on_message(filters.command("restart") & filters.user(ADMINS))
async def restart_bot(client, message):
    await message.reply("🔄 **Initiating Server Reboot...** Please wait 10-15 seconds for systems to come back online.")
    os.execl(sys.executable, sys.executable, *sys.argv)

# --- MAIN MEGA LOGIC ---

async def process_file(client, message, file_path, status_msg, user):
    quality = user.get("quality", "360p")
    target_channel = user.get("target_channel")
    upload_path = file_path

    if file_path.lower().endswith(('.mp4', '.mkv', '.avi', '.webm')):
        await status_msg.edit(f"⚙️ **Transcoding Video Engine Active**\n\nProcessing media down to **{quality}** using hardware FFmpeg. Please be patient, as this takes time depending on the file size...")
        converted_path = os.path.join(DOWNLOAD_DIR, f"conv_{os.path.basename(file_path)}")
        res = await convert_video(file_path, converted_path, quality)
        if res:
            os.remove(file_path)
            upload_path = converted_path

    await status_msg.edit(f"📤 **Upload in Progress...**\n\nPushing `{os.path.basename(upload_path)}` directly to Telegram servers.")
    
    # Secure Dump Upload
    dump_msg = await client.send_document(
        chat_id=DUMP_CHANNEL, 
        document=upload_path,
        caption=f"📁 **File Data:** `{os.path.basename(upload_path)}`\n👤 **Requested By:** `{message.from_user.id}`{CREDIT_TEXT}"
    )
    
    # Route to user or target
    if target_channel:
        try:
            await dump_msg.copy(chat_id=target_channel)
        except Exception as e:
            await message.reply(f"⚠️ **Warning:** Could not route to your target channel. Sending here instead.\n`{e}`")
            await dump_msg.copy(chat_id=message.chat.id)
    else:
        await dump_msg.copy(chat_id=message.chat.id)

    if os.path.exists(upload_path):
        os.remove(upload_path)

@app.on_message(filters.regex(r"(?i)mega\.nz") & filters.private)
async def handle_mega(client, message):
    status_msg = await message.reply("🔍 **Analyzing Link...** Extracting secure keys and verifying format.")
    
    try:
        if await is_banned(message.from_user.id):
            return await status_msg.edit("🚫 **Access Denied:** You have been banned from using this bot.")
        
        text = message.text or message.caption
        if not text:
            return await status_msg.edit("❌ **Error:** No readable text found in your message.")
            
        url = extract_and_convert_mega_link(text)
        if not url:
            return await status_msg.edit("❌ **Invalid Link format.** Please ensure the link contains the decryption key (the part after the #).")
            
        await status_msg.edit("⏳ **Bypassing Mega Limits...** Authenticating anonymous session.")
        user = await get_user(message.from_user.id)
        
        task_id = str(uuid.uuid4())
        task_dir = os.path.join(DOWNLOAD_DIR, task_id)
        os.makedirs(task_dir, exist_ok=True)
        
        await status_msg.edit("📥 **Downloading Assets...**\n\nFull Folder/File extraction is currently active. Large requests may take several minutes.")
        
        cmd = f"megadl '{url}' --path '{task_dir}'"
        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            error_msg = stderr.decode() or stdout.decode()
            raise Exception(f"Megatools Extraction Failure: {error_msg.strip()}")
            
        await status_msg.edit("📂 **Download Complete!** Beginning Telegram upload sequence...")
        
        uploaded_count = 0
        for root, dirs, files in os.walk(task_dir):
            for file in files:
                full_path = os.path.join(root, file)
                await process_file(client, message, full_path, status_msg, user)
                uploaded_count += 1
                
        if uploaded_count == 0:
            await status_msg.edit("⚠️ **Warning:** Extraction finished, but the folder appeared to be empty or corrupted.")
        else:
            await status_msg.delete()
            await message.reply("✅ **Batch Process Completed Successfully!**")
            
    except Exception as e:
        logger.error(f"Mega Error: {str(e)}")
        await status_msg.edit(f"❌ **Fatal Processing Error:**\n\n`{str(e)}`")
        
    finally:
        if 'task_dir' in locals() and os.path.exists(task_dir):
            shutil.rmtree(task_dir, ignore_errors=True)

# --- WEB SERVER (RENDER REQUIREMENT) ---

async def web_handler(request):
    return web.Response(text="Mega Bot Service is Active and Healthy!")

async def start_webserver():
    web_app = web.Application()
    web_app.add_routes([web.get('/', web_handler)])
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"🌐 Cloud Health-Check Web Server initialized on Port {PORT}")

# --- STARTUP SEQUENCE ---

async def main():
    await start_webserver()
    await app.start()
    logger.info("🤖 Primary Bot Modules Online!")
    await idle()
    await app.stop()

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
