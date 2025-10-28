# Copyright 2025 npz35
#
# See the NOTICE file for this project for license details.
# This file may not be used except in accordance with the NOTICE.

import pytest
from flask import Flask
from app.main import create_app
from app.config import Config

@pytest.fixture
def app():
    """Create and configure a new app instance for each test."""
    app, _ = create_app(Config)
    app.config.update({
        "TESTING": True,
    })
    yield app

@pytest.fixture
def client(app: Flask):
    """A test client for the app."""
    return app.test_client()

def test_health_check(client):
    """Test the /health endpoint."""
    response = client.get('/health')
    assert response.status_code == 200
    json_data = response.get_json()
    assert 'status' in json_data
    assert json_data['status'] in ['healthy', 'warning']
    assert 'timestamp' in json_data
    assert 'disk_free_mb' in json_data
    assert 'memory_usage_percent' in json_data
    assert 'directories' in json_data
    assert 'upload' in json_data['directories']
    assert 'output' in json_data['directories']
    assert 'response_time_ms' in json_data