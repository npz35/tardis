# Copyright 2025 npz35
#
# See the NOTICE file for this project for license details.
# This file may not be used except in accordance with the NOTICE.

import logging
import math
from typing import Optional
import pdfplumber
from app.config import Config
from app.data_model import BBox, CharBlock, ColumnIndex, WordBlock, TextBlock, TextArea, FontInfo, ColumnType
from app.text.common import PdfAnalyzer

'''
Example of each element of extract_text_lines

{
    'text': 'Hello, World! (Page 1)',
    'x0': 78.0,
    'top': 80.07,
    'x1': 176.36,
    'bottom': 90.07,
    'chars': [
        {
            'matrix': (1.0, 0.0, 0.0, 1.0, 78.0, 704.0),
            'fontname': 'Helvetica',
            'adv': 7.22,
            'upright': True,
            'x0': 78.0,
            'y0': 701.93,
            'x1': 85.22,
            'y1': 711.93,
            'width': 7.21,
            'height': 10.0,
            'size': 10.0,
            'mcid': None,
            'tag': None,
            'object_type': 'char',
            'page_number': 1,
            'ncs': 'DeviceRGB',
            'text': 'H',
            'stroking_color': (0,),
            'non_stroking_color': (0.0, 0.0, 0.0),
            'top': 80.07000000000005,
            'bottom': 90.07000000000005,
            'doctop': 80.07000000000005
        },
        {
            'matrix': ...
        }
    ]
}
'''

class PdfplumberAnalyzer(PdfAnalyzer):
    def __init__(self):
        super().__init__()

    def extract_pazesizes(self, pdf_path: str) -> list[tuple[float, float]]:
        self.logger.debug(f"Function start: extract_pazesizes(pdf_path='{pdf_path}')")

        if self.all_page_sizes:
            return self.all_page_sizes

        try:
            with pdfplumber.open(pdf_path) as pdf:
                self.all_page_sizes = []
                for page_idx, page in enumerate(pdf.pages):
                    if Config.MAX_PDF_PAGES <= page_idx:
                        break

                    self.all_page_sizes.append((page.width, page.height))
        except Exception as e:
            self.logger.error(f'Error extracting paze sizes with pdfplumber from {pdf_path}: {e}')
            raise

        self.logger.debug(f'Function end: extract_pazesizes. Extracted {len(self.all_page_sizes)} pages.')
        return self.all_page_sizes

    def extract_charblocks(self, pdf_path: str) -> list[list[CharBlock]]:
        self.logger.debug(f"Function start: extract_charblocks(pdf_path='{pdf_path}')")

        self.extract_pazesizes(pdf_path)

        if self.all_page_char_blocks:
            return self.all_page_char_blocks

        try:
            with pdfplumber.open(pdf_path) as pdf:
                self.all_page_char_blocks = []
                for page_idx, page in enumerate(pdf.pages):
                    if Config.MAX_PDF_PAGES <= page_idx:
                        break

                    self.logger.debug(f'Page {page_idx + 1}: Extract characters.')
                    current_page_char_blocks: list[CharBlock] = []
                    
                    # Extract text lines to analyze column structure
                    text_lines = page.extract_text_lines()
                    column_boundaries = self._detect_column_boundaries(text_lines, page.width)

                    for char_data in page.chars:
                        font_name = char_data.get('fontname', 'unknown')
                        font_size = char_data.get('size', 0.0)
                        is_bold = 'bold' in font_name.lower()
                        is_italic = 'italic' in font_name.lower()

                        # Determine column index based on x position
                        char_x = char_data['x0']
                        column_index = self._get_column_index(char_x, column_boundaries)

                        char_block = CharBlock(
                            char=char_data['text'],
                            bbox=BBox(
                                x0=char_data['x0'],
                                y0=char_data['y0'],
                                x1=char_data['x1'],
                                y1=char_data['y1']
                            ),
                            font_info=FontInfo(
                                name=font_name,
                                size=font_size,
                                is_bold=is_bold,
                                is_italic=is_italic
                            ),
                            page_number=page_idx + 1,
                            column_index=column_index
                        )
                        current_page_char_blocks.append(char_block)
                    # self.logger.debug(f'current_page_char_blocks: {current_page_char_blocks}')
                    self.all_page_char_blocks.append(current_page_char_blocks)
        except Exception as e:
            self.logger.error(f'Error extracting character with pdfplumber from {pdf_path}: {e}')
            raise

        self.logger.debug(f'Function end: extract_charblocks. Extracted {len(self.all_page_char_blocks)} pages with character blocks.')
        return self.all_page_char_blocks

    def extract_rect_blocks(self, pdf_path: str) -> list[list[BBox]]:
        self.logger.debug(f"Function start: extract_rect_blocks(pdf_path='{pdf_path}')")

        with pdfplumber.open(pdf_path) as pdf:
            self.current_page_rect_blocks = []
            for page_idx, page in enumerate(pdf.pages):
                if Config.MAX_PDF_PAGES <= page_idx:
                    break

                current_page_rect_blocks: list[BBox] = []
                current_page_rect_blocks = [BBox(x0=rect['x0'], y0=page.height - rect['bottom'], x1=rect['x1'], y1=page.height - rect['top']) for rect in page.rects]
                self.all_page_rect_blocks.append(current_page_rect_blocks)

        self.logger.debug(f'Function end: extract_rect_blocks. Extracted {len(self.all_page_rect_blocks)} pages with rect blocks.')
        return self.all_page_rect_blocks

    def extract_image_blocks(self, pdf_path: str) -> list[list[BBox]]:
        self.logger.debug(f"Function start: extract_image_blocks(pdf_path='{pdf_path}')")

        with pdfplumber.open(pdf_path) as pdf:
            self.all_page_image_blocks = []
            for page_idx, page in enumerate(pdf.pages):
                if Config.MAX_PDF_PAGES <= page_idx:
                    break

                current_page_image_blocks: list[BBox] = []
                current_page_image_blocks = [BBox(x0=image['x0'], y0=page.height - image['bottom'], x1=image['x1'], y1=page.height - image['top']) for image in page.images]
                self.all_page_image_blocks.append(current_page_image_blocks)

        self.logger.debug(f'Function end: extract_image_blocks. Extracted {len(self.all_page_image_blocks)} pages with image blocks.')
        return self.all_page_image_blocks

    def _detect_column_boundaries(self, text_lines: list[dict], page_width: float) -> list[float]:
        """
        Detect column boundaries by analyzing the x positions of text lines.
        Returns a list of x positions that represent column boundaries.
        """
        if not text_lines:
            return []
        
        # Collect x0 positions from all text lines
        x_positions = []
        for line in text_lines:
            if 'x0' in line:
                x_positions.append(line['x0'])
        
        if not x_positions:
            return []
        
        # Sort x positions
        x_positions.sort()
        
        # Find gaps between x positions that might indicate column boundaries
        gaps = []
        for i in range(1, len(x_positions)):
            gap = x_positions[i] - x_positions[i-1]
            gaps.append((x_positions[i-1], x_positions[i], gap))
        
        # Identify significant gaps (potential column boundaries)
        # A gap is significant if it's larger than 20% of the page width
        significant_gaps = [gap for gap in gaps if gap[2] > page_width * 0.2]
        
        # Return the x positions of significant gaps
        return [gap[1] for gap in significant_gaps]
    
    def _get_column_index(self, x: float, column_boundaries: list[float]) -> ColumnIndex:
        """
        Determine the column index based on x position and column boundaries.
        """
        if not column_boundaries:
            return ColumnIndex.UNKNOWN
        
        # Sort boundaries
        sorted_boundaries = sorted(column_boundaries)
        
        # If x is to the left of the first boundary, it's in the left column
        if x < sorted_boundaries[0]:
            return ColumnIndex.LEFT
        
        # If x is to the right of the last boundary, it's in the right column
        if x >= sorted_boundaries[-1]:
            return ColumnIndex.RIGHT
        
        # If x is between boundaries, determine which column it's in
        for i, boundary in enumerate(sorted_boundaries):
            if x < boundary:
                return ColumnIndex.LEFT if i % 2 == 0 else ColumnIndex.RIGHT
        
        return ColumnIndex.UNKNOWN
