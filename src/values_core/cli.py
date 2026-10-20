"""命令行入口。

设计目标：一条命令就能产出可粘贴的上下文，让没有 MCP 的 harness 也能用。

    values ctx "同事抢了我的功劳怎么办"
    values search "道歉" --limit 5
    values get 1546
    values route "借钱不还"
    values doctrine --tier core
    values mcp
"""
from __future__ import annotations

import argparse
import json
import pkgutil
import sys
from pathlib import Path

from . import doctrine, render
from .store import Store, StoreError

VERSION = "1.0.1"


def _force_utf8() -> None:
    """Windows 控制台默认 GBK，中文输出会炸；能改就改成 UTF-8。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")   # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


def _open(args) -> Store:
    return Store(getattr(args, "data", None))


def _print(text: str) -> None:
    sys.stdout.write(text.rstrip() + "\n")


def cmd_ctx(args) -> int:
    store = _open(args)
    text = render.build_context(
        store, args.question, limit=args.limit, tier=args.tier,
        budget=args.budget, with_style=args.with_style, path=args.path,
        doc_dir=args.doc_dir, force=args.force,
    )
    if not text:
        _print("没有取到内容，检查一下数据文件是否完整（values stats）。")
        return 0
    _print(text)
    return 0


def cmd_search(args) -> int:
    store = _open(args)
    hits = store.search(args.query, path=args.path, limit=args.limit)
    if args.json:
        _print(json.dumps([h.to_dict() for h in hits], ensure_ascii=False, indent=1))
        return 0
    if not hits:
        _print(f"没有找到与「{args.query}」相关的条目。换个说法，或用 values topics 看分类。")
        return 0
    for h in hits:
        e = h.entry
        path = e.paths[0] if e.paths else "未分类"
        title = e.title or "无标题"
        _print(f"[{e.n}] {title}　·　{path}\n    {e.summary[:160]}")
        if e.url:
            _print(f"    引用：[《{title}》]({e.url})")
    return 0


def cmd_get(args) -> int:
    store = _open(args)
    if args.json:
        e = store.get(args.n)
        if not e:
            _print(json.dumps({"error": f"没有第 {args.n} 条"}, ensure_ascii=False))
            return 1
        d = e.to_dict()
        d["neighbors"] = [x.to_dict() for x in store.neighbors(args.n, 5)]
        _print(json.dumps(d, ensure_ascii=False, indent=1))
        return 0
    _print(render.render_entry(store, args.n))
    return 0


def cmd_links(args) -> int:
    """只输出原文链接与标题，方便直接抓取全文。"""
    store = _open(args)
    hits = store.relevant(args.question, args.limit)
    if not hits:
        hits = store._rank_all(args.question, args.limit)
    if not hits:
        _print("没有找到相关条目。")
        return 0
    for h in hits:
        e = h.entry
        _print(f"{e.url}\t{e.title}")
    return 0


def cmd_route(args) -> int:
    store = _open(args)
    rows = store.route(args.question, top=args.top)
    if args.json:
        _print(json.dumps(rows, ensure_ascii=False, indent=1))
        return 0
    if not rows:
        _print("没有匹配到分类。")
        return 0
    for r in rows:
        _print(f"{r['score']:>6}  {r['path']}　（{r['entries']} 条）")
    return 0


def cmd_doctrine(args) -> int:
    if args.json:
        _print(json.dumps(doctrine.sections("doctrine", args.tier, args.doc_dir),
                          ensure_ascii=False, indent=1))
        return 0
    _print(doctrine.as_text("doctrine", args.tier, args.doc_dir,
                            with_src=not args.no_src))
    return 0


def cmd_voice(args) -> int:
    _print(doctrine.as_text("voice", "full", args.doc_dir))
    return 0


def cmd_topics(args) -> int:
    store = _open(args)
    rows = store.topics(args.l1)
    if args.json:
        _print(json.dumps(rows, ensure_ascii=False, indent=1))
        return 0
    cur = ""
    for r in rows:
        if r["l1"] != cur:
            cur = r["l1"]
            _print(f"\n【{cur}】")
        _print(f"  {r['path']}　{r['entries']}")
    return 0


def cmd_stats(args) -> int:
    store = _open(args)
    d = store.stats()
    d["doctrine"] = doctrine.stats("doctrine", args.doc_dir)
    d["voice_chars"] = len(doctrine.as_text("voice", "full", args.doc_dir))
    _print(json.dumps(d, ensure_ascii=False, indent=1))
    return 0


def cmd_sync(args) -> int:
    store = _open(args)
    info = store.sync(args.url)
    _print(f"已同步：{info['count']} 条，版本 {info['version']}\n保存到 {info['saved']}")
    return 0


def cmd_mcp(args) -> int:
    from .mcp_server import serve
    serve(getattr(args, "data", None))
    return 0


# Agent Skills 是开放标准：每个 harness 只是目录不同，SKILL.md 内容完全通用
SKILL_TARGETS = {
    "claude": "~/.claude/skills",
    "codex": "~/.codex/skills",
    "cursor": "~/.cursor/skills",
    "workbuddy": "~/.workbuddy/skills",
    "dsh": "~/.dsh/skills",
    "windsurf": "~/.windsurf/skills",
    "cline": "~/.cline/skills",
    "roo": "~/.roo/skills",
    "goose": "~/.goose/skills",
    "kiro": "~/.kiro/skills",
    "continue": "~/.continue/skills",
    "trae": "~/.trae/skills",
    "opencode": "~/.config/opencode/skills",
    "antigravity": "~/.agents/skills",
}


def _detected_targets() -> list[tuple[str, Path]]:
    out = []
    for name, raw in SKILL_TARGETS.items():
        d = Path(raw).expanduser()
        if d.parent.is_dir():
            out.append((name, d))
    return out


def _to_lf(text: str) -> str:
    """统一成 LF。

    源文件在 Windows 上常被 git 检出成 CRLF，包里带的也是 CRLF。
    后面按 \\n 做切分、再按文本模式写回时，Windows 会把每个 \\n 翻译成 \\r\\n，
    原本的 \\r\\n 就变成 \\r\\r\\n —— frontmatter 开头的 `---` 后面多了个 CR，
    YAML 解析失败，harness 会报 unknown skill。所以一律先归一到 LF。
    """
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _with_local_path(blob: bytes) -> str:
    """在 frontmatter 后插一行本机命令路径。

    values 未必在 PATH 里，模型照着抄 `values ctx` 会找不到命令；
    装的时候把真实路径写进去，就不依赖环境变量了。
    """
    text = _to_lf(blob.decode("utf-8"))
    argv0 = Path(sys.argv[0]).resolve()
    # 用当前正在跑的解释器，而不是裸 python：
    # Windows 上 python 常是 WindowsApps 存根，执行会静默失败退出码 1。
    exe = sys.executable or "python"
    if argv0.suffix == ".pyz" or argv0.is_file():
        cmd = f'"{exe}" "{argv0}"'
    else:
        cmd = f'"{exe}" -m values_core.cli'
    note = (f"\n> **本机命令**：`{cmd}`\n"
            f"> 下文出现的 `values` 都指这条命令；若它已在 PATH 里，也可以直接写 `values`。\n")
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            cut = end + 4
            return text[:cut] + "\n" + note + text[cut:]
    return note + "\n" + text


def cmd_install_skill(args) -> int:
    """把技能装到各 harness 的 skills 目录。SKILL.md 内容完全一样。"""
    blob = pkgutil.get_data("values_core", "skill/SKILL.md")
    if blob is None:
        _print("包里没有 skill/SKILL.md，请从仓库手工复制 skills/ 目录。")
        return 1

    if args.dir:
        targets = [("<dir>", Path(args.dir).expanduser())]
    elif args.target:
        names = [x.strip() for x in args.target.replace(",", " ").split() if x.strip()]
        unknown = [n for n in names if n not in SKILL_TARGETS]
        if unknown:
            _print(f"不认识的 target：{', '.join(unknown)}\n可用：{', '.join(SKILL_TARGETS)}")
            return 1
        targets = [(n, Path(SKILL_TARGETS[n]).expanduser()) for n in names]
    else:
        targets = _detected_targets()
        if not targets:
            _print("没检测到已安装的 agent。用 --target 指定：")
            for n, raw in SKILL_TARGETS.items():
                _print(f"  {n:<12}{raw}")
            _print("或 --dir 指定任意目录。")
            return 1

    ok = 0
    for name, base in targets:
        dst = base / "values-grounding"
        if dst.exists() and not args.force:
            _print(f"跳过 {name}：{dst} 已存在（加 --force 覆盖）")
            continue
        dst.mkdir(parents=True, exist_ok=True)
        # 写字节而不是文本：文本模式在 Windows 上会把 \\n 翻译成 \\r\\n
        (dst / "SKILL.md").write_bytes(_with_local_path(blob).encode("utf-8"))
        _print(f"已安装 {name:<12}{dst}")
        ok += 1
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="values",
        description="核心价值观检索与上下文注入。",
    )
    p.add_argument("--data", help="指定 values-core.json.gz 路径")
    p.add_argument("--doc-dir", dest="doc_dir", help="指定 doctrine.md / voice.md 所在目录")
    p.add_argument("--version", action="version", version=f"sooon-values {VERSION}")
    sub = p.add_subparsers(dest="cmd")

    c = sub.add_parser("ctx", help="产出可粘贴的上下文块")
    c.add_argument("question")
    c.add_argument("--limit", type=int, default=6, help="带几条原文，默认 6")
    c.add_argument("--tier", choices=["core", "full"], default="core")
    c.add_argument("--budget", type=int, default=6000, help="总字数上限，默认 6000")
    c.add_argument("--with-style", action="store_true", help="附上文风规则")
    c.add_argument("--path", help="限定三级路径")
    c.add_argument("--force", action="store_true",
                   help="不按分类裁剪，输出全部准则（默认只给相关章节）")
    c.set_defaults(func=cmd_ctx)

    s = sub.add_parser("search", help="按关键词搜条目")
    s.add_argument("query")
    s.add_argument("--limit", type=int, default=8)
    s.add_argument("--path")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_search)

    g = sub.add_parser("get", help="取单条全文")
    g.add_argument("n", type=int)
    g.add_argument("--json", action="store_true")
    g.set_defaults(func=cmd_get)

    lk = sub.add_parser("links", help="只输出原文链接（可配合抓取全文）")
    lk.add_argument("question")
    lk.add_argument("--limit", type=int, default=6)
    lk.set_defaults(func=cmd_links)

    r = sub.add_parser("route", help="把问题映射到三级分类")
    r.add_argument("question")
    r.add_argument("--top", type=int, default=5)
    r.add_argument("--json", action="store_true")
    r.set_defaults(func=cmd_route)

    d = sub.add_parser("doctrine", help="输出判断准则")
    d.add_argument("--tier", choices=["core", "full"], default="full")
    d.add_argument("--no-src", action="store_true",
                   help="不带来源编号（贴进聊天窗口用这个，编号对读者没意义）")
    d.add_argument("--json", action="store_true")
    d.set_defaults(func=cmd_doctrine)

    v = sub.add_parser("voice", help="输出文风规则")
    v.set_defaults(func=cmd_voice)

    t = sub.add_parser("topics", help="列出三级分类")
    t.add_argument("--l1", help="只看某个一级分类")
    t.add_argument("--json", action="store_true")
    t.set_defaults(func=cmd_topics)

    st = sub.add_parser("stats", help="数据概况")
    st.set_defaults(func=cmd_stats)

    sy = sub.add_parser("sync", help="从远端同步最新数据")
    sy.add_argument("--url", required=True)
    sy.set_defaults(func=cmd_sync)

    m = sub.add_parser("mcp", help="以 MCP 服务运行（stdio）")
    m.set_defaults(func=cmd_mcp)

    i = sub.add_parser("install-skill", help="安装技能到各 agent 的 skills 目录")
    i.add_argument("--target", help="逗号分隔：claude,codex,cursor,workbuddy,…；不填则自动检测")
    i.add_argument("--dir", help="装到指定目录（含 values-grounding 子目录）")
    i.add_argument("--force", action="store_true", help="覆盖已存在的技能")
    i.set_defaults(func=cmd_install_skill)

    return p


def main(argv: list[str] | None = None) -> int:
    _force_utf8()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "cmd", None):
        parser.print_help()
        return 0
    try:
        return args.func(args)
    except StoreError as e:
        sys.stderr.write(f"错误：{e}\n")
        return 2
    except BrokenPipeError:
        return 0
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
