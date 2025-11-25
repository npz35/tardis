# Copyright 2025 npz35
#
# See the NOTICE file for this project for license details.
# This file may not be used except in accordance with the NOTICE.

"""
Test for detecting text overlap in translated PDFs.

This test module verifies that translated text blocks do not overlap
when rendered in the output PDF. It uses mocked LLM API responses
based on data from logs/llm.log.
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from flask import Flask
from app.main import create_app
from app.config import TestingConfig
from app.data_model import BBox
from tests.fixtures.llm_responses import create_mock_translation_responses
import pdfplumber
from typing import Optional


class TestTextOverlapDetection:
    """Test suite for detecting text overlap in translated PDFs"""
    
    @pytest.fixture
    def app(self):
        """Create and configure a new app instance for each test"""
        app, _ = create_app(TestingConfig)
        app.config.update({
            'TESTING': True,
            'JAPANESE_FONT_PATH': 'static/fonts/ipaexg.ttf',
            'MIN_FONT_SIZE': 8,
        })
        yield app

    @pytest.fixture
    def client(self, app: Flask):
        """A test client for the app"""
        return app.test_client()

    @pytest.fixture
    def sample_pdf_path(self):
        """Path to the sample PDF for testing"""
        return 'samples/sample.pdf'

    def extract_text_bboxes_from_pdf(self, pdf_path: str) -> list[dict]:
        """
        Extract text and bounding boxes from a PDF file.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            List of dictionaries containing:
                - text: The text content
                - bbox: BBox object with coordinates (x0, y0, x1, y1)
                - page: Page number (1-indexed)
        """
        text_bboxes = []
        
        with pdfplumber.open(pdf_path) as pdf:
            for page_idx, page in enumerate(pdf.pages):
                page_number = page_idx + 1
                
                # Extract words with their bounding boxes
                words = page.extract_words(
                    x_tolerance=3,
                    y_tolerance=3,
                    keep_blank_chars=False,
                    use_text_flow=True
                )
                
                for word in words:
                    # pdfplumber uses (x0, top, x1, bottom) format
                    # Convert to BBox format (x0, y0, x1, y1) with bottom-left origin
                    # pdfplumber's coordinate system has origin at top-left
                    # We need to convert to bottom-left origin for consistency
                    page_height = page.height
                    
                    bbox = BBox(
                        x0=word['x0'],
                        y0=page_height - word['bottom'],  # Convert from top-origin to bottom-origin
                        x1=word['x1'],
                        y1=page_height - word['top']      # Convert from top-origin to bottom-origin
                    )
                    
                    text_bboxes.append({
                        'text': word['text'],
                        'bbox': bbox,
                        'page': page_number
                    })
        
        return text_bboxes

    def bboxes_overlap(self, bbox1: BBox, bbox2: BBox, tolerance: float = 0.5) -> bool:
        """
        Check if two bounding boxes overlap.
        
        Args:
            bbox1: First bounding box
            bbox2: Second bounding box
            tolerance: Small tolerance value to account for floating point precision
            
        Returns:
            True if the bounding boxes overlap, False otherwise
        """
        # Check if rectangles overlap on X axis
        if bbox1.x1 <= bbox2.x0 + tolerance or bbox2.x1 <= bbox1.x0 + tolerance:
            return False
        # Check if rectangles overlap on Y axis
        if bbox1.y1 <= bbox2.y0 + tolerance or bbox2.y1 <= bbox1.y0 + tolerance:
            return False
        return True

    def calculate_overlap_area(self, bbox1: BBox, bbox2: BBox) -> float:
        """
        Calculate the area of overlap between two bounding boxes.
        
        Args:
            bbox1: First bounding box
            bbox2: Second bounding box
            
        Returns:
            The area of overlap in square points
        """
        # Calculate intersection rectangle
        x_overlap = max(0, min(bbox1.x1, bbox2.x1) - max(bbox1.x0, bbox2.x0))
        y_overlap = max(0, min(bbox1.y1, bbox2.y1) - max(bbox1.y0, bbox2.y0))
        
        return x_overlap * y_overlap

    def detect_bbox_overlaps(self, text_bboxes: list[dict]) -> list[dict]:
        """
        Detect overlaps between text bounding boxes.
        
        Args:
            text_bboxes: List of text and bbox dictionaries
            
        Returns:
            List of overlap information dictionaries, empty if no overlaps found
        """
        overlaps = []
        
        # Check all pairs of bboxes
        for i in range(len(text_bboxes)):
            for j in range(i + 1, len(text_bboxes)):
                bbox1_data = text_bboxes[i]
                bbox2_data = text_bboxes[j]
                
                # Only check overlaps on the same page
                if bbox1_data['page'] != bbox2_data['page']:
                    continue
                
                bbox1 = bbox1_data['bbox']
                bbox2 = bbox2_data['bbox']
                
                if self.bboxes_overlap(bbox1, bbox2):
                    overlap_area = self.calculate_overlap_area(bbox1, bbox2)
                    
                    overlaps.append({
                        'text1': bbox1_data['text'],
                        'bbox1': bbox1,
                        'text2': bbox2_data['text'],
                        'bbox2': bbox2,
                        'page': bbox1_data['page'],
                        'overlap_area': overlap_area
                    })
        
        return overlaps

    def format_overlap_report(self, overlaps: list[dict]) -> str:
        """
        Format overlap information into a readable report.
        
        Args:
            overlaps: List of overlap dictionaries
            
        Returns:
            Formatted string report
        """
        if not overlaps:
            return "No overlaps detected."
        
        report = f"\n{'=' * 80}\n"
        report += f"TEXT OVERLAP DETECTED: {len(overlaps)} overlap(s) found\n"
        report += f"{'=' * 80}\n\n"
        
        for idx, overlap in enumerate(overlaps, 1):
            report += f"Overlap {idx}:\n"
            report += f"  Page: {overlap['page']}\n"
            report += f"  Text 1: \"{overlap['text1']}\"\n"
            report += f"  BBox 1: {overlap['bbox1']}\n"
            report += f"  Text 2: \"{overlap['text2']}\"\n"
            report += f"  BBox 2: {overlap['bbox2']}\n"
            report += f"  Overlap area: {overlap['overlap_area']:.2f} sq pt\n"
            report += "\n"
        
        report += f"{'=' * 80}\n"
        return report

    def test_no_text_overlap_in_translated_pdf(self, client, sample_pdf_path):
        """
        Test that translated text blocks do not overlap in the generated PDF.
        
        This test:
        1. Uploads the sample PDF
        2. Mocks the Translator.translate_texts() to use predefined translations
        3. Calls /draw_text endpoint to generate a translated PDF
        4. Extracts text and bounding boxes from the generated PDF
        5. Verifies that no text blocks overlap
        
        Expected behavior:
        - Currently: Test FAILS due to known bug (text overlap exists)
        - After fix: Test PASSES (no text overlap)
        """
        # 1. Upload the file first to get filename and unique_id
        with open(sample_pdf_path, 'rb') as f:
            upload_data = {'file': (f, 'sample.pdf')}
            upload_response = client.post('/upload', data=upload_data, content_type='multipart/form-data')
        
        assert upload_response.status_code == 200
        upload_json = upload_response.get_json()
        assert upload_json['success'] is True
        assert 'filename' in upload_json
        assert 'unique_id' in upload_json
        
        filename = upload_json['filename']
        unique_id = upload_json['unique_id']

        with patch('app.main.Translator') as MockTranslator, \
             patch('app.main.PdfFigureExtractor') as MockPdfFigureExtractor:

            # Mock Translator to return predefined translations
            mock_translator_instance = MockTranslator.return_value
            
            def mock_translate_texts(texts, source_lang='English', target_lang='Japanese', max_retries=3):
                return create_mock_translation_responses(texts, source_lang, target_lang)
            
            mock_translator_instance.translate_texts.side_effect = mock_translate_texts

            # Mock PdfFigureExtractor to return empty figures list (we're focusing on text)
            mock_figure_extractor_instance = MockPdfFigureExtractor.return_value
            mock_figure_extractor_instance.extract_figures.return_value = []

            # 2. Call /draw_text with the obtained filename and unique_id
            draw_text_data = {
                'filename': filename,
                'unique_id': unique_id
            }
            response = client.post('/draw_text', data=draw_text_data)

            assert response.status_code == 200
            json_data = response.get_json()
            assert json_data['success'] is True
            assert 'filename' in json_data
            assert 'output_path' in json_data

            output_pdf_path = json_data['output_path']
            
            # Verify the output PDF file exists
            assert os.path.exists(output_pdf_path), f"Output PDF not found at {output_pdf_path}"

            # 3. Extract text and bounding boxes from the generated PDF
            text_bboxes = self.extract_text_bboxes_from_pdf(output_pdf_path)
            
            assert len(text_bboxes) > 0, "No text extracted from the generated PDF"

            # 4. Detect overlaps
            overlaps = self.detect_bbox_overlaps(text_bboxes)

            # 5. Assert no overlaps (this will fail if the bug exists)
            overlap_report = self.format_overlap_report(overlaps)
            
            assert len(overlaps) == 0, f"Text overlap detected in translated PDF!\n{overlap_report}"

    def test_no_text_overlap_in_page_2(self, client, sample_pdf_path):
        """
        Test that text blocks do not overlap specifically on page 2 (two-column layout).
        
        Page 2 has a two-column layout which is more prone to overlap issues.
        This test focuses specifically on page 2.
        """
        # 1. Upload the file
        with open(sample_pdf_path, 'rb') as f:
            upload_data = {'file': (f, 'sample.pdf')}
            upload_response = client.post('/upload', data=upload_data, content_type='multipart/form-data')
        
        assert upload_response.status_code == 200
        upload_json = upload_response.get_json()
        filename = upload_json['filename']
        unique_id = upload_json['unique_id']

        with patch('app.main.Translator') as MockTranslator, \
             patch('app.main.PdfFigureExtractor') as MockPdfFigureExtractor:

            # Mock Translator
            mock_translator_instance = MockTranslator.return_value
            mock_translator_instance.translate_texts.side_effect = lambda texts, **kwargs: create_mock_translation_responses(texts)

            # Mock PdfFigureExtractor
            mock_figure_extractor_instance = MockPdfFigureExtractor.return_value
            mock_figure_extractor_instance.extract_figures.return_value = []

            # 2. Call /draw_text
            draw_text_data = {'filename': filename, 'unique_id': unique_id}
            response = client.post('/draw_text', data=draw_text_data)

            assert response.status_code == 200
            json_data = response.get_json()
            output_pdf_path = json_data['output_path']

            # 3. Extract text and bounding boxes from page 2 only
            text_bboxes = self.extract_text_bboxes_from_pdf(output_pdf_path)
            page_2_text_bboxes = [item for item in text_bboxes if item['page'] == 2]
            
            assert len(page_2_text_bboxes) > 0, "No text extracted from page 2"

            # 4. Detect overlaps on page 2
            overlaps = self.detect_bbox_overlaps(page_2_text_bboxes)

            # 5. Assert no overlaps on page 2
            overlap_report = self.format_overlap_report(overlaps)
            
            assert len(overlaps) == 0, f"Text overlap detected on page 2!\n{overlap_report}"

    def test_measure_overlap_area_if_exists(self, client, sample_pdf_path):
        """
        If overlaps exist, measure and report the total overlap area.
        This test is informational and will not fail but will log overlap statistics.
        """
        # Upload and process PDF
        with open(sample_pdf_path, 'rb') as f:
            upload_data = {'file': (f, 'sample.pdf')}
            upload_response = client.post('/upload', data=upload_data, content_type='multipart/form-data')
        
        upload_json = upload_response.get_json()
        filename = upload_json['filename']
        unique_id = upload_json['unique_id']

        with patch('app.main.Translator') as MockTranslator, \
             patch('app.main.PdfFigureExtractor') as MockPdfFigureExtractor:

            mock_translator_instance = MockTranslator.return_value
            mock_translator_instance.translate_texts.side_effect = lambda texts, **kwargs: create_mock_translation_responses(texts)

            mock_figure_extractor_instance = MockPdfFigureExtractor.return_value
            mock_figure_extractor_instance.extract_figures.return_value = []

            draw_text_data = {'filename': filename, 'unique_id': unique_id}
            response = client.post('/draw_text', data=draw_text_data)
            json_data = response.get_json()
            output_pdf_path = json_data['output_path']

            # Extract and analyze overlaps
            text_bboxes = self.extract_text_bboxes_from_pdf(output_pdf_path)
            overlaps = self.detect_bbox_overlaps(text_bboxes)

            if overlaps:
                total_overlap_area = sum(overlap['overlap_area'] for overlap in overlaps)
                print(f"\n{'=' * 80}")
                print(f"OVERLAP STATISTICS")
                print(f"{'=' * 80}")
                print(f"Total overlaps found: {len(overlaps)}")
                print(f"Total overlap area: {total_overlap_area:.2f} sq pt")
                print(f"Average overlap area: {total_overlap_area / len(overlaps):.2f} sq pt")
                print(self.format_overlap_report(overlaps))
            else:
                print("\nNo overlaps detected. PDF rendering is working correctly!")