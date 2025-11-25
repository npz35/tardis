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
from app.data_model import Area, BBox, TextArea, TextPermutation, TranslationResponse
from app.pdf_text_layout import PdfTextLayout
from reportlab.lib.colors import Color

class TestDrawTextEndpoint:
    @pytest.fixture
    def app(self):
        '''Create and configure a new app instance for each test.'''
        app, _ = create_app(TestingConfig)
        app.config.update({
            'TESTING': True,
            'JAPANESE_FONT_PATH': 'static/fonts/ipaexg.ttf', # テスト用にフォントパスを設定するのだ
            'MIN_FONT_SIZE': 8,
        })
        yield app

    @pytest.fixture
    def client(self, app: Flask):
        '''A test client for the app.'''
        return app.test_client()

    @pytest.fixture
    def sample_pdf_path(self):
        '''Path to the sample PDF for testing.'''
        return 'samples/sample.pdf'

    def test_draw_text_endpoint_success(self, client, sample_pdf_path):
        '''Test the /draw_text endpoint with a sample PDF and mocked dependencies.'''
        # 1. Upload the file first to get filename and unique_id
        with open(sample_pdf_path, 'rb') as f:
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
             patch('app.main.PdfTextLayout') as MockPdfTextLayout, \
             patch('pypdf.PdfReader') as MockPdfReader, \
             patch('pypdf.PdfWriter') as MockPdfWriter, \
             patch('reportlab.pdfgen.canvas.Canvas') as MockCanvas:

            # Mock PdfplumberAnalyzer
            mock_pdfplumber_analyzer_instance = MockPdfplumberAnalyzer.return_value
            mock_pdfplumber_analyzer_instance.extract_textpermutations.return_value = [
                [
                    TextPermutation(area=TextArea(blocks=[], bbox=BBox(x0=100, y0=700, x1=200, y1=720), page_number=1), text='Hello, World!', page_number=1),
                    TextPermutation(area=TextArea(blocks=[], bbox=BBox(x0=100, y0=680, x1=200, y1=700), page_number=1), text='This is a test.', page_number=1)
                ]
            ]

            # Mock PdfAreaSeparator (still needed for create_colored_pdf, though not directly called in _draw_translated_text_on_pdf)
            mock_area_separator_instance = MockPdfAreaSeparator.return_value
            # create_colored_pdf は /area_separation エンドポイントで使われるので、ここではモックしないのだ
            # mock_area_separator_instance.create_colored_pdf.return_value = '/path/to/translated_text_blocks.pdf'

            # Mock Translator
            mock_translator_instance = MockTranslator.return_value
            mock_translator_instance.translate_texts.return_value = [
                TranslationResponse(original_text='Hello, World!', translated_text='こんにちは、世界！', source_lang='English', target_lang='Japanese', model='mock-model'),
                TranslationResponse(original_text='This is a test.', translated_text='これはテストです。', source_lang='English', target_lang='Japanese', model='mock-model')
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

            # 2. Call /draw_text with the obtained filename and unique_id
            draw_text_data = {
                'filename': filename,
                'unique_id': unique_id
            }
            response = client.post('/draw_text', data=draw_text_data)

            assert response.status_code == 200
            json_data = response.get_json()
            assert json_data['success'] is True
            assert 'filename' in json_data
            assert 'output_path' in json_data
            assert 'processing_time' in json_data
            assert json_data['translated_units'] == 2

            MockPdfplumberAnalyzer.assert_called_once()
            mock_pdfplumber_analyzer_instance.extract_textpermutations.assert_called_once()
            MockTranslator.assert_called_once()
            mock_translator_instance.translate_texts.assert_called_once_with(['Hello, World!', 'This is a test.'])
            MockPdfTextLayout.assert_called_once_with(
                font_path=client.application.config['JAPANESE_FONT_PATH'],
                min_font_size=client.application.config['MIN_FONT_SIZE']
            )
            mock_pdf_text_layout_instance.draw_white_rectangle.assert_not_called() # Should not be called anymore
            assert mock_pdf_text_layout_instance.draw_translated_text.call_count == 2 # Two blocks
            
            # Check that pypdf is no longer used for merging
            MockPdfReader.assert_not_called()
            MockPdfWriter.assert_not_called()

            # Check that a new canvas is created and saved once
            MockCanvas.assert_called_once()
            mock_canvas_instance.save.assert_called_once()

    def test_draw_text_endpoint_no_file(self, client):
        '''Test /draw_text with no file uploaded.'''
        response = client.post('/draw_text', data={})
        assert response.status_code == 302 # Redirect to index
        with client.session_transaction() as session:
            assert 'An error occurred during text drawing' in session['_flashes'][0][1]

    def test_draw_text_endpoint_multiple_texts_in_same_area(self, client, sample_pdf_path):
        '''Test /draw_text endpoint with multiple translated texts belonging to the same TextArea.'''
        # 1. Upload the file first to get filename and unique_id
        with open(sample_pdf_path, 'rb') as f:
            upload_data = {'file': (f, 'sample.pdf')}
            upload_response = client.post('/upload', data=upload_data, content_type='multipart/form-data')
        
        assert upload_response.status_code == 200
        upload_json = upload_response.get_json()
        assert upload_json['success'] is True
        assert 'filename' in upload_json
        assert 'unique_id' in upload_json
        
        filename = upload_json['filename']
        unique_id = upload_json['unique_id']

        # Create a shared TextArea instance
        shared_area = TextArea(blocks=[], bbox=BBox(x0=100, y0=600, x1=300, y1=700), page_number=1)

        with patch('app.main.PdfplumberAnalyzer') as MockPdfplumberAnalyzer, \
             patch('app.main.PdfAreaSeparator') as MockPdfAreaSeparator, \
             patch('app.main.Translator') as MockTranslator, \
             patch('app.main.PdfTextLayout') as MockPdfTextLayout, \
             patch('pypdf.PdfReader') as MockPdfReader, \
             patch('pypdf.PdfWriter') as MockPdfWriter, \
             patch('reportlab.pdfgen.canvas.Canvas') as MockCanvas:

            # Mock PdfplumberAnalyzer to return TextPermutations sharing the same TextArea
            mock_pdfplumber_analyzer_instance = MockPdfplumberAnalyzer.return_value
            mock_pdfplumber_analyzer_instance.extract_textpermutations.return_value = [
                [
                    TextPermutation(area=shared_area, text='First sentence.', page_number=1),
                    TextPermutation(area=shared_area, text='Second sentence.', page_number=1),
                    TextPermutation(area=shared_area, text='Third sentence.', page_number=1)
                ]
            ]

            # Mock Translator
            mock_translator_instance = MockTranslator.return_value
            mock_translator_instance.translate_texts.return_value = [
                TranslationResponse(original_text='First sentence.', translated_text='最初の文です。', source_lang='English', target_lang='Japanese', model='mock-model'),
                TranslationResponse(original_text='Second sentence.', translated_text='二番目の文です。', source_lang='English', target_lang='Japanese', model='mock-model'),
                TranslationResponse(original_text='Third sentence.', translated_text='三番目の文です。', source_lang='English', target_lang='Japanese', model='mock-model')
            ]

            # Mock PdfTextLayout
            mock_pdf_text_layout_instance = MockPdfTextLayout.return_value
            mock_pdf_text_layout_instance.draw_white_rectangle.return_value = None
            mock_pdf_text_layout_instance.draw_translated_text.return_value = None
            mock_pdf_text_layout_instance.draw_multiple_translated_texts_in_area.return_value = None # Mock the new method

            # Mock pypdf components
            mock_pdf_reader_instance = MockPdfReader.return_value
            mock_pdf_reader_instance.pages = [MagicMock()] # Simulate one page
            mock_pdf_writer_instance = MockPdfWriter.return_value
            mock_pdf_writer_instance.add_page.return_value = None
            mock_pdf_writer_instance.write.return_value = None

            # Mock canvas and BytesIO
            mock_canvas_instance = MockCanvas.return_value
            mock_canvas_instance.showPage.return_value = None
            mock_canvas_instance.save.return_value = None

            # 2. Call /draw_text with the obtained filename and unique_id
            draw_text_data = {
                'filename': filename,
                'unique_id': unique_id
            }
            response = client.post('/draw_text', data=draw_text_data)

            assert response.status_code == 200
            json_data = response.get_json()
            assert json_data['success'] is True
            assert 'filename' in json_data
            assert 'output_path' in json_data
            assert 'processing_time' in json_data
            assert json_data['translated_units'] == 3 # Three units translated

            MockPdfplumberAnalyzer.assert_called_once()
            mock_pdfplumber_analyzer_instance.extract_textpermutations.assert_called_once()
            MockTranslator.assert_called_once()
            mock_translator_instance.translate_texts.assert_called_once_with(['First sentence.', 'Second sentence.', 'Third sentence.'])
            MockPdfTextLayout.assert_called_once_with(
                font_path=client.application.config['JAPANESE_FONT_PATH'],
                min_font_size=client.application.config['MIN_FONT_SIZE']
            )
            mock_pdf_text_layout_instance.draw_translated_text.assert_not_called() # Should not be called for multiple texts in one area
            mock_pdf_text_layout_instance.draw_multiple_translated_texts_in_area.assert_called_once_with(
                mock_canvas_instance,
                ['最初の文です。', '二番目の文です。', '三番目の文です。'],
                shared_area.bbox,
                mock_pdfplumber_analyzer_instance.extract_textpermutations.return_value[0][0].font_info # Font info from the first permutation
            )
            
            # Check that pypdf is no longer used for merging
            MockPdfReader.assert_not_called()
            MockPdfWriter.assert_not_called()

            # Check that a new canvas is created and saved once
            MockCanvas.assert_called_once()
            mock_canvas_instance.save.assert_called_once()

    def test_draw_text_endpoint_empty_filename(self, client):
        '''Test /draw_text with an empty filename.'''
        response = client.post('/draw_text', data={'filename': '', 'unique_id': 'some_id'})
        assert response.status_code == 302 # Redirect to index
        with client.session_transaction() as session:
            assert 'An error occurred during text drawing' in session['_flashes'][0][1]

    def test_draw_text_endpoint_invalid_extension(self, client, sample_pdf_path):
        '''Test /draw_text with an invalid file extension.'''
        with open(sample_pdf_path, 'rb') as f:
            upload_data = {'file': (f, 'test.txt')} # Upload with invalid extension
            upload_response = client.post('/upload', data=upload_data, content_type='multipart/form-data')
        
        assert upload_response.status_code == 302 # Redirect due to invalid extension
        with client.session_transaction() as session:
            assert 'Only PDF files are supported' in session['_flashes'][0][1]

    def test_draw_text_endpoint_file_too_large(self, client, tmp_path):
        '''Test /draw_text with a file exceeding the size limit.'''
        large_file_path = tmp_path / 'large.pdf'
        with open(large_file_path, 'wb') as f:
            f.write(os.urandom(TestingConfig.MAX_CONTENT_LENGTH + 1)) # 20MB + 1 byte
 
        with open(large_file_path, 'rb') as file:
            response = client.post('/upload', data={'file': (file, 'large.pdf')}, content_type='multipart/form-data')
        assert response.status_code == 413 # Request Entity Too Large

    def test_draw_text_endpoint_disk_space_error(self, client, sample_pdf_path):
        '''Test /draw_text with insufficient disk space.'''
        with patch('app.main.psutil.disk_usage') as mock_disk_usage:
            mock_disk_usage.return_value.free = TestingConfig.REQUIRED_DISK_SPACE - 1 # Simulate insufficient space
            with open(sample_pdf_path, 'rb') as pdf_file:
                response = client.post('/upload', data={'file': (pdf_file, 'sample.pdf')}, content_type='multipart/form-data')
        assert response.status_code == 503 # Service Unavailable

    def test_draw_text_endpoint_area_separator_error(self, client, sample_pdf_path):
        '''Test /draw_text when PdfAreaSeparator raises an exception.'''
        # 1. Upload the file first to get filename and unique_id
        with open(sample_pdf_path, 'rb') as f:
            upload_data = {'file': (f, 'sample.pdf')}
            upload_response = client.post('/upload', data=upload_data, content_type='multipart/form-data')
        
        assert upload_response.status_code == 200
        upload_json = upload_response.get_json()
        assert upload_json['success'] is True
        
        filename = upload_json['filename']
        unique_id = upload_json['unique_id']

        with patch('app.main.PdfplumberAnalyzer') as MockPdfplumberAnalyzer:
            mock_pdfplumber_analyzer_instance = MockPdfplumberAnalyzer.return_value
            mock_pdfplumber_analyzer_instance.extract_textpermutations.side_effect = Exception('Failed to extract text permutations')

            draw_text_data = {
                'filename': filename,
                'unique_id': unique_id
            }
            response = client.post('/draw_text', data=draw_text_data)
            assert response.status_code == 302 # Redirect to index
            with client.session_transaction() as session:
                assert 'Failed to extract text from PDF' in session['_flashes'][0][1] # Generic error message for now

    def test_draw_text_endpoint_translator_error(self, client, sample_pdf_path):
        '''Test /draw_text when Translator raises an exception.'''
        # 1. Upload the file first to get filename and unique_id
        with open(sample_pdf_path, 'rb') as f:
            upload_data = {'file': (f, 'sample.pdf')}
            upload_response = client.post('/upload', data=upload_data, content_type='multipart/form-data')
        
        assert upload_response.status_code == 200
        upload_json = upload_response.get_json()
        assert upload_json['success'] is True
        
        filename = upload_json['filename']
        unique_id = upload_json['unique_id']

        with patch('app.main.PdfplumberAnalyzer') as MockPdfplumberAnalyzer, \
             patch('app.main.PdfAreaSeparator') as MockPdfAreaSeparator, \
             patch('app.main.Translator') as MockTranslator:
            
            mock_pdfplumber_analyzer_instance = MockPdfplumberAnalyzer.return_value
            mock_pdfplumber_analyzer_instance.extract_textpermutations.return_value = [
                [
                    TextPermutation(area=TextArea(blocks=[], bbox=BBox(x0=100, y0=700, x1=200, y1=720), page_number=1), text='Hello, World!', page_number=1)
                ]
            ]
 
            mock_translator_instance = MockTranslator.return_value
            mock_translator_instance.translate_texts.side_effect = Exception('翻訳エラーが発生しました')
 
            draw_text_data = {
                'filename': filename,
                'unique_id': unique_id
            }
            response = client.post('/draw_text', data=draw_text_data)
            assert response.status_code == 302 # Redirect to index
            with client.session_transaction() as session:
                assert 'An error occurred during translation. Please try again later.' in session['_flashes'][0][1]
 
    def test_draw_text_endpoint_pdf_layout_error(self, client, sample_pdf_path):
        '''Test /draw_text when PdfTextLayout raises an exception during drawing.'''
        # 1. Upload the file first to get filename and unique_id
        with open(sample_pdf_path, 'rb') as f:
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
             patch('app.main.PdfTextLayout') as MockPdfTextLayout, \
             patch('pypdf.PdfReader') as MockPdfReader, \
             patch('pypdf.PdfWriter') as MockPdfWriter, \
             patch('reportlab.pdfgen.canvas.Canvas') as MockCanvas:
 
            mock_pdfplumber_analyzer_instance = MockPdfplumberAnalyzer.return_value
            mock_pdfplumber_analyzer_instance.extract_textpermutations.return_value = [
                [
                    TextPermutation(area=TextArea(blocks=[], bbox=BBox(x0=100, y0=700, x1=200, y1=720), page_number=1), text='Hello, World!', page_number=1)
                ]
            ]
 
            mock_translator_instance = MockTranslator.return_value
            mock_translator_instance.translate_texts.return_value = [
                TranslationResponse(original_text='Hello, World!', translated_text='こんにちは、世界！', source_lang='English', target_lang='Japanese', model='mock-model')
            ]
 
            mock_pdf_text_layout_instance = MockPdfTextLayout.return_value
            mock_pdf_text_layout_instance.draw_translated_text.side_effect = Exception('Failed to draw text')
 
            mock_pdf_reader_instance = MockPdfReader.return_value
            mock_pdf_reader_instance.pages = [MagicMock()]
            mock_pdf_writer_instance = MockPdfWriter.return_value
            mock_pdf_writer_instance.add_page.return_value = None
            mock_pdf_writer_instance.write.return_value = None
 
            mock_canvas_instance = MockCanvas.return_value
            mock_canvas_instance.showPage.return_value = None
            mock_canvas_instance.save.return_value = None
 
            draw_text_data = {
                'filename': filename,
                'unique_id': unique_id
            }
            response = client.post('/draw_text', data=draw_text_data)
            assert response.status_code == 302 # Redirect to index
            with client.session_transaction() as session:
                assert 'An error occurred during text drawing' in session['_flashes'][0][1]