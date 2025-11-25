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

class TestColumnSeparationEndpoint:
    def test_separation_endpoint(self, client):
        '''Test the /column_separation endpoint with a sample PDF.'''
        file_path = 'samples/sample.pdf'
        
        # 1. Upload the file first to get filename and unique_id
        with open(file_path, 'rb') as f:
            upload_data = {'file': (f, 'sample.pdf')}
            upload_response = client.post('/upload', data=upload_data, content_type='multipart/form-data')
        
        assert upload_response.status_code == 200
        upload_json = upload_response.get_json()
        assert upload_json['success'] is True
        assert 'filename' in upload_json
        assert 'unique_id' in upload_json
        
        filename = upload_json['filename']
        unique_id = upload_json['unique_id']

        # 2. Call /column_separation with the obtained filename and unique_id
        separation_data = {
            'filename': filename,
            'unique_id': unique_id
        }
        response = client.post('/column_separation', data=separation_data)

        assert response.status_code == 200
        json_data = response.get_json()
        assert json_data['success'] is True
        assert 'filename' in json_data
        assert 'output_path' in json_data
        assert 'processing_time' in json_data

    def test_separation_endpoint_success(self, client):
        file_path = 'samples/sample.pdf'
        
        # 1. Upload the file first to get filename and unique_id
        with open(file_path, 'rb') as f:
            upload_data = {'file': (f, 'sample.pdf')}
            upload_response = client.post('/upload', data=upload_data, content_type='multipart/form-data')
        
        assert upload_response.status_code == 200
        upload_json = upload_response.get_json()
        assert upload_json['success'] is True
        
        filename = upload_json['filename']
        unique_id = upload_json['unique_id']

        # 2. Call /column_separation with the obtained filename and unique_id
        separation_data = {
            'filename': filename,
            'unique_id': unique_id
        }
        response = client.post('/column_separation', data=separation_data)

        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] == True
        assert 'filename' in data
        assert 'output_path' in data
        assert 'processing_time' in data

    def test_separation_endpoint_no_file(self, client):
        response = client.post('/column_separation', data={})
        assert response.status_code == 302 # Redirect to index
        with client.session_transaction() as session:
            assert 'An error occurred during column_separation' in session['_flashes'][0][1]

    def test_separation_endpoint_empty_filename(self, client):
        response = client.post('/column_separation', data={'filename': '', 'unique_id': 'some_id'})
        assert response.status_code == 302 # Redirect to index
        with client.session_transaction() as session:
            assert 'An error occurred during column_separation' in session['_flashes'][0][1]

    def test_separation_endpoint_invalid_extension(self, client):
        file_path = 'samples/sample.pdf'
        with open(file_path, 'rb') as f:
            upload_data = {'file': (f, 'test.txt')} # Upload with invalid extension
            upload_response = client.post('/upload', data=upload_data, content_type='multipart/form-data')
        
        assert upload_response.status_code == 302 # Redirect due to invalid extension
        with client.session_transaction() as session:
            assert 'Only PDF files are supported' in session['_flashes'][0][1]

    def test_separation_endpoint_file_too_large(self, client, tmp_path):
        large_file_path = tmp_path / 'large.pdf'
        with open(large_file_path, 'wb') as f:
            f.write(os.urandom(TestingConfig.MAX_CONTENT_LENGTH + 1)) # 20MB + 1 byte

        with open(large_file_path, 'rb') as file:
            response = client.post('/upload', data={'file': (file, 'large.pdf')}, content_type='multipart/form-data')
        assert response.status_code == 413 # Request Entity Too Large
        # Flash message is not set for 413 errors, as it's handled by Werkzeug
        # with client.session_transaction() as session:
        #     assert 'File size exceeds 20MB' in session['_flashes'][0][1]

    def test_separation_endpoint_disk_space_error(self, client):
        file_path = 'samples/sample.pdf'
        with patch('psutil.disk_usage') as mock_disk_usage:
            mock_disk_usage.return_value.free = TestingConfig.REQUIRED_DISK_SPACE - 1 # Simulate insufficient space
            with open(file_path, 'rb') as pdf_file:
                response = client.post('/upload', data={'file': (pdf_file, 'sample.pdf')}, content_type='multipart/form-data')
        assert response.status_code == 503

    def test_separation_endpoint_separation_error(self, client):
        file_path = 'samples/sample.pdf'
        
        # 1. Upload the file first to get filename and unique_id
        with open(file_path, 'rb') as f:
            upload_data = {'file': (f, 'sample.pdf')}
            upload_response = client.post('/upload', data=upload_data, content_type='multipart/form-data')
        
        assert upload_response.status_code == 200
        upload_json = upload_response.get_json()
        assert upload_json['success'] is True
        
        filename = upload_json['filename']
        unique_id = upload_json['unique_id']

        with patch('app.main.PdfColumnSeparator') as MockPdfColumnSeparator:
            mock_instance = MockPdfColumnSeparator.return_value
            mock_instance.analyze_separation_lines.side_effect = Exception('Failed to separate columns')

            separation_data = {
                'filename': filename,
                'unique_id': unique_id
            }
            response = client.post('/column_separation', data=separation_data)
            
            assert response.status_code == 302 # Redirect to index
            with client.session_transaction() as session:
                assert 'Failed to separate columns in PDF. The file may be corrupted.' in session['_flashes'][0][1]