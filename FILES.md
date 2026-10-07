# 文件地图

> 给第一次打开这个仓库的人。**先看什么 → 想看的"工作逻辑"在哪 → 其余可以不管。**
> 顶层那几份文档各自讲什么，见 `README.md` 的「先看哪一份」。

---

## 一、先看这三份（十分钟就够）

| 文件 | 讲什么 |
|---|---|
| **`README.md`** | 这是什么 · 解决什么问题 · 怎么跑起来 · 怎么接自己的 API · **5 张界面截图** |
| ⭐ **`DESIGN.md`** | **这套流程怎么运转**：四个位置 · 信息隔离矩阵 · 一轮怎么跑 · 凭证与台账 · **每一层能不能换工具** |
| **`NOTICE.md`** | 上游是谁 · **我们加了什么、不声明什么** · 许可怎么算 |

---

## 二、⭐ "工作逻辑"落在哪几行

**先说清一件事，免得对不上：**

> 这套方法里，**"谁跟谁说话、按什么顺序跑"那一层（写手 → 外包读者 → 逻辑审 → 工头）
> 是在终端里跑的**，它的说明书是 `DESIGN.md`——**不是本仓库这段代码**。
> **本仓库是那条生产线读写的那张桌子**（稿子、设定、大纲、记忆、伏笔都躺在它的文件里），
> 外加一个能就地起 AI 任务的界面。

**但下面这些，本仓库是有代码的，而且就是这套方法的骨头：**

| 方法里的说法 | 实现在哪 | 干什么 |
|---|---|---|
| **"给谁什么信息"要按角色定** | `core/prompt_builder.py` · `core/context_budget.py` | 提示词**按任务拼**；上下文**按预算裁**（优先级低的先砍，砍了就地标出来）。**"给多少设定"是由调用点决定的，没有一个全局开关** |
| **AI 的产出不能直接信** | `core/ai_protocol.py` · `core/ai_result_service.py` | 回复要过协议校验：**改稿范围异常扩大就拒写回**；结构化结果先验再落盘 |
| **一次任务一条链，别串味** | `core/ai_workflow.py` · `core/task_context.py` · `core/task_controller.py` | UI 无关的编排；**快照防过期结果写回**；前台任务的生命周期 |
| **两层保真：写到哪、记得住** | `core/memory.py` · `core/foreshadowing.py` · `core/character_cards.py` · `core/sync_state.py` | 章节摘要 · 伏笔台账 · 角色卡 · "哪几章还没同步进记忆" |
| **引擎可换，接口不变** | `core/engine.py` · `core/claude_client.py` · `core/api_client.py` | 本机 `claude` 命令 / 直连 API，**同一套接口** |
| **改稿要能解释** | `core/text_anchor.py` · `core/text_stats.py` | 锚点**只认唯一匹配**，不做模糊替换；字数口径对齐平台 |

---

## 三、其余目录（按需翻，不用通读）

| 目录 / 文件 | 干什么 |
|---|---|
| **`core/`**（41 个） | 与界面无关的逻辑。**除上表那几份，其余是项目/配置/导入导出/备份这类地基** |
| **`ui/`**（38 个） | 界面：主窗 · 左栏树 · 编辑器 · 对话栏 · 表格 · 关系图 · 框架图 · 设置 |
| **`tests/`**（47 个） | 单元测试，一个模块一份 |
| **`assets/`** | 内嵌字体与图标；`screenshots/` 是 README 里那 5 张 |
| **`licenses/`** | 第三方许可证全文 |
| **`projects/example/`** | 一个**空的示例书**——打开面板就能看见东西，不用你自己先建 |
| **`main.py`** | 入口（`--self-test` 可以只自检、不开界面） |
| **`run.bat`** | Windows 一键启动（先试 `python`、不行再试 `py`） |
| **`agentorium.spec`** · `scripts/build_windows.ps1` · `PACKAGING.md` | 打包成 exe |
| **`config.example.json`** | 配置样例（密钥栏是空的，照它建 `config.json`） |
| **`.github/workflows/`** | CI 与自动打包（**放 Gitee 上不会触发，留着无害**） |
| `.gitattributes` · `.gitignore` · `VERSION` | 行尾策略 · 忽略规则 · 版本号 |

---

## 四、想自己跑一遍

```bash
pip install -r requirements.txt     # 就一个依赖：PySide6
python main.py                      # Windows 上如果 python 没反应，用 py main.py
```

Windows 双击 `run.bat` 也行（它会自己建 venv、装依赖、启动）。

**只想确认环境对不对、不想开界面**：

```bash
python main.py --self-test          # 验资源 / 图标 / 字体 / 主窗，通过就退出 0
python -m pytest -q                 # 跑单元测试
```
