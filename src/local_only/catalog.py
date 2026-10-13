"""Provider catalog boundary for the standalone variant.

The native provider catalog (`resources/config/provider/zcode-builtin.json`) ships
account-owned Zhipu providers and their templates. This patch drops them and adds
a native 9Router template so the app offers the local gateway the same way it
offers OpenAI/DeepSeek, without the manual custom-provider flow.
"""
import json

ZHIPU_TEMPLATES = ("zai-api", "zai-standard-api", "bigmodel-api", "bigmodel-standard-api")
ZHIPU_ACCOUNT_GROUPS = ("zai-family", "bigmodel-family")
ZHIPU_MARKERS = ("z.ai", "bigmodel.cn", "account:zai", "account:bigmodel", "zhipu-account", "zhipu-coding-plan-api-key")
NINEROUTER_TEMPLATE_ID = "9router"
NINEROUTER_BASE_URL = "http://127.0.0.1:20128/v1"
NINEROUTER_MODEL = "combo/coding-harian"
NINEROUTER_TEMPLATE = {
    "templateId": NINEROUTER_TEMPLATE_ID,
    "templateNameMap": {"zh-CN": "9Router", "en-US": "9Router"},
    "config": {
        "access": {"type": "api-key"},
        "api": {"type": "openai-chat-completions", "baseUrl": NINEROUTER_BASE_URL},
        "builtinModelIds": [NINEROUTER_MODEL],
    },
}


def _is_zhipu_template(rule):
    if rule.get("templateId") in ZHIPU_TEMPLATES:
        return True
    config = rule.get("config") or {}
    access = config.get("access") or {}
    return access.get("type") == "zhipu-coding-plan-api-key"


def _is_zhipu_provider(rule):
    provider_id = str(rule.get("providerId") or "")
    config = rule.get("config") or {}
    access = config.get("access") or {}
    if provider_id.startswith("account:zai") or provider_id.startswith("account:bigmodel"):
        return True
    if access.get("type") == "zhipu-account":
        return True
    return config.get("group") in ZHIPU_ACCOUNT_GROUPS


def _is_zhipu_model_rule(entry):
    text = json.dumps(entry, ensure_ascii=False)
    if NINEROUTER_TEMPLATE_ID in text:
        return False
    if entry.get('templateId') in ZHIPU_TEMPLATES or entry.get('providerId') in ('zai', 'bigmodel'):
        return True
    return any(marker in text for marker in ZHIPU_MARKERS)


def patch_catalog(text):
    """Return the catalog JSON without Zhipu providers and with the 9Router template."""
    document = json.loads(text)
    config = document.get("config") or {}
    provider_rules = config.get("providerConfigRules") or {}
    if "templateRules" not in provider_rules or "providerRules" not in provider_rules:
        raise ValueError("Provider catalog shape changed: providerConfigRules is incomplete")

    provider_rules["providerRules"] = [rule for rule in provider_rules["providerRules"] if not _is_zhipu_provider(rule)]
    templates = [rule for rule in provider_rules["templateRules"] if not _is_zhipu_template(rule)]
    templates = [rule for rule in templates if rule.get("templateId") != NINEROUTER_TEMPLATE_ID]
    templates.append(json.loads(json.dumps(NINEROUTER_TEMPLATE)))
    provider_rules["templateRules"] = templates

    model_rules = config.get("modelConfigRules")
    if isinstance(model_rules, dict):
        for key, entries in list(model_rules.items()):
            if isinstance(entries, list):
                model_rules[key] = [entry for entry in entries if not _is_zhipu_model_rule(entry)]

    if config.get("modelConfigRules") is not None:
        _ensure_ninerouter_model_rule(config["modelConfigRules"])
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def _ensure_ninerouter_model_rule(model_rules):
    """Give the combo the capability metadata 9Router reports for it."""
    entries = model_rules.get("modelRules")
    if not isinstance(entries, list):
        return
    entries = [entry for entry in entries if entry.get("modelMatch") != NINEROUTER_MODEL]
    entries.append({
        "modelMatch": NINEROUTER_MODEL,
        "config": {
            "enabled": True,
            "properties": {
                "contextWindow": 1000000,
                "inputFormat": {"supportsText": True, "supportsImage": True, "supportsPdf": False,
                                "supportsAudio": False, "supportsVideo": False},
                "outputFormat": {"supportsText": True},
                "supportsToolCall": True,
                "supportsJsonSchemaOutput": False,
                "supportsNativeWebSearch": False,
                "supportsMidConversationSystem": False,
                "requiresMfjsToolSchema": False,
            },
            "optionSpecs": {
                "maxOutputTokens": {"max": 384000},
                # The combo fixes its members' reasoning upstream, so the picker
                # must not offer levels that never reach the provider.
                "reasoningLevel": {"values": ["disabled"], "map": "{}"},
            },
        },
    })
    model_rules["modelRules"] = entries
