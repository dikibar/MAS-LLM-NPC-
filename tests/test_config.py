import sys
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from core.config import Settings


class SettingsTests(unittest.TestCase):
    def test_openrouter_url_is_preserved(self):
        settings = Settings(
            _env_file=None,
            OPENROUTER_BASE_URL="https://openrouter.ai/api/v1",
        )

        self.assertEqual(settings.llm_base_url, "https://openrouter.ai/api/v1")

    def test_azure_project_url_becomes_openai_v1_url(self):
        settings = Settings(
            _env_file=None,
            OPENROUTER_BASE_URL=(
                "https://example.services.ai.azure.com/api/projects/MultiAgent"
            ),
        )

        self.assertEqual(
            settings.llm_base_url,
            "https://example.services.ai.azure.com/openai/v1/",
        )

    def test_gpt5_uses_supported_chat_completion_parameters(self):
        settings = Settings(
            _env_file=None,
            OPENROUTER_MODEL="gpt-5-mini",
        )

        self.assertEqual(
            settings.llm_model_params,
            {
                "max_completion_tokens": 1000,
                "reasoning_effort": "minimal",
            },
        )

    def test_model_params_can_be_resolved_for_separate_judge_model(self):
        settings = Settings(
            _env_file=None,
            OPENROUTER_MODEL="gpt-5-mini",
        )

        self.assertEqual(
            settings.model_params_for(
                "openai/gpt-4.1",
                500,
                temperature=0,
            ),
            {
                "max_tokens": 500,
                "temperature": 0,
            },
        )


if __name__ == "__main__":
    unittest.main()
