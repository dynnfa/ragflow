"""Exercise TTS selection without importing the RAG runtime's native dependencies."""

import ast
import logging
import re
import time
from datetime import datetime, timezone
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call


class DialogTtsModelTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        source = Path(__file__).resolve().parents[5] / "api/db/services/dialog_service.py"
        tree = ast.parse(source.read_text())
        functions = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in ("_get_tts_model_config", "get_models", "async_chat_solo")]
        self.resolve = Mock(return_value={"model": "team-tts"})
        self.default = Mock(return_value={"model": "personal-tts", "model_type": "chat"})
        namespace = {
            "resolve_model_config": self.resolve,
            "get_tenant_default_model_by_type": self.default,
            "LLMType": SimpleNamespace(TTS="tts", CHAT="chat"),
            "KnowledgebaseService": SimpleNamespace(get_by_ids=lambda _: []),
            "validate_dataset_embedding_models": lambda _: None,
            "LLMBundle": lambda tenant, config, **kwargs: SimpleNamespace(config=config, trace_context=None, async_chat=AsyncMock(return_value="answer")),
            "get_files_content": lambda *_: ("", [], []),
            "tts": lambda model, _: model.config,
            "re": re,
            "logging": logging,
            "time": time,
            "datetime": datetime,
            "timezone": timezone,
        }
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), "exec"), namespace)
        self.solo = namespace["async_chat_solo"]
        self.select = lambda dialog: namespace["get_models"](dialog)[4].config

    def test_saved_team_model_is_resolved_as_the_resource_owner(self):
        dialog = SimpleNamespace(tenant_id="member", kb_ids=[], llm_id="", rerank_id="", prompt_config={"tts": True, "tts_model_id": "team-model-id"})
        self.assertEqual(self.select(dialog), {"model": "team-tts"})
        self.resolve.assert_called_once_with("member", "tts", "team-model-id")
        self.assertNotIn(call("member", "tts"), self.default.call_args_list)

    def test_unset_selection_uses_resource_default(self):
        dialog = SimpleNamespace(tenant_id="member", kb_ids=[], llm_id="", rerank_id="", prompt_config={"tts": True})
        self.assertEqual(self.select(dialog)["model"], "personal-tts")
        self.default.assert_any_call("member", "tts")

    def test_revoked_model_access_does_not_fall_back_to_personal_credentials(self):
        self.resolve.side_effect = LookupError("access denied")
        dialog = SimpleNamespace(tenant_id="member", kb_ids=[], llm_id="", rerank_id="", prompt_config={"tts": True, "tts_model_id": "team-model-id"})
        with self.assertRaisesRegex(LookupError, "access denied"):
            self.select(dialog)
        self.assertNotIn(call("member", "tts"), self.default.call_args_list)

    async def test_solo_chat_synthesizes_with_the_saved_team_model(self):
        dialog = SimpleNamespace(tenant_id="member", llm_id="", llm_setting={}, prompt_config={"tts": True, "tts_model_id": "team-model-id"})
        responses = [response async for response in self.solo(dialog, [{"role": "user", "content": "hello"}], stream=False)]
        self.assertEqual(responses[0]["audio_binary"], {"model": "team-tts"})
        self.resolve.assert_called_once_with("member", "tts", "team-model-id")
