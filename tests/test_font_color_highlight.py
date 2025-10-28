# Copyright 2025 npz35
#
# See the NOTICE file for this project for license details.
# This file may not be used except in accordance with the NOTICE.

import os
import pytest
import logging
from unittest.mock import MagicMock, patch
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from app.pdf_text_layout import PdfTextLayout
from app.config import Config

# Mock Config for testing purposes
class MockConfig(Config):
    ENABLE_FONT_COLOR_HIGHLIGHT = True
    FONT_COLOR_MAP = {
        "Helvetica": (0.0, 0.0, 0.0),      # Black
        "Times-Roman": (1.0, 0.0, 0.0),    # Red
        "Courier": (0.0, 0.0, 1.0),        # Blue
        "default": (0.5, 0.5, 0.5)         # Gray for unknown fonts
    }
    JAPANESE_FONT_PATH = "tests/test_uploads/dummy_font.ttf" # Dummy font path for testing

@pytest.fixture
def pdf_text_layout_instance():
    # Create a dummy font file for testing
    dummy_font_path = MockConfig.JAPANESE_FONT_PATH
    os.makedirs(os.path.dirname(dummy_font_path), exist_ok=True)
    with open(dummy_font_path, 'w') as f:
        f.write("dummy font content")
    
    # Patch Config to use MockConfig
    with patch('app.pdf_text_layout.Config', MockConfig):
        yield PdfTextLayout()
    
    # Clean up dummy font file
    os.remove(dummy_font_path)

@pytest.fixture
def mock_canvas():
    mock = MagicMock(spec=canvas.Canvas)
    # Mock stringWidth to return a reasonable width based on text length and font size
    mock.stringWidth.side_effect = lambda text, font_name, font_size: len(text) * font_size * 0.6
    return mock

def test_draw_translated_text_with_font_color_highlight(pdf_text_layout_instance, mock_canvas, caplog):
    caplog.set_level(logging.DEBUG)

    translated_text = "Hello World"
    bbox = (10, 10, 100, 50)

    # Test with Helvetica font
    font_info_helvetica = {"font_name": "Helvetica", "font_size": 12}
    pdf_text_layout_instance.draw_translated_text(mock_canvas, translated_text, bbox, font_info_helvetica)
    mock_canvas.setFillColorRGB.assert_any_call(0.0, 0.0, 0.0) # Black

    # Test with Times-Roman font
    font_info_times = {"font_name": "Times-Roman", "font_size": 12}
    pdf_text_layout_instance.draw_translated_text(mock_canvas, translated_text, bbox, font_info_times)
    mock_canvas.setFillColorRGB.assert_any_call(1.0, 0.0, 0.0) # Red

    # Test with Courier font
    font_info_courier = {"font_name": "Courier", "font_size": 12}
    pdf_text_layout_instance.draw_translated_text(mock_canvas, translated_text, bbox, font_info_courier)
    mock_canvas.setFillColorRGB.assert_any_call(0.0, 0.0, 1.0) # Blue

    # Test with unknown font (should default to gray)
    font_info_unknown = {"font_name": "UnknownFont", "font_size": 12}
    pdf_text_layout_instance.draw_translated_text(mock_canvas, translated_text, bbox, font_info_unknown)
    mock_canvas.setFillColorRGB.assert_any_call(0.5, 0.5, 0.5) # Gray

    # Test with font name containing '+' (e.g., XLDELO+CMMI10 -> CMMI10)
    font_info_plus = {"font_name": "XLDELO+CMMI10", "font_size": 12}
    # Add CMMI10 to the mock config's FONT_COLOR_MAP
    MockConfig.FONT_COLOR_MAP["CMMI10"] = (0.1, 0.2, 0.3)
    pdf_text_layout_instance.draw_translated_text(mock_canvas, translated_text, bbox, font_info_plus)
    mock_canvas.setFillColorRGB.assert_any_call(0.1, 0.2, 0.3)

    # Verify log messages
    assert any("Setting font color for 'Helvetica' to RGB(0.0, 0.0, 0.0)" in record.message for record in caplog.records)
    assert any("Setting font color for 'Times-Roman' to RGB(1.0, 0.0, 0.0)" in record.message for record in caplog.records)
    assert any("Setting font color for 'Courier' to RGB(0.0, 0.0, 1.0)" in record.message for record in caplog.records)
    assert any("Setting font color for 'UnknownFont' to RGB(0.5, 0.5, 0.5)" in record.message for record in caplog.records)
    assert any("Setting font color for 'CMMI10' to RGB(0.1, 0.2, 0.3)" in record.message for record in caplog.records)

def test_draw_translated_text_without_font_color_highlight(pdf_text_layout_instance, mock_canvas, caplog):
    caplog.set_level(logging.DEBUG)

    # Temporarily disable font color highlighting
    with patch('app.pdf_text_layout.Config.ENABLE_FONT_COLOR_HIGHLIGHT', False):
        translated_text = "Hello World"
        bbox = (10, 10, 100, 50)
        font_info = {"font_name": "Helvetica", "font_size": 12}
        pdf_text_layout_instance.draw_translated_text(mock_canvas, translated_text, bbox, font_info)
        mock_canvas.setFillColorRGB.assert_any_call(0, 0, 0) # Should be black
        assert not any("Setting font color for" in record.message for record in caplog.records)
