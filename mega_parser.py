import re

def extract_and_convert_mega_link(text):
    """Safely extracts and formats Mega links for megatools compatibility."""
    match = re.search(r"(https?://(?:www\.)?mega\.nz/[^\s]+)", text, re.IGNORECASE)
    if not match:
        return None
    
    url = match.group(1)
    
    # Safely convert /folder/ format
    folder_match = re.search(r"mega\.nz/folder/([^#\s]+)#([^\s]+)", url)
    if folder_match:
        return f"https://mega.nz/#F!{folder_match.group(1)}!{folder_match.group(2)}"
        
    # Safely convert /file/ format
    file_match = re.search(r"mega\.nz/file/([^#\s]+)#([^\s]+)", url)
    if file_match:
        return f"https://mega.nz/#!{file_match.group(1)}!{file_match.group(2)}"
        
    # Return as-is if it's already a classic format
    return url
