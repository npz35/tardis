# Copyright 2025 npz35
#
# See the NOTICE file for this project for license details.
# This file may not be used except in accordance with the NOTICE.

from http.client import HTTPException
import os
import uuid
from datetime import datetime
import traceback
import psutil
import time
from werkzeug.exceptions import RequestEntityTooLarge, ServiceUnavailable
from werkzeug.utils import secure_filename
from werkzeug.datastructures import FileStorage
from app.config import Config, DevelopmentConfig
from app.data_model import PageAnalyzeData, TranslatedUnit, TranslationResponse, TextPermutation
from app.pdf_figure_extractor import PdfFigureExtractor
from app.pdf_area_separator import PdfAreaSeparator
from app.pdf_column_separator import PdfColumnSeparator
from app.pdf_text_extractor import PdfTextExtractor
from app.translator import Translator
from app.pdf_text_layout import PdfTextLayout
from app.pdf_text_manager import PdfTextManager # PdfTextManagerをインポートするのだ
from app.data_model import BBox, TextBlock, FontInfo, Area, UserRequest
from app.utils import setup_logging
from flask import Flask, render_template, request, jsonify, send_file, flash, redirect, url_for, send_from_directory, make_response, Response, current_app
from app.text.pdfminer import PdfminerAnalyzer
from app.text.pdfplumber import PdfplumberAnalyzer
from app.text.pypdf import PyPdfAnalyzer
from app.text.unstructured import UnstructuredAnalyzer
from app.text.common import PdfAnalyzer # PdfAnalyzerもインポートするのだ
from flask_socketio import SocketIO
from typing import Any, Union, Type, Optional # Optionalをインポートするのだ
from pypdf import PdfReader
import io
from datetime import timedelta # timedeltaをインポートするのだ


def _cleanup_old_files_in_folder(app: Flask, target_folder: str) -> None:
    '''
    Deletes files in the specified folder that are older than FILE_RETENTION_DAYS.
    '''
    app.logger.info(f'Starting cleanup of old files in {target_folder}')
    
    now = datetime.now()
    
    # Walk through the directory tree from bottom up
    for root, dirs, files in os.walk(target_folder, topdown=False):
        for file_name in files:
            file_path = os.path.join(root, file_name)
            try:
                # Get file modification time
                mod_timestamp = os.path.getmtime(file_path)
                mod_datetime = datetime.fromtimestamp(mod_timestamp)
                
                # If file is older than FILE_RETENTION_DAYS, delete it
                if now - mod_datetime > timedelta(days=app.config['FILE_RETENTION_DAYS']):
                    os.remove(file_path)
                    app.logger.info(f'Deleted old file: {file_path}')
            except Exception as e:
                app.logger.error(f'Error deleting old file {file_path}: {str(e)}')
                app.logger.error(traceback.format_exc())

        for dir_name in dirs:
            dir_path = os.path.join(root, dir_name)
            try:
                # Check if directory is empty
                if not os.listdir(dir_path):
                    mod_timestamp = os.path.getmtime(dir_path)
                    mod_datetime = datetime.fromtimestamp(mod_timestamp)
                    
                    # If directory is older than FILE_RETENTION_DAYS and empty, delete it
                    if now - mod_datetime > timedelta(days=app.config['FILE_RETENTION_DAYS']):
                        os.rmdir(dir_path)
                        app.logger.info(f'Deleted old empty directory: {dir_path}')
            except Exception as e:
                app.logger.error(f'Error deleting old directory {dir_path}: {str(e)}')
                app.logger.error(traceback.format_exc())
        
    app.logger.info(f'Finished cleanup of old files in {target_folder}.')


def _cleanup_old_files(app: Flask) -> None:
    '''
    Orchestrates cleanup of old files in UPLOAD_FOLDER and OUTPUT_FOLDER.
    '''
    _cleanup_old_files_in_folder(app, app.config['UPLOAD_FOLDER'])
    _cleanup_old_files_in_folder(app, app.config['OUTPUT_FOLDER'])


def _bboxes_overlap(bbox1: BBox, bbox2: BBox, tolerance: float = 0.1) -> bool:
    """
    Check if two bounding boxes overlap.
    
    Args:
        bbox1: First bounding box
        bbox2: Second bounding box
        tolerance: Small tolerance for floating point comparison
        
    Returns:
        True if bboxes overlap, False otherwise
    """
    return not (bbox1.x1 < bbox2.x0 - tolerance or
                bbox2.x1 < bbox1.x0 - tolerance or
                bbox1.y1 < bbox2.y0 - tolerance or
                bbox2.y1 < bbox1.y0 - tolerance)


def _draw_translated_text_on_pdf(
    filepath: str,
    pdf_output_filepath: str,
    translated_units: list[TranslatedUnit],
    figures: list[dict[str, Any]],
    japanese_font_path: str,
    min_font_size: int
) -> None:
    '''
    Draw figures and translated text on a blank PDF.
    
    Args:
        filepath: Path to the input PDF file (used to get page sizes)
        pdf_output_filepath: Path for the output PDF file
        translated_units: List of TranslatedUnit objects containing translated text and metadata
        figures: List of figure data extracted from the PDF
        japanese_font_path: Path to the Japanese font file
        min_font_size: Minimum font size for text rendering
    '''
    from reportlab.pdfgen import canvas
    import pdfplumber

    # Initialize PdfTextLayout
    pdf_text_layout_processor: PdfTextLayout = PdfTextLayout(
        font_path=japanese_font_path,
        min_font_size=min_font_size
    )

    # Get page sizes from original PDF
    page_sizes = []
    total_pages = 0
    with pdfplumber.open(filepath) as pdf:
        total_pages = len(pdf.pages)
        for page_idx, page in enumerate(pdf.pages):
            if Config.MAX_PDF_PAGES <= page_idx:
                break
            page_sizes.append((float(page.width), float(page.height)))
    
    if not page_sizes:
        c = canvas.Canvas(pdf_output_filepath)
        c.save()
        return

    c = canvas.Canvas(pdf_output_filepath, pagesize=page_sizes[0])

    # Group figures by page
    figures_by_page: dict[int, list[dict[str, Any]]] = {}
    for figure in figures:
        page_num = figure['page_number']
        if page_num not in figures_by_page:
            figures_by_page[page_num] = []
        figures_by_page[page_num].append(figure)

    for page_idx in range(min(total_pages, Config.MAX_PDF_PAGES)):
        page_number = page_idx + 1
        
        # Draw figures first
        if page_number in figures_by_page:
            for figure in figures_by_page[page_number]:
                if figure['figure_type'] == 'image_figure':
                    x0, y0, x1, y1 = figure['bbox']
                    rl_x, rl_y = x0, y0
                    rl_width, rl_height = x1 - x0, y1 - y0
                    image_path = figure.get('image_path')
                    if image_path and os.path.exists(image_path):
                        try:
                            c.drawImage(image_path, rl_x, rl_y, width=rl_width, height=rl_height, preserveAspectRatio=True)
                        except Exception as e:
                            current_app.logger.error(f'Error drawing image figure {image_path}: {e}')

        # Group translated units by TextArea
        page_translated_units = [u for u in translated_units if u.page_number == page_number]
        
        # Sort units by Y coordinate (descending) to draw from top to bottom
        page_translated_units.sort(key=lambda u: u.bbox.y1, reverse=True)
        
        # Track drawn bboxes to prevent overlaps
        drawn_bboxes: list[BBox] = []
        
        area_to_units: dict[int, list[TranslatedUnit]] = {}
        for unit in page_translated_units:
            if unit.area is None:
                # areaがない場合は個別に描画（後方互換性）
                if unit.text:
                    # Check and adjust bbox to prevent overlap
                    adjusted_bbox = unit.bbox
                    for drawn_bbox in drawn_bboxes:
                        if _bboxes_overlap(adjusted_bbox, drawn_bbox):
                            # Move bbox below the drawn bbox
                            gap = Config.TEXT_BLOCK_VERTICAL_MARGIN
                            adjusted_bbox = BBox(
                                x0=adjusted_bbox.x0,
                                y0=drawn_bbox.y0 - adjusted_bbox.height() - gap,
                                x1=adjusted_bbox.x1,
                                y1=drawn_bbox.y0 - gap
                            )
                    
                    pdf_text_layout_processor.draw_translated_text(
                        c, unit.text, adjusted_bbox, unit.font_info
                    )
                    drawn_bboxes.append(adjusted_bbox)
            else:
                area_id = id(unit.area)
                if area_id not in area_to_units:
                    area_to_units[area_id] = []
                area_to_units[area_id].append(unit)
        
        # Draw grouped texts
        for area_id, units in area_to_units.items():
            if len(units) == 1:
                # Single text: use existing method
                unit = units[0]
                if unit.text:
                    # Check and adjust bbox to prevent overlap
                    adjusted_bbox = unit.bbox
                    for drawn_bbox in drawn_bboxes:
                        if _bboxes_overlap(adjusted_bbox, drawn_bbox):
                            # Move bbox below the drawn bbox
                            gap = Config.TEXT_BLOCK_VERTICAL_MARGIN
                            adjusted_bbox = BBox(
                                x0=adjusted_bbox.x0,
                                y0=drawn_bbox.y0 - adjusted_bbox.height() - gap,
                                x1=adjusted_bbox.x1,
                                y1=drawn_bbox.y0 - gap
                            )
                    
                    pdf_text_layout_processor.draw_translated_text(
                        c, unit.text, adjusted_bbox, unit.font_info
                    )
                    drawn_bboxes.append(adjusted_bbox)
            else:
                # Multiple texts: use new method
                texts = [u.text for u in units if u.text]
                if texts:
                    # Check and adjust bbox to prevent overlap
                    adjusted_bbox = units[0].bbox
                    for drawn_bbox in drawn_bboxes:
                        if _bboxes_overlap(adjusted_bbox, drawn_bbox):
                            # Move bbox below the drawn bbox
                            gap = Config.TEXT_BLOCK_VERTICAL_MARGIN
                            adjusted_bbox = BBox(
                                x0=adjusted_bbox.x0,
                                y0=drawn_bbox.y0 - adjusted_bbox.height() - gap,
                                x1=adjusted_bbox.x1,
                                y1=drawn_bbox.y0 - gap
                            )
                    
                    # Use the adjusted bbox and font_info
                    pdf_text_layout_processor.draw_multiple_translated_texts_in_area(
                        c, texts, adjusted_bbox, units[0].font_info
                    )
                    drawn_bboxes.append(adjusted_bbox)
        
        c.showPage()

    c.save()


def _handle_file_upload(file: FileStorage, app: Flask) -> UserRequest:
    '''
    Handles the secure saving of an uploaded file to a unique directory.

    Args:
        file: The FileStorage object representing the uploaded file.
        app: The Flask application instance.

    Returns:
        A dictionary containing:
            - 'filepath': The full path to the saved file.
            - 'unique_id': The unique ID generated for the upload directory.
            - 'filename': The secure filename of the uploaded file.
    '''
    filename: str = secure_filename(file.filename)
    unique_id: str = str(uuid.uuid4())
    upload_dir: str = os.path.join(app.config['UPLOAD_FOLDER'], unique_id)
    os.makedirs(upload_dir, exist_ok=True)
    filepath = os.path.join(upload_dir, filename)

    file.save(filepath)
    app.logger.info(f'File uploaded: {filename} -> {filepath}')
    return UserRequest(filepath=filepath, filename=filename, unique_id=unique_id)


def _validate_upload_request(filename: str, unique_id: str) -> str:
    '''
    Validates the existence and accessibility of an already uploaded file.

    Args:
        filename: The secure filename of the uploaded file.
        unique_id: The unique ID of the directory where the file is stored.

    Returns:
        The full path to the validated file.

    Raises:
        Exception: If the file is not found, inaccessible, or invalid.
    '''
    current_app.logger.debug(f"Function start: _validate_upload_request(filename='{filename}', unique_id='{unique_id}')")

    # Reconstruct the expected file path
    upload_dir: str = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_id)
    filepath: str = os.path.join(upload_dir, filename)

    # Check if the file exists
    if not os.path.exists(filepath):
        current_app.logger.error(f'File not found: {filepath}')
        raise Exception('File not found. Please upload the file again.')

    # Check if the file is a PDF
    if not filename.lower().endswith('.pdf'):
        current_app.logger.error(f'Unsupported file type: {filename}')
        raise Exception('Only PDF files are supported.')

    # Check file read permissions
    if not os.access(filepath, os.R_OK):
        current_app.logger.error(f'Cannot read file: {filepath}')
        raise Exception('Cannot read file. Please check permissions.')

    # Check file size (20MB limit)
    file_length: int = os.path.getsize(filepath)

    if file_length > Config.MAX_CONTENT_LENGTH:
        raise RequestEntityTooLarge('File size exceeds 20MB')

    if file_length > Config.MAX_CONTENT_LENGTH:
        current_app.logger.error(f'File size exceeds 20MB: {filepath} ({file_length} bytes)')
        raise RequestEntityTooLarge('File size exceeds 20MB')

    current_app.logger.info(f'Validated file: {filepath}, size: {file_length} bytes')
    current_app.logger.debug('Function end: _validate_upload_request (success)')
    return filepath


def progress_callback(percentage: int, step: int) -> None:
    """
    Progress callback function for emitting progress updates via SocketIO.
    
    Args:
        percentage: Progress percentage (0-100)
        step: Current processing step identifier
    """
    current_app.extensions['socketio'].emit('progress', {'percentage': percentage, 'step': step})
    current_app.logger.info(f'Emitted progress: {percentage}% (Step: {step})')


def _extract_and_validate_request(request_data: dict) -> tuple[str, str, str]:
    """
    Extract and validate request parameters for PDF processing.
    
    Args:
        request_data: Dictionary containing form data
        
    Returns:
        Tuple of (filepath, filename, unique_id)
        
    Raises:
        Exception: If required parameters are missing or validation fails
    """
    filename: str = request_data.get('filename', '')
    unique_id: str = request_data.get('unique_id', '')

    if not filename or not unique_id:
        raise Exception('Missing filename or unique_id in request.')

    # Validate the already uploaded file
    filepath = _validate_upload_request(filename, unique_id)
    
    return filepath, filename, unique_id


def _extract_textpermutations_from_pdf(filepath: str, output_folder: str) -> list[list[TextPermutation]]:
    """
    Extract text permutations from PDF using PdfAreaSeparator.
    
    Args:
        filepath: Path to the PDF file
        output_folder: Output folder path for PdfAreaSeparator
        
    Returns:
        List of pages, each containing filtered TextPermutation objects
    """
    # Initialize PdfplumberAnalyzer to get text permutation information
    pdfplumber_analyzer: PdfplumberAnalyzer = PdfplumberAnalyzer()
    all_page_text_permutations = pdfplumber_analyzer.extract_textpermutations(filepath)

    text_permutations_by_page: list[list[TextPermutation]] = []
    for page_idx, page_text_permutations in enumerate(all_page_text_permutations):
        if Config.MAX_PDF_PAGES <= page_idx:
            break

        allowed_page_text_permutations = [text_permutation for text_permutation in page_text_permutations if text_permutation.text.strip()]
        text_permutations_by_page.append(allowed_page_text_permutations)
    
    return text_permutations_by_page


def _generate_text_output_file(all_page_text_permutations: list[list[TextPermutation]], text_output_filepath: str, include_translation: bool = False, translated_texts: list[str] = None) -> None:
    """
    Generate text file with extracted text data in TextPermutation format.
    
    Args:
        all_page_text_permutations: List of pages, each containing TextPermutation objects
        text_output_filepath: Path for the output text file
        include_translation: Whether to include translated text
        translated_texts: List of translated texts (required if include_translation is True)
    """
    with open(text_output_filepath, 'w', encoding='utf-8') as f:
        global_permutation_idx = 0
        for page_idx, page_text_permutations in enumerate(all_page_text_permutations):
            for text_permutation in page_text_permutations:
                # Write TextPermutation header
                f.write(f"TextPermutation {global_permutation_idx} (Page {text_permutation.page_number}):\n")
                
                # Write Area BBox information
                area_bbox = text_permutation.area.bbox
                f.write(f"  Area BBox: (x0={area_bbox.x0:.2f}, y0={area_bbox.y0:.2f}, x1={area_bbox.x1:.2f}, y1={area_bbox.y1:.2f})\n")
                
                # Write TextBlocks count
                text_blocks_count = len(text_permutation.area.blocks)
                f.write(f"  TextBlocks Count: {text_blocks_count}\n")
                
                # Write FontInfo if available
                if text_permutation.font_info:
                    font = text_permutation.font_info
                    f.write(f"  Font: {font.name}, Size: {font.size:.2f}, Bold: {font.is_bold}, Italic: {font.is_italic}\n")
                
                # Write original text
                f.write(f"  Original: {text_permutation.text}\n")
                
                # Write translated text if available
                if include_translation and translated_texts and global_permutation_idx < len(translated_texts):
                    f.write(f"  Translated: {translated_texts[global_permutation_idx]}\n")
                
                f.write("\n")
                global_permutation_idx += 1


def _translate_texts_in_batches(all_page_text_permutations: list[list[TextPermutation]], logger) -> tuple[list[list[str]], int]:
    """
    Translate texts in batches with progress tracking and limits.
    
    Args:
        all_page_text_permutations: List of pages, each containing TextPermutation objects
        logger: Logger instance for logging messages
        
    Returns:
        Tuple of (translated_texts_by_page, total_translated_units)
    """
    # Initialize translator
    translator: Translator = Translator()
    
    translated_units_count: int = 0 # Counter for total translated units
    
    # Calculate total number of text blocks across all pages
    total_text_blocks = sum(len(page_text_permutations) for page_text_permutations in all_page_text_permutations)
    
    all_translated_results: list[TranslationResponse] = []
    current_global_block_index = 0
    
    translation_start_progress = 20
    translation_end_progress = 80
    
    # Iterate through pages and then text permutations within each page
    for page_idx, page_text_permutations in enumerate(all_page_text_permutations):
        page_block_index = 0
        while page_block_index < len(page_text_permutations):
            # Apply global translation unit limit (TRANSLATION_MAX_UNIT)
            if Config.TRANSLATION_MAX_UNIT is not None:
                remaining_global_units_capacity = Config.TRANSLATION_MAX_UNIT - translated_units_count
                if remaining_global_units_capacity <= 0:
                    logger.warning(f'Global translation unit limit ({Config.TRANSLATION_MAX_UNIT}) reached. Skipping further translation.')
                    break # Stop processing further blocks
    
            # Apply per-request translation unit limit (TRANSLATION_MAX_UNIT_PER_REQUEST)
            if Config.TRANSLATION_MAX_UNIT_PER_REQUEST is not None:
                # Determine the end index for the current request batch
                request_batch_end_index = min(page_block_index + Config.TRANSLATION_MAX_UNIT_PER_REQUEST, len(page_text_permutations))
            else:
                request_batch_end_index = len(page_text_permutations) # No per-request limit
    
            batch_texts_to_translate = [item.text for item in page_text_permutations[page_block_index:request_batch_end_index]]
            
            if not batch_texts_to_translate:
                break # No more texts to translate in this page
    
            logger.info(f'Attempting translation for batch from page {page_idx}, index {page_block_index} to {request_batch_end_index - 1} with {len(batch_texts_to_translate)} units.')
            
            # Calculate current progress percentage for translation step
            current_progress = translation_start_progress + int((current_global_block_index / total_text_blocks) * (translation_end_progress - translation_start_progress))
            progress_callback(current_progress, 3) # Translation in progress (step 3)
    
            translated_results_for_batch: list[TranslationResponse] = translator.translate_texts(batch_texts_to_translate)
            all_translated_results.extend(translated_results_for_batch)
            translated_units_count += len(translated_results_for_batch)
            current_global_block_index += len(translated_results_for_batch)
            page_block_index = request_batch_end_index
            logger.debug(f'current_global_block_index: {current_global_block_index}')
    
        if Config.TRANSLATION_MAX_UNIT is not None and translated_units_count >= Config.TRANSLATION_MAX_UNIT:
            break # Global limit reached, stop processing further pages

    # Reconstruct translated_texts_by_page
    translated_texts_by_page: list[list[str]] = []
    global_translated_idx = 0
    for page_text_permutations in all_page_text_permutations:
        page_translated_texts: list[str] = []
        for _ in page_text_permutations:
            if global_translated_idx < len(all_translated_results):
                page_translated_texts.append(all_translated_results[global_translated_idx].translated_text)
                global_translated_idx += 1
            else:
                page_translated_texts.append("") # Fallback for untranslated blocks
        translated_texts_by_page.append(page_translated_texts)
    
    progress_callback(translation_end_progress, 3) # Translation completed (80% overall, step 3)
    
    return translated_texts_by_page, translated_units_count




# Initialize the application
def create_app(config_class: Type[Config] = Config) -> Flask:
    app_name = __name__
    static_folder = config_class.STATIC_FOLDER
    template_folder = config_class.TEMPLATE_FOLDER
    app: Flask = Flask(app_name,
                static_folder=static_folder,
                template_folder=template_folder)
    app.config.from_object(config_class)
    socketio = SocketIO(app) # Initialize SocketIO
    app.extensions['socketio'] = socketio # Store socketio instance in app extensions

    # Call logging settings from utils
    setup_logging(log_level=app.config['LOG_LEVEL'], log_file_path=app.config['LOG_FILE'])

    app.logger.debug(f'Function start: create_app(config_class={config_class.__name__})')
    app.logger.info('Tardis startup')
    app.logger.info(f"LOG_LEVEL={app.config['LOG_LEVEL']}")
    app.logger.info(f"LOG_FILE={app.config['LOG_FILE']}")

    # Create directories
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

    # Run cleanup of old files on startup
    _cleanup_old_files(app)

    app.logger.debug('Function end: create_app (success)')

    # Routes
    @app.route('/')
    def index() -> Response:
        app.logger.debug('Function start: index()')
        app.logger.debug('Function end: index (success)')
        return render_template('index.html')

    @app.route('/upload', methods=['POST'])
    def upload_pdf() -> Response:
        app.logger.debug('Function start: upload_pdf()')
        filepath: Union[str, None] = None
        # Check disk space
        disk_usage: psutil.DiskUsage = psutil.disk_usage(current_app.config['UPLOAD_FOLDER'])
        if disk_usage.free < Config.REQUIRED_DISK_SPACE:
            raise ServiceUnavailable('Insufficient disk space. Please free up some space.')

        # Check if file exists in request
        if 'file' not in request.files:
            flash('No file selected')
            current_app.logger.debug(f'Function end: upload_pdf (no file selected)')
            return redirect(request.url)

        file: FileStorage = request.files['file']
        if file.filename == '':
            flash('No file selected')
            current_app.logger.debug(f'Function end: upload_pdf (empty filename)')
            return redirect(request.url)
        
        # Check file extension
        if not file.filename.lower().endswith('.pdf'):
            flash('Only PDF files are supported')
            current_app.logger.debug(f'Function end: upload_pdf (unsupported file type)')
            return redirect(request.url)

        # Check file size (20MB limit)
        file.seek(0, os.SEEK_END)
        file_length: int = file.tell()
        file.seek(0)  # Reset file pointer
        if file_length > Config.MAX_CONTENT_LENGTH:
            raise RequestEntityTooLarge('File size exceeds 20MB')
        current_app.logger.info(f'file_length: {file_length}')

        # Handle file upload and get unique ID
        user_request: UserRequest = _handle_file_upload(file, app)
        filepath = user_request.filepath
        filename = user_request.filename
        unique_id = user_request.unique_id
        num_pages = 0 # Default to 0 if page count cannot be determined

        # Get PDF page count
        try:
            # Re-open the file from the saved path to read pages
            with open(filepath, 'rb') as f:
                pdf_reader = PdfReader(f)
                num_pages = len(pdf_reader.pages)
        except RequestEntityTooLarge as e:
            app.logger.error(f'File size error during upload: {str(e)}')
            flash('File size exceeds 20MB')
            app.logger.debug('Function end: upload_pdf (RequestEntityTooLarge)')
            return redirect(url_for('index'))
        except Exception as e:
            app.logger.error(f'Error during upload: {str(e)}')
            app.logger.error(traceback.format_exc())
            flash('An error occurred during file upload')
            app.logger.debug('Function end: upload_pdf (failed)')
            return redirect(url_for('index'))

        current_app.logger.info(f'PDF has {num_pages} pages.')
        current_app.logger.info(f'PDF size {file_length}[B]')
        app.logger.debug('Function end: upload_pdf (success)')
        return jsonify({
            'success': True,
            'filename': filename,
            'unique_id': unique_id,
            'num_pages': num_pages,
            'file_size': file_length,
            'max_pdf_pages': Config.MAX_PDF_PAGES
        })

    # Add column_separation endpoint
    @app.route('/column_separation', methods=['POST'])
    def column_separation_from_pdf() -> Response:
        app.logger.debug('Function start: column_separation_from_pdf()')
        filepath: Union[str, None] = None
        try:
            # Get filename and unique_id from form data
            filename: str = request.form.get('filename', '')
            unique_id: str = request.form.get('unique_id', '')

            if not filename or not unique_id:
                raise Exception('Missing filename or unique_id in request.')

            # Validate the already uploaded file
            filepath = _validate_upload_request(filename, unique_id)

            # Start processing
            start_time: float = time.time()
            app.logger.info(f'Separating columns in file: {filename}')

            pdf_output_filename = f'column_separation_{unique_id}.pdf'
            pdf_output_filepath: str = os.path.join(app.config['OUTPUT_FOLDER'], pdf_output_filename)

            # Initialize PdfColumnSeparator module and call its method
            pdf_column_separator: PdfColumnSeparator = PdfColumnSeparator()
            analyze_pages_data: list[PageAnalyzeData] = pdf_column_separator.analyze_separation_lines(filepath)
            pdf_column_separator.draw_separation_lines(analyze_pages_data, pdf_output_filepath)

            processing_time: float = time.time() - start_time
            app.logger.info(f'Column column_separation completed in {processing_time:.2f} seconds')
            app.logger.info(f'column_separation PDF created: {pdf_output_filepath}')

            app.logger.debug('Function end: column_separation_from_pdf (success)')
            return jsonify({
                'success': True,
                'filename': pdf_output_filename,
                'output_path': pdf_output_filepath,
                'processing_time': f'{processing_time:.2f} seconds',
            })

        except RequestEntityTooLarge as e:
            app.logger.error(f'File size error during column_separation: {str(e)}')
            flash('File size exceeds 20MB for column_separation')
            app.logger.debug('Function end: column_separation_from_pdf (RequestEntityTooLarge)')
            return redirect(url_for('index'))
        except Exception as e:
            # Detailed error logging
            app.logger.error(f'Error during column_separation: {str(e)}')
            app.logger.error(traceback.format_exc())

            # Error message to the user
            error_message: str = 'An error occurred during column_separation'
            if 'Insufficient disk space' in str(e):
                error_message = 'Insufficient disk space. Please free up some space.'
            elif 'Failed to separate columns' in str(e):
                error_message = 'Failed to separate columns in PDF. The file may be corrupted.'
            elif 'PDF parsing error' in str(e):
                error_message = 'An error occurred during PDF parsing for column_separation. Please check the file format.'

            flash(error_message)
            app.logger.debug('Function end: column_separation_from_pdf (failed)')
            return redirect(url_for('index'))
        finally:
            app.logger.debug('Function end: column_separation_from_pdf (success/finally)')

    # Area Coloring endpoint
    @app.route('/area_separation', methods=['POST'])
    def area_separation_from_pdf() -> Response:
        app.logger.debug('Function start: area_separation_from_pdf()')
        filepath: Union[str, None] = None
        try:
            # Get filename and unique_id from form data
            filename: str = request.form.get('filename', '')
            unique_id: str = request.form.get('unique_id', '')

            if not filename or not unique_id:
                raise Exception('Missing filename or unique_id in request.')

            # Validate the already uploaded file
            filepath = _validate_upload_request(filename, unique_id)

            # Start processing
            start_time: float = time.time()
            app.logger.info(f'Coloring areas in file: {filename}')

            pdf_output_filename = f'area_separation_{unique_id}.pdf'

            # Initialize PdfAreaSeparator module and call its method
            pdf_area_separator: PdfAreaSeparator = PdfAreaSeparator(app.config['OUTPUT_FOLDER'])
            pdf_output_filepath: str = pdf_area_separator.create_colored_pdf(filepath, pdf_output_filename)

            processing_time: float = time.time() - start_time
            app.logger.info(f'Area coloring completed in {processing_time:.2f} seconds')
            app.logger.info(f'Area colored PDF created: {pdf_output_filepath}')

            app.logger.debug('Function end: area_separation_from_pdf (success)')
            return jsonify({
                'success': True,
                'filename': pdf_output_filename,
                'output_path': pdf_output_filepath,
                'processing_time': f'{processing_time:.2f} seconds',
            })

        except RequestEntityTooLarge as e:
            app.logger.error(f'File size error during area coloring: {str(e)}')
            flash('File size exceeds 20MB for area coloring')
            app.logger.debug('Function end: area_separation_from_pdf (RequestEntityTooLarge)')
            return redirect(url_for('index'))
        except Exception as e:
            # Detailed error logging
            app.logger.error(f'Error during area coloring: {str(e)}')
            app.logger.error(traceback.format_exc())

            # Error message to the user
            error_message: str = 'An error occurred during area coloring'
            if 'Insufficient disk space' in str(e):
                error_message = 'Insufficient disk space. Please free up some space.'
            elif 'Failed to color areas' in str(e):
                error_message = 'Failed to color areas in PDF. The file may be corrupted.'
            elif 'PDF parsing error' in str(e):
                error_message = 'An error occurred during PDF parsing for area coloring. Please check the file format.'

            flash(error_message)
            app.logger.debug('Function end: area_separation_from_pdf (failed)')
            return redirect(url_for('index'))
        finally:
            app.logger.debug('Function end: area_separation_from_pdf (success/finally)')

    # Extract text from PDF
    @app.route('/extract_text', methods=['POST'])
    def extract_text_from_pdf() -> Response:
        app.logger.debug('Function start: extract_text_from_pdf()')
        filepath: Union[str, None] = None
        text_output_filepath: Union[str, None] = None
        pdf_output_filepath: Union[str, None] = None
        try:
            # Extract and validate request parameters
            filepath, filename, unique_id = _extract_and_validate_request(request.form)

            # Start processing
            start_time: float = time.time()
            app.logger.info(f'Extracting text blocks from file: {filename}')

            pdf_output_filename = f'extracted_text_blocks_{unique_id}.pdf'
            text_output_filename = f'extracted_text_{unique_id}.txt'
            text_output_filepath = os.path.join(app.config['OUTPUT_FOLDER'], text_output_filename)

            # Extract text permutations from PDF
            all_page_text_permutations = _extract_textpermutations_from_pdf(filepath, app.config['OUTPUT_FOLDER'])
            
            # Calculate total number of text blocks for logging and response
            total_extracted_text_units = sum(len(page_text_permutations) for page_text_permutations in all_page_text_permutations)
            app.logger.info(f'text_permutations size: {total_extracted_text_units}')

            # Generate text file
            _generate_text_output_file(all_page_text_permutations, text_output_filepath, include_translation=False)

            if not os.path.exists(text_output_filepath):
                raise Exception(f'Not found {text_output_filepath}.')

            # Generate PDF with colored areas and block IDs
            pdf_area_separator: PdfAreaSeparator = PdfAreaSeparator(app.config['OUTPUT_FOLDER'])
            pdf_output_filepath = pdf_area_separator.create_colored_pdf(filepath, pdf_output_filename)

            processing_time: float = time.time() - start_time
            app.logger.info(f'Text extraction completed in {processing_time:.2f} seconds')
            app.logger.info(f'PDF with colored areas and block IDs created: {pdf_output_filepath}')
 
            app.logger.debug('Function end: extract_text_from_pdf (success)')
            return jsonify({
                'success': True,
                'filename': pdf_output_filename,
                'text_filename': text_output_filename,
                'processing_time': f'{processing_time:.2f} seconds',
                'extracted_text_units': total_extracted_text_units,
            })

        except RequestEntityTooLarge as e:
            app.logger.error(f'File size error during text extraction: {str(e)}')
            flash('File size exceeds 20MB for text extraction')
            app.logger.debug('Function end: extract_text_from_pdf (RequestEntityTooLarge)')
            return redirect(url_for('index'))
        except Exception as e:
            # Detailed error logging
            app.logger.error(f'Error during text extraction: {str(e)}')
            app.logger.error(traceback.format_exc())

            # Error message to the user
            error_message: str = 'An error occurred during text extraction'
            if 'Insufficient disk space' in str(e):
                error_message = 'Insufficient disk space. Please free up some space.'
            elif 'Failed to extract text' in str(e):
                error_message = 'Failed to extract text from PDF. The file may be corrupted or contain no text.'
            elif 'PDF parsing error' in str(e):
                error_message = 'An error occurred during PDF parsing for text extraction. Please check the file format.'

            flash(error_message)
            app.logger.debug('Function end: extract_text_from_pdf (failed)')
            return redirect(url_for('index'))

    # Translate text from PDF
    @app.route('/translate_text', methods=['POST'])
    def translate_text_from_pdf() -> Response:
        app.logger.debug('Function start: translate_text_from_pdf()')
        filepath: Union[str, None] = None
        text_output_filepath: Union[str, None] = None
        pdf_output_filepath: Union[str, None] = None
        try:
            # Extract and validate request parameters
            filepath, filename, unique_id = _extract_and_validate_request(request.form)

            # Start processing
            start_time: float = time.time()
            app.logger.info(f'Extracting and translating text blocks from file: {filename}')

            pdf_output_filename = f'translated_text_blocks_{unique_id}.pdf'
            text_output_filename = f'translated_text_{unique_id}.txt'
            text_output_filepath = os.path.join(app.config['OUTPUT_FOLDER'], text_output_filename)

            # Extract text permutations from PDF
            all_page_text_permutations = _extract_textpermutations_from_pdf(filepath, app.config['OUTPUT_FOLDER'])
            
            # Translate texts in batches
            translated_texts_by_page, translated_units_count = _translate_texts_in_batches(all_page_text_permutations, app.logger)

            # Flatten translated texts for _generate_text_output_file (which expects a flat list of translated strings)
            flattened_translated_texts: list[str] = []
            for page_translated_texts in translated_texts_by_page:
                flattened_translated_texts.extend(page_translated_texts)

            # Generate text file with original and translated texts
            _generate_text_output_file(all_page_text_permutations, text_output_filepath, include_translation=True, translated_texts=flattened_translated_texts)
            app.logger.info(f'Translated text file created: {text_output_filepath}')

            # Generate PDF with colored areas and block IDs (reusing existing functionality)
            # This step is after translation, so it should be part of the final progress
            progress_callback(85, 4) # PDF generation started (85% overall, step 4)

            pdf_area_separator: PdfAreaSeparator = PdfAreaSeparator(app.config['OUTPUT_FOLDER'])
            pdf_output_filepath = pdf_area_separator.create_colored_pdf(filepath, pdf_output_filename)
            
            progress_callback(100, 5) # Completed (100% overall, step 5)

            processing_time: float = time.time() - start_time
            app.logger.info(f'Text translation completed in {processing_time:.2f} seconds')
            app.logger.info(f'PDF with colored areas and block IDs created: {pdf_output_filepath}')
 
            app.logger.debug('Function end: translate_text_from_pdf (success)')
            return jsonify({
                'success': True,
                'filename': pdf_output_filename,
                'text_filename': text_output_filename,
                'processing_time': f'{processing_time:.2f} seconds',
                'translated_units': translated_units_count,
            })

        except RequestEntityTooLarge as e:
            app.logger.error(f'File size error during text translation: {str(e)}')
            flash('File size exceeds 20MB for text translation')
            app.logger.debug('Function end: translate_text_from_pdf (RequestEntityTooLarge)')
            return redirect(url_for('index'))
        except Exception as e:
            # Detailed error logging
            app.logger.error(f'Error during text translation: {str(e)}')
            app.logger.error(traceback.format_exc())

            # Error message to the user
            error_message: str = 'An error occurred during text translation'
            if 'Insufficient disk space' in str(e):
                error_message = 'Insufficient disk space. Please free up some space.'
            elif 'Failed to extract text' in str(e):
                error_message = 'Failed to extract text from PDF. The file may be corrupted or contain no text.'
            elif 'PDF parsing error' in str(e):
                error_message = 'An error occurred during PDF parsing for text translation. Please check the file format.'
            elif '翻訳' in str(e):
                error_message = 'An error occurred during translation. Please try again later.'

            flash(error_message)
            app.logger.debug('Function end: translate_text_from_pdf (failed)')
            return redirect(url_for('index'))

    # Extract figures from PDF
    @app.route('/extract_figures', methods=['POST'])
    def extract_figures_from_pdf() -> Response:
        app.logger.debug('Function start: extract_figures_from_pdf()')
        filepath: Union[str, None] = None
        try:
            # Get filename and unique_id from form data
            filename: str = request.form.get('filename', '')
            unique_id: str = request.form.get('unique_id', '')

            if not filename or not unique_id:
                raise Exception('Missing filename or unique_id in request.')

            # Validate the already uploaded file
            filepath = _validate_upload_request(filename, unique_id)

            # Start processing
            start_time: float = time.time()
            app.logger.info(f'Extracting figures from file: {filename}')

            pdf_output_filename = f'figures_{unique_id}.pdf'
            pdf_output_filepath: str = os.path.join(app.config['OUTPUT_FOLDER'], pdf_output_filename)

            # Initialize PdfFigureExtractor
            pdf_figure_extractor: PdfFigureExtractor = PdfFigureExtractor(app.config['JAPANESE_FONT_PATH'], app.config['OUTPUT_FOLDER'])
            figures: list[dict[str, Any]] = pdf_figure_extractor.extract_figures(filepath, unique_id)

            '''
            figures example
            
            [
                {
                    'page_number': 1,
                    'bbox': (39.7, 511.6, 66.2, 538.1),
                    'figure_type': 'image',
                    'image_data': '/tmp/tmp1yuhuyld/X8.png',
                    'width': 26.5,
                    'height': 26.5,
                    'confidence': 1.0
                },
                {
                    'page_number': 1, 'bbox': (39.7, 481.8, 66.2, 508.3),
                    'figure_type': 'image',
                    'image_data': '/tmp/tmp3w52ndxd/X8.png',
                    'width': 26.5,
                    'height': 26.5,
                    'confidence': 1.0
                },
            ]
            '''

            app.logger.warning('figures')
            app.logger.warning(figures)

            pdf_figure_extractor.create_figure_pdf(figures, pdf_output_filepath, filepath)

            processing_time: float = time.time() - start_time
            app.logger.info(f'Figure extraction completed in {processing_time:.2f} seconds')
            app.logger.info(f'Figure PDF created: {pdf_output_filepath}')

            app.logger.debug('Function end: extract_figures_from_pdf (success)')
            return jsonify({
                'success': True,
                'filename': pdf_output_filename,
                'output_path': pdf_output_filepath,
                'processing_time': f'{processing_time:.2f} seconds',
                'extracted_figures': len(figures),
            })

        except RequestEntityTooLarge as e:
            app.logger.error(f'File size error during figure extraction: {str(e)}')
            flash('File size exceeds 20MB for figure extraction')
            app.logger.debug('Function end: extract_figures_from_pdf (RequestEntityTooLarge)')
            return redirect(url_for('index'))
        except Exception as e:
            # Detailed error logging
            app.logger.error(f'Error during figure extraction: {str(e)}')
            app.logger.error(traceback.format_exc())

            # Error message to the user
            error_message: str = 'An error occurred during figure extraction'
            if 'Insufficient disk space' in str(e):
                error_message = 'Insufficient disk space. Please free up some space.'
            elif 'Failed to extract figures' in str(e):
                error_message = 'Failed to extract figures from PDF. The file may be corrupted or contain no figures.'
            elif 'PDF parsing error' in str(e):
                error_message = 'An error occurred during PDF parsing for figure extraction. Please check the file format.'

            flash(error_message)
            app.logger.debug('Function end: extract_figures_from_pdf (failed)')
            return redirect(url_for('index'))
        finally:
            app.logger.debug('Function end: extract_figures_from_pdf (success/finally)')

    # Draw translated text on PDF
    @app.route('/draw_text', methods=['POST'])
    def draw_text_on_pdf() -> Response:
        app.logger.debug('Function start: draw_text_on_pdf()')
        filepath: Union[str, None] = None
        pdf_output_filepath: Union[str, None] = None
        try:
            # Extract and validate request parameters
            filepath, filename, unique_id = _extract_and_validate_request(request.form)

            # Start processing
            start_time: float = time.time()
            app.logger.info(f'Drawing translated text on PDF for file: {filename}')

            pdf_output_filename = f'drawn_translated_text_{unique_id}.pdf'
            pdf_output_filepath = os.path.join(app.config['OUTPUT_FOLDER'], pdf_output_filename)

            # Extract text permutations from PDF
            all_page_text_permutations = _extract_textpermutations_from_pdf(filepath, app.config['OUTPUT_FOLDER'])
            
            # Translate texts in batches
            translated_texts_by_page, translated_units_count = _translate_texts_in_batches(all_page_text_permutations, app.logger)

            translated_units = []
            global_block_idx = 0
            for page_idx, page_text_permutations in enumerate(all_page_text_permutations):
                for block_idx, text_permutation in enumerate(page_text_permutations):
                    if page_idx < len(translated_texts_by_page) and block_idx < len(translated_texts_by_page[page_idx]):
                        translated_text = translated_texts_by_page[page_idx][block_idx]
                        translated_unit = TranslatedUnit(
                            bbox=text_permutation.area.bbox,
                            text=translated_text,
                            page_number=text_permutation.page_number,
                            font_info=text_permutation.font_info,
                            area=text_permutation.area
                        )
                        translated_units.append(translated_unit)
                    global_block_idx += 1

            # Extract figures
            pdf_figure_extractor: PdfFigureExtractor = PdfFigureExtractor(app.config['JAPANESE_FONT_PATH'], app.config['OUTPUT_FOLDER'])
            figures: list[dict[str, Any]] = pdf_figure_extractor.extract_figures(filepath, unique_id)

            # Draw figures and translated text
            _draw_translated_text_on_pdf(
                filepath=filepath,
                pdf_output_filepath=pdf_output_filepath,
                translated_units=translated_units,
                figures=figures,
                japanese_font_path=app.config['JAPANESE_FONT_PATH'],
                min_font_size=app.config['MIN_FONT_SIZE']
            )

            processing_time: float = time.time() - start_time
            app.logger.info(f'Text drawing completed in {processing_time:.2f} seconds')
            app.logger.info(f'PDF with translated text drawn created: {pdf_output_filepath}')
 
            app.logger.debug('Function end: draw_text_on_pdf (success)')
            return jsonify({
                'success': True,
                'filename': pdf_output_filename,
                'output_path': pdf_output_filepath,
                'processing_time': f'{processing_time:.2f} seconds',
                'translated_units': translated_units_count,
            })

        except RequestEntityTooLarge as e:
            app.logger.error(f'File size error during text drawing: {str(e)}')
            flash('File size exceeds 20MB for text drawing')
            app.logger.debug('Function end: draw_text_on_pdf (RequestEntityTooLarge)')
            return redirect(url_for('index'))
        except Exception as e:
            # Detailed error logging
            app.logger.error(f'Error during text drawing: {str(e)}')
            app.logger.error(traceback.format_exc())

            # Error message to the user
            error_message: str = 'An error occurred during text drawing'
            if 'Insufficient disk space' in str(e):
                error_message = 'Insufficient disk space. Please free up some space.'
            elif 'Failed to extract text' in str(e):
                error_message = 'Failed to extract text from PDF. The file may be corrupted or contain no text.'
            elif 'PDF parsing error' in str(e):
                error_message = 'An error occurred during PDF parsing for text drawing. Please check the file format.'
            elif '翻訳' in str(e):
                error_message = 'An error occurred during translation. Please try again later.'

            flash(error_message)
            app.logger.debug('Function end: draw_text_on_pdf (failed)')
            return redirect(url_for('index'))
        finally:
            app.logger.debug('Function end: draw_text_on_pdf (success/finally)')

    # Download translated PDF
    @app.route('/download/<filename>')
    def download_file(filename: str) -> Response:
        app.logger.debug(f"Function start: download_file(filename='{filename}')")
        output_path: Union[str, None] = None
        try:
            # Verify filename safety
            if not secure_filename(filename) == filename:
                raise Exception('Invalid filename')

            output_path = os.path.join(app.config['OUTPUT_FOLDER'], filename)

            # Check if file exists
            if not os.path.exists(output_path):
                raise Exception('File not found')

            # Check file read permissions
            if not os.access(output_path, os.R_OK):
                raise Exception('Cannot read file')

            # Check file size
            file_size: int = os.path.getsize(output_path)
            if file_size == 0:
                raise Exception('File is empty')

            app.logger.info(f'File download: {filename}')
            app.logger.debug("Function end: download_file(filename='{filename}')")
            return send_file(output_path, as_attachment=True)

        except Exception as e:
            app.logger.error(f'Error during download: {str(e)}')
            app.logger.error(traceback.format_exc())

            # Error message to the user
            error_message: str = 'An error occurred during download'
            if '見つかりません' in str(e):
                error_message = 'Requested file not found'
            elif '読み取る' in str(e):
                error_message = 'Cannot read file'
            elif '空です' in str(e):
                error_message = 'File is empty'

            flash(error_message)
            app.logger.debug('Function end: download_file (failed)')
            return redirect(url_for('index'))
        finally:
            app.logger.debug('Function end: download_file (success/finally)')
            pass

    # Preview translated PDF
    @app.route('/preview/<filename>')
    def preview_file(filename: str) -> Response:
        app.logger.debug(f"Function start: preview_file(filename='{filename}')")
        try:
            # Verify filename safety
            if not secure_filename(filename) == filename:
                raise Exception('Invalid filename')

            output_path: str = os.path.join(app.config['OUTPUT_FOLDER'], filename)

            # Check if file exists
            if not os.path.exists(output_path):
                raise Exception('File not found')

            # Check file read permissions
            if not os.access(output_path, os.R_OK):
                raise Exception('Cannot read file')

            # Check file size
            file_size: int = os.path.getsize(output_path)
            if file_size == 0:
                raise Exception('File is empty')

            app.logger.info(f'File preview: {filename}')
            response: Response = make_response(send_from_directory(app.config['OUTPUT_FOLDER'], filename, mimetype='application/pdf', as_attachment=False, max_age=0))
            response.headers['X-Content-Type-Options'] = 'nosniff'
            app.logger.debug('Function end: preview_file (success)')
            return response

        except Exception as e:
            app.logger.error(f'Error during preview: {str(e)}')
            app.logger.error(traceback.format_exc())
            flash('An error occurred during preview')
            app.logger.debug('Function end: preview_file (failed)')
            return redirect(url_for('index'))

    # Preview text file
    @app.route('/preview_text/<filename>')
    def preview_text_file(filename: str) -> Response:
        app.logger.debug(f"Function start: preview_text_file(filename='{filename}')")
        try:
            # Verify filename safety
            if not secure_filename(filename) == filename:
                raise Exception('Invalid filename')

            output_path: str = os.path.join(app.config['OUTPUT_FOLDER'], filename)

            # Check if file exists
            if not os.path.exists(output_path):
                raise Exception('File not found')

            # Check file read permissions
            if not os.access(output_path, os.R_OK):
                raise Exception('Cannot read file')

            # Check file size
            file_size: int = os.path.getsize(output_path)
            if file_size == 0:
                raise Exception('File is empty')

            app.logger.info(f'Text file preview: {filename}')
            # テキストファイルの内容を直接返すのだ
            with open(output_path, 'r', encoding='utf-8') as f:
                content = f.read()
            response: Response = make_response(content)
            response.headers['Content-Type'] = 'text/plain; charset=utf-8'
            response.headers['X-Content-Type-Options'] = 'nosniff'
            app.logger.debug('Function end: preview_text_file (success)')
            return response

        except Exception as e:
            app.logger.error(f'Error during text preview: {str(e)}')
            app.logger.error(traceback.format_exc())
            flash('An error occurred during text preview')
            app.logger.debug('Function end: preview_text_file (failed)')
            return redirect(url_for('index'))

    # Health check
    @app.route('/health')
    def health_check() -> Response:
        app.logger.debug('Function start: health_check()')
        try:
            # Check disk space
            disk_usage: psutil.DiskUsage = psutil.disk_usage(app.config['UPLOAD_FOLDER'])
            disk_free_mb: float = disk_usage.free / (1024 * 1024)

            # Check memory usage
            memory: psutil.virtual_memory = psutil.virtual_memory()
            memory_usage_percent: float = memory.percent

            # Check if required directories exist
            upload_exists: bool = os.path.exists(app.config['UPLOAD_FOLDER'])
            output_exists: bool = os.path.exists(app.config['OUTPUT_FOLDER'])

            # Measure response time
            start_time: float = time.time()
            # Check responsiveness with a simple operation
            test_response: str = 'OK'
            response_time: float = (time.time() - start_time) * 1000  # milliseconds

            health_status: dict[str, Any] = {
                'status': 'healthy',
                'timestamp': datetime.now().isoformat(),
                'disk_free_mb': round(disk_free_mb, 2),
                'memory_usage_percent': round(memory_usage_percent, 2),
                'directories': {
                    'upload': upload_exists,
                    'output': output_exists
                },
                'response_time_ms': round(response_time, 2)
            }

            # Warn if disk space is low
            if disk_free_mb < 100:  # Less than 100MB
                health_status['status'] = 'warning'
                health_status['message'] = 'Disk space is low'

            # Warn if memory usage is high
            if memory_usage_percent > 90:  # More than 90%
                health_status['status'] = 'warning'
                health_status['message'] = 'Memory usage is high'

            app.logger.info(f'Health check: {health_status}')
            app.logger.debug('Function end: health_check (success)')
            return jsonify(health_status)

        except Exception as e:
            app.logger.error(f'Health check error: {str(e)}')
            app.logger.debug('Function end: health_check (failed)')
            return jsonify({
                'status': 'unhealthy',
                'timestamp': datetime.now().isoformat(),
                'error': str(e)
            }), 500

    # Cleanup on application shutdown
    @app.teardown_appcontext
    def cleanup(exception: Union[Exception, None] = None) -> None:
        app.logger.debug(f'Function start: cleanup(exception={exception})')
        try:
            # Log exception if it occurred
            if exception:
                app.logger.error(f'Application teardown with exception: {str(exception)}')

            # Cleanup resources if necessary
            # e.g., close database connections, delete temporary files
            app.logger.info('Application teardown completed')

        except Exception as cleanup_error:
            app.logger.error(f'Error during teardown cleanup: {str(cleanup_error)}')
        finally:
            app.logger.debug('Function end: cleanup (success/finally)')

    app.logger.debug('Function end: create_app (success)')
 
    return app, socketio

# Run the application
if __name__ == '__main__':
    # app = create_app()
    app: Flask
    socketio: SocketIO
    app, socketio = create_app(DevelopmentConfig)
    socketio.run(app, debug=True, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)