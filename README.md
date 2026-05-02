# 🚀 Advanced Mega.nz Downloader Bot

An enterprise-grade Telegram bot designed to securely bypass Mega.nz restrictions and download massive public folders. Built with strict memory management and sequential extraction architecture to prevent server overflow on low-tier hosting (Render/Koyeb).

## ✨ Advanced Features
- **Sequential Extraction:** Evaluates folder nodes and downloads files strictly one-by-one to conserve disk space.
- **Pre-compiled Regex & Indexing:** Optimized parsing and MongoDB indexing for rapid query execution.
- **FFmpeg Faststart Integration:** Transcoded videos are optimized for instant Telegram streaming.
- **Stateful Conversations:** Interactive UI for binding target channels.
- **Secure Subprocessing:** Asynchronous shell execution with strict memory leak prevention.

## 🛠️ Deployment Instructions
1. Fork or clone this repository.
2. Setup a free MongoDB Cluster and a burner Mega.nz account.
3. Add your credentials to your Cloud Host's Environment Variables (refer to `.env.example`).
4. Deploy using Docker. The `Dockerfile` handles all system dependencies automatically.

## 📝 Admin Commands
* `/users` - Export total database registry.
* `/ban [ID]` / `/unban [ID]` - Manage access control.
* `/restart` - Safely trigger a server reboot.
