# Copyright 2025 npz35
#
# See the NOTICE file for this project for license details.
# This file may not be used except in accordance with the NOTICE.

import os
import pytest
from unittest.mock import patch, MagicMock
from flask import Flask
from app.main import create_app
from app.config import TestingConfig
from app.data_model import Area, BBoxRL
from app.pdf_area_separator import PdfAreaSeparator
from app.translator import Translator
from werkzeug.datastructures import FileStorage
import io
from reportlab.lib.colors import Color

@pytest.fixture
def app():
    """Create and configure a new app instance for each test."""
    app, _ = create_app(TestingConfig)
    app.config.update({
        "TESTING": True,
    })
    yield app

@pytest.fixture
def client(app: Flask):
    """A test client for the app."""
    return app.test_client()

def test_translate_text_endpoint_success(client):
    """Test the /translate_text endpoint with a sample PDF."""
    with patch('app.main.PdfAreaSeparator') as MockPdfAreaSeparator, \
         patch('app.main.Translator') as MockTranslator, \
         patch('app.main.os.path.exists', return_value=True), \
         patch('app.main.os.remove') as mock_remove:

        # Mock PdfAreaSeparator
        mock_area_separator_instance = MockPdfAreaSeparator.return_value
        mock_area_separator_instance.extract_area_infos.return_value = [[
            Area(color=Color(1, 0, 0, 1), text="Hello, World!", block_id=1, rect=BBoxRL(x=0, y=0, width=100, height=10), font_info={'font_name': 'Helvetica', 'font_size': 12.0, 'is_bold': False, 'is_italic': False}),
            Area(color=Color(1, 0, 0, 1), text="This is a test.", block_id=2, rect=BBoxRL(x=0, y=10, width=100, height=10), font_info={'font_name': 'Helvetica', 'font_size': 12.0, 'is_bold': False, 'is_italic': False})
        ]]
        mock_area_separator_instance.create_colored_pdf.return_value = "/path/to/translated_text_blocks.pdf"

        # Mock Translator
        mock_translator_instance = MockTranslator.return_value
        mock_translator_instance.translate_texts.return_value = [
            {'translated_text': "こんにちは、世界！"},
            {'translated_text': "これはテストです。"}
        ]

        # Mock file operations for saving the uploaded file and writing output files
        mock_file_storage = MagicMock(spec=FileStorage)
        mock_file_storage.filename = 'sample.pdf'
        # Read the actual sample.pdf content
        with open('uploads/sample.pdf', 'rb') as f:
            sample_pdf_content = f.read()
        mock_file_storage.stream = io.BytesIO(sample_pdf_content) # Use BytesIO for stream
        mock_file_storage.save.side_effect = lambda x: None # Don't actually save, just simulate

        # Use the actual sample.pdf for the client post request
        with open('uploads/sample.pdf', 'rb') as f:
            data = {
                'file': (f, 'sample.pdf')
            }
            response = client.post('/translate_text', data=data, content_type='multipart/form-data')

        assert response.status_code == 200
        json_data = response.get_json()
        assert json_data['success'] is True
        assert 'text_filename' in json_data
        assert 'filename' in json_data
        assert 'processing_time' in json_data
        assert json_data['translated_text_blocks'] == 2

        MockPdfAreaSeparator.assert_called_once()
        mock_area_separator_instance.extract_area_infos.assert_called_once()
        MockTranslator.assert_called_once()
        mock_translator_instance.translate_texts.assert_called_once_with(["Hello, World!", "This is a test."])
        mock_area_separator_instance.create_colored_pdf.assert_called_once()

def test_translate_text_endpoint_translation_error(client):
    with patch('app.main.PdfAreaSeparator') as MockPdfAreaSeparator, \
         patch('app.main.Translator') as MockTranslator, \
         patch('app.main.os.path.exists', return_value=True), \
         patch('app.main.os.remove') as mock_remove:

        mock_area_separator_instance = MockPdfAreaSeparator.return_value
        mock_area_separator_instance.extract_area_infos.return_value = [[
            Area(color=Color(1, 0, 0, 1), text="Hello, World!", block_id=1, rect=BBoxRL(x=0, y=0, width=100, height=10))
        ]]
        mock_area_separator_instance.create_colored_pdf.return_value = "/path/to/translated_text_blocks.pdf"

        mock_translator_instance = MockTranslator.return_value
        mock_translator_instance.translate_texts.side_effect = Exception("Translation service failed")

        # Use the actual sample.pdf for the client post request
        with open('uploads/sample.pdf', 'rb') as f:
            data = {
                'file': (f, 'sample.pdf')
            }
            response = client.post('/translate_text', data=data, content_type='multipart/form-data')

        assert response.status_code == 302 # Redirect to index
