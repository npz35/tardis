# Copyright 2025 npz35
#
# See the NOTICE file for this project for license details.
# This file may not be used except in accordance with the NOTICE.

"""
Mock translation data extracted from logs/llm.log
This file contains translation pairs used for testing without calling the actual LLM API.
"""

from app.data_model import TranslationResponse

# Translation mapping extracted from logs/llm.log
# Generated from gen_sample_pdf.py test PDF
SAMPLE_PDF_TRANSLATIONS = {
    "Hello, World!": "こんにちは、世界！",
    "This is Page 1.": "これはページ1です。",
    "This is a test PDF for figure extraction across multiple pages.": "これは複数ページにわたる図抽出のためのテストPDFです。",
    "Here is an image on Page 1:": "ここに1ページ目の画像があります：",
    "This is a formula.": "これは式です。",
    "T(p, q) = { e } if pq =  e": "pq = e の場合、T(p, q) = { e }",
    "This is the left column on Page 2.": "これは2ページの左側の列です。",
    "This is the second page with another image, laid out in two columns.": "これは別の画像を含む2ページ目で、2段組みでレイアウトされています。",
    "Here is an image on Page 2, Column 1:": "2ページ、1列に画像があります：",
    "This is a passage from https://en.wikipedia.org/wiki/Apollo_11 .": "これは https://en.wikipedia.org/wiki/Apollo_11 からの文章です。",
    "Apollo 11 was the first spaceflight to land humans on the Moon, conducted by NASA from July 16 to 24, 1969.": "Apollo 11は、1969年7月16日から24日にかけてNASAによって実施された、人類を月に着陸させた最初の宇宙飛行でした。",
    "Commander Neil Armstrong and Lunar Module Pilot Edwin \"Buzz\" Aldrin landed the Lunar Module Eagle on July 20 at 20:17 UTC, and Armstrong became the first person to step onto the surface about six hours later, at 02:56 UTC on July 21.": "司令官ニール・アームストロングと月着陸船パイロットのエドウィン「バズ」・オルドリンは7月20日20:17UTCに月着陸船イーグルを着陸させ、約6時間後の7月21日02:56UTCにアームストロングが最初に月面に足を踏み入れました。",
    "Aldrin joined him 19 minutes afterward, and together they spent about two and a half hours exploring the site they had named Tranquility Base upon landing.": "その19分後、オルドリンが彼に合流し、二人は着陸後に命名した tranquility base と呼ばれる場所を調査するために約2時間半を費やした。",
    "They collected 47.5 pounds (21.5 kg) of lunar material to bring back to Earth before re-entering the Lunar Module.": "彼らは再び月着陸船に乗り込む前に、地球に持ち帰るため、47.5ポンド（21.5キログラム）の月の物質を収集した。",
    "In total, they were on the Moon's surface for 21 hours, 36 minutes before returning to the Command Module Columbia, which remained in lunar orbit, piloted by Michael Collins.": "合計して、彼らは月面に21時間36分滞在し、その後月軌道上に留まっていたマイケル・コリンズが操縦した司令船コロンビアに帰還しました。",
    "Apollo 11 was launched by a Saturn V rocket from Kennedy Space Center in Florida, on July 16 at 13:32 UTC (9:32 am EDT, local time).": "アポロ11号は、フロリダ州のケネディ宇宙センターから、7月16日UTC午後1時32分（現地時間午前9時32分EDT）にサターンVロケットにより打ち上げられました。",
    "It was the fifth crewed mission of the Apollo program.": "それはアポロ計画の5番目の有人ミッションでした。",
    "The Apollo spacecraft consisted of three parts: the command module (CM), which housed the three astronauts and was the only part to return to Earth; the service module (SM), which provided propulsion, electrical power, oxygen, and water to the command module; and the Lunar Module (LM), which had two stages—a descent stage with a large engine and fuel tanks for landing on the Moon, and a lighter ascent stage containing a cabin for two astronauts and a small engine to return them to lunar orbit.": "アポロ宇宙船は三つの部分で構成されていました。宇宙飛行士三人が搭乗し、地球に帰還する唯一の部分であった司令船（CM）、司令船に推進力、電力、酸素、水を供給したサービスモジュール（SM）、そして二つの段階を持つ月着陸船（LM）です。月面に着陸するための大きなエンジンと燃料タンクを備えた降下段階と、二人の宇宙飛行士のためのキャビンと、彼らを月の軌道に戻すための小型エンジンを内蔵したより軽量な上昇段階です。",
    "After being sent to the Moon by the Saturn V's third stage, the astronauts separated the spacecraft from it.": "サターンVの第3段階によって月に送られた後、宇宙飛行たちは宇宙船からそれを分離した。",
    "This is the text at the bottom left of page 2.": "これは2ページの左下のテキストです。",
    "This is the text at the top right of page 2.": "これは2ページの右上にある文章です。",
    "Armstrong and Aldrin then moved into Eagle and landed in the Mare Tranquillitatis on July 20.": "その後、アームストロングとオルドリンはイーグル号に移動し、7月20日に静かの海に着陸しました。",
    "The astronauts used Eagle's ascent stage to lift off from the lunar surface and rejoin Collins in the command module.": "宇宙飛行たちはイーグルの上昇段階を使用して月面から離陸し、指令モジュールでコリンズと合流しました。",
    "They jettisoned Eagle before they performed the maneuvers that propelled Columbia out of the last of its 30 lunar orbits onto a trajectory back to Earth.": "彼らはコロンビアを30周目の月軌道から地球への軌道に乗せる機動動作を実行する前に、イーグルを投棄した。",
    "[9] They returned to Earth and splashed down in the Pacific Ocean on July 24 at 16:35:35 UTC after more than eight days in space.": "[9] 彼らは8日以上宇宙に滞在した後、7月24日16時35分35分UTCに太平洋に着水し、地球に帰還した。",
}


def create_mock_translation_response(original_text: str, source_lang: str = 'English', target_lang: str = 'Japanese') -> TranslationResponse:
    """
    Create a mock TranslationResponse based on the predefined translation mapping.
    
    Args:
        original_text: The original text to translate
        source_lang: Source language (default: 'English')
        target_lang: Target language (default: 'Japanese')
        
    Returns:
        TranslationResponse with mocked translation data
    """
    translated_text = SAMPLE_PDF_TRANSLATIONS.get(original_text, original_text)
    
    return TranslationResponse(
        success=True,
        error=None,
        original_text=original_text,
        translated_text=translated_text,
        source_lang=source_lang,
        target_lang=target_lang,
        model='mock-model',
        tokens_used=100,
        processing_time=0.1,
        status_code=200,
        attempts=1
    )


def create_mock_translation_responses(texts: list[str], source_lang: str = 'English', target_lang: str = 'Japanese') -> list[TranslationResponse]:
    """
    Create mock TranslationResponse list for multiple texts.
    
    Args:
        texts: List of original texts to translate
        source_lang: Source language (default: 'English')
        target_lang: Target language (default: 'Japanese')
        
    Returns:
        List of TranslationResponse with mocked translation data
    """
    return [create_mock_translation_response(text, source_lang, target_lang) for text in texts]