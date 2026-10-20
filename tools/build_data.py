"""把交付包编译成 values-core 的数据文件。

输入（Codex 交付目录）：
  delivery/values.txt        每条 [n] + 摘要正文
  delivery/values_urls.txt   n|url
  delivery/topic_data.json   n -> {title, paths[]}

输出：
  data/values-core.json.gz   精简结构，供 MCP / Skill / 可移植包共用
  data/topics.txt            143 条三级路径清单（人看）
"""
from __future__ import annotations

import gzip
import json
import re
import sys
from collections import Counter
from pathlib import Path

DELIVERY = Path(
    "C:/Users/lala/Documents/Codex/2026-10-17/workbuddy-2/outputs/"
    "values-increment-20261020/delivery"
)
OUT = Path(__file__).resolve().parent.parent / "data"

ENTRY_RE = re.compile(r"(?m)^\[(\d{1,6})\]\s*$")


def load_entries(text_path: Path) -> dict[int, str]:
    """按行首 [n] 切分 values.txt。"""
    raw = text_path.read_text(encoding="utf-8")
    matches = list(ENTRY_RE.finditer(raw))
    out: dict[int, str] = {}
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        body = raw[start:end].strip()
        if body:
            out[int(m.group(1))] = body
    return out


def load_urls(path: Path) -> dict[int, str]:
    out: dict[int, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "|" not in s:
            continue
        k, _, u = s.partition("|")
        try:
            out[int(k.strip())] = u.strip()
        except ValueError:
            continue
    return out


def load_titles(path: Path) -> dict[int, dict]:
    data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    out: dict[int, dict] = {}
    for k, v in (data.get("map") or {}).items():
        try:
            n = int(k)
        except (TypeError, ValueError):
            continue
        paths = []
        for seg in v.get("paths") or []:
            parts = [str(p.get("name") or "").strip() for p in seg]
            parts = [p for p in parts if p]
            if len(parts) == 3:
                paths.append(" / ".join(parts))
        out[n] = {"title": str(v.get("title") or "").strip(), "paths": sorted(set(paths))}
    return out


def build_tree(entries: dict[str, dict]) -> dict:
    tree: dict[str, dict[str, dict[str, list[int]]]] = {}
    for key, e in entries.items():
        n = int(key)
        for path in e["p"]:
            parts = [p.strip() for p in path.split(" / ")]
            if len(parts) != 3:
                continue
            l1, l2, l3 = parts
            tree.setdefault(l1, {}).setdefault(l2, {}).setdefault(l3, []).append(n)
    return {
        l1: {l2: {l3: sorted(set(ns)) for l3, ns in l2d.items()} for l2, l2d in l1d.items()}
        for l1, l1d in sorted(tree.items())
    }


def main() -> int:
    values_txt = DELIVERY / "values.txt"
    urls_txt = DELIVERY / "values_urls.txt"
    topic_json = DELIVERY / "topic_data.json"
    for p in (values_txt, urls_txt, topic_json):
        if not p.exists():
            print(f"缺少输入文件：{p}", file=sys.stderr)
            return 1

    bodies = load_entries(values_txt)
    urls = load_urls(urls_txt)
    meta = load_titles(topic_json)

    entries: dict[str, dict] = {}
    for n in sorted(bodies):
        m = meta.get(n) or {}
        entries[str(n)] = {
            "t": m.get("title") or "",
            "s": bodies[n],
            "u": urls.get(n, ""),
            "p": m.get("paths") or [],
        }

    tree = build_tree(entries)
    no_path = [int(n) for n, e in entries.items() if not e["p"]]
    no_url = [int(n) for n, e in entries.items() if not e["u"]]

    payload = {
        "version": json.loads(topic_json.read_text(encoding="utf-8", errors="replace"))
        .get("meta", {})
        .get("generated_at", "2026-10-20"),
        "count": len(entries),
        "tree": tree,
        "entries": entries,
        "stats": {
            "no_path": len(no_path),
            "no_url": len(no_url),
            "zhihu": sum(1 for e in entries.values() if "zhihu.com" in e["u"]),
            "sooon": sum(1 for e in entries.values() if "sooon.ai" in e["u"]),
            "chars": sum(len(e["s"]) for e in entries.values()),
        },
    }

    OUT.mkdir(parents=True, exist_ok=True)
    dst = OUT / "values-core.json.gz"
    with gzip.open(dst, "wt", encoding="utf-8", compresslevel=9) as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))

    lines = []
    for l1, l2d in tree.items():
        for l2, l3d in l2d.items():
            for l3, ns in l3d.items():
                lines.append(f"{l1} / {l2} / {l3}\t{len(ns)}")
    (OUT / "topics.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"条目 {len(entries)}　路径 {len(lines)}　无分类 {len(no_path)}　无链接 {len(no_url)}")
    print(f"知乎 {payload['stats']['zhihu']}　素问 {payload['stats']['sooon']}")
    print(f"正文字数 {payload['stats']['chars']}")
    print(f"输出 {dst} {dst.stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
