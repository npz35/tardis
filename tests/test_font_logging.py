# Copyright 2025 npz35
#
# See the NOTICE file for this project for license details.
# This file may not be used except in accordance with the NOTICE.

import pytest
import logging
from unittest.mock import MagicMock, patch
from app.config import Config
from app.pdf_text_manager import PdfTextManager
from pdfminer.layout import LTChar, LTTextLineHorizontal, LTTextBoxHorizontal, LAParams
from pdfminer.pdfpage import PDFPage

# Mock Config for testing purposes
class MockConfig:
    MAX_PDF_PAGES = 10

# Mock PDFPage for testing purposes
class MockPDFPage:
    def __init__(self, pageid, elements):
        self.pageid = pageid
        self._elements = elements
        self.x0 = 0
        self.y0 = 0
        self.x1 = 100
        self.y1 = 100

    def __iter__(self):
        return iter(self._elements)

@pytest.fixture
def pdf_text_manager():
    return PdfTextManager()

@pytest.fixture
def mock_pdf_path():
    return "dummy_path.pdf"

def create_mock_char(text, fontname, size, x0=0, y0=0, x1=10, y1=10):
    char = MagicMock(spec=LTChar)
    char.get_text.return_value = text
    char.fontname = fontname
    char.size = size
    char.bbox = (x0, y0, x1, y1) # bbox属性を追加するのだ
    return char

def create_mock_text_line(chars, x0=0, y0=0, x1=100, y1=10):
    line = MagicMock(spec=LTTextLineHorizontal)
    line.x0 = x0
    line.y0 = y0
    line.x1 = x1
    line.y1 = y1
    line.__iter__.return_value = iter(chars)
    return line

def create_mock_text_box(lines, x0=0, y0=0, x1=100, y1=100):
    box = MagicMock(spec=LTTextBoxHorizontal)
    box.x0 = x0
    box.y0 = y0
    box.x1 = x1
    box.y1 = y1
    box.__iter__.return_value = iter(lines)
    return box

@patch('app.text.pdfminer.extract_pages')
def test_font_logging(mock_extract_pages, pdf_text_manager, mock_pdf_path, caplog):
    caplog.set_level(logging.INFO)

    # ConfigのTEXT_EXTRACTION_METHODを一時的にpdfminerに設定
    original_extraction_method = Config.TEXT_EXTRACTION_METHOD
    Config.TEXT_EXTRACTION_METHOD = "pdfminer"

    # Mock characters with different font names
    char1 = create_mock_char("H", "Helvetica", 12, x0=0, y0=80, x1=10, y1=90)
    char2 = create_mock_char("e", "Helvetica", 12, x0=10, y0=80, x1=20, y1=90)
    char3 = create_mock_char("l", "Times-Roman", 10, x0=0, y0=60, x1=10, y1=70)
    char4 = create_mock_char("l", "Times-Roman", 10, x0=10, y0=60, x1=20, y1=70)
    char5 = create_mock_char("o", "Courier", 14, x0=0, y0=40, x1=10, y1=50)

    # Mock text lines
    line1 = create_mock_text_line([char1, char2])
    line2 = create_mock_text_line([char3, char4])
    line3 = create_mock_text_line([char5])

    # Mock text boxes
    text_box1 = create_mock_text_box([line1])
    text_box2 = create_mock_text_box([line2, line3])

    # Mock page layout
    mock_page_layout = MockPDFPage(pageid=1, elements=[text_box1, text_box2])
    mock_extract_pages.return_value = [mock_page_layout]

    # Call the method under test
    pdf_text_manager.extract_textblocks(mock_pdf_path)

    # Check if the log message for unique font names is present
    expected_log_message = "All unique font names found: ['Courier', 'Helvetica', 'Times-Roman']"
    assert any(expected_log_message in record.message for record in caplog.records)

    # Check if the log message contains the expected font names
    found_log = False
    for record in caplog.records:
        if "All unique font names found:" in record.message:
            found_log = True
            # Extract the list part from the log message and convert to a set for comparison
            log_fonts_str = record.message.split("All unique font names found: ")[1]
            # Use ast.literal_eval to safely parse the string representation of the list
            import ast
            logged_fonts = set(ast.literal_eval(log_fonts_str))
            expected_fonts = {'Helvetica', 'Times-Roman', 'Courier'}
            assert logged_fonts == expected_fonts
            break
    assert found_log, "Expected log message 'All unique font names found:' not found."

    # ConfigのTEXT_EXTRACTION_METHODを元に戻す
    Config.TEXT_EXTRACTION_METHOD = original_extraction_method
