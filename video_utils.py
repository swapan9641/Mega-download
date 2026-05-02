import asyncio
import os
import logging

logger = logging.getLogger("VideoUtils")

async def convert_video(input_path: str, output_path: str, quality: str = "360p") -> str | None:
    """
    Transcodes a video using FFmpeg. 
    Applies strict compression and faststart mapping for Telegram optimization.
    """
    scale_map = {
        "360p": "-2:360",
        "480p": "-2:480",
        "720p": "-2:720",
        "1080p": "-2:1080"
    }
    scale = scale_map.get(quality, "-2:360")

    # -movflags +faststart optimizes the mp4 file for web streaming
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-vf", f"scale={scale}",
        "-c:v", "libx264", "-crf", "28", "-preset", "fast",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        output_path
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await process.communicate()
        
        if process.returncode == 0 and os.path.exists(output_path):
            return output_path
        else:
            logger.error(f"FFmpeg Error: {stderr.decode()}")
            return None
            
    except Exception as e:
        logger.error(f"Transcoding Exception: {e}")
        return None
