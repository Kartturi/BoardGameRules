"""AI generation package for fallback rules, quick recaps, and grounded answers."""

from boardgamerules.ai.config import AiSettings
from boardgamerules.ai.generator import GeminiAiRuleGenerator, create_gemini_ai_generator
from boardgamerules.ai.prompts import (
    PromptBundle,
    build_fallback_rules_prompt,
    build_quick_recap_prompt,
    build_rule_answer_prompt,
)
from boardgamerules.ai.schemas import (
    FallbackRulesSchema,
    QuickRecapSchema,
    RuleAnswerSchema,
    map_fallback_rules_to_domain,
    map_quick_recap_to_domain,
    map_rule_answer_to_domain,
)

__all__ = [
    "AiSettings",
    "FallbackRulesSchema",
    "GeminiAiRuleGenerator",
    "PromptBundle",
    "QuickRecapSchema",
    "RuleAnswerSchema",
    "build_fallback_rules_prompt",
    "build_quick_recap_prompt",
    "build_rule_answer_prompt",
    "create_gemini_ai_generator",
    "map_fallback_rules_to_domain",
    "map_quick_recap_to_domain",
    "map_rule_answer_to_domain",
]
