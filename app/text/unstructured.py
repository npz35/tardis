# Copyright 2025 npz35
#
# See the NOTICE file for this project for license details.
# This file may not be used except in accordance with the NOTICE.

import logging
from typing import List, Dict, Any, Tuple
from unstructured.partition.pdf import partition_pdf

from app.text.common import PdfAnalyzer
from app.data_model import BBox, TextBlock, PageAnalyzeData, FontInfo

logger: logging.Logger = logging.getLogger(__name__)

class UnstructuredAnalyzer(PdfAnalyzer):
    def __init__(self):
        super().__init__()

    def extract_textblocks(self, pdf_path: str) -> List[List[TextBlock]]:
        logger.debug(f"Function start: extract_textblocks(pdf_path='{pdf_path}')")
        extracted_data: List[List[TextBlock]] = []

        try:
            # Use unstructured to partition the PDF
            elements = partition_pdf(filename=pdf_path, infer_table_structure=True)

            for element in elements:
                # Each element has a text attribute and may have a bbox
                text = element.text
                # The bbox from unstructured is (x1, y1, x2, y2) where (x1, y1) is the top-left corner
                # and (x2, y2) is the bottom-right corner.
                # We need to convert this to (x0, y0, x1, y1) where (x0, y0) is the bottom-left corner
                # and (x1, y1) is the top-right corner.
                # However, without the page height, we cannot accurately convert the y-coordinates.
                # For now, we will use the coordinates as they are and see the result.
                # x0 = element.metadata.coordinates.points[0][0]
                # y0 = element.metadata.coordinates.points[0][1]
                # x1 = element.metadata.coordinates.points[2][0]
                # y1 = element.metadata.coordinates.points[2][1]
                
                # unstructured returns coordinates in element.metadata.coordinates.points
                # The format is ((x1, y1), (x1, y2), (x2, y2), (x2, y1))
                if element.metadata.coordinates:
                    points = element.metadata.coordinates.points
                    x0 = points[0][0]
                    y0 = points[1][1] # This should be the bottom y-coordinate
                    x1 = points[2][0]
                    y1 = points[0][1] # This should be the top y-coordinate
                    bbox = (x0, y0, x1, y1)
                    page_number = element.metadata.page_number

                    # unstructured does not provide font info, so we pass None for FontInfo
                    text_block = TextBlock(
                        text=text,
                        bbox=BBox(*bbox),
                        font_info=None,
                        page_number=page_number,
                    )
                    # For now, we'll put each TextBlock in its own list,
                    # as the return type expects List[List[TextBlock]].
                    # Further logic might be needed to group them into meaningful blocks.
                    extracted_data.append([text_block])

        except Exception as e:
            logger.error(f"Error extracting text with unstructured from {pdf_path}: {e}")
            raise

        logger.debug(f"Function end: extract_text_with_positions. Extracted {len(extracted_data)} elements.")
        return extracted_data

    def crop_textblock(self, pdf_path: str, page_number: int) -> List[TextBlock]:
        raise NotImplementedError("UnstructuredAnalyzer does not implement extract_textblock yet.")
