# Copyright 2025 npz35
#
# See the NOTICE file for this project for license details.
# This file may not be used except in accordance with the NOTICE.

from dataclasses import dataclass, field
import math
from enum import Enum
from typing import Optional, Any
from reportlab.lib.colors import Color


@dataclass
class UserRequest:
    filepath: str
    filename: str
    unique_id: str


@dataclass
class LLMResponse:
    success: bool
    error: str
    status_code: int
    response_json: Any
    translated_text: str
    is_formula: bool
    skip_translation: bool


@dataclass
class HealthResponse:
    success: bool
    error: str
    api_url: str
    model: str
    model_available: bool
    available_models: list[dict[str, Any]]


@dataclass
class ModelResponse:
    success: bool
    error: str
    model_info: dict[str, Any]


@dataclass
class TranslationResponse:
    source_lang: str
    target_lang: str
    model: str
    success: bool = False
    error: Optional[str] = 'Unexecuted'
    original_text: Optional[str] = None
    translated_text: Optional[str] = None
    tokens_used: int = 0
    processing_time: float = 0.0
    status_code: Optional[int] = None
    attempts: int = 0


@dataclass
class FontInfo:
    name: str
    size: float
    is_bold: bool
    is_italic: bool

    def __repr__(self):
        return f'FontInfo(name=\'{self.name}\', size={self.size:.2f}, is_bold={self.is_bold}, is_italic={self.is_italic})'

@dataclass
class BBox:
    # The origin is at the bottom left
    x0: float
    y0: float
    x1: float
    y1: float

    def __repr__(self):
        return f'BBox(x0={self.x0:.2f}, y0={self.y0:.2f}, x1={self.x1:.2f}, y1={self.y1:.2f})'

    def width(self) -> float:
        return abs(self.x1 - self.x0)

    def height(self) -> float:
        return abs(self.y1 - self.y0)

class ColumnIndex(Enum):
    UNKNOWN = -1
    LEFT = 0
    RIGHT = 1

@dataclass
class CharBlock:
    char: str
    bbox: BBox
    font_info: FontInfo
    page_number: int
    column_index: ColumnIndex = ColumnIndex.UNKNOWN

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
    column_index: ColumnIndex = ColumnIndex.UNKNOWN

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
    column_index: ColumnIndex = ColumnIndex.UNKNOWN

    def width(self) -> float:
        return abs(self.bbox.x1 - self.bbox.x0)

    def height(self) -> float:
        return abs(self.bbox.y1 - self.bbox.y0)

@dataclass
class TextArea:
    blocks: list[TextBlock] = field(default_factory=list)
    bbox: BBox = field(default_factory=lambda: BBox(x0=math.inf, x1=-math.inf, y0=math.inf, y1=-math.inf))
    page_number: int = -1 # Default to -1, will be set when the first block is appended or in __post_init__

    def __repr__(self):
        return f'TextArea(bbox=\'{self.bbox}\', page_number={self.page_number})'

    def __post_init__(self):
        if self.blocks: # Only run if blocks are provided during initialization
            # Ensure bbox covers all blocks
            self.bbox.x0 = min(block.bbox.x0 for block in self.blocks)
            self.bbox.y0 = min(block.bbox.y0 for block in self.blocks)
            self.bbox.x1 = max(block.bbox.x1 for block in self.blocks)
            self.bbox.y1 = max(block.bbox.y1 for block in self.blocks)
            self.page_number = self.blocks[0].page_number # All blocks in a TextArea should be on the same page

    def append(self, block: TextBlock):
        if not self.blocks:
            self.blocks.append(block)
            self.bbox = BBox(x0=block.bbox.x0, y0=block.bbox.y0, x1=block.bbox.x1, y1=block.bbox.y1)
            self.page_number = block.page_number
        else:
            self.blocks.append(block)
            self.bbox.x0 = min(self.bbox.x0, block.bbox.x0)
            self.bbox.x1 = max(self.bbox.x1, block.bbox.x1)
            self.bbox.y0 = min(self.bbox.y0, block.bbox.y0)
            self.bbox.y1 = max(self.bbox.y1, block.bbox.y1)
    
    def text(self) -> str:
        return ' '.join([block.text for block in self.blocks])

@dataclass
class TextPermutation:
    area: TextArea
    text: str # TODO: Change to "texts: list[str]"
    page_number: int
    font_info: Optional[FontInfo] = None # Add font_info to TextPermutation

@dataclass
class TranslatedUnit:
    bbox: BBox
    text: str
    page_number: int
    font_info: Optional[FontInfo] = None
    area: Optional[TextArea] = None

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

    def __repr__(self):
        return f'RightSideWord(left={self.left:.2f}, middle_x={self.middle_x:.2f}, text="{self.text}")'

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
    
    def distance_from_center(self, page_width: float) -> float:
        middle_x = page_width / 2
        return abs(self.center_x() - middle_x)

    def on_border_range(self, page_width: float) -> bool:
        return self.distance_from_center(page_width) < page_width * self.MIDDLE_PAGE_RANGE_FACTOR

@dataclass
class ColumnType:
    # The origin is at the bottom left
    bbox: BBox
    page_height: float

    is_two_column: bool

    def top(self) -> float:
        # The origin is at the top left
        return self.page_height - self.bbox.y1

    def bottom(self) -> float:
        # The origin is at the top left
        return self.page_height - self.bbox.y0

    def height(self) -> float:
        return self.bbox.y1 - self.bbox.y0

@dataclass
class PageAnalyzeData:
    page_idx: int
    page_width: float
    page_height: float
    column_boundary_data: Optional[tuple[WordsBorderGap, float, float]] # (closest_central_gap, border_bottom, border_top)
    blue_crosses_data: list[WordsBorderGap] # all_gaps_on_border_range

@dataclass
class Area:
    page_number: int # 1-idx
    color: Color
    bbox: BBox
    text: str = ''
    block_id: Optional[int] = None
    font_info: Optional[FontInfo] = None
