# Copyright 2025 npz35
#
# See the NOTICE file for this project for license details.
# This file may not be used except in accordance with the NOTICE.

from reportlab.pdfgen import canvas
from reportlab.lib.colors import red, blue
import os
import logging
from app.config import Config
from app.data_model import TextArea, TextBlock, Word, RightSideWord, WordsBorderGap, ColumnType, PageAnalyzeData
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

    def __init__(self):
        self.logger: logging.Logger = logging.getLogger(__name__)
        self.pdfplumber_analyzer = PdfplumberAnalyzer()

    def _find_valid_gaps(self, words_in_line: list[Word], middle_x: float, line_top: float, line_bottom: float) -> list[WordsBorderGap]:
        gaps_in_line: list[WordsBorderGap] = []
        for i in range(1, len(words_in_line)):
            gaps_in_line.append(
                WordsBorderGap(
                    left=words_in_line[i-1].right,
                    right=words_in_line[i].left,
                    top=line_top,
                    bottom=line_bottom,
                    right_side_word=RightSideWord(left=words_in_line[i].left, middle_x=middle_x, text=words_in_line[i].text)
                )
            )

        valid_gaps_in_line: list[WordsBorderGap] = [gaps for gaps in gaps_in_line if gaps.is_valid(middle_x)]

        self.logger.debug(f"gap width in gaps_in_line        : {[f'{gaps.width():.2f}' for gaps in gaps_in_line]}")
        self.logger.debug(f"gap width in valid_gaps_in_line  : {[f'{gaps.width():.2f}' for gaps in valid_gaps_in_line]}")

        return valid_gaps_in_line

    def _filter_gaps_on_border_range(self, valid_gaps_in_line: list[WordsBorderGap], page_width: float) -> list[WordsBorderGap]:
        gaps_on_border_range: list[WordsBorderGap] = [gaps for gaps in valid_gaps_in_line if gaps.on_border_range(page_width)]
        self.logger.debug(f"gap width in gaps_on_border_range: {[f'{gaps.width():.2f}' for gaps in gaps_on_border_range]}")
        self.logger.debug(f"gap top in gaps_on_border_range  : {[f'{gaps.top:.2f}' for gaps in gaps_on_border_range]}")

        return gaps_on_border_range

    def _draw_column_boundary(self, c: canvas.Canvas, closest_central_gap: WordsBorderGap, border_bottom: float, border_top: float):
        boundary_x = closest_central_gap.center_x()

        self.logger.debug(f'closest_central_gap.center_x            : {boundary_x:.2f}')
        self.logger.debug(f'closest_central_gap.width               : {closest_central_gap.width():.2f}')
        self.logger.debug(f'closest_central_gap.right_side_word.text: {closest_central_gap.right_side_word.text}')
        
        c.setStrokeColor(red)
        c.setLineWidth(1)
        # The origin is at the bottom left
        c.line(boundary_x, border_bottom, boundary_x, border_top)

    def _draw_page_number(self, c: canvas.Canvas, page_width: float, page_idx: int):
        # Draw page number at bottom right
        c.setFont('Helvetica', 10)
        c.setFillColor(blue)
        # The origin is at the bottom left
        c.drawString(page_width - 50, 20, f'p{page_idx + 1}')

    def _determine_border_position(self, page_height: float, upper_border_y: float, lower_border_y: float, page_idx: int) -> tuple[float, float]:
        border_top = page_height
        border_bottom = 0.0

        self.logger.info(f'Page {page_idx + 1}: lower_border_y={lower_border_y:.2f}')
        self.logger.info(f'Page {page_idx + 1}: upper_border_y={upper_border_y:.2f}')

        if 0.0 < lower_border_y and lower_border_y < upper_border_y and upper_border_y < page_height:
            # Both transitions found, draw in the middle
            border_top = upper_border_y
            border_bottom = lower_border_y
            self.logger.info(f'Page {page_idx + 1}: Drawing boundary from y={border_top:.2f} to y={border_bottom:.2f} (both transitions).')
        elif 0.0 < upper_border_y:
            # Only 1-column to 2-column transition found, draw from transition to bottom
            border_top = upper_border_y
            border_bottom = 0.0
            self.logger.info(f'Page {page_idx + 1}: Drawing boundary from y={border_top:.2f} to y={border_bottom:.2f} (1-to-2 transition).')
        elif lower_border_y < page_height:
            # Only 2-column to 1-column transition found, draw from top to transition
            border_top = page_height
            border_bottom = lower_border_y
            self.logger.info(f'Page {page_idx + 1}: Drawing boundary from y={border_top:.2f} to y={border_bottom:.2f} (2-to-1 transition).')
        else:
            self.logger.info(f'Page {page_idx + 1}: Mixed layout, but no clear transition point found for drawing.')
            return None, None # No clear transition, so no line drawn
        
        return border_top, border_bottom

    def _draw_gaps_as_blue_crosses(self, c: canvas.Canvas, all_gaps_on_border_range: list[WordsBorderGap]):
        '''
        Draws blue crosses and center_y values for each gap in all_gaps_on_border_range.
        '''
        c.setStrokeColor(blue)
        c.setLineWidth(0.5) # 細めの線にする
        for gap in all_gaps_on_border_range:
            center_x = gap.center_x()
            center_y = gap.center_y()
            cross_size = max(2, gap.width() / 4)

            self.logger.debug(f'gap (y,x)=({center_y:.2f}, {center_x:.2f}), right_side_word.text={gap.right_side_word.text}')

            # Draw center_y on left
            c.setFillColor(blue)
            c.setFont('Helvetica', 6)
            c.drawString(center_x - cross_size - 30, center_y - 2, f'y={center_y:.2f}')

            # The origin is at the bottom left
            c.line(center_x - cross_size, center_y - cross_size, center_x + cross_size, center_y + cross_size)
            c.line(center_x - cross_size, center_y + cross_size, center_x + cross_size, center_y - cross_size)

            # Draw gap.right_side_word.text on the right of the cross
            c.setFillColor(blue)
            c.setFont('Helvetica', 6)
            c.drawString(center_x + cross_size + 5, center_y - 2, gap.right_side_word.text)

    def _extract_all_gaps_on_border_range(self, pdf_path: str, lines: list[ColumnType], bottom_y: float, top_y: float, page_number: int, page_width: float) -> list[WordsBorderGap]:
        middle_x = page_width / 2
        all_gaps_on_border_range: list[WordsBorderGap] = []
        for line in lines:
            # Only consider lines within the determined drawing range
            if not (bottom_y <= line.bbox.y0 and line.bbox.y1 <= top_y):
                continue

            # extract_textblockはpdf_pathとpage_numberを必要とするのだ
            # ここでは、元のページ番号を使用するのだ
            crop_page_text_blocks: list[TextBlock] = self.pdfplumber_analyzer.crop_textblock(pdf_path, page_number, line)

            if not crop_page_text_blocks:
                self.logger.warning(f'Page {page_number}: No crop_page_text_blocks')
                continue

            words_in_line: list[Word] = [Word(left=block.bbox.x0, right=block.bbox.x1, text=block.text) for block in crop_page_text_blocks]
            words_in_line.sort(key=lambda word: word.left) # Sort by left to ensure correct gap calculation
            valid_gaps_in_line: list[WordsBorderGap] = self._find_valid_gaps(words_in_line, middle_x, line.bbox.y1, line.bbox.y0)
            gaps_on_border_range: list[WordsBorderGap] = self._filter_gaps_on_border_range(valid_gaps_in_line, page_width)

            self.logger.debug(f'Page {page_number}: Extract gaps from y0={line.bbox.y0:.2f} to y1={line.bbox.y1:.2f}')
            self.logger.debug(f'Page {page_number}: text                   : {[w.text for w in words_in_line]}')
            self.logger.debug(f'Page {page_number}: words_in_line          : {words_in_line}')
            self.logger.debug(f'Page {page_number}: valid_gaps_in_line     : {valid_gaps_in_line}')
            self.logger.debug(f'Page {page_number}: gaps_on_border_range   : {gaps_on_border_range}')
            self.logger.debug(f'Page {page_number}: Line texts height range: {line.bbox.y0:.2f}~{line.bbox.y1:.2f}')

            all_gaps_on_border_range.extend(gaps_on_border_range)

        return all_gaps_on_border_range

    def _is_one_side(self, areas: TextArea, page_width: float, middle_x: float) -> bool:
        '''
        Determines if a line is considered two-column based on its position being predominantly on one side of the page.
        This handles cases where text might only exist in the left or right half of the page.
        '''
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

        self.logger.debug(f'Check one side')
        self.logger.debug(f'areas              : {areas}')
        self.logger.debug(f'left_edge_on_left  : {areas.bbox.x0 - middle_x:.2f} < {x_padding:.2f}')
        self.logger.debug(f'right_edge_on_left : {abs(middle_x - areas.bbox.x1):.2f} < {page_width * self.MIDDLE_PAGE_RANGE_FACTOR:.2f}')
        self.logger.debug(f'left_edge_on_right : {abs(areas.bbox.x0 - middle_x):.2f} < {page_width * self.MIDDLE_PAGE_RANGE_FACTOR:.2f}')
        self.logger.debug(f'right_edge_on_right: {page_width - areas.bbox.x1:.2f} < {x_padding:.2f}')
        self.logger.debug(f'one_side: {one_side}')
        self.logger.debug(f'on_left : {left_edge_on_left} and {right_edge_on_left}')
        self.logger.debug(f'on_right: {left_edge_on_right} and {right_edge_on_right}')

        return is_two_column

    def _analyze_line(self, areas: TextArea, page_width: float, page_height: float) -> ColumnType:
        middle_x = page_width / 2
        result: ColumnType = ColumnType(bbox=areas.bbox, page_height=page_height, is_two_column=False)

        if not areas.blocks:
            return result

        words_in_line: list[Word] = [Word(left=block.bbox.x0, right=block.bbox.x1, text=block.text) for block in areas.blocks]
        words_in_line.sort(key=lambda word: word.left) # Sort by left to ensure correct gap calculation
        valid_gaps_in_line: list[WordsBorderGap] = self._find_valid_gaps(words_in_line, middle_x, areas.bbox.y1, areas.bbox.y0)
        gaps_on_border_range: list[WordsBorderGap] = self._filter_gaps_on_border_range(valid_gaps_in_line, page_width)

        self.logger.debug(f'Analyze line from y0={result.bbox.y0:.2f} to y1={result.bbox.y1:.2f}')
        self.logger.debug(f'text                   : {[w.text for w in words_in_line]}')
        self.logger.debug(f'words_in_line          : {words_in_line}')
        self.logger.debug(f'valid_gaps_in_line     : {valid_gaps_in_line}')
        self.logger.debug(f'gaps_on_border_range   : {gaps_on_border_range}')
        self.logger.debug(f'Line texts height range: {result.bottom():.2f}~{result.top():.2f}')
        
        is_two_column = False
        if gaps_on_border_range:
            right_side_words = [gap.right_side_word for gap in gaps_on_border_range]
            right_side_words.sort(key=lambda r: r.dist())
            closest_right_side_word = right_side_words[0]
            is_two_column = closest_right_side_word.on_border_range()
        else:
            is_two_column = self._is_one_side(areas, page_width, middle_x)

        result.is_two_column = is_two_column
        return result

    def _calculate_column_height_percentages(self, column_types: list[ColumnType], total_column_height: float) -> tuple[float, float]:
        '''
        Calculates total heights for 1-column and 2-column lines and their percentages.
        '''
        total_1_column_height = sum(r.height() for r in column_types if not r.is_two_column)
        total_2_column_height = sum(r.height() for r in column_types if r.is_two_column)

        self.logger.debug(f'Total column height  : {total_column_height:.2f}')
        self.logger.debug(f'Total 1-column height: {total_1_column_height:.2f}')
        self.logger.debug(f'Total 2-column height: {total_2_column_height:.2f}')

        per_1_column = total_1_column_height / total_column_height if total_column_height > 0 else 0.0
        per_2_column = total_2_column_height / total_column_height if total_column_height > 0 else 0.0

        return per_1_column, per_2_column

    def analyze_separation_lines(self, pdf_path: str) -> list[PageAnalyzeData]:
        analyze_pages_data: list[PageAnalyzeData] = []

        all_page_sizes = self.pdfplumber_analyzer.extract_pazesizes(pdf_path)
        all_page_text_areas = self.pdfplumber_analyzer.extract_textareas(pdf_path)

        for page_idx, page_text_areas in enumerate(all_page_text_areas):
            if Config.MAX_PDF_PAGES <= page_idx:
                break

            page_width, page_height = all_page_sizes[page_idx]
            page_analyze_data = PageAnalyzeData(
                page_idx=page_idx,
                page_width=page_width,
                page_height=page_height,
                column_boundary_data=None,
                blue_crosses_data=[]
            )

            self.logger.debug(f'Page {page_idx + 1}: page width  {page_width:.2f}')
            self.logger.debug(f'Page {page_idx + 1}: page height {page_height:.2f}')

            if not page_text_areas:
                self.logger.warning(f'Page {page_idx + 1}: No text areas found on page.')
                analyze_pages_data.append(page_analyze_data)
                continue

            self.logger.debug(f'Page {page_idx + 1}: First text area         : {page_text_areas[0]}')
            self.logger.debug(f'Page {page_idx + 1}: First 10 text areas text: {[[block.text for block in area.blocks] for area in page_text_areas[:10]]} ...')
            self.logger.debug(f"Page {page_idx + 1}: First 10 text areas y0  : {[f'{block.bbox.y0:.2f}' for block in page_text_areas[:10]]} ...")
            self.logger.debug(f"Page {page_idx + 1}: First 10 text areas y1  : {[f'{block.bbox.y1:.2f}' for block in page_text_areas[:10]]} ...")
            
            column_types: list[ColumnType] = []
            for areas in page_text_areas:
                result: ColumnType = self._analyze_line(areas, page_width, page_height)
                column_types.append(result)
                self.logger.debug(f'Page {page_idx + 1}: ColumnType: {result}')
                self.logger.debug(f'Page {page_idx + 1}: Area text : {[block.text for block in areas.blocks]}')

            total_column_height = sum(text_areas.bbox.height() for text_areas in page_text_areas)
            per_1_column, per_2_column = \
                self._calculate_column_height_percentages(column_types, total_column_height)

            # Determine overall page layout
            if per_1_column >= self.SINGLE_COLUMN_CONFIRM_RATIO:
                self.logger.info(f'Page {page_idx + 1}: Detected as mostly single-column.')
                # No boundary line for single column
                analyze_pages_data.append(page_analyze_data)
                continue

            if per_2_column >= self.TWO_COLUMN_CONFIRM_RATIO:
                self.logger.info(f'Page {page_idx + 1}: Detected as mostly two-column.')
                # Draw boundary line across the entire page height
                all_gaps_on_border_range = self._extract_all_gaps_on_border_range(
                    pdf_path, column_types, 0.0, page_height, page_idx + 1, page_width
                )

                self.logger.info(f'Page {page_idx + 1}: Detected full page two columns layout.')
                if all_gaps_on_border_range:
                    all_gaps_on_border_range.sort(key=lambda gap: gap.distance_from_center(page_width))
                    closest_central_gap = all_gaps_on_border_range[0]
                    page_analyze_data.column_boundary_data = (closest_central_gap, 0, page_height)
                    page_analyze_data.blue_crosses_data.extend(all_gaps_on_border_range)
                    self.logger.info(f'Page {page_idx + 1}: all_gaps_on_border_range: {all_gaps_on_border_range}')
                    self.logger.info(f'Page {page_idx + 1}: closest_central_gap     : {closest_central_gap}')
                else:
                    self.logger.info(f'Page {page_idx + 1}: No clear boundary found.')
                analyze_pages_data.append(page_analyze_data)
                continue

            self.logger.info(f'Page {page_idx + 1}: Mixed column layout detected. Searching for transition point.')
            # Mixed layout: search for transition point
            upper_border_y = 0.0
            lower_border_y = page_height
            
            # Sort lines by top coordinate (from top to bottom)
            column_types.sort(key=lambda x: x.bbox.y1, reverse=True)

            # Search for 1-column to 2-column transition (top to bottom)
            consecutive_two_column_lines = 0
            current_two_column_height = 0.0
            for i, result in enumerate(column_types):
                if result.is_two_column:
                    consecutive_two_column_lines += 1
                    current_two_column_height += result.height()
                    if consecutive_two_column_lines >= self.COLUMN_LINE_THRESHOLD_COUNT and \
                        current_two_column_height / total_column_height >= self.COLUMN_LINE_HEIGHT_RATIO_THRESHOLD:
                        # Found a sustained two-column section, set the start Y to the top of the first line in this section
                        block_tops = [column_types[j].bbox.y1 for j in range(i - consecutive_two_column_lines + 1, i + 1)]
                        upper_border_y = max(block_tops) # The lowest 'top' is the highest point of the block
                else:
                    if consecutive_two_column_lines >= self.COLUMN_LINE_THRESHOLD_COUNT and \
                        current_two_column_height / total_column_height >= self.COLUMN_LINE_HEIGHT_RATIO_THRESHOLD:
                        self.logger.info(f'Page {page_idx + 1}: consecutive_two_column_lines {consecutive_two_column_lines}')
                        self.logger.info(f'Page {page_idx + 1}: current_two_column_height    {current_two_column_height:.2f}')
                        self.logger.info(f'Page {page_idx + 1}: upper_border_y               {upper_border_y:.2f}')
                        break
                    consecutive_two_column_lines = 0
                    current_two_column_height = 0.0

            # Search for 2-column to 1-column transition (bottom to top)
            # Sort lines by bottom coordinate (from bottom to top)
            column_types.sort(key=lambda x: x.bbox.y0)

            consecutive_one_column_lines = 0
            current_one_column_height = 0.0
            for i, result in enumerate(column_types):
                if not result.is_two_column:
                    consecutive_one_column_lines += 1
                    current_one_column_height += result.height()
                    if consecutive_one_column_lines >= self.COLUMN_LINE_THRESHOLD_COUNT and \
                        current_one_column_height / total_column_height >= self.COLUMN_LINE_HEIGHT_RATIO_THRESHOLD:
                        # Found a sustained one-column section, set the end Y to the bottom of the last line in this section
                        block_bottoms = [column_types[j].bbox.y0 for j in range(i - consecutive_one_column_lines + 1, i + 1)]
                        lower_border_y = max(block_bottoms) # The highest 'bottom' is the lowest point of the block
                else:
                    if consecutive_one_column_lines >= self.COLUMN_LINE_THRESHOLD_COUNT and \
                        current_one_column_height / total_column_height >= self.COLUMN_LINE_HEIGHT_RATIO_THRESHOLD:
                        self.logger.info(f'Page {page_idx + 1}: consecutive_one_column_lines {consecutive_one_column_lines}')
                        self.logger.info(f'Page {page_idx + 1}: current_one_column_height    {current_one_column_height:.2f}')
                        self.logger.info(f'Page {page_idx + 1}: lower_border_y               {lower_border_y:.2f}')
                        break
                    consecutive_one_column_lines = 0
                    current_one_column_height = 0.0

            self.logger.info(f'Page {page_idx + 1}: 1-column to 2-column transition detected at y={upper_border_y:.2f}')
            self.logger.info(f'Page {page_idx + 1}: 2-column to 1-column transition detected at y={lower_border_y:.2f}')

            border_top, border_bottom = self._determine_border_position(page_height, upper_border_y, lower_border_y, page_idx)
            if border_top is None or border_bottom is None: # No clear transition, so no line drawn
                analyze_pages_data.append(page_analyze_data)
                continue

            all_gaps_on_border_range = self._extract_all_gaps_on_border_range(
                pdf_path, column_types, border_bottom, border_top, page_idx + 1, page_width
            )
            
            self.logger.info(f'Page {page_idx + 1}: Detected mixed columns layout.')
            self.logger.info(f'Page {page_idx + 1}: Boundary from y={border_bottom:.2f} to y={border_top:.2f}')
            self.logger.info(f'Page {page_idx + 1}: all_gaps_on_border_range size: {len(all_gaps_on_border_range)}')
            if all_gaps_on_border_range:
                middle_x = page_width / 2
                all_gaps_on_border_range.sort(key=lambda gap: abs(gap.center_x() - middle_x))
                closest_central_gap = all_gaps_on_border_range[0]
                page_analyze_data.column_boundary_data = (closest_central_gap, border_bottom, border_top)
                page_analyze_data.blue_crosses_data.extend(all_gaps_on_border_range)
                self.logger.info(f"Page {page_idx + 1}: right_side_dists={[f'{w.right_side_word.dist():.2f}' for w in all_gaps_on_border_range]} .")
                self.logger.info(f'Page {page_idx + 1}: right_side_texts={[w.right_side_word.text for w in all_gaps_on_border_range]} .')
            else:
                self.logger.info(f'Page {page_idx + 1}: No clear boundary found.')

            analyze_pages_data.append(page_analyze_data)
        return analyze_pages_data

    def draw_separation_lines(self, analyze_pages_data: list[PageAnalyzeData], output_path: str):
        c: canvas.Canvas = None
        for page_analyze_data in analyze_pages_data:
            if page_analyze_data.page_idx == 0:
                c = canvas.Canvas(output_path, pagesize=(page_analyze_data.page_width, page_analyze_data.page_height))
            else:
                c.showPage()
                c.setPageSize((page_analyze_data.page_width, page_analyze_data.page_height)) # Set page size for subsequent pages

            # Draw page number
            self._draw_page_number(c, page_analyze_data.page_width, page_analyze_data.page_idx)

            # Draw column boundaries
            if page_analyze_data.column_boundary_data:
                closest_central_gap, border_bottom, border_top = page_analyze_data.column_boundary_data
                self._draw_column_boundary(c, closest_central_gap, border_bottom, border_top)
            
            # Draw blue crosses
            self._draw_gaps_as_blue_crosses(c, page_analyze_data.blue_crosses_data)

        if c:
            c.save()
