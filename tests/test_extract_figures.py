# Copyright 2025 npz35
#
# See the NOTICE file for this project for license details.
# This file may not be used except in accordance with the NOTICE.

import os
import pytest
from unittest.mock import patch
from flask import Flask
from app.main import create_app
from app.config import TestingConfig
from app.pdf_figure_extractor import PdfFigureExtractor


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

def test_extract_figures_endpoint(client):
    """Test the /extract_figures endpoint with a sample PDF."""
    file_path = 'uploads/sample.pdf'
    with open(file_path, 'rb') as f:
        data = {
            'file': (f, 'sample.pdf')
        }
        response = client.post('/extract_figures', data=data, content_type='multipart/form-data')

    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data['success'] is True
    assert 'filename' in json_data
    assert 'extracted_figures' in json_data
    assert isinstance(json_data['extracted_figures'], int)

def test_extract_figures_from_complex_pdf():
    extractor = PdfFigureExtractor(TestingConfig.JAPANESE_FONT_PATH, TestingConfig.OUTPUT_FOLDER)
    figures = extractor.extract_figures('uploads/sample.pdf', 'test_unique_id')

    # 抽出された図表の数を検証するのだ
    assert len(figures) == 2

def test_extract_figures_endpoint_success(client):
    with patch('app.main.PdfFigureExtractor') as MockPdfFigureExtractor:
        mock_instance = MockPdfFigureExtractor.return_value
        mock_instance.extract_figures.return_value = [
            {"page": 1, "bbox": (10, 10, 100, 100), "figure_type": "image", "image_data": "", "width": 90, "height": 90, "confidence": 1.0}
        ]
        mock_instance.create_figure_pdf.return_value = None

        with open('uploads/sample.pdf', 'rb') as pdf_file:
            response = client.post('/extract_figures', data={'file': (pdf_file, 'sample.pdf')})

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] == True
        assert 'filename' in data
        assert 'output_path' in data
        assert 'processing_time' in data
        assert data['extracted_figures'] == 1
        mock_instance.extract_figures.assert_called_once()
        mock_instance.create_figure_pdf.assert_called_once()

def test_extract_figures_endpoint_no_file(client):
    response = client.post('/extract_figures', data={})
    assert response.status_code == 302 # Redirect to index
    with client.session_transaction() as session:
        assert 'No file selected' in session['_flashes'][0][1]

def test_extract_figures_endpoint_empty_filename(client):
    response = client.post('/extract_figures', data={'file': (b'', '')})
    assert response.status_code == 302 # Redirect to index
    with client.session_transaction() as session:
        assert 'No file selected' in session['_flashes'][0][1]

def test_extract_figures_endpoint_invalid_extension(client):
    with open('uploads/sample.pdf', 'rb') as file:
        response = client.post('/extract_figures', data={'file': (file, 'test.txt')})
    assert response.status_code == 302 # Redirect to index
    with client.session_transaction() as session:
        assert 'Only PDF files are supported' in session['_flashes'][0][1]

def test_extract_figures_endpoint_file_too_large(client, tmp_path):
    large_file_path = tmp_path / "large.pdf"
    with open(large_file_path, 'wb') as f:
        f.write(os.urandom(TestingConfig.MAX_CONTENT_LENGTH + 1)) # 16MB + 1 byte

    with open(large_file_path, 'rb') as file:
        response = client.post('/extract_figures', data={'file': (file, 'large.pdf')})
    assert response.status_code == 302 # Redirect to index
    with client.session_transaction() as session:
        assert 'File size exceeds 16MB for figure extraction' in session['_flashes'][0][1]

def test_extract_figures_endpoint_disk_space_error(client):
    with patch('psutil.disk_usage') as mock_disk_usage:
        mock_disk_usage.return_value.free = TestingConfig.REQUIRED_DISK_SPACE - 1 # Simulate insufficient space
        with open('uploads/sample.pdf', 'rb') as pdf_file:
            response = client.post('/extract_figures', data={'file': (pdf_file, 'sample.pdf')})
        assert response.status_code == 302 # Redirect to index
        with client.session_transaction() as session:
            assert 'Insufficient disk space. Please free up some space.' in session['_flashes'][0][1]

def test_extract_figures_endpoint_figure_extraction_error(client):
    with patch('app.main.PdfFigureExtractor') as MockPdfFigureExtractor:
        mock_instance = MockPdfFigureExtractor.return_value
        mock_instance.extract_figures.side_effect = Exception("Failed to extract figures")

        with open('uploads/sample.pdf', 'rb') as pdf_file:
            response = client.post('/extract_figures', data={'file': (pdf_file, 'sample.pdf')})
        assert response.status_code == 302 # Redirect to index
        with client.session_transaction() as session:
            assert 'Failed to extract figures from PDF. The file may be corrupted or contain no figures.' in session['_flashes'][0][1]
