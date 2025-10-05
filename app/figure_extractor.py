# Copyright 2025 npz35
#
# See the NOTICE file for this project for license details.
# This file may not be used except in accordance with the NOTICE.

import os
import logging
from typing import List, Dict, Any, Tuple

from pdfminer.high_level import extract_pages
from pdfminer.layout import LTFigure, LTImage, LTTextContainer, LTTextBoxHorizontal
from pdfminer.image import ImageWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PIL import Image as PILImage


class FigureExtractor:
    def __init__(self, japanese_font_path: str): # Add logger argument
        self.logger: logging.Logger = logging.getLogger(__name__)
        self.logger.debug(f"Function start: FigureExtractor.__init__(japanese_font_path='{japanese_font_path}')")
        self.japanese_font_path = japanese_font_path
        pdfmetrics.registerFont(TTFont('IPAexMincho', self.japanese_font_path))
        self.logger.debug("Function end: FigureExtractor.__init__ (success)")

    def extract_figures(self, pdf_path: str) -> List[Dict[str, Any]]:
        self.logger.debug(f"Function start: extract_figures(pdf_path='{pdf_path}')")
        """
        Extracts figures from a PDF.
        """
        figures = []
        for page_layout in extract_pages(pdf_path):
            page_number = page_layout.pageid
            self.logger.info(f"Processing page {page_number}.") # Use logger
            page_figures_found = 0 # Count the number of figures found on this page
            current_page_figures = [] # Temporarily store figures found on the current page
            for element in page_layout:
                if isinstance(element, LTFigure):
                    # LTFigure may contain images or drawings
                    for component in element:
                        if isinstance(component, LTImage):
                            # Image extraction
                            x0, y0, x1, y1 = self._normalize_bbox(component.bbox, page_layout.height)
                            image_data = self._extract_image_data(component)
                            if image_data:
                                current_page_figures.append({
                                    "page": page_number,
                                    "bbox": (x0, y0, x1, y1),
                                    "figure_type": "image",
                                    "image_data": image_data,
                                    "width": component.width,
                                    "height": component.height,
                                    "confidence": 1.0 # Simple implementation
                                })
                                page_figures_found += 1
                        elif isinstance(component, LTTextContainer):
                            # Treat text within LTFigure as part of the figure
                            x0, y0, x1, y1 = self._normalize_bbox(component.bbox, page_layout.height)
                            current_page_figures.append({
                                "page": page_number,
                                "bbox": (x0, y0, x1, y1),
                                "figure_type": "text_in_figure",
                                "text": component.get_text().strip(),
                                "confidence": 0.8 # Simple implementation
                            })
                            page_figures_found += 1
                # Add detection logic for figures other than LTFigure (e.g., tables)
                # Here, we simply detect a collection of text blocks as a table
                elif isinstance(element, LTTextBoxHorizontal):
                    # Infer tables from text block size and position
                    # This is a very simple implementation, and more advanced logic is needed for actual table detection.
                    # For example, to determine if multiple text blocks are arranged in a grid.
                    if element.width > page_layout.width * 0.5 and element.height > page_layout.height * 0.05:
                        x0, y0, x1, y1 = self._normalize_bbox(element.bbox, page_layout.height)
                        current_page_figures.append({
                            "page": page_number,
                            "bbox": (x0, y0, x1, y1),
                            "figure_type": "table_candidate",
                            "text": element.get_text().strip(),
                            "confidence": 0.5 # Simple implementation
                        })
                        page_figures_found += 1
            
            self.logger.info(f"Detected {page_figures_found} figures on page {page_number}.") # Log the number of figures detected per page
            
            # If no figures are detected on this page, add it as a blank page
            if page_figures_found == 0:
                self.logger.info(f"No figures detected on page {page_number}, adding as an empty page.")
                figures.append({
                    "page": page_number,
                    "bbox": (0, 0, page_layout.width, page_layout.height), # Bbox covering the entire page
                    "figure_type": "empty_page",
                    "confidence": 0.0
                })
            else:
                figures.extend(current_page_figures) # Add detected figures
        self.logger.debug("Function end: extract_figures (success)")
        return figures

    def _normalize_bbox(self, bbox: Tuple[float, float, float, float], page_height: float) -> Tuple[float, float, float, float]:
        self.logger.debug(f"Function start: _normalize_bbox(bbox={bbox}, page_height={page_height})")
        """
        Normalizes PDFMiner's bbox to ReportLab's coordinate system.
        Both PDFMiner and ReportLab use the bottom-left as the origin, with the Y-axis increasing upwards.
        Therefore, no special conversion is needed.
        """
        self.logger.debug(f"Function end: _normalize_bbox (success) -> {bbox}")
        return bbox

    def _extract_image_data(self, image_element: LTImage) -> str:
        self.logger.debug(f"Function start: _extract_image_data(image_element={image_element})")
        """
        Extracts image data from an LTImage element and base64 encodes it.
        """
        # Extract image data from LTImage element and save as a temporary file.
        # Return the path of the extracted image file.
        if not hasattr(image_element, 'stream') or not image_element.stream:
            self.logger.info("Image stream not found.") # Use logger
            self.logger.debug(f"Function end: _extract_image_data(image_element={image_element})")
            return ""

        # Use PDFMiner's ImageWriter to extract images.
        # ImageWriter saves images as temporary files.
        # Here, create a temporary directory and save images there.
        import tempfile
        temp_dir = tempfile.mkdtemp()
        image_writer = ImageWriter(temp_dir)
        try:
            # ImageWriter generates BMP by default.
            # Convert to PNG format, which is recommended by ReportLab, and save.
            original_image_filename = image_writer.export_image(image_element)
            original_image_path = os.path.join(temp_dir, original_image_filename)

            # Use PIL (Pillow) to convert BMP to PNG.
            try:
                # Generate the filename after conversion
                base_name, _ = os.path.splitext(original_image_filename)
                png_filename = base_name + '.png'
                png_image_path = os.path.join(temp_dir, png_filename)

                with PILImage.open(original_image_path) as img:
                    img.save(png_image_path, 'PNG')
                self.logger.info(f"Converted image to PNG format: {png_image_path}") # Use logger
                os.remove(original_image_path) # Delete the original BMP file
                self.logger.debug(f"Function end: _extract_image_data(image_element={image_element})")
                return png_image_path
            except Exception as e:
                self.logger.error(f"Image format conversion error: {e}. Returning original BMP path.") # Use logger
                # If conversion fails, return the original BMP path.
                self.logger.debug(f"Function end: _extract_image_data(image_element={image_element})")
                return original_image_path
        except Exception as e:
            self.logger.error(f"Image extraction error: {e}") # Use logger
            self.logger.debug(f"Function end: _extract_image_data(image_element={image_element})")
            return ""
        finally:
            # The temporary directory needs to be cleaned up later.
            # Here, we return the image path, so the caller manages deletion.
            self.logger.debug("Function end: _extract_image_data (success/finally)")
            pass

    def create_figure_pdf(self, figures: List[Dict[str, Any]], output_path: str):
        self.logger.debug(f"Function start: create_figure_pdf(output_path='{output_path}')")
        """
        Generates a PDF containing only figures based on the extracted figure information.
        """
        c = canvas.Canvas(output_path, pagesize=A4)
        width, height = A4

        current_page = -1
        for figure in figures:
            page_number = figure["page"]
            bbox = figure["bbox"]
            figure_type = figure["figure_type"]

            if page_number != current_page:
                if current_page != -1:
                    c.showPage() # Switch page
                current_page = page_number
                # Draw page number on the new page
                c.setFont('IPAexMincho', 12)
                c.drawString(10*mm, height - 10*mm, f"Page {page_number}")


            if figure_type == "image":
                x0, y0, x1, y1 = bbox
                image_file_path = figure.get("image_data") # image_data is now a file path
                if image_file_path and os.path.exists(image_file_path):
                    try:
                        self.logger.info(f"Image file to draw exists! Path: {image_file_path}") # Use logger
                        c.drawImage(image_file_path, x0, y0, width=x1-x0, height=y1-y0, preserveAspectRatio=True)
                    except Exception as e:
                        self.logger.error(f"Image drawing error: {e}") # Use logger
                        # Draw a dummy rectangle on error
                        c.rect(x0, y0, x1 - x0, y1 - y0)
                        c.setFont('IPAexMincho', 10)
                        c.drawString(x0, y0 + (y1 - y0) / 2, f"Image Draw Error (Page {page_number})")
                    finally:
                        # Delete temporary file after use (temporarily commented out for debugging)
                        # os.remove(image_file_path)
                        # The temporary directory created by ImageWriter also needs to be deleted (temporarily commented out for debugging)
                        # import shutil
                        # temp_dir = os.path.dirname(image_file_path)
                        # if os.path.exists(temp_dir):
                        #     shutil.rmtree(temp_dir)
                        pass # Add pass to avoid indentation error
                else:
                    # Draw a dummy rectangle if no image data
                    self.logger.info("No image file to draw.") # Use logger
                    c.rect(x0, y0, x1 - x0, y1 - y0)
                    c.setFont('IPAexMincho', 10)
                    c.drawString(x0, y0 + (y1 - y0) / 2, f"Image Placeholder (Page {page_number})")
            elif figure_type == "text_in_figure":
                # Draw text within the figure
                x0, y0, x1, y1 = bbox
                text_content = figure.get("text", "")
                c.setFont('IPAexMincho', 8) # Draw with a smaller font
                c.drawString(x0, y0, f"Text in Figure: {text_content[:50]}...") # Truncate if long
                c.rect(x0, y0, x1 - x0, y1 - y0, stroke=1, fill=0) # Enclose with a border
            elif figure_type == "table_candidate":
                # Draw table candidate text
                x0, y0, x1, y1 = bbox
                text_content = figure.get("text", "")
                c.setFont('IPAexMincho', 8) # Draw with a smaller font
                c.drawString(x0, y0 + (y1 - y0) / 2, f"Table Candidate: {text_content[:50]}...") # Truncate if long
                c.rect(x0, y0, x1 - x0, y1 - y0, stroke=1, fill=0) # Enclose with a border
            elif figure_type == "empty_page":
                # Do not draw anything for blank pages
                self.logger.info(f"Page {page_number} is processed as a blank page.")
                # Page is already created, so do nothing
 
        c.save()
        self.logger.debug("Function end: create_figure_pdf (success)")

if __name__ == '__main__':
    import os
    import sys
    import tempfile
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Image, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from PIL import Image as PILImage
    # import shutil # shutil is not currently used, so delete it

    # Generate a PDF for testing
    temp_pdf_file = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
    temp_pdf_file.close()
    # Use the PDF path generated by the user
    temp_pdf_path = "uploads/sample_2.pdf" # Remove extra space at the beginning of the path

    # dummy_image_pathはgen_sample_pdf.pyで生成・削除されるので、ここでは不要
    # img = PILImage.new('RGB', (200, 100), color = 'blue')
    # img.save(dummy_image_path)

    # doc = SimpleDocTemplate(temp_pdf_path, pagesize=letter)
    # styles = getSampleStyleSheet()
    # flowables = []

    # flowables.append(Paragraph('Hello, World!', styles['Normal']))
    # flowables.append(Paragraph('This is a test PDF for figure extraction.', styles['Normal']))
    # flowables.append(Spacer(1, 0.2 * inch))
    # flowables.append(Paragraph('Here is an image:', styles['Normal']))
    # flowables.append(Image(dummy_image_path, width=2*inch, height=1*inch))
    # flowables.append(Spacer(1, 0.2 * inch))
    # flowables.append(Paragraph('This is a table candidate text block:', styles['Normal']))
    # flowables.append(Paragraph('Column1   Column2   Column3', styles['Normal']))
    # flowables.append(Paragraph('Data1     Data2     Data3', styles['Normal']))
    # flowables.append(Paragraph('More Data More Data More Data', styles['Normal']))

    # doc.build(flowables)
    # os.remove(dummy_image_path)

    print(f"Using user-generated test PDF: {temp_pdf_path}")

    font_path = os.environ.get('JAPANESE_FONT_PATH')
    if not font_path:
        print("JAPANESE_FONT_PATH environment variable is not set.")
        # Assume IPAexMincho font path.
        # Adjustment is needed according to the actual environment.
        # Use project's static/fonts/ipaexm.ttf.
        # BASE_DIR can be obtained with os.path.dirname(os.path.dirname(__file__)).
        base_dir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
        font_path = os.path.join(base_dir, 'static', 'fonts', 'ipaexm.ttf')
        print(f"Using default font path: {font_path}")
        # sys.exit(1) # Comment out to allow continuation even if environment variable is not set.

    extractor = FigureExtractor(font_path)
    figures = extractor.extract_figures(temp_pdf_path)
    output_figure_pdf_path = "output_figures.pdf"
    extractor.create_figure_pdf(figures, output_figure_pdf_path)

    print(f"Generated PDF of extracted figures: {output_figure_pdf_path}")
    print("Extracted figure information:")
    for fig in figures:
        print(fig)
