import os
import sys
import asyncio
import uuid
import shutil
import contextlib
import time
import math
from aiohttp import web
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait

from config import *
from database import *
from video_utils import convert_video
from mega_parser import extract_and_convert_mega_link

app = Client("MegaBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ==========================================
# 🌟 CORE UI GENERATORS
# ==========================================
def get_start_text(first_name: str) -> str:
    return (f"✨ **Hello {first_name}, Welcome to the Heavy-Duty Mega Engine!** ✨\n\n"
            f"I am built to bypass storage limits. When you send me a massive Mega folder, I authenticate, map the nodes, and download/upload the files **strictly one-by-one**.\n\n"
            f"👇 **Explore my features below:**")

def get_start_buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📖 Read User Guide", callback_data="help")],
        [InlineKeyboardButton("⚙️ Settings & Quality", callback_data="settings"), InlineKeyboardButton("🎧 Support", callback_data="support")]
    ])

# ==========================================
# 🎮 STANDARD COMMANDS
# ==========================================
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    await add_user(message.from_user.id, message.from_user.username)
    await update_settings(message.from_user.id, "state", None)
    if await is_banned(message.from_user.id):
        return await message.reply("🚫 **Access Denied:** Your account is suspended.")
    await message.reply(get_start_text(message.from_user.first_name), reply_markup=get_start_buttons())

@app.on_callback_query(filters.regex("^start$"))
async def start_cb(client, callback_query):
    await update_settings(callback_query.from_user.id, "state", None)
    await callback_query.message.edit_text(get_start_text(callback_query.from_user.first_name), reply_markup=get_start_buttons())

@app.on_callback_query(filters.regex("^help$"))
async def help_cb(client, callback_query):
    text = ("**📖 Mega Bot User Guide**\n\n"
            "**📥 How to Download:**\n"
            "Paste any Mega link in this chat. Folders are automatically processed sequentially.\n\n"
            "**⚙️ Available Commands:**\n"
            "• `/set_channel` - Route files to your own channel.\n"
            "• `/support` - Get help or contact admins.")
    await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="start")]]))

@app.on_callback_query(filters.regex("^support$"))
async def support_cb(client, callback_query):
    await callback_query.message.edit_text("**🎧 Support Center**\n\nIf the bot stalls, a large file might be processing. Do not spam links.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="start")]]))

@app.on_callback_query(filters.regex("^settings$"))
async def settings_cb(client, callback_query):
    user = await get_user(callback_query.from_user.id)
    quality = user.get("quality", "360p")
    target = user.get("target_channel", "Not Set")
    
    text = f"**⚙️ Preferences**\n\n**🎥 Quality:** `{quality}`\n**🎯 Target Channel:** `{target}`\n\n_Use /set_channel to change your upload destination._"
    
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("📺 360p", callback_data="q_360p"), InlineKeyboardButton("📺 480p", callback_data="q_480p")],
        [InlineKeyboardButton("📺 720p", callback_data="q_720p"), InlineKeyboardButton("📺 1080p", callback_data="q_1080p")],
        [InlineKeyboardButton("🔙 Back", callback_data="start")]
    ])
    await callback_query.message.edit_text(text, reply_markup=buttons)

@app.on_callback_query(filters.regex(r"^q_"))
async def set_quality_cb(client, callback_query):
    new_quality = callback_query.data.split("_")
    await update_settings(callback_query.from_user.id, "quality", new_quality)
    await callback_query.answer(f"✅ Quality updated to {new_quality}.", show_alert=True)
    await settings_cb(client, callback_query)

# ==========================================
# 🎯 CHANNEL SETUP (STATEFUL)
# ==========================================
@app.on_message(filters.command("set_channel") & filters.private)
async def set_channel_start(client, message):
    await update_settings(message.from_user.id, "state", "WAITING_FOR_CHANNEL")
    await message.reply("**🎯 Target Channel Setup**\n\n**Step 1:** Add me to your Channel as Admin.\n**Step 2:** Reply with the **Chat ID** (e.g., `-1001234567890`).\n\n_Send /cancel to abort._")

@app.on_message(filters.command("cancel") & filters.private)
async def cancel_process(client, message):
    await update_settings(message.from_user.id, "state", None)
    await message.reply("🚫 **Cancelled.**")

@app.on_message(filters.text & filters.private & ~filters.regex(r"(?i)mega\.nz") & ~filters.command(["start", "help", "users", "ban", "unban", "restart", "set_channel", "cancel"]))
async def conversation_handler(client, message):
    user = await get_user(message.from_user.id)
    if user and user.get("state") == "WAITING_FOR_CHANNEL":
        try:
            channel_id = int(message.text.strip())
            await update_settings(message.from_user.id, "target_channel", channel_id)
            await update_settings(message.from_user.id, "state", None)
            
            try:
                test_msg = await client.send_message(channel_id, "🔗 **Connection Verified!**")
                await test_msg.delete()
                await message.reply(f"🎉 **Success!** Configured to `{channel_id}`.")
            except Exception as e:
                logger.warning(f"Verification msg failed for {channel_id}: {e}")
                await message.reply(f"✅ **ID Saved (`{channel_id}`), but Verification Failed!**\n\nForward any message from that channel to me here to register it in my cache.")
        except ValueError:
            await message.reply("❌ **Invalid Format!** Must be a numeric ID.")

# ==========================================
# 📊 PROGRESS BAR ENGINE
# ==========================================
last_edit_time = {}

async def progress_bar(current, total, status_msg, start_time, current_file, total_files):
    now = time.time()
    msg_id = status_msg.id
    
    if msg_id in last_edit_time and (now - last_edit_time[msg_id]) < 3.0:
        if current != total:
            return
            
    last_edit_time[msg_id] = now
    
    percentage = current * 100 / total
    speed = current / (now - start_time) if (now - start_time) > 0 else 1
    eta = round((total - current) / speed) if speed > 0 else 0
    
    completed_blocks = math.floor(percentage / 5)
    remaining_blocks = 20 - completed_blocks
    progress_str = f"[{'█' * completed_blocks}{'░' * remaining_blocks}]"
    
    text = (f"📤 **Uploading File {current_file}/{total_files}**\n\n"
            f"{progress_str}\n\n"
            f"**🚀 Progress:** `{round(percentage, 2)}%`\n"
            f"**⚡ Speed:** `{round(speed / 1024 / 1024, 2)} MB/s`\n"
            f"**⏳ ETA:** `{eta} Seconds`")
    
    try:
        await status_msg.edit(text)
    except Exception:
        pass

# ==========================================
# 🚀 CORE ENGINE: AUTHENTICATED BATCH EXTRACTION
# ==========================================
async def execute_cmd(cmd: str) -> tuple[str, str, int]:
    process = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    return stdout.decode().strip(), stderr.decode().strip(), process.returncode

async def process_single_upload(client, message, file_path, status_msg, user, current, total):
    quality = user.get("quality", "360p")
    target = user.get("target_channel")
    upload_path = file_path

    if file_path.lower().endswith(('.mp4', '.mkv', '.avi', '.webm')):
        await status_msg.edit(f"⚙️ **Transcoding File {current}/{total}**\nProcessing to {quality}...")
        converted = os.path.join(DOWNLOAD_DIR, f"conv_{os.path.basename(file_path)}")
        
        if await convert_video(file_path, converted, quality):
            with contextlib.suppress(FileNotFoundError):
                os.remove(file_path)
            upload_path = converted

    start_time = time.time()
    
    try:
        dump_msg = await client.send_document(
            chat_id=DUMP_CHANNEL, 
            document=upload_path, 
            caption=f"📁 **File:** `{os.path.basename(upload_path)}`\n👤 **User:** `{message.from_user.id}`{CREDIT_TEXT}",
            progress=progress_bar,
            progress_args=(status_msg, start_time, current, total)
        )
        if target:
            await dump_msg.copy(chat_id=target)
        else:
            await dump_msg.copy(chat_id=message.chat.id)
            
    except FloodWait as e:
        logger.warning(f"FloodWait triggered. Sleeping for {e.value} seconds.")
        await asyncio.sleep(e.value)
        await client.send_document(chat_id=message.chat.id, document=upload_path)
    except Exception as e:
        logger.error(f"Upload error: {e}")
        await client.send_message(chat_id=message.chat.id, text=f"⚠️ Upload failed for `{os.path.basename(upload_path)}`")
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.remove(upload_path)

@app.on_message(filters.regex(r"(?i)mega\.nz") & filters.private)
async def handle_mega(client, message):
    status_msg = await message.reply("🔍 **Authenticating with Mega...**")
    
    try:
        user = await get_user(message.from_user.id)
        if user.get("is_banned"): 
            return await status_msg.edit("🚫 Access Denied.")
            
        url = extract_and_convert_mega_link(message.text or message.caption)
        if not url: 
            return await status_msg.edit("❌ Invalid Link format.")

        task_dir = os.path.join(DOWNLOAD_DIR, str(uuid.uuid4()))
        os.makedirs(task_dir, exist_ok=True)
        
        await status_msg.edit("📥 **Downloading Payload to Server...**\n\n_Because this is a public folder, I am downloading the full package first. I will separate and upload the files sequentially right after._")
        
        dl_cmd = f"megadl --config {MEGARC_PATH} '{url}' --path '{task_dir}'"
        stdout, stderr, code = await execute_cmd(dl_cmd)
        
        if code != 0:
            raise Exception(f"Download failed. Check link or storage limits:\n`{stderr or stdout}`")

        downloaded_files = []
        for root, dirs, files in os.walk(task_dir):
            for file in files:
                downloaded_files.append(os.path.join(root, file))
                
        total = len(downloaded_files)
        
        if total == 0:
            await status_msg.edit("⚠️ **Process finished, but the folder was empty.**")
            return
            
        await status_msg.edit(f"📂 **Extraction Complete!**\n\n_Mapped {total} files. Initiating sequential upload..._")
        
        successful = 0
        for index, file_path in enumerate(downloaded_files, 1):
            try:
                await process_single_upload(client, message, file_path, status_msg, user, index, total)
                successful += 1
            except Exception as e:
                logger.error(f"Error on file {index}: {e}")

        await status_msg.delete()
        await message.reply(f"✅ **Operation Complete!**\nSuccessfully extracted and uploaded **{successful}/{total}** files.")
            
    except Exception as e:
        logger.error(f"Mega handler critical error: {e}")
        await status_msg.edit(f"❌ **System Error:**\n\n`{str(e)[:800]}`")
    finally:
        if 'task_dir' in locals() and os.path.exists(task_dir):
            shutil.rmtree(task_dir, ignore_errors=True)

# ==========================================
# 🛡 ADMIN COMMANDS & WEB SERVER
# ==========================================
@app.on_message(filters.command("users") & filters.user(ADMINS))
async def list_users(client, message):
    users = await get_all_users()
    with open("users_list.txt", "w") as f:
        f.write(f"--- Mega Bot Database ---\nTotal: {len(users)}\n\n")
        for u in [f"ID: {u['_id']} | Banned: {u.get('is_banned', False)}\n" for u in users]: 
            f.write(u)
    await message.reply_document("users_list.txt")
    os.remove("users_list.txt")

@app.on_message(filters.command("ban") & filters.user(ADMINS))
async def ban_cmd(client, message):
    try:
        user_id = int(message.text.split())
        await ban_user(user_id, True)
        await message.reply(f"✅ User `{user_id}` banned.")
    except Exception:
        await message.reply("⚠️ Usage: `/ban [user_id]`")

@app.on_message(filters.command("unban") & filters.user(ADMINS))
async def unban_cmd(client, message):
    try:
        user_id = int(message.text.split())
        await ban_user(user_id, False)
        await message.reply(f"✅ User `{user_id}` unbanned.")
    except Exception:
        await message.reply("⚠️ Usage: `/unban [user_id]`")

@app.on_message(filters.command("restart") & filters.user(ADMINS))
async def restart_bot(client, message):
    await message.reply("🔄 **Initiating Reboot...**")
    os.execl(sys.executable, sys.executable, *sys.argv)

async def web_handler(request):
    return web.Response(text="Service Active!")

async def start_webserver():
    web_app = web.Application()
    web_app.add_routes([web.get('/', web_handler)])
    runner = web.AppRunner(web_app)
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', PORT).start()
    logger.info(f"Web server started on port {PORT}")

async def main():
    await setup_database()
    await start_webserver()
    await app.start()
    logger.info("🤖 Bot Online!")
    await idle()
    await app.stop()

if __name__ == "__main__":
    if sys.platform == 'win32': 
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.get_event_loop().run_until_complete(main())
