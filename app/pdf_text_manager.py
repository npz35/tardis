# Copyright 2025 npz35
#
# See the NOTICE file for this project for license details.
# This file may not be used except in accordance with the NOTICE.

import logging
import difflib
from typing import List, Dict, Any
from app.config import Config
from app.text.pdfminer import PdfminerAnalyzer
from app.text.unstructured import UnstructuredAnalyzer
from app.text.pypdf import PyPdfAnalyzer
from app.pdf_text_extractor import PdfTextExtractor
from app.data_model import TextBlock, BBox, FontInfo # TextBlock, BBox, FontInfoを追加するのだ

class PdfTextManager:
    """PDF Text Management Class"""

    def __init__(self):
        self.logger: logging.Logger = logging.getLogger(__name__)
        self.logger.debug("Function start: PdfTextManager.__init__()")
        """
        Initialization
        """
        self.pdf_text_extractor = PdfTextExtractor()
        self.pdfminer_analyzer = PdfminerAnalyzer()
        self.unstructured_analyzer = UnstructuredAnalyzer()
        self.pypdf_analyzer = PyPdfAnalyzer()
        self.logger.debug("Function end: PdfTextManager.__init__ (success)")

    def _convert_dict_list_to_text_block_list(self, dict_list: List[Dict[str, Any]]) -> List[TextBlock]:
        """
        Converts a list of dictionaries (from unstructured or pypdf) into a list of TextBlock instances.
        """
        return [TextBlock(
            text=item.get('text', ''),
            bbox=BBox(x0=item['bbox'][0], y0=item['bbox'][1], x1=item['bbox'][2], y1=item['bbox'][3]),
            font_info=FontInfo(name="unknown", size=0.0, is_bold=False, is_italic=False),
            page_number=item.get('page_number', 0),
            column_index=-1 # デフォルト値なのだ
        ) for item in dict_list]

    def extract_textblocks(self, pdf_path: str) -> List[TextBlock]:
        self.logger.debug(f"Function start: extract_textblocks(pdf_path='{pdf_path}')")
        """
        Extracts text and its position from a PDF.
        The extraction method is determined by the configuration.

        Args:
            pdf_path: Path to the PDF file.

        Returns:
            A list of TextBlock instances.
        """
        self.logger.info(f"TEXT_EXTRACTION_METHOD: {Config.TEXT_EXTRACTION_METHOD}")
        
        if Config.TEXT_EXTRACTION_METHOD == "pdfminer":
            all_page_text_blocks: List[List[TextBlock]] = self.pdfminer_analyzer.extract_textblocks(pdf_path)
            return self.pdf_text_extractor.extract_text_blocks(pdf_path, char_data_from_specific_extractor=all_page_text_blocks)
        elif Config.TEXT_EXTRACTION_METHOD == "pdfplumber":
            return self.pdf_text_extractor.extract_text_blocks(pdf_path)
        elif Config.TEXT_EXTRACTION_METHOD == "unstructured":
            all_page_text_blocks: List[List[TextBlock]] = self.unstructured_analyzer.extract_textblocks(pdf_path)
            return self.pdf_text_extractor.extract_text_blocks(pdf_path, char_data_from_specific_extractor=all_page_text_blocks)
        elif Config.TEXT_EXTRACTION_METHOD == "pypdf":
            all_page_text_blocks: List[List[TextBlock]] = self.pypdf_analyzer.extract_textblocks(pdf_path)
            return self.pdf_text_extractor.extract_text_blocks(pdf_path, char_data_from_specific_extractor=all_page_text_blocks)
        elif Config.TEXT_EXTRACTION_METHOD == "hybrid_pdfminer_pypdf":
            pdfminer_all_page_text_blocks: List[List[TextBlock]] = self.pdfminer_analyzer.extract_textblocks(pdf_path)
            pypdf_all_page_text_blocks: List[List[TextBlock]] = self.pypdf_analyzer.extract_textblocks(pdf_path)
            
            pdfminer_text_blocks = self.pdf_text_extractor.extract_text_blocks(pdf_path, char_data_from_specific_extractor=pdfminer_all_page_text_blocks)
            pypdf_text_blocks = self.pdf_text_extractor.extract_text_blocks(pdf_path, char_data_from_specific_extractor=pypdf_all_page_text_blocks)
            return self._correct_text_with_pypdf(pdfminer_text_blocks, pypdf_text_blocks)
        else:
            self.logger.error(f"Unknown text extraction method: {Config.TEXT_EXTRACTION_METHOD}")
            raise ValueError(f"Unknown text extraction method: {Config.TEXT_EXTRACTION_METHOD}")

    def _correct_text_with_pypdf(self, pdfminer_data: List[TextBlock], pypdf_data: List[TextBlock]) -> List[TextBlock]: # 引数と戻り値の型ヒントを修正するのだ
        """
        Corrects text extracted by pdfminer with text from pypdf.
        """
        self.logger.debug("Function start: _correct_text_with_pypdf()")
        pypdf_texts_by_page = {item.page_number: item.text for item in pypdf_data} # 属性アクセスに修正するのだ
        
        # Group pdfminer data by page
        pdfminer_pages: Dict[int, List[TextBlock]] = {} # 型ヒントを修正するのだ
        for item in pdfminer_data:
            page_num = item.page_number # 属性アクセスに修正するのだ
            if page_num not in pdfminer_pages:
                pdfminer_pages[page_num] = []
            pdfminer_pages[page_num].append(item)

        corrected_pdfminer_data = []
        for page_num, items in pdfminer_pages.items():
            if page_num not in pypdf_texts_by_page:
                corrected_pdfminer_data.extend(items)
                continue

            # pdfminer_dataを論理的な行に展開
            # 各itemが複数の論理的な行を含む可能性があるため、ここで展開する
            pdfminer_logical_lines: List[TextBlock] = [] # 型ヒントを修正するのだ
            for item_index, item in enumerate(items):
                split_text = item.text.split('\n') # 属性アクセスに修正するのだ
                for line_in_block_index, line_text in enumerate(split_text):
                    if line_text.strip():
                        # 元のitemの情報を保持しつつ、論理的な行を作成
                        # TextBlockのコピーを作成し、textを更新するのだ
                        logical_line = TextBlock(
                            text=line_text.strip(),
                            bbox=item.bbox,
                            font_info=item.font_info,
                            page_number=item.page_number,
                            column_index=item.column_index
                        )
                        # 元のitemのインデックスと行のインデックスを一時的に保持するのだ
                        # TextBlockに直接追加できないので、別途管理するか、TextBlockを拡張する必要があるのだ
                        # ここでは、一時的に属性を追加する形で対応するのだ
                        setattr(logical_line, 'original_item_index', item_index)
                        setattr(logical_line, 'line_in_block_index', line_in_block_index)
                        pdfminer_logical_lines.append(logical_line)

            # 論理的な行をy座標（降順）、x座標（昇順）でソートして、読み取り順序を確立
            pdfminer_logical_lines.sort(key=lambda x: (-x.bbox.y1, x.bbox.x0)) # 属性アクセスに修正するのだ

            pdfminer_lines_text_for_comparison = [ll.text for ll in pdfminer_logical_lines] # 属性アクセスに修正するのだ
            self.logger.debug(f"Page {page_num} pdfminer_lines_text_for_comparison: {pdfminer_lines_text_for_comparison}")

            pypdf_raw_text = pypdf_texts_by_page[page_num]
            self.logger.debug(f"Page {page_num} pypdf_raw_text: '{pypdf_raw_text}'")
            pypdf_lines = [line.strip() for line in pypdf_raw_text.split('\n') if line.strip()]
            self.logger.debug(f"Page {page_num} pypdf_lines: {pypdf_lines}")

            if len(pdfminer_lines_text_for_comparison) != len(pypdf_lines):
                self.logger.warning(f"Page {page_num}: Line count mismatch between pdfminer ({len(pdfminer_lines_text_for_comparison)}) and pypdf ({len(pypdf_lines)}). Skipping correction for this page.")
                corrected_pdfminer_data.extend(items)
                continue

            matcher = difflib.SequenceMatcher(None, pdfminer_lines_text_for_comparison, pypdf_lines)
            for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                if tag == 'replace':
                    for i in range(i1, i2):
                        p_line_index = j1 + (i - i1)
                        if p_line_index < len(pypdf_lines):
                            self.logger.info(f"Replacing line on page {page_num}: '{pdfminer_logical_lines[i].text}' -> '{pypdf_lines[p_line_index]}'") # 属性アクセスに修正するのだ
                            pdfminer_logical_lines[i].text = pypdf_lines[p_line_index] # 属性アクセスに修正するのだ

            # 修正された論理的な行を元のpdfminer_dataの構造に戻す
            # 各元のitemのtextを再構築するための辞書
            reconstructed_texts: Dict[int, List[str]] = {}
            for ll in pdfminer_logical_lines:
                original_item_index = getattr(ll, 'original_item_index') # 属性アクセスに修正するのだ
                if original_item_index not in reconstructed_texts:
                    reconstructed_texts[original_item_index] = []
                reconstructed_texts[original_item_index].append(ll.text) # 属性アクセスに修正するのだ
            
            # 元のitemsをコピーして、textを更新するのだ
            temp_pdfminer_data = []
            for item_index, original_item in enumerate(items):
                if item_index in reconstructed_texts:
                    # 修正された論理的な行を結合して、元のitemのtextを更新
                    updated_text = "\n".join(reconstructed_texts[item_index])
                    temp_pdfminer_data.append(TextBlock(
                        text=updated_text,
                        bbox=original_item.bbox,
                        font_info=original_item.font_info,
                        page_number=original_item.page_number,
                        column_index=original_item.column_index
                    ))
                else:
                    temp_pdfminer_data.append(original_item) # 変更がない場合は元のアイテムを追加するのだ
            
            corrected_pdfminer_data.extend(temp_pdfminer_data)

        self.logger.debug("Function end: _correct_text_with_pypdf (success)")
        return corrected_pdfminer_data
