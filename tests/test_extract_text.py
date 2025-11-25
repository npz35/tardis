# Copyright 2025 npz35
#
# See the NOTICE file for this project for license details.
# This file may not be used except in accordance with the NOTICE.

import pytest
from flask import Flask
from app.main import create_app
from app.config import Config
import os

@pytest.fixture
def app():
    '''Create and configure a new app instance for each test.'''
    app, _ = create_app(Config)
    app.config.update({
        'TESTING': True,
    })
    yield app

@pytest.fixture
def client(app: Flask):
    '''A test client for the app.'''
    return app.test_client()

class TestExtractTextEndpoint:
    def test_extract_text_endpoint(self, client):
        '''Test the /extract_text endpoint with a sample PDF.'''
        # Ensure the uploads directory exists for the test
        os.makedirs('uploads', exist_ok=True)
        
        # Create a dummy PDF file for testing
        # In a real scenario, you might use a more robust way to create a sample PDF
        # For now, we'll assume 'samples/sample.pdf' exists or create a minimal one
        # For this test, we'll use a simple dummy file if it doesn't exist
        sample_pdf_path = 'samples/sample.pdf'
        if not os.path.exists(sample_pdf_path):
            # Create a very basic dummy PDF for the test to pass file existence check
            # This PDF won't have actual text content for extraction, but allows the endpoint to be called
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import letter
            c = canvas.Canvas(sample_pdf_path, pagesize=letter)
            c.drawString(100, 750, 'Hello, this is a test PDF.')
            c.save()

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

        # 2. Call /extract_text with the obtained filename and unique_id
        extract_text_data = {
            'filename': filename,
            'unique_id': unique_id
        }
        response = client.post('/extract_text', data=extract_text_data)

        assert response.status_code == 200
        json_data = response.get_json()
        assert json_data['success'] is True

    # def test_extract_text_hybrid_mode(self, client, app):
    #     '''Test the /extract_text endpoint with hybrid_pdfminer_pypdf mode.'''
    #     os.makedirs('uploads', exist_ok=True)
    #     sample_pdf_path = 'uploads/sample_hybrid.pdf'
    #
    #     # Create a dummy PDF with a known 'error' for pdfminer and correct text for pypdf
    #     from reportlab.pdfgen import canvas
    #     from reportlab.lib.pagesizes import letter
    #     c = canvas.Canvas(sample_pdf_path, pagesize=letter)
    #     c.drawString(100, 750, 'Hello, this is a test PDF with ε character.')
    #     c.save()
    #
    #     # Temporarily set the extraction method to hybrid_pdfminer_pypdf
    #     original_method = Config.TEXT_EXTRACTION_METHOD
    #     Config.TEXT_EXTRACTION_METHOD = 'hybrid_pdfminer_pypdf'
    #
    #     with open(sample_pdf_path, 'rb') as f:
    #         data = {
    #             'file': (f, 'sample_hybrid.pdf')
    #         }
    #         response = client.post('/extract_text', data=data, content_type='multipart/form-data')
    #
    #     # Restore original method
    #     Config.TEXT_EXTRACTION_METHOD = original_method
    #
    #     assert response.status_code == 200
    #     json_data = response.get_json()
    #     assert json_data['success'] is True