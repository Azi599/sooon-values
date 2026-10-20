"""MCP 服务（stdio 传输），零第三方依赖。

MCP 客户端只要把命令配成 `python values.pyz mcp` 就能接入。
提供 6 个工具 + 2 个资源 + 1 个提示词模板。

工具描述刻意写得具体：模型是否调用，几乎完全取决于描述。
"""
from __future__ import annotations

import json
import sys

from . import doctrine, render
from .store import Store, StoreError

PROTOCOL = "2024-11-05"
SERVER_INFO = {"name": "values-core", "version": "1.0.0"}

TOOLS = [
    {
        "name": "values_route",
        "description": (
            "判断一条问题该不该按「核心价值观」回答，以及它归属哪几支分类。"
            "先定一级（与自己／与亲族／与友人／与合作者／与社会／与其它／与自然），"
            "再二级，再三级，返回占比最高的几条路径。"
            "在决定是否调用 values_context 之前，可以用它做一次预判。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "用户的问题或情境描述"},
                "top": {"type": "integer", "description": "返回几条候选路径，默认 5",
                        "minimum": 1, "maximum": 10},
            },
            "required": ["question"],
        },
    },
    {
        "name": "values_search",
        "description": (
            "在条目库里检索（BM25，标题加权）。"
            "当问题涉及人际冲突、亲密关系、情绪处理、职业伦理、财富取舍、"
            "教育、社会议题时用它找原文依据。返回条目编号、标题、分类、摘要和原文链接。"
            "拿到编号后可用 values_get 取全文。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "检索词或问题描述"},
                "path": {"type": "string",
                         "description": "限定三级路径，如「与友人 / 与恋人 / 相处」；也可只给末级名如「相处」"},
                "limit": {"type": "integer", "description": "返回条数，默认 6",
                          "minimum": 1, "maximum": 20},
            },
            "required": ["query"],
        },
    },
    {
        "name": "values_get",
        "description": (
            "按编号取「核心价值观」单条全文，附分类、原文链接和同分类的相邻条目。"
            "在你已经知道条目编号、或需要核对某条到底怎么说的时使用。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "n": {"type": "integer", "description": "条目编号，例如 1546"},
            },
            "required": ["n"],
        },
    },
    {
        "name": "values_doctrine",
        "description": (
            "取「核心价值观」的判断准则（93 条，分 12 节：总纲、归因与责任、爱与亲密关系、"
            "亲子、情绪与表达、能力与学习、财富与欲望、时间与人生、名誉与尊严、"
            "合作与权力、社会与舆论、边界）。tier=core 只返回 41 条核心准则，"
            "适合上下文紧张时；tier=full 返回全部。"
            "默认不带条目编号：引用依据请改用 values_search / values_context 给出的链接，"
            "把 [《标题》](链接) 写进回答，不要写裸编号。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "tier": {"type": "string", "enum": ["core", "full"],
                         "description": "core=核心准则（默认），full=全部"},
                "section": {"type": "string",
                            "description": "只看某一节，按标题模糊匹配，例如「情绪」「财富」"},
                "with_source": {"type": "boolean",
                                "description": "带来源条目编号（〔1546〕形式），仅供内部核对，"
                                               "不要写进给用户的回答"},
            },
        },
    },
    {
        "name": "values_context",
        "description": (
            "一次拿到可直接使用的完整判断上下文：命中的分类范围 + 判断准则 + 本题最相关的原文"
            "（含可引用的链接）+ 使用约束。"
            "**它会自己判断这条问题该不该用这套价值观**：不属于的（查资料、写代码、翻译、"
            "配置、推荐）返回【不加载】，此时按你平常的方式回答，不要强行套用。"
            "属于的只加载命中分类对应的章节，不会整本倒给你。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "用户的问题或情境"},
                "budget": {"type": "integer", "description": "总字数上限，默认 6000",
                           "minimum": 1200, "maximum": 30000},
                "limit": {"type": "integer", "description": "带几条原文，默认 6",
                          "minimum": 0, "maximum": 20},
                "tier": {"type": "string", "enum": ["core", "full"],
                         "description": "准则层级，默认 core"},
                "with_style": {"type": "boolean",
                               "description": "是否附上文风规则（默认 false）"},
                "force": {"type": "boolean",
                          "description": "不按分类裁剪，输出全部准则（默认只给相关章节）"},
            },
            "required": ["question"],
        },
    },
    {
        "name": "values_style",
        "description": (
            "取「核心价值观」的文风规则：句法、论证方式、态度、引用格式。"
            "当用户要求「用这套价值观的语气写」「像这个人一样说」时使用。"
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
]

RESOURCES = [
    {
        "uri": "values://doctrine",
        "name": "判断准则（全部）",
        "description": "88 条判断准则，分 11 节，每条带来源编号。",
        "mimeType": "text/markdown",
    },
    {
        "uri": "values://doctrine/core",
        "name": "判断准则（核心）",
        "description": "42 条核心准则，适合直接作为系统提示词。",
        "mimeType": "text/markdown",
    },
    {
        "uri": "values://style",
        "name": "文风规则",
        "description": "这套价值观的表达方式与引用规范。",
        "mimeType": "text/markdown",
    },
    {
        "uri": "values://stats",
        "name": "数据概况",
        "description": "条目数、分类数、版本。",
        "mimeType": "application/json",
    },
]

PROMPTS = [
    {
        "name": "values_grounded_answer",
        "description": "按核心价值观回答一个涉及判断的问题（自动带入准则与相关原文）。",
        "arguments": [
            {"name": "question", "description": "用户的问题", "required": True},
        ],
    }
]


class Server:
    def __init__(self, data_file: str | None = None):
        self.store = Store(data_file)

    # ---------- 工具实现 ----------

    def _tool_route(self, a: dict) -> str:
        rows = self.store.route(str(a.get("question") or ""),
                                top=int(a.get("top") or 5))
        if not rows:
            return "没有匹配到分类。可直接用 values_search 按关键词检索。"
        head = ""
        body = "\n".join(
            f"{r['score']:>6}  {r['path']}（{r['entries']} 条）" for r in rows
        )
        return head + body

    def _tool_search(self, a: dict) -> str:
        hits = self.store.search(str(a.get("query") or ""),
                                 path=a.get("path"),
                                 limit=int(a.get("limit") or 6))
        if not hits:
            return "没有找到相关条目。可以换一种说法，或先用 values_route 看分类。"
        out = []
        for h in hits:
            e = h.entry
            path = e.paths[0] if e.paths else "未分类"
            out.append(f"[{e.n}] {e.title}（{path}）\n{e.summary[:200]}")
        return "\n\n".join(out)

    def _tool_get(self, a: dict) -> str:
        return render.render_entry(self.store, int(a.get("n") or 0))

    def _tool_doctrine(self, a: dict) -> str:
        tier = a.get("tier") if a.get("tier") in ("core", "full") else "core"
        text = doctrine.as_text("doctrine", tier, with_src=bool(a.get("with_source")))
        sec = str(a.get("section") or "").strip()
        if not sec:
            return text
        blocks = text.split("\n【")
        keep = [b for b in blocks if sec in b.split("】")[0]]
        return "【" + "\n【".join(keep) if keep else f"没有标题含「{sec}」的章节。"

    def _tool_context(self, a: dict) -> str:
        text = render.build_context(
            self.store, str(a.get("question") or ""),
            limit=int(a.get("limit") if a.get("limit") is not None else 6),
            tier=a.get("tier") if a.get("tier") in ("core", "full") else "core",
            budget=int(a.get("budget") or 6000),
            with_style=bool(a.get("with_style")),
            force=bool(a.get("force")),
        )
        return text

    def _tool_style(self, _a: dict) -> str:
        return doctrine.as_text("voice", "full")

    # ---------- 资源 ----------

    def _resource(self, uri: str) -> tuple[str, str]:
        if uri == "values://doctrine":
            return "text/markdown", doctrine.as_markdown("doctrine", "full")
        if uri == "values://doctrine/core":
            return "text/markdown", doctrine.as_markdown("doctrine", "core")
        if uri == "values://style":
            return "text/markdown", doctrine.as_markdown("voice", "full")
        if uri == "values://stats":
            return "application/json", json.dumps(self.store.stats(), ensure_ascii=False, indent=1)
        raise KeyError(uri)

    # ---------- 协议 ----------

    def handle(self, msg: dict) -> dict | None:
        method = msg.get("method")
        mid = msg.get("id")
        params = msg.get("params") or {}

        # 通知不需要回复
        if mid is None and isinstance(method, str) and method.startswith("notifications/"):
            return None

        if method == "initialize":
            return self._ok(mid, {
                "protocolVersion": params.get("protocolVersion") or PROTOCOL,
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {"subscribe": False, "listChanged": False},
                    "prompts": {"listChanged": False},
                },
                "serverInfo": SERVER_INFO,
            })

        if method == "ping":
            return self._ok(mid, {})

        if method == "tools/list":
            return self._ok(mid, {"tools": TOOLS})

        if method == "tools/call":
            name = params.get("name")
            args = params.get("arguments") or {}
            table = {
                "values_route": self._tool_route,
                "values_search": self._tool_search,
                "values_get": self._tool_get,
                "values_doctrine": self._tool_doctrine,
                "values_context": self._tool_context,
                "values_style": self._tool_style,
            }
            fn = table.get(name)
            if fn is None:
                return self._err(mid, -32602, f"未知工具：{name}")
            try:
                text = fn(args)
            except (ValueError, TypeError, KeyError) as e:
                return self._ok(mid, {"content": [{"type": "text", "text": f"参数有误：{e}"}],
                                      "isError": True})
            return self._ok(mid, {"content": [{"type": "text", "text": text}],
                                  "isError": False})

        if method == "resources/list":
            return self._ok(mid, {"resources": RESOURCES})

        if method == "resources/read":
            uri = str(params.get("uri") or "")
            try:
                mime, text = self._resource(uri)
            except KeyError:
                return self._err(mid, -32602, f"未知资源：{uri}")
            return self._ok(mid, {"contents": [{"uri": uri, "mimeType": mime, "text": text}]})

        if method == "prompts/list":
            return self._ok(mid, {"prompts": PROMPTS})

        if method == "prompts/get":
            name = params.get("name")
            if name != "values_grounded_answer":
                return self._err(mid, -32602, f"未知提示词：{name}")
            q = str((params.get("arguments") or {}).get("question") or "")
            body = render.build_context(self.store, q, limit=6, tier="core", budget=6000)
            if not body:
                body = "（这条问题不在核心价值观的覆盖范围内，按你平常的方式回答即可。）"
            return self._ok(mid, {
                "description": "按核心价值观回答",
                "messages": [{"role": "user", "content": {"type": "text",
                                                          "text": body + "\n\n【问题】\n" + q}}],
            })

        return self._err(mid, -32601, f"未实现的方法：{method}")

    @staticmethod
    def _ok(mid, result) -> dict:
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    @staticmethod
    def _err(mid, code: int, message: str) -> dict:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def serve(data_file: str | None = None) -> None:
    """读 stdin 的逐行 JSON-RPC，写 stdout。日志一律走 stderr。"""
    try:
        srv = Server(data_file)
    except StoreError as e:
        sys.stderr.write(f"values-core 无法启动：{e}\n")
        raise SystemExit(2) from e

    sys.stderr.write(
        f"values-core 已启动：{srv.store.count} 条，"
        f"{len(srv.store.leaf_paths)} 条路径，数据源 {srv.store.source}\n"
    )
    sys.stderr.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            sys.stdout.write(json.dumps(
                {"jsonrpc": "2.0", "id": None,
                 "error": {"code": -32700, "message": "JSON 解析失败"}}) + "\n")
            sys.stdout.flush()
            continue

        if isinstance(msg, list):
            replies = [r for r in (srv.handle(m) for m in msg if isinstance(m, dict)) if r]
        else:
            replies = [srv.handle(msg)] if isinstance(msg, dict) else []

        for r in replies:
            if r is None:
                continue
            sys.stdout.write(json.dumps(r, ensure_ascii=False) + "\n")
        sys.stdout.flush()
