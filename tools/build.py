"""打包：把数据、准则、技能收进包，产出单文件 values.pyz 与插件目录。

用法：
    python tools/build.py
    python tools/build.py --no-zipapp     # 只同步数据与技能
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import zipapp
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
PKG = SRC / "values_core"
DATA = ROOT / "data"
DIST = ROOT / "dist"


def sync_data() -> None:
    dst = PKG / "data"
    dst.mkdir(parents=True, exist_ok=True)
    for name in ("values-core.json.gz", "doctrine.md", "voice.md"):
        src = DATA / name
        if not src.is_file():
            raise SystemExit(f"缺少 {src}")
        shutil.copy2(src, dst / name)
        print(f"  数据 {name}  {src.stat().st_size / 1024:.0f} KB")


def sync_plugin() -> None:
    src = ROOT / "skills" / "values-grounding" / "SKILL.md"
    (PKG / "skill").mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, PKG / "skill" / "SKILL.md")
    dst = ROOT / "plugin" / "skills" / "values-grounding"
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst / "SKILL.md")
    print(f"  插件技能 {dst.relative_to(ROOT)}")


def build_zipapp() -> Path:
    DIST.mkdir(parents=True, exist_ok=True)
    out = DIST / "values.pyz"
    if out.exists():
        out.unlink()
    zipapp.create_archive(
        SRC, target=out,
        interpreter="/usr/bin/env python3",
        main="values_core.cli:main",
        compressed=True,
    )
    print(f"  values.pyz  {out.stat().st_size / 1024:.0f} KB")
    return out


def smoke(pyz: Path) -> None:
    """打包后跑一次真实检索，确认数据进得去、出得来。"""
    r = subprocess.run(
        [sys.executable, str(pyz), "stats"],
        capture_output=True, text=True, encoding="utf-8",
    )
    if r.returncode != 0:
        raise SystemExit(f"打包后无法运行：{r.stderr[:400]}")
    if '"count": 3831' not in r.stdout:
        raise SystemExit(f"条目数不对：{r.stdout[:300]}")
    print("  自检通过：3831 条")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-zipapp", action="store_true")
    args = ap.parse_args()

    print("同步数据…")
    sync_data()
    print("同步插件…")
    sync_plugin()

    if not args.no_zipapp:
        print("打包…")
        pyz = build_zipapp()
        smoke(pyz)

    print("完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
