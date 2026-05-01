import os
import sys
import asyncio
import logging
import uuid
import shutil
import re
from aiohttp import web
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from mega import Mega

from config import *
from database import *
from video_utils import convert_video

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)
logging.getLogger("pyrogram").setLevel(logging.WARNING)

app = Client("MegaBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Initialize Mega Client
mega_client = Mega()
mega_api = mega_client.login()

# ==========================================
# 🌟 USER INTERFACE & MENUS
# ==========================================

def get_start_text(first_name):
    return (f"✨ **Hello {first_name}, Welcome to the Ultimate Mega Downloader!** ✨\n\n"
            f"I am an advanced cloud-extraction AI. I can bypass limits and download massive files and complete folders directly from **Mega.nz**.\n\n"
            f"**💡 How I Work:**\n"
            f"Just send me a Mega link. If it's a huge folder, I will download and upload the files **one by one** so my servers never crash, ensuring you get every single file flawlessly!\n\n"
            f"👇 **Explore my features below:**")

def get_start_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📖 Read User Guide", callback_data="help")],
        [InlineKeyboardButton("⚙️ Settings & Quality", callback_data="settings"), InlineKeyboardButton("🎧 Support", callback_data="support")]
    ])

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    await add_user(message.from_user.id, message.from_user.username)
    # Clear any pending conversational states
    await update_settings(message.from_user.id, "state", None)
    
    if await is_banned(message.from_user.id):
        return await message.reply("🚫 **Access Denied:** Your account has been suspended by the administrators.")
    await message.reply(get_start_text(message.from_user.first_name), reply_markup=get_start_buttons())

@app.on_callback_query(filters.regex("^start$"))
async def start_cb(client, callback_query):
    await update_settings(callback_query.from_user.id, "state", None)
    await callback_query.message.edit_text(get_start_text(callback_query.from_user.first_name), reply_markup=get_start_buttons())

@app.on_callback_query(filters.regex("^help$"))
async def help_cb(client, callback_query):
    text = ("**📖 Mega Bot User Guide**\n\n"
            "**📥 How to Download:**\n"
            "Copy any `mega.nz/file/` or `mega.nz/folder/` link and paste it in this chat. I will handle the encryption and extraction automatically.\n\n"
            "**⚙️ Available Commands:**\n"
            "• `/start` - Refresh the bot and view the main menu.\n"
            "• `/set_channel` - Step-by-step guide to route files to your own channel.\n"
            "• `/support` - Get help or contact admins.\n\n"
            "**🛠 Admin Controls:**\n"
            "• `/users` - Export database.\n"
            "• `/ban [ID]` / `/unban [ID]` - Manage users.\n"
            "• `/restart` - Reboot the server.")
    await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="start")]]))

@app.on_callback_query(filters.regex("^support$"))
async def support_cb(client, callback_query):
    text = ("**🎧 Help & Support Center**\n\n"
            "**Common Issues:**\n"
            "• *Bot is silent?* - The server might be processing a massive file for another user. Please be patient!\n"
            "• *Upload failed?* - Make sure the file isn't larger than Telegram's 2GB limit.\n\n"
            "If you need further assistance, please contact the administrators.")
    await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="start")]]))

@app.on_callback_query(filters.regex("^settings$"))
async def settings_cb(client, callback_query):
    user = await get_user(callback_query.from_user.id)
    quality = user.get("quality", "360p")
    target = user.get("target_channel", "Not Set")
    
    text = (f"**⚙️ Control Panel & Preferences**\n\n"
            f"**🎥 Current Video Quality:** `{quality}`\n"
            f"**🎯 Target Upload Channel:** `{target}`\n\n"
            f"_Select a default video quality below, or use /set_channel to change your upload destination._")
    
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
    await callback_query.answer(f"✅ Awesome! Your videos will now be compressed to {new_quality}.", show_alert=True)
    await settings_cb(client, callback_query)

# ==========================================
# 🎯 INTERACTIVE /SET_CHANNEL PROCESS
# ==========================================

@app.on_message(filters.command("set_channel") & filters.private)
async def set_channel_start(client, message):
    # Step 1: Trigger the conversational state
    await update_settings(message.from_user.id, "state", "WAITING_FOR_CHANNEL")
    
    text = ("**🎯 Target Channel Setup**\n\n"
            "You can route all your downloaded files directly to a specific Telegram Channel or Group.\n\n"
            "**Step 1:** Add me to your Channel/Group and promote me to **Admin**.\n"
            "**Step 2:** Please reply to this message with your **Chat ID** (e.g., `-1001234567890`).\n\n"
            "_Send /cancel if you want to abort this process._")
    await message.reply(text)

@app.on_message(filters.command("cancel") & filters.private)
async def cancel_process(client, message):
    await update_settings(message.from_user.id, "state", None)
    await message.reply("🚫 **Process Cancelled.** You have been returned to the main menu.")

@app.on_message(filters.text & filters.private & ~filters.regex(r"(?i)mega\.nz") & ~filters.command(["start", "help", "users", "ban", "unban", "restart", "set_channel", "cancel"]))
async def conversation_handler(client, message):
    user = await get_user(message.from_user.id)
    
    # Check if the user is in the middle of setting up a channel
    if user and user.get("state") == "WAITING_FOR_CHANNEL":
        channel_input = message.text.strip()
        
        try:
            channel_id = int(channel_input)
            
            # Save the channel and clear the state
            await update_settings(message.from_user.id, "target_channel", channel_id)
            await update_settings(message.from_user.id, "state", None)
            
            # Send verification test
            try:
                test_msg = await client.send_message(channel_id, "🔗 **Connection Verified:** Mega Bot is now actively linked to this channel!")
                await test_msg.delete()
                await message.reply(f"🎉 **Success!**\n\nYour target channel has been configured to `{channel_id}`. All future downloads will be pushed there automatically.")
            except Exception as e:
                await message.reply(
                    f"✅ **ID Saved (`{channel_id}`), but Verification Failed!**\n\n"
                    f"**Why?** Telegram hasn't registered this channel in my memory yet.\n"
                    f"**How to Fix:** Please go to your channel and **forward any message** from it to me here. Once you do that, it will work perfectly!"
                )
        except ValueError:
            await message.reply("❌ **Invalid Format!**\n\nA Chat ID must be a number (like `-100987654321`). Please try sending the ID again, or type `/cancel` to abort.")

# ==========================================
# 🚀 1-BY-1 SEQUENTIAL MEGA ENGINE
# ==========================================

async def process_upload(client, message, file_path, status_msg, user):
    quality = user.get("quality", "360p")
    target_channel = user.get("target_channel")
    upload_path = file_path

    if file_path.lower().endswith(('.mp4', '.mkv', '.avi', '.webm')):
        await status_msg.edit(f"⚙️ **Transcoding Engine Active...**\n\n_Compressing video to {quality}. Please wait..._")
        converted_path = os.path.join(DOWNLOAD_DIR, f"conv_{os.path.basename(file_path)}")
        res = await convert_video(file_path, converted_path, quality)
        if res:
            os.remove(file_path)
            upload_path = converted_path

    await status_msg.edit(f"📤 **Uploading to Telegram:**\n`{os.path.basename(upload_path)}`")
    
    dump_msg = await client.send_document(chat_id=DUMP_CHANNEL, document=upload_path, caption=f"📁 **File:** `{os.path.basename(upload_path)}`\n👤 **Requested By:** `{message.from_user.id}`{CREDIT_TEXT}")
    
    if target_channel:
        try:
            await dump_msg.copy(chat_id=target_channel)
        except Exception:
            await dump_msg.copy(chat_id=message.chat.id)
    else:
        await dump_msg.copy(chat_id=message.chat.id)

    # Clean up local storage immediately
    if os.path.exists(upload_path):
        os.remove(upload_path)

@app.on_message(filters.regex(r"(?i)mega\.nz") & filters.private)
async def handle_mega(client, message):
    status_msg = await message.reply("🔍 **Intercepting Mega Link...**\n_Reading encryption keys..._")
    
    try:
        user = await get_user(message.from_user.id)
        if user.get("is_banned"):
            return await status_msg.edit("🚫 **Access Denied.**")
            
        # Extract Link
        url_match = re.search(r"(https?://(?:www\.)?mega\.nz/[^\s]+)", message.text or message.caption, re.IGNORECASE)
        if not url_match:
            return await status_msg.edit("❌ **Invalid Format.** Could not isolate a proper Mega link.")
        url = url_match.group(1)

        await status_msg.edit("⏳ **Querying Mega API...**\n_Mapping folder structure and nodes..._")
        
        # Download logic using the mega.py wrapper to handle files inside the folder dynamically
        task_dir = os.path.join(DOWNLOAD_DIR, str(uuid.uuid4()))
        os.makedirs(task_dir, exist_ok=True)
        
        # Run the mega.py download synchronously in a thread
        loop = asyncio.get_event_loop()
        
        await status_msg.edit("📥 **Extraction Sequence Started!**\n\n_I am downloading the contents to my temporary server. For massive folders, this step may take several minutes._")
        
        # mega_api.download_url handles both files and folders based on the link provided
        downloaded_path = await loop.run_in_executor(None, mega_api.download_url, url, task_dir)
        
        await status_msg.edit("📂 **Extraction Complete!**\n\n_Initializing the one-by-one upload sequence..._")
        
        uploaded_count = 0
        
        # If it was a single file, downloaded_path is a string. If folder, we walk the dir.
        if isinstance(downloaded_path, str) and os.path.isfile(downloaded_path):
            await process_upload(client, message, downloaded_path, status_msg, user)
            uploaded_count += 1
        else:
            # Iterate through the folder and upload ONE BY ONE
            for root, dirs, files in os.walk(task_dir):
                for file in files:
                    full_path = os.path.join(root, file)
                    await status_msg.edit(f"📦 **Processing item {uploaded_count + 1}...**")
                    await process_upload(client, message, full_path, status_msg, user)
                    uploaded_count += 1
                    
        if uploaded_count == 0:
            await status_msg.edit("⚠️ **Warning:** The folder was processed, but no readable files were found inside.")
        else:
            await status_msg.delete()
            await message.reply(f"✅ **Mission Accomplished!**\n\n🎉 Successfully processed and uploaded **{uploaded_count}** files.")
            
    except Exception as e:
        logger.error(f"Mega Logic Error: {str(e)}")
        await status_msg.edit(f"❌ **System Error:**\n\n`{str(e)}`")
    finally:
        # Final safety cleanup ensures disk space is wiped clean
        if 'task_dir' in locals() and os.path.exists(task_dir):
            shutil.rmtree(task_dir, ignore_errors=True)

# ==========================================
# 🛡 ADMIN COMMANDS & WEB SERVER
# ==========================================

@app.on_message(filters.command("users") & filters.user(ADMINS))
async def list_users(client, message):
    users = await get_all_users()
    file_path = "users_list.txt"
    with open(file_path, "w") as f:
        f.write(f"--- Mega Bot Database ---\nTotal Active Users: {len(users)}\n\n")
        for u in users:
            f.write(f"ID: {u['_id']} | Username: @{u.get('username', 'Unknown')}\n")
    await message.reply_document(file_path)
    os.remove(file_path)

@app.on_message(filters.command("restart") & filters.user(ADMINS))
async def restart_bot(client, message):
    await message.reply("🔄 **Initiating Server Reboot...**")
    os.execl(sys.executable, sys.executable, *sys.argv)

async def web_handler(request):
    return web.Response(text="Mega Bot Service is Active and Healthy!")

async def start_webserver():
    web_app = web.Application()
    web_app.add_routes([web.get('/', web_handler)])
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()

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
