from services.llm import call_llm_json
from unittest.mock import patch


def test_strips_markdown_fences():
    with patch("services.llm.call_llm", return_value='```json\n{"a": 1}\n```'):
        result = call_llm_json("system", "user")
        assert result == {"a": 1}
