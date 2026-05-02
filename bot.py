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
# 🌟 CORE COMMAND EXECUTOR
# ==========================================
async def execute_cmd(cmd: str) -> tuple[str, str, int]:
    """Robust async subprocess executor."""
    process = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    return stdout.decode().strip(), stderr.decode().strip(), process.returncode

async def execute_cmd_with_progress(cmd: str, status_msg) -> tuple[str, int]:
    """Runs a shell command and streams its output to Telegram live."""
    process = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    
    last_update = time.time()
    full_output = []
    
    while True:
        chunk = await process.stdout.read(1024)
        if not chunk:
            break
        
        decoded = chunk.decode(errors='ignore')
        full_output.append(decoded)
        
        now = time.time()
        if now - last_update > 4.0:
            lines = decoded.replace('\r', '\n').strip().split('\n')
            tail = lines[-1].strip() if lines else ""
            
            if tail and any(char.isdigit() for char in tail): 
                try:
                    await status_msg.edit(
                        f"📥 **Downloading Payload to Server...**\n\n"
                        f"**Live Server Output:**\n`{tail[:80]}`\n\n"
                        f"_Please be patient, massive folders take time._"
                    )
                    last_update = now
                except Exception:
                    pass
                    
    await process.wait()
    return "".join(full_output), process.returncode

# ==========================================
# 🌟 UI GENERATORS & STANDARD COMMANDS
# ==========================================
def get_start_text(first_name: str) -> str:
    return (f"✨ **Hello {first_name}, Welcome to the Heavy-Duty Mega Engine!** ✨\n\n"
            f"I am built to bypass storage limits and quotas. Send me a massive Mega link, and I will download and upload the files sequentially.\n\n"
            f"**💡 Pro Tip:** Use `/login` to connect your own Mega account and bypass the public server quota limits!")

def get_start_buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔐 Login to Mega", callback_data="login_cb"), InlineKeyboardButton("⚙️ Settings", callback_data="settings")],
        [InlineKeyboardButton("📖 Help & Support", callback_data="help")]
    ])

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
            "**⚙️ Commands:**\n"
            "• `/login` - Link your personal Mega account to bypass quota limits.\n"
            "• `/logout` - Remove your credentials.\n"
            "• `/set_channel` - Route files to your own channel.\n"
            "• `/support` - Get help or contact admins.")
    await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="start")]]))

@app.on_callback_query(filters.regex("^settings$"))
async def settings_cb(client, callback_query):
    user = await get_user(callback_query.from_user.id)
    quality = user.get("quality", "360p")
    target = user.get("target_channel", "Not Set")
    account = user.get("mega_email", "None (Using Bot Default)")
    
    text = (f"**⚙️ Preferences**\n\n"
            f"**👤 Mega Account:** `{account}`\n"
            f"**🎥 Video Quality:** `{quality}`\n"
            f"**🎯 Target Channel:** `{target}`\n\n"
            f"_Use /set_channel to change your upload destination._")
    
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
# 🔐 AUTHENTICATION & CHANNEL SETUP (STATEFUL)
# ==========================================
@app.on_message(filters.command("set_channel") & filters.private)
async def set_channel_start(client, message):
    await update_settings(message.from_user.id, "state", "WAITING_FOR_CHANNEL")
    await message.reply("**🎯 Target Channel Setup**\n\n**Step 1:** Add me to your Channel as Admin.\n**Step 2:** Reply with the **Chat ID** (e.g., `-1001234567890`).\n\n_Send /cancel to abort._")

@app.on_callback_query(filters.regex("^login_cb$"))
async def login_cb_start(client, callback_query):
    await update_settings(callback_query.from_user.id, "state", "WAITING_FOR_EMAIL")
    await callback_query.message.edit_text("🔐 **Mega.nz Login**\n\nPlease enter your Mega Account **Email Address**:\n\n_Type /cancel to abort._")

@app.on_message(filters.command("login") & filters.private)
async def login_cmd(client, message):
    await update_settings(message.from_user.id, "state", "WAITING_FOR_EMAIL")
    await message.reply("🔐 **Mega.nz Login**\n\nPlease enter your Mega Account **Email Address**:\n\n_Type /cancel to abort._")

@app.on_message(filters.command("logout") & filters.private)
async def logout_cmd(client, message):
    await update_settings(message.from_user.id, "mega_email", None)
    await update_settings(message.from_user.id, "mega_password", None)
    await message.reply("🔓 **Successfully logged out.**\nThe bot will now use the default server quota.")

@app.on_message(filters.command("cancel") & filters.private)
async def cancel_process(client, message):
    await update_settings(message.from_user.id, "state", None)
    await message.reply("🚫 **Cancelled.**")

@app.on_message(filters.text & filters.private & ~filters.regex(r"(?i)mega\.nz") & ~filters.command(["start", "help", "users", "ban", "unban", "restart", "set_channel", "cancel", "login", "logout"]))
async def conversation_handler(client, message):
    user = await get_user(message.from_user.id)
    state = user.get("state")
    
    if not state:
        return

    # CHANNEL SETUP LOGIC
    if state == "WAITING_FOR_CHANNEL":
        try:
            channel_id = int(message.text.strip())
            await update_settings(message.from_user.id, "target_channel", channel_id)
            await update_settings(message.from_user.id, "state", None)
            try:
                test_msg = await client.send_message(channel_id, "🔗 **Connection Verified!**")
                await test_msg.delete()
                await message.reply(f"🎉 **Success!** Configured to `{channel_id}`.")
            except Exception:
                await message.reply(f"✅ **ID Saved (`{channel_id}`), but Verification Failed!**\n\nForward any message from that channel to me here to register it in my cache.")
        except ValueError:
            await message.reply("❌ **Invalid Format!** Must be a numeric ID.")

    # EMAIL LOGIN LOGIC
    elif state == "WAITING_FOR_EMAIL":
        email = message.text.strip()
        await update_settings(message.from_user.id, "temp_email", email)
        await update_settings(message.from_user.id, "state", "WAITING_FOR_PASSWORD")
        await message.reply(f"📧 **Email Set:** `{email}`\n\nNow, please enter your **Password**:\n\n_🛡️ For your security, I will automatically delete your password message after you send it._")

    # PASSWORD LOGIN & VERIFICATION LOGIC
    elif state == "WAITING_FOR_PASSWORD":
        password = message.text.strip()
        email = user.get("temp_email")
        
        # Security Feature: Delete user's message containing the password
        with contextlib.suppress(Exception):
            await message.delete()
            
        status = await message.reply("🔄 **Verifying credentials with Mega's Servers...**")
        
        # Test the credentials by asking Mega for free space (megadf)
        test_rc_path = os.path.abspath(f".megarc_test_{message.from_user.id}")
        with open(test_rc_path, "w") as f:
            f.write(f"[Login]\nUsername = {email}\nPassword = {password}\n")
            
        _, _, code = await execute_cmd(f"megadf --config {test_rc_path}")
        
        with contextlib.suppress(FileNotFoundError):
            os.remove(test_rc_path)
            
        if code == 0:
            await update_settings(message.from_user.id, "mega_email", email)
            await update_settings(message.from_user.id, "mega_password", password)
            await update_settings(message.from_user.id, "state", None)
            await update_settings(message.from_user.id, "temp_email", None)
            await status.edit("✅ **Login Successful!**\n\nYour personal Mega account is securely linked. You will no longer hit the public server quota limits.")
        else:
            await update_settings(message.from_user.id, "state", None)
            await update_settings(message.from_user.id, "temp_email", None)
            await status.edit("❌ **Login Failed!**\n\nIncorrect email or password. Please try again with `/login`.")

# ==========================================
# 📊 PROGRESS BAR ENGINE (UPLOAD)
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
    
    with contextlib.suppress(Exception):
        await status_msg.edit(text)

# ==========================================
# 🚀 CORE ENGINE: BATCH EXTRACTION WITH DYNAMIC AUTH
# ==========================================
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
        await asyncio.sleep(e.value)
        await client.send_document(chat_id=message.chat.id, document=upload_path)
    except Exception as e:
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
        
        # Check if user has personal login credentials
        user_email = user.get("mega_email")
        user_password = user.get("mega_password")
        
        if user_email and user_password:
            # Create a custom .megarc for this specific user's download
            active_megarc = os.path.join(task_dir, ".megarc")
            with open(active_megarc, "w") as f:
                f.write(f"[Login]\nUsername = {user_email}\nPassword = {user_password}\n")
            await status_msg.edit(f"📥 **Initializing Download...**\n_Bypassing quota using personal account:_ `{user_email}`")
        else:
            # Fallback to the global server .env credentials
            active_megarc = MEGARC_PATH
            await status_msg.edit("📥 **Initializing Download...**\n_Using default server quota. Use /login to add your own account if you hit limits._")
        
        dl_cmd = f"megadl --config {active_megarc} '{url}' --path '{task_dir}'"
        output, code = await execute_cmd_with_progress(dl_cmd, status_msg)
        
        if code != 0:
            raise Exception(f"Download failed. Check link or storage limits:\n`{output[:300]}`")

        downloaded_files = []
        for root, dirs, files in os.walk(task_dir):
            for file in files:
                # Ignore the temporary config file
                if file != ".megarc":
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
                pass

        await status_msg.delete()
        await message.reply(f"✅ **Operation Complete!**\nSuccessfully extracted and uploaded **{successful}/{total}** files.")
            
    except Exception as e:
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

async def main():
    await setup_database()
    await start_webserver()
    await app.start()
    await idle()
    await app.stop()

if __name__ == "__main__":
    if sys.platform == 'win32': 
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.get_event_loop().run_until_complete(main())
