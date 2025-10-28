# Copyright 2025 npz35
#
# See the NOTICE file for this project for license details.
# This file may not be used except in accordance with the NOTICE.

from dataclasses import dataclass
import math
from typing import List, Optional, Tuple, Dict, Any
from reportlab.lib.colors import Color


@dataclass
class FontInfo:
    name: str
    size: float
    is_bold: bool
    is_italic: bool


@dataclass
class BBox:
    x0: float
    y0: float
    x1: float
    y1: float

    def width(self) -> float:
        return abs(self.x1 - self.x0)

    def height(self) -> float:
        return abs(self.y1 - self.y0)

@dataclass
class CharBlock:
    char: str
    bbox: BBox
    font_info: FontInfo
    page_number: int

    def width(self) -> float:
        return abs(self.bbox.x1 - self.bbox.x0)

    def height(self) -> float:
        return abs(self.bbox.y1 - self.bbox.y0)

@dataclass
class WordBlock:
    word: str
    bbox: BBox
    font_info: FontInfo
    page_number: int

    def width(self) -> float:
        return abs(self.bbox.x1 - self.bbox.x0)

    def height(self) -> float:
        return abs(self.bbox.y1 - self.bbox.y0)

@dataclass
class TextBlock:
    text: str
    bbox: BBox
    font_info: FontInfo
    page_number: int
    column_index: int = -1

    def width(self) -> float:
        return abs(self.bbox.x1 - self.bbox.x0)

    def height(self) -> float:
        return abs(self.bbox.y1 - self.bbox.y0)

class TextArea:
    blocks: List[TextBlock] = []
    bbox: BBox = BBox(x0=math.inf, x1=-math.inf, y0=math.inf, y1=-math.inf)

    def __init__(self, blocks: List[TextBlock], bbox: BBox):
        self.blocks = blocks
        self.bbox = bbox

    def append(self, block: TextBlock):
        self.blocks.append(block)
        self.bbox.x0 = min(self.bbox.x0, block.bbox.x0)
        self.bbox.x1 = max(self.bbox.x1, block.bbox.x1)
        self.bbox.y0 = min(self.bbox.y0, block.bbox.y0)
        self.bbox.y1 = max(self.bbox.y1, block.bbox.y1)
    
    def text(self) -> str:
        return ' '.join([block.text for block in self.blocks])

@dataclass
class Word:
    left: float
    right: float
    text: str

@dataclass
class RightSideWord:
    left: float
    middle_x: float
    text: str

    MAX_RIGHT_SIDE_DIST = 999.0

    def dist(self) -> float:
        return self.left - self.middle_x

    def on_border_range(self) -> bool:
        return self.dist() <= self.MAX_RIGHT_SIDE_DIST

@dataclass
class WordsBorderGap:
    left: float
    right: float
    top: float
    bottom: float
    right_side_word: RightSideWord
    
    MIN_COLUMN_BOUNDARY_WIDTH = 5.0 # Adjusted based on user feedback and logs
    MIDDLE_PAGE_RANGE_FACTOR = 0.1

    def width(self) -> float:
        return self.right - self.left
    
    def center_x(self) -> float:
        return (self.right + self.left) / 2

    def center_y(self) -> float:
        return (self.top + self.bottom) / 2
    
    def is_valid(self, middle_x: float) -> bool:
        if self.right < middle_x:
            return False
        if middle_x < self.left:
            return False
        if self.width() < self.MIN_COLUMN_BOUNDARY_WIDTH:
            return False
        return True
    
    def on_border_range(self, page_width: float) -> bool:
        middle_x = page_width / 2
        center = (self.left + self.right) / 2
        abs_diff = abs(center - middle_x)
        return abs_diff < page_width * self.MIDDLE_PAGE_RANGE_FACTOR

@dataclass
class Line:
    # The origin is at the bottom left
    y0: float
    y1: float
    x0: float
    x1: float

    # The origin is at the top left
    top: float
    bottom: float

    is_two_column: bool

    def height(self) -> float:
        return self.y1 - self.y0

@dataclass
class PageAnalyzeData:
    page_num: int
    page_width: float
    page_height: float
    column_boundary_data: Optional[Tuple[WordsBorderGap, float, float]] # (closest_central_gap, border_bottom, border_top)
    blue_crosses_data: List[WordsBorderGap] # all_gaps_on_border_range

class BBoxRL:
    """
    ReportLabの座標系に合わせたBounding Boxクラスなのだ。
    x, yは左下隅の座標、width, heightは幅と高さなのだ。
    """
    def __init__(self, x: float, y: float, width: float, height: float):
        self.x = x
        self.y = y
        self.width = width
        self.height = height

    def __repr__(self):
        return f"BBoxRL(x={self.x:.2f}, y={self.y:.2f}, width={self.width:.2f}, height={self.height:.2f})"

@dataclass
class Area:
    color: Color
    rect: BBoxRL
    text: str = "" # テキストブロックのテキストを追加するのだ
    block_id: Optional[int] = None # テキストブロックのIDを追加するのだ
    font_info: Dict[str, Any] = None # フォント情報を追加するのだ
