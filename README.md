# Sooon Values｜素问价值观

把一套固定的价值观做成**任何 AI 都能调用**的判断依据。

3831 篇文章 → 93 条判断准则 + 全文检索 + 原文链接。装上之后，AI 遇到需要立场的问题
不再泛泛而谈，而是先按这套准则判断，再回答。

单文件、零依赖、离线可用。

---

## 它解决什么

普通 AI 面对「同事抢了我的功劳怎么办」，会给你三段「建议沟通」「保持专业」「视情况而定」。

这套东西不这么答。它会先判断：抢功的定义是"被追问主力却不提你"，而不是"领导没夸你"；
组织看功劳先看谁担保，其次才看谁干活；年轻人不妨主动用出让功劳换参与更高项目的机会。

差别不在文采，在于**有没有一套前后一致的判断标准**。这个仓库就是把那套标准做成可调用的接口。

---

## 判断交给模型，工具只给内容

工具里**没有关键词表，也不判断该不该用**。判断由调用它的模型做——它读得懂
「我带的实习生捅了篓子」是在求判断，而关键词表读不懂（实测留出集上词表召回只有 60%）。

技能里写清了什么该用、什么不该用：

| 该用 | 不该用 |
|---|---|
| 我该怎么办 / 这样对不对 / 他过分吗 | 查事实、查数据、查定义 |
| 只描述处境没提问的 | 写代码、报错排查、配置部署 |
| 你怎么看 X / 你怎么理解 X | 翻译、润色、总结、格式转换 |
| 情绪、纠结、拿不定主意 | 推荐内容、预测涨跌 |

一句话：**对方要的是「怎么想」还是「怎么做」**。误用只是多读一两千字，该用没用等于白装。

调用之后：

```bash
values ctx "用户的原话"          # 约 3 千字：相关章节 + 原文摘要 + 链接
values ctx "…" --budget 2500     # 压到 2500 字以内
values ctx "…" --force           # 不按分类裁剪，输出全部准则
values links "用户的原话"        # 只要原文链接，方便抓全文
```

### 摘要不够就读原文

每条原文都带链接。要点：

- 上下文里写明「摘要只有一两百字，需要例子、数字、论证时可以打开链接读全文，以原文为准」。
- `values links` 只吐 URL，方便模型一次拿几条去抓。
- 抓不到（知乎/素问可能挡爬虫或要登录）就用摘要，明确说没读到，不许编造原文内容。

---

## 三种接入方式

| 你的环境 | 用哪个 | 效果 |
|---|---|---|
| Claude Desktop、Cursor、WorkBuddy、Cherry Studio 等支持 MCP | **MCP** | AI 自己发现工具，按需检索 |
| Codex CLI、Claude Code、DSH、Cline、Aider 等有终端 | **CLI** | 一条命令拿到可粘贴的上下文 |
| WorkBuddy / Claude 支持技能 | **Skill** | 自动判断何时用、怎么引、不许编链接 |
| ChatGPT 网页、豆包、Kimi、Gemini | **粘贴** | 准则放进项目知识库，或单题粘贴 |

三个可以叠着用。MCP 管"能查"，Skill 管"会用"，CLI 是兜底。

---

## 快速开始

### 1. 拿到它

```bash
git clone https://github.com/Azi599/sooon-values.git
cd sooon-values
python dist/values.pyz stats
```

仓库里自带打包好的 `dist/values.pyz`，不用安装依赖。改了代码或准则后重新打包：

```bash
python tools/build.py
```

应该输出 3831 条、143 条路径。没有 Python 就先装一个（3.9 以上）。

### 2. 试一下

```bash
python values.pyz probe "同事把我的功劳抢走了，我该怎么办"   # 先看值不值得
python values.pyz ctx   "同事把我的功劳抢走了，我该怎么办"   # 取内容
```

输出三段：判断准则、本题相关原文、使用约束。整段粘进任何 AI 都行。

### 3. 接入

**MCP**：把 `integrations/mcp.example.json` 里的路径改成你机器上的实际路径，
合并进 MCP 客户端的配置文件。WorkBuddy 是 `~/.workbuddy/mcp.json`。

```json
{
  "mcpServers": {
    "values": {
      "command": "python",
      "args": ["D:/tools/values/values.pyz", "mcp"]
    }
  }
}
```

**CLI**：把 `values.pyz` 放到任意目录，按 `integrations/agent-instructions.md` 里的说明
往 `AGENTS.md` / `CLAUDE.md` 加一段。

**Skill**（Agent Skills 开放标准，一份 SKILL.md 通用）：

```bash
python values.pyz install-skill                  # 自动检测已装的 agent
python values.pyz install-skill --target dsh,claude,codex
python values.pyz install-skill --dir ./skills   # 装到项目目录
```

安装位置：

| agent | 目录 |
|---|---|
| Claude Code | `~/.claude/skills/` |
| Codex CLI | `~/.codex/skills/` |
| Cursor | `~/.cursor/skills/` |
| DSH | `~/.dsh/skills/` |
| WorkBuddy | `~/.workbuddy/skills/` |
| Copilot | `.github/skills/` |
| Windsurf / Cline / Roo / Goose / Kiro / Continue / Trae | 各自 `.<name>/skills/` |
| Antigravity | `.agents/skills/` |
| OpenCode | `~/.config/opencode/skills/` |

装的时候会把真实的 `values` 命令路径写进 SKILL.md，所以模型不用配 PATH。

**纯聊天**：看 `integrations/plain-chat.md`。

---

## 命令

```
values ctx "<问题>"            产出可粘贴的上下文块
values links "<问题>"          只输出原文链接（配合抓全文）
       --limit 6               带几条原文
       --tier core|full        准则层级，core 约 5 千字，full 约 1.1 万字
       --budget 6000           总字数上限
       --with-style            附上文风规则
       --force                 不按分类裁剪，输出全部准则
       --path "与友人 / 与恋人 / 相处"   限定分类

values search "<关键词>"       按关键词检索
       --path --limit --json

values get 1546                取单条全文 + 原文链接 + 相邻条目

values route "<问题>"          把问题映射到三级分类

values doctrine --tier core    输出判断准则
values voice                   输出文风规则
values topics --l1 与自己      列出三级分类
values stats                   数据概况

values mcp                     以 MCP 服务运行（stdio）
values sync --url <URL>        从远端同步最新数据
values install-skill           安装自带技能
```

`values` 是 `python values.pyz` 的简写。想直接敲 `values`，把 `values.pyz` 改名为
`values` 并加可执行权限（Windows 上建一个 `values.cmd`）。

---

## MCP 工具

| 工具 | 用途 |
|---|---|
| `values_context` | 一次拿到准则 + 相关原文 + 约束，已按预算裁剪 |
| `values_search` | 按关键词或分类检索条目 |
| `values_get` | 取单条全文与链接 |
| `values_route` | 把问题映射到 143 条三级路径 |
| `values_doctrine` | 取判断准则，可按层级或章节过滤 |
| `values_style` | 取文风规则 |

另有两个资源 `values://doctrine`、`values://style`，一个提示词模板
`values_grounded_answer`。

---

## 数据

| | |
|---|---|
| 条目 | 3831 条，编号 1–3839（中间有 1704 个空号，是确认同篇转载留下的） |
| 分类 | 7 个一级、143 条三级路径，一篇可属多条 |
| 链接 | 3752 条指向素问原文，79 条旧条目指向知乎原文 |
| 判断准则 | 93 条，分 12 节，41 条标为核心 |
| 体积 | 数据 993KB（gzip），打包后 1.0MB |

### 准则与原文的关系

`data/doctrine.md` 是**归纳稿**，不是原文。每条末尾的 〔N〕 是来源条目编号，
可以用 `values get N` 核对。凡与原文冲突，以原文为准。

这样设计是为了让 AI"学会"而不是"查字典"：准则给出判断，原文提供依据和可追溯性。

---

## 来源与版权

- 文章摘要整理自知乎收藏夹「q9adg」与 sooon.ai 的公开文章，**版权归原作者**。
- 本仓库只做检索、归纳与引用，不替代原文；每个条目都保留指向原文的链接。
- 公开分发时请保留链接与出处说明；如果要批量输出全文，请先取得授权。
- 代码部分 MIT。

---

## 目录

```
values.pyz                    单文件可执行（推荐分发这个）
data/
  values-core.json.gz         3831 条结构化数据
  doctrine.md                 判断准则（人读、可改）
  voice.md                    文风规则
  topics.txt                  143 条三级路径清单
src/values_core/
  store.py                    数据加载与检索
  doctrine.py                 准则解析与分层
  render.py                   上下文组装
  cli.py                      命令行
  mcp_server.py               MCP 服务
  skill/SKILL.md              技能说明
skills/values-grounding/      Agent Skills 技能（跨 harness 通用）
plugin/                       WorkBuddy 插件包
integrations/                 各客户端的接入配置
data/eval/                    评测标注集（labeled / heldout）
tools/build_data.py           从原始交付重建数据
tools/build.py                打包 values.pyz 与插件
```

---

## 改准则

直接改 `data/doctrine.md`：

- 每条一行，`- ` 开头
- 行首 `★` 表示核心条目（`--tier core` 只输出这些）
- 末尾 `〔12, 34〕` 是来源编号，可省略
- `##` / `###` 开头的行是章节标题

改完运行 `python tools/build.py` 重新打包。不想重打包就把文件放别处，
用 `--doc-dir` 或环境变量 `VALUES_DOC_DIR` 指过去。

数据同理：`VALUES_DATA` 指新的 json.gz，或 `values sync --url` 从远端拉。

---

## 评测

```bash
python tools/eval.py --out dist/eval-report.md    # 全离线，不调模型，约 10 秒
```

| 项目 | 结果 |
|---|---|
| 注入规模 | 平均 3500 字（1660–3860），174 条标注问题 |
| 检索 801 条（标题当查询） | Recall@1 97.5%，Recall@5 100%，MRR 0.986 |
| 分类命中 | 88.6%（调参集 79 条）/ 76.7%（留出集 30 条）/ 82.5%（标题查询 291 条） |
| 数据完整性 | 3831 条；93 条准则引用的 85 个编号全部有效 |
| 稳健性 | 空串、超长、emoji、中英混合、注入串均不报错；重复调用结果一致 |

如实说明：

1. **标题当查询太容易**。标题几乎就是原文片段，97.5% 的 Recall@1 只证明索引没坏，
   不证明语义检索能力。要测语义得用改写过的问句和标注，目前没有。
2. **词表那版已被删掉**。之前用它做判断，调参集 100%、留出集 76%，漏的全是陈述式求助；
   现在不再做判断，也就不存在这个指标。
3. **分类命中 77–89%**。判偏不会答错，但注入的章节主题会偏，这是当前最大的质量短板。
   已用「前两支一级都加载」把命中从 56.7% 拉到 76.7%，代价是每次多几百字。

## 常见问题

**问：它会不会把我的问题发到网上？**
不会。检索完全在本地，MCP 和 CLI 都不联网。只有 `values sync` 会访问你指定的 URL。

**问：为什么 93 条准则，不是把 3831 条都塞进去？**
66 万字塞不进任何上下文，塞进去也会被稀释。准则给判断，原文按需检索——
这是让它"学会"而不是"查字典"的唯一做法。

**问：回答里会出现 `[1546]` 这种编号吗？**
不会。给用户的回答里只出现链接，形如
`（[《刚烈者》](https://sooon.ai/p/s/xxxxx)）`。编号只在内部用于 `values get N` 核对，
`ctx` 和 `doctrine` 返回给模型的内容都不带裸编号——否则模型会照抄，读者看不懂那是什么。

**问：链接能信吗？**
能。链接是工具从数据里直接给出的，不是模型拼的。`values get N` 能看到同一条的全文。

**问：能用在英文 AI 上吗？**
能。准则和数据是中文的，但工具返回的是文本，任何模型都能读。英文提问会在检索时损失一些匹配度，
可以先用中文关键词搜。

**问：`values` 和 qatool 是什么关系？**
同源。qatool 是解析题目时按需注入价值观，Sooon Values 是把同一套数据做成通用接口。
