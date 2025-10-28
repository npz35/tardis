# Copyright 2025 npz35
#
# See the NOTICE file for this project for license details.
# This file may not be used except in accordance with the NOTICE.

import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Tuple

from pdfplumber.page import Page

from app.data_model import BBox, TextBlock, PageAnalyzeData, FontInfo

logger: logging.Logger = logging.getLogger(__name__)

class PdfAnalyzer(ABC):
    """
    PDF解析の抽象基底クラスなのだ。
    異なるPDF解析ライブラリ（pdfplumber, pypdfなど）に対応するための共通インターフェースを定義するのだ。
    """

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    def extract_textblocks(self, pdf_path: str) -> List[List[TextBlock]]:
        """
        PDFからテキストとその位置情報を抽出するのだ。
        """
        pass

    @abstractmethod
    def crop_textblock(self, pdf_path: str, page_number: int) -> List[TextBlock]:
        """
        PDFページから単語とそのbbox情報を抽出するのだ。
        """
        pass
