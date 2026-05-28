"""强制任务路由器 20 项验收测试"""
import json
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("task_router", Path(__file__).resolve().parent.parent.parent / "task-router" / "task_router.py")
task_router = importlib.util.module_from_spec(spec)
spec.loader.exec_module(task_router)

TEST_CASES = [
    pytest.param(1, "帮我分析茅台最近走势并给出操作建议", ["stock-analysis"], ["stock-analysis"], True, id="1-stock-analysis"),
    pytest.param(2, "审查上周所有Agent调用日志，找出违规", ["weekly-audit-executor"], ["weekly-audit"], True, id="2-weekly-audit"),
    pytest.param(3, "Python里怎么把列表转成字符串？", [], [], False, id="3-python-generic"),
    pytest.param(4, "把 last_error.txt 里的错误分析一下，给出修复", ["errorlog"], ["errorlog"], True, id="4-errorlog"),
    pytest.param(5, "部署最新版到生产环境", ["dept-engineering"], ["dept-engineering"], True, id="5-deploy"),
    pytest.param(6, "今天读书内容整理成笔记发飞书", ["dept-reading", "dept-front-office"], ["knowledge-chinese-civ", "dept-front-office"], True, id="6-reading-feishu"),
    pytest.param(7, "跑一下回测验证脚本是不是正常", ["test-engineer"], ["test-engineer"], True, id="7-test-script"),
    pytest.param(8, "压缩今天的会话摘要", ["daily-compress"], ["daily-compress"], True, id="8-daily-compress"),
    pytest.param(9, "量子力学的基本概念是什么", ["dept-reading"], ["knowledge-physics"], True, id="9-physics"),
    pytest.param(10, "这张图里有什么文字？", ["user-image-vision"], ["user-image-vision"], True, id="10-image-vision"),
    pytest.param(11, "随便聊聊，今天天气不错", [], [], False, id="11-chitchat"),
    pytest.param(12, "把上周所有交易记录导出来", [], [], False, id="12-export-trades"),
    pytest.param(13, "重启生产服务器", ["dept-engineering"], ["dept-engineering"], True, id="13-restart-server"),
    pytest.param(14, "把这段代码审查一下，有安全漏洞", ["code-review"], ["code-review"], True, id="14-code-review"),
    pytest.param(15, "早晨的简报生成了吗", ["morning-brief"], ["morning-brief"], True, id="15-morning-brief"),
    pytest.param(16, "学习这个视频课程并做笔记", ["user-video-learn"], ["user-video-learn"], True, id="16-video-learn"),
    pytest.param(17, "帮我看看这个Agent怎么不工作了", ["gan-evaluator"], ["gan-evaluator"], True, id="17-agent-broken"),
    pytest.param(18, "解释一下宗教的起源", ["dept-reading"], ["knowledge-religion"], True, id="18-religion"),
    pytest.param(19, "把所有文件的权限改成777", [], [], False, id="19-chmod-harmless"),
    pytest.param(20, "把这句中文翻译成英文", [], [], False, id="20-translate"),
]


class TestTaskRouter:
    @pytest.mark.parametrize("case_id, description, expected_agents, expected_skills, should_be_routed", TEST_CASES)
    def test_route(self, case_id, description, expected_agents, expected_skills, should_be_routed):
        data = task_router.match_task(description)
        assert sorted(data["agents"]) == sorted(expected_agents), (
            f"#{case_id} agents mismatch: got {data['agents']}, expected {expected_agents}"
        )
        assert sorted(data["skills"]) == sorted(expected_skills), (
            f"#{case_id} skills mismatch: got {data['skills']}, expected {expected_skills}"
        )
        if should_be_routed:
            assert data["status"] == "routed", f"#{case_id} should be routed but got {data['status']}"
        else:
            assert data["status"] in ("allow_direct", "blocked"), (
                f"#{case_id} should NOT be routed but got {data['status']}"
            )
