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
    TRANSLATION_API_URL: str = os.environ.get('TRANSLATION_API_URL') or 'http://localhost:11435'
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
    MAX_PDF_PAGES: int = int(os.environ.get('MAX_PDF_PAGES', 1)) # Maximum number of pages to process

    # Text extraction settings
    TEXT_EXTRACTION_METHOD: str = os.environ.get('TEXT_EXTRACTION_METHOD') or 'pdfplumber' # Method for text extraction (e.g., 'pdfminer', 'ocr', 'hybrid_pdfminer_pypdf')

    # Font color highlighting settings
    ENABLE_FONT_COLOR_HIGHLIGHT: bool = os.environ.get('ENABLE_FONT_COLOR_HIGHLIGHT', 'False').lower() == 'true'
    FONT_COLOR_MAP: dict[str, tuple[float, float, float]] = {
        "Helvetica": (0.0, 0.0, 0.0),              # Black
        "CMMI10": (1.0, 0.0, 0.0),                 # Red
        "SourceSansPro-Regular": (0.0, 0.0, 1.0),  # Blue
        "SourceSansPro-Semibold": (0.0, 1.0, 0.0), # Green
        "CMTI8": (1.0, 0.75, 0.0),
        "CMBX10": (1.0, 0.5, 0.0),                 # Orange
        "CMTT10": (1.0, 0.5, 0.5),
        "CMR12": (0.75, 0.75, 0.0),                # Dark Yellow
        "CMR8": (0.75, 0.0, 0.75),                 # Dark Magenta
        "CMSY10": (0.75, 0.25, 0.25),              # Light Red
        "CMR10": (0.5, 0.0, 0.5),                  # Purple
        "CMEX10": (0.5, 0.5, 0.0),                 # Olive
        "Martel-Regular": (0.5, 0.5, 0.5),
        "CMSL10": (0.25, 0.25, 0.25),              # Dark Gray
        "CMTI10": (0.25, 0.25, 0.75),              # Light Blue
        "CMR17": (0.0, 0.75, 0.75),                # Dark Cyan
        "CMBX12": (0.0, 0.5, 0.5),                 # Teal
        "default": (0.0, 0.0, 0.0)                 # Default to black if font not in map
    }

    # Translation settings
    TRANSLATION_MAX_LENGTH: int = 10000  # Maximum characters to translate at once
    TRANSLATION_TIMEOUT: int = 30  # Timeout (seconds)
    TRANSLATION_MAX_UNIT: int | None = int(os.environ.get('TRANSLATION_MAX_UNIT')) if os.environ.get('TRANSLATION_MAX_UNIT') else None # Maximum number of translation units per create_translated_pdf execution
    TRANSLATION_MAX_UNIT_PER_REQUEST: int | None = int(os.environ.get('TRANSLATION_MAX_UNIT_PER_REQUEST')) if os.environ.get('TRANSLATION_MAX_UNIT_PER_REQUEST') else None # Maximum number of translation units per request
    RENDER_ORIGINAL_ON_TRANSLATION_FAILURE: bool = os.environ.get('RENDER_ORIGINAL_ON_TRANSLATION_FAILURE', 'False').lower() == 'true' # Render original text if translation fails

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

    # Default font size for cases where font size cannot be extracted
    DEFAULT_FONT_SIZE: float = 12.0
    MIN_FONT_SIZE: float = 8.0 # Minimum font size for translated Japanese text

class DevelopmentConfig(Config):
    """Development environment settings"""
    DEBUG: bool = False
    TESTING: bool = False

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