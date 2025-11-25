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
    return 'dummy_path.pdf'

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
