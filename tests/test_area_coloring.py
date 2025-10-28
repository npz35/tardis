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
from app.pdf_area_separator import PdfAreaSeparator
from pypdf import PdfReader

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

def test_area_coloring_endpoint(client):
    """Test the /area_separation endpoint with a sample PDF."""
    file_path = 'uploads/sample.pdf'
    with open(file_path, 'rb') as f:
        data = {
            'file': (f, 'sample.pdf')
        }
        response = client.post('/area_separation', data=data, content_type='multipart/form-data')

    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data['success'] is True
    assert 'filename' in json_data

    # Verify the output PDF file exists and is a valid PDF
    output_filename = json_data['filename']
    output_path = os.path.join(client.application.config['OUTPUT_FOLDER'], output_filename)
    assert os.path.exists(output_path)

    # Check if it's a valid PDF by trying to read it
    try:
        reader = PdfReader(output_path)
        assert len(reader.pages) > 0
    except Exception as e:
        pytest.fail(f"Generated PDF is not valid: {e}")
    finally:
        # Clean up the generated file
        if os.path.exists(output_path):
            os.remove(output_path)

def test_area_coloring_endpoint_success(client):
    with open('uploads/sample.pdf', 'rb') as pdf_file:
        response = client.post('/area_separation', data={'file': (pdf_file, 'sample.pdf')})

    assert response.status_code == 200
    data = response.get_json()
    assert data['success'] == True
    assert 'filename' in data
    assert 'output_path' in data
    assert 'processing_time' in data

def test_area_coloring_endpoint_no_file(client):
    response = client.post('/area_separation', data={})
    assert response.status_code == 302 # Redirect to index
    with client.session_transaction() as session:
        assert 'No file selected' in session['_flashes'][0][1]

def test_area_coloring_endpoint_empty_filename(client):
    response = client.post('/area_separation', data={'file': (b'', '')})
    assert response.status_code == 302 # Redirect to index
    with client.session_transaction() as session:
        assert 'No file selected' in session['_flashes'][0][1]

def test_area_coloring_endpoint_invalid_extension(client):
    with open('uploads/sample.pdf', 'rb') as file:
        response = client.post('/area_separation', data={'file': (file, 'test.txt')})
    assert response.status_code == 302 # Redirect to index
    with client.session_transaction() as session:
        assert 'Only PDF files are supported' in session['_flashes'][0][1]

def test_area_coloring_endpoint_file_too_large(client, tmp_path):
    large_file_path = tmp_path / "large.pdf"
    with open(large_file_path, 'wb') as f:
        f.write(os.urandom(TestingConfig.MAX_CONTENT_LENGTH + 1)) # 16MB + 1 byte

    with open(large_file_path, 'rb') as file:
        response = client.post('/area_separation', data={'file': (file, 'large.pdf')})
    assert response.status_code == 302 # Redirect to index
    with client.session_transaction() as session:
        assert 'File size exceeds 16MB for area coloring' in session['_flashes'][0][1]

def test_area_coloring_endpoint_disk_space_error(client):
    with patch('psutil.disk_usage') as mock_disk_usage:
        mock_disk_usage.return_value.free = TestingConfig.REQUIRED_DISK_SPACE - 1 # Simulate insufficient space
        with open('uploads/sample.pdf', 'rb') as pdf_file:
            response = client.post('/area_separation', data={'file': (pdf_file, 'sample.pdf')})
        assert response.status_code == 302 # Redirect to index
        with client.session_transaction() as session:
            assert 'Insufficient disk space. Please free up some space.' in session['_flashes'][0][1]

def test_area_coloring_endpoint_area_coloring_error(client):
    with patch('app.main.PdfAreaSeparator') as MockPdfAreaSeparator:
        mock_instance = MockPdfAreaSeparator.return_value
        # extract_area_infosが2つの値を返すようにモックするのだ
        mock_instance.extract_area_infos.return_value = ({1: []}) # ダミーのページ情報なのだ
        mock_instance.create_colored_pdf.side_effect = Exception("Failed to color areas")

        with open('uploads/sample.pdf', 'rb') as pdf_file:
            response = client.post('/area_separation', data={'file': (pdf_file, 'sample.pdf')})
        assert response.status_code == 302 # Redirect to index
        with client.session_transaction() as session:
            assert 'Failed to color areas in PDF. The file may be corrupted.' in session['_flashes'][0][1]