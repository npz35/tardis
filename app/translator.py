# Copyright 2025 npz35
#
# See the NOTICE file for this project for license details.
# This file may not be used except in accordance with the NOTICE.

import os
import requests
import json
import logging
from typing import List, Dict, Any, Optional, Union
import time
import traceback
import tempfile
import copy # Add copy module for deepcopy
from app.config import Config
from app.llm import LLM

class Translator:
    """Translation API Integration Module - Handles API integration with llama.cpp."""

    def __init__(self, api_url: Optional[str] = None, model: Optional[str] = None, timeout: int = 30):
        self.logger: logging.Logger = logging.getLogger(__name__)
        self.logger.debug(f"Function start: Translator.__init__(api_url='{api_url}', model='{model}', timeout={timeout})")
        """
        Initialization

        Args:
            api_url: URL of the translation API
            model: Model to use
            timeout: Timeout duration (seconds)
        """
        self.api_url: str = api_url or Config.TRANSLATION_API_URL
        self.model: str = model or Config.TRANSLATION_MODEL
        self.timeout: int = timeout

        # Create LLM instance
        self.llm: LLM = LLM(api_url=self.api_url, timeout=self.timeout)

        self.logger.debug("Function end: Translator.__init__ (success)")

    def translate_texts(self, texts: List[str], source_lang: str = "English",
                        target_lang: str = "Japanese", max_retries: int = 3) -> List[Dict[str, Any]]:
        self.logger.debug(f"Function start: translate_texts(texts_len={len(texts)}, source_lang='{source_lang}', target_lang='{target_lang}', max_retries={max_retries})")
        """
        Translates a list of texts.

        Args:
            texts: List of texts to translate
            source_lang: Source language
            target_lang: Target language
            max_retries: Maximum number of retries

        Returns:
            List of dictionaries of translation results
        """

        initial_result: Dict[str, Any] = {
            "success": False,
            "error": "Unexecuted",
            "original_text": None,
            "translated_text": None,
            "source_lang": source_lang,
            "target_lang": target_lang,
            "model": self.model,
            "tokens_used": 0,
            "processing_time": 0.0,
            "status_code": None,
            "attempts": 0
        }
        results: List[Dict[str, Any]] = []
        
        # Input validation for the list of texts
        if not texts:
            self.logger.error("Empty list of texts provided for translation")
            self.logger.debug("Function end: translate_texts (empty texts list)")
            result: Dict[str, Any] = copy.deepcopy(initial_result)
            result["error"] = "List of texts to translate is empty"
            results.append(result)
            return results
        
        # Individual text validation and pre-processing
        processed_texts: List[str] = []
        for i, text in enumerate(texts):
            result: Dict[str, Any] = copy.deepcopy(initial_result)
            result["original_text"] = text

            if not text or not text.strip():
                self.logger.warning(f"Empty text provided for translation at index {i}")
                result["error"] = "Text to translate is empty"
                results.append(result)
                processed_texts.append("") # Add empty string to maintain index
                continue

            if len(text) > Config.TRANSLATION_MAX_LENGTH:
                self.logger.warning(f"Text too long for translation at index {i}: {len(text)} characters (max: {Config.TRANSLATION_MAX_LENGTH})")
                result["error"] = f"Text to translate is too long (up to {Config.TRANSLATION_MAX_LENGTH} characters)"
                results.append(result)
                processed_texts.append("") # Add empty string to maintain index
                continue
            
            if len(text) <= 1:
                self.logger.warning(f"Text too short for translation at index {i}: {len(text)} characters")
                result["success"] = True
                result["error"] = "Text to translate is too short (2 characters or more)"
                result["translated_text"] = text
                results.append(result)
                processed_texts.append("") # Add empty string to maintain index
                continue
            
            if text[0] == '\\':
                self.logger.warning(f"The first character, {text[0]}, is invalid at index {i}.")
                result["success"] = True
                result["error"] = "Invalid first character"
                result["translated_text"] = text
                results.append(result)
                processed_texts.append("") # Add empty string to maintain index
                continue
            
            processed_texts.append(text)
            results.append(result)

        # Filter out empty processed_texts to avoid sending empty requests to LLM
        texts_to_translate = [text for text in processed_texts if text]
        if not texts_to_translate:
            self.logger.info("All texts were either empty, too long, or too short. No texts to send to LLM.")
            return results # Return results from initial validation
        start_time: float = time.time()

        self.logger.debug("================ TRANSLATION TEXTS ================")
        self.logger.debug(texts_to_translate)
        self.logger.debug("===================================================")

        # Retry logic
        for attempt in range(max_retries):
            try:
                # Create API request payload
                payload: Dict[str, Any] = self.llm.translation_prompt(texts_to_translate)
                llm_responses: List[Dict[str, Any]] = self.llm.translation_request(payload)

                if not llm_responses:
                    self.logger.error("LLM returned an empty response list.")
                    raise Exception("LLM returned an empty response list.")

                # Process each response
                for i, llm_response in enumerate(llm_responses):
                    original_text_index = processed_texts.index(texts_to_translate[i]) # Find original index
                    result = results[original_text_index]

                    if llm_response["status_code"] == 503:
                        self.logger.error(f"Failed to connect to API")
                        result["error"] = f"llm_response: {llm_response['error']}"
                        result["status_code"] = 503
                        result["attempts"] = attempt + 1
                        return results

                    if not llm_response["success"]:
                        self.logger.error(f"LLM post request failed for text at index {original_text_index}: {llm_response['error']}")
                        result["error"] = f"llm_response: {llm_response['error']}"
                        result["status_code"] = llm_response["status_code"]
                        result["attempts"] = attempt + 1
                        continue # Continue to next response

                    translated_text: str = llm_response["translated_text"].strip() if llm_response["translated_text"] else ""
                    is_formula: bool = llm_response["is_formula"]
                    skip_translation: bool = llm_response["skip_translation"]

                    # Handle skip translation
                    if skip_translation:
                        self.logger.info(f"Translation skipped by LLM for text at index {original_text_index}")
                        result["success"] = True
                        result["error"] = "Translation skipped by LLM"
                        result["translated_text"] = result["original_text"] # Return original text
                        result["is_formula"] = is_formula
                        result["skip_translation"] = skip_translation
                        result["attempts"] = attempt + 1
                        continue

                    # Handle formula
                    if is_formula:
                        self.logger.info(f"Text detected as formula for text at index {original_text_index}, returning as is")
                        result["success"] = True
                        result["error"] = "Text is a formula"
                        result["translated_text"] = result["original_text"] # Return original text
                        result["is_formula"] = is_formula
                        result["skip_translation"] = skip_translation
                        result["attempts"] = attempt + 1
                        continue

                    # Format translation result
                    translated_text = self._clean_translation(translated_text)

                    # Response validation
                    if not translated_text:
                        self.logger.warning(f"Empty translation result received for text at index {original_text_index}")
                        result["success"] = False
                        result["error"] = "Translation result is empty"
                        result["translated_text"] = None
                        result["is_formula"] = is_formula
                        result["skip_translation"] = skip_translation
                        result["attempts"] = attempt + 1
                        continue

                    # Validate translation quality
                    if self._is_invalid_translation(result["original_text"], translated_text):
                        self.logger.warning(f"Invalid translation detected for text at index {original_text_index}: '{translated_text}'. Retrying...")
                        # Do not mark as failed yet, allow retry
                        result["error"] = f"Translation result is inappropriate (no improvement after {max_retries} retries)"
                        result["translated_text"] = result["original_text"]
                        result["is_formula"] = is_formula
                        result["skip_translation"] = skip_translation
                        result["attempts"] = attempt + 1
                        continue

                    result["success"] = True
                    result["error"] = None
                    result["translated_text"] = translated_text
                    result["model"] = self.model
                    result["tokens_used"] = llm_response.get("prompt_eval_count", 0) + llm_response.get("eval_count", 0)
                    result["attempts"] = attempt + 1

            except Exception as e:
                self.logger.error(f"An error occurred during translation attempt {attempt + 1}/{max_retries}: {e}")
                for result in results:
                    if not result["success"]: # Only update if not already successful
                        result["error"] = f"An error occurred: {e}"
                        result["attempts"] = attempt + 1
            
            if any(result["success"] is False for result in results):
                if attempt < max_retries - 1:
                    self.logger.info(f"Retrying all translations (attempt {attempt + 1}/{max_retries})")
                    time.sleep(1)  # Wait 1 second and retry
                else:
                    self.logger.error(f"All {max_retries} translation attempts failed.")
                    processing_time = time.time() - start_time
                    for result in results:
                        if not result["success"]:
                            result["error"] = f"Translation failed ({max_retries} attempts)"
                            result["processing_time"] = processing_time / len(results) if results else 0.0
                            result["attempts"] = max_retries
                    return results

        processing_time: float = time.time() - start_time
        for result in results:
            result["processing_time"] = processing_time / len(results) if results else 0.0
        self.logger.info(f"All translations completed in {processing_time:.2f}s.")
        return results

    def translate_text(self, text: str, source_lang: str = "English",
                       target_lang: str = "Japanese", max_retries: int = 3) -> Dict[str, Any]:
        self.logger.debug(f"Function start: translate_text(text_len={len(text)}, source_lang='{source_lang}', target_lang='{target_lang}', max_retries={max_retries})")
        """
        Translates text. This is a wrapper for translate_texts for single text translation.

        Args:
            text: Text to translate
            source_lang: Source language
            target_lang: Target language
            max_retries: Maximum number of retries

        Returns:
            Dictionary of translation results for the single text
        """
        results = self.translate_texts(
            texts=[text],
            source_lang=source_lang,
            target_lang=target_lang,
            max_retries=max_retries,
        )
        if results:
            return results[0]
        else:
            return {
                "error": "Translation failed unexpectedly",
                "original_text": text,
                "translated_text": None,
                "source_lang": source_lang,
                "target_lang": target_lang,
                "model": self.model,
                "tokens_used": 0,
                "processing_time": 0.0,
                "status_code": None,
                "attempts": 0
            }

    def _clean_translation(self, translated_text: str) -> str:
        self.logger.debug(f"Function start: _clean_translation(translated_text={translated_text})")
        """
        Formats the translation result.

        Args:
            translated_text: Unformatted translated text

        Returns:
            Formatted translated text
        """
        if not translated_text:
            self.logger.debug("Function end: _clean_translation (empty text)")
            return ""

        # Remove extra whitespace
        cleaned: str = translated_text.strip()

        # Normalize newlines
        cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")

        # Remove unnecessary prefixes/suffixes
        prefixes_to_remove: List[str] = [
            "Japanese translation:",
            "Japanese:",
            "日本語訳:",
            "日本語:",
            "翻訳:",
            "Translation:",
            "translation:",
        ]

        for prefix in prefixes_to_remove:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
                break

        # Remove unnecessary suffixes
        suffixes_to_remove: List[str] = [
            "translation",
            "Translation",
            "訳",
            "翻訳",
        ]

        for suffix in suffixes_to_remove:
            if cleaned.endswith(suffix):
                cleaned = cleaned[:-len(suffix)].strip()
                break

        self.logger.debug("Function end: _clean_translation (success)")
        return cleaned

    def _is_invalid_translation(self, original_text: str, translated_text: str) -> bool:
        self.logger.debug(f"Function start: _is_invalid_translation(original_text={original_text}, translated_text={translated_text})")
        """
        Validates if the translation result is inappropriate.

        Args:
            original_text: Original text
            translated_text: Translated text

        Returns:
            True if inappropriate, False if appropriate
        """
        if len(original_text.strip()) <= 1 and len(translated_text.strip())  <= 1:
            self.logger.warning("Texts is too short.")
            self.logger.debug("Function end: _is_invalid_translation (text too short)")
            return False

        if 1 < len(original_text.strip()) and len(translated_text.strip())  <= 1:
            self.logger.warning("Translation result is too short.")
            self.logger.debug("Function end: _is_invalid_translation (translation result too short)")
            return True

        # If translation result contains only inappropriate words
        invalid_responses: List[str] = ["OK", "ok", "Okay", "okay", "Yes", "yes", "No", "no",
                           "はい", "いいえ", "OKです", "了解", "承知いたしました"]
        if (original_text not in invalid_responses) and (translated_text.strip() in invalid_responses):
            self.logger.warning("Translation result is invalid.")
            self.logger.debug("Function end: _is_invalid_translation (invalid translation result)")
            return True
        
        if 5 <= len(original_text.strip()) and 5 <= len(translated_text.strip()) and original_text.strip() == translated_text.strip():
            self.logger.warning("Translation result is same text.")
            self.logger.debug("Function end: _is_invalid_translation (same text)")
            # TODO: As a temporary measure, it is now considered normal
            return False

        # If translation result is too short (e.g., "OK")
        if 2 < len(original_text.strip()) and len(translated_text.strip()) <= 2:
            self.logger.warning("Translation result is too short.")
            self.logger.debug("Function end: _is_invalid_translation (translation too short)")
            return False

        # If translation result contains only symbols
        if translated_text.strip().isalnum() and len(translated_text.strip()) <= 5:
            self.logger.warning("The translation result only contains symbols.")
            self.logger.debug("Function end: _is_invalid_translation (translation contains only symbols)")
            return False

        self.logger.debug("Function end: _is_invalid_translation (success)")
        return False

    def _clean_translation(self, translated_text: str) -> str:
        self.logger.debug(f"Function start: _clean_translation(translated_text={translated_text})")
        """
        Formats the translation result.

        Args:
            translated_text: Unformatted translated text

        Returns:
            Formatted translated text
        """
        if not translated_text:
            self.logger.debug("Function end: _clean_translation (empty text)")
            return ""

        # Remove extra whitespace
        cleaned: str = translated_text.strip()

        # Normalize newlines
        cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")

        # Remove unnecessary prefixes/suffixes
        prefixes_to_remove: List[str] = [
            "Japanese translation:",
            "Japanese:",
            "日本語訳:",
            "日本語:",
            "翻訳:",
            "Translation:",
            "translation:",
        ]

        for prefix in prefixes_to_remove:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
                break

        # Remove unnecessary suffixes
        suffixes_to_remove: List[str] = [
            "translation",
            "Translation",
            "訳",
            "翻訳",
        ]

        for suffix in suffixes_to_remove:
            if cleaned.endswith(suffix):
                cleaned = cleaned[:-len(suffix)].strip()
                break

        self.logger.debug("Function end: _clean_translation (success)")
        return cleaned

    def _is_invalid_translation(self, original_text: str, translated_text: str) -> bool:
        self.logger.debug(f"Function start: _is_invalid_translation(original_text={original_text}, translated_text={translated_text})")
        """
        Validates if the translation result is inappropriate.

        Args:
            original_text: Original text
            translated_text: Translated text

        Returns:
            True if inappropriate, False if appropriate
        """
        if len(original_text.strip()) <= 1 and len(translated_text.strip())  <= 1:
            self.logger.warning("Texts is too short.")
            self.logger.debug("Function end: _is_invalid_translation (text too short)")
            return False

        if 1 < len(original_text.strip()) and len(translated_text.strip())  <= 1:
            self.logger.warning("Translation result is too short.")
            self.logger.debug("Function end: _is_invalid_translation (translation result too short)")
            return True

        # If translation result contains only inappropriate words
        invalid_responses: List[str] = ["OK", "ok", "Okay", "okay", "Yes", "yes", "No", "no",
                           "はい", "いいえ", "OKです", "了解", "承知いたしました"]
        if (original_text not in invalid_responses) and (translated_text.strip() in invalid_responses):
            self.logger.warning("Translation result is invalid.")
            self.logger.debug("Function end: _is_invalid_translation (invalid translation result)")
            return True
        
        if 5 <= len(original_text.strip()) and 5 <= len(translated_text.strip()) and original_text.strip() == translated_text.strip():
            self.logger.warning("Translation result is same text.")
            self.logger.debug("Function end: _is_invalid_translation (same text)")
            # TODO: As a temporary measure, it is now considered normal
            return False

        # If translation result is too short (e.g., "OK")
        if 2 < len(original_text.strip()) and len(translated_text.strip()) <= 2:
            self.logger.warning("Translation result is too short.")
            self.logger.debug("Function end: _is_invalid_translation (translation too short)")
            return False

        # If translation result contains only symbols
        if translated_text.strip().isalnum() and len(translated_text.strip()) <= 5:
            self.logger.warning("The translation result only contains symbols.")
            self.logger.debug("Function end: _is_invalid_translation (translation contains only symbols)")
            return False

        self.logger.debug("Function end: _is_invalid_translation (success)")
        return False
