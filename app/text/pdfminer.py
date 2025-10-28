# Copyright 2025 npz35
#
# See the NOTICE file for this project for license details.
# This file may not be used except in accordance with the NOTICE.

import logging
from typing import List, Dict, Any, Tuple
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextContainer, LTChar, LAParams
from app.config import Config
from app.data_model import BBox, TextBlock, PageAnalyzeData, FontInfo
from app.text.common import PdfAnalyzer

logger: logging.Logger = logging.getLogger(__name__)

CUSTOM_STATIC_DECODE = {
    # XLDELO+CMMI10
    'CMMI10': {
        '"': 'ε',
    }
}

class PdfminerAnalyzer(PdfAnalyzer):
    def __init__(self):
        super().__init__()
        self.laparams = LAParams(
            line_overlap=0.5,
            char_margin=1.0,
            word_margin=0.1,
            line_margin=0.5,
            boxes_flow=0.5,
            detect_vertical=False,
            all_texts=True
        )

    def extract_textblocks(self, pdf_path: str) -> List[List[TextBlock]]:
        self.logger.debug(f"Method start: extract_textblocks(pdf_path='{pdf_path}')")
        """
        Extracts text and its position from a PDF using pdfminer.six.

        Args:
            pdf_path: Path to the PDF file.

        Returns:
            A list of lists of TextBlock, each containing character and its bounding box.
        """

        self.logger.info(f"Extracting text with positions from {pdf_path} using pdfminer.six")
        all_font_names = set()
        extracted_data: List[List[TextBlock]] = []
        try:
            for page_layout in extract_pages(pdf_path, laparams=self.laparams):
                if page_layout.pageid > Config.MAX_PDF_PAGES:
                    self.logger.warning(f"Reached maximum page limit of {Config.MAX_PDF_PAGES}. Stopping further page processing.")
                    break
                
                page_text_blocks: List[TextBlock] = []
                for element in page_layout:
                    if isinstance(element, LTTextContainer):
                        # For each text container (paragraph or block)
                        block_text = []
                        block_bbox = [float('inf'), float('inf'), float('-inf'), float('-inf')] # x0, y0, x1, y1

                        for text_line in element:
                            self.logger.debug(f"text_line: {text_line}")

                            if isinstance(text_line, LTTextContainer): # LTTextLine is also a LTTextContainer
                                last_char_bbox = None
                                for character in text_line:
                                    if isinstance(character, LTChar):
                                        original_char = character.get_text()
                                        fixed_char = original_char
                                        
                                        font_name_part = character.fontname.split('+')[-1] if character.fontname else ''
                                        if font_name_part in CUSTOM_STATIC_DECODE:
                                            if original_char in CUSTOM_STATIC_DECODE[font_name_part]:
                                                fixed_char = CUSTOM_STATIC_DECODE[font_name_part][original_char]

                                        # 修正された文字を使用
                                        block_text.append(fixed_char)
                                        
                                        # Update bounding box for the entire block
                                        block_bbox[0] = min(block_bbox[0], character.bbox[0])
                                        block_bbox[1] = min(block_bbox[1], character.bbox[1])
                                        block_bbox[2] = max(block_bbox[2], character.bbox[2])
                                        block_bbox[3] = max(block_bbox[3], character.bbox[3])

                                        last_char_bbox = character.bbox # 最後の文字のbboxを更新するのだ
                                        
                                        if character.fontname:
                                            all_font_names.add(character.fontname)

                                        self.logger.debug(f"LTChar text: {character.get_text()},\tfortname: {character.fontname},\tsize:{character.size}")
                                    else: # LTAnnoなどのオブジェクトの場合
                                        char_text = character.get_text()
                                        if char_text.isspace() and last_char_bbox:
                                            # 直前の文字のbboxを考慮してスペースのbboxを計算するのだ
                                            # スペースの幅は、直前の文字のフォントサイズから推測するのだ
                                            # ここでは簡略化のため、直前の文字の高さと同じ幅を仮定するのだ
                                            space_width = last_char_bbox[3] - last_char_bbox[1] if last_char_bbox[3] - last_char_bbox[1] > 0 else 5 # 最小幅を5とするのだ
                                            space_bbox = (
                                                last_char_bbox[2], # 直前の文字の右端から開始
                                                last_char_bbox[1],
                                                last_char_bbox[2] + space_width, # スペースの幅を加算
                                                last_char_bbox[3]
                                            )
                                            block_text.append(char_text)
                                            
                                            # Update bounding box for the entire block
                                            block_bbox[0] = min(block_bbox[0], space_bbox[0])
                                            block_bbox[1] = min(block_bbox[1], space_bbox[1])
                                            block_bbox[2] = max(block_bbox[2], space_bbox[2])
                                            block_bbox[3] = max(block_bbox[3], space_bbox[3])

                                            # スペースのbboxもlast_char_bboxとして更新するのだ
                                            last_char_bbox = space_bbox
                                        self.logger.debug(f"not LTChar text: {char_text}")
                                        # それ以外のLTAnnoは無視するのだ
                        
                        if block_text:
                            # Determine font_info for the block (using the first character's info as representative)
                            first_char_info = None
                            for text_line in element:
                                if isinstance(text_line, LTTextContainer):
                                    for character in text_line:
                                        if isinstance(character, LTChar):
                                            first_char_info = {
                                                "font_name": character.fontname,
                                                "font_size": character.size,
                                                "is_bold": ("Bold" in character.fontname),
                                                "is_italic": ("Italic" in character.fontname)
                                            }
                                            break
                                    if first_char_info:
                                        break
                            
                            font_info = FontInfo(
                                name=first_char_info["font_name"] if first_char_info else "Unknown",
                                size=first_char_info["font_size"] if first_char_info else 0.0,
                                is_bold=first_char_info["is_bold"] if first_char_info else False,
                                is_italic=first_char_info["is_italic"] if first_char_info else False
                            )

                            text_block = TextBlock(
                                text="".join(block_text),
                                bbox=BBox(x0=block_bbox[0], y0=block_bbox[1], x1=block_bbox[2], y1=block_bbox[3]),
                                font_info=font_info,
                                page_number=page_layout.pageid,
                            )
                            page_text_blocks.append(text_block)
                
                if page_text_blocks:
                    extracted_data.append(page_text_blocks)

            self.logger.info(f"Successfully extracted text from {len(extracted_data)} pages.")
            self.logger.info(f"All unique font names found: {sorted(list(all_font_names))}")
            self.logger.debug("Method end: extract_text_with_positions (success)")
            return extracted_data
        except Exception as e:
            self.logger.error(f"Failed to extract text from {pdf_path}: {e}")
            self.logger.debug("Method end: extract_text_with_positions (failed)")
            raise

    def crop_textblock(self, pdf_path: str, page_number: int) -> List[Any]:
        raise NotImplementedError("extract_textblock is not implemented for PdfminerAnalyzer yet.")
