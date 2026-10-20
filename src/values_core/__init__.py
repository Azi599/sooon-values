"""values-core：把一套核心价值观做成任意 AI 都能调用的判断依据。

    from values_core import Store, build_context
    store = Store()
    print(build_context(store, "同事抢了我的功劳怎么办"))
"""
from .doctrine import as_markdown, as_text, sections
from .render import build_context, render_entry
from .store import Entry, SearchHit, Store, StoreError

__version__ = "1.0.0"
__all__ = [
    "Store", "Entry", "SearchHit", "StoreError",
    "build_context", "render_entry",
    "as_text", "as_markdown", "sections",
    "__version__",
]
