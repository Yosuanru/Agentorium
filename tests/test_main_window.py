import unittest
from pathlib import Path

from ui.main_window import MainWindow, fallback_chapter_after_delete
from ui.navigation import PrimaryNavigation


class MainWindowDeleteBehaviorTests(unittest.TestCase):
    def test_non_current_delete_does_not_choose_a_fallback(self) -> None:
        chapters = [Path("chapter_01.md"), Path("chapter_02.md"), Path("chapter_03.md")]

        self.assertIsNone(fallback_chapter_after_delete(chapters, 1, False))

    def test_current_delete_chooses_next_then_previous(self) -> None:
        chapters = [Path("chapter_01.md"), Path("chapter_02.md"), Path("chapter_03.md")]

        self.assertEqual(
            fallback_chapter_after_delete(chapters, 1, True),
            Path("chapter_03.md"),
        )
        self.assertEqual(
            fallback_chapter_after_delete(chapters, 2, True),
            Path("chapter_02.md"),
        )
        self.assertIsNone(fallback_chapter_after_delete([chapters[0]], 0, True))

    def test_delete_shortcut_does_not_overlap_editor_word_delete(self) -> None:
        self.assertEqual(MainWindow.DELETE_CHAPTER_SHORTCUT, "Ctrl+Shift+Delete")

    def test_trash_is_a_navigation_action_not_a_workspace_route(self) -> None:
        self.assertTrue(hasattr(PrimaryNavigation, "trash_requested"))
        self.assertNotIn("trash", {route for route, _icon, _label in PrimaryNavigation.ROUTES})


class MainWindowWiringTests(unittest.TestCase):
    """**接线本身**也要有人看着——写错一个方法名，功能整个用不了，而且不报错。"""

    def test_the_money_spending_entries_point_at_methods_that_exist(self) -> None:
        """「花钱的动作」那几个入口，确认之后必须调到一个**真的存在**的方法。

        踩过：`check_consistency()` 里写的是 `ai_workflow_controller.check_consistency`，
        可控制器上那个方法叫 `check` —— 作者点「确认写入」那一下会 AttributeError，
        **「检查设定」整个用不了**。一直没人发现，是因为 AI 功能没人实测过。

        ⚠️ 这里是**静态读源码**，不起窗口——起窗口的测试在这套里会互相打架。
        """
        import ast
        import inspect

        from ui.ai_workflow_controller import AIWorkflowController

        source = Path(inspect.getsourcefile(MainWindow)).read_text(encoding="utf-8")
        available = {name for name in dir(AIWorkflowController) if not name.startswith("_")}

        referenced: set[str] = set()
        for node in ast.walk(ast.parse(source)):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Attribute)
                and node.value.attr == "ai_workflow_controller"
            ):
                referenced.add(node.attr)

        missing = sorted(referenced - available)
        self.assertEqual(
            missing, [],
            "MainWindow 调了 AIWorkflowController 上不存在的方法：%s" % missing,
        )


if __name__ == "__main__":
    unittest.main()
