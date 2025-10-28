# Copyright 2025 npz35
#
# See the NOTICE file for this project for license details.
# This file may not be used except in accordance with the NOTICE.

import os
import pytest
from unittest.mock import patch, MagicMock
from flask import Flask
from werkzeug.datastructures import FileStorage # FileStorageをインポートするのだ
from app.main import create_app
import io # ioモジュールをインポートするのだ
from app.config import TestingConfig
from app.data_model import Area, BBoxRL
from app.pdf_text_layout import PdfTextLayout
from reportlab.lib.colors import Color

@pytest.fixture
def app():
    """Create and configure a new app instance for each test."""
    app, _ = create_app(TestingConfig)
    app.config.update({
        "TESTING": True,
        "JAPANESE_FONT_PATH": "static/fonts/ipaexg.ttf", # テスト用にフォントパスを設定するのだ
        "MIN_FONT_SIZE": 8,
    })
    yield app

@pytest.fixture
def client(app: Flask):
    """A test client for the app."""
    return app.test_client()

@pytest.fixture
def sample_pdf_path():
    """Path to the sample PDF for testing."""
    return 'uploads/sample.pdf'

def test_draw_text_endpoint_success(client, sample_pdf_path):
    """Test the /draw_text endpoint with a sample PDF and mocked dependencies."""
    with patch('app.main.PdfAreaSeparator') as MockPdfAreaSeparator, \
         patch('app.main.Translator') as MockTranslator, \
         patch('app.main.PdfTextLayout') as MockPdfTextLayout, \
         patch('pypdf.PdfReader') as MockPdfReader, \
         patch('pypdf.PdfWriter') as MockPdfWriter, \
         patch('reportlab.pdfgen.canvas.Canvas') as MockCanvas:

        # FileStorageオブジェクトを直接作成するのだ
        # 実際のPDFファイルを読み込むのだ
        # client.postに渡すファイルオブジェクトは、FileStorageインスタンスである必要があるのだ
        # そのため、ここでは実際のファイルを開いてFileStorageにラップするのだ
        pdf_file_content = open(sample_pdf_path, 'rb').read()
        mock_file_storage = FileStorage(
            stream=io.BytesIO(pdf_file_content),
            filename='sample.pdf',
            name='file',
            content_type='application/pdf'
        )

        # Mock PdfAreaSeparator
        mock_area_separator_instance = MockPdfAreaSeparator.return_value
        mock_area_separator_instance.extract_area_infos.return_value = [[
            Area(color=Color(1, 0, 0, 1), text="Hello, World!", rect=BBoxRL(x=100, y=700, width=100, height=20), block_id=0, font_info={'font_name': 'Helvetica', 'font_size': 12.0, 'is_bold': False, 'is_italic': False}),
            Area(color=Color(1, 0, 0, 1), text="This is a test.", rect=BBoxRL(x=100, y=680, width=100, height=20), block_id=1, font_info={'font_name': 'Helvetica', 'font_size': 12.0, 'is_bold': False, 'is_italic': False})
        ]]

        # Mock Translator
        mock_translator_instance = MockTranslator.return_value
        mock_translator_instance.translate_texts.return_value = [
            {'translated_text': 'こんにちは、世界！'},
            {'translated_text': 'これはテストです。'}
        ]

        # Mock PdfTextLayout
        mock_pdf_text_layout_instance = MockPdfTextLayout.return_value
        mock_pdf_text_layout_instance.draw_white_rectangle.return_value = None
        mock_pdf_text_layout_instance.draw_translated_text.return_value = None

        # Mock pypdf components
        mock_pdf_reader_instance = MockPdfReader.return_value
        mock_pdf_reader_instance.pages = [MagicMock(), MagicMock()] # Simulate two pages
        mock_pdf_writer_instance = MockPdfWriter.return_value
        mock_pdf_writer_instance.add_page.return_value = None
        mock_pdf_writer_instance.write.return_value = None

        # Mock canvas and BytesIO
        mock_canvas_instance = MockCanvas.return_value
        mock_canvas_instance.showPage.return_value = None
        mock_canvas_instance.save.return_value = None

        response = client.post('/draw_text', data={'file': mock_file_storage})

        assert response.status_code == 200
        json_data = response.get_json()
        assert json_data['success'] is True
        assert 'filename' in json_data
        assert 'output_path' in json_data
        assert 'processing_time' in json_data
        assert json_data['drawn_text_blocks'] == 2

        MockPdfAreaSeparator.assert_called_once_with(client.application.config['OUTPUT_FOLDER'])
        mock_area_separator_instance.extract_area_infos.assert_called_once()
        MockTranslator.assert_called_once()
        mock_translator_instance.translate_texts.assert_called_once_with(["Hello, World!", "This is a test."])
        MockPdfTextLayout.assert_called_once_with(
            font_path=client.application.config['JAPANESE_FONT_PATH'],
            min_font_size=client.application.config['MIN_FONT_SIZE']
        )
        assert mock_pdf_text_layout_instance.draw_white_rectangle.call_count == 2 # Two blocks
        assert mock_pdf_text_layout_instance.draw_translated_text.call_count == 2 # Two blocks
        mock_pdf_writer_instance.write.assert_called_once()

def test_draw_text_endpoint_no_file(client):
    """Test /draw_text with no file uploaded."""
    response = client.post('/draw_text', data={})
    assert response.status_code == 302 # Redirect to index
    with client.session_transaction() as session:
        assert 'No file selected' in session['_flashes'][0][1]

def test_draw_text_endpoint_empty_filename(client):
    """Test /draw_text with an empty filename."""
    empty_file_storage = FileStorage(
        stream=io.BytesIO(b''),
        filename='',
        name='file',
        content_type='application/pdf'
    )
    response = client.post('/draw_text', data={'file': empty_file_storage})
    assert response.status_code == 302 # Redirect to index
    with client.session_transaction() as session:
        assert 'No file selected' in session['_flashes'][0][1]

def test_draw_text_endpoint_invalid_extension(client, sample_pdf_path):
    """Test /draw_text with an invalid file extension."""
    invalid_ext_file_content = open(sample_pdf_path, 'rb').read()
    invalid_ext_file_storage = FileStorage(
        stream=io.BytesIO(invalid_ext_file_content),
        filename='test.txt',
        name='file',
        content_type='text/plain'
    )
    response = client.post('/draw_text', data={'file': invalid_ext_file_storage})
    assert response.status_code == 302 # Redirect to index
    with client.session_transaction() as session:
        assert 'Only PDF files are supported' in session['_flashes'][0][1]

def test_draw_text_endpoint_file_too_large(client, tmp_path):
    """Test /draw_text with a file exceeding the size limit."""
    large_file_path = tmp_path / "large.pdf"
    with open(large_file_path, 'wb') as f:
        f.write(os.urandom(TestingConfig.MAX_CONTENT_LENGTH + 1)) # 16MB + 1 byte

    large_file_path = tmp_path / "large.pdf"
    with open(large_file_path, 'wb') as f:
        f.write(os.urandom(TestingConfig.MAX_CONTENT_LENGTH + 1)) # 16MB + 1 byte

    large_file_content = open(large_file_path, 'rb').read()
    large_file_storage = FileStorage(
        stream=io.BytesIO(large_file_content),
        filename='large.pdf',
        name='file',
        content_type='application/pdf'
    )
    response = client.post('/draw_text', data={'file': large_file_storage})
    assert response.status_code == 302 # Redirect to index
    with client.session_transaction() as session:
        assert 'File size exceeds 16MB for text drawing' in session['_flashes'][0][1]

def test_draw_text_endpoint_disk_space_error(client, sample_pdf_path):
    """Test /draw_text with insufficient disk space."""
    with patch('psutil.disk_usage') as mock_disk_usage:
        mock_disk_usage.return_value.free = TestingConfig.REQUIRED_DISK_SPACE - 1 # Simulate insufficient space
        pdf_file_content = open(sample_pdf_path, 'rb').read()
        mock_file_storage = FileStorage(
            stream=io.BytesIO(pdf_file_content),
            filename='sample.pdf',
            name='file',
            content_type='application/pdf'
        )
        response = client.post('/draw_text', data={'file': mock_file_storage})
        assert response.status_code == 302 # Redirect to index
        with client.session_transaction() as session:
            assert 'Insufficient disk space. Please free up some space.' in session['_flashes'][0][1]

def test_draw_text_endpoint_area_separator_error(client, sample_pdf_path):
    """Test /draw_text when PdfAreaSeparator raises an exception."""
    with patch('app.main.PdfAreaSeparator') as MockPdfAreaSeparator:
        mock_area_separator_instance = MockPdfAreaSeparator.return_value
        mock_area_separator_instance.extract_area_infos.side_effect = Exception("Failed to extract areas")

        pdf_file_content = open(sample_pdf_path, 'rb').read()
        mock_file_storage = FileStorage(
            stream=io.BytesIO(pdf_file_content),
            filename='sample.pdf',
            name='file',
            content_type='application/pdf'
        )
        response = client.post('/draw_text', data={'file': mock_file_storage})
        assert response.status_code == 302 # Redirect to index
        with client.session_transaction() as session:
            assert 'An error occurred during text drawing' in session['_flashes'][0][1] # Generic error message for now

def test_draw_text_endpoint_translator_error(client, sample_pdf_path):
    """Test /draw_text when Translator raises an exception."""
    with patch('app.main.PdfAreaSeparator') as MockPdfAreaSeparator, \
         patch('app.main.Translator') as MockTranslator:
        
        mock_area_separator_instance = MockPdfAreaSeparator.return_value
        mock_area_separator_instance.extract_area_infos.return_value = [[
            Area(color=Color(1, 0, 0, 1), text="Hello, World!", rect=BBoxRL(x=100, y=700, width=100, height=20), block_id=0, font_info={'font_name': 'Helvetica', 'font_size': 12.0, 'is_bold': False, 'is_italic': False})
        ]]

        mock_translator_instance = MockTranslator.return_value
        mock_translator_instance.translate_texts.side_effect = Exception("翻訳エラーが発生しました")

        pdf_file_content = open(sample_pdf_path, 'rb').read()
        mock_file_storage = FileStorage(
            stream=io.BytesIO(pdf_file_content),
            filename='sample.pdf',
            name='file',
            content_type='application/pdf'
        )
        response = client.post('/draw_text', data={'file': mock_file_storage})
        assert response.status_code == 302 # Redirect to index
        with client.session_transaction() as session:
            assert 'An error occurred during translation. Please try again later.' in session['_flashes'][0][1]

def test_draw_text_endpoint_pdf_layout_error(client, sample_pdf_path):
    """Test /draw_text when PdfTextLayout raises an exception during drawing."""
    with patch('app.main.PdfAreaSeparator') as MockPdfAreaSeparator, \
         patch('app.main.Translator') as MockTranslator, \
         patch('app.main.PdfTextLayout') as MockPdfTextLayout, \
         patch('pypdf.PdfReader') as MockPdfReader, \
         patch('pypdf.PdfWriter') as MockPdfWriter, \
         patch('reportlab.pdfgen.canvas.Canvas') as MockCanvas:

        mock_area_separator_instance = MockPdfAreaSeparator.return_value
        mock_area_separator_instance.extract_area_infos.return_value = [[
            Area(color=Color(1, 0, 0, 1), text="Hello, World!", rect=BBoxRL(x=100, y=700, width=100, height=20), block_id=0, font_info={'font_name': 'Helvetica', 'font_size': 12.0, 'is_bold': False, 'is_italic': False})
        ]]

        mock_translator_instance = MockTranslator.return_value
        mock_translator_instance.translate_texts.return_value = [
            {'translated_text': 'こんにちは、世界！'}
        ]

        mock_pdf_text_layout_instance = MockPdfTextLayout.return_value
        mock_pdf_text_layout_instance.draw_translated_text.side_effect = Exception("Failed to draw text")

        mock_pdf_reader_instance = MockPdfReader.return_value
        mock_pdf_reader_instance.pages = [MagicMock()]
        mock_pdf_writer_instance = MockPdfWriter.return_value
        mock_pdf_writer_instance.add_page.return_value = None
        mock_pdf_writer_instance.write.return_value = None

        mock_canvas_instance = MockCanvas.return_value
        mock_canvas_instance.showPage.return_value = None
        mock_canvas_instance.save.return_value = None

        pdf_file_content = open(sample_pdf_path, 'rb').read()
        mock_file_storage = FileStorage(
            stream=io.BytesIO(pdf_file_content),
            filename='sample.pdf',
            name='file',
            content_type='application/pdf'
        )
        response = client.post('/draw_text', data={'file': mock_file_storage})
        assert response.status_code == 302 # Redirect to index
        with client.session_transaction() as session:
            assert 'An error occurred during text drawing' in session['_flashes'][0][1]