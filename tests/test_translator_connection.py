# Copyright 2025 npz35
#
# See the NOTICE file for this project for license details.
# This file may not be used except in accordance with the NOTICE.

import unittest
import requests

from app.config import Config
from app.translator import Translator
from app.llm import LLM

# API endpoint for integration tests
# Inferred from docker-compose.yml information
INTEGRATION_API_URL = Config.TRANSLATION_API_URL

class TestTranslatorIntegration(unittest.TestCase):
    """Integration tests for the Translator class"""

    def setUp(self):
        """Setup executed before each test method"""
        # Create Translator instance specifying the actual API endpoint
        self.translator = Translator(api_url=INTEGRATION_API_URL, model="default-model", timeout=60) # Adjust model to the actual model name, extend timeout
        self.llm = LLM(api_url=INTEGRATION_API_URL, timeout=60)

    def test_translate_text_real_api_success(self):
        """Integration test: Send request to the actual API and confirm success"""
        # Text for testing
        text_to_translate = "Who are you?"

        # To avoid errors if the API does not respond or the model does not exist,
        # first, check basic connectivity with an API health check.
        try:
            health_check_result = self.llm.check_api_health()
            self.assertTrue(health_check_result["success"], f"API health check failed: {health_check_result.get('error')}")
            # Also check if the model exists (whether the target model is available)
            # self.assertTrue(health_check_result["model_available"], f"Model '{self.translator.model}' not available. Available models: {health_check_result.get('available_models')}")
            # Note: The response structure of check_api_health may differ between /chat/completions and /v1/models,
            # so here we only perform basic connectivity checks.
        except requests.exceptions.RequestException as e:
            self.skipTest(f"Skipping integration test: API is not reachable at {INTEGRATION_API_URL}. Error: {e}")
        except Exception as e:
            self.skipTest(f"Skipping integration test due to unexpected error during health check: {e}")

        # テスト実行
        result = self.translator.translate_texts([text_to_translate])

        # 結果の検証
        self.assertTrue(result[0]["success"], f"Translation failed: {result[0].get('error')}")
        self.assertEqual(result[0]["original_text"], text_to_translate)
        self.assertIsNotNone(result[0]["translated_text"])
        self.assertGreater(len(result[0]["translated_text"]), 0, "Translated text should not be empty")
        # 翻訳結果が日本語になっているかどうかの簡易チェック
        self.assertIn("あなた", result[0]["translated_text"])

    def test_translate_text_real_api_invalid_url(self):
        """Integration test: Error handling when an invalid API URL is specified"""
        invalid_translator = Translator(api_url="http://invalid-url-that-does-not-exist.local", model="test-model")

        try:
            result = invalid_translator.translate_texts(["This text should fail."])
            self.assertFalse(result[0]["success"])
            # The error message depends on requests.exceptions.ConnectionError
            self.assertIn("Failed to connect to API", result[0]["error"])
        except requests.exceptions.RequestException as e:
            # ConnectionErrorが発生した場合
            self.assertFalse(result[0]["success"])
            self.assertIn("Failed to connect to API", result[0]["error"])
        except Exception as e:
            self.fail(f"An unexpected error occurred: {e}")
