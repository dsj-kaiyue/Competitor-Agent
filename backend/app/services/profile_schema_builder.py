import hashlib
import re


DIMENSION_KEY_MAP = {
    "产品定位": "positioning",
    "核心功能": "core_features",
    "Agent 能力": "agent_capabilities",
    "IDE 集成": "ide_integration",
    "价格策略": "pricing_strategy",
    "企业能力": "enterprise_capabilities",
    "安全合规": "security_compliance",
    "适用用户": "target_users",
    "目标用户": "target_users",
    "开发者生态": "developer_ecosystem",
    "数据采集能力": "data_collection_capabilities",
    "网页抓取能力": "web_scraping_capabilities",
    "结构化抽取能力": "structured_extraction_capabilities",
    "引用质量": "citation_quality",
    "搜索能力": "search_capabilities",
    "多模态能力": "multimodal_capabilities",
    "智能驾驶": "intelligent_driving",
    "续航能力": "driving_range",
    "补能体系": "charging_network",
}

FIELD_PRESETS = {
    "pricing_strategy": {
        "type": "text",
        "required": True,
        "source_requirements": ["pricing_page", "official_website"],
        "query_templates": [
            "{competitor} pricing plans official",
            "{competitor} subscription billing team enterprise",
        ],
    },
    "security_compliance": {
        "type": "text",
        "required": False,
        "source_requirements": ["security", "enterprise", "docs", "official_website"],
        "query_templates": [
            "{competitor} security privacy compliance official",
            "{competitor} enterprise trust center data protection",
        ],
    },
    "core_features": {
        "type": "list",
        "required": True,
        "source_requirements": ["official_website", "docs", "blog"],
        "query_templates": [
            "{competitor} core features documentation",
            "{competitor} product capabilities official",
        ],
    },
}

DEFAULT_FIELD = {
    "type": "text",
    "required": False,
    "source_requirements": ["official_website", "docs", "blog"],
    "query_templates": ["{competitor} {label} official"],
}


def _dimension_key(label: str, index: int) -> str:
    normalized = re.sub(r"\s+", " ", label).strip()
    if normalized in DIMENSION_KEY_MAP:
        return DIMENSION_KEY_MAP[normalized]

    ascii_words = re.findall(r"[A-Za-z0-9]+", normalized)
    if ascii_words:
        suffix = "support" if "支持" in normalized and ascii_words[-1].lower() != "support" else None
        words = [word.lower() for word in ascii_words]
        if suffix:
            words.append(suffix)
        return "_".join(words)

    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:8]
    return f"dimension_{index + 1}_{digest}"


class ProfileSchemaBuilder:
    def build_schema(self, task_plan: dict) -> dict:
        dimensions = [str(item).strip() for item in task_plan.get("analysis_dimensions", []) if str(item).strip()]
        fields = []
        seen_keys: set[str] = set()
        for index, label in enumerate(dimensions):
            key = _dimension_key(label, index)
            if key in seen_keys:
                key = f"{key}_{index + 1}"
            seen_keys.add(key)
            preset = {**DEFAULT_FIELD, **FIELD_PRESETS.get(key, {})}
            fields.append(
                {
                    "key": key,
                    "label": label,
                    "type": preset["type"],
                    "required": preset["required"],
                    "description": f"围绕“{label}”分析产品表现、差异化和证据支撑。",
                    "source_requirements": preset["source_requirements"],
                    "query_templates": preset["query_templates"],
                }
            )
        return {
            "template_key": task_plan.get("template_key"),
            "industry": task_plan.get("industry"),
            "fields": fields,
        }
