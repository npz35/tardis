# Copyright 2025 npz35
#
# See the NOTICE file for this project for license details.
# This file may not be used except in accordance with the NOTICE.

import os
import uuid
from datetime import datetime
import traceback
import psutil
import time
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename
from werkzeug.datastructures import FileStorage
from app.config import Config, DevelopmentConfig
from app.data_model import PageAnalyzeData
from app.pdf_figure_extractor import PdfFigureExtractor
from app.pdf_area_separator import PdfAreaSeparator
from app.pdf_column_separator import PdfColumnSeparator
from app.pdf_text_extractor import PdfTextExtractor
from app.translator import Translator
from app.pdf_text_layout import PdfTextLayout
from app.pdf_text_manager import PdfTextManager # PdfTextManagerをインポートするのだ
from app.data_model import BBox, TextBlock, FontInfo, Area
from app.utils import setup_logging
from flask import Flask, render_template, request, jsonify, send_file, flash, redirect, url_for, send_from_directory, make_response, Response, current_app
from flask_socketio import SocketIO
from typing import List, Dict, Any, Union, Type, Optional # Optionalをインポートするのだ
from pypdf import PdfReader
import io


def _handle_file_upload(file: FileStorage, app: Flask) -> Dict[str, str]:
    """
    Handles the secure saving of an uploaded file to a unique directory.

    Args:
        file: The FileStorage object representing the uploaded file.
        app: The Flask application instance.

    Returns:
        A dictionary containing:
            - 'filepath': The full path to the saved file.
            - 'unique_id': The unique ID generated for the upload directory.
            - 'filename': The secure filename of the uploaded file.
    """
    filename: str = secure_filename(file.filename)
    unique_id: str = str(uuid.uuid4())
    upload_dir: str = os.path.join(app.config['UPLOAD_FOLDER'], unique_id)
    os.makedirs(upload_dir, exist_ok=True)
    filepath = os.path.join(upload_dir, filename)

    file.save(filepath)
    app.logger.info(f"File uploaded: {filename} -> {filepath}")
    return {'filepath': filepath, 'unique_id': unique_id, 'filename': filename}


def _validate_upload_request(caller_function_name: str) -> Union[FileStorage, Response]:
    # Check disk space
    disk_usage: psutil.DiskUsage = psutil.disk_usage(current_app.config['UPLOAD_FOLDER'])
    if disk_usage.free < Config.REQUIRED_DISK_SPACE:
        raise Exception("Insufficient disk space. Please free up some space.")

    # Check if file exists
    if 'file' not in request.files:
        flash('No file selected')
        current_app.logger.debug(f"Function end: {caller_function_name} (no file selected)")
        return redirect(request.url)

    file: FileStorage = request.files['file']
    if file.filename == '':
        flash('No file selected')
        current_app.logger.debug(f"Function end: {caller_function_name} (empty filename)")
        return redirect(request.url)
    
    # Check file extension
    if not file.filename.lower().endswith('.pdf'):
        flash('Only PDF files are supported')
        current_app.logger.debug(f"Function end: {caller_function_name} (unsupported file type)")
        return redirect(request.url)

    # Check file size (16MB limit)
    file.seek(0, os.SEEK_END)
    file_length: int = file.tell()
    file.seek(0)  # Reset file pointer

    if file_length > Config.MAX_CONTENT_LENGTH:
        raise RequestEntityTooLarge("File size exceeds 16MB")

    current_app.logger.info(f"file_length: {file_length}")
    return file


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

    app.logger.debug(f"Function start: create_app(config_class={config_class.__name__})")
    app.logger.info('Tardis startup')
    app.logger.info(f"LOG_LEVEL={app.config['LOG_LEVEL']}")
    app.logger.info(f"LOG_FILE={app.config['LOG_FILE']}")

    # Create directories
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

    app.logger.debug("Function end: create_app (success)")

    # Routes
    @app.route('/')
    def index() -> Response:
        app.logger.debug("Function start: index()")
        app.logger.debug("Function end: index (success)")
        return render_template('index.html')
    
    # Add column_separation endpoint
    @app.route('/column_separation', methods=['POST'])
    def column_separation_from_pdf() -> Response:
        app.logger.debug("Function start: column_separation_from_pdf()")
        filepath: Union[str, None] = None
        try:
            file: FileStorage = _validate_upload_request(caller_function_name='column_separation_from_pdf')

            uploaded_file_info: Dict[str, str] = _handle_file_upload(file, app)
            filepath = uploaded_file_info['filepath']
            filename = uploaded_file_info['filename']
            unique_id = uploaded_file_info['unique_id']

            # Start processing
            start_time: float = time.time()
            app.logger.info(f"Separating columns in file: {filename}")

            # Initialize PdfColumnSeparator module and call its method
            pdf_column_separator: PdfColumnSeparator = PdfColumnSeparator(app.config['OUTPUT_FOLDER'])
            analyze_pages_data: List[PageAnalyzeData] = pdf_column_separator.analyze_separation_lines(filepath)
            pdf_output_filename = f"column_separation_{unique_id}.pdf"
            output_path: str = pdf_column_separator.draw_separation_lines(analyze_pages_data, pdf_output_filename)

            processing_time: float = time.time() - start_time
            app.logger.info(f"Column column_separation completed in {processing_time:.2f} seconds")
            app.logger.info(f"column_separation PDF created: {output_path}")

            app.logger.debug("Function end: column_separation_from_pdf (success)")
            return jsonify({
                'success': True,
                'filename': pdf_output_filename,
                'output_path': output_path,
                'processing_time': f"{processing_time:.2f} seconds",
            })

        except RequestEntityTooLarge as e:
            app.logger.error(f"File size error during column_separation: {str(e)}")
            flash('File size exceeds 16MB for column_separation')
            app.logger.debug("Function end: column_separation_from_pdf (RequestEntityTooLarge)")
            return redirect(url_for('index'))
        except Exception as e:
            # Detailed error logging
            app.logger.error(f"Error during column_separation: {str(e)}")
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
            app.logger.debug("Function end: column_separation_from_pdf (failed)")
            return redirect(url_for('index'))
        finally:
            # Cleanup temporary files
            if filepath and os.path.exists(filepath):
                try:
                    os.remove(filepath)
                    app.logger.info(f"Cleaned up temp file after column_separation: {filepath}")
                except Exception as cleanup_error:
                    app.logger.error(f"Failed to cleanup temp file {filepath} after column_separation: {str(cleanup_error)}")
            app.logger.debug("Function end: column_separation_from_pdf (success/finally)")

    # Area Coloring endpoint
    @app.route('/area_separation', methods=['POST'])
    def area_separation_from_pdf() -> Response:
        app.logger.debug("Function start: area_separation_from_pdf()")
        filepath: Union[str, None] = None
        try:
            file: FileStorage = _validate_upload_request(caller_function_name='area_separation_from_pdf')

            uploaded_file_info: Dict[str, str] = _handle_file_upload(file, app)
            filepath = uploaded_file_info['filepath']
            filename = uploaded_file_info['filename']
            unique_id = uploaded_file_info['unique_id']

            # Start processing
            start_time: float = time.time()
            app.logger.info(f"Coloring areas in file: {filename}")

            # Initialize PdfAreaSeparator module and call its method
            pdf_area_separator: PdfAreaSeparator = PdfAreaSeparator(app.config['OUTPUT_FOLDER'])
            pdf_output_filename = f"area_separation_{unique_id}.pdf"
            output_path: str = pdf_area_separator.create_colored_pdf(filepath, pdf_output_filename)

            processing_time: float = time.time() - start_time
            app.logger.info(f"Area coloring completed in {processing_time:.2f} seconds")
            app.logger.info(f"Area colored PDF created: {output_path}")

            app.logger.debug("Function end: area_separation_from_pdf (success)")
            return jsonify({
                'success': True,
                'filename': pdf_output_filename,
                'output_path': output_path,
                'processing_time': f"{processing_time:.2f} seconds",
            })

        except RequestEntityTooLarge as e:
            app.logger.error(f"File size error during area coloring: {str(e)}")
            flash('File size exceeds 16MB for area coloring')
            app.logger.debug("Function end: area_separation_from_pdf (RequestEntityTooLarge)")
            return redirect(url_for('index'))
        except Exception as e:
            # Detailed error logging
            app.logger.error(f"Error during area coloring: {str(e)}")
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
            app.logger.debug("Function end: area_separation_from_pdf (failed)")
            return redirect(url_for('index'))
        finally:
            # Cleanup temporary files
            if filepath and os.path.exists(filepath):
                try:
                    os.remove(filepath)
                    app.logger.info(f"Cleaned up temp file after area coloring: {filepath}")
                except Exception as cleanup_error:
                    app.logger.error(f"Failed to cleanup temp file {filepath} after area coloring: {str(cleanup_error)}")
            app.logger.debug("Function end: area_separation_from_pdf (success/finally)")

    # Extract text from PDF
    @app.route('/extract_text', methods=['POST'])
    def extract_text_from_pdf() -> Response:
        app.logger.debug("Function start: extract_text_from_pdf()")
        filepath: Union[str, None] = None
        text_output_filepath: Union[str, None] = None
        pdf_output_filepath: Union[str, None] = None
        try:
            file: FileStorage = _validate_upload_request(caller_function_name='extract_text_from_pdf')

            uploaded_file_info: Dict[str, str] = _handle_file_upload(file, app)
            filepath = uploaded_file_info['filepath']
            filename = uploaded_file_info['filename']
            unique_id = uploaded_file_info['unique_id']

            # Start processing
            start_time: float = time.time()
            app.logger.info(f"Extracting text blocks from file: {filename}")

            # Initialize PdfAreaSeparator module to get text block information
            pdf_area_separator: PdfAreaSeparator = PdfAreaSeparator(app.config['OUTPUT_FOLDER'])
            
            all_page_areas = pdf_area_separator.extract_area_infos(filepath)

            extracted_text_data: List[Dict[str, Any]] = []
            for page_num, page_areas in enumerate(all_page_areas):
                for area in page_areas:
                    if area.text and area.block_id is not None:
                        extracted_text_data.append({
                            'page_number': page_num + 1,
                            'block_id': area.block_id,
                            'text': area.text,
                            'bbox': (area.rect.x, area.rect.y, area.rect.x + area.rect.width, area.rect.y + area.rect.height)
                        })
            
            app.logger.info(f"extracted_text_data size: {len(extracted_text_data)}")

            # Generate text file
            text_output_filename = f"extracted_text_{unique_id}.txt"
            text_output_filepath = os.path.join(app.config['OUTPUT_FOLDER'], text_output_filename)
            with open(text_output_filepath, 'w', encoding='utf-8') as f:
                for item in extracted_text_data:
                    f.write(f"Block {item['block_id']} (Page {item['page_number']}):\n")
                    f.write(f"{item['text']}\n\n")
            app.logger.info(f"Text file created: {text_output_filepath}")

            if not os.path.exists(text_output_filepath):
                raise Exception(f"Not found {text_output_filepath}.")

            # Generate PDF with colored areas and block IDs
            pdf_output_filename = f"extracted_text_blocks_{unique_id}.pdf"
            pdf_output_filepath = pdf_area_separator.create_colored_pdf(filepath, pdf_output_filename)

            processing_time: float = time.time() - start_time
            app.logger.info(f"Text extraction completed in {processing_time:.2f} seconds")
            app.logger.info(f"PDF with colored areas and block IDs created: {pdf_output_filepath}")
 
            app.logger.debug("Function end: extract_text_from_pdf (success)")
            return jsonify({
                'success': True,
                'filename': pdf_output_filename,
                'text_filename': text_output_filename,
                'processing_time': f"{processing_time:.2f} seconds",
                'extracted_text_blocks': len(extracted_text_data),
                'extracted_text_data': extracted_text_data
            })

        except RequestEntityTooLarge as e:
            app.logger.error(f"File size error during text extraction: {str(e)}")
            flash('File size exceeds 16MB for text extraction')
            app.logger.debug("Function end: extract_text_from_pdf (RequestEntityTooLarge)")
            return redirect(url_for('index'))
        except Exception as e:
            # Detailed error logging
            app.logger.error(f"Error during text extraction: {str(e)}")
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
            app.logger.debug("Function end: extract_text_from_pdf (failed)")
            return redirect(url_for('index'))

    # Translate text from PDF
    @app.route('/translate_text', methods=['POST'])
    def translate_text_from_pdf() -> Response:
        app.logger.debug("Function start: translate_text_from_pdf()")
        filepath: Union[str, None] = None
        text_output_filepath: Union[str, None] = None
        pdf_output_filepath: Union[str, None] = None
        try:
            file: FileStorage = _validate_upload_request(caller_function_name='translate_text_from_pdf')

            uploaded_file_info: Dict[str, str] = _handle_file_upload(file, app)
            filepath = uploaded_file_info['filepath']
            filename = uploaded_file_info['filename']
            unique_id = uploaded_file_info['unique_id']

            # Start processing
            start_time: float = time.time()
            app.logger.info(f"Extracting and translating text blocks from file: {filename}")

            # Initialize PdfAreaSeparator module to get text block information
            pdf_area_separator: PdfAreaSeparator = PdfAreaSeparator(app.config['OUTPUT_FOLDER'])
            all_page_areas = pdf_area_separator.extract_area_infos(filepath)

            extracted_text_data: List[Dict[str, Any]] = []
            texts_to_translate: List[str] = []
            for page_num, page_areas in enumerate(all_page_areas):
                for area in page_areas:
                    if area.text and area.block_id is not None:
                        extracted_text_data.append({
                            'page_number': page_num + 1,
                            'block_id': area.block_id,
                            'original_text': area.text,
                            'translated_text': None, # Initialize translated_text
                            'bbox': (area.rect.x, area.rect.y, area.rect.x + area.rect.width, area.rect.y + area.rect.height)
                        })
                        texts_to_translate.append(area.text)
            
            # Group extracted_text_data by page for easier processing and progress tracking
            extracted_data_by_page: Dict[int, List[Dict[str, Any]]] = {}
            for item in extracted_text_data:
                page_num = item['page_number']
                if page_num not in extracted_data_by_page:
                    extracted_data_by_page[page_num] = []
                extracted_data_by_page[page_num].append(item)

            # Initialize translator
            translator: Translator = Translator()
            
            translated_units_count: int = 0 # Counter for total translated units
            total_text_blocks = len(extracted_text_data)
            
            # Define progress callback for translation
            def progress_callback(percentage: int, step: int):
                current_app.extensions['socketio'].emit('progress', {'percentage': percentage, 'step': step})
                current_app.logger.info(f"Emitted progress: {percentage}% (Step: {step})")

            # Perform translation in batches, similar to PdfManager
            all_translated_results: List[Dict[str, Any]] = []
            current_global_block_index = 0
            
            # Progress from 20% to 80% for translation
            translation_start_progress = 20
            translation_end_progress = 80
            
            while current_global_block_index < total_text_blocks:
                # Apply global translation unit limit (TRANSLATION_MAX_UNIT)
                if Config.TRANSLATION_MAX_UNIT is not None:
                    remaining_global_units_capacity = Config.TRANSLATION_MAX_UNIT - translated_units_count
                    if remaining_global_units_capacity <= 0:
                        app.logger.warning(f"Global translation unit limit ({Config.TRANSLATION_MAX_UNIT}) reached. Skipping further translation.")
                        break # Stop processing further blocks
                    
                    # Determine the end index for the current global batch, considering TRANSLATION_MAX_UNIT
                    global_batch_end_index = min(current_global_block_index + remaining_global_units_capacity, total_text_blocks)
                else:
                    global_batch_end_index = total_text_blocks # No global limit

                # Apply per-request translation unit limit (TRANSLATION_MAX_UNIT_PER_REQUEST)
                if Config.TRANSLATION_MAX_UNIT_PER_REQUEST is not None:
                    # Determine the end index for the current request batch
                    request_batch_end_index = min(current_global_block_index + Config.TRANSLATION_MAX_UNIT_PER_REQUEST, global_batch_end_index)
                else:
                    request_batch_end_index = global_batch_end_index # No per-request limit

                batch_texts_to_translate = [item['original_text'] for item in extracted_text_data[current_global_block_index:request_batch_end_index]]
                
                if not batch_texts_to_translate:
                    break # No more texts to translate

                app.logger.info(f"Attempting translation for batch from index {current_global_block_index} to {request_batch_end_index - 1} with {len(batch_texts_to_translate)} units.")
                
                # Calculate current progress percentage for translation step
                current_progress = translation_start_progress + int((current_global_block_index / total_text_blocks) * (translation_end_progress - translation_start_progress))
                progress_callback(current_progress, 3) # Translation in progress (step 3)

                translated_results_for_batch: List[Dict[str, Any]] = translator.translate_texts(batch_texts_to_translate)
                all_translated_results.extend(translated_results_for_batch)
                translated_units_count += len(translated_results_for_batch)
                current_global_block_index = request_batch_end_index
                app.logger.debug(f'current_global_block_index: {current_global_block_index}')

            # Update extracted_text_data with translation results
            for i, result in enumerate(all_translated_results):
                if i < len(extracted_text_data):
                    extracted_text_data[i]['translated_text'] = result.get('translated_text')
                    # You might want to add more details from result if needed, e.g., success, error
            
            if progress_callback:
                progress_callback(translation_end_progress, 3) # Translation completed (80% overall, step 3)

            # Generate text file with original and translated texts
            text_output_filename = f"translated_text_{unique_id}.txt"
            text_output_filepath = os.path.join(app.config['OUTPUT_FOLDER'], text_output_filename)
            with open(text_output_filepath, 'w', encoding='utf-8') as f:
                for item in extracted_text_data:
                    f.write(f"Block {item['block_id']} (Page {item['page_number']}):\n")
                    f.write(f"Original: {item['original_text']}\n")
                    f.write(f"Translated: {item['translated_text']}\n\n")
            app.logger.info(f"Translated text file created: {text_output_filepath}")

            # Generate PDF with colored areas and block IDs (reusing existing functionality)
            # This step is after translation, so it should be part of the final progress
            if progress_callback:
                progress_callback(85, 4) # PDF generation started (85% overall, step 4)

            pdf_output_filename = f"translated_text_blocks_{unique_id}.pdf"
            pdf_output_filepath = pdf_area_separator.create_colored_pdf(filepath, pdf_output_filename)
            
            if progress_callback:
                progress_callback(100, 5) # Completed (100% overall, step 5)

            processing_time: float = time.time() - start_time
            app.logger.info(f"Text translation completed in {processing_time:.2f} seconds")
            app.logger.info(f"PDF with colored areas and block IDs created: {pdf_output_filepath}")
 
            app.logger.debug("Function end: translate_text_from_pdf (success)")
            return jsonify({
                'success': True,
                'filename': pdf_output_filename,
                'text_filename': text_output_filename,
                'processing_time': f"{processing_time:.2f} seconds",
                'translated_text_blocks': len(extracted_text_data)
            })

        except RequestEntityTooLarge as e:
            app.logger.error(f"File size error during text translation: {str(e)}")
            flash('File size exceeds 16MB for text translation')
            app.logger.debug("Function end: translate_text_from_pdf (RequestEntityTooLarge)")
            return redirect(url_for('index'))
        except Exception as e:
            # Detailed error logging
            app.logger.error(f"Error during text translation: {str(e)}")
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
            app.logger.debug("Function end: translate_text_from_pdf (failed)")
            return redirect(url_for('index'))

    # Extract figures from PDF
    @app.route('/extract_figures', methods=['POST'])
    def extract_figures_from_pdf() -> Response:
        app.logger.debug("Function start: extract_figures_from_pdf()")
        filepath: Union[str, None] = None
        try:
            file: FileStorage = _validate_upload_request(caller_function_name='extract_figures_from_pdf')

            uploaded_file_info: Dict[str, str] = _handle_file_upload(file, app)
            filepath = uploaded_file_info['filepath']
            filename = uploaded_file_info['filename']
            unique_id = uploaded_file_info['unique_id']

            # Start processing
            start_time: float = time.time()
            app.logger.info(f"Extracting figures from file: {filename}")

            # Initialize PdfFigureExtractor
            pdf_figure_extractor: PdfFigureExtractor = PdfFigureExtractor(app.config['JAPANESE_FONT_PATH'], app.config['OUTPUT_FOLDER'])
            figures: List[Dict[str, Any]] = pdf_figure_extractor.extract_figures(filepath, unique_id)

            '''
            figures example
            
            [
                {
                    'page': 1,
                    'bbox': (39.7, 511.6, 66.2, 538.1),
                    'figure_type': 'image',
                    'image_data': '/tmp/tmp1yuhuyld/X8.png',
                    'width': 26.5,
                    'height': 26.5,
                    'confidence': 1.0
                },
                {
                    'page': 1, 'bbox': (39.7, 481.8, 66.2, 508.3),
                    'figure_type': 'image',
                    'image_data': '/tmp/tmp3w52ndxd/X8.png',
                    'width': 26.5,
                    'height': 26.5,
                    'confidence': 1.0
                },
            ]
            '''

            app.logger.warning("figures")
            app.logger.warning(figures)

            pdf_output_filename = f"figures_{unique_id}.pdf"
            output_path: str = os.path.join(app.config['OUTPUT_FOLDER'], pdf_output_filename)
            pdf_figure_extractor.create_figure_pdf(figures, output_path, filepath)

            processing_time: float = time.time() - start_time
            app.logger.info(f"Figure extraction completed in {processing_time:.2f} seconds")
            app.logger.info(f"Figure PDF created: {output_path}")

            app.logger.debug("Function end: extract_figures_from_pdf (success)")
            return jsonify({
                'success': True,
                'filename': pdf_output_filename,
                'output_path': output_path,
                'processing_time': f"{processing_time:.2f} seconds",
                'extracted_figures': len(figures)
            })

        except RequestEntityTooLarge as e:
            app.logger.error(f"File size error during figure extraction: {str(e)}")
            flash('File size exceeds 16MB for figure extraction')
            app.logger.debug("Function end: extract_figures_from_pdf (RequestEntityTooLarge)")
            return redirect(url_for('index'))
        except Exception as e:
            # Detailed error logging
            app.logger.error(f"Error during figure extraction: {str(e)}")
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
            app.logger.debug("Function end: extract_figures_from_pdf (failed)")
            return redirect(url_for('index'))
        finally:
            # Cleanup temporary files
            if filepath and os.path.exists(filepath):
                try:
                    os.remove(filepath)
                    app.logger.info(f"Cleaned up temp file after figure extraction: {filepath}")
                except Exception as cleanup_error:
                    app.logger.error(f"Failed to cleanup temp file {filepath} after figure extraction: {str(cleanup_error)}")
            app.logger.debug("Function end: extract_figures_from_pdf (success/finally)")

    # Draw translated text on PDF
    @app.route('/draw_text', methods=['POST'])
    def draw_text_on_pdf() -> Response:
        app.logger.debug("Function start: draw_text_on_pdf()")
        filepath: Union[str, None] = None
        pdf_output_filepath: Union[str, None] = None
        try:
            file: FileStorage = _validate_upload_request(caller_function_name='draw_text_on_pdf')

            uploaded_file_info: Dict[str, str] = _handle_file_upload(file, app)
            filepath = uploaded_file_info['filepath']
            filename = uploaded_file_info['filename']
            unique_id = uploaded_file_info['unique_id']

            # Start processing
            start_time: float = time.time()
            app.logger.info(f"Drawing translated text on PDF for file: {filename}")

            # Initialize PdfAreaSeparator module to get text block information
            pdf_area_separator: PdfAreaSeparator = PdfAreaSeparator(app.config['OUTPUT_FOLDER'])
            all_page_areas: List[List[Area]] = pdf_area_separator.extract_area_infos(filepath)

            extracted_text_data: List[Dict[str, Any]] = []
            texts_to_translate: List[str] = []
            for page_num, page_areas in enumerate(all_page_areas):
                for area in page_areas:
                    if area.text and area.block_id is not None:
                        extracted_text_data.append({
                            'page_number': page_num,
                            'block_id': area.block_id,
                            'original_text': area.text,
                            'translated_text': None, # Initialize translated_text
                            'bbox': (area.rect.x, area.rect.y, area.rect.x + area.rect.width, area.rect.y + area.rect.height),
                            'font_info': area.font_info # Add font information
                        })
                        texts_to_translate.append(area.text)
            
            # Group extracted_text_data by page for easier processing and progress tracking
            extracted_data_by_page: Dict[int, List[Dict[str, Any]]] = {}
            for item in extracted_text_data:
                page_num = item['page_number']
                if page_num not in extracted_data_by_page:
                    extracted_data_by_page[page_num] = []
                extracted_data_by_page[page_num].append(item)

            # Initialize translator
            translator: Translator = Translator()
            
            translated_units_count: int = 0 # Counter for total translated units
            total_text_blocks = len(extracted_text_data)
            
            # Define progress callback for translation
            def progress_callback(percentage: int, step: int):
                current_app.extensions['socketio'].emit('progress', {'percentage': percentage, 'step': step})
                current_app.logger.info(f"Emitted progress: {percentage}% (Step: {step})")

            # Perform translation in batches, similar to PdfManager
            all_translated_results: List[Dict[str, Any]] = []
            current_global_block_index = 0
            
            # Progress from 20% to 80% for translation
            translation_start_progress = 20
            translation_end_progress = 80
            
            while current_global_block_index < total_text_blocks:
                # Apply global translation unit limit (TRANSLATION_MAX_UNIT)
                if Config.TRANSLATION_MAX_UNIT is not None:
                    remaining_global_units_capacity = Config.TRANSLATION_MAX_UNIT - translated_units_count
                    if remaining_global_units_capacity <= 0:
                        app.logger.warning(f"Global translation unit limit ({Config.TRANSLATION_MAX_UNIT}) reached. Skipping further translation.")
                        break # Stop processing further blocks
                    
                    # Determine the end index for the current global batch, considering TRANSLATION_MAX_UNIT
                    global_batch_end_index = min(current_global_block_index + remaining_global_units_capacity, total_text_blocks)
                else:
                    global_batch_end_index = total_text_blocks # No global limit
 
                # Apply per-request translation unit limit (TRANSLATION_MAX_UNIT_PER_REQUEST)
                if Config.TRANSLATION_MAX_UNIT_PER_REQUEST is not None:
                    # Determine the end index for the current request batch
                    request_batch_end_index = min(current_global_block_index + Config.TRANSLATION_MAX_UNIT_PER_REQUEST, global_batch_end_index)
                else:
                    request_batch_end_index = global_batch_end_index # No per-request limit
 
                batch_texts_to_translate = [item['original_text'] for item in extracted_text_data[current_global_block_index:request_batch_end_index]]
                
                if not batch_texts_to_translate:
                    break # No more texts to translate
 
                app.logger.info(f"Attempting translation for batch from index {current_global_block_index} to {request_batch_end_index - 1} with {len(batch_texts_to_translate)} units.")
                
                # Calculate current progress percentage for translation step
                current_progress = translation_start_progress + int((current_global_block_index / total_text_blocks) * (translation_end_progress - translation_start_progress))
                progress_callback(current_progress, 3) # Translation in progress (step 3)
 
                translated_results_for_batch: List[Dict[str, Any]] = translator.translate_texts(batch_texts_to_translate)
                all_translated_results.extend(translated_results_for_batch)
                translated_units_count += len(translated_results_for_batch)
                current_global_block_index = request_batch_end_index
                app.logger.debug(f'current_global_block_index: {current_global_block_index}')

            # Update extracted_text_data with translation results
            for i, result in enumerate(all_translated_results):
                if i < len(extracted_text_data):
                    extracted_text_data[i]['translated_text'] = result.get('translated_text')
            
            if progress_callback:
                progress_callback(translation_end_progress, 3) # Translation completed (80% overall, step 3)

            # Now, draw the translated text onto a new PDF
            if progress_callback:
                progress_callback(85, 4) # PDF generation started (85% overall, step 4)

            pdf_output_filename = f"drawn_translated_text_{unique_id}.pdf"
            pdf_output_filepath = os.path.join(app.config['OUTPUT_FOLDER'], pdf_output_filename)

            # Initialize PdfTextLayout
            pdf_text_layout_processor: PdfTextLayout = PdfTextLayout(
                font_path=app.config['JAPANESE_FONT_PATH'],
                min_font_size=app.config['MIN_FONT_SIZE']
            )

            # Create a new PDF document
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import letter
            from pypdf import PdfReader, PdfWriter

            reader = PdfReader(filepath)
            writer = PdfWriter()

            for page_num, page in enumerate(reader.pages):
                # Create a new canvas for the current page
                packet = io.BytesIO()
                c = canvas.Canvas(packet, pagesize=letter)
                
                # Draw white rectangles over original text areas
                for item in extracted_text_data:
                    if item['page_number'] == page_num:
                        pdf_text_layout_processor.draw_white_rectangle(c, item['bbox'])

                # Draw translated text
                for item in extracted_text_data:
                    if item['page_number'] == page_num and item['translated_text']:
                        pdf_text_layout_processor.draw_translated_text(c, item['translated_text'], item['bbox'], item['font_info'])
                
                c.showPage()
                c.save()

                # Move to the beginning of the StringIO buffer
                packet.seek(0)
                new_pdf = PdfReader(packet)
                page.merge_page(new_pdf.pages[0])
                writer.add_page(page)

            with open(pdf_output_filepath, "wb") as output_pdf:
                writer.write(output_pdf)

            if progress_callback:
                progress_callback(100, 5) # Completed (100% overall, step 5)

            processing_time: float = time.time() - start_time
            app.logger.info(f"Text drawing completed in {processing_time:.2f} seconds")
            app.logger.info(f"PDF with translated text drawn created: {pdf_output_filepath}")
 
            app.logger.debug("Function end: draw_text_on_pdf (success)")
            return jsonify({
                'success': True,
                'filename': pdf_output_filename,
                'output_path': pdf_output_filepath,
                'processing_time': f"{processing_time:.2f} seconds",
                'drawn_text_blocks': len(extracted_text_data)
            })

        except RequestEntityTooLarge as e:
            app.logger.error(f"File size error during text drawing: {str(e)}")
            flash('File size exceeds 16MB for text drawing')
            app.logger.debug("Function end: draw_text_on_pdf (RequestEntityTooLarge)")
            return redirect(url_for('index'))
        except Exception as e:
            # Detailed error logging
            app.logger.error(f"Error during text drawing: {str(e)}")
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
            app.logger.debug("Function end: draw_text_on_pdf (failed)")
            return redirect(url_for('index'))
        finally:
            # Cleanup temporary files
            if filepath and os.path.exists(filepath):
                try:
                    os.remove(filepath)
                    app.logger.info(f"Cleaned up temp file after text drawing: {filepath}")
                except Exception as cleanup_error:
                    app.logger.error(f"Failed to cleanup temp file {filepath} after text drawing: {str(cleanup_error)}")
            if pdf_output_filepath and os.path.exists(pdf_output_filepath) and 'success' not in locals():
                try:
                    os.remove(pdf_output_filepath)
                    app.logger.info(f"Cleaned up generated PDF output file: {pdf_output_filepath}")
                except Exception as cleanup_error:
                    app.logger.error(f"Failed to cleanup generated PDF output file {pdf_output_filepath}: {str(cleanup_error)}")

    # Download translated PDF
    @app.route('/download/<filename>')
    def download_file(filename: str) -> Response:
        app.logger.debug(f"Function start: download_file(filename='{filename}')")
        output_path: Union[str, None] = None
        try:
            # Verify filename safety
            if not secure_filename(filename) == filename:
                raise Exception("Invalid filename")

            output_path = os.path.join(app.config['OUTPUT_FOLDER'], filename)

            # Check if file exists
            if not os.path.exists(output_path):
                raise Exception("File not found")

            # Check file read permissions
            if not os.access(output_path, os.R_OK):
                raise Exception("Cannot read file")

            # Check file size
            file_size: int = os.path.getsize(output_path)
            if file_size == 0:
                raise Exception("File is empty")

            app.logger.info(f"File download: {filename}")
            app.logger.debug("Function end: download_file(filename='{filename}')")
            return send_file(output_path, as_attachment=True)

        except Exception as e:
            app.logger.error(f"Error during download: {str(e)}")
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
            app.logger.debug("Function end: download_file (failed)")
            return redirect(url_for('index'))
        finally:
            # Cleanup after download (if necessary)
            app.logger.debug("Function end: download_file (success/finally)")
            pass

    # Preview translated PDF
    @app.route('/preview/<filename>')
    def preview_file(filename: str) -> Response:
        app.logger.debug(f"Function start: preview_file(filename='{filename}')")
        try:
            # Verify filename safety
            if not secure_filename(filename) == filename:
                raise Exception("Invalid filename")

            output_path: str = os.path.join(app.config['OUTPUT_FOLDER'], filename)

            # Check if file exists
            if not os.path.exists(output_path):
                raise Exception("File not found")

            # Check file read permissions
            if not os.access(output_path, os.R_OK):
                raise Exception("Cannot read file")

            # Check file size
            file_size: int = os.path.getsize(output_path)
            if file_size == 0:
                raise Exception("File is empty")

            app.logger.info(f"File preview: {filename}")
            response: Response = make_response(send_from_directory(app.config['OUTPUT_FOLDER'], filename, mimetype='application/pdf', as_attachment=False, max_age=0))
            response.headers['X-Content-Type-Options'] = 'nosniff'
            app.logger.debug("Function end: preview_file (success)")
            return response

        except Exception as e:
            app.logger.error(f"Error during preview: {str(e)}")
            app.logger.error(traceback.format_exc())
            flash('An error occurred during preview')
            app.logger.debug("Function end: preview_file (failed)")
            return redirect(url_for('index'))

    # Preview text file
    @app.route('/preview_text/<filename>')
    def preview_text_file(filename: str) -> Response:
        app.logger.debug(f"Function start: preview_text_file(filename='{filename}')")
        try:
            # Verify filename safety
            if not secure_filename(filename) == filename:
                raise Exception("Invalid filename")

            output_path: str = os.path.join(app.config['OUTPUT_FOLDER'], filename)

            # Check if file exists
            if not os.path.exists(output_path):
                raise Exception("File not found")

            # Check file read permissions
            if not os.access(output_path, os.R_OK):
                raise Exception("Cannot read file")

            # Check file size
            file_size: int = os.path.getsize(output_path)
            if file_size == 0:
                raise Exception("File is empty")

            app.logger.info(f"Text file preview: {filename}")
            # テキストファイルの内容を直接返すのだ
            with open(output_path, 'r', encoding='utf-8') as f:
                content = f.read()
            response: Response = make_response(content)
            response.headers['Content-Type'] = 'text/plain; charset=utf-8'
            response.headers['X-Content-Type-Options'] = 'nosniff'
            app.logger.debug("Function end: preview_text_file (success)")
            return response

        except Exception as e:
            app.logger.error(f"Error during text preview: {str(e)}")
            app.logger.error(traceback.format_exc())
            flash('An error occurred during text preview')
            app.logger.debug("Function end: preview_text_file (failed)")
            return redirect(url_for('index'))

    # Health check
    @app.route('/health')
    def health_check() -> Response:
        app.logger.debug("Function start: health_check()")
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
            test_response: str = "OK"
            response_time: float = (time.time() - start_time) * 1000  # milliseconds

            health_status: Dict[str, Any] = {
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

            app.logger.info(f"Health check: {health_status}")
            app.logger.debug("Function end: health_check (success)")
            return jsonify(health_status)

        except Exception as e:
            app.logger.error(f"Health check error: {str(e)}")
            app.logger.debug("Function end: health_check (failed)")
            return jsonify({
                'status': 'unhealthy',
                'timestamp': datetime.now().isoformat(),
                'error': str(e)
            }), 500

    # Cleanup on application shutdown
    @app.teardown_appcontext
    def cleanup(exception: Union[Exception, None] = None) -> None:
        app.logger.debug(f"Function start: cleanup(exception={exception})")
        try:
            # Log exception if it occurred
            if exception:
                app.logger.error(f"Application teardown with exception: {str(exception)}")

            # Cleanup resources if necessary
            # e.g., close database connections, delete temporary files
            app.logger.info("Application teardown completed")

        except Exception as cleanup_error:
            app.logger.error(f"Error during teardown cleanup: {str(cleanup_error)}")
        finally:
            app.logger.debug("Function end: cleanup (success/finally)")

    app.logger.debug("Function end: create_app (success)")
 
    return app, socketio

# Run the application
if __name__ == '__main__':
    # app = create_app()
    app: Flask
    socketio: SocketIO
    app, socketio = create_app(DevelopmentConfig)
    socketio.run(app, debug=True, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)