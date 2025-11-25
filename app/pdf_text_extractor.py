# Copyright 2025 npz35
#
# See the NOTICE file for this project for license details.
# This file may not be used except in accordance with the NOTICE.

import logging
from typing import Any, Optional
import pdfplumber
import numpy as np
from scipy.signal import find_peaks
from app.config import Config
from app.data_model import BBox, ColumnIndex, TextArea, TextBlock, FontInfo
from app.text.pdfminer import PdfminerAnalyzer
from app.text.pdfplumber import PdfplumberAnalyzer
from app.text.pypdf import PyPdfAnalyzer
from app.text.unstructured import UnstructuredAnalyzer

class PdfTextExtractor:
    '''
    PDFからテキストを抽出し、テキストブロックを構成するクラスなのだ。
    列の検出やテキストブロックの結合ロジックを含むのだ。
    '''
    def __init__(self):
        self.logger: logging.Logger = logging.getLogger(__name__)
        self.logger.debug('Function start: PdfTextExtractor.__init__()')

        # self.pdfminer_analyzer = PdfminerAnalyzer()
        self.pdfplumber_analyzer = PdfplumberAnalyzer()
        # self.pypdf_analyzer = PyPdfAnalyzer()
        # self.unstructured_analyzer = UnstructuredAnalyzer()

        self.logger.debug('Function end: PdfTextExtractor.__init__ (success)')

    def _get_column_boundaries(self, all_page_text_blocks: list[list[TextBlock]], page_width: float) -> list[float]:
        '''
        テキストブロックのX座標の分布を分析し、列の境界を動的に決定するのだ。
        ヒストグラム分析とピーク検出を用いて、列間の空白領域を特定するのだ。
        '''
        if not all_page_text_blocks:
            return []

        # テキストブロックのX座標の中心点を収集するのだ
        x_centers = []
        for page_text_blocks in all_page_text_blocks:
            for block in page_text_blocks:
                if block.bbox: # TextBlockのbbox属性にアクセスするのだ
                    x0, _, x1, _ = block.bbox.x0, block.bbox.y0, block.bbox.x1, block.bbox.y1
                    x_centers.append((x0 + x1) / 2)

        if not x_centers:
            return []

        # ヒストグラムを作成するのだ
        # ビンの数をページの幅に応じて調整するのだ
        num_bins = int(page_width / 5) # 5ptごとにビンを作成するのだ
        hist, bin_edges = np.histogram(x_centers, bins=num_bins, range=(0, page_width))

        # ヒストグラムを平滑化するのだ（ノイズを減らすため）
        smoothed_hist = np.convolve(hist, np.ones(5)/5, mode='valid') # 5点移動平均なのだ

        # ピーク（テキストの集中領域）を検出するのだ
        # 谷間（列間の空白領域）を見つけるために、ヒストグラムを反転させてピークを検出するのだ
        inverted_hist = -smoothed_hist
        # ピークの相対的な高さと幅を調整して、適切な谷間を見つけるのだ
        peaks, _ = find_peaks(inverted_hist, prominence=0.5 * np.max(inverted_hist), width=5)

        column_boundaries = []
        for peak_idx in peaks:
            # ピークの位置が列の境界となるのだ
            # bin_edgesのインデックスはsmoothed_histより小さいので調整するのだ
            boundary_x = bin_edges[peak_idx + 2] # 調整が必要なのだ
            column_boundaries.append(boundary_x)
        
        # 検出された境界をソートするのだ
        column_boundaries.sort()

        # ページの端を境界として追加するのだ
        if 0 not in column_boundaries:
            column_boundaries.insert(0, 0)
        if page_width not in column_boundaries:
            column_boundaries.append(page_width)

        # 重複を削除してソートし直すのだ
        column_boundaries = sorted(list(set(column_boundaries)))

        self.logger.debug(f'Detected column boundaries: {column_boundaries}, page_width: {page_width}')
        return column_boundaries

    def extract_textareas(self, pdf_path: str) -> list[list[TextArea]]:
        self.logger.debug(f"Function start: extract_textareas(pdf_path='{pdf_path}')")
        
        if Config.TEXT_EXTRACTION_METHOD == 'pdfminer':
            raise NotImplementedError('Not implement yet.')
        elif Config.TEXT_EXTRACTION_METHOD == 'pdfplumber':
            return self.pdfplumber_analyzer.extract_textareas(pdf_path)
        elif Config.TEXT_EXTRACTION_METHOD == 'pypdf':
            # return self.pypdf_analyzer.extract_textareas(pdf_path)
            raise NotImplementedError('Not implement yet.')
        elif Config.TEXT_EXTRACTION_METHOD == 'unstructured':
            # return self.unstructured_analyzer.extract_textareas(pdf_path)
            raise NotImplementedError('Not implement yet.')
        elif Config.TEXT_EXTRACTION_METHOD == 'hybrid_pdfminer_pypdf':
            raise NotImplementedError('Not implement yet.')
        else:
            self.logger.error(f'Unknown text extraction method: {Config.TEXT_EXTRACTION_METHOD}')
            raise ValueError(f'Unknown text extraction method: {Config.TEXT_EXTRACTION_METHOD}')
