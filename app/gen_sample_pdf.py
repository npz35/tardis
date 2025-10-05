# Copyright 2025 npz35
#
# See the NOTICE file for this project for license details.
# This file may not be used except in accordance with the NOTICE.

from reportlab.platypus import Paragraph, SimpleDocTemplate, Image, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from typing import Any
import os

# Create a test PDF file
output_pdf_path = 'uploads/sample.pdf'

# Create a dummy image file
dummy_image_path = "dummy_image.png"
from PIL import Image as PILImage
img = PILImage.new('RGB', (200, 100), color = 'red')
img.save(dummy_image_path)

# Create a SimpleDocTemplate
doc: SimpleDocTemplate = SimpleDocTemplate(output_pdf_path, pagesize=letter)
styles: dict[str, ParagraphStyle] = getSampleStyleSheet()

# Define flowables
flowables: list[Any] = [] # Changed to Any to accommodate Image and Spacer

# Page 1
flowables.append(Paragraph('Hello, World! (Page 1)', styles['Normal']))
flowables.append(Paragraph('This is a test PDF for figure extraction across multiple pages.', styles['Normal']))
flowables.append(Spacer(1, 0.2 * inch)) # Add some space
flowables.append(Paragraph('Here is an image on Page 1:', styles['Normal']))
flowables.append(Image(dummy_image_path, width=2*inch, height=1*inch))
flowables.append(Spacer(1, 0.2 * inch)) # Add some space
flowables.append(Paragraph('This is a table candidate text block on Page 1:', styles['Normal']))
flowables.append(Paragraph('Column1   Column2   Column3', styles['Normal']))
flowables.append(Paragraph('Data1     Data2     Data3', styles['Normal']))
flowables.append(Paragraph('<i>T(p, q) = {ε} if pq = ε</i>', styles['Normal']))
flowables.append(Paragraph('More Data More Data More Data', styles['Normal']))

# Add a page break
flowables.append(PageBreak())

# Page 2
flowables.append(Paragraph('Hello, World! (Page 2)', styles['Normal']))
flowables.append(Paragraph('This is the second page with another image.', styles['Normal']))
flowables.append(Spacer(1, 0.2 * inch)) # Add some space
flowables.append(Paragraph('Here is another image on Page 2:', styles['Normal']))
flowables.append(Image(dummy_image_path, width=2*inch, height=1*inch))
flowables.append(Spacer(1, 0.2 * inch)) # Add some space
flowables.append(Paragraph('Another table candidate text block on Page 2:', styles['Normal']))
flowables.append(Paragraph('ItemA     ItemB     ItemC', styles['Normal']))
flowables.append(Paragraph('ValueX    ValueY    ValueZ', styles['Normal']))

# Build the PDF
doc.build(flowables)

print(f'Test PDF created: {output_pdf_path}')

# Clean up the dummy image
os.remove(dummy_image_path)