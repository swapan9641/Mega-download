import re

# Pre-compile regex patterns for performance and memory efficiency
URL_PATTERN = re.compile(r"(https?://(?:www\.)?mega\.nz/[^\s]+)", re.IGNORECASE)
FOLDER_PATTERN = re.compile(r"mega\.nz/folder/([^#\s]+)#([^\s]+)")
FILE_PATTERN = re.compile(r"mega\.nz/file/([^#\s]+)#([^\s]+)")

def extract_and_convert_mega_link(text: str) -> str | None:
    """
    Safely extracts and formats Mega links for megatools CLI compatibility.
    Handles legacy formats and newer /file/ or /folder/ formats.
    """
    if not text:
        return None
        
    match = URL_PATTERN.search(text)
    if not match:
        return None
    
    url = match.group(1)
    
    folder_match = FOLDER_PATTERN.search(url)
    if folder_match:
        return f"https://mega.nz/#F!{folder_match.group(1)}!{folder_match.group(2)}"
        
    file_match = FILE_PATTERN.search(url)
    if file_match:
        return f"https://mega.nz/#!{file_match.group(1)}!{file_match.group(2)}"
        
    return url
