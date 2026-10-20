"""Sooon Values 的数据与检索核心。

只用标准库，方便在任意 harness 里直接跑，不要求 pip install。

数据文件 values-core.json.gz 结构：
    {
      "version": "...",
      "count": 3831,
      "tree":  {"一级": {"二级": {"三级": [条目号, ...]}}},
      "entries": {"1": {"t": 标题, "s": 摘要, "u": 链接, "p": ["一级 / 二级 / 三级"]}}
    }
"""
from __future__ import annotations

import gzip
import io
import json
import math
import os
import pkgutil
import re
import tempfile
import time
import urllib.request
from pathlib import Path

__all__ = ["Store", "Entry", "SearchHit", "StoreError", "DATA_NAME"]

DATA_NAME = "values-core.json.gz"

# 中文按二元组切分；英文与数字按词
_TOKEN = re.compile(r"[a-zA-Z0-9]+|[\u4e00-\u9fff]+")

# 提问时的套话，会把检索带偏（「我该怎么办」本身没有语义，却会命中讲这个短语的条目）
_NOISE = (
    "我该怎么办", "该怎么办", "我该怎么做", "该怎么做", "我该", "该怎么办呢",
    "怎么处理", "怎么办才好", "怎么办", "如何是好", "怎么看待", "怎么看",
    "我是不是", "是不是", "对不对", "好不好", "可以吗", "请问", "帮我",
)

# 这些高频二元组对区分话题没有帮助，检索时剔除
# 后半段是跨词边界的垃圾二元组（「把我的」切出「把我」）和代词短语
_STOP = {
    "什么", "怎么", "如何", "为什", "么办", "是否", "可以", "应该", "一个", "这个",
    "那个", "我们", "你们", "他们", "自己", "没有", "就是", "不是", "这样", "那样",
    "因为", "所以", "但是", "如果", "已经", "还是", "或者", "而且", "时候", "问题",
    "觉得", "感觉", "知道", "认为", "现在", "可能", "需要", "希望", "真的", "一样",
    "我的", "你的", "他的", "她的", "把我", "给我", "给你", "对他", "对我",
    "走了", "来了", "说了", "做了", "的事", "回事", "这种", "那种",
    "一直", "有点", "一些", "有些", "其实", "然后", "之前", "之后",
}


class StoreError(RuntimeError):
    """数据文件缺失、损坏或远端不可用。"""


def user_data_dir() -> Path:
    """同步下来的数据存放目录，可用 VALUES_HOME 覆盖。"""
    home = os.environ.get("VALUES_HOME")
    base = Path(home) if home else Path.home() / ".values-core"
    return base


def clean_query(text: str) -> str:
    """去掉提问套话，保留有信息量的部分。"""
    s = str(text or "")
    for p in _NOISE:
        s = s.replace(p, " ")
    return s.strip() or str(text or "").strip()


def match_tokens(text: str) -> list[str]:
    """用于相关性比较的词：去掉停用词，避免「就是」「是不」这类虚词拉高分。"""
    return [t for t in tokenize(text) if t not in _STOP]


def tokenize(text: str) -> list[str]:
    """中文切二元组，英文数字按词。"""
    toks: list[str] = []
    for m in _TOKEN.finditer(str(text or "").lower()):
        s = m.group(0)
        if s[0].isascii():
            toks.append(s)
        elif len(s) == 1:
            toks.append(s)
        else:
            toks.extend(s[i:i + 2] for i in range(len(s) - 1))
    return toks


class Entry:
    __slots__ = ("n", "title", "summary", "url", "paths")

    def __init__(self, n: int, raw: dict):
        self.n = n
        self.title = str(raw.get("t") or "")
        self.summary = str(raw.get("s") or "")
        self.url = str(raw.get("u") or "")
        self.paths = [str(p) for p in (raw.get("p") or [])]

    def to_dict(self) -> dict:
        return {"n": self.n, "title": self.title, "summary": self.summary,
                "url": self.url, "paths": self.paths}

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Entry {self.n} {self.title!r}>"


class SearchHit:
    __slots__ = ("entry", "score")

    def __init__(self, entry: Entry, score: float):
        self.entry = entry
        self.score = score

    def to_dict(self) -> dict:
        d = self.entry.to_dict()
        d["score"] = round(self.score, 3)
        return d


class Store:
    def __init__(self, data_file: str | Path | None = None):
        self.source = ""
        self._load(data_file)

    # ---------- 加载 ----------

    def _read_data(self, data_file: str | Path | None) -> bytes:
        if data_file:
            p = Path(data_file)
            if not p.is_file():
                raise StoreError(f"数据文件不存在：{p}")
            self.source = str(p)
            return p.read_bytes()

        env = os.environ.get("VALUES_DATA")
        if env:
            p = Path(env)
            if not p.is_file():
                raise StoreError(f"VALUES_DATA 指向的文件不存在：{p}")
            self.source = str(p)
            return p.read_bytes()

        synced = user_data_dir() / DATA_NAME
        if synced.is_file():
            self.source = str(synced)
            return synced.read_bytes()

        blob = pkgutil.get_data("values_core", f"data/{DATA_NAME}")
        if blob is None:
            raise StoreError(
                "找不到数据文件。已尝试：VALUES_DATA、"
                f"{synced}、包内 data/{DATA_NAME}。"
            )
        self.source = "builtin"
        return blob

    def _load(self, data_file: str | Path | None) -> None:
        blob = self._read_data(data_file)
        try:
            raw = json.loads(gzip.decompress(blob).decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
            raise StoreError(f"数据文件损坏：{self.source}（{e}）") from e

        self.version = str(raw.get("version") or "")
        self.entries: dict[int, Entry] = {
            int(n): Entry(int(n), v) for n, v in (raw.get("entries") or {}).items()
        }
        self.tree: dict = raw.get("tree") or {}
        self.count = len(self.entries)

        self.leaf_paths: dict[str, list[int]] = {}
        for l1, l2d in self.tree.items():
            for l2, l3d in l2d.items():
                for l3, ns in l3d.items():
                    self.leaf_paths[f"{l1} / {l2} / {l3}"] = list(ns)

        # 每个一级下有多少条（去重）：用来抵消大分类的体量优势
        self.l1_sizes: dict[str, int] = {}
        seen_l1: dict[str, set[int]] = {}
        for n, e in self.entries.items():
            for p in e.paths:
                seen_l1.setdefault(p.split(" / ")[0], set()).add(n)
        self.l1_sizes = {k: len(v) for k, v in seen_l1.items()}

        # 路径检索用的轻量索引：路径串 → 二元组集合
        self._path_tokens: list[tuple[str, set[str], int]] = [
            (p, set(tokenize(p)), len(ns)) for p, ns in self.leaf_paths.items()
        ]
        self._df: dict[str, int] | None = None

    # ---------- 检索 ----------

    def _doc_freq(self) -> dict[str, int]:
        """全量二元组文档频率，首次检索时构建并缓存。"""
        if self._df is None:
            df: dict[str, int] = {}
            for e in self.entries.values():
                for t in set(tokenize(e.title) * 2 + tokenize(e.summary)):
                    df[t] = df.get(t, 0) + 1
            self._df = df
        return self._df

    def match(self, question: str, *, max_branches: int = 3) -> dict:
        """三级归属判断：先定一级，再二级，再三级。

        返回 branches（按占比从高到低）和命中的条目。占比小于 20% 的一级不保留，
        这样「有一部分属于」时只带真正相关的那几支，不会把整套都拖进来。
        """
        hits = self._rank_all(question, limit=80)
        if not hits:
            return {"branches": [], "hits": []}

        l1: dict[str, float] = {}
        l2: dict[tuple[str, str], float] = {}
        l3: dict[tuple[str, str, str], float] = {}
        for h in hits:
            for p in h.entry.paths:
                parts = p.split(" / ")
                if len(parts) != 3:
                    continue
                a, b, c = parts
                l1[a] = l1.get(a, 0.0) + h.score
                l2[(a, b)] = l2.get((a, b), 0.0) + h.score
                l3[(a, b, c)] = l3.get((a, b, c), 0.0) + h.score

        # 「与自己」占 39% 的语料，不归一化会把别的一级都吸走；
        # 按条目数的平方根折扣，抵消体量优势（实测一级准确率 +2.5 个点）
        norm = {a: v / math.sqrt(max(1, self.l1_sizes.get(a, 1)))
                for a, v in l1.items()}
        total = sum(norm.values()) or 1.0

        # 前两支一级都保留：分类只决定加载哪几节准则，多带一节比带错一节划算
        ranked = sorted(norm.items(), key=lambda x: x[1], reverse=True)
        picked_l1 = [(a, v / total) for a, v in ranked if v / total >= 0.12][:2]
        if not picked_l1 and ranked:
            picked_l1 = [(ranked[0][0], ranked[0][1] / total)]

        branches: list[dict] = []
        for a, share in picked_l1:
            subs = [(k, v) for k, v in l2.items() if k[0] == a]
            subs.sort(key=lambda x: x[1], reverse=True)
            for (aa, b), sb in subs[:2]:
                leaves = [(k, v) for k, v in l3.items() if k[0] == a and k[1] == b]
                leaves.sort(key=lambda x: x[1], reverse=True)
                for (_, _, c), sc in leaves[:2]:
                    branches.append({
                        "l1": a, "l2": b, "l3": c,
                        "path": f"{a} / {b} / {c}",
                        "score": round(sc, 2),
                        "share": round(sc / total, 3),
                    })

        # 一级决定取哪些条目，二三级只用来决定加载哪几节准则。
        # 筛到三级会误杀：问「同事抢功」，最好的那条在「与管理者 / 博弈」，
        # 但它显然属于「与合作者」。
        keep_l1 = {b["l1"] for b in branches}
        picked = [h for h in hits
                  if any(p.split(" / ")[0] in keep_l1 for p in h.entry.paths)]
        if len(picked) < 8:
            seen = {h.entry.n for h in picked}
            picked += [h for h in hits if h.entry.n not in seen]

        # 不再按分数全局重排：保持一级优先的顺序，免得第二支的叶子排到第一支前面
        return {"branches": branches, "hits": picked}

    def _rank_all(self, query: str, limit: int | None = None) -> list[SearchHit]:
        hits = self._score_entries(tokenize(clean_query(query)), list(self.entries))
        return hits[:limit] if limit else hits

    def relevant(self, question: str, limit: int = 6) -> list[SearchHit]:
        """取与问题最相关的条目（已按命中一级收窄）。"""
        limit = max(1, int(limit or 6))
        m = self.match(question)
        return m["hits"][:limit]

    def route(self, query: str, top: int = 5) -> list[dict]:
        """三级归属：返回命中的路径分支，供按分类取内容时用。"""
        top = max(1, min(int(top or 5), 10))
        m = self.match(query, max_branches=top)
        return [{"path": b["path"], "score": b["score"], "share": b["share"],
                 "entries": len(self.leaf_paths.get(b["path"], []))}
                for b in m["branches"]][:top]

    def _score_entries(self, toks: list[str], pool: list[int]) -> list[SearchHit]:
        """对候选条目做 BM25，标题按三倍计权。"""
        df = self._doc_freq()
        n_docs = max(1, len(self.entries))
        weights: dict[str, float] = {}
        for t in set(toks):
            if t in _STOP:
                continue
            d = df.get(t, 0)
            if d == 0:
                continue
            weights[t] = math.log(1 + (n_docs - d + 0.5) / (d + 0.5))
        if not weights:
            return []

        k1, b = 1.2, 0.6
        avg_len = 90.0
        hits: list[SearchHit] = []
        for n in pool:
            e = self.entries.get(n)
            if not e:
                continue
            field = tokenize(e.title) * 3 + tokenize(e.summary)
            if not field:
                continue
            tf: dict[str, int] = {}
            for t in field:
                tf[t] = tf.get(t, 0) + 1
            raw = 0.0
            for t, w in weights.items():
                c = tf.get(t)
                if not c:
                    continue
                norm = c * (k1 + 1) / (c + k1 * (1 - b + b * len(field) / avg_len))
                raw += w * norm
            if raw > 0:
                hits.append(SearchHit(e, raw))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits

    def search(self, query: str, *, path: str | None = None,
               limit: int = 8) -> list[SearchHit]:
        """检索条目。给了 path 就在该分类里排序，否则全量排序。"""
        limit = max(1, min(int(limit or 8), 50))
        toks = tokenize(clean_query(query))

        if path:
            pool = self.leaf_paths.get(path)
            if pool is None:
                tail = path.split(" / ")[-1]
                pool = [n for p, ns in self.leaf_paths.items()
                        if p.split(" / ")[-1] == tail for n in ns]
            if pool:
                return self._score_entries(toks, pool)[:limit]

        return self._rank_all(query, limit)

    def get(self, n: int) -> Entry | None:
        try:
            return self.entries.get(int(n))
        except (TypeError, ValueError):
            return None

    def neighbors(self, n: int, limit: int = 5) -> list[Entry]:
        """同一路径下的相邻条目。"""
        e = self.entries.get(int(n))
        if not e:
            return []
        out: list[Entry] = []
        seen = {e.n}
        for p in e.paths:
            for x in self.leaf_paths.get(p, []):
                if x in seen:
                    continue
                seen.add(x)
                out.append(self.entries[x])
                if len(out) >= limit:
                    return out
        return out

    # ---------- 分类 ----------

    def topics(self, l1: str | None = None) -> list[dict]:
        """三级路径清单，可只取某个一级。"""
        out: list[dict] = []
        for a, l2d in self.tree.items():
            if l1 and a != l1:
                continue
            for b, l3d in l2d.items():
                for c, ns in l3d.items():
                    out.append({"l1": a, "l2": b, "l3": c,
                                "path": f"{a} / {b} / {c}", "entries": len(ns)})
        return out

    def stats(self) -> dict:
        return {
            "version": self.version,
            "count": self.count,
            "paths": len(self.leaf_paths),
            "l1": len(self.tree),
            "source": self.source,
            "with_url": sum(1 for e in self.entries.values() if e.url),
        }

    # ---------- 同步 ----------

    def sync(self, url: str, timeout: int = 30) -> dict:
        """从远端拉取最新数据文件，原子替换用户目录里的副本。

        远端只需返回 gzip 压缩的 values-core.json.gz 原始字节。
        """
        req = urllib.request.Request(url, headers={"User-Agent": "sooon-values/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                blob = resp.read()
        except OSError as e:
            raise StoreError(f"同步失败：{e}") from e

        try:
            raw = json.loads(gzip.decompress(blob).decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
            raise StoreError(f"远端返回的不是有效数据：{e}") from e
        if not raw.get("entries"):
            raise StoreError("远端数据为空，已放弃写入")

        dst = user_data_dir()
        dst.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkstemp(dir=str(dst), suffix=".tmp")[1])
        tmp.write_bytes(blob)

        target = dst / DATA_NAME
        old = target.with_suffix(".bak")
        if target.is_file():
            target.replace(old)
        tmp.replace(target)

        self._load(target)
        return {"version": self.version, "count": self.count, "saved": str(target)}
