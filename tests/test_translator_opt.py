# Copyright 2025 npz35
#
# See the NOTICE file for this project for license details.
# This file may not be used except in accordance with the NOTICE.

import unittest

from app.translator import Translator

class TestTranslatorOpt(unittest.TestCase):
    """Tests for the Translator class"""

    def setUp(self):
        """Setup executed before each test method"""
        self.translator = Translator(api_url="http://test-api.example.com", model="test-model")

    def test_clean_translation_empty_string(self):
        """Test _clean_translation with an empty string"""
        self.assertEqual(self.translator._clean_translation(""), "")

    def test_clean_translation_whitespace(self):
        """Test _clean_translation with extra whitespace"""
        self.assertEqual(self.translator._clean_translation("  Hello World  "), "Hello World")
        self.assertEqual(self.translator._clean_translation("\tHello\nWorld\t"), "Hello\nWorld")

    def test_clean_translation_newlines(self):
        """Test _clean_translation with various newline characters"""
        self.assertEqual(self.translator._clean_translation("Line1\r\nLine2\rLine3"), "Line1\nLine2\nLine3")
        self.assertEqual(self.translator._clean_translation("Line1\rLine2"), "Line1\nLine2")

    def test_clean_translation_prefixes(self):
        """Test _clean_translation with unnecessary prefixes"""
        self.assertEqual(self.translator._clean_translation("Japanese translation: Hello"), "Hello")
        self.assertEqual(self.translator._clean_translation("日本語訳: こんにちは"), "こんにちは")
        self.assertEqual(self.translator._clean_translation("Translation: Test"), "Test")
        self.assertEqual(self.translator._clean_translation("Japanese: Text"), "Text")
        self.assertEqual(self.translator._clean_translation("日本語: テキスト"), "テキスト")
        self.assertEqual(self.translator._clean_translation("翻訳: テスト"), "テスト")
        self.assertEqual(self.translator._clean_translation("translation: test"), "test")

    def test_clean_translation_suffixes(self):
        """Test _clean_translation with unnecessary suffixes"""
        self.assertEqual(self.translator._clean_translation("Hello translation"), "Hello")
        self.assertEqual(self.translator._clean_translation("こんにちは訳"), "こんにちは")
        self.assertEqual(self.translator._clean_translation("Test Translation"), "Test")
        self.assertEqual(self.translator._clean_translation("テスト翻訳"), "テスト")

    def test_clean_translation_combined(self):
        """Test _clean_translation with combined cleaning operations"""
        text = "  Japanese translation: \r\n  Hello World \t translation \r "
        expected = "Hello World"
        self.assertEqual(self.translator._clean_translation(text), expected)

        text2 = "日本語訳: \n テストテキスト 翻訳 "
        expected2 = "テストテキスト"
        self.assertEqual(self.translator._clean_translation(text2), expected2)

    def test_is_invalid_translation_with_ok_response(self):
        """Test if translation result 'OK' is considered invalid"""
        original_text = "Hello, world!"
        invalid_translation = "OK"
        
        result = self.translator._is_invalid_translation(original_text, invalid_translation)
        
        self.assertTrue(result, "Translation result 'OK' should be considered invalid")

    def test_is_invalid_translation_with_short_response(self):
        """Test if translation result is too short and considered invalid"""
        original_text = "Hello, world!"
        invalid_translation = "はい"
        
        result = self.translator._is_invalid_translation(original_text, invalid_translation)
        
        self.assertTrue(result, "Translation result less than 3 characters should be considered invalid")

    def test_is_invalid_translation_with_same_text(self):
        """Test if translation result is the same as original text and considered invalid"""
        original_text = "Hello, world!"
        invalid_translation = "Hello, world!"
        
        result = self.translator._is_invalid_translation(original_text, invalid_translation)
        
        self.assertFalse(result, "Translation result same as original text should be considered valid") # TODO

    def test_is_invalid_translation_with_invalid_responses(self):
        """Test if translation result is an inappropriate word and considered invalid"""
        original_text = "Hello, world!"
        invalid_responses = ["OK", "ok", "Okay", "okay", "Yes", "yes", "No", "no", 
                           "はい", "いいえ", "OKです", "了解", "承知いたしました"]
        
        for invalid_response in invalid_responses:
            with self.subTest(response=invalid_response):
                result = self.translator._is_invalid_translation(original_text, invalid_response)
                self.assertTrue(result, f"Translation result '{invalid_response}' should be considered invalid")

    def test_is_invalid_translation_with_valid_response(self):
        """Test if translation result is appropriate and not considered invalid"""
        original_text = "Hello, world!"
        valid_translation = "こんにちは、世界！"
        
        result = self.translator._is_invalid_translation(original_text, valid_translation)
        
        self.assertFalse(result, "Appropriate translation result should not be considered invalid")

    def test_is_invalid_translation_with_empty_response(self):
        """Test if translation result is empty and considered invalid"""
        original_text = "Hello, world!"
        invalid_translation = ""
        
        result = self.translator._is_invalid_translation(original_text, invalid_translation)
        
        self.assertTrue(result, "Empty translation result should be considered invalid")