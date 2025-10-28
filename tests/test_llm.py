# Copyright 2025 npz35
#
# See the NOTICE file for this project for license details.
# This file may not be used except in accordance with the NOTICE.

import pytest
import requests
from unittest.mock import Mock, patch
import logging

from app.llm import LLM
from app.config import Config

# Suppress logging during tests for cleaner output
logging.disable(logging.CRITICAL)

class TestLLM:
    @pytest.fixture
    def llm_instance(self):
        # Use a dummy API URL and model for testing
        return LLM(api_url="http://test-api.com", model="test-model")

    @patch('requests.Session.get')
    def test_check_api_health_success_model_in_data(self, mock_get, llm_instance):
        # Mock a successful API response where the model is found in 'data'
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "object": "list",
            "data": [
                {"id": "model-id-0", "object": "model", "created": 123, "owned_by": "org"},
                {"id": "test-model", "object": "model", "created": 456, "owned_by": "openai"}
            ],
            "object": "list"
        }
        mock_get.return_value = mock_response

        result = llm_instance.check_api_health()

        assert result["success"] is True
        assert result["model_available"] is True
        assert result["api_url"] == "http://test-api.com"
        assert result["model"] == "test-model"
        assert "available_models" in result
        assert result["error"] == "Unexecuted" # Initial error message should be cleared on success

        mock_get.assert_called_once_with(
            f"{llm_instance.api_url}/v1/models",
            params={"name": llm_instance.model},
            headers=llm_instance.headers,
            timeout=llm_instance.timeout
        )

    @patch('requests.Session.get')
    def test_check_api_health_success_model_in_models(self, mock_get, llm_instance):
        # Mock a successful API response where the model is found in 'models' (alternative structure)
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "object": "list",
            "models": [
                {"name": "model-id-0", "object": "model", "created": 123, "owned_by": "org"},
                {"name": "test-model", "object": "model", "created": 456, "owned_by": "openai"}
            ],
            "object": "list"
        }
        mock_get.return_value = mock_response

        result = llm_instance.check_api_health()

        assert result["success"] is True
        assert result["model_available"] is True
        assert result["api_url"] == "http://test-api.com"
        assert result["model"] == "test-model"
        assert "available_models" in result
        assert result["error"] == "Unexecuted" # Initial error message should be cleared on success

    @patch('requests.Session.get')
    def test_check_api_health_success_model_not_available(self, mock_get, llm_instance):
        # Mock a successful API response where the model is NOT found
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "object": "list",
            "data": [
                {"id": "model-id-0", "object": "model", "created": 123, "owned_by": "org"}
            ],
            "object": "list"
        }
        mock_get.return_value = mock_response

        result = llm_instance.check_api_health()

        assert result["success"] is True
        assert result["model_available"] is False
        assert result["api_url"] == "http://test-api.com"
        assert result["model"] == "test-model"
        assert "available_models" in result
        assert result["error"] == "Unexecuted" # Initial error message should be cleared on success

    @patch('requests.Session.get')
    def test_check_api_health_request_exception(self, mock_get, llm_instance):
        # Mock a RequestException (e.g., connection error, timeout)
        mock_get.side_effect = requests.exceptions.RequestException("Connection refused")

        result = llm_instance.check_api_health()

        assert result["success"] is False
        assert result["model_available"] is False
        assert result["error"] == "Connection refused"
        assert result["api_url"] == "http://test-api.com"
        assert result["model"] == "test-model"
        assert result["available_models"] is None

    @patch('requests.Session.get')
    def test_check_api_health_http_error(self, mock_get, llm_instance):
        # Mock an HTTPError (e.g., 404 Not Found)
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Client Error: Not Found for url: http://test-api.com/v1/models")
        mock_get.return_value = mock_response

        result = llm_instance.check_api_health()

        assert result["success"] is False
        assert result["model_available"] is False
        assert result["error"] == "404 Client Error: Not Found for url: http://test-api.com/v1/models"
        assert result["api_url"] == "http://test-api.com"
        assert result["model"] == "test-model"
        assert result["available_models"] is None

    @patch('requests.Session.get')
    def test_check_api_health_unexpected_exception(self, mock_get, llm_instance):
        # Mock an unexpected generic exception
        mock_get.side_effect = Exception("Something unexpected happened")

        result = llm_instance.check_api_health()

        assert result["success"] is False
        assert result["model_available"] is False
        assert result["error"] == "Something unexpected happened"
        assert result["api_url"] == "http://test-api.com"
        assert result["model"] == "test-model"
        assert result["available_models"] is None

    @patch('requests.Session.get')
    def test_check_api_health_empty_response_data(self, mock_get, llm_instance):
        # Mock a successful API response with empty 'data' and 'models'
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "object": "list",
            "data": [],
            "models": []
        }
        mock_get.return_value = mock_response

        result = llm_instance.check_api_health()

        assert result["success"] is True
        assert result["model_available"] is False
        assert result["api_url"] == "http://test-api.com"
        assert result["model"] == "test-model"
        assert result["available_models"] is None
        assert result["error"] == "Unexecuted"
    @patch('requests.Session.get')
    def test_get_model_info_success(self, mock_get, llm_instance):
        # Mock a successful API response with model information
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "object": "list",
            "data": [
                {"id": "model-id-0", "object": "model", "created": 123, "owned_by": "org"},
                {"id": "test-model", "object": "model", "created": 456, "owned_by": "openai"}
            ],
            "object": "list"
        }
        mock_get.return_value = mock_response

        result = llm_instance.get_model_info()

        assert result["success"] is True
        assert "model_info" in result
        assert result["model_info"]["data"][1]["id"] == "test-model"

        mock_get.assert_called_once_with(
            f"{llm_instance.api_url}/v1/models",
            params={"name": llm_instance.model},
            headers=llm_instance.headers,
            timeout=llm_instance.timeout
        )

    @patch('requests.Session.get')
    def test_get_model_info_request_exception(self, mock_get, llm_instance):
        # Mock a RequestException
        mock_get.side_effect = requests.exceptions.RequestException("Connection error during model info retrieval")

        result = llm_instance.get_model_info()

        assert result["success"] is False
        assert result["error"] == "Connection error during model info retrieval"
        assert "model_info" not in result

    @patch('requests.Session.get')
    def test_get_model_info_http_error(self, mock_get, llm_instance):
        # Mock an HTTPError
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Server Error: Internal Server Error for url: http://test-api.com/v1/models")
        mock_get.return_value = mock_response

        result = llm_instance.get_model_info()

        assert result["success"] is False
        assert result["error"] == "500 Server Error: Internal Server Error for url: http://test-api.com/v1/models"
        assert "model_info" not in result

    @patch('requests.Session.get')
    def test_get_model_info_unexpected_exception(self, mock_get, llm_instance):
        # Mock an unexpected generic exception
        mock_get.side_effect = Exception("Unknown error during model info retrieval")

        result = llm_instance.get_model_info()

        assert result["success"] is False
        assert result["error"] == "Unknown error during model info retrieval"
        assert "model_info" not in result
    @patch('requests.Session.post')
    def test_translation_request_success(self, mock_post, llm_instance):
        # Mock a successful API response with valid XML content
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": "<llm><response><translated_text>Translated text 1</translated_text><is_formula>false</is_formula><skip_translation>false</skip_translation></response><response><translated_text>Translated text 2</translated_text><is_formula>true</is_formula><skip_translation>false</skip_translation></response></llm>"
                }
            }]
        }
        mock_post.return_value = mock_response

        json_payload = {"messages": [{"role": "user", "content": "test"}]}
        results = llm_instance.translation_request(json_payload)

        assert len(results) == 2
        assert results[0]["success"] is True
        assert results[0]["translated_text"] == "Translated text 1"
        assert results[0]["is_formula"] is False
        assert results[0]["skip_translation"] is False
        assert results[0]["status_code"] == 200

        assert results[1]["success"] is True
        assert results[1]["translated_text"] == "Translated text 2"
        assert results[1]["is_formula"] is True
        assert results[1]["skip_translation"] is False
        assert results[1]["status_code"] == 200

        mock_post.assert_called_once_with(
            url=f"{llm_instance.api_url}/v1/chat/completions",
            headers=llm_instance.headers,
            json=json_payload,
            timeout=llm_instance.timeout
        )

    @patch('requests.Session.post')
    def test_translation_request_empty_llm_content(self, mock_post, llm_instance):
        # Mock an API response with empty LLM content
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": ""
                }
            }]
        }
        mock_post.return_value = mock_response

        json_payload = {"messages": [{"role": "user", "content": "test"}]}
        results = llm_instance.translation_request(json_payload)

        assert len(results) == 1
        assert results[0]["success"] is False
        assert results[0]["error"] == "Translation result is empty"
        assert results[0]["translated_text"] == ""
        assert results[0]["status_code"] == 200

    @patch('requests.Session.post')
    def test_translation_request_xml_parse_error(self, mock_post, llm_instance):
        # Mock an API response with invalid XML content
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": "<llm><response><translated_text>Invalid XML</translated_text></response>"
                }
            }]
        }
        mock_post.return_value = mock_response

        json_payload = {"messages": [{"role": "user", "content": "test"}]}
        results = llm_instance.translation_request(json_payload)

        assert len(results) == 1
        assert results[0]["success"] is False
        assert "Failed to parse LLM response as XML" in results[0]["error"]
        assert results[0]["status_code"] == 500

    @patch('requests.Session.post')
    def test_translation_request_timeout(self, mock_post, llm_instance):
        # Mock a requests.exceptions.Timeout
        mock_post.side_effect = requests.exceptions.Timeout("API response timed out")

        json_payload = {"messages": [{"role": "user", "content": "test"}]}
        results = llm_instance.translation_request(json_payload)

        assert len(results) == 1
        assert results[0]["success"] is False
        assert "API response timed out" in results[0]["error"]
        assert results[0]["status_code"] == 408

    @patch('requests.Session.post')
    def test_translation_request_connection_error(self, mock_post, llm_instance):
        # Mock a requests.exceptions.ConnectionError
        mock_post.side_effect = requests.exceptions.ConnectionError("Failed to connect")

        json_payload = {"messages": [{"role": "user", "content": "test"}]}
        results = llm_instance.translation_request(json_payload)

        assert len(results) == 1
        assert results[0]["success"] is False
        assert results[0]["error"] == "Failed to connect to API"
        assert results[0]["status_code"] == 503

    @patch('requests.Session.post')
    def test_translation_request_http_error(self, mock_post, llm_instance):
        # Mock a requests.exceptions.HTTPError (e.g., 400 Bad Request)
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("400 Bad Request", response=mock_response)
        mock_post.return_value = mock_response

        json_payload = {"messages": [{"role": "user", "content": "test"}]}
        results = llm_instance.translation_request(json_payload)

        assert len(results) == 1
        assert results[0]["success"] is False
        assert results[0]["error"] == "Invalid request (text may be too long)"
        assert results[0]["status_code"] == 400

    @patch('requests.Session.post')
    def test_translation_request_unexpected_error(self, mock_post, llm_instance):
        # Mock an unexpected generic exception
        mock_post.side_effect = Exception("Generic unexpected error")

        json_payload = {"messages": [{"role": "user", "content": "test"}]}
        results = llm_instance.translation_request(json_payload)

        assert len(results) == 1
        assert results[0]["success"] is False
        assert results[0]["error"] == "An unexpected error occurred: Generic unexpected error"
        assert results[0]["status_code"] == 500