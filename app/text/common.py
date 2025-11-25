# Copyright 2025 npz35
#
# See the NOTICE file for this project for license details.
# This file may not be used except in accordance with the NOTICE.

import logging
from abc import ABC, abstractmethod
import math
import re # Added for sentence ending detection
from typing import Optional

from app.config import Config
from app.data_model import BBox, CharBlock, ColumnIndex, ColumnType, TextArea, TextBlock, TextPermutation, WordBlock

logger: logging.Logger = logging.getLogger(__name__)

class PdfAnalyzer(ABC):
    '''
    PDF解析の抽象基底クラスなのだ。
    異なるPDF解析ライブラリ（pdfplumber, pypdfなど）に対応するための共通インターフェースを定義するのだ。
    '''

    MERGE_AREA_Y_TOLERANCE = 8.0

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)

        self.all_page_sizes: list[tuple[float, float]] = []
        self.all_page_char_blocks: list[list[CharBlock]] = []
        self.all_page_word_blocks: list[list[WordBlock]] = []
        self.all_page_text_blocks: list[list[TextBlock]] = []
        self.all_page_text_areas: list[list[TextArea]] = []
        self.all_page_text_permutations: list[list[TextPermutation]] = []
        self.all_page_rect_blocks: list[list[BBox]] = []
        self.all_page_image_blocks: list[list[BBox]] = []

    @abstractmethod
    def extract_pazesizes(self, pdf_path: str) -> list[tuple[float, float]]:
        pass

    # @abstractmethod
    # def extract_charblocks(self, pdf_path: str) -> list[list[CharBlock]]:
    #     pass

    @abstractmethod
    def extract_rect_blocks(self, pdf_path: str) -> list[list[BBox]]:
        pass

    @abstractmethod
    def extract_image_blocks(self, pdf_path: str) -> list[list[BBox]]:
        pass

    def _are_blocks_on_same_line(self, bbox1: BBox, bbox2: BBox, y_tolerance: float = 2.0) -> bool:
        '''
        二つのBBoxが同じ行にあるかを判定するのだ。
        y軸方向の重なりを考慮するのだ。
        '''
        # Check for vertical overlap
        vertical_overlap = max(0, min(bbox1.y1, bbox2.y1) - max(bbox1.y0, bbox2.y0))
        
        # If there's significant vertical overlap, consider them on the same line
        # The threshold can be adjusted based on typical line spacing and font sizes
        h1 = bbox1.height()
        h2 = bbox2.height()
        min_height = min(h1, h2)
        return vertical_overlap > (min_height - y_tolerance)

    def _get_column_index_from_area(self, area: TextArea) -> ColumnIndex:
        """
        Get column index from TextArea's first block.
        
        Args:
            area: TextArea to extract column index from
            
        Returns:
            ColumnIndex of the first block, or UNKNOWN if no blocks
        """
        if area.blocks:
            return area.blocks[0].column_index
        return ColumnIndex.UNKNOWN

    def _protect_special_patterns(self, text: str) -> tuple[str, dict[str, str]]:
        '''
        Protect special patterns (URLs, emails, etc.) from being split by replacing them with placeholders.
        Returns the protected text and a mapping of placeholders to original values.
        '''
        placeholders = {}
        protected_text = text
        
        # Define patterns to protect
        patterns = [
            # URLs (http://, https://, ftp://, etc.)
            (r'(?:https?|ftp)://[^\s]+', '__URL_{}_'),
            # Email addresses
            (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '__EMAIL_{}_'),
            # File paths with extensions (e.g., example.com, file.pdf)
            (r'\b\w+\.\w+(?:/\S*)?', '__PATH_{}_'),
        ]
        
        for pattern, placeholder_template in patterns:
            matches = list(re.finditer(pattern, protected_text))
            # Process matches in reverse order to preserve indices
            for i, match in enumerate(reversed(matches)):
                placeholder = placeholder_template.format(len(placeholders))
                placeholders[placeholder] = match.group(0)
                protected_text = protected_text[:match.start()] + placeholder + protected_text[match.end():]
        
        return protected_text, placeholders

    def _restore_special_patterns(self, text: str, placeholders: dict[str, str]) -> str:
        '''
        Restore special patterns by replacing placeholders with their original values.
        '''
        restored_text = text
        for placeholder, original in placeholders.items():
            restored_text = restored_text.replace(placeholder, original)
        return restored_text

    def _is_sentence_end(self, text: str) -> bool:
        '''
        Determines if the given text ends with a sentence-ending punctuation,
        while considering common abbreviations and numerical patterns.
        '''
        text = text.strip()
        if not text:
            return False

        # Protect special patterns (URLs, emails, etc.)
        text_protected, placeholders = self._protect_special_patterns(text)
        
        # Temporarily replace 'ε' to avoid interference with sentence splitting logic
        # This is a heuristic to handle specific symbols that might be part of formulas
        # and should not be treated as sentence endings.
        text_processed = text_protected.replace('ε', '__EPSILON__')

        # Check for common sentence endings
        if text_processed.endswith(('.', '?', '!')):
            # Simple check for abbreviations that often end with a period
            # This list can be expanded
            abbreviations = ['dr.', 'mr.', 'mrs.', 'ms.', 'prof.', 'rev.', 'fr.', 'sr.', 'jr.', 'etc.', 'e.g.', 'i.e.', 'fig.', 'figs.', 'vs.', 'co.', 'corp.', 'inc.', 'ltd.', 'univ.', 'dept.', 'vol.', 'chap.', 'sec.', 'anon.', 'approx.', 'cf.', 'cont.', 'diag.', 'esp.', 'ex.', 'ext.', 'ibid.', 'id.', 'loc. cit.', 'op. cit.', 'p.', 'pp.', 'para.', 'q.v.', 's.v.', 'trans.', 'viz.']
            
            # Check if the text ends with an abbreviation followed by a period
            # This is a simplified check and might need more sophisticated NLP for full accuracy
            for abbr in abbreviations:
                if text_processed.lower().endswith(abbr):
                    # If the abbreviation is at the very end, it might not be a sentence end
                    # unless it's followed by a space and then a capital letter (which we can't easily check here)
                    # For now, assume abbreviations followed by a period are NOT sentence ends.
                    return False
            
            # Check for numbers followed by a period (e.g., "Figure 1.", "Section 2.3.")
            # However, if the text contains multiple words (more than 3), it's likely a complete sentence
            # Example: "This is Page 1." should be considered a sentence end
            if re.search(r'\d\.$', text_processed):
                # Count words in the text
                word_count = len(text_processed.split())
                # If there are 3 or fewer words, it's likely a reference (e.g., "Figure 1.")
                # If there are more than 3 words, it's likely a complete sentence
                if word_count <= 3:
                    return False

            return True
        return False

    def _split_into_sentences(self, text: str) -> list[str]:
        '''
        Splits the given text into sentences, considering abbreviations and numerical patterns.
        '''
        text = text.strip()
        if not text:
            return []

        # Protect special patterns (URLs, emails, etc.)
        text_protected, placeholders = self._protect_special_patterns(text)
        
        # Temporarily replace 'ε' to avoid interference with sentence splitting logic
        # This is a heuristic to handle specific symbols that might be part of formulas
        # and should not be treated as sentence endings.
        text_with_placeholder = text_protected.replace('ε', '__EPSILON__')

        abbreviations = ['dr.', 'mr.', 'mrs.', 'ms.', 'prof.', 'rev.', 'fr.', 'sr.', 'jr.', 'etc.', 'e.g.', 'i.e.', 'fig.', 'figs.', 'vs.', 'co.', 'corp.', 'inc.', 'ltd.', 'univ.', 'dept.', 'vol.', 'chap.', 'sec.', 'anon.', 'approx.', 'cf.', 'cont.', 'diag.', 'esp.', 'ex.', 'ext.', 'ibid.', 'id.', 'loc. cit.', 'op. cit.', 'p.', 'pp.', 'para.', 'q.v.', 's.v.', 'trans.', 'viz.']
        
        sentences = []
        last_split_idx = 0
        
        # Find all potential sentence delimiters
        for match in re.finditer(r'[\.?!]', text_with_placeholder):
            end_idx = match.end()
            delimiter = match.group(0)
            
            # Check if it's a true sentence end
            is_sentence_end = True
            
            # Extract the text segment ending just before the delimiter
            pre_delimiter_segment = text_with_placeholder[last_split_idx:end_idx].strip().lower()
            for abbr in abbreviations:
                if pre_delimiter_segment.endswith(abbr):
                    is_sentence_end = False
                    break
            
            # Check for numbers followed by a period
            # However, if the segment contains multiple words (more than 3), it's likely a complete sentence
            if is_sentence_end and delimiter == '.' and re.search(r'\d\.$', pre_delimiter_segment):
                # Count words in the segment
                word_count = len(pre_delimiter_segment.split())
                # If there are 3 or fewer words, it's likely a reference (e.g., "Figure 1.")
                if word_count <= 3:
                    is_sentence_end = False
            
            if is_sentence_end:
                sentence = text_with_placeholder[last_split_idx:end_idx].strip()
                if sentence:
                    # Restore special patterns and 'ε'
                    sentence = sentence.replace('__EPSILON__', 'ε')
                    sentence = self._restore_special_patterns(sentence, placeholders)
                    sentences.append(sentence)
                last_split_idx = end_idx
                
                # Skip any trailing whitespace after the delimiter
                while last_split_idx < len(text_with_placeholder) and text_with_placeholder[last_split_idx].isspace():
                    last_split_idx += 1

        # Add any remaining text as a sentence
        remaining_text = text_with_placeholder[last_split_idx:].strip()
        if remaining_text:
            # Restore special patterns and 'ε'
            remaining_text = remaining_text.replace('__EPSILON__', 'ε')
            remaining_text = self._restore_special_patterns(remaining_text, placeholders)
            sentences.append(remaining_text)
            
        return sentences

    def extract_wordblocks(self, pdf_path: str) -> list[list[WordBlock]]:
        self.logger.debug(f"Function start: extract_wordblocks(pdf_path='{pdf_path}')")

        if self.all_page_word_blocks:
            return self.all_page_word_blocks

        self.all_page_char_blocks: list[list[CharBlock]] = self.extract_charblocks(pdf_path)

        for page_char_blocks in self.all_page_char_blocks:
            current_page_word_blocks: list[WordBlock] = []
            current_word_chars: list[CharBlock] = []
            
            if not page_char_blocks:
                self.logger.warning('page_char_blocks is empty')
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
                    
                    word_text = ''.join([c.char for c in current_word_chars])
                    
                    current_page_word_blocks.append(WordBlock(
                        word=word_text,
                        bbox=word_bbox,
                        font_info=first_char.font_info,
                        page_number=first_char.page_number,
                        column_index=first_char.column_index
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
                
                word_text = ''.join([c.char for c in current_word_chars])
                
                current_page_word_blocks.append(WordBlock(
                    word=word_text,
                    bbox=word_bbox,
                    font_info=first_char.font_info,
                    page_number=first_char.page_number,
                    column_index=first_char.column_index
                ))
            
            # self.logger.debug(f'current_page_word_blocks: {current_page_word_blocks}')
            self.all_page_word_blocks.append(current_page_word_blocks)

        self.logger.debug(f'Function end: extract_wordblocks. Extracted {len(self.all_page_word_blocks)} pages with word blocks.')
        return self.all_page_word_blocks
    
    def extract_textblocks(self, pdf_path: str) -> list[list[TextBlock]]:
        self.logger.debug(f"Function start: extract_textblocks(pdf_path='{pdf_path}')")

        if self.all_page_text_blocks:
            return self.all_page_text_blocks

        self.all_page_word_blocks: list[list[WordBlock]] = self.extract_wordblocks(pdf_path)

        for page_word_blocks in self.all_page_word_blocks:
            current_page_text_blocks: list[TextBlock] = []
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
                        column_index=word_block.column_index
                    )
                    current_page_text_blocks.append(current_text_block)
                else:
                    # If same font info and on the same line, append to existing TextBlock
                    current_text_block.text += ' ' + word_block.word
                    current_text_block.bbox.x1 = word_block.bbox.x1
                    current_text_block.bbox.y0 = min(current_text_block.bbox.y0, word_block.bbox.y0)
                    current_text_block.bbox.y1 = max(current_text_block.bbox.y1, word_block.bbox.y1)
            
            if current_page_text_blocks:
                # self.logger.debug(f'current_page_text_blocks: {current_page_text_blocks}')
                self.all_page_text_blocks.append(current_page_text_blocks)

        self.logger.debug(f'Function end: extract_textblocks. Extracted {len(self.all_page_text_blocks)} pages with text blocks.')
        return self.all_page_text_blocks
    
    def extract_textareas(self, pdf_path: str) -> list[list[TextArea]]:
        self.logger.debug(f"Function start: extract_textareas(pdf_path='{pdf_path}')")

        if self.all_page_text_areas:
            return self.all_page_text_areas

        self.all_page_text_blocks: list[list[TextBlock]] = self.extract_textblocks(pdf_path)

        merge_page_text_areas: list[TextArea]
        page_text_areas: list[TextArea]
        current_text_area: TextArea
        for page_idx, page_text_blocks in enumerate(self.all_page_text_blocks):
            if Config.MAX_PDF_PAGES <= page_idx:
                break

            merge_page_text_areas = []
            page_text_areas = []

            # Horizontal merge
            self.logger.debug(f'Page {page_idx + 1}: Horizontal merge text blocks')
            # y0 (下端) を基準に降順、x0 (左端) を基準に昇順でソートするのだ
            sorted_page_text_blocks: list[TextBlock] = sorted(page_text_blocks, key=lambda block: (-block.bbox.y0, block.bbox.x0))
            current_text_area: Optional[TextArea] = None

            for text_block in sorted_page_text_blocks:
                if current_text_area is None:
                    current_text_area = TextArea(blocks=[text_block], bbox=text_block.bbox, page_number=text_block.page_number)
                    self.logger.warning(f'Page {page_idx + 1}: first {current_text_area.bbox.y0:.2f} < {text_block.bbox.y1:.2f} and {text_block.bbox.y0:.2f} < {current_text_area.bbox.y1:.2f}')
                else:
                    # self.logger.warning(f'Page {page_idx + 1}: {current_text_area.bbox.x0:.2f} < {text_block.bbox.x1:.2f} and {text_block.bbox.x0:.2f} < {current_text_area.bbox.x1:.2f}')
                    # self.logger.warning(f'Page {page_idx + 1}: {current_text_area.bbox.y0:.2f} < {text_block.bbox.y1:.2f} and {text_block.bbox.y0:.2f} < {current_text_area.bbox.y1:.2f}')

                    overlap_horizontal = current_text_area.bbox.x0 < text_block.bbox.x1 and text_block.bbox.x0 < current_text_area.bbox.x1
                    overlap_vertical = current_text_area.bbox.y0 < text_block.bbox.y1 and text_block.bbox.y0 < current_text_area.bbox.y1
                    nearby_vertical = abs(current_text_area.bbox.y0 - text_block.bbox.y1) < self.MERGE_AREA_Y_TOLERANCE or abs(current_text_area.bbox.y1 - text_block.bbox.y0) < self.MERGE_AREA_Y_TOLERANCE
                    overlap = overlap_horizontal and overlap_vertical
                    nearby_area = overlap or (overlap_horizontal and nearby_vertical)

                    # self.logger.debug(f'Page {page_idx + 1}: current_text_area text : {current_text_area.text()}')
                    # self.logger.debug(f'Page {page_idx + 1}: text_block text        : {text_block.text}')
                    # self.logger.debug(f'Page {page_idx + 1}: overlap_horizontal     : {overlap_horizontal}')
                    # self.logger.debug(f'Page {page_idx + 1}: overlap_vertical       : {overlap_vertical}')
                    # self.logger.debug(f'Page {page_idx + 1}: nearby_vertical        : {nearby_vertical}')
                    # self.logger.debug(f'Page {page_idx + 1}: nearby_area            : {nearby_area}')

                    if nearby_area:
                        last_block_in_area = current_text_area.blocks[-1]
                        horizontal_gap = text_block.bbox.x0 - last_block_in_area.bbox.x1
                        
                        avg_char_width = 0
                        font_size = last_block_in_area.font_info.size if last_block_in_area.font_info else 10.0
                        if last_block_in_area.text and len(last_block_in_area.text) > 0:
                            avg_char_width = last_block_in_area.bbox.width() / len(last_block_in_area.text)
                        else:
                            avg_char_width = font_size * 0.6 # Heuristic for average char width

                        # If the gap is larger than 3 spaces, don't merge
                        should_merge_by_gap = horizontal_gap <= avg_char_width * 3

                        if should_merge_by_gap:
                            current_text_area.append(text_block)
                        else:
                            # Don't merge due to large gap, finalize current area and start a new one
                            current_text_area.blocks = sorted(current_text_area.blocks, key=lambda block: (-block.bbox.y1, block.bbox.x0))
                            merge_page_text_areas.append(current_text_area)
                            current_text_area = TextArea(blocks=[text_block], bbox=text_block.bbox, page_number=text_block.page_number)
                    else:
                        # Not nearby, finalize current area and start a new one
                        current_text_area.blocks = sorted(current_text_area.blocks, key=lambda block: (-block.bbox.y1, block.bbox.x0))
                        merge_page_text_areas.append(current_text_area)
                        current_text_area = TextArea(blocks=[text_block], bbox=text_block.bbox, page_number=text_block.page_number)

            if current_text_area is not None:
                current_text_area.blocks = sorted(current_text_area.blocks, key=lambda block: (-block.bbox.y1, block.bbox.x0))
                merge_page_text_areas.append(current_text_area)

            # Vertical merge
            self.logger.debug(f'Page {page_idx + 1}: Vertical merge text areas')
            # x0 (左端) を基準に昇順、y0 (下端) を基準に降順でソートするのだ
            sorted_page_text_areas: list[TextArea] = sorted(merge_page_text_areas, key=lambda area: (area.bbox.x0, -area.bbox.y0))
            current_text_area: Optional[TextArea] = None
            for text_area in sorted_page_text_areas:
                if current_text_area is None:
                    current_text_area = TextArea(blocks=text_area.blocks, bbox=text_area.bbox, page_number=text_area.page_number)
                    continue

                overlap_horizontal = current_text_area.bbox.x0 < text_area.bbox.x1 and text_area.bbox.x0 < current_text_area.bbox.x1
                overlap_vertical = current_text_area.bbox.y0 < text_area.bbox.y1 and text_area.bbox.y0 < current_text_area.bbox.y1
                nearby_vertical = abs(current_text_area.bbox.y0 - text_area.bbox.y1) < 2.0 or abs(current_text_area.bbox.y1 - text_area.bbox.y0) < 2.0
                nearby_area = (overlap_horizontal and overlap_vertical) or (overlap_horizontal and nearby_vertical)

                # self.logger.debug(f'Page {page_idx + 1}: current_text_area text : {current_text_area.text()}')
                # self.logger.debug(f'Page {page_idx + 1}: text_block text        : {text_block.text}')
                # self.logger.debug(f'Page {page_idx + 1}: overlap_horizontal     : {overlap_horizontal}')
                # self.logger.debug(f'Page {page_idx + 1}: overlap_vertical       : {overlap_vertical}')
                # self.logger.debug(f'Page {page_idx + 1}: nearby_vertical        : {nearby_vertical}')
                # self.logger.debug(f'Page {page_idx + 1}: nearby_area            : {nearby_area}')

                if not nearby_area:
                    current_text_area.blocks = sorted(current_text_area.blocks, key=lambda block: (block.bbox.x0, -block.bbox.y1))
                    page_text_areas.append(current_text_area)
                    current_text_area = TextArea(blocks=[], bbox=BBox(x0=math.inf, x1=-math.inf, y0=math.inf, y1=-math.inf))

                for block in text_area.blocks:
                    current_text_area.append(block)

            if current_text_area is not None:
                current_text_area.blocks = sorted(current_text_area.blocks, key=lambda block: (block.bbox.x0, -block.bbox.y1))
                page_text_areas.append(current_text_area)

            if page_text_areas:
                self.logger.debug(f'Page {page_idx + 1}: page_text_areas[:10]: {page_text_areas[:10]}')
                self.logger.debug(f'Page {page_idx + 1}: page_text_areas size: {len(page_text_areas)}')
                self.all_page_text_areas.append(page_text_areas)

        self.logger.debug(f'Function end: extract_textareas. Extracted {len(self.all_page_text_areas)} pages with text areas.')
        return self.all_page_text_areas
    
    def extract_textpermutations(self, pdf_path: str) -> list[list[TextPermutation]]:
        self.logger.debug(f"Function start: extract_textpermutations(pdf_path='{pdf_path}')")

        if self.all_page_text_permutations:
            return self.all_page_text_permutations
        
        self.all_page_text_areas: list[list[TextArea]] = self.extract_textareas(pdf_path)

        # Flatten all_page_text_areas into a single list of TextAreas
        flat_text_areas: list[TextArea] = []
        for page_text_areas in self.all_page_text_areas:
            flat_text_areas.extend(page_text_areas)

        # Split TextAreas into sentence-level TextPermutation candidates
        sentence_permutations_candidates: list[TextPermutation] = []
        for area in flat_text_areas:
            sentences = self._split_into_sentences(area.text())
            for sentence_text in sentences:
                if sentence_text: # Skip empty sentences
                    sentence_permutations_candidates.append(
                        TextPermutation(
                            area=area, # Reference the original TextArea
                            text=sentence_text,
                            page_number=area.page_number,
                            font_info=area.blocks[0].font_info if area.blocks else None # Set font_info from the first block of the first TextArea
                        )
                    )

        # Sort sentence-level TextPermutation candidates in Z-shaped reading order
        # Prioritize by page number, then by y-coordinate (top to bottom), then by x-coordinate (left to right)
        sorted_sentence_permutations: list[TextPermutation] = sorted(
            sentence_permutations_candidates,
            key=lambda perm: (
                perm.page_number,                                    # 1. ページ番号
                self._get_column_index_from_area(perm.area).value,  # 2. 列インデックス（LEFT=0, RIGHT=1, UNKNOWN=-1）
                -perm.area.bbox.y0,                                  # 3. 上から下（y座標降順、下端を基準にするのだ）
                perm.area.bbox.x0                                    # 4. 左から右（x座標昇順）
            )
        )

        current_text_permutation: Optional[TextPermutation] = None
        all_text_permutations_flat: list[TextPermutation] = []

        for perm_candidate in sorted_sentence_permutations:
            if current_text_permutation is None:
                # Start a new TextPermutation with the current sentence candidate
                current_text_permutation = perm_candidate
            else:
                # Check if the current sentence candidate can be merged with the previous TextPermutation
                is_same_page = current_text_permutation.page_number == perm_candidate.page_number

                # Get column indices for both permutations
                current_column = self._get_column_index_from_area(current_text_permutation.area)
                candidate_column = self._get_column_index_from_area(perm_candidate.area)
                is_same_column = current_column == candidate_column

                vertical_distance = abs(current_text_permutation.area.bbox.y0 - perm_candidate.area.bbox.y1)
                horizontal_overlap = max(0,
                    min(current_text_permutation.area.bbox.x1, perm_candidate.area.bbox.x1) -
                    max(current_text_permutation.area.bbox.x0, perm_candidate.area.bbox.x0)
                )

                vertical_tolerance = 10.0
                min_horizontal_overlap = 5.0

                # Check if the previous permutation ends a sentence
                ends_sentence = self._is_sentence_end(current_text_permutation.text)

                # 結合条件を厳しくするのだ
                # 1. 同じページであること
                # 2. 同じ列であること
                # 3. 垂直方向の距離が許容範囲内であること
                # 4. 水平方向の重なりが許容範囲内であること
                # 5. 前のTextPermutationが文末で終わっていないこと（これが重要！）
                # 6. 次のTextPermutationの先頭が大文字で始まっていないこと（新しい文の始まりではないこと）
                
                # 次のPermutationの先頭文字を取得するのだ
                next_perm_starts_with_capital = False
                if perm_candidate.text and perm_candidate.text[0].isupper():
                    next_perm_starts_with_capital = True

                if (is_same_page and
                    is_same_column and
                    vertical_distance < vertical_tolerance and
                    horizontal_overlap > min_horizontal_overlap and
                    not ends_sentence and
                    not next_perm_starts_with_capital): # 新規追加：次のPermutationが新しい文の始まりではないことを確認するのだ
                    
                    # Merge the sentence candidate into the current TextPermutation
                    # Merge the two TextAreas into a new one
                    merged_blocks = current_text_permutation.area.blocks + perm_candidate.area.blocks
                    merged_bbox = BBox(
                        x0=min(current_text_permutation.area.bbox.x0, perm_candidate.area.bbox.x0),
                        y0=min(current_text_permutation.area.bbox.y0, perm_candidate.area.bbox.y0),
                        x1=max(current_text_permutation.area.bbox.x1, perm_candidate.area.bbox.x1),
                        y1=max(current_text_permutation.area.bbox.y1, perm_candidate.area.bbox.y1)
                    )
                    merged_area = TextArea(blocks=merged_blocks, bbox=merged_bbox, page_number=current_text_permutation.page_number)
                    current_text_permutation.area = merged_area
                    current_text_permutation.text += ' ' + perm_candidate.text
                else:
                    # Current sentence candidate cannot be merged, finalize the current TextPermutation and start a new one
                    all_text_permutations_flat.append(current_text_permutation)
                    current_text_permutation = perm_candidate
        
        # Add the last TextPermutation if it exists
        if current_text_permutation is not None:
            all_text_permutations_flat.append(current_text_permutation)

        # Group TextPermutations by page number
        self.all_page_text_permutations = []
        if all_text_permutations_flat:
            current_page_number = all_text_permutations_flat[0].page_number
            current_page_permutations: list[TextPermutation] = []
            for perm in all_text_permutations_flat:
                if perm.page_number == current_page_number:
                    current_page_permutations.append(perm)
                else:
                    self.all_page_text_permutations.append(current_page_permutations)
                    current_page_number = perm.page_number
                    current_page_permutations = [perm]
            self.all_page_text_permutations.append(current_page_permutations)

        for page_idx, page_text_permutations in enumerate(self.all_page_text_permutations):
            if page_text_permutations:
                self.logger.debug(f'Page {page_idx + 1}: page_text_permutations[:10]: {page_text_permutations[:10]}')
                self.logger.debug(f'Page {page_idx + 1}: page_text_permutations size: {len(page_text_permutations)}')

        self.logger.debug(f'Function end: extract_textpermutations. Extracted {len(self.all_page_text_permutations)} pages with text permutations.')
        return self.all_page_text_permutations

    def crop_textblock(self, pdf_path: str, current_page_number: int, line: ColumnType) -> list[TextBlock]:
        '''
        PDFページから単語とそのbbox情報を抽出するのだ。
        '''
        self.logger.debug(f"Function start: crop_textblock(pdf_path='{pdf_path}', current_page_number={current_page_number}, line={line})")

        all_page_text_blocks = self.extract_textblocks(pdf_path)
        page_text_blocks = all_page_text_blocks[current_page_number - 1]

        crop_page_text_blocks = page_text_blocks
        # crop_page_text_blocks = [block for block in crop_page_text_blocks if line.x0 <= block.bbox.x0]
        crop_page_text_blocks = [block for block in crop_page_text_blocks if line.bbox.y0 <= block.bbox.y0]
        # crop_page_text_blocks = [block for block in crop_page_text_blocks if block.bbox.x1 <= line.x1]
        crop_page_text_blocks = [block for block in crop_page_text_blocks if block.bbox.y1 <= line.bbox.y1]

        self.logger.debug(f'Page {current_page_number}: page_text_blocks size     : {len(page_text_blocks)}')
        self.logger.debug(f'Page {current_page_number}: line                      : {line}')
        self.logger.debug(f'Page {current_page_number}: crop_page_text_blocks size: {len(crop_page_text_blocks)}')

        self.logger.debug(f"Function end: crop_textblock(pdf_path='{pdf_path}', current_page_number={current_page_number}, line={line})")
        return crop_page_text_blocks
