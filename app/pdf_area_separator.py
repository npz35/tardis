# Copyright 2025 npz35
#
# See the NOTICE file for this project for license details.
# This file may not be used except in accordance with the NOTICE.

import os
import logging
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
import pdfplumber
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.colors import red, blue, green, black, lightgreen, Color
from app.data_model import BBox, PageAnalyzeData, TextArea, TextBlock, FontInfo, BBoxRL, Area
from app.pdf_text_extractor import PdfTextExtractor
from app.config import Config
from app.text.pdfplumber import PdfplumberAnalyzer

from app.pdf_column_separator import PdfColumnSeparator


class PdfAreaSeparator:
    # 除外条件の閾値を設定するのだ (調整が必要なのだ)
    MIN_HEIGHT_THRESHOLD = 999.0  # 縦幅がこれ以下の場合は小さいとみなすのだ
    MAX_WIDTH_RATIO_THRESHOLD = 0.5 # 横幅がページ幅のこれ以上の場合は大きいとみなすのだ
    # 画像ブロックのY座標範囲とテキストブロックが重なるか、または非常に近いかをチェックするのだ
    # Y軸方向の許容誤差を設けるのだ
    Y_TOLERANCE = 999.0 # 隣接
    Y_TOLERANCE_BLOCK_MERGE = 2.0 # 隣接
    X_TOLERANCE_BLOCK_MERGE = 5.0 # 左右のテキストブロック統合時のX方向の許容誤差なのだ
    X_SPARSE_RATIO = 0.7

    def __init__(self, output_folder: str):
        self.logger: logging.Logger = logging.getLogger(__name__)
        self.output_folder = output_folder
        self.pdf_text_extractor = PdfTextExtractor()
        self.pdf_column_separator = PdfColumnSeparator(output_folder)
        self.pdfplumber_analyzer = PdfplumberAnalyzer()

    def _is_overlapping(self, target_bbox: BBox, text_block_bboxes: List[BBox]) -> bool:
        """
        指定されたBBoxがテキストブロックのBBoxリストのいずれかと重なっているかを判定するのだ。
        """
        for text_bbox in text_block_bboxes:
            # 重なっていない条件:
            # 1. target_bboxがtext_bboxの左にある
            # 2. target_bboxがtext_bboxの右にある
            # 3. target_bboxがtext_bboxの下にある
            # 4. target_bboxがtext_bboxの上にある
            if not (target_bbox.x1 <= text_bbox.x0 or
                    text_bbox.x1 <= target_bbox.x0 or
                    target_bbox.y1 <= text_bbox.y0 or
                    text_bbox.y1 <= target_bbox.y0):
                return True # 重なっているのだ
        return False # 重なっていないのだ

    def _convert_bbox_to_reportlab_coords(self, bbox: BBox, page_height: float) -> 'BBoxRL':
        """
        pdfplumberのbbox座標をReportLabの座標に変換し、BBoxRLインスタンスとして返すのだ。
        pdfplumberは左下原点、ReportLabも左下原点だが、Y軸の向きが異なる場合があるため調整する。
        """
        # pdfplumberとReportLabはどちらも左下原点、Y軸上向きなので、Y座標の変換は不要なのだ
        x = bbox.x0
        y = bbox.y0
        width = bbox.x1 - bbox.x0
        height = bbox.y1 - bbox.y0
        
        return BBoxRL(x=x, y=y, width=width, height=height)

    def _identify_figures_and_tables(self, page_width: float, page_height: float, text_block_bboxes: List[BBox], rect_bboxes: List[BBox], image_bboxes: List[BBox], page_analyze_data: PageAnalyzeData) -> Tuple[List[BBox], List[BBox], List[BBox]]:
        """
        テキストブロック以外の領域から図や表を識別するのだ。
        列の境界がある場合は、左右の領域で個別に判定し、1列組と2列組の図を分けて返すのだ。
        """
        single_column_figures: List[BBox] = []
        two_column_figures: List[BBox] = []
        tables: List[BBox] = [] # テーブルは色分けしないので1つのリストで良いのだ

        # 列の境界がある場合は、左右の領域で個別に判定するのだ
        # 2列組の境界データが存在する場合
        if page_analyze_data and page_analyze_data.column_boundary_data:
            # column_boundary_dataは (WordsBorderGap, border_bottom, border_top) のタプルなのだ
            gap, border_bottom, border_top = page_analyze_data.column_boundary_data
            column_boundary_x = gap.center_x()

            # ページを3つの領域に分割して処理するのだ
            # 1. border_top より上の領域 (単一列として処理)
            top_region_text_blocks = [bbox for bbox in text_block_bboxes if bbox.y0 >= border_top]
            top_region_rect_bboxes = [bbox for bbox in rect_bboxes if bbox.y0 >= border_top]
            top_region_image_bboxes = [bbox for bbox in image_bboxes if bbox.y0 >= border_top]

            self.logger.debug('top process region')
            top_figures, top_tables = self._process_region(page_width, page_height, top_region_text_blocks, top_region_rect_bboxes, top_region_image_bboxes)
            single_column_figures.extend(top_figures)
            tables.extend(top_tables)

            # 2. border_bottom と border_top の間の領域 (2列として処理)
            # この領域に属するテキストブロック、rects、imagesをフィルタリングするのだ
            two_column_region_text_blocks = [bbox for bbox in text_block_bboxes if border_bottom <= bbox.y0 and bbox.y1 <= border_top]
            two_column_region_rect_bboxes = [bbox for bbox in rect_bboxes if border_bottom <= bbox.y0 and bbox.y1 <= border_top]
            two_column_region_image_bboxes = [bbox for bbox in image_bboxes if border_bottom <= bbox.y0 and bbox.y1 <= border_top]

            # 左側の領域で図と表を識別するのだ
            left_text_block_bboxes = [bbox for bbox in two_column_region_text_blocks if bbox.x1 <= column_boundary_x]
            right_text_block_bboxes = [bbox for bbox in two_column_region_text_blocks if bbox.x0 >= column_boundary_x]

            left_rect_bboxes = [bbox for bbox in two_column_region_rect_bboxes if bbox.x1 <= column_boundary_x]
            right_rect_bboxes = [bbox for bbox in two_column_region_rect_bboxes if bbox.x0 >= column_boundary_x]

            left_image_bboxes = [bbox for bbox in two_column_region_image_bboxes if bbox.x1 <= column_boundary_x]
            right_image_bboxes = [bbox for bbox in two_column_region_image_bboxes if bbox.x0 >= column_boundary_x]

            self.logger.debug('left process region')
            left_figures, left_tables = self._process_region(page_width, page_height, left_text_block_bboxes, left_rect_bboxes, left_image_bboxes)
            two_column_figures.extend(left_figures)
            tables.extend(left_tables)

            # 右側の領域で図と表を識別するのだ
            self.logger.debug('right process region')
            right_figures, right_tables = self._process_region(page_width, page_height, right_text_block_bboxes, right_rect_bboxes, right_image_bboxes)
            two_column_figures.extend(right_figures)
            tables.extend(right_tables)

            # 3. border_bottom より下の領域 (単一列として処理)
            bottom_region_text_blocks = [bbox for bbox in text_block_bboxes if bbox.y1 <= border_bottom]
            bottom_region_rect_bboxes = [bbox for bbox in rect_bboxes if bbox.y1 <= border_bottom]
            bottom_region_image_bboxes = [bbox for bbox in image_bboxes if bbox.y1 <= border_bottom]

            self.logger.debug('bottom process region')
            bottom_figures, bottom_tables = self._process_region(page_width, page_height, bottom_region_text_blocks, bottom_region_rect_bboxes, bottom_region_image_bboxes)
            single_column_figures.extend(bottom_figures)
            tables.extend(bottom_tables)

            self.logger.debug(f"top_figures   : {top_figures}")
            self.logger.debug(f"top_tables    : {top_tables}")
            self.logger.debug(f"left_figures  : {left_figures}")
            self.logger.debug(f"left_tables   : {left_tables}")
            self.logger.debug(f"right_figures : {right_figures}")
            self.logger.debug(f"right_tables  : {right_tables}")
            self.logger.debug(f"bottom_figures: {bottom_figures}")
            self.logger.debug(f"bottom_tables : {bottom_tables}")
        else:
            # 列の境界がない場合は、ページ全体で判定するのだ
            self.logger.debug('full process region')
            page_figures, page_tables = self._process_region(page_width, page_height, text_block_bboxes, rect_bboxes, image_bboxes)
            single_column_figures.extend(page_figures)
            tables.extend(page_tables)

            self.logger.debug(f"page_figures: {page_figures}")
            self.logger.debug(f"page_tables : {page_tables}")
        
        return single_column_figures, two_column_figures, tables

    def _process_region(self, page_width: float, page_height: float, text_block_bboxes: List[BBox], page_rect_bboxes: List[BBox], page_image_bboxes: List[BBox]) -> Tuple[List[BBox], List[BBox]]:
        region_figures: List[BBox] = []
        region_tables: List[BBox] = []

        # rects の処理
        for rect_bbox in page_rect_bboxes:
            is_overlapping_with_text = self._is_overlapping(rect_bbox, text_block_bboxes)
            
            if not is_overlapping_with_text:
                region_tables.append(rect_bbox)

        # images の処理
        for image_bbox in page_image_bboxes:
            # 画像ブロックの縦幅と横幅を計算するのだ
            image_height = image_bbox.y1 - image_bbox.y0
            image_width = image_bbox.x1 - image_bbox.x0

            # 上下に隣接するテキストブロックがあるかを確認するのだ
            has_adjacent_text_block = False
            for text_bbox in text_block_bboxes:
                # 画像ブロックのすぐ上またはすぐ下にテキストブロックがあるか
                # X軸が重なっているか
                overlap_x = max(image_bbox.x0, text_bbox.x0) < min(image_bbox.x1, text_bbox.x1)
                # テキストブロックが画像ブロックのすぐ上にある
                near_upper_y = abs(image_bbox.y0 - text_bbox.y1) <= self.Y_TOLERANCE
                # テキストブロックが画像ブロックのすぐ下にある
                near_lower_y = abs(image_bbox.y1 - text_bbox.y0) <= self.Y_TOLERANCE

                if overlap_x and (near_upper_y or near_lower_y):
                    has_adjacent_text_block = True
                    break

            # 除外条件をチェックするのだ
            # 1. 上下に隣接するテキストブロックがある
            # 2. 縦幅が十分に小さい
            # 3. 横幅が十分に大きい (ページ幅に対する比率で判断するのだ)
            short_height = image_height <= self.MIN_HEIGHT_THRESHOLD
            long_width = image_width >= page_width * self.MAX_WIDTH_RATIO_THRESHOLD

            self.logger.debug(f"has_adjacent_text_block: {has_adjacent_text_block}")
            self.logger.debug(f"short_height: {short_height}")
            self.logger.debug(f"long_width: {long_width}")

            if (has_adjacent_text_block and short_height and long_width):
                self.logger.debug(f"Excluding image bbox due to adjacent text, small height, and large width: {image_bbox}")
                continue # この画像ブロックは除外するのだ

            is_overlapping_with_text = self._is_overlapping(image_bbox, text_block_bboxes)
            
            if not is_overlapping_with_text:
                region_figures.append(image_bbox)
        
        return region_figures, region_tables

    def _create_text_block_from_words(self, words: List[TextBlock], page_number: int) -> TextBlock:
        if not words:
            return TextBlock(
                text='',
                bbox=BBox(x0=0, y0=0, x1=0, y1=0), # BBoxオブジェクトとして返すのだ
                font_info=FontInfo(name='unknown', size=0.0, is_bold=False, is_italic=False),
                page_number=page_number,
            )
        
        # 全ての単語のbboxを結合して、新しいテキストブロックのbboxを計算するのだ
        min_x0 = min(word.bbox.x0 for word in words)
        min_y0 = min(word.bbox.y0 for word in words)
        max_x1 = max(word.bbox.x1 for word in words)
        max_y1 = max(word.bbox.y1 for word in words)
        
        # テキストを結合するのだ
        combined_text = " ".join(word.text for word in words)

        # 最も頻繁に出現するフォント情報を取得するのだ
        font_names = [word.font_info.name for word in words if word.font_info.name]
        font_sizes = [word.font_info.size for word in words if word.font_info.size > 0]

        # 最頻値を取得するヘルパー関数なのだ
        def get_most_common(items: List[Any]) -> Any:
            if not items:
                return None
            from collections import Counter
            return Counter(items).most_common(1)[0][0]

        most_common_font_name = get_most_common(font_names)
        # フォントサイズが0.0の場合はデフォルト値を使用するのだ
        most_common_font_size = get_most_common(font_sizes)
        if most_common_font_size is None or most_common_font_size == 0.0:
            most_common_font_size = Config.DEFAULT_FONT_SIZE # デフォルトのフォントサイズを使用するのだ
        
        font_info = {
            'font_name': most_common_font_name if most_common_font_name else '',
            'font_size': most_common_font_size
        }
        
        return TextBlock(
            text=combined_text,
            bbox=BBox(x0=min_x0, y0=min_y0, x1=max_x1, y1=max_y1),
            page_number=page_number,
            font_info=font_info
        )

    def _combine_words_to_text_blocks(self, all_page_text_blocks: List[List[TextBlock]], page_analyze_data_list: List[PageAnalyzeData]) -> Tuple[List[TextBlock], List[List[BBox]]]:
        combined_text_blocks: List[TextBlock] = []
        all_page_guess_figure_bboxes: List[List[BBox]] = []
        
        for idx, page_text_blocks in enumerate(all_page_text_blocks):
            self.logger.debug(f'idx: {idx}')
            sorted_page_text_blocks: List[TextBlock] = sorted(page_text_blocks, key=lambda w: (w.bbox.y0, w.bbox.x0))
            page_analyze_data = next((data for data in page_analyze_data_list if data.page_num == idx), None)

            page_guess_figure_bboxes: List[BBox] = []

            if not page_analyze_data:
                self.logger.warning(f"Page analyze data not found for page {idx}. Skipping text block combination for this page.")
                continue

            # 2. 各ページで、Y座標が近い単語を同じ行としてグループ化するのだ
            lines: List[List[TextBlock]] = []
            if sorted_page_text_blocks:
                current_line: List[TextBlock] = [sorted_page_text_blocks[0]]
                for i in range(1, len(sorted_page_text_blocks)):
                    # 同じ行とみなすY座標の許容範囲を設定するのだ
                    # ここでは、前の単語の高さの半分を許容範囲とするのだ
                    if abs(sorted_page_text_blocks[i].bbox.y0 - current_line[-1].bbox.y0) < current_line[-1].height() / 2:
                        current_line.append(sorted_page_text_blocks[i])
                    else:
                        lines.append(current_line)
                        current_line = [sorted_page_text_blocks[i]]
                lines.append(current_line) # 最後の行を追加するのだ

            # 3. 各行を、列の境界を考慮しながらテキストブロックにまとめるのだ
            for line_words in lines:
                # 行内の単語をX座標でソートするのだ
                line_words.sort(key=lambda w: w.bbox.x0)

                # 行の単語密度を計算するのだ
                total_word_width = 0.0
                current_x_end = line_words[0].bbox.x0 # 現在までにカバーされたX軸の最大値なのだ

                for word in line_words:
                    if word.bbox.x0 > current_x_end:
                        # 単語間に空白がある場合、その単語の幅をそのまま加算するのだ
                        total_word_width += word.width()
                    else:
                        # 単語が重なっているか、隣接している場合、重なっていない部分の幅だけを加算するのだ
                        total_word_width += max(0.0, word.bbox.x1 - current_x_end)
                    
                    # current_x_endを更新するのだ
                    current_x_end = max(current_x_end, word.bbox.x1)
                
                line_bbox_width = line_words[-1].bbox.x1 - line_words[0].bbox.x0
                
                # 単語が1つしかない場合は密度を1とみなすのだ
                if len(line_words) == 1:
                    word_density = 1.0
                elif line_bbox_width > 0:
                    word_density = total_word_width / line_bbox_width
                else:
                    word_density = 0.0 # 幅がない場合は密度0なのだ

                # 単語密度が低い場合、その行全体を図とみなすのだ (閾値は調整が必要なのだ)
                if page_analyze_data.column_boundary_data:
                    # 2列組の場合の処理なのだ
                    gap, _, _ = page_analyze_data.column_boundary_data
                    column_boundary_x = gap.center_x()

                    left_column_words = [word for word in line_words if word.bbox.x1 <= column_boundary_x]
                    right_column_words = [word for word in line_words if word.bbox.x0 >= column_boundary_x]

                    # 左列の単語密度を計算するのだ
                    left_word_density = 0.0
                    if left_column_words:
                        left_total_word_width = 0.0
                        left_current_x_end = left_column_words[0].bbox.x0

                        for word in left_column_words:
                            if word.bbox.x0 > left_current_x_end:
                                left_total_word_width += word.width()
                            else:
                                left_total_word_width += max(0.0, word.bbox.x1 - left_current_x_end)
                            left_current_x_end = max(left_current_x_end, word.bbox.x1)
                        
                        left_line_bbox_width = left_column_words[-1].bbox.x1 - left_column_words[0].bbox.x0
                        if len(left_column_words) == 1:
                            left_word_density = 1.0
                        elif left_line_bbox_width > 0:
                            left_word_density = left_total_word_width / left_line_bbox_width
                        else:
                            left_word_density = 0.0
                        
                        if left_word_density < self.X_SPARSE_RATIO:
                            min_x0 = min(word.bbox.x0 for word in left_column_words)
                            min_y0 = min(word.bbox.y0 for word in left_column_words)
                            max_x1 = max(word.bbox.x1 for word in left_column_words)
                            max_y1 = max(word.bbox.y1 for word in left_column_words)
                            page_guess_figure_bboxes.append(BBox(x0=min_x0, y0=min_y0, x1=max_x1, y1=max_y1))
                            # 左列が図とみなされた場合、その単語はテキストブロックとして処理しないようにするのだ
                            line_words = [word for word in line_words if word not in left_column_words]

                    # 右列の単語密度を計算するのだ
                    right_word_density = 0.0
                    if right_column_words:
                        right_total_word_width = 0.0
                        right_current_x_end = right_column_words[0].bbox.x0

                        for word in right_column_words:
                            if word.bbox.x0 > right_current_x_end:
                                right_total_word_width += word.width()
                            else:
                                right_total_word_width += max(0.0, word.bbox.x1 - right_current_x_end)
                            right_current_x_end = max(right_current_x_end, word.bbox.x1)
                        
                        right_line_bbox_width = right_column_words[-1].bbox.x1 - right_column_words[0].bbox.x0
                        if len(right_column_words) == 1:
                            right_word_density = 1.0
                        elif right_line_bbox_width > 0:
                            right_word_density = right_total_word_width / right_line_bbox_width
                        else:
                            right_word_density = 0.0

                        if right_word_density < self.X_SPARSE_RATIO:
                            min_x0 = min(word.bbox.x0 for word in right_column_words)
                            min_y0 = min(word.bbox.y0 for word in right_column_words)
                            max_x1 = max(word.bbox.x1 for word in right_column_words)
                            max_y1 = max(word.bbox.y1 for word in right_column_words)
                            page_guess_figure_bboxes.append(BBox(x0=min_x0, y0=min_y0, x1=max_x1, y1=max_y1))
                            # 右列が図とみなされた場合、その単語はテキストブロックとして処理しないようにするのだ
                            line_words = [word for word in line_words if word not in right_column_words]
                else:
                    # 1列組の場合の処理なのだ
                    if word_density < self.X_SPARSE_RATIO: # 例: 単語の総幅が行のbbox幅の50%未満の場合
                        min_x0 = min(word.bbox.x0 for word in line_words)
                        min_y0 = min(word.bbox.y0 for word in line_words)
                        max_x1 = max(word.bbox.x1 for word in line_words)
                        max_y1 = max(word.bbox.y1 for word in line_words)
                        page_guess_figure_bboxes.append(BBox(x0=min_x0, y0=min_y0, x1=max_x1, y1=max_y1)) # BBoxオブジェクトとして追加するのだ
                        continue # 図とみなされた行はテキストブロックとして処理しないのだ
                
                current_block_words: List[TextBlock] = []
                for i, word in enumerate(line_words):
                    if not current_block_words:
                        current_block_words.append(word)
                    else:
                        prev_word = current_block_words[-1]
                        
                        # 列の境界を考慮するのだ
                        is_crossing_column_boundary = False
                        if page_analyze_data.column_boundary_data:
                            gap, _, _ = page_analyze_data.column_boundary_data
                            # 単語の間に列の境界があるかチェックするのだ
                            if prev_word.bbox.x1 < gap.center_x() < word.bbox.x0:
                                is_crossing_column_boundary = True
                        
                        # 単語間の距離が近い、かつ列の境界をまたがない場合に結合するのだ
                        # ここでは、前の単語の高さの半分を許容範囲とするのだ
                        # 同じ行にあると判断された単語は、X座標が近い場合に結合するのだ
                        if (word.bbox.x0 - prev_word.bbox.x1) < self.X_TOLERANCE_BLOCK_MERGE and not is_crossing_column_boundary:
                            current_block_words.append(word)
                        else:
                            if current_block_words:
                                combined_text_blocks.append(self._create_text_block_from_words(current_block_words, idx))
                            current_block_words = [word]
                
                if current_block_words:
                    combined_text_blocks.append(self._create_text_block_from_words(current_block_words, idx))

            all_page_guess_figure_bboxes.append(page_guess_figure_bboxes)
            
            # 左右に隣接するテキストブロックを統合するのだ
            # 同じページ内のブロックのみを対象にするのだ
            page_blocks = [block for block in combined_text_blocks if block.page_number == idx]
            
            # 統合処理を繰り返すのだ。なぜなら、統合によってさらに統合可能なブロックが生まれる可能性があるからなのだ。
            # 統合処理は、結合可能なブロックがなくなるまで繰り返すのだ
            while True:
                merged_any_block_in_page = False
                new_page_blocks: List[Dict[str, Any]] = []
                
                # 統合済みのブロックを追跡するセットなのだ
                merged_indices = set()

                for i in range(len(page_blocks)):
                    if i in merged_indices:
                        continue

                    block1: TextBlock = page_blocks[i]
                    merged_current_block = False

                    for j in range(i + 1, len(page_blocks)):
                        if j in merged_indices:
                            continue

                        block2: TextBlock = page_blocks[j]

                        # 同じ行にあり、かつ左右に隣接しているかをチェックするのだ
                        # Y座標が重なっているか、または非常に近いかをチェックするのだ
                        # X座標が隣接しているかをチェックするのだ
                        # 許容誤差は、ブロックの高さの半分とするのだ
                        gap_y0 = abs(block1.bbox.y0 - block2.bbox.y0)
                        gap_y1 = abs(block1.bbox.y1 - block2.bbox.y1)
                        gap_x = abs(block1.bbox.x1 - block2.bbox.x0)
                        if (gap_y0 <= self.Y_TOLERANCE_BLOCK_MERGE and
                            gap_y1 <= self.Y_TOLERANCE_BLOCK_MERGE and
                            gap_x <= self.X_TOLERANCE_BLOCK_MERGE): # X方向の距離が定数以下の場合に結合するのだ
                            
                            # 結合可能な場合、新しいブロックを作成するのだ
                            merged_bbox = BBox(
                                x0=min(block1.bbox.x0, block2.bbox.x0),
                                y0=min(block1.bbox.y0, block2.bbox.y0),
                                x1=max(block1.bbox.x1, block2.bbox.x1),
                                y1=max(block1.bbox.y1, block2.bbox.y1)
                            )
                            merged_text = f"{block1.text} {block2.text}" # テキストも結合するのだ
                            
                            # 結合可能な場合、新しいブロックを作成するのだ
                            # 統合されたブロックのfont_infoは、結合元のブロックのfont_infoを引き継ぐのだ
                            merged_font_info = block1.font_info # block1のfont_infoをデフォルトとするのだ
                            
                            new_page_blocks.append(TextBlock(
                                text=merged_text,
                                bbox=merged_bbox,
                                font_info=merged_font_info,
                                page_number=idx,
                            ))
                            merged_indices.add(i)
                            merged_indices.add(j)
                            merged_any_block_in_page = True
                            merged_current_block = True
                            break # block1とblock2が結合されたので、次のblock1を探すのだ
                    
                    if not merged_current_block and i not in merged_indices:
                        new_page_blocks.append(block1) # 統合されなかったブロックもfont_infoを持つはずなのだ
                
                # 統合が行われなかった場合はループを終了するのだ
                if not merged_any_block_in_page:
                    break
                
                # 統合されたブロックでpage_blocksを更新するのだ
                page_blocks = new_page_blocks
            
            # 統合されたブロックを全体のリストに反映するのだ
            # まず、現在のページに属する既存のブロックを削除するのだ
            combined_text_blocks = [block for block in combined_text_blocks if block.page_number != idx]
            # 次に、統合された新しいブロックを追加するのだ
            combined_text_blocks.extend(page_blocks)
            
        # 最終的なテキストブロックをページ番号、Y座標、X座標でソートするのだ
        combined_text_blocks.sort(key=lambda b: (b.page_number, b.bbox.y0, b.bbox.x0))

        return combined_text_blocks, all_page_guess_figure_bboxes

    def extract_area_infos(self, input_pdf_path: str) -> List[List[Area]]:
        """
        PDFからテキスト領域と図表領域を抽出し、描画情報を収集するのだ。
        pre_extracted_text_blocksが指定された場合、それを使用してテキストブロックを構成するのだ。
        """
        all_page_areas: List[List[Area]] = []

        page_width, page_height = self.pdfplumber_analyzer.extract_pazesizes(input_pdf_path)[0]

        page_analyze_data_list = self.pdf_column_separator.analyze_separation_lines(input_pdf_path)
        
        # guess_figure_bboxes: List[List[BBox]] = []

        if Config.TEXT_EXTRACTION_METHOD == "pdfplumber":
            all_page_text_areas = self.pdfplumber_analyzer.extract_textareas(input_pdf_path)
            # TODO
            # guess_figure_bboxes = self._guess_figure_bboxes(all_page_text_areas, page_analyze_data_list)
        elif Config.TEXT_EXTRACTION_METHOD == "unstructured":
            raise NotImplementedError("Not implement yet.")
        elif Config.TEXT_EXTRACTION_METHOD == "pypdf":
            raise NotImplementedError("Not implement yet.")
        elif Config.TEXT_EXTRACTION_METHOD == "hybrid_pdfminer_pypdf":
            raise NotImplementedError("Not implement yet.")
        else:
            raise ValueError(f"Unknown text extraction method: {Config.TEXT_EXTRACTION_METHOD}")

        self.pdfplumber_analyzer.extract_textareas(input_pdf_path)
        self.pdfplumber_analyzer.extract_rect_blocks(input_pdf_path)
        self.pdfplumber_analyzer.extract_image_blocks(input_pdf_path)

        # 2. ページごとのエリア情報を収集するためのループなのだ
        for idx in range(len(all_page_text_areas)):
            page_width, page_height = self.pdfplumber_analyzer.all_page_sizes[idx]

            self.logger.debug(f'current idx: {idx}')

            text_areas = self.pdfplumber_analyzer.all_page_text_areas[idx]
            page_analyze_data = page_analyze_data_list[idx]
            text_bboxes = [area.bbox for area in text_areas]
            rect_bboxes = self.pdfplumber_analyzer.all_page_rect_blocks[idx]
            image_bboxes = self.pdfplumber_analyzer.all_page_image_blocks[idx]

            single_column_figures, two_column_figures, tables_bboxes = self._identify_figures_and_tables(
                page_width, page_height, text_bboxes, rect_bboxes, image_bboxes, page_analyze_data
            )
            # single_column_figures.extend(guess_figure_bboxes[idx]) # TODO

            # テキストブロックにIDを割り振るのだ
            page_areas: List[Area] = []
            for i, text_area in enumerate(text_areas):
                bbox_obj = text_area.bbox
                bbox_rl = self._convert_bbox_to_reportlab_coords(bbox_obj, page_height)

                text = text_area.text()
                font_info = text_area.blocks[0].font_info # TODO
                if not text.strip():
                    color_to_draw = black
                    self.logger.debug(f"Prepare to draw black rect for empty text block ({bbox_rl})")
                else:
                    color_to_draw = red
                    self.logger.debug(f"Prepare to draw red rect ({bbox_rl}), text: {text}")
                
                page_areas.append(
                    Area(color=color_to_draw, rect=bbox_rl, text=text, block_id=i + 1, font_info=font_info) # 1から始まるIDを振り、font_infoを追加するのだ
                )

            self.logger.debug(f"tables_bboxes size        : {len(tables_bboxes)}")
            self.logger.debug(f"single_column_figures size: {len(single_column_figures)}")
            self.logger.debug(f"two_column_figures size   : {len(two_column_figures)}")

            for bbox_obj in tables_bboxes:
                bbox_rl = self._convert_bbox_to_reportlab_coords(bbox_obj, page_height)
                color_to_draw = blue
                self.logger.debug(f"Prepare to draw blue rect ({bbox_rl})")
                page_areas.append(
                    Area(color=color_to_draw, rect=bbox_rl)
                )
            
            for bbox_obj in single_column_figures:
                bbox_rl = self._convert_bbox_to_reportlab_coords(bbox_obj, page_height)
                color_to_draw = green
                self.logger.debug(f"Prepare to draw green rect ({bbox_rl})")
                page_areas.append(
                    Area(color=color_to_draw, rect=bbox_rl)
                )

            for bbox_obj in two_column_figures:
                bbox_rl = self._convert_bbox_to_reportlab_coords(bbox_obj, page_height)
                color_to_draw = lightgreen
                self.logger.debug(f"Prepare to draw lightgreen rect ({bbox_rl})")
                page_areas.append(
                    Area(color=color_to_draw, rect=bbox_rl)
                )
            
            all_page_areas.append(page_areas)
    
        return all_page_areas

    def _draw_colored_pdf(self, output_filepath: str, all_page_areas: List[List[Area]]) -> str:
        """
        収集した描画コマンドに基づいて色分けされたPDFを生成するのだ。
        """
        c = canvas.Canvas(output_filepath, pagesize=letter)

        for idx, page_areas in enumerate(all_page_areas):
            page_width, page_height = self.pdfplumber_analyzer.all_page_sizes[idx]
            c.setPageSize((page_width, page_height))

            for area_info in page_areas:
                color = area_info.color
                bbox_rl = area_info.rect
                
                c.setFillColor(color)
                c.rect(bbox_rl.x, bbox_rl.y, bbox_rl.width, bbox_rl.height, fill=1)

                # テキストブロックのIDを描画するのだ
                if area_info.block_id is not None:
                    c.setFillColor(black) # IDは黒で描画するのだ
                    c.setFont('Helvetica', 10) # フォントとサイズを設定するのだ
                    # ブロックの中央にIDを描画するのだ
                    text_x = bbox_rl.x + bbox_rl.width / 2
                    text_y = bbox_rl.y + bbox_rl.height / 2 - 5 # 少し上にずらすのだ
                    c.drawCentredString(text_x, text_y, str(area_info.block_id))
            
            c.showPage()
        
        c.save()
        return output_filepath

    def create_colored_pdf(self, input_pdf_path: str, output_pdf_path: str) -> str:
        """
        入力PDFのテキスト領域と図表領域を色分けして新しいPDFを生成する。
        """
        output_filepath = os.path.join(self.output_folder, os.path.basename(output_pdf_path))
        
        all_page_areas = self.extract_area_infos(input_pdf_path)
        return self._draw_colored_pdf(output_filepath, all_page_areas)
