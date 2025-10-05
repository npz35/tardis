# Copyright 2025 npz35
#
# See the NOTICE file for this project for license details.
# This file may not be used except in accordance with the NOTICE.

import os
import logging
import uuid
import shutil
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple
import re
import json
from pypdf import PdfReader
from app.config import Config

def setup_logging(log_level: str = "INFO") -> None:
    """
    Sets up logging.

    Args:
        log_level: Log level
    """
    # Set log level
    level: int = getattr(logging, log_level.upper(), logging.INFO)

    # Configure logger
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(Config.LOG_FILE), # Use Config.LOG_FILE
            logging.StreamHandler()
        ]
    )

def ensure_directory(path: str) -> bool:
    logging.debug(f"Function start: ensure_directory(path='{path}')")
    """
    Creates a directory if it does not exist.

    Args:
        path: Path to the directory

    Returns:
        True if successful
    """
    try:
        os.makedirs(path, exist_ok=True)
        logging.debug("Function end: ensure_directory (success)")
        return True
    except Exception as e:
        logging.error(f"Failed to create directory {path}: {str(e)}")
        logging.debug("Function end: ensure_directory (failure)")
        return False

def cleanup_old_files(directory: str, days: int = 2) -> int:
    logging.debug(f"Function start: cleanup_old_files(directory='{directory}', days={days})")
    """
    Deletes files older than the specified number of days.

    Args:
        directory: Path to the directory
        days: Number of days for deletion target

    Returns:
        Number of deleted files
    """
    try:
        if not os.path.exists(directory):
            logging.debug("Function end: cleanup_old_files (no directory)")
            return 0

        # Cutoff date for deletion
        cutoff_date: datetime = datetime.now() - timedelta(days=days)

        deleted_count: int = 0

        # Check files in the directory
        for filename in os.listdir(directory):
            file_path: str = os.path.join(directory, filename)

            # If the file is older than the target date
            if os.path.isfile(file_path):
                file_mtime: datetime = datetime.fromtimestamp(os.path.getmtime(file_path))
                if file_mtime < cutoff_date:
                    try:
                        os.remove(file_path)
                        deleted_count += 1
                        logging.info(f"Deleted old file: {file_path}")
                    except Exception as e:
                        logging.error(f"Failed to delete file {file_path}: {str(e)}")

        logging.debug(f"Function end: cleanup_old_files (success) -> deleted {deleted_count} files")
        return deleted_count

    except Exception as e:
        logging.error(f"Failed to cleanup old files in {directory}: {str(e)}")
        logging.debug("Function end: cleanup_old_files (failure)")
        return 0

def generate_unique_filename(original_filename: str, prefix: str = "") -> str:
    logging.debug(f"Function start: generate_unique_filename(original_filename='{original_filename}', prefix='{prefix}')")
    """
    Generates a unique filename.

    Args:
        original_filename: Original filename
        prefix: Prefix

    Returns:
        Unique filename
    """
    try:
        # Get file extension
        name: str
        ext: str
        name, ext = os.path.splitext(original_filename)

        # Generate UUID
        unique_id: str = str(uuid.uuid4())[:8]

        # Generate new filename
        new_filename: str = f"{prefix}{name}_{unique_id}{ext}"

        logging.debug("Function end: generate_unique_filename (success)")
        return new_filename

    except Exception as e:
        logging.error(f"Failed to generate unique filename: {str(e)}")
        logging.debug("Function end: generate_unique_filename (failure)")
        return original_filename

def validate_pdf_file(file_path: str) -> Tuple[bool, str]:
    logging.debug(f"Function start: validate_pdf_file(file_path='{file_path}')")
    """
    Validates a PDF file.

    Args:
        file_path: Path to the file

    Returns:
        (Validation result, Error message)
    """
    try:
        # Check if file exists
        if not os.path.exists(file_path):
            logging.debug("Function end: validate_pdf_file (file does not exist)")
            return False, "File does not exist"

        # Check file size
        file_size: int = os.path.getsize(file_path)
        if file_size == 0:
            logging.debug("Function end: validate_pdf_file (file is empty)")
            return False, "File is empty"

        # Check file size limit (16MB)
        max_size: int = Config.MAX_CONTENT_LENGTH
        if file_size > max_size:
            logging.debug("Function end: validate_pdf_file (file size too large)")
            return False, f"File size is too large (maximum {max_size/1024/1024:.1f}MB)"

        # Check if it's a PDF file
        if not file_path.lower().endswith('.pdf'):
            logging.debug("Function end: validate_pdf_file (not a pdf file)")
            return False, "Not a PDF file"

        # Validate by opening with pypdf
        try:
            reader: PdfReader = PdfReader(file_path)
            # Attempt to read a page to validate the PDF
            if not reader.pages:
                logging.debug("Function end: validate_pdf_file (no pages found)")
                return False, "PDF file is empty or corrupted (no pages found)"
            # Accessing a page can trigger validation errors for corrupted files
            _ = reader.pages[0]
        except Exception as e:
            logging.debug("Function end: validate_pdf_file (corrupted)")
            return False, f"PDF file is corrupted: {str(e)}"

    except Exception as e:
        logging.error(f"An error occurred during file validation: {str(e)}")
        logging.debug("Function end: validate_pdf_file (failure)")
        return False, f"An error occurred during file validation: {str(e)}"
    
    logging.debug("Function end: validate_pdf_file (success)")
    return True, ""

def sanitize_filename(filename: str) -> str:
    logging.debug(f"Function start: sanitize_filename(filename='{filename}')")
    """
    Sanitizes a filename.

    Args:
        filename: Original filename

    Returns:
        Sanitized filename
    """
    try:
        # Remove or replace unsafe characters
        unsafe_chars: str = r'[<>:"/\\|?*]'
        sanitized: str = re.sub(unsafe_chars, '_', filename)

        # Remove leading and trailing spaces
        sanitized = sanitized.strip()

        # Default name if empty
        if not sanitized:
            sanitized = "unnamed"

        logging.debug("Function end: sanitize_filename (success)")
        return sanitized

    except Exception as e:
        logging.error(f"Failed to sanitize filename: {str(e)}")
        logging.debug("Function end: sanitize_filename (failure)")
        return filename

def format_file_size(size_bytes: int) -> str:
    logging.debug(f"Function start: format_file_size(size_bytes={size_bytes})")
    """
    Formats file size.

    Args:
        size_bytes: Size in bytes

    Returns:
        Formatted size string
    """
    try:
        if size_bytes == 0:
            logging.debug("Function end: format_file_size (zero bytes)")
            return "0B"

        size_names: List[str] = ["B", "KB", "MB", "GB", "TB"]
        i: int = 0
        size: float = float(size_bytes)

        while size >= 1024.0 and i < len(size_names) - 1:
            size /= 1024.0
            i += 1

        logging.debug("Function end: format_file_size (success)")
        return f"{size:.1f}{size_names[i]}"

    except Exception as e:
        logging.error(f"Failed to format file size: {str(e)}")
        logging.debug("Function end: format_file_size (failure)")
        return "0B"

def get_translation_prompt(text: str, font_info: Dict[str, Any] | None = None) -> str:
    logging.debug(f"Function start: get_translation_prompt(text_len={len(text)}, font_info={font_info})")
    """
    Generates a prompt for translation.

    Args:
        text: Text to translate
        font_info: Font information

    Returns:
        Prompt string
    """
    try:
        # Basic prompt
        prompt: str = f"""Translate the following English text into Japanese.

Translation requirements:
1. Translate into natural and easy-to-understand Japanese.
2. Accurately preserve the original meaning.
3. Translate technical terms appropriately.
4. Adjust honorifics according to context.

Text to translate:
{text}

Translation result:"""

        # If font information is available
        if font_info:
            font_style: str = ""
            if font_info.get("is_bold", False):
                font_style += "bold, "
            if font_info.get("is_italic", False):
                font_style += "italic, "

            if font_style:
                prompt = f"""Translate the following English text into Japanese.

Translation requirements:
1. Translate into natural and easy-to-understand Japanese.
2. Accurately preserve the original meaning.
3. Translate technical terms appropriately.
4. Adjust honorifics according to context.
5. The original text is {font_style.rstrip(', ')}. Maintain that style in the translation.

Text to translate:
{text}

Translation result:"""

        logging.debug("Function end: get_translation_prompt (success)")
        return prompt

    except Exception as e:
        logging.error(f"Failed to generate translation prompt: {str(e)}")
        logging.debug("Function end: get_translation_prompt (failure)")
        return f"Translate: {text}"

def merge_text_blocks(blocks: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    logging.debug(f"Function start: merge_text_blocks(blocks_count={len(blocks)})")
    """
    Merges text blocks.

    Args:
        blocks: List of text blocks

    Returns:
        Merged block
    """
    try:
        if not blocks:
            logging.debug("Function end: merge_text_blocks (empty list)")
            return None

        # Use the first block as a base
        merged_block: Dict[str, Any] = blocks[0].copy()

        # Combine texts
        texts: List[str] = [block["text"] for block in blocks]
        merged_block["text"] = " ".join(texts)

        # Calculate bounding box
        x0: float = min(block["bbox"][0] for block in blocks)
        y0: float = min(block["bbox"][1] for block in blocks)
        x1: float = max(block["bbox"][2] for block in blocks)
        y1: float = max(block["bbox"][3] for block in blocks)
        merged_block["bbox"] = (x0, y0, x1, y1)

        # Integrate font information
        font_sizes: List[float] = [block["font_info"]["font_size"] for block in blocks]
        merged_block["font_info"]["font_size"] = max(font_sizes)

        # Determine bold and italic status
        has_bold: bool = any(block["font_info"].get("is_bold", False) for block in blocks)
        has_italic: bool = any(block["font_info"].get("is_italic", False) for block in blocks)
        merged_block["font_info"]["is_bold"] = has_bold
        merged_block["font_info"]["is_italic"] = has_italic

        logging.debug("Function end: merge_text_blocks (success)")
        return merged_block

    except Exception as e:
        logging.error(f"Failed to merge text blocks: {str(e)}")
        logging.debug("Function end: merge_text_blocks (failure)")
        return blocks[0] if blocks else None

def calculate_text_dimensions(text: str, font_size: float) -> Tuple[float, float]:
    logging.debug(f"Function start: calculate_text_dimensions(text_len={len(text)}, font_size={font_size})")
    """
    Calculates text dimensions.

    Args:
        text: Text
        font_size: Font size

    Returns:
        (Width, Height)
    """
    try:
        char_width: float = font_size * Config.JP_CHAR_WIDTH_FACTOR
        char_height: float = font_size * Config.JP_CHAR_HEIGHT_FACTOR

        # Calculate text width and height
        width: float = len(text) * char_width
        height: float = char_height

        logging.debug("Function end: calculate_text_dimensions (success)")
        return width, height

    except Exception as e:
        logging.error(f"Failed to calculate text dimensions: {str(e)}")
        logging.debug("Function end: calculate_text_dimensions (failure)")
        return 0, 0

def save_processing_log(log_data: Dict[str, Any], log_file: str = "processing.log") -> bool:
    logging.debug(f"Function start: save_processing_log(log_file='{log_file}')")
    """
    Saves processing logs.

    Args:
        log_data: Log data
        log_file: Path to the log file

    Returns:
        True if successful
    """
    try:
        # Add timestamp to log data
        log_data["timestamp"] = datetime.now().isoformat()

        # Append to the log file
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_data, ensure_ascii=False) + "\n")

        logging.debug("Function end: save_processing_log (success)")
        return True

    except Exception as e:
        logging.error(f"Failed to save processing log: {str(e)}")
        logging.debug("Function end: save_processing_log (failure)")
        return False

def load_processing_log(log_file: str = "processing.log") -> List[Dict[str, Any]]:
    logging.debug(f"Function start: load_processing_log(log_file='{log_file}')")
    """
    Loads processing logs.

    Args:
        log_file: Path to the log file

    Returns:
        List of log data
    """
    try:
        logs: List[Dict[str, Any]] = []

        if not os.path.exists(log_file):
            logging.debug("Function end: load_processing_log (file not found)")
            return logs

        # Read the log file
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    log_data: Dict[str, Any] = json.loads(line.strip())
                    logs.append(log_data)
                except json.JSONDecodeError:
                    continue

        logging.debug("Function end: load_processing_log (success)")
        return logs

    except Exception as e:
        logging.error(f"Failed to load processing log: {str(e)}")
        logging.debug("Function end: load_processing_log (failure)")
        return []

def create_backup_file(file_path: str, backup_dir: str = "backups") -> str:
    logging.debug(f"Function start: create_backup_file(file_path='{file_path}', backup_dir='{backup_dir}')")
    """
    Creates a backup of a file.

    Args:
        file_path: Path to the original file
        backup_dir: Directory for backups

    Returns:
        Path to the backup file
    """
    try:
        # Create backup directory
        ensure_directory(backup_dir)

        # Generate backup filename
        filename: str = os.path.basename(file_path)
        name: str
        ext: str
        name, ext = os.path.splitext(filename)
        timestamp: str = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename: str = f"{name}_backup_{timestamp}{ext}"
        backup_path: str = os.path.join(backup_dir, backup_filename)

        # Create backup
        shutil.copy2(file_path, backup_path)

        logging.info(f"Created backup: {backup_path}")
        logging.debug("Function end: create_backup_file (success)")
        return backup_path

    except Exception as e:
        logging.error(f"Failed to create backup file: {str(e)}")
        logging.debug("Function end: create_backup_file (failure)")
        return ""