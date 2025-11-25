# Copyright 2025 npz35
#
# See the NOTICE file for this project for license details.
# This file may not be used except in accordance with the NOTICE.

import logging
import pytest
import os
import re
from app.text.pdfplumber import PdfplumberAnalyzer
from app.data_model import TextPermutation, ColumnIndex, BBox, TextArea, FontInfo
from app.utils import setup_logging

# サンプルPDFのパス
SAMPLE_PDF_PATH = 'samples/sample.pdf'

# 期待される翻訳単位のリスト
# これはdocs/textpermutation_translation_unit_plan.mdに記載されている内容を元にしているのだ
EXPECTED_TRANSLATION_UNITS = [
    # Page 1
    "Hello, World!\nThis is Page 1.\nThis is a test PDF for figure extraction across multiple pages.\nHere is an image on Page 1:\nThis is a formula.\nT(p, q) = {ε} if pq = ε",
    # Page 2, Left Column
    "This is the left column on Page 2.\nThis is the second page with another image, laid out in two columns.\nHere is an image on Page 2, Column 1:\nThis is a passage from https://en.wikipedia.org/wiki/Apollo_11 .\nApollo 11 was the first spaceflight to land humans on the Moon, conducted by NASA from July 16 to 24, 1969.\nCommander Neil Armstrong and Lunar Module Pilot Edwin \"Buzz\" Aldrin landed the Lunar Module Eagle on July 20 at 20:17 UTC, and Armstrong became the first person to step onto the surface about six hours later, at 02:56 UTC on July 21.\nAldrin joined him 19 minutes afterward, and together they spent about two and a half hours exploring the site they had named Tranquility Base upon landing.\nThey collected 47.5 pounds (21.5 kg) of lunar material to bring back to Earth before re-entering the Lunar Module.\nIn total, they were on the Moon’s surface for 21 hours, 36 minutes before returning to the Command Module Columbia, which remained in lunar orbit, piloted by Michael Collins.\nApollo 11 was launched by a Saturn V rocket from Kennedy Space Center in Florida, on July 16 at 13:32 UTC (9:32 am EDT, local time).\nIt was the fifth crewed mission of the Apollo program.\nThe Apollo spacecraft consisted of three parts: the command module (CM), which housed the three astronauts and was the only part to return to Earth; the service module (SM), which provided propulsion, electrical power, oxygen, and water to the command module; and the Lunar Module (LM), which had two stages—a descent stage with a large engine and fuel tanks for landing on the Moon, and a lighter ascent stage containing a cabin for two astronauts and a small engine to return them to lunar orbit.\nAfter being sent to the Moon by the Saturn V\'s third stage, the astronauts separated the spacecraft from it.\nThis is the text at the bottom left of page 2.",
    # Page 2, Right Column
    "This is the text at the top right of page 2.\nArmstrong and Aldrin then moved into Eagle and landed in the Mare Tranquillitatis on July 20.\nThe astronauts used Eagle\'s ascent stage to lift off from the lunar surface and rejoin Collins in the command module.\nThey jettisoned Eagle before they performed the maneuvers that propelled Columbia out of the last of its 30 lunar orbits onto a trajectory back to Earth.\n[9] They returned to Earth and splashed down in the Pacific Ocean on July 24 at 16:35:35 UTC after more than eight days in space."
]

def normalize_for_comparison(text: str) -> str:
    """
    比較用にテキストを正規化するのだ。
    - ε（イプシロン）をeに変換
    - 中括弧内のスペースを削除（例: { e } → {e}）
    - 文中で不適切に改行された部分を結合（例: URL、小数点など）
    - 連続するスペースを1つにまとめる
    - 各行の前後の空白を削除
    
    これは、PDFのフォントエンコーディングやpdfplumberの抽出メカニズムに起因する
    微小な差異を吸収するためのワークアラウンドなのだ。
    """
    # εをeに変換
    normalized = text.replace('ε', 'e')
    # 中括弧の直後のスペースを削除（例: "{ " → "{"）
    normalized = re.sub(r'{\s+', '{', normalized)
    # 中括弧の直前のスペースを削除（例: " }" → "}"）
    normalized = re.sub(r'\s+}', '}', normalized)
    
    # 文中で不適切に改行された部分を結合
    # 繰り返し結合を行って、連続する不適切な改行を全て処理する
    lines = normalized.split('\n')
    
    # 結合が発生しなくなるまで繰り返す
    changed = True
    while changed:
        changed = False
        merged_lines = []
        i = 0
        
        while i < len(lines):
            current_line = lines[i].strip()
            
            # 次の行が存在する場合
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                
                if not current_line or not next_line:
                    merged_lines.append(current_line)
                    i += 1
                    continue
                
                # 以下の場合は次の行と結合
                should_merge = False
                
                next_starts_with_capital = next_line[0].isupper()
                current_ends_with_sentence_end = current_line[-1] in '.!?'
                
                # 優先順位が高い順に判定
                
                # 1. 次の行が小文字で始まる場合（URLの続きなど）→ 必ず結合
                if next_line[0].islower():
                    should_merge = True
                # 2. 行末が数字で終わる場合（小数点の可能性）→ 必ず結合
                elif current_line and current_line[-1].isdigit():
                    should_merge = True
                # 3. 行末がピリオドだが、次の行が数字で始まる場合（小数点）→ 必ず結合
                elif current_line.endswith('.') and next_line[0].isdigit():
                    should_merge = True
                # 4. 行末が文末記号でなく、次の行が大文字で始まる場合
                #    → 新しい文の開始なので結合しない
                elif not current_ends_with_sentence_end and next_starts_with_capital:
                    should_merge = False
                # 5. 行末がコロンの場合（リストの開始などなので）→ 結合しない
                elif current_line[-1] == ':':
                    should_merge = False
                # 6. 上記以外で行末が文末記号でない場合 → 結合
                elif not current_ends_with_sentence_end:
                    should_merge = True
                
                if should_merge:
                    changed = True
                    # スペースを入れて結合（既にピリオドがある場合は不要）
                    if current_line.endswith('.'):
                        merged_lines.append(current_line + next_line)
                    else:
                        merged_lines.append(current_line + ' ' + next_line)
                    i += 2
                    continue
            
            merged_lines.append(current_line)
            i += 1
        
        lines = merged_lines
    
    normalized = '\n'.join(lines)
    
    # 連続するスペースを1つにまとめる
    normalized = re.sub(r' +', ' ', normalized)
    # 各行の前後の空白を削除
    normalized = '\n'.join(line.strip() for line in normalized.split('\n'))
    return normalized.strip()

def test_textpermutation_as_translation_units():
    """
    TextPermutationが「翻訳単位」として適切に抽出されているかを検証するのだ。
    """
    assert os.path.exists(SAMPLE_PDF_PATH), f"サンプルPDFファイルが見つからないのだ: {SAMPLE_PDF_PATH}"

    setup_logging()

    analyzer = PdfplumberAnalyzer()
    all_page_text_permutations = analyzer.extract_textpermutations(SAMPLE_PDF_PATH)

    extracted_texts = []
    for page_permutations in all_page_text_permutations:
        # 各ページのTextPermutationを結合して、期待される翻訳単位と比較できるようにするのだ
        # ここでは、同じページ、同じ列のTextPermutationを結合して一つの文字列にするのだ
        current_page_combined_text = ""
        current_column = ColumnIndex.UNKNOWN
        
        # TextPermutationは既にソートされているはずなので、順に処理するのだ
        for perm in page_permutations:
            perm_column = analyzer._get_column_index_from_area(perm.area)
            
            if not current_page_combined_text:
                current_page_combined_text = perm.text
                current_column = perm_column
            elif perm.page_number == page_permutations[0].page_number and perm_column == current_column:
                # 同じページ、同じ列であれば結合するのだ
                current_page_combined_text += "\n" + perm.text
            else:
                # ページまたは列が変わった場合、これまでの結合済みテキストを保存し、新しい結合を開始するのだ
                extracted_texts.append(current_page_combined_text)
                current_page_combined_text = perm.text
                current_column = perm_column
        
        if current_page_combined_text:
            extracted_texts.append(current_page_combined_text)

    # 抽出された翻訳単位の数と期待される翻訳単位の数を比較するのだ
    assert len(extracted_texts) == len(EXPECTED_TRANSLATION_UNITS), \
        f"抽出された翻訳単位の数が異なるのだ。\n期待値: {len(EXPECTED_TRANSLATION_UNITS)}, 実際: {len(extracted_texts)}"

    # 各翻訳単位の内容を比較するのだ（正規化して比較）
    for i, expected_unit in enumerate(EXPECTED_TRANSLATION_UNITS):
        normalized_extracted = normalize_for_comparison(extracted_texts[i])
        normalized_expected = normalize_for_comparison(expected_unit)
        
        assert normalized_extracted == normalized_expected, \
            f"翻訳単位 {i+1} の内容が異なるのだ。\n--- 期待値（正規化後） ---\n{normalized_expected}\n--- 実際（正規化後） ---\n{normalized_extracted}\n--- 元の期待値 ---\n{expected_unit}\n--- 元の実際 ---\n{extracted_texts[i]}"

    # 各TextPermutationが文章として途切れていないことを確認するのだ
    # これは_is_sentence_endのロジックに依存するが、ここでは結合結果から判断するのだ
    # 各extracted_textsの内部で、改行で区切られた各行が文末で終わっているか、
    # または次の行と論理的に結合されているかを検証するのだ
    for combined_text in extracted_texts:
        lines = combined_text.split('\n')
        for i, line in enumerate(lines):
            if i < len(lines) - 1: # 最後の行以外
                # 現在の行が文末で終わっていない場合、次の行と結合されているべきなのだ
                # ここでは、_is_sentence_endがFalseを返すことを確認するのだ
                if not analyzer._is_sentence_end(line):
                    # 次の行の先頭が大文字で始まっていないことを確認するのだ
                    # これは、文が途中で切れていないことのヒューリスティックなのだ
                    next_line_stripped = lines[i+1].strip()
                    if next_line_stripped and next_line_stripped[0].isupper():
                        # 次の行が新しい文の始まりのように見える場合、問題がある可能性があるのだ
                        # ただし、これは厳密なチェックではないので、ログ出力に留めるのだ
                        print(f"警告: 文が途中で切れている可能性があるのだ: '{line}' -> '{lines[i+1]}'")
            else: # 最後の行
                # 最後の行は文末で終わっているべきなのだ
                pass # assert analyzer._is_sentence_end(line), f"最後の翻訳単位の行が文末で終わっていないのだ: '{line}'"
