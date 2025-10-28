# Copyright 2025 npz35
#
# See the NOTICE file for this project for license details.
# This file may not be used except in accordance with the NOTICE.

import logging
import logging
import math
import queue
from typing import List, Dict, Any, Tuple, Optional
import pdfplumber
from pdfplumber.page import Page
from app.data_model import BBox, PageAnalyzeData, CharBlock, WordBlock, TextBlock, TextArea, FontInfo, Line
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
    MERGE_AREA_Y_TOLERANCE = 8.0

    def __init__(self):
        super().__init__()
        self.all_page_sizes: List[Tuple[float, float]] = []
        self.all_page_char_blocks: List[List[CharBlock]] = []
        self.all_page_word_blocks: List[List[WordBlock]] = []
        self.all_page_text_blocks: List[List[TextBlock]] = []
        self.all_page_text_areas: List[List[TextArea]] = []
        self.all_page_rect_blocks: List[List[BBox]] = []
        self.all_page_image_blocks: List[List[BBox]] = []

    def extract_pazesizes(self, pdf_path: str) -> List[Tuple[float, float]]:
        self.logger.debug(f"Function start: extract_pazesizes(pdf_path='{pdf_path}')")

        if self.all_page_sizes:
            return self.all_page_sizes

        try:
            with pdfplumber.open(pdf_path) as pdf:
                self.all_page_sizes = []
                for page in pdf.pages:
                    self.all_page_sizes.append((page.width, page.height))
        except Exception as e:
            self.logger.error(f"Error extracting paze sizes with pdfplumber from {pdf_path}: {e}")
            raise

        self.logger.debug(f"Function end: extract_pazesizes. Extracted {len(self.all_page_sizes)} pages.")
        return self.all_page_sizes

    def extract_charblocks(self, pdf_path: str) -> List[List[CharBlock]]:
        self.logger.debug(f"Function start: extract_charblocks(pdf_path='{pdf_path}')")

        self.extract_pazesizes(pdf_path)

        if self.all_page_char_blocks:
            return self.all_page_char_blocks

        try:
            with pdfplumber.open(pdf_path) as pdf:
                self.all_page_char_blocks = []
                for page_num, page in enumerate(pdf.pages):
                    current_page_char_blocks: List[CharBlock] = []
                    for char_data in page.chars:
                        font_name = char_data.get('fontname', 'unknown')
                        font_size = char_data.get('size', 0.0)
                        is_bold = 'bold' in font_name.lower()
                        is_italic = 'italic' in font_name.lower()

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
                            page_number=page_num + 1
                        )
                        current_page_char_blocks.append(char_block)
                    self.logger.debug(f"current_page_char_blocks: {current_page_char_blocks}")
                    self.all_page_char_blocks.append(current_page_char_blocks)
        except Exception as e:
            self.logger.error(f"Error extracting character with pdfplumber from {pdf_path}: {e}")
            raise

        self.logger.debug(f"Function end: extract_charblocks. Extracted {len(self.all_page_char_blocks)} pages with character blocks.")
        return self.all_page_char_blocks

    def extract_wordblocks(self, pdf_path: str) -> List[List[WordBlock]]:
        self.logger.debug(f"Function start: extract_wordblocks(pdf_path='{pdf_path}')")

        if self.all_page_word_blocks:
            return self.all_page_word_blocks

        self.all_page_char_blocks: List[List[CharBlock]] = self.extract_charblocks(pdf_path)

        for page_char_blocks in self.all_page_char_blocks:
            current_page_word_blocks: List[WordBlock] = []
            current_word_chars: List[CharBlock] = []
            
            if not page_char_blocks:
                self.logger.warning("page_char_blocks is empty")
                self.all_page_word_blocks.append([])
                continue

            for i, char_block in enumerate(page_char_blocks):
                if not current_word_chars:
                    current_word_chars.append(char_block)
                else:
                    # Check if the current character is part of the same word
                    # A simple heuristic: if the horizontal distance between characters is small
                    # and they are on roughly the same baseline, consider them part of the same word.
                    last_char = current_word_chars[-1]
                    horizontal_distance = char_block.bbox.x0 - last_char.bbox.x1
                    vertical_overlap = max(0, min(char_block.bbox.y1, last_char.bbox.y1) - max(char_block.bbox.y0, last_char.bbox.y0))
                    
                    # Heuristic for same word: small horizontal gap, significant vertical overlap, and similar font size
                    # A threshold for horizontal distance can be a fraction of the font size or a fixed small value.
                    # For simplicity, let's use a fixed small value (e.g., 2 units) and check for vertical overlap.
                    # Also, consider font changes as word breaks.
                    is_near = horizontal_distance < 2
                    is_sameline = vertical_overlap > (min(char_block.height(), last_char.height()) * 0.5)
                    is_same_font_size = char_block.font_info.size == last_char.font_info.size
                    is_same_font_name = char_block.font_info.name == last_char.font_info.name
                    if is_near and is_sameline and is_same_font_size and is_same_font_name:
                        current_word_chars.append(char_block)
                        continue

                    # End of a word, create WordBlock
                    first_char = current_word_chars[0]
                    last_char_of_word = current_word_chars[-1]
                    
                    word_bbox = BBox(
                        x0=first_char.bbox.x0,
                        y0=min(c.bbox.y0 for c in current_word_chars),
                        x1=last_char_of_word.bbox.x1,
                        y1=max(c.bbox.y1 for c in current_word_chars)
                    )
                    
                    word_text = "".join([c.char for c in current_word_chars])
                    
                    current_page_word_blocks.append(WordBlock(
                        word=word_text,
                        bbox=word_bbox,
                        font_info=first_char.font_info,
                        page_number=first_char.page_number
                    ))
                    
                    # Start a new word
                    current_word_chars = [char_block]
            
            # Add the last word block if any characters are remaining
            if current_word_chars:
                first_char = current_word_chars[0]
                last_char_of_word = current_word_chars[-1]
                
                word_bbox = BBox(
                    x0=first_char.bbox.x0,
                    y0=min(c.bbox.y0 for c in current_word_chars),
                    x1=last_char_of_word.bbox.x1,
                    y1=max(c.bbox.y1 for c in current_word_chars)
                )
                
                word_text = "".join([c.char for c in current_word_chars])
                
                current_page_word_blocks.append(WordBlock(
                    word=word_text,
                    bbox=word_bbox,
                    font_info=first_char.font_info,
                    page_number=first_char.page_number
                ))
            
            self.logger.debug(f"current_page_word_blocks: {current_page_word_blocks}")
            self.all_page_word_blocks.append(current_page_word_blocks)

        self.logger.debug(f"Function end: extract_wordblocks. Extracted {len(self.all_page_word_blocks)} pages with word blocks.")
        return self.all_page_word_blocks
    
    def _are_blocks_on_same_line(self, bbox1: BBox, bbox2: BBox, y_tolerance: float = 2.0) -> bool:
        """
        二つのBBoxが同じ行にあるかを判定するのだ。
        y軸方向の重なりを考慮するのだ。
        """
        # Check for vertical overlap
        vertical_overlap = max(0, min(bbox1.y1, bbox2.y1) - max(bbox1.y0, bbox2.y0))
        
        # If there's significant vertical overlap, consider them on the same line
        # The threshold can be adjusted based on typical line spacing and font sizes
        h1 = bbox1.height()
        h2 = bbox2.height()
        min_height = min(h1, h2)
        return vertical_overlap > (min_height - y_tolerance)

    def extract_textblocks(self, pdf_path: str) -> List[List[TextBlock]]:
        self.logger.debug(f"Function start: extract_textblocks(pdf_path='{pdf_path}')")

        if self.all_page_text_blocks:
            return self.all_page_text_blocks

        self.all_page_word_blocks: List[List[WordBlock]] = self.extract_wordblocks(pdf_path)

        for page_word_blocks in self.all_page_word_blocks:
            current_page_text_blocks: List[TextBlock] = []
            current_text_block: Optional[TextBlock] = None

            for word_block in page_word_blocks:
                # If current_text_block is None or font info changes, start a new TextBlock
                is_none = current_text_block is None
                # not_same_font_name = is_none or current_text_block.font_info.name != word_block.font_info.name
                # not_same_font_size = is_none or current_text_block.font_info.size != word_block.font_info.size
                # not_same_bold = is_none or current_text_block.font_info.is_bold != word_block.font_info.is_bold
                # not_same_italic = is_none or current_text_block.font_info.is_italic != word_block.font_info.is_italic
                not_same_font = False # TODO: is_none or not_same_font_name or not_same_font_size or not_same_bold or not_same_italic
                not_same_line = is_none or not self._are_blocks_on_same_line(current_text_block.bbox, word_block.bbox)
                if is_none or not_same_font or not_same_line:
                    current_text_block = TextBlock(
                        text=word_block.word,
                        bbox=word_block.bbox,
                        font_info=word_block.font_info,
                        page_number=word_block.page_number,
                    )
                    current_page_text_blocks.append(current_text_block)
                else:
                    # If same font info and on the same line, append to existing TextBlock
                    current_text_block.text += " " + word_block.word
                    current_text_block.bbox.x1 = word_block.bbox.x1
                    current_text_block.bbox.y0 = min(current_text_block.bbox.y0, word_block.bbox.y0)
                    current_text_block.bbox.y1 = max(current_text_block.bbox.y1, word_block.bbox.y1)
            
            if current_page_text_blocks:
                self.logger.debug(f"current_page_text_blocks: {current_page_text_blocks}")
                self.all_page_text_blocks.append(current_page_text_blocks)

        self.logger.debug(f"Function end: extract_textblocks. Extracted {len(self.all_page_text_blocks)} pages with text blocks.")
        return self.all_page_text_blocks
    
    def extract_textareas(self, pdf_path: str) -> List[List[TextArea]]:
        self.logger.debug(f"Function start: extract_textareas(pdf_path='{pdf_path}')")

        if self.all_page_text_areas:
            return self.all_page_text_areas

        self.all_page_text_blocks: List[List[TextBlock]] = self.extract_textblocks(pdf_path)

        merge_page_text_areas: List[TextArea]
        page_text_areas: List[TextArea]
        current_text_area: TextArea
        for page_num, page_text_blocks in enumerate(self.all_page_text_blocks):
            merge_page_text_areas = []
            page_text_areas = []

            # Horizontal merge
            self.logger.debug(f"Page {page_num + 1}: Horizontal merge text blocks")
            sorted_page_text_blocks: List[TextBlock] = sorted(page_text_blocks, key=lambda block: (-block.bbox.y0, block.bbox.x0))
            current_text_area = TextArea(blocks=[], bbox=BBox(x0=math.inf, x1=-math.inf, y0=math.inf, y1=-math.inf))

            # self.logger.warning(f"Page {page_num + 1}: init page_text_blocks size: {len(page_text_blocks)}")
            # self.logger.warning(f"Page {page_num + 1}: init current_text_area.blocks size: {len(current_text_area.blocks)}")

            for text_block in sorted_page_text_blocks:
                if not current_text_area.blocks:
                    current_text_area.append(text_block)
                    self.logger.warning(f"Page {page_num + 1}: first {current_text_area.bbox.y0:.2f} < {text_block.bbox.y1:.2f} and {text_block.bbox.y0:.2f} < {current_text_area.bbox.y1:.2f}")
                    continue

                # self.logger.warning(f"Page {page_num + 1}: {current_text_area.bbox.x0:.2f} < {text_block.bbox.x1:.2f} and {text_block.bbox.x0:.2f} < {current_text_area.bbox.x1:.2f}")
                # self.logger.warning(f"Page {page_num + 1}: {current_text_area.bbox.y0:.2f} < {text_block.bbox.y1:.2f} and {text_block.bbox.y0:.2f} < {current_text_area.bbox.y1:.2f}")

                overlap_horizontal = current_text_area.bbox.x0 < text_block.bbox.x1 and text_block.bbox.x0 < current_text_area.bbox.x1
                overlap_vertical = current_text_area.bbox.y0 < text_block.bbox.y1 and text_block.bbox.y0 < current_text_area.bbox.y1
                nearby_vertical = abs(current_text_area.bbox.y0 - text_block.bbox.y1) < self.MERGE_AREA_Y_TOLERANCE or abs(current_text_area.bbox.y1 - text_block.bbox.y0) < self.MERGE_AREA_Y_TOLERANCE
                overlap = overlap_horizontal and overlap_vertical
                nearby_area = overlap or (overlap_horizontal and nearby_vertical)

                self.logger.debug(f"Page {page_num + 1}: current_text_area text : {current_text_area.text()}")
                self.logger.debug(f"Page {page_num + 1}: text_block text        : {text_block.text}")
                self.logger.debug(f"Page {page_num + 1}: overlap_horizontal     : {overlap_horizontal}")
                self.logger.debug(f"Page {page_num + 1}: overlap_vertical       : {overlap_vertical}")
                self.logger.debug(f"Page {page_num + 1}: nearby_vertical        : {nearby_vertical}")
                self.logger.debug(f"Page {page_num + 1}: nearby_area            : {nearby_area}")

                if not nearby_area:
                    current_text_area.blocks = sorted(current_text_area.blocks, key=lambda block: (-block.bbox.y0, block.bbox.x0))
                    merge_page_text_areas.append(current_text_area)
                    current_text_area = TextArea(blocks=[], bbox=BBox(x0=math.inf, x1=-math.inf, y0=math.inf, y1=-math.inf))

                current_text_area.append(text_block)

            if current_text_area.blocks:
                current_text_area.blocks = sorted(current_text_area.blocks, key=lambda block: (-block.bbox.y0, block.bbox.x0))
                merge_page_text_areas.append(current_text_area)

            # Vertical merge
            self.logger.debug(f"Page {page_num + 1}: Vertical merge text areas")
            sorted_page_text_areas: List[TextArea] = sorted(merge_page_text_areas, key=lambda area: (area.bbox.x0, -area.bbox.y0))
            current_text_area = TextArea(blocks=[], bbox=BBox(x0=math.inf, x1=-math.inf, y0=math.inf, y1=-math.inf))
            for text_area in sorted_page_text_areas:
                if not current_text_area.blocks:
                    for block in text_area.blocks:
                        current_text_area.append(block)
                    continue

                overlap_horizontal = current_text_area.bbox.x0 < text_area.bbox.x1 and text_area.bbox.x0 < current_text_area.bbox.x1
                overlap_vertical = current_text_area.bbox.y0 < text_area.bbox.y1 and text_area.bbox.y0 < current_text_area.bbox.y1
                nearby_vertical = abs(current_text_area.bbox.y0 - text_area.bbox.y1) < 2.0 or abs(current_text_area.bbox.y1 - text_area.bbox.y0) < 2.0
                nearby_area = (overlap_horizontal and overlap_vertical) or (overlap_horizontal and nearby_vertical)

                self.logger.debug(f"Page {page_num + 1}: current_text_area text : {current_text_area.text()}")
                self.logger.debug(f"Page {page_num + 1}: text_block text        : {text_block.text}")
                self.logger.debug(f"Page {page_num + 1}: overlap_horizontal     : {overlap_horizontal}")
                self.logger.debug(f"Page {page_num + 1}: overlap_vertical       : {overlap_vertical}")
                self.logger.debug(f"Page {page_num + 1}: nearby_vertical        : {nearby_vertical}")
                self.logger.debug(f"Page {page_num + 1}: nearby_area            : {nearby_area}")

                if not nearby_area:
                    current_text_area.blocks = sorted(current_text_area.blocks, key=lambda block: (block.bbox.x0, -block.bbox.y0))
                    page_text_areas.append(current_text_area)
                    current_text_area = TextArea(blocks=[], bbox=BBox(x0=math.inf, x1=-math.inf, y0=math.inf, y1=-math.inf))

                for block in text_area.blocks:
                    current_text_area.append(block)

            if current_text_area.blocks:
                current_text_area.blocks = sorted(current_text_area.blocks, key=lambda block: (block.bbox.x0, -block.bbox.y0))
                page_text_areas.append(current_text_area)

            if page_text_areas:
                self.logger.debug(f"Page {page_num + 1}: page_text_areas: {page_text_areas}")
                self.logger.debug(f"Page {page_num + 1}: page_text_areas size: {len(page_text_areas)}")
                self.all_page_text_areas.append(page_text_areas)

        self.logger.debug(f"Function end: extract_textareas. Extracted {len(self.all_page_text_areas)} pages with text areas.")
        return self.all_page_text_areas

    def extract_rect_blocks(self, pdf_path: str) -> List[List[BBox]]:
        self.logger.debug(f"Function start: extract_rect_blocks(pdf_path='{pdf_path}')")

        with pdfplumber.open(pdf_path) as pdf:
            self.current_page_rect_blocks = []
            for page in pdf.pages:
                current_page_rect_blocks: List[BBox] = []
                current_page_rect_blocks = [BBox(x0=rect['x0'], y0=page.height - rect['bottom'], x1=rect['x1'], y1=page.height - rect['top']) for rect in page.rects]
                self.all_page_rect_blocks.append(current_page_rect_blocks)

        self.logger.debug(f"Function end: extract_rect_blocks. Extracted {len(self.all_page_rect_blocks)} pages with rect blocks.")
        return self.all_page_rect_blocks

    def extract_image_blocks(self, pdf_path: str) -> List[List[BBox]]:
        self.logger.debug(f"Function start: extract_image_blocks(pdf_path='{pdf_path}')")

        with pdfplumber.open(pdf_path) as pdf:
            self.all_page_image_blocks = []
            for page in pdf.pages:
                current_page_image_blocks: List[BBox] = []
                current_page_image_blocks = [BBox(x0=image['x0'], y0=page.height - image['bottom'], x1=image['x1'], y1=page.height - image['top']) for image in page.images]
                self.all_page_image_blocks.append(current_page_image_blocks)

        self.logger.debug(f"Function end: extract_image_blocks. Extracted {len(self.all_page_image_blocks)} pages with image blocks.")
        return self.all_page_image_blocks

    def crop_textblock(self, pdf_path: str, current_page_number: int, line: Line) -> List[TextBlock]:
        """
        PDFページから単語とそのbbox情報を抽出するのだ。
        """
        self.logger.debug(f"Function start: crop_textblock(pdf_path='{pdf_path}', current_page_number={current_page_number}, line={line})")

        all_page_text_blocks = self.extract_textblocks(pdf_path)
        page_text_blocks = all_page_text_blocks[current_page_number - 1]

        crop_page_text_blocks = page_text_blocks
        # crop_page_text_blocks = [block for block in crop_page_text_blocks if line.x0 <= block.bbox.x0]
        crop_page_text_blocks = [block for block in crop_page_text_blocks if line.y0 <= block.bbox.y0]
        # crop_page_text_blocks = [block for block in crop_page_text_blocks if block.bbox.x1 <= line.x1]
        crop_page_text_blocks = [block for block in crop_page_text_blocks if block.bbox.y1 <= line.y1]

        self.logger.debug(f'Page {current_page_number}: page_text_blocks size     : {len(page_text_blocks)}')
        self.logger.debug(f'Page {current_page_number}: line                      : {line}')
        self.logger.debug(f'Page {current_page_number}: crop_page_text_blocks size: {len(crop_page_text_blocks)}')

        self.logger.debug(f"Function end: crop_textblock(pdf_path='{pdf_path}', current_page_number={current_page_number}, line={line})")
        return crop_page_text_blocks

    def first_page_width(self, pdf_path: str) -> float:
        with pdfplumber.open(pdf_path) as pdf:
            if pdf.pages:
                return pdf.pages[0].width
        
        # デフォルトのページ幅を設定 (例: A4の幅)
        return 595.276 # ReportLabのA4幅
