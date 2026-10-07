"""Theme palettes shared by configuration validation and the Qt renderer.

调色思路（2026-10-03 第二版）：

上一版走的是「暖米纸 + 赭石点缀」——那正好是当下 AI 生成界面最典型的默认套路
（warm cream ≈ #F4F1EA + terracotta ≈ #D97757）。等于从一个默认换到了另一个默认。

这一版的立场：**纸面是主角，界面往后撤。**

- 底色用**中性纸白**，不是暖米色——偏一点灰绿，像稿纸，不像奶油。
- **朱红只承载意义**：批注、未保存、破坏性动作。它不做品牌色，不往每个按钮上抹。
- 正文交给字体去立（思源宋体 + 宽行距），chrome 尽量轻。

深色版同理：真墨黑（略带暖），不是蓝黑，也不是纯黑。
"""

LIGHT_COLORS = {
    # 三层，造出「桌 → 面板 → 纸」的层次。
    # 原来三层都是同一个白，所以整块看着平、也分不出主次。
    "background_color": "#E9E8E3",   # 桌：最暗的一层，托住一切
    "panel_color": "#F7F6F3",        # 面板：侧栏、卡片
    "field_color": "#FFFFFF",        # 纸：正文和输入区，最亮
    "border_color": "#DCDAD3",
    "text_color": "#1F1E1C",         # 墨
    "muted_text_color": "#78766F",
    "accent_color": "#B23A2E",       # 朱：只给「批」与关键动作，不做装饰
    "selection_color": "#E4E2DA",
    "hover_color": "#EFEEEA",
}

DARK_COLORS = {
    "background_color": "#161514",   # 墨黑，略带暖，不是蓝黑也不是纯黑
    "panel_color": "#1E1D1B",
    "field_color": "#1A1917",
    "border_color": "#35332F",
    "text_color": "#E7E5E0",
    "muted_text_color": "#918D86",
    "accent_color": "#D4574A",       # 朱（深色下提亮）
    "selection_color": "#3A2A26",
    "hover_color": "#26241F",
}

# 字体：本机已装思源系列，别再退回微软雅黑。
UI_FONT = '"Noto Sans SC", "思源黑体", "Microsoft YaHei UI", sans-serif'
PROSE_FONT = '"Noto Serif SC", "思源宋体", "Songti SC", "SimSun", serif'
