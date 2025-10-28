# Copyright 2025 npz35
#
# See the NOTICE file for this project for license details.
# This file may not be used except in accordance with the NOTICE.

import unittest
from unittest.mock import patch, MagicMock
import requests

from app.translator import Translator

class TestTranslator(unittest.TestCase):
    """Tests for the Translator class"""

    def setUp(self):
        """Setup executed before each test method"""
        self.translator = Translator(api_url="http://test-api.example.com", model="test-model")

    @patch('app.llm.requests.Session.post')
    def test_translate_text_success(self, mock_post):
        """Normal case: Ensure appropriate text can be translated"""
        # Set up mock response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": "chatcmpl-test-id",
            "object": "chat.completion",
            "created": 1234567890,
            "model": "test-model",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "<llm><response><translated_text>これはテスト翻訳です。</translated_text><is_formula>false</is_formula><skip_translation>false</skip_translation></response></llm>",
                        "refusal": None,
                        "annotations": []
                    },
                    "logprobs": None,
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": 15,
                "completion_tokens": 8,
                "total_tokens": 23,
                "prompt_tokens_details": {
                    "cached_tokens": 0,
                    "audio_tokens": 0
                },
                "completion_tokens_details": {
                    "reasoning_tokens": 0,
                    "audio_tokens": 0,
                    "accepted_prediction_tokens": 0,
                    "rejected_prediction_tokens": 0
                }
            },
            "service_tier": "default"
        }
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        # Execute test
        result = self.translator.translate_texts(["This is a test text."])

        # Verify result
        self.assertTrue(result[0]["success"])
        self.assertEqual(result[0]["original_text"], "This is a test text.")
        self.assertEqual(result[0]["translated_text"], "これはテスト翻訳です。")
        self.assertEqual(result[0]["source_lang"], "English")
        self.assertEqual(result[0]["target_lang"], "Japanese")
        self.assertEqual(result[0]["model"], "test-model")

    def test_translate_text_empty_text(self):
        """Error case: Handling when an empty text is passed"""
        # テスト実行
        result = self.translator.translate_texts([""])

        # 結果の検証
        self.assertFalse(result[0]["success"])
        self.assertIn("Text to translate is empty", result[0]["error"])

    def test_translate_text_too_long_text(self):
        """Error case: Handling when text is too long"""
        # Create excessively long text
        long_text = "a" * 10001  # 10001文字のテキスト

        # テスト実行
        result = self.translator.translate_texts([long_text])

        # 結果の検証
        self.assertFalse(result[0]["success"])
        self.assertIn("Text to translate is too long", result[0]["error"])

    @patch('app.llm.requests.Session.post')
    def test_translate_text_timeout_error(self, mock_post):
        """Error case: Handling timeout"""
        # Set up mock response (simulate timeout)
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": ""}}] # Empty content to trigger error
        }
        mock_post.side_effect = requests.exceptions.Timeout("Timeout")
        mock_post.return_value = mock_response # Ensure mock_post returns something for the json() call

        # テスト実行
        result = self.translator.translate_texts(["This is a test text."])

        # 結果の検証
        self.assertFalse(result[0]["success"])
        self.assertIn("Translation failed (3 attempts)", result[0]["error"])

    @patch('app.llm.requests.Session.post')
    def test_translate_text_connection_error(self, mock_post):
        """Error case: Handling connection error"""
        # Set up mock response (simulate connection error)
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": ""}}] # Empty content to trigger error
        }
        mock_post.side_effect = requests.exceptions.ConnectionError("Connection Error")
        mock_post.return_value = mock_response # Ensure mock_post returns something for the json() call

        # テスト実行
        result = self.translator.translate_texts(["This is a test text."])

        # 結果の検証
        self.assertFalse(result[0]["success"])
        self.assertIn("Failed to connect to API", result[0]["error"])

    @patch('app.llm.requests.Session.post')
    def test_translate_text_http_error(self, mock_post):
        """Error case: Handling HTTP error"""
        # Set up mock response (simulate HTTP error)
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": ""}}] # Empty content to trigger error
        }
        # Pass the response object to raise HTTPError
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("HTTP Error", response=mock_response)
        mock_response.status_code = 400
        mock_post.return_value = mock_response

        # テスト実行
        result = self.translator.translate_texts(["This is a test text."])

        # 結果の検証
        self.assertFalse(result[0]["success"])
        self.assertIn("Translation failed (3 attempts)", result[0]["error"])

    @patch('app.llm.requests.Session.post')
    def test_translate_text_empty_response_retry(self, mock_post):
        """Test if retries occur when translation result is empty"""
        # MagicMock returning an empty response
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "choices": [{"message": {"content": ""}}]
        }
        mock_post.return_value = mock_response
        
        # Execute translation
        result = self.translator.translate_texts(["Hello, world!"])
        
        # Verify result
        self.assertFalse(result[0]["success"], "Should fail if translation result is empty")
        self.assertIn("Translation failed (3 attempts)", result[0]["error"])
        self.assertEqual(result[0]["attempts"], 3, "3 retries should have been attempted")

    @patch('app.llm.requests.Session.post')
    def test_translate_text_success_after_retry(self, mock_post):
        """Test if translation succeeds after retries when result is invalid"""
        
        # MagicMock returning invalid responses for the first two attempts and a valid one for the third
        mock_response_invalid = MagicMock()
        mock_response_invalid.raise_for_status.return_value = None
        mock_response_invalid.json.return_value = {
            "choices": [{"message": {"content": "OK"}}]
        }
        
        mock_response_valid = MagicMock()
        mock_response_valid.raise_for_status.return_value = None
        mock_response_valid.json.return_value = {
            "choices": [{"message": {"content": "<llm><response><translated_text>こんにちは、世界！</translated_text><is_formula>false</is_formula><skip_translation>false</skip_translation></response></llm>"}}]
        }
        
        # Return invalid responses for the first two attempts and a valid one for the third
        mock_post.side_effect = [mock_response_invalid, mock_response_invalid, mock_response_valid]
        
        # Execute translation
        result = self.translator.translate_texts(["Hello, world!"])
        
        # Verify result
        self.assertTrue(result[0]["success"], "Should succeed if the final translation result is valid")
        self.assertEqual(result[0]["translated_text"], "こんにちは、世界！", "Translation result should be correct")
        self.assertEqual(result[0]["attempts"], 3, "3 attempts should have been made")

    @patch('app.llm.requests.Session.post')
    def test_translate_texts_success(self, mock_post):
        """Normal case: Ensure multiple texts can be translated"""
        # Set up mock response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": "chatcmpl-test-id",
            "object": "chat.completion",
            "created": 1234567890,
            "model": "test-model",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "<llm><response><translated_text>こんにちは世界。</translated_text><is_formula>false</is_formula><skip_translation>false</skip_translation></response><response><translated_text>テストテキストです。</translated_text><is_formula>false</is_formula><skip_translation>false</skip_translation></response></llm>",
                        "refusal": None,
                        "annotations": []
                    },
                    "logprobs": None,
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": 30,
                "completion_tokens": 16,
                "total_tokens": 46,
                "prompt_tokens_details": {
                    "cached_tokens": 0,
                    "audio_tokens": 0
                },
                "completion_tokens_details": {
                    "reasoning_tokens": 0,
                    "audio_tokens": 0,
                    "accepted_prediction_tokens": 0,
                    "rejected_prediction_tokens": 0
                }
            },
            "service_tier": "default"
        }
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        # Execute test
        texts_to_translate = ["Hello world.", "This is a test text."]
        results = self.translator.translate_texts(texts_to_translate)

        # Verify results
        self.assertEqual(len(results), 2)

        self.assertTrue(results[0]["success"])
        self.assertEqual(results[0]["original_text"], "Hello world.")
        self.assertEqual(results[0]["translated_text"], "こんにちは世界。")
        self.assertEqual(results[0]["source_lang"], "English")
        self.assertEqual(results[0]["target_lang"], "Japanese")
        self.assertEqual(results[0]["model"], "test-model")

        self.assertTrue(results[1]["success"])
        self.assertEqual(results[1]["original_text"], "This is a test text.")
        self.assertEqual(results[1]["translated_text"], "テストテキストです。")
        self.assertEqual(results[1]["source_lang"], "English")
        self.assertEqual(results[1]["target_lang"], "Japanese")
        self.assertEqual(results[1]["model"], "test-model")
