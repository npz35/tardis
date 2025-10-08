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
import logging
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename
from werkzeug.datastructures import FileStorage
from app.config import Config, DevelopmentConfig
from app.translator import Translator
from app.pdf_document_manager import PdfDocumentManager
from app.figure_extractor import FigureExtractor
from app.utils import setup_logging
from flask import Flask, render_template, request, jsonify, send_file, flash, redirect, url_for, send_from_directory, make_response, Response, current_app
from flask_socketio import SocketIO, emit
from typing import List, Dict, Any, Union, Type, Tuple
from pypdf import PdfReader


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
    
    app.logger.debug(f"Function start: create_app(config_class={config_class.__name__})")

    # Call logging settings from utils
    setup_logging(log_level=app.config['LOG_LEVEL'])
    app.logger.info('Tardis startup')

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

    # PDF upload and translation processing
    @app.route('/upload', methods=['POST'])
    def upload_file() -> Response:
        app.logger.debug("Function start: upload_file()")
        filepath: Union[str, None] = None  # Initialize filepath
        try:
            # Check disk space
            disk_usage: psutil.DiskUsage = psutil.disk_usage(app.config['UPLOAD_FOLDER'])
            if disk_usage.free < Config.REQUIRED_DISK_SPACE:
                raise Exception("Insufficient disk space. Please free up some space.")

            # Check if file exists
            if 'file' not in request.files:
                flash('No file selected')
                app.logger.debug("Function end: upload_file (no file selected)")
                return redirect(request.url)

            file: FileStorage = request.files['file']
            if file.filename == '':
                flash('No file selected')
                app.logger.debug("Function end: upload_file (empty filename)")
                return redirect(request.url)

            # Check file extension
            if not file.filename.lower().endswith('.pdf'):
                flash('Only PDF files are supported')
                app.logger.debug("Function end: upload_file (unsupported file type)")
                return redirect(request.url)

            # Check file size (16MB limit)
            file.seek(0, os.SEEK_END)
            file_length: int = file.tell()
            file.seek(0)  # Reset file pointer

            if file_length > Config.MAX_CONTENT_LENGTH:
                raise RequestEntityTooLarge("File size exceeds 16MB")

            app.logger.info(f"file_length: {file_length}")

            # Generate secure filename
            filename: str = secure_filename(file.filename)
            unique_id: str = str(uuid.uuid4())
            temp_filename: str = f"{unique_id}_{filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], temp_filename)

            # Save the file
            try:
                file.save(filepath)
                if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                    app.logger.info(f"{filename} was saved successfully: {filepath}")
                else:
                    raise IOError(f"Save completed but file does not exist or size is 0: {filepath}")
            except Exception as e:
                raise IOError(f"Failed to save {filepath}")

            # Start processing
            start_time: float = time.time()
            app.logger.info(f"Processing file: {filename}")

            def progress_callback(percentage: int, step: int):
                current_app.extensions['socketio'].emit('progress', {'percentage': percentage, 'step': step})
                current_app.logger.info(f"Emitted progress: {percentage}% (Step: {step})")

            # Initialize PDF processing modules
            translator: Translator = Translator()

            app.logger.info("Using alternative PDF processing library.")
            # Initialize PdfDocumentManager for new implementation
            pdf_document_manager: PdfDocumentManager = PdfDocumentManager()
            output_path: str = os.path.join(app.config['OUTPUT_FOLDER'], f"translated_{unique_id}.pdf")
            output_path, finish_time, translated_units = pdf_document_manager.create_translated_pdf(
                filepath,
                output_path,
                translator,
                temp_filename,
                progress_callback=progress_callback
            )
            processing_time = finish_time - start_time

            # Return filename in JSON format
            app.logger.debug("Function end: upload_file (success)")
            return jsonify({
                'success': True,
                'filename': f"translated_{unique_id}.pdf",
                'output_path': output_path,
                'processingTime': f"{processing_time:.2f} seconds",
                'translatedUnits': len(translated_units)
            })

        except RequestEntityTooLarge as e:
            app.logger.error(f"File size error: {str(e)}")
            flash('File size exceeds 16MB')
            app.logger.debug("Function end: upload_file (RequestEntityTooLarge)")
            return redirect(url_for('index'))
        except Exception as e:
            # Detailed error logging
            app.logger.error(f"Error during processing: {str(e)}")
            app.logger.error(traceback.format_exc())

            # Error message to the user
            error_message: str = 'An error occurred during processing'
            if 'ディスク容量' in str(e):
                error_message = 'Insufficient disk space. Please free up some space.'
            elif 'テキストを抽出できませんでした' in str(e):
                error_message = 'Failed to extract text from PDF. The file may be corrupted.'
            elif 'PDFの解析または要素抽出中にエラーが発生しました' in str(e):
                error_message = 'An error occurred during PDF parsing. Please check the file format.'
            elif '翻訳' in str(e):
                error_message = 'An error occurred during translation. Please try again later.'

            flash(error_message)
            app.logger.debug("Function end: upload_file (failed)")
            return redirect(url_for('index'))
        finally:
            # Cleanup temporary files
            if filepath and os.path.exists(filepath):
                try:
                    os.remove(filepath)
                    app.logger.info(f"Cleaned up temp file: {filepath}")
                except Exception as cleanup_error:
                    app.logger.error(f"Failed to cleanup temp file {filepath}: {str(cleanup_error)}")
            app.logger.debug("Function end: upload_file (success/finally)")
 
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

    # Extract figures from PDF
    @app.route('/extract_figures', methods=['POST'])
    def extract_figures_from_pdf() -> Response:
        app.logger.debug("Function start: extract_figures_from_pdf()")
        filepath: Union[str, None] = None
        try:
            # Check disk space
            disk_usage: psutil.DiskUsage = psutil.disk_usage(app.config['UPLOAD_FOLDER'])
            if disk_usage.free < Config.REQUIRED_DISK_SPACE:
                raise Exception("Insufficient disk space. Please free up some space.")

            # Check if file exists
            if 'file' not in request.files:
                flash('No file selected')
                app.logger.debug("Function end: extract_figures_from_pdf (no file selected)")
                return redirect(request.url)

            file: FileStorage = request.files['file']
            if file.filename == '':
                flash('No file selected')
                app.logger.debug("Function end: extract_figures_from_pdf (empty filename)")
                return redirect(request.url)

            # Check file extension
            if not file.filename.lower().endswith('.pdf'):
                flash('Only PDF files are supported')
                app.logger.debug("Function end: extract_figures_from_pdf (unsupported file type)")
                return redirect(request.url)

            # Check file size (16MB limit)
            file.seek(0, os.SEEK_END)
            file_length: int = file.tell()
            file.seek(0)  # Reset file pointer

            if file_length > Config.MAX_CONTENT_LENGTH:
                raise RequestEntityTooLarge("File size exceeds 16MB")

            # Generate secure filename
            filename: str = secure_filename(file.filename)
            unique_id: str = str(uuid.uuid4())
            temp_filename: str = f"figures_{unique_id}_{filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], temp_filename)

            # Save the file
            file.save(filepath)
            app.logger.info(f"File uploaded for figure extraction: {filename} -> {temp_filename}")

            # Start processing
            start_time: float = time.time()
            app.logger.info(f"Extracting figures from file: {filename}")

            # Log the number of pages in the PDF
            try:
                reader = PdfReader(filepath)
                num_pages = len(reader.pages)
                app.logger.info(f"Uploaded PDF has {num_pages} pages.")
            except Exception as pdf_read_error:
                app.logger.error(f"Failed to read PDF pages for logging: {pdf_read_error}")

            # Initialize FigureExtractor
            figure_extractor: FigureExtractor = FigureExtractor(app.config['JAPANESE_FONT_PATH'])
            figures: List[Dict[str, Any]] = figure_extractor.extract_figures(filepath)

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

            output_path: str = os.path.join(app.config['OUTPUT_FOLDER'], f"figures_{unique_id}.pdf")
            figure_extractor.create_figure_pdf(figures, output_path)

            processing_time: float = time.time() - start_time
            app.logger.info(f"Figure extraction completed in {processing_time:.2f} seconds")
            app.logger.info(f"Figure PDF created: {output_path}")

            app.logger.debug("Function end: extract_figures_from_pdf (success)")
            return jsonify({
                'success': True,
                'filename': f"figures_{unique_id}.pdf",
                'output_path': output_path,
                'processingTime': f"{processing_time:.2f} seconds",
                'extractedFigures': len(figures)
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