# Copyright 2025 npz35
#
# See the NOTICE file for this project for license details.
# This file may not be used except in accordance with the NOTICE.

import pdfplumber
from pdfplumber.page import Page
from reportlab.pdfgen import canvas
from reportlab.lib.colors import red, blue
import os
import logging
from typing import List, Tuple, Dict, Any, Optional
from dataclasses import dataclass
from app.data_model import TextArea, TextBlock, Word, RightSideWord, WordsBorderGap, Line, PageAnalyzeData
from app.text.pdfplumber import PdfplumberAnalyzer


class PdfColumnSeparator:
    # Constants for column detection heuristics
    X_TOLERANCE = 3
    MIDDLE_PAGE_RANGE_FACTOR = 0.1
    PADDING_PAGE_RANGE_FACTOR = 0.2
    COLUMN_LINE_THRESHOLD_COUNT = 3 # Minimum number of consecutive two-column lines to confirm a two-column section
    COLUMN_LINE_HEIGHT_RATIO_THRESHOLD = 0.1 # Minimum height ratio of two-column lines to page height
    SINGLE_COLUMN_CONFIRM_RATIO = 0.95 # If 1-column lines cover this much of the page height, assume whole page is 1-column
    TWO_COLUMN_CONFIRM_RATIO = 0.95 # If 2-column lines cover this much of the page height, assume whole page is 2-column

    def __init__(self, output_folder: str):
        self.logger: logging.Logger = logging.getLogger(__name__)
        self.output_folder = output_folder
        os.makedirs(self.output_folder, exist_ok=True)
        self.pdfplumber_analyzer = PdfplumberAnalyzer()

    def _find_line_gaps(self, line_words: List[Word], middle_x: float, line_top: float, line_bottom: float) -> List[WordsBorderGap]:
        line_gaps: List[WordsBorderGap] = []
        for i in range(1, len(line_words)):
            words_gap = WordsBorderGap(
                left=line_words[i-1].right,
                right=line_words[i].left,
                top=line_top,
                bottom=line_bottom,
                right_side_word=RightSideWord(left=line_words[i].left, middle_x=middle_x, text=line_words[i].text)
            )

            self.logger.debug(f"words_gap.width() : {words_gap.width()}")

            if words_gap.is_valid(middle_x):
                line_gaps.append(words_gap)

        return line_gaps

    def _find_gaps_on_border_range(self, line_gaps: List[WordsBorderGap], middle_x: float, page_width: float) -> List[WordsBorderGap]:
        gaps_on_border_range: List[WordsBorderGap] = []
        for gap in line_gaps:
            self.logger.debug(f"is_valid       : {gap.is_valid(middle_x)}")
            self.logger.debug(f"on_border_range: {gap.on_border_range(page_width)}")

            if gap.is_valid(middle_x) and gap.on_border_range(page_width):
                gaps_on_border_range.append(gap)
                self.logger.debug(f"Detect gap {gap.width():.2f}, line_top: {gap.top:.2f}")

        return gaps_on_border_range

    def _draw_column_boundary(self, c: canvas.Canvas, closest_central_gap: WordsBorderGap, border_bottom: float, border_top: float):
        boundary_x = closest_central_gap.center_x()

        self.logger.debug(f"closest_central_gap.center_x            : {boundary_x:.2f}")
        self.logger.debug(f"closest_central_gap.width               : {closest_central_gap.width():.2f}")
        self.logger.debug(f"closest_central_gap.right_side_word.text: {closest_central_gap.right_side_word.text}")
        
        c.setStrokeColor(red)
        c.setLineWidth(1)
        # The origin is at the bottom left
        c.line(boundary_x, border_bottom, boundary_x, border_top)

    def _draw_page_number(self, c: canvas.Canvas, page_width: float, page_num: int):
        # Draw page number at bottom right
        c.setFont("Helvetica", 10)
        c.setFillColor(blue)
        # The origin is at the bottom left
        c.drawString(page_width - 50, 20, f"p{page_num + 1}")

    def _determine_border_position(self, page_height: float, upper_border_y: float, lower_border_y: float, page_num: int) -> Tuple[float, float]:
        border_top = page_height
        border_bottom = 0.0

        self.logger.info(f"Page {page_num + 1}: lower_border_y={lower_border_y:.2f}")
        self.logger.info(f"Page {page_num + 1}: upper_border_y={upper_border_y:.2f}")

        if 0.0 < lower_border_y and lower_border_y < upper_border_y and upper_border_y < page_height:
            # Both transitions found, draw in the middle
            border_top = upper_border_y
            border_bottom = lower_border_y
            self.logger.info(f"Page {page_num + 1}: Drawing boundary from y={border_top:.2f} to y={border_bottom:.2f} (both transitions).")
        elif 0.0 < upper_border_y:
            # Only 1-column to 2-column transition found, draw from transition to bottom
            border_top = upper_border_y
            border_bottom = 0.0
            self.logger.info(f"Page {page_num + 1}: Drawing boundary from y={border_top:.2f} to y={border_bottom:.2f} (1-to-2 transition).")
        elif lower_border_y < page_height:
            # Only 2-column to 1-column transition found, draw from top to transition
            border_top = page_height
            border_bottom = lower_border_y
            self.logger.info(f"Page {page_num + 1}: Drawing boundary from y={border_top:.2f} to y={border_bottom:.2f} (2-to-1 transition).")
        else:
            self.logger.info(f"Page {page_num + 1}: Mixed layout, but no clear transition point found for drawing.")
            return None, None # No clear transition, so no line drawn
        
        return border_top, border_bottom

    def _draw_gaps_as_blue_crosses(self, c: canvas.Canvas, all_gaps_on_border_range: List[WordsBorderGap]):
        """
        Draws blue crosses and center_y values for each gap in all_gaps_on_border_range.
        """
        c.setStrokeColor(blue)
        c.setLineWidth(0.5) # 細めの線にする
        for gap in all_gaps_on_border_range:
            center_x = gap.center_x()
            center_y = gap.center_y()
            cross_size = max(2, gap.width() / 4)

            self.logger.debug(f"gap (y,x)=({center_y:.2f}, {center_x:.2f}), right_side_word.text={gap.right_side_word.text}")

            # Draw center_y on left
            c.setFillColor(blue)
            c.setFont("Helvetica", 6)
            c.drawString(center_x - cross_size - 30, center_y - 2, f"y={center_y:.2f}")

            # The origin is at the bottom left
            c.line(center_x - cross_size, center_y - cross_size, center_x + cross_size, center_y + cross_size)
            c.line(center_x - cross_size, center_y + cross_size, center_x + cross_size, center_y - cross_size)

            # Draw gap.right_side_word.text on the right of the cross
            c.setFillColor(blue)
            c.setFont("Helvetica", 6)
            c.drawString(center_x + cross_size + 5, center_y - 2, gap.right_side_word.text)

    def _extract_all_gaps_on_border_range(self, pdf_path: str, lines: List[Line], bottom_y: float, top_y: float, page_number: int, page_width: float) -> List[WordsBorderGap]:
        middle_x = page_width / 2
        all_gaps_on_border_range: List[WordsBorderGap] = []
        for line in lines:
            # Only consider lines within the determined drawing range
            if not (bottom_y <= line.y0 and line.y1 <= top_y):
                continue

            # extract_textblockはpdf_pathとpage_numberを必要とするのだ
            # ここでは、元のページ番号を使用するのだ
            crop_page_text_blocks: List[TextBlock] = self.pdfplumber_analyzer.crop_textblock(pdf_path, page_number, line)

            if not crop_page_text_blocks:
                self.logger.warning(f'Page {page_number}: No crop_page_text_blocks')
                continue

            line_words: List[Word] = [Word(left=block.bbox.x0, right=block.bbox.x1, text=block.text) for block in crop_page_text_blocks]
            line_words.sort(key=lambda word: word.left) # Sort by left to ensure correct gap calculation
            line_gaps: List[WordsBorderGap] = self._find_line_gaps(line_words, middle_x, line.y1, line.y0)
            gaps_on_border_range: List[WordsBorderGap] = self._find_gaps_on_border_range(line_gaps, middle_x, page_width)

            self.logger.debug(f'Page {page_number}: line_words             : {line_words}')
            self.logger.debug(f'Page {page_number}: line_gaps              : {line_gaps}')
            self.logger.debug(f'Page {page_number}: gaps_on_border_range   : {gaps_on_border_range}')
            self.logger.debug(f"Page {page_number}: Line texts height range: {line.y0:.2f}~{line.y1:.2f}, texts {[w.text for w in line_words]}")

            all_gaps_on_border_range.extend(gaps_on_border_range)
        return all_gaps_on_border_range

    def _is_one_side(self, areas: TextArea, page_width: float, middle_x: float) -> bool:
        """
        Determines if a line is considered two-column based on its position being predominantly on one side of the page.
        This handles cases where text might only exist in the left or right half of the page.
        """
        line_width: float = areas.bbox.x1 - areas.bbox.x0
        one_side = line_width < page_width / 2

        x_padding: float = page_width * self.PADDING_PAGE_RANGE_FACTOR
        left_edge_on_left = areas.bbox.x0 - middle_x < x_padding
        right_edge_on_left = abs(middle_x - areas.bbox.x1) < page_width * self.MIDDLE_PAGE_RANGE_FACTOR
        left_edge_on_right = abs(areas.bbox.x0 - middle_x) < page_width * self.MIDDLE_PAGE_RANGE_FACTOR
        right_edge_on_right = page_width - areas.bbox.x1 < x_padding

        on_left = left_edge_on_left and right_edge_on_left
        on_right = left_edge_on_right and right_edge_on_right
        is_two_column = one_side and (on_left or on_right)

        self.logger.debug(f"Check one side")
        self.logger.debug(f"areas              : {areas}")
        self.logger.debug(f"left_edge_on_left  : {areas.bbox.x0 - middle_x:.2f} < {x_padding:.2f}")
        self.logger.debug(f"right_edge_on_left : {abs(middle_x - areas.bbox.x1):.2f} < {page_width * self.MIDDLE_PAGE_RANGE_FACTOR:.2f}")
        self.logger.debug(f"left_edge_on_right : {abs(areas.bbox.x0 - middle_x):.2f} < {page_width * self.MIDDLE_PAGE_RANGE_FACTOR:.2f}")
        self.logger.debug(f"right_edge_on_right: {page_width - areas.bbox.x1:.2f} < {x_padding:.2f}")
        self.logger.debug(f"one_side: {one_side}")
        self.logger.debug(f"on_left : {left_edge_on_left} and {right_edge_on_left}")
        self.logger.debug(f"on_right: {left_edge_on_right} and {right_edge_on_right}")

        return is_two_column

    def _analyze_line(self, areas: TextArea, page_width: float, page_height: float) -> Line:
        middle_x = page_width / 2
        line_top = page_height - areas.bbox.y1
        line_bottom = page_height - areas.bbox.y0
        result: Line = Line(y0=areas.bbox.y0, y1=areas.bbox.y1, x0=areas.bbox.x0, x1=areas.bbox.x1, top=line_top, bottom=line_bottom, is_two_column=False)

        if not areas.blocks:
            return result

        line_words: List[Word] = [Word(left=block.bbox.x0, right=block.bbox.x1, text=block.text) for block in areas.blocks]
        line_words.sort(key=lambda word: word.left) # Sort by left to ensure correct gap calculation
        line_gaps: List[WordsBorderGap] = self._find_line_gaps(line_words, middle_x, areas.bbox.y1, areas.bbox.y0)
        gaps_on_border_range: List[WordsBorderGap] = self._find_gaps_on_border_range(line_gaps, middle_x, page_width)

        self.logger.debug(f"Extract line from top={line_top:.2f} to bottom={line_bottom:.2f}")
        self.logger.debug(f"Analyze line from y0 ={result.y0:.2f} to y1    ={result.y1:.2f}: text={[w.text for w in line_words]}")
        
        is_two_column = False
        if gaps_on_border_range:
            right_side_words = [gap.right_side_word for gap in gaps_on_border_range]
            right_side_words.sort(key=lambda r: r.dist())
            is_two_column = right_side_words[0].on_border_range()
        else:
            is_two_column = self._is_one_side(areas, page_width, middle_x)

        result.is_two_column = is_two_column
        return result

    def _calculate_column_height_percentages(self, line_analysis_results: List[Line], total_column_height: float) -> Tuple[float, float]:
        """
        Calculates total heights for 1-column and 2-column lines and their percentages.
        """
        total_1_column_height = sum(r.height() for r in line_analysis_results if not r.is_two_column)
        total_2_column_height = sum(r.height() for r in line_analysis_results if r.is_two_column)

        self.logger.debug(f"Total column height  : {total_column_height:.2f}")
        self.logger.debug(f"Total 1-column height: {total_1_column_height:.2f}")
        self.logger.debug(f"Total 2-column height: {total_2_column_height:.2f}")

        per_1_column = total_1_column_height / total_column_height if total_column_height > 0 else 0.0
        per_2_column = total_2_column_height / total_column_height if total_column_height > 0 else 0.0

        return per_1_column, per_2_column

    def analyze_separation_lines(self, pdf_path: str) -> List[PageAnalyzeData]:
        analyze_pages_data: List[PageAnalyzeData] = []

        with pdfplumber.open(pdf_path) as pdf:
            all_page_sizes = self.pdfplumber_analyzer.extract_pazesizes(pdf_path)
            all_page_text_areas = self.pdfplumber_analyzer.extract_textareas(pdf_path)

            for page_num, page_text_areas in enumerate(all_page_text_areas):
                page_width, page_height = all_page_sizes[page_num]
                page_analyze_data = PageAnalyzeData(
                    page_num=page_num,
                    page_width=page_width,
                    page_height=page_height,
                    column_boundary_data=None,
                    blue_crosses_data=[]
                )

                self.logger.debug(f"Page {page_num + 1}: page width  {page_width:.2f}")
                self.logger.debug(f"Page {page_num + 1}: page height {page_height:.2f}")

                if not page_text_areas:
                    self.logger.warning(f"Page {page_num + 1}: No text areas found on page.")
                    analyze_pages_data.append(page_analyze_data)
                    continue

                self.logger.debug(f"Page {page_num + 1}: Extracted first text area    : {page_text_areas[0]}")
                self.logger.debug(f"Page {page_num + 1}: Extracted text areas text    : {[[block.text for block in area.blocks] for area in page_text_areas[:10]]} ...")
                self.logger.debug(f"Page {page_num + 1}: Extracted text areas y0      : {[f'{block.bbox.y0:.2f}' for block in page_text_areas[:10]]} ...")
                self.logger.debug(f"Page {page_num + 1}: Extracted text areas y1      : {[f'{block.bbox.y1:.2f}' for block in page_text_areas[:10]]} ...")
                
                line_analysis_results: List[Line] = []
                for areas in page_text_areas:
                    result: Line = self._analyze_line(areas, page_width, page_height)
                    line_analysis_results.append(result)
                    self.logger.debug(f"Page {page_num + 1}: Line from y={result.y0:.2f} to y={result.y1:.2f}: is_two_column={result.is_two_column}, text={[block.text for block in areas.blocks]}")

                total_column_height = sum(text_areas.bbox.height() for text_areas in page_text_areas)
                per_1_column, per_2_column = \
                    self._calculate_column_height_percentages(line_analysis_results, total_column_height)

                # Determine overall page layout
                if per_1_column >= self.SINGLE_COLUMN_CONFIRM_RATIO:
                    self.logger.info(f"Page {page_num + 1}: Detected as mostly single-column.")
                    # No boundary line for single column
                    analyze_pages_data.append(page_analyze_data)
                    continue

                if per_2_column >= self.TWO_COLUMN_CONFIRM_RATIO:
                    self.logger.info(f"Page {page_num + 1}: Detected as mostly two-column.")
                    # Draw boundary line across the entire page height
                    all_gaps_on_border_range = self._extract_all_gaps_on_border_range(
                        pdf_path, line_analysis_results, 0.0, page_height, page_num + 1, page_width
                    )

                    self.logger.info(f"Page {page_num + 1}: Detected full page two columns layout.")
                    if all_gaps_on_border_range:
                        middle_x = page_width / 2
                        all_gaps_on_border_range.sort(key=lambda gap: abs(gap.center_x() - middle_x))
                        closest_central_gap = all_gaps_on_border_range[0]
                        page_analyze_data.column_boundary_data = (closest_central_gap, 0, page_height)
                        page_analyze_data.blue_crosses_data.extend(all_gaps_on_border_range)
                        self.logger.info(f"Page {page_num + 1}: right_side_dists={[f'{w.right_side_word.dist():.2f}' for w in all_gaps_on_border_range]} .")
                        self.logger.info(f"Page {page_num + 1}: right_side_texts={[w.right_side_word.text for w in all_gaps_on_border_range]} .")
                    else:
                        self.logger.info(f"Page {page_num + 1}: No clear boundary found.")
                    analyze_pages_data.append(page_analyze_data)
                    continue

                self.logger.info(f"Page {page_num + 1}: Mixed column layout detected. Searching for transition point.")
                # Mixed layout: search for transition point
                upper_border_y = 0.0
                lower_border_y = page_height
                
                # Sort lines by top coordinate (from top to bottom)
                line_analysis_results.sort(key=lambda x: x.y1, reverse=True)

                # Search for 1-column to 2-column transition (top to bottom)
                consecutive_two_column_lines = 0
                current_two_column_height = 0.0
                for i, result in enumerate(line_analysis_results):
                    if result.is_two_column:
                        consecutive_two_column_lines += 1
                        current_two_column_height += result.height()
                        if consecutive_two_column_lines >= self.COLUMN_LINE_THRESHOLD_COUNT and \
                            current_two_column_height / total_column_height >= self.COLUMN_LINE_HEIGHT_RATIO_THRESHOLD:
                            # Found a sustained two-column section, set the start Y to the top of the first line in this section
                            block_tops = [line_analysis_results[j].y1 for j in range(i - consecutive_two_column_lines + 1, i + 1)]
                            upper_border_y = max(block_tops) # The lowest 'top' is the highest point of the block
                    else:
                        if consecutive_two_column_lines >= self.COLUMN_LINE_THRESHOLD_COUNT and \
                            current_two_column_height / total_column_height >= self.COLUMN_LINE_HEIGHT_RATIO_THRESHOLD:
                            self.logger.info(f"Page {page_num + 1}: consecutive_two_column_lines {consecutive_two_column_lines}")
                            self.logger.info(f"Page {page_num + 1}: current_two_column_height    {current_two_column_height:.2f}")
                            self.logger.info(f"Page {page_num + 1}: upper_border_y               {upper_border_y:.2f}")
                            break
                        consecutive_two_column_lines = 0
                        current_two_column_height = 0.0

                # Search for 2-column to 1-column transition (bottom to top)
                # Sort lines by bottom coordinate (from bottom to top)
                line_analysis_results.sort(key=lambda x: x.y0)

                consecutive_one_column_lines = 0
                current_one_column_height = 0.0
                for i, result in enumerate(line_analysis_results):
                    if not result.is_two_column:
                        consecutive_one_column_lines += 1
                        current_one_column_height += result.height()
                        if consecutive_one_column_lines >= self.COLUMN_LINE_THRESHOLD_COUNT and \
                            current_one_column_height / total_column_height >= self.COLUMN_LINE_HEIGHT_RATIO_THRESHOLD:
                            # Found a sustained one-column section, set the end Y to the bottom of the last line in this section
                            block_bottoms = [line_analysis_results[j].y0 for j in range(i - consecutive_one_column_lines + 1, i + 1)]
                            lower_border_y = max(block_bottoms) # The highest 'bottom' is the lowest point of the block
                    else:
                        if consecutive_one_column_lines >= self.COLUMN_LINE_THRESHOLD_COUNT and \
                            current_one_column_height / total_column_height >= self.COLUMN_LINE_HEIGHT_RATIO_THRESHOLD:
                            self.logger.info(f"Page {page_num + 1}: consecutive_one_column_lines {consecutive_one_column_lines}")
                            self.logger.info(f"Page {page_num + 1}: current_one_column_height    {current_one_column_height:.2f}")
                            self.logger.info(f"Page {page_num + 1}: lower_border_y               {lower_border_y:.2f}")
                            break
                        consecutive_one_column_lines = 0
                        current_one_column_height = 0.0

                self.logger.info(f"Page {page_num + 1}: 1-column to 2-column transition detected at y={upper_border_y:.2f}")
                self.logger.info(f"Page {page_num + 1}: 2-column to 1-column transition detected at y={lower_border_y:.2f}")

                border_top, border_bottom = self._determine_border_position(page_height, upper_border_y, lower_border_y, page_num)
                if border_top is None or border_bottom is None: # No clear transition, so no line drawn
                    analyze_pages_data.append(page_analyze_data)
                    continue

                all_gaps_on_border_range = self._extract_all_gaps_on_border_range(
                    pdf_path, line_analysis_results, border_bottom, border_top, page_num + 1, page_width
                )
                
                self.logger.info(f"Page {page_num + 1}: Detected mixed columns layout.")
                self.logger.info(f"Page {page_num + 1}: Boundary from y={border_bottom:.2f} to y={border_top:.2f}")
                self.logger.info(f"Page {page_num + 1}: all_gaps_on_border_range size: {len(all_gaps_on_border_range)}")
                if all_gaps_on_border_range:
                    middle_x = page_width / 2
                    all_gaps_on_border_range.sort(key=lambda gap: abs(gap.center_x() - middle_x))
                    closest_central_gap = all_gaps_on_border_range[0]
                    page_analyze_data.column_boundary_data = (closest_central_gap, border_bottom, border_top)
                    page_analyze_data.blue_crosses_data.extend(all_gaps_on_border_range)
                    self.logger.info(f"Page {page_num + 1}: right_side_dists={[f'{w.right_side_word.dist():.2f}' for w in all_gaps_on_border_range]} .")
                    self.logger.info(f"Page {page_num + 1}: right_side_texts={[w.right_side_word.text for w in all_gaps_on_border_range]} .")
                else:
                    self.logger.info(f"Page {page_num + 1}: No clear boundary found.")

                analyze_pages_data.append(page_analyze_data)
        return analyze_pages_data

    def draw_separation_lines(self, analyze_pages_data: List[PageAnalyzeData], output_filename: str) -> str:
        output_path = os.path.join(self.output_folder, output_filename)
        c: canvas.Canvas = None
        for page_analyze_data in analyze_pages_data:
            if page_analyze_data.page_num == 0:
                c = canvas.Canvas(output_path, pagesize=(page_analyze_data.page_width, page_analyze_data.page_height))
            else:
                c.showPage()
                c.setPageSize((page_analyze_data.page_width, page_analyze_data.page_height)) # Set page size for subsequent pages

            # Draw page number
            self._draw_page_number(c, page_analyze_data.page_width, page_analyze_data.page_num)

            # Draw column boundaries
            if page_analyze_data.column_boundary_data:
                closest_central_gap, border_bottom, border_top = page_analyze_data.column_boundary_data
                self._draw_column_boundary(c, closest_central_gap, border_bottom, border_top)
            
            # Draw blue crosses
            self._draw_gaps_as_blue_crosses(c, page_analyze_data.blue_crosses_data)

        if c:
            c.save()
        return output_path
