# Copyright 2025 npz35
#
# See the NOTICE file for this project for license details.
# This file may not be used except in accordance with the NOTICE.

import logging
from typing import List, Dict, Any
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextContainer, LTChar, LAParams
from app.config import Config

CUSTOM_STATIC_DECODE = {
    # XLDELO+CMMI10
    'CMMI10': {
        '"': 'ε',
    }
}

class PdfTextManager:
    """PDF Text Management Class"""

    def __init__(self):
        self.logger: logging.Logger = logging.getLogger(__name__)
        self.logger.debug("Function start: PdfTextManager.__init__()")
        """
        Initialization
        """
        self.logger.debug("Function end: PdfTextManager.__init__ (success)")

    def extract_text_with_positions(self, pdf_path: str) -> List[Dict[str, Any]]:
        self.logger.debug(f"Function start: extract_text_with_positions(pdf_path='{pdf_path}')")
        """
        Extracts text and its position from a PDF using pdfminer.six.

        Args:
            pdf_path: Path to the PDF file.

        Returns:
            A list of dictionaries, each containing text and its bounding box.
        """

        laparams = LAParams(
            line_overlap=0.5,
            char_margin=1.0,
            word_margin=0.1,
            line_margin=0.5,
            boxes_flow=0.5,
            detect_vertical=False,
            all_texts=True
        )

        self.logger.info(f"Extracting text with positions from {pdf_path}")
        extracted_data = []
        try:
            for page_layout in extract_pages(pdf_path, laparams=laparams):
                if page_layout.pageid > Config.MAX_PDF_PAGES:
                    self.logger.warning(f"Reached maximum page limit of {Config.MAX_PDF_PAGES}. Stopping further page processing.")
                    break
                for element in page_layout:
                    if isinstance(element, LTTextContainer):
                        # For each text container (paragraph or block)
                        text_content = ""
                        min_x0, min_y0, max_x1, max_y1 = float('inf'), float('inf'), float('-inf'), float('-inf')
                        font_names = []
                        font_sizes = []
                        is_bold_flags = []
                        is_italic_flags = []

                        for text_line in element:
                            self.logger.debug(f"text_line: {text_line}")

                            if isinstance(text_line, LTTextContainer): # LTTextLine is also a LTTextContainer
                                min_x0 = min(min_x0, text_line.x0)
                                min_y0 = min(min_y0, text_line.y0)
                                max_x1 = max(max_x1, text_line.x1)
                                max_y1 = max(max_y1, text_line.y1)

                                for character in text_line:
                                    if isinstance(character, LTChar):
                                        original_char = character.get_text()
                                        fixed_char = original_char
                                        
                                        font_name_part = character.fontname.split('+')[-1] if character.fontname else ''
                                        if font_name_part in CUSTOM_STATIC_DECODE:
                                            if original_char in CUSTOM_STATIC_DECODE[font_name_part]:
                                                fixed_char = CUSTOM_STATIC_DECODE[font_name_part][original_char]

                                        # 修正された文字を使用
                                        text_content += fixed_char
                                        
                                        font_names.append(character.fontname)
                                        font_sizes.append(character.size)
                                        is_bold_flags.append("Bold" in character.fontname)
                                        is_italic_flags.append("Italic" in character.fontname)

                                        self.logger.debug(f"LTChar text: {character.get_text()},\tfortname: {character.fontname},\tsize:{character.size}")
                                    else:
                                        text_content += character.get_text()
                        
                        if text_content.strip(): # Only add if there's actual text
                            # Use the overall bbox of the text container
                            bbox = (min_x0, min_y0, max_x1, max_y1)

                            self.logger.debug(f"Extract text      : {text_content.strip()}")
                            self.logger.debug(f"Extract font_names: {font_names}")
                            
                            # Determine representative font info
                            font_name = max(set(font_names), key=font_names.count) if font_names else "Helvetica"
                            font_size = sum(font_sizes) / len(font_sizes) if font_sizes else 12.0
                            is_bold = any(is_bold_flags)
                            is_italic = any(is_italic_flags)

                            text_data = {
                                "text": text_content.strip(),
                                "bbox": bbox,
                                "page_number": page_layout.pageid,
                                "font_name": font_name,
                                "font_size": font_size,
                                "is_bold": is_bold,
                                "is_italic": is_italic
                            }
                            self.logger.debug(f"Appending extracted data: {text_data}")
                            extracted_data.append(text_data)
            self.logger.info(f"Successfully extracted text from {len(extracted_data)} elements.")
            self.logger.debug("Function end: extract_text_with_positions (success)")
            return extracted_data
        except Exception as e:
            self.logger.error(f"Failed to extract text from {pdf_path}: {e}")
            self.logger.debug("Function end: extract_text_with_positions (failed)")
            raise

