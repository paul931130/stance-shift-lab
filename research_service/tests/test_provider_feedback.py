"""Schema-failure feedback, failed-call routing and retry accounting found by the Gemini smoke test."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from jsonschema import ValidationError

from research_service import model_router, models
from research_service.protocol import StudyProtocol, decision_plan


class FakeLiteLLM:
    """Answers with an over-long field first, then a valid one; records every request."""

    def __init__(self, answers):
        self.answers, self.requests = list(answers), []

    def get_supported_openai_params(self, model):
        return []

    def completion(self, **kwargs):
        self.requests.append(kwargs["messages"])
        content = self.answers.pop(0)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
                               usage={"prompt_tokens": 10, "completion_tokens": 5}, model="gemini-test")


class SchemaFeedbackTests(unittest.TestCase):
    schema = {"type": "object", "required": ["note"], "additionalProperties": False,
              "properties": {"note": {"type": "string", "maxLength": 5}}}

    def run_generate(self, answers):
        fake = FakeLiteLLM(answers)
        protocol = StudyProtocol(model="gemini/gemini-2.5-flash")
        messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
        with patch.dict("sys.modules", {"litellm": fake}), \
                patch.object(models, "output_schema_for", lambda _: self.schema), \
                patch.object(models, "_completion_with_rate_limit_wait", lambda lib, kwargs, usage: lib.completion(**kwargs)), \
                patch.object(models.time, "sleep", lambda _: None):
            return fake, messages, models.generate(protocol, messages)

    def test_retry_names_the_failed_field_and_limit(self):
        fake, messages, (result, audit) = self.run_generate([json.dumps({"note": "far too long"}),
                                                             json.dumps({"note": "ok"})])
        self.assertEqual(result, {"note": "ok"})
        self.assertEqual(fake.requests[0], messages)
        feedback = fake.requests[1][-1]["content"]
        self.assertIn("`note`", feedback)
        self.assertIn("maxLength 5", feedback)
        self.assertEqual(fake.requests[1][:-1], messages)
        self.assertEqual(audit["attempts"][0]["schema_feedback"], feedback)
        self.assertEqual(audit["prompt_hash"], models.digest(messages))

    def test_non_schema_errors_get_no_feedback(self):
        self.assertIsNone(models.schema_feedback(ValueError("x")))
        self.assertIsNone(models.schema_feedback(json.JSONDecodeError("x", "{", 0)))
        self.assertIn("maxLength", models.schema_feedback(ValidationError("too long", validator="maxLength",
                                                                          validator_value=240, path=["a"])))


class RouterAccountingTests(unittest.TestCase):
    def test_failed_routed_call_carries_its_model_route(self):
        protocol = StudyProtocol.router(model="ollama/qwen3:32b", debate_model_b="ollama/gemma3:27b")
        call = next(c for c in decision_plan(protocol) if getattr(c, "assignment", None) == "AB"
                    and c.kind == "debate" and c.agent == "agent-b")
        error = ValidationError("too long")
        error.model_attempt_audit = {"provider_attempts": 3, "attempts": []}

        def failing(*args, **kwargs):
            raise error

        with self.assertRaises(ValidationError) as caught:
            model_router.call_with_route(failing, protocol, call, call.key, [], 1, {"temperature": .2})
        route = caught.exception.model_attempt_audit["model_route"]
        self.assertEqual((route["model"], route["model_slot"], route["status"]), ("ollama/gemma3:27b", "B", "failed"))

    def test_route_retry_count_matches_compute_usage_rule(self):
        audit = {"model_route": {}, "validation_retries": [{"accepted_as_output": True}, {"error_type": "ValueError"}]}
        route = model_router.finalize_route(audit)["model_route"]
        self.assertEqual((route["validation_retries"], route["accepted_after_check"]), (1, 1))


if __name__ == "__main__":
    unittest.main()
