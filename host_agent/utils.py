import re

_CJK_PATTERN = re.compile(r"[\u4e00-\u9fff]")


def detect_language(text: str | None) -> str:
    """Return 'zh' for CJK input and 'en' otherwise."""
    if text and _CJK_PATTERN.search(text):
        return "zh"
    return "en"
