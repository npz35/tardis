# Copyright 2025 npz35
#
# See the NOTICE file for this project for license details.
# This file may not be used except in accordance with the NOTICE.

import math
import os
import logging
import uuid
from typing import List, Dict, Any, Tuple
import pdfplumber
import io
import tempfile

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PIL import Image as PILImage
from reportlab.lib.colors import Color, red, black
from pdfplumber.page import Page
from app.data_model import Area, BBoxRL

from app.pdf_area_separator import PdfAreaSeparator


class PdfFigureExtractor:
    def __init__(self, japanese_font_path: str, output_folder: str):
        self.logger: logging.Logger = logging.getLogger(__name__)
        self.logger.debug(f"Function start: PdfFigureExtractor.__init__(japanese_font_path='{japanese_font_path}', output_folder='{output_folder}')")
        self.japanese_font_path = japanese_font_path
        self.output_folder = output_folder
        pdfmetrics.registerFont(TTFont('IPAexMincho', self.japanese_font_path))
        self.pdf_area_separator = PdfAreaSeparator(output_folder)
        self.logger.debug("Function end: PdfFigureExtractor.__init__ (success)")

    def _normalize_color(self, color_data: Any) -> Tuple[float, float, float]:
        """
        pdfplumberから取得した色情報をReportLabで使えるRGB形式に変換する。
        """
        if color_data is None:
            return (0, 0, 0) # デフォルトは黒
        
        if isinstance(color_data, (tuple, list)) and len(color_data) == 3:
            # すでにRGB形式
            return tuple(c / 255.0 if c > 1 else c for c in color_data) # 0-255の範囲なら0-1に変換する
        elif isinstance(color_data, (int, float)):
            # グレースケール値
            return (color_data, color_data, color_data)
        elif isinstance(color_data, str):
            # 16進数文字列の場合（例: "000000"）
            if len(color_data) == 6:
                r = int(color_data[0:2], 16) / 255.0
                g = int(color_data[2:4], 16) / 255.0
                b = int(color_data[4:6], 16) / 255.0
                return (r, g, b)
        
        self.logger.warning(f"Unknown color format: {color_data}. Defaulting to black.")
        return (0, 0, 0) # 不明な場合は黒

    def _extract_figure_as_image(self, page: Page, page_number: int, area_id: int, bbox: Tuple[float, float, float, float], unique_id: str) -> Dict[str, Any]:
        """
        指定されたバウンディングボックスの領域を画像として抽出し、その情報を返す
        """
        x0, y0, x1, y1 = bbox
        
        # 親ページのバウンディングボックスを取得する
        page_bbox = page.bbox # (x0, y0, x1, y1)
        
        # 図表のバウンディングボックスを親ページの範囲内にクリップする
        clipped_x0 = max(x0, page_bbox[0])
        clipped_y0 = max(y0, page_bbox[1])
        clipped_x1 = min(x1, page_bbox[2])
        clipped_y1 = min(y1, page_bbox[3])

        self.logger.debug(f"clipped_x0 = max({x0}, {page_bbox[0]})")
        self.logger.debug(f"clipped_y0 = max({y0}, {page_bbox[1]})")
        self.logger.debug(f"clipped_x1 = min({x1}, {page_bbox[2]})")
        self.logger.debug(f"clipped_y1 = min({y1}, {page_bbox[3]})")
        
        # クリップされたバウンディングボックスが有効な範囲を持つか確認する
        if clipped_x1 <= clipped_x0 or clipped_y1 <= clipped_y0:
            self.logger.warning(f"Clipped bbox is invalid, skipping image extraction: {bbox} -> ({clipped_x0}, {clipped_y0}, {clipped_x1}, {clipped_y1})")
            return {
                "page": page_number,
                "bbox": bbox,
                "figure_type": "empty_figure", # 無効な図表は空として扱う
                "confidence": 0.0
            }
        
        abs_tol = 0.01 * max(page_bbox[2], page_bbox[3])
        is_close_x0 = math.isclose(clipped_x0, page_bbox[0], abs_tol=abs_tol)
        is_close_y0 = math.isclose(clipped_y0, page_bbox[1], abs_tol=abs_tol)
        is_close_x1 = math.isclose(clipped_x1, page_bbox[2], abs_tol=abs_tol)
        is_close_y1 = math.isclose(clipped_y1, page_bbox[3], abs_tol=abs_tol)
        if is_close_x0 and is_close_y0 and is_close_x1 and is_close_y1:
            self.logger.warning(f"Clipped bbox is too large, skipping image extraction")
            return {
                "page": page_number,
                "bbox": bbox,
                "figure_type": "empty_figure", # 無効な図表は空として扱う
                "confidence": 0.0
            }

        self.logger.info(f"Crop image")
        
        # cropped_page.to_image()はPIL.Imageオブジェクトを返す
        # ページ全体の画像を一度生成し、そこから指定されたbboxの領域を切り出す
        page_image = page.to_image(resolution=150) # 解像度を上げて品質を向上させる
        pil_image = page_image.original
        
        # pdfplumberの座標系からPILの座標系に変換する
        # pdfplumberは左下原点、PILは左上原点な
        # また、pdfplumberの座標はPDFのポイント単位、PILの座標はピクセル単位な
        # 変換には解像度を考慮する必要がある
        
        # ページの高さと幅を取得する
        page_width = float(page.width)
        page_height = float(page.height)
        
        # PIL画像の幅と高さを取得する
        pil_width, pil_height = pil_image.size
        
        # 座標変換のスケールファクタを計算する
        scale_x = pil_width / page_width
        scale_y = pil_height / page_height
        
        # pdfplumberのbboxをPILのピクセル座標に変換する
        # pdfplumberのy座標は下から上へ、PILのy座標は上から下へなので反転させる
        pil_x0 = int(clipped_x0 * scale_x)
        pil_y0 = int((page_height - clipped_y1) * scale_y)
        pil_x1 = int(clipped_x1 * scale_x)
        pil_y1 = int((page_height - clipped_y0) * scale_y)
        
        # PILのcropメソッドで画像を切り出す
        cropped_pil_image = pil_image.crop((pil_x0, pil_y0, pil_x1, pil_y1))
        
        # 画像を一時ファイルとしてunique_idを含むディレクトリに保存するのだ
        figure_output_dir: str = os.path.join(self.output_folder, unique_id)
        os.makedirs(figure_output_dir, exist_ok=True) # unique_idディレクトリが存在しない場合は作成するのだ

        img_filename = f"figure_page{page_number}_id{area_id}.png"
        img_path = os.path.join(figure_output_dir, img_filename) # unique_idディレクトリ内に保存するのだ
        
        # 切り出した画像を直接ファイルに保存するのだ
        cropped_pil_image.save(img_path, format='PNG')
        
        self.logger.debug(f"Extracted figure as image: {img_path} for bbox {bbox}")
        return {
            "page": page_number,
            "bbox": (clipped_x0, clipped_y0, clipped_x1, clipped_y1), # クリップされたbboxを格納する
            "figure_type": "image_figure",
            "image_path": img_path,
            "width": clipped_x1 - clipped_x0,
            "height": clipped_y1 - clipped_y0,
            "confidence": 1.0
        }
 
    def extract_figures(self, pdf_path: str, current_unique_id: str) -> List[Dict[str, Any]]:
        self.logger.debug(f"Function start: extract_figures(pdf_path='{pdf_path}', current_unique_id='{current_unique_id}')")
        """
        Extracts figures from a PDF using PdfAreaSeparator block information.
        """
        figures = []
        page_and_areas = self.pdf_area_separator.extract_area_infos(pdf_path)

        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                if page_num not in page_and_areas:
                    self.logger.info(f"No areas found on page {page_num}, adding as an empty page.")
                    figures.append({
                        "page": page_num,
                        "bbox": (0, 0, float(page.width), float(page.height)),
                        "figure_type": "empty_page",
                    })
                    continue

                page_areas = page_and_areas[page_num]
                page_figures_found = 0

                for area_id, area in enumerate(page_areas):
                    # テキストブロック（red or black）は除外するのだ
                    if area.color == red or area.color == black:
                        continue
                    
                    # BBoxRLをpdfplumberのBBoxに変換するのだ
                    # BBoxRLは左下原点、Y軸上向き
                    # pdfplumberのbboxも左下原点、Y軸上向き
                    x0 = area.rect.x
                    y0 = area.rect.y
                    x1 = area.rect.x + area.rect.width
                    y1 = area.rect.y + area.rect.height
                    bbox = (x0, y0, x1, y1)
                    
                    figure_image_data = self._extract_figure_as_image(page, page_num, area_id, bbox, current_unique_id)
                    if figure_image_data["figure_type"] == "empty_figure":
                        self.logger.info(f"Figure is empty.")
                    else:
                        self.logger.info(f"Append figure {figure_image_data}")
                        figures.append(figure_image_data)
                        page_figures_found += 1

                if page_figures_found == 0:
                    self.logger.info(f"No figures detected on page {page_num}, adding as an empty page.")
                    figures.append({
                        "page": page_num,
                        "bbox": (0, 0, float(page.width), float(page.height)),
                        "figure_type": "empty_page",
                    })

        self.logger.debug("Function end: extract_figures (success)")
        return figures


    def create_figure_pdf(self, figures: List[Dict[str, Any]], output_path: str, original_pdf_path: str):
        self.logger.debug(f"Function start: create_figure_pdf(output_path='{output_path}')")
        
        with pdfplumber.open(original_pdf_path) as pdf:
            if not pdf.pages:
                self.logger.error(f"No pages found in {original_pdf_path}")
                # ページがない場合は空のPDFを作成して終了する
                c = canvas.Canvas(output_path, pagesize=A4)
                c.save()
                return

            first_page = pdf.pages[0]
            # Use the dimensions of the first page of the original PDF
            page_size = (float(first_page.width), float(first_page.height))
            c = canvas.Canvas(output_path, pagesize=page_size)

        # ページごとに図をグループ化するのだ
        figures_by_page: Dict[int, List[Dict[str, Any]]] = {}
        for figure in figures:
            page_num = figure["page"]
            if page_num not in figures_by_page:
                figures_by_page[page_num] = []
            figures_by_page[page_num].append(figure)

        # 元のPDFの総ページ数を取得するのだ
        total_pages = 0
        with pdfplumber.open(original_pdf_path) as pdf:
            total_pages = len(pdf.pages)

        # 1ページ目から最終ページまでループするのだ
        for page_number in range(1, total_pages + 1):
            if page_number in figures_by_page:
                page_figures = figures_by_page[page_number]
                for figure in page_figures:
                    figure_type = figure["figure_type"]

                    if figure_type == "image_figure":
                        x0, y0, x1, y1 = figure["bbox"]
                        # ReportLabの座標系に変換するのだ
                        # pdfplumberとReportLabは同じ座標系なので、変換は不要なのだ
                        rl_x = x0
                        rl_y = y0
                        rl_width = x1 - x0
                        rl_height = y1 - y0

                        image_path = figure.get("image_path")
                        if image_path and os.path.exists(image_path):
                            try:
                                self.logger.info(f"Drawing extracted image figure: {image_path} at ({rl_x}, {rl_y}) with size ({rl_width}, {rl_height})")
                                c.drawImage(image_path, rl_x, rl_y, width=rl_width, height=rl_height, preserveAspectRatio=True)
                            except Exception as e:
                                self.logger.error(f"Error drawing image figure {image_path}: {e}")
                        else:
                            self.logger.warning(f"Image path not found or does not exist for figure on page {page_number} with bbox {figure['bbox']}")
            
            # ページに内容が描画されたかどうかにかかわらず、必ずページを追加するのだ
            c.showPage()

        c.save()
        self.logger.debug("Function end: create_figure_pdf (success)")
