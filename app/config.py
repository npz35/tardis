# Copyright 2025 npz35
#
# See the NOTICE file for this project for license details.
# This file may not be used except in accordance with the NOTICE.

import os

class Config:
    """Base configuration class"""

    # Flask settings
    SECRET_KEY: str = os.environ.get('SECRET_KEY') or 'tardis-secret-key-change-in-production'
    MAX_CONTENT_LENGTH: int = 16 * 1024 * 1024  # 16MB

    REQUIRED_DISK_SPACE: int = 100 * 1024 * 1024 # 100MB

    # Directory settings
    BASE_DIR: str = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    LOG_FOLDER: str = os.path.join(BASE_DIR, 'logs')
    OUTPUT_FOLDER: str = os.path.join(BASE_DIR, 'outputs')
    STATIC_FOLDER: str = os.path.join(BASE_DIR, 'static')
    TEMPLATE_FOLDER: str = os.path.join(BASE_DIR, 'templates')
    UPLOAD_FOLDER: str = os.path.join(BASE_DIR, 'uploads')

    # API settings
    TRANSLATION_API_URL: str = os.environ.get('TRANSLATION_API_URL') or 'http://host.docker.internal:11435'
    TRANSLATION_MODEL: str = os.environ.get('TRANSLATION_MODEL') or 'default-model'

    # Japanese font settings
    JAPANESE_FONT_PATH: str = os.environ.get('JAPANESE_FONT_PATH') or os.path.join(STATIC_FOLDER, 'fonts', 'ipaexm.ttf')

    # File retention period (hours)
    FILE_RETENTION_HOURS: int = 48

    # Logging settings
    LOG_LEVEL: str = os.environ.get('LOG_LEVEL') or 'INFO'
    LOG_FILE: str = os.path.join(BASE_DIR, 'logs', 'tardis.log')

    # PDF processing settings
    PDF_DPI: int = 300  # Resolution
    PDF_TEXT_THRESHOLD: int = 5  # Threshold between text blocks (pixels)
    MAX_PDF_PAGES: int = 3 # Maximum number of pages to process

    # Translation settings
    TRANSLATION_MAX_LENGTH: int = 10000  # Maximum characters to translate at once
    TRANSLATION_TIMEOUT: int = 30  # Timeout (seconds)

    # Layout adjustment settings
    FONT_SIZE_ADJUSTMENT_FACTOR: float = 1.2  # Japanese font size adjustment factor
    LINE_HEIGHT_FACTOR: float = 1.4  # Line height factor
    BBOX_EXPAND_MARGIN: int = 2  # pixels
    LINE_WIDTH_MARGIN: int = 5  # pixels
    LINE_SPACING_FACTOR: float = 1.2
    JP_CHAR_WIDTH_FACTOR: float = 1.0
    JP_CHAR_HEIGHT_FACTOR: float = 1.2
    ADJUST_SLIGHTLY_FACTOR: float = 0.9
    VERTICAL_DIST_FACTOR: float = 2.0
    HORIZONTAL_DIST_FACTOR: float = 2.0

class DevelopmentConfig(Config):
    """Development environment settings"""
    DEBUG: bool = True
    TESTING: bool = False

    # Output more detailed logs in development environment
    LOG_LEVEL = 'DEBUG'

class ProductionConfig(Config):
    """Production environment settings"""
    DEBUG: bool = False
    TESTING: bool = False

    # More secure settings in production environment
    SECRET_KEY = os.environ.get('SECRET_KEY')  # Must be obtained from environment variable

class TestingConfig(Config):
    """Test environment settings"""
    TESTING: bool = True
    # Upload folder for testing
    BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'test_uploads')
    OUTPUT_FOLDER = os.path.join(BASE_DIR, 'test_outputs')

    # Simplified settings for testing
    TRANSLATION_MAX_LENGTH = 100
    PDF_DPI = 150

# Configuration mapping
config: dict[str, type[Config]] = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}