# Copyright 2025 npz35
#
# See the NOTICE file for this project for license details.
# This file may not be used except in accordance with the NOTICE.

from typing import List,Dict, Any, Optional
import logging
import requests
import xml.etree.ElementTree as ET
import copy

from app.config import Config


class LLM:
    def __init__(self, api_url: Optional[str] = None, model: Optional[str] = None, timeout: int = 60):
        self.logger: logging.Logger = logging.getLogger(__name__)
        self.logger.debug(f"Function start: LLM.__init__(api_url='{api_url}', timeout={timeout})")

        self.api_url: str = api_url or Config.TRANSLATION_API_URL
        self.model: str = model or Config.TRANSLATION_MODEL
        self.timeout: int = timeout

        # Create session
        self.session: requests.Session = requests.Session()

        # Set headers
        self.headers: Dict[str, str] = {
            "Content-Type": "application/json",
            "Authorization": "Bearer none"
        }

        # https://huggingface.co/webbigdata/gemma-2-2b-jpn-it-translate-gguf
        # self.system_prompt = "You are a highly skilled professional Japanese-English and English-Japanese translator. Translate the given text accurately, taking into account the context and specific instructions provided. Only when the subject is specified in the Japanese sentence, the subject will be added when translating into English. Use your expertise to consider what the most appropriate context is and provide a natural translation that aligns with that context. When translating, strive to faithfully reflect the meaning and tone of the original text, pay attention to cultural nuances and differences in language usage, and ensure that the translation is grammatically correct and easy to read. After completing the translation, review it once more to check for errors or unnatural expressions. For technical terms and proper nouns, either leave them in the original language or use appropriate translations as necessary. Take a deep breath, calm down, and start translating.\n\nTranslate from English to Japanese.\nPlease translate from {source_lang} to {target_lang}.\n"
        # self.system_prompt = f"あなたは高度なスキルを持つ日本語・英語の翻訳者です。与えられたテキストを、文脈や指示事項を考慮しながら正確に翻訳してください。日本語の文に主語が明示されている場合のみ、英語訳にも主語を付け加えてください。あなたの専門知識に基づいて適切な文脈を推測し、その文脈に合った自然な表現で翻訳してください。翻訳にあたっては、原文の意味とニュアンスを忠実に表現すること、文化的な差異や表現の違いに注意すること、そして文法的に正しく読みやすい文章になるように心がけてください。翻訳が完了したら、誤りや不自然な表現がないか再度確認してください。専門用語や固有名詞は、そのまま原文のままにするか、適切な訳語を用いるか、状況に応じて判断してください。回答には「日本語訳」や「翻訳結果です」などの、純粋な翻訳結果以外の文章は不要です。\n以降に与えられる文章を {source_lang} から {target_lang} へ翻訳してください。ここまでの指示に問題が無ければ「OK」とだけ回答して、以降は与えられた文章を翻訳してください。\n\n"
        self.system_prompt: str = f"あなたはプロの翻訳家です。あなたのタスクは、ユーザーから提供された英語の文章を、**完全かつ正確**に日本語に翻訳することです。翻訳結果以外の前置き、後書き、説明、確認の言葉（例：「日本語訳:」「OK」「承知しました」）は**一切含めないでください**。翻訳結果のみを出力してください。元の文章の意図を完全に反映し、要約や意訳はせず、提供された文章に対応する完全な日本語訳のみを提供してください。"

        self.logger.debug("Function end: LLM.__init__ (success)")

    def check_api_health(self) -> Dict[str, Any]:
        self.logger.debug("Function start: check_api_health")
        """
        Performs an API health check.

        Returns:
            Health check result
        """
        result: Dict[str, Any] = {
            "success": False,
            "error": "Unexecuted",
            "api_url": self.api_url,
            "model": self.model,
            "model_available": False,
            "available_models": None
        }

        try:
            '''
            Example

            Request

            curl https://api.openai.com/v1/models \
                -H "Authorization: Bearer none"

            Response

            {
                "object": "list",
                "data": [
                    {
                        "id": "model-id-0",
                        "object": "model",
                        "created": 1686935002,
                        "owned_by": "organization-owner"
                    },
                    {
                        "id": "model-id-1",
                        "object": "model",
                        "created": 1686935002,
                        "owned_by": "organization-owner"
                    },
                    {
                        "id": "model-id-2",
                        "object": "model",
                        "created": 1686935002,
                        "owned_by": "openai"
                    },
                ],
                "object": "list"
            }
            '''

            # Request for health check
            response: requests.Response = self.session.get(
                f"{self.api_url}/v1/models",
                params={"name": self.model},
                headers=self.headers,
                timeout=self.timeout
            )

            # Check response
            response.raise_for_status()

            # Get model information
            response_data: Dict[str, Any] = response.json()
            models: List[Dict[str, Any]] = response_data.get("models", [])
            data_models: List[Dict[str, Any]] = response_data.get("data", [])

            # Check if model exists (check both arrays)
            model_available: bool = (
                any(model.get("name") == self.model for model in models) or
                any(model.get("id") == self.model for model in data_models)
            )

            self.logger.debug("Function end: check_api_health (success)")
            result["success"] = True
            result["model_available"] = model_available
            result["available_models"] = models if models else None
            return result

        except requests.exceptions.RequestException as e:
            self.logger.error(f"Health check failed: {str(e)}")
            self.logger.debug("Function end: check_api_health (failed)")
            result["error"] = str(e)
            return result
        except Exception as e:
            self.logger.error(f"Unexpected error during health check: {str(e)}")
            self.logger.debug("Function end: check_api_health (unexpected error)")
            result["error"] = str(e)
            return result

    def get_model_info(self) -> Dict[str, Any]:
        self.logger.debug("Function start: get_model_info")
        """
        Retrieves model information.

        Returns:
            Model information
        """
        try:
            '''
            Example

            Request

            curl https://api.openai.com/v1/models \
                -H "Authorization: Bearer none"

            Response

            {
                "object": "list",
                "data": [
                    {
                        "id": "model-id-0",
                        "object": "model",
                        "created": 1686935002,
                        "owned_by": "organization-owner"
                    },
                    {
                        "id": "model-id-1",
                        "object": "model",
                        "created": 1686935002,
                        "owned_by": "organization-owner"
                    },
                    {
                        "id": "model-id-2",
                        "object": "model",
                        "created": 1686935002,
                        "owned_by": "openai"
                    },
                ],
                "object": "list"
            }
            '''

            # Get model information
            response: requests.Response = self.session.get(
                f"{self.api_url}/v1/models",
                headers=self.headers,
                params={"name": self.model},
                timeout=self.timeout
            )

            # Check response
            response.raise_for_status()

            # Parse model information
            model_info: Dict[str, Any] = response.json()

            self.logger.debug("Function end: get_model_info (success)")
            return {
                "success": True,
                "model_info": model_info
            }

        except requests.exceptions.RequestException as e:
            self.logger.error(f"Failed to get model info: {str(e)}")
            self.logger.debug("Function end: get_model_info (failed)")
            return {
                "success": False,
                "error": str(e)
            }
        except Exception as e:
            self.logger.error(f"Unexpected error getting model info: {str(e)}")
            self.logger.debug("Function end: get_model_info (unexpected error)")
            return {
                "success": False,
                "error": str(e)
            }

    def translation_prompt(self, original_texts: List[str]) -> Dict[str, Any]:
        request_tags = "".join([f"<request><original_text>{text}</original_text></request>" for text in original_texts])
        user_content = f"<llm>{request_tags}</llm>"

        return {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": self.system_prompt + """\n\n
                    ユーザーからの入力はXML形式で提供されます。<llm>タグの中に1つ以上の<request>タグが含まれます。各<request>タグには<original_text>タグが含まれます。翻訳結果もXML形式で返してください。<llm>タグの中に1つ以上の<response>タグを含めてください。各<response>タグには<translated_text>、<is_formula>、<skip_translation>のタグを含めてください。
                    もし<skip_translation>がtrueの場合、<translated_text>には元のテキストをそのまま含めてください。
                    テキストに数式が含まれている場合は<is_formula>をtrueにしてください。また、テキスト中の ∈ や Σ などの数式記号は翻訳する必要はありません。
                    テキストに含まれている人名は翻訳する必要はありません。
                    テキストに含まれている記号は翻訳する必要はありません。
                    テキストに含まれている'\\xa' などの '\\'で始まる文字列は記号として扱ってください。
                    テキストに含まれている記号'<'と'>'はXMLと干渉する恐れがあるため、 <translated_text>要素に含めるテキストの中では'＜'と'＞'に置き換えてください。
                    """
                },
                {
                    "role": "user",
                    "content": "<llm><request><original_text>The quick brown fox jumps over the lazy dog.</original_text></request><request><original_text>Ito Hirobumi is the first Prime Minister of Japan.</original_text></request><request><original_text>Development on Ubuntu 24.04 provides a stable environment.</original_text></request><request><original_text>For s ∈ Σ^+, we denote by |s| the length of s and by s[i] the ith character of s for 1 ≤ i ≤ |s|.</original_text></request><request><original_text>E = mc^2</original_text></request></llm>"
                },
                {
                    "role": "assistant",
                    "content": "<llm><response><translated_text>すばやい茶色のキツネが怠惰な犬を飛び越える。</translated_text><is_formula>false</is_formula><skip_translation>false</skip_translation></response><response><translated_text>Ito Hirobumiは日本の初代内閣総理大臣です。</translated_text><is_formula>false</is_formula><skip_translation>false</skip_translation></response><response><translated_text>Ubuntu 24.04での開発は安定した環境を提供します。</translated_text><is_formula>false</is_formula><skip_translation>false</skip_translation></response><response><translated_text>s ∈ Σ^+ において、|s| を s の長さ、s[i] を s の i 番目の文字 (1 ≤ i ≤ |s|) と表します。</translated_text><is_formula>false</is_formula><skip_translation>false</skip_translation></response><response><translated_text>E = mc^2</translated_text><is_formula>true</is_formula><skip_translation>true</skip_translation></response></llm>"
                },
                {
                    "role": "user",
                    "content": user_content
                }
            ],
            "stream": False
        }

    def translation_request(self, json_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        self.logger.debug(f"Function start: translation_request(json_payload_keys={json_payload.keys()})")

        '''
        Example

        Request

        curl https://api.openai.com/v1/chat/completions \
            -H "Content-Type: application/json" \
            -H "Authorization: Bearer none" \
            -d '{
                "model": "default-model",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a helpful assistant."
                    },
                    {
                        "role": "user",
                        "content": "Hello!"
                    }
                ]
            }'

        Reponse

        {
            "id": "chatcmpl-B9MBs8CjcvOU2jLn4n570S5qMJKcT",
            "object": "chat.completion",
            "created": 1741569952,
            "model": "default-model",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "Hello! How can I assist you today?",
                        "refusal": null,
                        "annotations": []
                    },
                    "logprobs": null,
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": 19,
                "completion_tokens": 10,
                "total_tokens": 29,
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
        '''

        # self.logger.debug("================ TRANSLATION REQUEST ================")
        # self.logger.debug(json_payload)
        # self.logger.debug("=====================================================")

        initial_result: Dict[str, Any] = {
            "success": False,
            "error": "Unexecuted",
            "response_json": None,
            "translated_text": None,
            "is_formula": False,
            "skip_translation": True,
            "status_code": None
        }
        results: List[Dict[str, Any]] = []

        try:
            response: requests.Response = self.session.post(
                url=f"{self.api_url}/v1/chat/completions",
                headers=self.headers,
                json=json_payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            response_json = response.json()
            
            # Extract content from LLM response
            llm_content = response_json.get("choices", [{}])[0].get("message", {}).get("content", "").strip()

            self.logger.debug("================ TRANSLATION RESPONSE ================")
            self.logger.debug(llm_content)
            self.logger.debug("======================================================")

            # If LLM response is empty, return empty translation result
            if not llm_content:
                self.logger.warning("LLM response is empty")
                result: Dict[str, Any] = copy.deepcopy(initial_result)
                result["error"] = "Translation result is empty"
                result["response_json"] = response_json
                result["translated_text"] = ""
                result["status_code"] = response.status_code
                results.append(result)
                self.logger.debug("Function end: translation_request (empty LLM response)")
                return results

            # Parse XML content
            try:
                root = ET.fromstring(llm_content)
                for response_elem in root.findall("response"):
                    result: Dict[str, Any] = copy.deepcopy(initial_result)

                    translated_text = response_elem.find("translated_text").text if response_elem.find("translated_text") is not None else None
                    is_formula_str = response_elem.find("is_formula").text if response_elem.find("is_formula") is not None else "false"
                    skip_translation_str = response_elem.find("skip_translation").text if response_elem.find("skip_translation") is not None else "false"

                    is_formula = is_formula_str.lower() == "true"
                    skip_translation = skip_translation_str.lower() == "true"
                    
                    result["success"] = True
                    result["error"] = "" # not error
                    result["response_json"] = response_json
                    result["translated_text"] = translated_text
                    result["is_formula"] = is_formula
                    result["skip_translation"] = skip_translation
                    result["status_code"] = response.status_code
                    results.append(result)
            except ET.ParseError as e:
                self.logger.error(f"XML parse error: {e}. Content: {llm_content}")
                result: Dict[str, Any] = copy.deepcopy(initial_result) # Initialize result here
                result["error"] = f"Failed to parse LLM response as XML: {e}"
                result["response_json"] = response_json
                result["status_code"] = 500
                results.append(result)
                return results
            except Exception as e:
                self.logger.error(f"Error processing LLM XML response: {e}. Content: {llm_content}")
                result: Dict[str, Any] = copy.deepcopy(initial_result) # Initialize result here
                result["error"] = f"Error processing LLM XML response: {e}"
                result["response_json"] = response_json
                result["status_code"] = 500
                results.append(result)
                return results

        except requests.exceptions.Timeout as e:
            self.logger.error(f"Request timeout: {str(e)}")
            result: Dict[str, Any] = copy.deepcopy(initial_result)
            result["error"] = f"API response timed out ({self.timeout} seconds)"
            result["status_code"] = 408 # Request Timeout
            results.append(result)
            self.logger.debug("Function end: translation_request (timeout)")
            return results
        except requests.exceptions.ConnectionError as e:
            self.logger.error(f"Connection error: {str(e)}")
            result: Dict[str, Any] = copy.deepcopy(initial_result)
            result["error"] = "Failed to connect to API"
            result["status_code"] = 503 # Service Unavailable
            results.append(result)
            self.logger.debug("Function end: translation_request (connection error)")
            return results
        except requests.exceptions.HTTPError as e:
            status_code: int = e.response.status_code if hasattr(e, 'response') else 500
            self.logger.error(f"HTTP error {status_code}: {str(e)}")

            if status_code == 400:
                error_msg: str = "Invalid request (text may be too long)"
            elif status_code == 401:
                error_msg = "API authentication failed"
            elif status_code == 403:
                error_msg = "Access to API denied"
            elif status_code == 404:
                error_msg = "API endpoint not found"
            elif status_code == 429:
                error_msg = "Too many API requests (rate limit)"
            elif status_code >= 500:
                error_msg = "Server error occurred"
            else:
                error_msg = f"HTTP error occurred (status code: {status_code})"

            result: Dict[str, Any] = copy.deepcopy(initial_result)
            result["error"] = error_msg
            result["status_code"] = status_code
            results.append(result)
            self.logger.debug("Function end: translation_request (HTTP error)")
            return results
        except Exception as e:
            self.logger.error(f"Unexpected error during request: {str(e)}")
            result: Dict[str, Any] = copy.deepcopy(initial_result)
            result["error"] = f"An unexpected error occurred: {str(e)}"
            result["status_code"] = 500 # Internal Server Error
            results.append(result)
            self.logger.debug("Function end: translation_request (unexpected error)")
            return results

        self.logger.debug("Function end: translation_request (success)")
        return results
