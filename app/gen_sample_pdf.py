# Copyright 2025 npz35
#
# See the NOTICE file for this project for license details.
# This file may not be used except in accordance with the NOTICE.

from reportlab.platypus import Paragraph, SimpleDocTemplate, Image, Spacer, PageBreak, BaseDocTemplate, PageTemplate, Frame, NextPageTemplate
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
# Create a BaseDocTemplate
doc: BaseDocTemplate = BaseDocTemplate(output_pdf_path, pagesize=letter)
styles: dict[str, ParagraphStyle] = getSampleStyleSheet()

# Define frames for two-column layout on Page 2
frame1_margin = inch
frame_width = (letter[0] - 2 * frame1_margin - 0.2 * inch) / 2 # Total width - margins - gutter
frame_height = letter[1] - 2 * frame1_margin

# Frame for Page 1 (single column)
frame_page1 = Frame(frame1_margin, frame1_margin, letter[0] - 2 * frame1_margin, frame_height,
                    id='normal')

# Frames for Page 2 (two columns)
frame_page2_col1 = Frame(frame1_margin, frame1_margin, frame_width, frame_height,
                         id='col1')
frame_page2_col2 = Frame(frame1_margin + frame_width + 0.2 * inch, frame1_margin, frame_width, frame_height,
                         id='col2')

# Define page templates
# Page 1 template (single column)
page1_template = PageTemplate(id='Page1Template', frames=[frame_page1])
# Page 2 template (two columns)
page2_template = PageTemplate(id='Page2Template', frames=[frame_page2_col1, frame_page2_col2])

doc.addPageTemplates([page1_template, page2_template])

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

# Add a page break and switch to Page2Template
flowables.append(NextPageTemplate('Page2Template'))
flowables.append(PageBreak())
flowables.append(Paragraph('Hello, World! (Page 2 - Column 1)', styles['Normal']))
flowables.append(Paragraph('This is the second page with another image, laid out in two columns.', styles['Normal']))
flowables.append(Spacer(1, 0.2 * inch)) # Add some space
flowables.append(Paragraph('Here is an image on Page 2, Column 1:', styles['Normal']))
flowables.append(Image(dummy_image_path, width=2*inch, height=1*inch))
flowables.append(Spacer(1, 0.2 * inch)) # Add some space
flowables.append(Paragraph('This is some more text for Column 1. We need enough content to demonstrate the two-column layout effectively. This block will continue to fill the first column.', styles['Normal']))
flowables.append(Paragraph('More text for Column 1. This should push content into the second column if there is enough of it.', styles['Normal']))
flowables.append(Paragraph('Another table candidate text block on Page 2, Column 1:', styles['Normal']))
flowables.append(Paragraph('ItemA     ItemB     ItemC', styles['Normal']))
flowables.append(Paragraph('ValueX    ValueY    ValueZ', styles['Normal']))
flowables.append(Paragraph('This is the start of content for Column 2. It will automatically flow from Column 1.', styles['Normal']))
flowables.append(Paragraph('More content for Column 2. This demonstrates how text wraps from one column to the next. We are adding more text to ensure that both columns are filled and the layout is visible.', styles['Normal']))
flowables.append(Paragraph('Final text for Page 2. This should appear in Column 2. The goal is to have a clear two-column layout for the second page of the PDF.', styles['Normal']))

flowables.append(Paragraph('Apollo 11 was the first spaceflight to land humans on the Moon, conducted by NASA from July 16 to 24, 1969. Commander Neil Armstrong and Lunar Module Pilot Edwin "Buzz" Aldrin landed the Lunar Module Eagle on July 20 at 20:17 UTC, and Armstrong became the first person to step onto the surface about six hours later, at 02:56 UTC on July 21. Aldrin joined him 19 minutes afterward, and together they spent about two and a half hours exploring the site they had named Tranquility Base upon landing. They collected 47.5 pounds (21.5 kg) of lunar material to bring back to Earth before re-entering the Lunar Module. In total, they were on the Moon’s surface for 21 hours, 36 minutes before returning to the Command Module Columbia, which remained in lunar orbit, piloted by Michael Collins. This is the text at the bottom left of page 2.', styles['Normal']))

flowables.append(Paragraph('This is the text at the top right of page 2. Apollo 11 was launched by a Saturn V rocket from Kennedy Space Center in Florida, on July 16 at 13:32 UTC (9:32 am EDT, local time). It was the fifth crewed mission of the Apollo program. The Apollo spacecraft consisted of three parts: the command module (CM), which housed the three astronauts and was the only part to return to Earth; the service module (SM), which provided propulsion, electrical power, oxygen, and water to the command module; and the Lunar Module (LM), which had two stages—a descent stage with a large engine and fuel tanks for landing on the Moon, and a lighter ascent stage containing a cabin for two astronauts and a small engine to return them to lunar orbit.', styles['Normal']))

# Build the PDF
doc.build(flowables)

print(f'Test PDF created: {output_pdf_path}')

# Clean up the dummy image
os.remove(dummy_image_path)