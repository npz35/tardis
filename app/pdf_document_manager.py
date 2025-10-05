# Copyright 2025 npz35
#
# See the NOTICE file for this project for license details.
# This file may not be used except in accordance with the NOTICE.

import logging
import os
import time
import traceback
from typing import List, Dict, Any, Tuple
import pypdf
from reportlab.pdfgen import canvas
from io import BytesIO

from app.pdf_text_manager import PdfTextManager
from app.pdf_text_layout import PdfTextLayout
from app.config import Config

class PdfDocumentManager:
    """PDF Document Management Class"""

    def __init__(self):
        self.logger: logging.Logger = logging.getLogger(__name__)
        self.logger.debug("Function start: PdfDocumentManager.__init__()")
        """
        Initialization
        """
        self.pdf_text_manager = PdfTextManager()
        self.pdf_text_layout = PdfTextLayout()
        self.logger.debug("Function end: PdfDocumentManager.__init__ (success)")

    def create_translated_pdf(self, original_pdf_path: str,
                            output_path: str,
                            translator: Any, # Use Any for now, will refine later
                            temp_filename: str) -> Tuple[str, float, List[Dict[str, Any]]]:
        self.logger.debug(f"Function start: create_translated_pdf(original_pdf_path='{original_pdf_path}', output_path='{output_path}', temp_filename='{temp_filename}')")
        """
        Create a translated PDF using alternative libraries (pdfminer.six, pypdf, ReportLab)

        Args:
            original_pdf_path: Path to the original PDF file
            translated_units: List of translated units
            output_path: Path for output

        Returns:
            True if successful
        """
        try:
            self.logger.info(f"Starting PDF translation process for {original_pdf_path} using alternative libraries.")

            # 1. Check if input file exists
            if not os.path.exists(original_pdf_path):
                error_msg: str = f"Original PDF file not found: {original_pdf_path}"
                self.logger.error(error_msg)
                self.logger.debug("Function end: create_translated_pdf (failed - file not found)")
                raise FileNotFoundError(error_msg)

            # 2. Check if output directory exists, create if not
            output_dir: str = os.path.dirname(output_path)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)
                self.logger.info(f"Created output directory: {output_dir}")

            # 3. Extract text with positions using pdfminer.six
            extracted_text_data = self.pdf_text_manager.extract_text_with_positions(original_pdf_path)
            self.logger.debug(f"Extracted {len(extracted_text_data)} text elements from original PDF.")

            # Convert extracted_text_data to the format expected by _combine_text_blocks
            formatted_extracted_data: List[Dict[str, Any]] = []
            for item in extracted_text_data:
                formatted_extracted_data.append({
                    "page": item["page_number"] - 1, # pdfminer page_number is 1-based, _combine_text_blocks expects 0-based
                    "bbox": item["bbox"],
                    "block_type": "text",
                    "text": item["text"],
                    "font_size": item.get("font_size", 12.0), # Use extracted font size, default to 12.0
                    "font_name": item.get("font_name", "Helvetica"), # Use extracted font name, default to Helvetica
                    "is_bold": item.get("is_bold", False),
                    "is_italic": item.get("is_italic", False)
                })

            # 4. Combine extracted text into translation units (similar to PdfProcessor.combine_text_blocks)
            translation_units: List[Dict[str, Any]] = self._combine_text_blocks(formatted_extracted_data)
            self.logger.info(f"Combined {len(translation_units)} translation units.")

            # 5. Translate text
            translated_units: List[Dict[str, Any]] = []
            for i, unit in enumerate(translation_units):
                self.logger.debug(f"Translating unit {i+1}/{len(translation_units)}")
                translation_result: Dict[str, Any] = translator.translate_text(
                    unit['text'],
                    pdf_filename=temp_filename,
                    page_number=unit['blocks'][0]['page'],
                    block_id=str(unit['blocks'][0]['bbox'])
                )

                if translation_result.get("success"):
                    # Convert the unit to the format expected by the PDF drawing logic
                    translated_unit = {
                        'original': {
                            'blocks': [{
                                'page': unit['page'], # Use the page number from the combined unit
                                'bbox': unit['bbox'], # Use the combined bbox
                                'font_info': unit['font_info']
                            }]
                        },
                        'translated': translation_result
                    }
                    self.logger.debug(f"Appending translated unit: {translated_unit}")
                    translated_units.append(translated_unit)
                else:
                    error_msg_from_translator: str = translation_result.get("error", "Unknown translation error")
                    self.logger.error(f"Translation error for unit {i}: {error_msg_from_translator}")
                    self.logger.error(f"Original text: {unit['text']}")
                    self.logger.debug("Function end: create_translated_pdf (failed - translation error)")
                    raise Exception(f"Translation failed: {error_msg_from_translator}")

            self.logger.info(f"Translated {len(translated_units)} units.")

            # 6. Create a transparent PDF with translated text using ReportLab
            output_pdf_writer = pypdf.PdfWriter()
            original_pdf_reader = pypdf.PdfReader(original_pdf_path)
            num_pages = len(original_pdf_reader.pages)

            for page_num in range(num_pages):
                original_page = original_pdf_reader.pages[page_num]
                page_width = original_page.mediabox.width
                page_height = original_page.mediabox.height

                # Create a new BytesIO and ReportLab canvas for each page
                translated_text_buffer_page = BytesIO()
                reportlab_canvas_page = canvas.Canvas(translated_text_buffer_page, pagesize=(page_width, page_height))
                
                page_units = [unit for unit in translated_units if unit["original"]["blocks"][0]["page"] == page_num]

                for unit in page_units:
                    bbox = unit["original"]["blocks"][0]["bbox"]
                    font_info = unit["original"]["blocks"][0]["font_info"]
                    translated_text = unit["translated"]["translated_text"]
                    
                    # Expand bbox slightly to ensure full coverage
                    expanded_bbox = self.pdf_text_layout.expand_bbox(bbox)
                    
                    # Draw a white rectangle to cover the original text
                    self.pdf_text_layout.draw_white_rectangle(reportlab_canvas_page, expanded_bbox)
                    
                    # Draw the translated text
                    self.pdf_text_layout.draw_translated_text(reportlab_canvas_page, translated_text, expanded_bbox, font_info)
                
                reportlab_canvas_page.showPage()
                reportlab_canvas_page.save()
                translated_text_buffer_page.seek(0)
                
                # Merge the current original page with the translated text page
                translated_text_pdf_reader_page = pypdf.PdfReader(translated_text_buffer_page)
                translated_page = translated_text_pdf_reader_page.pages[0] # Only one page in this buffer
                
                # Get the original page for merging
                current_original_page = original_pdf_reader.pages[page_num]
                
                current_original_page.merge_page(translated_page)
                output_pdf_writer.add_page(current_original_page)

            with open(output_path, "wb") as out_file:
                output_pdf_writer.write(out_file)
            self.logger.info(f"Merged PDFs and saved final translated PDF to {output_path}")

            self.logger.info(f"Successfully completed translated PDF creation process for {output_path}.")
            self.logger.debug("Function end: create_translated_pdf (success)")
            return output_path, time.time(), translated_units

        except FileNotFoundError as e:
            self.logger.error(str(e))
            self.logger.debug("Function end: create_translated_pdf (failed - file not found)")
            raise
        except Exception as e:
            error_msg: str = f"An unexpected error occurred during PDF translation: {str(e)}"
            self.logger.error(error_msg)
            self.logger.debug(f"Detailed error information:\n{traceback.format_exc()}")
            self.logger.debug("Function end: create_translated_pdf (failed - unexpected error)")
            raise Exception(error_msg)

    def _combine_text_blocks(self, extracted_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        self.logger.debug(f"Function start: _combine_text_blocks")
        """
        Combines extracted text blocks into translation units.

        Args:
            extracted_data: List of extracted data
            text_threshold: Threshold between text blocks (pixels)

        Returns:
            List of combined translation units
        """
        try:
            # Extract only text blocks
            text_blocks: List[Dict[str, Any]] = [block for block in extracted_data if block["block_type"] == "text"]

            # Group by page
            pages: Dict[int, List[Dict[str, Any]]] = {}
            for block in text_blocks:
                page_num: int = block["page"]
                if page_num not in pages:
                    pages[page_num] = []
                pages[page_num].append(block)

            # Combine text blocks on each page
            combined_units: List[Dict[str, Any]] = []

            for page_num, blocks in pages.items():
                # Sort by bounding box (top-left to bottom-right)
                sorted_blocks: List[Dict[str, Any]] = sorted(blocks, key=lambda b: (b["bbox"][1], b["bbox"][0]))

                # Combination logic
                current_unit: Dict[str, Any] | None = None

                for block in sorted_blocks:
                    if current_unit is None:
                        # First block, initialize bbox with its own bbox
                        current_unit = {
                            "text": block["text"],
                            "blocks": [block],
                            "bbox": block["bbox"], # Initialize with the first block's bbox
                            "page": block["page"], # Add page number here
                            "font_info": {
                                "font_size": block["font_size"],
                                "font_name": block["font_name"],
                                "is_bold": block["is_bold"],
                                "is_italic": block["is_italic"]
                            }
                        }
                    else:
                        # Calculate distance from previous block
                        # bbox = (min_x, min_y, max_x, max_y)
                        prev_block: Dict[str, Any] = current_unit["blocks"][-1]
                        prev_bbox: Tuple[float, float, float, float] = prev_block["bbox"]
                        curr_bbox: Tuple[float, float, float, float] = block["bbox"]

                        distance_h: float = curr_bbox[0] - prev_bbox[2] # top - bottom
                        distance_v: float = curr_bbox[1] - prev_bbox[3] # left - right

                        thres_h: float = Config.PDF_TEXT_THRESHOLD * Config.HORIZONTAL_DIST_FACTOR # default 10[pixel]
                        thres_v: float = Config.PDF_TEXT_THRESHOLD * Config.VERTICAL_DIST_FACTOR   # default 5[pixel]

                        near_h: bool = abs(distance_h) < thres_h
                        near_v: bool = abs(distance_v) < thres_v
                        is_similar: bool = self._is_similar_font(current_unit["font_info"], block)

                        # Combine if on the same line or next line, and horizontal distance is within threshold
                        if (near_h and near_v):
                            # Combine only if font information is similar
                            if (is_similar):
                                current_text = current_unit["text"]
                                current_text = current_text[:-1] + ' ' if current_text.endswith('\n') else current_text
                                current_unit["text"] = current_text + " " + block["text"]
                                current_unit["blocks"].append(block)
                                # Expand the bbox to include the new block
                                current_unit["bbox"] = (
                                    min(current_unit["bbox"][0], curr_bbox[0]),
                                    min(current_unit["bbox"][1], curr_bbox[1]),
                                    max(current_unit["bbox"][2], curr_bbox[2]),
                                    max(current_unit["bbox"][3], curr_bbox[3])
                                )
                            else:
                                # If fonts are different, create a new unit
                                combined_units.append(current_unit)
                                current_unit = {
                                    "page": block["page"],
                                    "text": block["text"],
                                    "blocks": [block],
                                    "bbox": curr_bbox,
                                    "font_info": {
                                        "font_size": block["font_size"],
                                        "font_name": block["font_name"],
                                        "is_bold": block["is_bold"],
                                        "is_italic": block["is_italic"]
                                    }
                                }
                        else:
                            # If different paragraph, create a new unit
                            combined_units.append(current_unit)
                            current_unit = {
                                "page": block["page"],
                                "text": block["text"],
                                "blocks": [block],
                                "bbox": curr_bbox,
                                "font_info": {
                                    "font_size": block["font_size"],
                                    "font_name": block["font_name"],
                                    "is_bold": block["is_bold"],
                                    "is_italic": block["is_italic"]
                                }
                            }

                # Add the last unit if it exists and has text
                if current_unit and current_unit["text"].strip():
                    combined_units.append(current_unit)

            self.logger.info(f"Combined {len(text_blocks)} text blocks into {len(combined_units)} translation units")
            self.logger.debug("Function end: _combine_text_blocks (success)")
            return combined_units

        except Exception as e:
            self.logger.error(f"Error combining text blocks: {str(e)}")
            self.logger.debug("Function end: _combine_text_blocks (failed)")
            raise
        self.logger.debug("Function end: _combine_text_blocks (success)")

    def _is_similar_font(self, font_info1: Dict[str, Any], font_info2: Dict[str, Any],
                        size_threshold: float = 1.0) -> bool:
        self.logger.debug(f"Function start: _is_similar_font(font_info1={font_info1}, font_info2={font_info2}, size_threshold={size_threshold})")
        """
        Determines if font information is similar.

        Args:
            font_info1: Font information 1
            font_info2: Font information 2
            size_threshold: Font size threshold

        Returns:
            True if similar
        """
        # Font size difference within threshold
        size_diff: float = abs(font_info1["font_size"] - font_info2["font_size"])

        # Bold/italic status is the same
        style_match: bool = (font_info1["is_bold"] == font_info2["is_bold"] and
                       font_info1["is_italic"] == font_info2["is_italic"])

        # For now, we will not compare font names due to potential inconsistencies between pdfminer.six and ReportLab.
        # A more robust solution would involve font mapping or a more flexible comparison.
        self.logger.debug(f"Function end: _is_similar_font (success) -> {size_diff <= size_threshold and style_match}")
        return size_diff <= size_threshold and style_match
