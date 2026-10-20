"""把准则与条目组装成一段可直接粘进任意 AI 的上下文块。

这里不做「该不该用」的判断——那由宿主模型自己决定。
本模块只负责：按检索结果挑出相关章节与条目，按预算裁剪，附上怎么说。
"""
from __future__ import annotations

from . import doctrine
from .store import Entry, Store, match_tokens

USAGE_LINES = [
    "【怎么用】",
    "- 像平常说话一样回答，先给结论，句子短。"
    "不要提“这套准则”“体系”“第几条”，也不要说明这些内容从哪来、有多少条。",
    "- 只回答对方实际问的那一点，用不上的别讲。",
    "- 不要主动标注出处。对方问到“依据 / 出处 / 原文”时，再用下面给的链接回答；没问就别标。",
    "- 摘要只有一两百字，细节可能丢。需要更具体的例子、数字、论证时，"
    "可以打开下面给的原文链接读全文再回答，以原文为准；打不开就用摘要，不要假装读过。",
    "- 对方没问就不搬这套东西；不替他做重大决定；医学、法律、财税、安全以专业意见为先。",
]

# 一级分类 → 该加载哪几节准则。命中哪个一级，就只带它对应的章节。
_SECTIONS_BY_L1 = {
    "与自己": ("归因与责任", "情绪与表达", "能力与学习", "财富与欲望",
               "时间与人生", "名誉与尊严"),
    "与亲族": ("爱与亲密关系", "亲子"),
    "与友人": ("爱与亲密关系",),
    "与合作者": ("合作与权力",),
    "与社会": ("社会与舆论",),
    "与其它": ("社会与舆论",),
    "与自然": (),
}


def _header(tier: str) -> str:
    kind = "判断标准" if tier == "core" else "判断标准（全部）"
    return (
        f"【{kind}】\n"
        "按下面的标准判断，用平常说话的方式回答。\n"
        "不必向对方说明这些内容的来源、条数或整理过程。\n"
        "「相关原文」里每条都带链接，摘要不够用时可以打开读全文。\n"
    )


def _entry_block(e: Entry, max_chars: int = 360) -> str:
    body = e.summary.strip()
    if len(body) > max_chars:
        body = body[:max_chars].rstrip() + "…"
    path = e.paths[0] if e.paths else "未分类"
    title = e.title or "无标题"
    # 编号写成「编号 440」而不是 [440]：后者太像引用标记，模型会照抄进回答
    lines = [f"《{title}》（{path}；编号 {e.n}，仅供 values get 取全文）", body]
    if e.url:
        lines.append(f"原文：{e.url}")
        lines.append(f"引用写法：[《{title}》]({e.url})")
    return "\n".join(lines)


def _rank_sections(question: str, tier: str, doc_dir: str | None,
                   allowed: tuple[str, ...] | None = None) -> list[dict]:
    """总纲永远第一；其余只保留命中一级对应的章节，再按相关度排序。"""
    secs = doctrine.sections("doctrine", tier, doc_dir)
    qs = set(match_tokens(question))

    def score(sec: dict) -> float:
        title_hit = qs & set(match_tokens(sec["title"]))
        body = "".join(r["text"] for r in sec["rules"])
        body_hit = qs & set(match_tokens(body))
        return 3.0 * len(title_hit) + 1.0 * len(body_hit)

    head = [s for s in secs if "总纲" in s["title"]]
    rest = [s for s in secs if "总纲" not in s["title"]]
    if allowed:
        rest = [s for s in rest if any(a in s["title"] for a in allowed)]
    rest.sort(key=score, reverse=True)
    return head + rest


def _scope_line(match: dict) -> str:
    branches = match.get("branches") or []
    if not branches:
        return ""
    names: list[str] = []
    for b in branches[:3]:
        if b["path"] not in names:
            names.append(b["path"])
    return f"【相关范围】{'；'.join(names)}"


def build_context(store: Store, question: str, *, limit: int = 6,
                  tier: str = "core", budget: int = 4000,
                  with_style: bool = False, path: str | None = None,
                  doc_dir: str | None = None, force: bool = False) -> str:
    """组装上下文块。

    不做相关性判断：调不调由模型决定，调了就给内容。
    只按检索命中的一级挑章节，避免把整本准则都塞进去。
    """
    budget = max(800, int(budget or 4000))

    if path:
        hits = store.search(question, path=path, limit=limit)
        allowed, head = None, _header(tier)
    elif force:
        hits = store._rank_all(question, limit)
        allowed = None
        head = _header(tier).rstrip() + "\n【相关范围】全部（未按分类裁剪）\n"
    else:
        match = store.match(question)
        hits = match["hits"][:limit]
        if not hits:
            hits = store._rank_all(question, limit)
        seen: list[str] = []
        for b in match["branches"]:
            seen.extend(_SECTIONS_BY_L1.get(b["l1"], ()))
        allowed = tuple(dict.fromkeys(seen)) or None
        head = _header(tier)
        scope = _scope_line(match)
        if scope:
            head = head.rstrip() + "\n" + scope + "\n"

    footer = "\n".join(USAGE_LINES)

    style_txt = ""
    if with_style:
        style_txt = "\n【文风】\n" + doctrine.as_text("voice", "full", doc_dir)

    fixed = len(head) + len(footer) + len(style_txt) + 150
    room = max(400, budget - fixed)

    # 准则最多占 62% 的空间
    rule_cap = int(room * 0.62)
    rule_parts: list[str] = []
    used = 0
    for sec in _rank_sections(question, tier, doc_dir, allowed):
        block = [f"【{sec['title']}】"]
        for r in sec["rules"]:
            block.append(f"- {doctrine.plain(r['text'])}")
        chunk = "\n".join(block) + "\n"
        if rule_parts and used + len(chunk) > rule_cap:
            break
        rule_parts.append(chunk)
        used += len(chunk)

    rules_txt = "\n".join(rule_parts).strip()

    entry_cap = max(300, room - len(rules_txt))
    entry_parts: list[str] = []
    used_e = 0
    for hit in hits:
        block = _entry_block(hit.entry)
        if entry_parts and used_e + len(block) > entry_cap:
            break
        entry_parts.append(block)
        used_e += len(block) + 2

    parts = [head, rules_txt]
    if entry_parts:
        parts.append("\n【相关原文】\n" + "\n\n".join(entry_parts))
    if style_txt:
        parts.append(style_txt.strip())
    parts.append(footer)
    return "\n\n".join(p for p in parts if p).strip()


def render_entry(store: Store, n: int, *, with_neighbors: bool = True) -> str:
    """单条的完整展示（命令行 get 用）。"""
    e = store.get(n)
    if not e:
        return f"没有第 {n} 条。可用范围 1-{max(store.entries) if store.entries else 0}。"
    title = e.title or "无标题"
    lines = [f"[{e.n}] {title}", ""]
    if e.paths:
        lines.append("分类：" + "；".join(e.paths))
    if e.url:
        lines.append("原文：" + e.url)
        lines.append(f"引用：[《{title}》]({e.url})")
    lines += ["", e.summary.strip()]
    if with_neighbors:
        nb = store.neighbors(n, limit=5)
        if nb:
            lines += ["", "同分类还有：" + "、".join(f"[{x.n}] {x.title}" for x in nb)]
    return "\n".join(lines)
