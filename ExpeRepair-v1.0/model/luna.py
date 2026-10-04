"""
gpt-5.6-luna via Codemate LiteLLM proxy (OpenAI-compatible endpoint).

Uses AZURE_LLM_API_KEY / AZURE_LLM_BASE_URL instead of OPENAI_KEY.
Inherits call()/call_n() from model.gpt.OpenaiModel, where temperature
and max_tokens are already commented out (o3-mini compat), so no
temperature patch is needed for Luna.
"""

import os
import sys

from openai import OpenAI

from model.gpt import OpenaiModel


class Gpt56Luna(OpenaiModel):
    def __init__(self):
        super().__init__(
            "gpt-5.6-luna", 12288, 0.0000011, 0.0000044, parallel_tool_call=True
        )
        self.note = "gpt-5.6-luna via Codemate proxy. Costs are placeholders."

    def setup(self) -> None:
        """
        Check API key, and initialize OpenAI client against the proxy.
        """
        if self.client is None:
            key = self.check_api_key()
            base_url = os.getenv("AZURE_LLM_BASE_URL")
            if not base_url:
                print("Please set the AZURE_LLM_BASE_URL env var")
                sys.exit(1)
            self.client = OpenAI(
                base_url=base_url,
                api_key=key,
            )

    def check_api_key(self) -> str:
        key = os.getenv("AZURE_LLM_API_KEY")
        if not key:
            print("Please set the AZURE_LLM_API_KEY env var")
            sys.exit(1)
        return key
