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
from app.data_model import Area, BBox, TextArea, TextPermutation, TranslationResponse
from app.pdf_area_separator import PdfAreaSeparator
from app.translator import Translator
from werkzeug.datastructures import FileStorage
import io
from reportlab.lib.colors import Color

@pytest.fixture
def app():
    '''Create and configure a new app instance for each test.'''
    app, _ = create_app(TestingConfig)
    app.config.update({
        'TESTING': True,
    })
    yield app

@pytest.fixture
def client(app: Flask):
    '''A test client for the app.'''
    return app.test_client()

class TestTranslateTextEndpoint:
    def test_translate_text_endpoint_success(self, client):
        '''Test the /translate_text endpoint with a sample PDF.'''
        # 1. Upload the file first to get filename and unique_id
        with open('samples/sample.pdf', 'rb') as f:
            upload_data = {'file': (f, 'sample.pdf')}
            upload_response = client.post('/upload', data=upload_data, content_type='multipart/form-data')
        
        assert upload_response.status_code == 200
        upload_json = upload_response.get_json()
        assert upload_json['success'] is True
        assert 'filename' in upload_json
        assert 'unique_id' in upload_json
        
        filename = upload_json['filename']
        unique_id = upload_json['unique_id']

        with patch('app.main.PdfplumberAnalyzer') as MockPdfplumberAnalyzer, \
             patch('app.main.PdfAreaSeparator') as MockPdfAreaSeparator, \
             patch('app.main.Translator') as MockTranslator, \
             patch('app.main.os.path.exists', return_value=True), \
             patch('app.main.os.remove') as mock_remove:

            # Mock PdfplumberAnalyzer
            mock_pdfplumber_analyzer_instance = MockPdfplumberAnalyzer.return_value
            mock_pdfplumber_analyzer_instance.extract_textpermutations.return_value = [
                [
                    TextPermutation(area=TextArea(blocks=[], bbox=BBox(x0=0, y0=0, x1=100, y1=10), page_number=1), text='Hello, World!', page_number=1),
                    TextPermutation(area=TextArea(blocks=[], bbox=BBox(x0=0, y0=10, x1=100, y1=20), page_number=1), text='This is a test.', page_number=1)
                ]
            ]

            # Mock PdfAreaSeparator (still needed for create_colored_pdf)
            mock_area_separator_instance = MockPdfAreaSeparator.return_value
            mock_area_separator_instance.create_colored_pdf.return_value = '/path/to/translated_text_blocks.pdf'

            # Mock Translator
            mock_translator_instance = MockTranslator.return_value
            mock_translator_instance.translate_texts.return_value = [
                TranslationResponse(original_text='Hello, World!', translated_text='こんにちは、世界！', source_lang='English', target_lang='Japanese', model='mock-model'),
                TranslationResponse(original_text='This is a test.', translated_text='これはテストです。', source_lang='English', target_lang='Japanese', model='mock-model')
            ]
            
            # 2. Call /translate_text with the obtained filename and unique_id
            translate_text_data = {
                'filename': filename,
                'unique_id': unique_id
            }
            response = client.post('/translate_text', data=translate_text_data)

            assert response.status_code == 200
            json_data = response.get_json()
            assert json_data['success'] is True
            assert 'text_filename' in json_data
            assert 'filename' in json_data
            assert 'processing_time' in json_data
            assert json_data['translated_units'] == 2

            MockPdfplumberAnalyzer.assert_called_once()
            mock_pdfplumber_analyzer_instance.extract_textpermutations.assert_called_once()
            MockTranslator.assert_called_once()
            mock_translator_instance.translate_texts.assert_called_once_with(['Hello, World!', 'This is a test.'])
            MockPdfAreaSeparator.assert_called() # create_colored_pdfはまだPdfAreaSeparatorを使うのだ
            mock_area_separator_instance.create_colored_pdf.assert_called_once()

    def test_translate_text_endpoint_translation_error(self, client):
        # 1. Upload the file first to get filename and unique_id
        with open('samples/sample.pdf', 'rb') as f:
            upload_data = {'file': (f, 'sample.pdf')}
            upload_response = client.post('/upload', data=upload_data, content_type='multipart/form-data')
        
        assert upload_response.status_code == 200
        upload_json = upload_response.get_json()
        assert upload_json['success'] is True
        
        filename = upload_json['filename']
        unique_id = upload_json['unique_id']

        with patch('app.main.PdfplumberAnalyzer') as MockPdfplumberAnalyzer, \
             patch('app.main.PdfAreaSeparator') as MockPdfAreaSeparator, \
             patch('app.main.Translator') as MockTranslator, \
             patch('app.main.os.path.exists', return_value=True), \
             patch('app.main.os.remove') as mock_remove:

            # Mock PdfplumberAnalyzer
            mock_pdfplumber_analyzer_instance = MockPdfplumberAnalyzer.return_value
            mock_pdfplumber_analyzer_instance.extract_textpermutations.return_value = [
                [
                    TextPermutation(area=TextArea(blocks=[], bbox=BBox(x0=0, y0=0, x1=100, y1=10), page_number=1), text='Hello, World!', page_number=1)
                ]
            ]

            mock_area_separator_instance = MockPdfAreaSeparator.return_value
            mock_area_separator_instance.create_colored_pdf.return_value = '/path/to/translated_text_blocks.pdf'

            mock_translator_instance = MockTranslator.return_value
            mock_translator_instance.translate_texts.side_effect = Exception('Translation service failed')

            # 2. Call /translate_text with the obtained filename and unique_id
            translate_text_data = {
                'filename': filename,
                'unique_id': unique_id
            }
            response = client.post('/translate_text', data=translate_text_data)

        assert response.status_code == 302 # Redirect to index
        with client.session_transaction() as session:
            assert 'An error occurred during text translation' in session['_flashes'][0][1]

    def test_extract_textpermutations_two_column_order(self):
        """Test that TextPermutations are extracted in the correct order for 2-column PDFs."""
        from app.text.pdfplumber import PdfplumberAnalyzer
        from app.data_model import ColumnIndex
        
        analyzer = PdfplumberAnalyzer()
        permutations = analyzer.extract_textpermutations('samples/sample.pdf')
        
        # Page 2 has two columns
        page2_perms = permutations[1] if len(permutations) > 1 else []
        
        # Check that left column texts come before right column texts
        left_column_indices = [i for i, p in enumerate(page2_perms)
                              if analyzer._get_column_index_from_area(p.area) == ColumnIndex.LEFT]
        right_column_indices = [i for i, p in enumerate(page2_perms)
                               if analyzer._get_column_index_from_area(p.area) == ColumnIndex.RIGHT]
        
        if left_column_indices and right_column_indices:
            assert max(left_column_indices) < min(right_column_indices), \
                "Left column texts should appear before right column texts"
        
        # Check that texts are not split mid-sentence
        for perm in page2_perms:
            # Texts ending with incomplete words like "laid", "the", etc. indicate incorrect splitting
            assert not perm.text.endswith(('the', 'a', 'an', 'into', 'and', 'laid')), \
                f"Text appears to be split mid-sentence: '{perm.text}'"
