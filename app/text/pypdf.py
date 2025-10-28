# Copyright 2025 npz35
#
# See the NOTICE file for this project for license details.
# This file may not be used except in accordance with the NOTICE.

import logging
from typing import List, Dict, Any
from pypdf import PdfReader

from app.text.common import PdfAnalyzer
from app.data_model import BBox, TextBlock, FontInfo

logger: logging.Logger = logging.getLogger(__name__)

class PyPdfAnalyzer(PdfAnalyzer):
    def __init__(self):
        super().__init__()

    def extract_textblocks(self, pdf_path: str) -> List[List[TextBlock]]:
        self.logger.debug(f"Function start: extract_textblocks(pdf_path='{pdf_path}')")
        extracted_data: List[List[TextBlock]] = []

        try:
            reader = PdfReader(pdf_path)
            for page_num, page in enumerate(reader.pages):
                text = page.extract_text()
                if text:
                    # pypdf does not provide character-level bounding boxes directly.
                    # We will approximate by using the page's bounding box for the entire text.
                    # This is a simplification and may not be suitable for all use cases.
                    # For more precise control, pdfminer.six is better.
                    
                    # Get page dimensions (width and height)
                    # MediaBox is usually [x0, y0, x1, y1]
                    # Assuming bottom-left origin for MediaBox
                    logger.warning(f"pypdf does not provide character-level bounding boxes directly.")

                    page_bbox = page.mediabox
                    bbox = (float(page_bbox[0]), float(page_bbox[1]), float(page_bbox[2]), float(page_bbox[3]))

                    # Create a dummy FontInfo since pypdf doesn't provide it
                    font_info = FontInfo(name="unknown", size=0.0, is_bold=False, is_italic=False)
                    
                    text_block = TextBlock(
                        text=text,
                        bbox=BBox(x0=bbox[0], y0=bbox[1], x1=bbox[2], y1=bbox[3]),
                        font_info=font_info,
                        page_number=page_num + 1,
                        column_index=0 # Assuming single column for pypdf
                    )
                    extracted_data.append([text_block])

        except Exception as e:
            self.logger.error(f"Error extracting text with pypdf from {pdf_path}: {e}")
            raise

        self.logger.debug(f"Function end: extract_text_with_positions. Extracted {len(extracted_data)} elements.")
        return extracted_data

    def crop_textblock(self, pdf_path: str, page_number: int) -> List[TextBlock]:
        raise NotImplementedError("pypdf does not support word-level bounding box extraction directly.")
