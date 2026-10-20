"""判断准则与文风的读取、分层与渲染。

数据目录里放两个 Markdown：
    doctrine.md  判断准则，每条以 "- " 开头，★ 表示核心条目，末尾 〔N〕 是来源编号
    voice.md     文风规则

可用 VALUES_DOC_DIR 指向自定义目录，方便改了不用重打包。
"""
from __future__ import annotations

import os
import pkgutil
import re
from pathlib import Path

DOC_FILES = {"doctrine": "doctrine.md", "voice": "voice.md"}

_HEAD = re.compile(r"^(#{1,3})\s+(.*)$")
_BULLET = re.compile(r"^[-*]\s+(.*)$")
_SRC = re.compile(r"〔([^〕]+)〕\s*$")
_STAR = re.compile(r"^[★☆]\s*")

__all__ = ["read_raw", "parse", "as_text", "as_markdown", "sections", "stats",
           "plain"]


def read_raw(name: str, doc_dir: str | Path | None = None) -> str:
    """读原始 Markdown。优先 VALUES_DOC_DIR / 显式目录，其次包内数据。"""
    fname = DOC_FILES.get(name, name)
    for base in (doc_dir, os.environ.get("VALUES_DOC_DIR")):
        if not base:
            continue
        p = Path(base) / fname
        if p.is_file():
            return p.read_text(encoding="utf-8")

    blob = pkgutil.get_data("values_core", f"data/{fname}")
    if blob is None:
        raise FileNotFoundError(f"找不到 {fname}")
    return blob.decode("utf-8")


def parse(markdown: str) -> dict:
    """把 Markdown 拆成 {intro, sections:[{title, level, rules:[{text, core, src}]}]}。"""
    intro: list[str] = []
    secs: list[dict] = []
    cur: dict | None = None

    for line in markdown.splitlines():
        s = line.rstrip()
        if not s.strip():
            continue

        m = _HEAD.match(s)
        if m:
            level, title = len(m.group(1)), m.group(2).strip()
            if level == 1 and not secs and not intro:
                intro.append(title)
                continue
            cur = {"title": title, "level": level, "rules": []}
            secs.append(cur)
            continue

        b = _BULLET.match(s)
        if b and cur is not None:
            body = b.group(1).strip()
            core = bool(_STAR.match(body))
            body = _STAR.sub("", body)
            src = ""
            sm = _SRC.search(body)
            if sm:
                src = sm.group(1).strip()
                body = body[:sm.start()].strip()
            cur["rules"].append({"text": body, "core": core, "src": src})
            continue

        # 引用块与普通段落进入 intro（只在第一个标题之前）
        if not secs:
            intro.append(s.lstrip("> ").strip())

    return {"intro": intro, "sections": secs}


def sections(name: str = "doctrine", tier: str = "full",
             doc_dir: str | Path | None = None) -> list[dict]:
    """按层级返回章节。tier=core 只保留★条目所在的章节与条目。"""
    data = parse(read_raw(name, doc_dir))
    out: list[dict] = []
    for sec in data["sections"]:
        rules = sec["rules"] if tier != "core" else [r for r in sec["rules"] if r["core"]]
        if rules:
            out.append({"title": sec["title"], "level": sec["level"], "rules": rules})
    return out


def _plain(text: str) -> str:
    """去掉 Markdown 强调标记，提示词里不需要 ** 和反引号。"""
    return re.sub(r"\*\*(.+?)\*\*", r"\1", text).replace("`", "")


plain = _plain


def as_text(name: str = "doctrine", tier: str = "full",
            doc_dir: str | Path | None = None, with_src: bool = True) -> str:
    """输出纯文本，供直接塞进提示词。

    with_src=False 用于模型消费：不给裸编号，避免它把〔1546〕照抄进回答。
    """
    secs = sections(name, tier, doc_dir)
    lines: list[str] = []
    for sec in secs:
        lines.append(f"【{sec['title']}】")
        for r in sec["rules"]:
            src = f" 〔{r['src']}〕" if (with_src and r["src"]) else ""
            lines.append(f"- {_plain(r['text'])}{src}")
        lines.append("")
    return "\n".join(lines).strip()


def as_markdown(name: str = "doctrine", tier: str = "full",
                doc_dir: str | Path | None = None) -> str:
    """输出 Markdown，保留层级，便于人读。"""
    secs = sections(name, tier, doc_dir)
    lines: list[str] = []
    for sec in secs:
        lines.append(f"{'#' * sec['level']} {sec['title']}")
        lines.append("")
        for r in sec["rules"]:
            mark = "★ " if r["core"] else ""
            src = f" 〔{r['src']}〕" if r["src"] else ""
            lines.append(f"- {mark}{r['text']}{src}")
        lines.append("")
    return "\n".join(lines).strip()


def stats(name: str = "doctrine", doc_dir: str | Path | None = None) -> dict:
    data = parse(read_raw(name, doc_dir))
    total = sum(len(s["rules"]) for s in data["sections"])
    core = sum(1 for s in data["sections"] for r in s["rules"] if r["core"])
    return {"sections": len(data["sections"]), "rules": total, "core": core,
            "chars": len(as_text(name, "full", doc_dir))}
