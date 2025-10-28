# Copyright 2025 npz35
#
# See the NOTICE file for this project for license details.
# This file may not be used except in accordance with the NOTICE.

import logging
from typing import List, Dict, Any, Optional
import pdfplumber
import numpy as np
from scipy.signal import find_peaks
from app.config import Config
from app.data_model import BBox, TextArea, TextBlock, FontInfo
from app.text.pdfminer import PdfminerAnalyzer
from app.text.pdfplumber import PdfplumberAnalyzer
from app.text.pypdf import PyPdfAnalyzer
from app.text.unstructured import UnstructuredAnalyzer

class PdfTextExtractor:
    """
    PDFからテキストを抽出し、テキストブロックを構成するクラスなのだ。
    列の検出やテキストブロックの結合ロジックを含むのだ。
    """
    def __init__(self):
        self.logger: logging.Logger = logging.getLogger(__name__)
        self.logger.debug("Function start: PdfTextExtractor.__init__()")
        self.logger.debug("Function end: PdfTextExtractor.__init__ (success)")
        self.pdfminer_analyzer = PdfminerAnalyzer()
        self.pdfplumber_analyzer = PdfplumberAnalyzer()
        self.pypdf_analyzer = PyPdfAnalyzer()
        self.unstructured_analyzer = UnstructuredAnalyzer()

    def _convert_char_data_to_text_blocks(self, char_data_list: List[List[Dict[str, Any]]]) -> List[List[TextBlock]]:
        """
        Converts a list of lists of character dictionaries into a list of lists of TextBlock instances.
        """
        converted_blocks: List[List[TextBlock]] = []
        for char_list in char_data_list:
            block_of_textblocks: List[TextBlock] = []
            for char_info in char_list:
                bbox_obj = BBox(x0=char_info['bbox'][0], y0=char_info['bbox'][1], x1=char_info['bbox'][2], y1=char_info['bbox'][3])
                font_info_obj = FontInfo(
                    name=char_info.get('font_name', "Helvetica"),
                    size=char_info.get('font_size', 12.0),
                    is_bold=char_info.get('is_bold', False),
                    is_italic=char_info.get('is_italic', False)
                )
                block_of_textblocks.append(TextBlock(
                    text=char_info.get('text', ''),
                    bbox=bbox_obj,
                    font_info=font_info_obj,
                    page_number=char_info.get('page_number', 0),
                ))
            converted_blocks.append(block_of_textblocks)
        return converted_blocks

    def _get_column_boundaries(self, all_page_text_blocks: List[List[TextBlock]], page_width: float) -> List[float]:
        """
        テキストブロックのX座標の分布を分析し、列の境界を動的に決定するのだ。
        ヒストグラム分析とピーク検出を用いて、列間の空白領域を特定するのだ。
        """
        if not all_page_text_blocks:
            return []

        # テキストブロックのX座標の中心点を収集するのだ
        x_centers = []
        for page_text_blocks in all_page_text_blocks:
            for block in page_text_blocks:
                if block.bbox: # TextBlockのbbox属性にアクセスするのだ
                    x0, _, x1, _ = block.bbox.x0, block.bbox.y0, block.bbox.x1, block.bbox.y1
                    x_centers.append((x0 + x1) / 2)

        if not x_centers:
            return []

        # ヒストグラムを作成するのだ
        # ビンの数をページの幅に応じて調整するのだ
        num_bins = int(page_width / 5) # 5ptごとにビンを作成するのだ
        hist, bin_edges = np.histogram(x_centers, bins=num_bins, range=(0, page_width))

        # ヒストグラムを平滑化するのだ（ノイズを減らすため）
        smoothed_hist = np.convolve(hist, np.ones(5)/5, mode='valid') # 5点移動平均なのだ

        # ピーク（テキストの集中領域）を検出するのだ
        # 谷間（列間の空白領域）を見つけるために、ヒストグラムを反転させてピークを検出するのだ
        inverted_hist = -smoothed_hist
        # ピークの相対的な高さと幅を調整して、適切な谷間を見つけるのだ
        peaks, _ = find_peaks(inverted_hist, prominence=0.5 * np.max(inverted_hist), width=5)

        column_boundaries = []
        for peak_idx in peaks:
            # ピークの位置が列の境界となるのだ
            # bin_edgesのインデックスはsmoothed_histより小さいので調整するのだ
            boundary_x = bin_edges[peak_idx + 2] # 調整が必要なのだ
            column_boundaries.append(boundary_x)
        
        # 検出された境界をソートするのだ
        column_boundaries.sort()

        # ページの端を境界として追加するのだ
        if 0 not in column_boundaries:
            column_boundaries.insert(0, 0)
        if page_width not in column_boundaries:
            column_boundaries.append(page_width)

        # 重複を削除してソートし直すのだ
        column_boundaries = sorted(list(set(column_boundaries)))

        self.logger.debug(f"Detected column boundaries: {column_boundaries}, page_width: {page_width}")
        return column_boundaries

    def _get_block_column_index(self, block: TextBlock, column_boundaries: List[float]) -> int:
        """
        テキストブロックがどの列に属するかを判断するのだ。
        """
        if not block.bbox or not column_boundaries: # TextBlockのbbox属性にアクセスするのだ
            return -1 # 不明なのだ

        block_x0 = block.bbox.x0 # TextBlockのbbox属性にアクセスするのだ
        for i in range(len(column_boundaries) - 1):
            if column_boundaries[i] <= block_x0 < column_boundaries[i+1]:
                return i
        return -1 # どの列にも属さないのだ

    def _combine_chars_to_text_blocks(self, char_data_list: List[List[TextBlock]], page_width: float, column_boundaries: List[float]) -> List[TextBlock]:
        """
        Combines character-level data into logical text blocks,
        considering detected column layouts.
        """
        combined_blocks: List[TextBlock] = []
        
        # ページごとに処理するために、char_data_listをページ番号でグループ化するのだ
        grouped_by_page: Dict[int, List[List[TextBlock]]] = {} # 型ヒントを修正するのだ
        for char_list in char_data_list:
            if char_list and char_list[0].page_number is not None: # TextBlockの属性にアクセスするのだ
                page_num = char_list[0].page_number # TextBlockの属性にアクセスするのだ
                if page_num not in grouped_by_page:
                    grouped_by_page[page_num] = []
                grouped_by_page[page_num].append(char_list)

        for page_num in sorted(grouped_by_page.keys()):
            page_char_lists = grouped_by_page[page_num]

            # ページ内のテキストブロックをソートするのだ
            # まず列のインデックスでソートし、次にY座標（top座標で昇順）、X座標（昇順）でソートするのだ
            sorted_page_char_lists = sorted(page_char_lists, key=lambda block_list: (
                self._get_block_column_index(block_list[0], column_boundaries), # 列のインデックスでソートなのだ
                block_list[0].bbox.y0 if block_list and block_list[0].bbox else float('inf'), # top座標で昇順なのだ
                block_list[0].bbox.x0 if block_list and block_list[0].bbox else float('-inf')
            ))

            current_block_chars_on_page: List[TextBlock] = [] # TextBlockのリストに変更するのだ

            for i, char_list in enumerate(sorted_page_char_lists):
                if not char_list:
                    continue

                first_char_current = char_list[0]
                current_y0 = first_char_current.bbox.y0 if first_char_current.bbox else None
                current_x0 = first_char_current.bbox.x0 if first_char_current.bbox else None
                current_column_index = self._get_block_column_index(first_char_current, column_boundaries)

                if not current_block_chars_on_page:
                    current_block_chars_on_page.extend(char_list)
                else:
                    last_char_prev_block = current_block_chars_on_page[-1]
                    prev_y1 = last_char_prev_block.bbox.y1 if last_char_prev_block.bbox else None
                    prev_x1 = last_char_prev_block.bbox.x1 if last_char_prev_block.bbox else None
                    prev_column_index = self._get_block_column_index(last_char_prev_block, column_boundaries)

                    Y_TOLERANCE = 2
                    X_TOLERANCE = 5
                    
                    is_same_line = (prev_y1 is not None and current_y0 is not None and abs(current_y0 - prev_y1) < Y_TOLERANCE)
                    is_continuous_x = (prev_x1 is not None and current_x0 is not None and (current_x0 - prev_x1) < X_TOLERANCE)
                    is_same_column = (current_column_index != -1 and current_column_index == prev_column_index)

                    if is_same_line and is_continuous_x and is_same_column:
                        current_block_chars_on_page.extend(char_list)
                    else:
                        if current_block_chars_on_page:
                            self._finalize_text_block(current_block_chars_on_page, combined_blocks, prev_column_index) # column_indexを渡すのだ
                        current_block_chars_on_page = list(char_list)

            if current_block_chars_on_page:
                self._finalize_text_block(current_block_chars_on_page, combined_blocks, current_column_index) # column_indexを渡すのだ

        return combined_blocks

    def _finalize_text_block(self, block_chars: List[TextBlock], combined_blocks: List[TextBlock], column_index: int):
        """Helper function to finalize a text block and append it to combined_blocks."""
        text_content = "".join([char.text for char in block_chars]) # 属性アクセスに修正するのだ
        
        valid_bboxes = [char.bbox for char in block_chars if char.bbox is not None] # 属性アクセスに修正するのだ

        if valid_bboxes:
            min_x0 = min(b.x0 for b in valid_bboxes)
            min_y0 = min(b.y0 for b in valid_bboxes)
            max_x1 = max(b.x1 for b in valid_bboxes)
            max_y1 = max(b.y1 for b in valid_bboxes)
            bbox = BBox(x0=min_x0, y0=min_y0, x1=max_x1, y1=max_y1)
        else:
            bbox = BBox(x0=0.0, y0=0.0, x1=0.0, y1=0.0)

        page_number = block_chars[0].page_number if block_chars else 0 # 属性アクセスに修正するのだ
        
        font_names = [char.font_info.name for char in block_chars if char.font_info and char.font_info.name] # 属性アクセスに修正するのだ
        font_sizes = [char.font_info.size for char in block_chars if char.font_info and char.font_info.size] # 属性アクセスに修正するのだ
        is_bold_flags = [char.font_info.is_bold for char in block_chars if char.font_info] # 属性アクセスに修正するのだ
        is_italic_flags = [char.font_info.is_italic for char in block_chars if char.font_info] # 属性アクセスに修正するのだ

        font_name = max(set(font_names), key=font_names.count) if font_names else "Helvetica"
        font_size = sum(font_sizes) / len(font_sizes) if font_sizes else 12.0
        is_bold = any(is_bold_flags)
        is_italic = any(is_italic_flags)

        font_info = FontInfo(name=font_name, size=font_size, is_bold=is_bold, is_italic=is_italic)

        combined_blocks.append(TextBlock(
            text=text_content.strip(),
            bbox=bbox,
            font_info=font_info,
            page_number=page_number,
            column_index=column_index
        ))

    def extract_text_blocks(self, pdf_path: str, char_data_from_specific_extractor: Optional[List[List[TextBlock]]] = None) -> List[TextBlock]:
        self.logger.debug(f"Function start: extract_text_blocks(pdf_path='{pdf_path}', char_data_from_specific_extractor={char_data_from_specific_extractor is not None})")
        
        page_width: float = 0.0
        all_page_text_blocks: List[List[TextBlock]] = []

        try:
            if char_data_from_specific_extractor:
                # 特定の抽出器からデータが渡された場合、そのデータからpage_widthと列検出用のブロックを推測するのだ
                # bboxの最大X座標をpage_widthとする（簡易的な方法なのだ）
                max_x = 0.0
                max_y = 0.0
                for page_chars in char_data_from_specific_extractor:
                    page_text_blocks: List[TextBlock] = []
                    for char_info in page_chars:
                        if char_info.bbox:
                            max_x = max(max_x, char_info.bbox.x1)
                            max_y = max(max_y, char_info.bbox.y1)
                            bbox_obj = char_info.bbox
                            page_text_blocks.append(TextBlock(
                                text="",
                                bbox=bbox_obj,
                                font_info=char_info.font_info,
                                page_number=char_info.page_number,
                            ))
                    all_page_text_blocks.append(page_text_blocks)

                if max_x > 0 and max_y > 0:
                    # ページの幅と高さをbboxから推測するのだ
                    # ここでは幅のみが必要なので、max_xを使用するのだ
                    page_width = max_x + 50 # 少し余裕を持たせるのだ
                else:
                    # デフォルトのページ幅を設定するのだ (例: A4の幅)
                    page_width = 595.276 # ReportLabのA4幅なのだ
                self.logger.debug(f"Inferred page_width from char_data_from_specific_extractor: {page_width}")
            else:
                # pdfplumberでPDFを開いてpage_widthと列検出用のブロックを収集するのだ
                page_width = self.pdfplumber_analyzer.first_page_width(pdf_path)
                all_page_text_blocks = self.pdfplumber_analyzer.extract_textblocks(pdf_path)
                self.logger.debug(f"Obtained page_width from pdfplumber: {page_width}")

            # 列の境界を検出するのだ
            column_boundaries = self._get_column_boundaries(all_page_text_blocks, page_width)

            if char_data_from_specific_extractor:
                # 渡された文字ごとのデータをTextBlockのリストに変換して結合するのだ
                combined_data = self._combine_chars_to_text_blocks(char_data_from_specific_extractor, page_width, column_boundaries)
                return combined_data
            elif Config.TEXT_EXTRACTION_METHOD == "pdfplumber":
                # pdfplumberは文字ごとの抽出に対応していないため、既存の関数をそのまま使用
                # ただし、_combine_chars_to_text_blocksで処理できるように、単語リストのリストとして返す
                # ここでは、extract_text_with_positions_pdfplumberが返す形式を想定しているのだ
                # extract_text_with_positions_pdfplumberはList[List[Dict[str, Any]]]を返すので、TextBlockのリストに変換するのだ
                pdfplumber_char_data = self.pdfplumber_analyzer.extract_textblocks(pdf_path)
                converted_char_data = pdfplumber_char_data
                return self._combine_chars_to_text_blocks(converted_char_data, page_width, column_boundaries)
            elif Config.TEXT_EXTRACTION_METHOD == "unstructured":
                # unstructuredは既にテキストブロックを返すので、そのまま返すのだ
                return self.unstructured_analyzer.extract_textblocks(pdf_path)
            elif Config.TEXT_EXTRACTION_METHOD == "pypdf":
                pypdf_char_data = self.pypdf_analyzer.extract_textblocks(pdf_path)
                return self._combine_chars_to_text_blocks(pypdf_char_data, page_width, column_boundaries)
            elif Config.TEXT_EXTRACTION_METHOD == "hybrid_pdfminer_pypdf":
                # ハイブリッドモードはPdfTextManagerで処理するため、ここではサポートしない
                self.logger.error("Hybrid mode is not supported in common text extraction.")
                raise ValueError("Hybrid mode is not supported in common text extraction.")
            else:
                self.logger.error(f"Unknown text extraction method: {Config.TEXT_EXTRACTION_METHOD}")
                raise ValueError(f"Unknown text extraction method: {Config.TEXT_EXTRACTION_METHOD}")

        except Exception as e:
            self.logger.error(f"Error in extract_text_blocks: {e}")
            raise

    def extract_textareas(self, pdf_path: str) -> List[List[TextArea]]:
        self.logger.debug(f"Function start: extract_textareas(pdf_path='{pdf_path}')")
        
        if Config.TEXT_EXTRACTION_METHOD == "pdfplumber":
            return self.pdfplumber_analyzer.extract_textareas(pdf_path)
        elif Config.TEXT_EXTRACTION_METHOD == "unstructured":
            # return self.unstructured_analyzer.extract_textareas(pdf_path)
            raise NotImplementedError("Not implement yet.")
        elif Config.TEXT_EXTRACTION_METHOD == "pypdf":
            # return self.pypdf_analyzer.extract_textareas(pdf_path)
            raise NotImplementedError("Not implement yet.")
        elif Config.TEXT_EXTRACTION_METHOD == "hybrid_pdfminer_pypdf":
            raise NotImplementedError("Not implement yet.")
        else:
            self.logger.error(f"Unknown text extraction method: {Config.TEXT_EXTRACTION_METHOD}")
            raise ValueError(f"Unknown text extraction method: {Config.TEXT_EXTRACTION_METHOD}")
