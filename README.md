# Mega.nz Downloader Bot 🚀

A highly professional, fully async Telegram bot that handles Mega.nz downloads, FFmpeg video transcoding, and MongoDB user tracking.

## 🌟 Key Features
- **Mega Support:** Handles files and folders.
- **Video Transcoding:** Automatically scales videos to 360p, 480p, or 720p using FFmpeg.
- **MongoDB Tracking:** Logs users, stores quality preferences, and manages target channels.
- **Dump Channel:** All downloaded files are securely logged in a central dump channel.
- **Admin Controls:** Comprehensive ban, unban, user listing, and restart commands.

## ⚙️ Deployment Settings

Create a `.env` file referencing `.env.example`.

### Docker Deployment (Recommended)
```bash
docker-compose up -d --build

### MANUAL DELPOY BASE

python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python bot.py
