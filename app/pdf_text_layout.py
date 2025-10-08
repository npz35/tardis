# Copyright 2025 npz35
#
# See the NOTICE file for this project for license details.
# This file may not be used except in accordance with the NOTICE.

import os
import logging
from typing import List, Dict, Any, Tuple
import re
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from app.config import Config


class PdfTextLayout:
    """PDF Text Layout Calculation and Drawing Class"""

    def __init__(self, font_path: str = Config.JAPANESE_FONT_PATH, min_font_size: float = 8.0, render_original_on_failure: bool = False):
        """
        Initialization

        Args:
            font_path: Path to the Japanese font
            min_font_size: Minimum font size for translated Japanese text
        """
        self.logger: logging.Logger = logging.getLogger(__name__)
        self.logger.debug(f"Function start: PdfTextLayout.__init__(font_path='{font_path}', min_font_size={min_font_size}, render_original_on_failure={render_original_on_failure})")
        self.font_path: str = font_path
        self.min_font_size: float = min_font_size
        self.render_original_on_failure: bool = render_original_on_failure
        self.japanese_font_name: str = "IPAexMincho" # A name for the registered font

        # Register Japanese font
        if not os.path.exists(self.font_path):
            error_msg: str = f"Japanese font not found at {self.font_path}"
            self.logger.error(error_msg)
            self.logger.debug("Function end: PdfTextLayout.__init__ (failed - font not found)")
            raise FileNotFoundError(error_msg)
        
        try:
            pdfmetrics.registerFont(TTFont(self.japanese_font_name, self.font_path))
            self.logger.info(f"Registered Japanese font: {self.japanese_font_name} from {self.font_path}")
        except Exception as e:
            error_msg: str = f"Failed to register Japanese font {self.font_path}: {e}"
            self.logger.error(error_msg)
            self.logger.debug("Function end: PdfTextLayout.__init__ (failed - font registration error)")
            raise RuntimeError(error_msg)
        self.logger.debug("Function end: PdfTextLayout.__init__ (success)")

    def calculate_text_lines(self, c: canvas.Canvas, text: str, max_width: float, font_size: float) -> List[str]:
        self.logger.debug(f"Function start: calculate_text_lines(text_len={len(text)}, max_width={max_width}, font_size={font_size})")
        """
        Splits text into lines based on max_width and font_size, considering Japanese character width.

        Args:
            text: The text to split.
            max_width: The maximum width available for the text.
            font_size: The font size to use for calculation.

        Returns:
            A list of strings, where each string is a line of text.
        """
        limit_width: float = max_width - Config.LINE_WIDTH_MARGIN

        self.logger.debug(f"Calculating text lines for text (len={len(text)}) with max_width={max_width}, limit_width={limit_width}, font_size={font_size}")
        draw_lines: List[str] = []
        current_line: str = ""
        current_line_width: float = 0.0

        # Estimate average character width (this is a simplification, ReportLab has better methods)
        # Japanese characters are typically wider than English characters at the same font size.
        # Config.JP_CHAR_WIDTH_FACTOR can be used here.
        # Set font for accurate width calculation
        c.setFont(self.japanese_font_name, font_size)

        words: List[str] = re.split(r'[ \n]+', text) # Split by space or newline

        for word in words:
            self.logger.debug(f"Processing word: '{word}'")
            word_width: float = c.stringWidth(word, self.japanese_font_name, font_size)

            # If the current word alone exceeds limit_width, it needs to be broken down
            if word_width > limit_width:
                self.logger.debug(f"Word '{word}' (width={word_width}) exceeds limit_width={limit_width}. Breaking down.")
                for char in word:
                    char_width: float = c.stringWidth(char, self.japanese_font_name, font_size)
                    if current_line_width + char_width > limit_width:
                        self.logger.debug(f"current_line : {current_line}")
                        self.logger.debug(f"char         : {char}")
                        self.logger.debug(f"{current_line_width} + {char_width} > {limit_width}")
                        self.logger.debug(f"Appending draw line: {current_line}")
                        draw_lines.append(current_line)
                        current_line = char
                        current_line_width = char_width
                    else:
                        current_line += char
                        current_line_width += char_width
            else: # Word fits within limit_width
                if current_line_width + word_width > limit_width:
                    self.logger.debug(f"{current_line_width} + {word_width} > {limit_width}")
                    self.logger.debug(f"Appending draw line: {current_line}")
                    draw_lines.append(current_line)
                    current_line = word
                    current_line_width = word_width
                else:
                    current_line += word
                    current_line_width += word_width

        if current_line:
            self.logger.debug(f"Appending draw line: {current_line}")
            draw_lines.append(current_line)
         
        self.logger.debug(f"Function end: calculate_text_lines (success) -> {len(draw_lines)} lines")
        return draw_lines

    def draw_translated_text(self, c: canvas.Canvas, translated_text: str, bbox: Tuple[float, float, float, float], font_info: Dict[str, Any]) -> None:
        self.logger.debug(f"Function start: draw_translated_text(translated_text_len={len(translated_text)}, bbox={bbox}, font_info={font_info})")
        """
        Draws translated text onto a ReportLab canvas within a specified bounding box.

        Args:
            c: The ReportLab canvas object.
            translated_text: The text to draw.
            bbox: The bounding box (x0, y0, x1, y1) for text placement.
            font_info: Dictionary containing font_size and font_name.
        """
        self.logger.info(f"Drawing translated text: '{translated_text[:50]}...' into bbox {bbox}")
        x0, y0, x1, y1 = bbox
        width = x1 - x0
        height = y1 - y0

        if width <= 0 or height <= 0:
            self.logger.error(f"Invalid bounding box dimensions: width={width}, height={height}")
            self.logger.debug("Function end: draw_translated_text (failed - invalid bbox)")
            raise ValueError("Invalid bounding box dimensions for drawing text.")

        font_size = font_info.get("font_size", 12.0)
        if font_size <= 0:
            self.logger.error(f"Invalid font size: {font_size}")
            self.logger.debug("Function end: draw_translated_text (failed - invalid font size)")
            raise ValueError("Invalid font size for drawing text.")

        # Adjust font size to fit
        optimal_font_size = self._adjust_font_size_to_fit(c, translated_text, width, height, font_size)
        
        c.setFont(self.japanese_font_name, optimal_font_size)
        
        if Config.ENABLE_FONT_COLOR_HIGHLIGHT:
            original_font_name = font_info.get("font_name", "default")
            # ex. 'XLDELO+CMMI10' -> 'CMMI10'
            display_font_name = original_font_name.split('+')[-1] if '+' in original_font_name else original_font_name
            
            color = Config.FONT_COLOR_MAP.get(display_font_name, Config.FONT_COLOR_MAP["default"])
            self.logger.debug(f"Setting font color for '{display_font_name}' to RGB{color}")
            c.setFillColorRGB(*color)
        else:
            c.setFillColorRGB(0, 0, 0) # Black text

        lines = self.calculate_text_lines(c, translated_text, width, optimal_font_size)
        line_height = optimal_font_size * Config.LINE_HEIGHT_FACTOR

        # Start from the top of the bbox, adjusting for ReportLab's y-origin (bottom-left)
        # and ensuring the first line's baseline is correctly positioned.
        # y1 is the top of the bbox. We want the baseline of the first line to be below y1.
        # A common approach is to subtract the font size itself, or a factor of it.
        current_y = y1 - optimal_font_size * Config.JP_CHAR_HEIGHT_FACTOR

        for line in lines:
            if current_y < y0: # Check if we are out of bounds
                self.logger.warning(f"Text line '{line}' exceeds bounding box height. Skipping.")
                break
            self.logger.debug(f"draw line: {line}")
            c.drawString(x0, current_y, line)
            current_y -= line_height
        self.logger.info(f"Finished drawing translated text. Final font size: {optimal_font_size}")
        self.logger.debug("Function end: draw_translated_text (success)")

    def _adjust_font_size_to_fit(self, c: canvas.Canvas, text: str, max_width: float, max_height: float, initial_font_size: float) -> float:
        self.logger.debug(f"Function start: _adjust_font_size_to_fit(text_len={len(text)}, max_width={max_width}, max_height={max_height}, initial_font_size={initial_font_size})")
        """
        Adjusts font size to ensure text fits within the given width and height.
        """
        current_font_size = initial_font_size
        for _ in range(10): # Try up to 10 iterations for adjustment
            # Temporarily set font for accurate width calculation
            c.setFont(self.japanese_font_name, current_font_size)
            lines = self.calculate_text_lines(c, text, max_width, current_font_size)
            total_text_height = len(lines) * (current_font_size * Config.LINE_HEIGHT_FACTOR)

            max_line_width = 0.0
            for line in lines:
                line_width = c.stringWidth(line, self.japanese_font_name, current_font_size)
                if line_width > max_line_width:
                    max_line_width = line_width

            if total_text_height > max_height or max_line_width > max_width:
                # Reduce font size
                height_ratio = max_height / total_text_height if total_text_height > 0 else 1
                width_ratio = max_width / max_line_width if max_line_width > 0 else 1
                
                adjustment_factor = min(height_ratio, width_ratio) * Config.ADJUST_SLIGHTLY_FACTOR
                current_font_size *= adjustment_factor
                current_font_size = max(self.min_font_size, current_font_size)
            else:
                break # Fits
        
        self.logger.debug(f"Function end: _adjust_font_size_to_fit (success) -> {current_font_size}")
        return current_font_size

    def draw_white_rectangle(self, c: canvas.Canvas, bbox: Tuple[float, float, float, float]) -> None:
        self.logger.debug(f"Function start: draw_white_rectangle(bbox={bbox})")
        """
        Draws a white rectangle onto a ReportLab canvas to cover original text.

        Args:
            c: The ReportLab canvas object.
            bbox: The bounding box (x0, y0, x1, y1) of the area to cover.
        """
        x0, y0, x1, y1 = bbox
        width = x1 - x0
        height = y1 - y0

        if width <= 0 or height <= 0:
            self.logger.warning(f"Invalid bounding box dimensions for drawing white rectangle: width={width}, height={height}. Skipping.")
            self.logger.debug("Function end: draw_white_rectangle (invalid bbox)")
            return

        c.setFillColorRGB(1, 1, 1) # White color
        c.rect(x0, y0, width, height, fill=1, stroke=0) # Fill with white, no border
        self.logger.debug(f"Drew white rectangle at {bbox}")
        self.logger.debug("Function end: draw_white_rectangle (success)")

    def rects_overlap(self, rect1: Tuple[float, float, float, float], rect2: Tuple[float, float, float, float]) -> bool:
        self.logger.debug(f"Function start: rects_overlap(rect1={rect1}, rect2={rect2})")
        """
        Determines if two rectangles overlap.

        Args:
            rect1: First rectangle (x0, y0, x1, y1).
            rect2: Second rectangle (x0, y0, x1, y1).

        Returns:
            True if the rectangles overlap, False otherwise.
        """
        # Check if rectangles overlap on X axis
        if rect1[2] < rect2[0] or rect2[2] < rect1[0]:
            self.logger.debug("Function end: rects_overlap (no overlap on X)")
            return False
        # Check if rectangles overlap on Y axis
        if rect1[3] < rect2[1] or rect2[3] < rect1[1]:
            self.logger.debug("Function end: rects_overlap (no overlap on Y)")
            return False
        is_overlap = True
        self.logger.debug(f"Function end: rects_overlap (success) -> {is_overlap}")
        return is_overlap

    def expand_bbox(self, bbox: Tuple[float, float, float, float]) -> Tuple[float, float, float, float]:
        self.logger.debug(f"Function start: expand_bbox(bbox={bbox})")
        """
        Expands a bounding box.

        Args:
            bbox: The original bounding box (x0, y0, x1, y1).

        Returns:
            The expanded bounding box.
        """
        x0, y0, x1, y1 = bbox
        expanded_bbox = (x0 - Config.BBOX_EXPAND_MARGIN, y0 - Config.BBOX_EXPAND_MARGIN, x1 + Config.BBOX_EXPAND_MARGIN, y1 + Config.BBOX_EXPAND_MARGIN)
        self.logger.debug(f"Function end: expand_bbox (success) -> {expanded_bbox}")
        return expanded_bbox
