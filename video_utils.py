import asyncio
import os

async def convert_video(input_path, output_path, quality="360p"):
    """Converts video to the requested quality using FFmpeg asynchronously."""
    
    # Map quality to FFmpeg scale
    scale_map = {
        "360p": "-2:360",
        "480p": "-2:480",
        "720p": "-2:720",
        "1080p": "-2:1080"
    }
    scale = scale_map.get(quality, "-2:360") # Default to 360p

    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-vf", f"scale={scale}",
        "-c:v", "libx264", "-crf", "28", "-preset", "fast",
        "-c:a", "aac", "-b:a", "128k",
        output_path
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    await process.communicate()
    
    if process.returncode == 0 and os.path.exists(output_path):
        return output_path
    return None
