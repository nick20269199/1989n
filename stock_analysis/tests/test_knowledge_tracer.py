"""上游追溯模块测试 — knowledge_tracer.py

覆盖: extract_references (核心提取) / score_reference / scan_archives / record_trace_findings
边界: 空文本 / 特殊格式 / 中英文混排 / 文件损坏
"""
import json
from pathlib import Path

import pytest

# ── extract_references 测试 ────────────────────────────────


def test_extract_arxiv():
    from knowledge_tracer import extract_references
    text = "Check out this paper arXiv:2310.12345 for more details"
    refs = extract_references(text)
    arxiv = [r for r in refs if r["ref_type"] == "paper_arxiv"]
    assert len(arxiv) == 1
    assert arxiv[0]["ref_name"] == "arXiv:2310.12345"
    assert "arxiv.org/abs/2310.12345" in arxiv[0]["ref_url"]


def test_extract_github_standard():
    from knowledge_tracer import extract_references
    text = "Source code at github.com/anthropics/claude-code"
    refs = extract_references(text)
    gh = [r for r in refs if r["ref_type"] == "github"]
    assert len(gh) >= 1
    assert "anthropics/claude-code" in gh[0]["ref_name"]


def test_extract_github_chinese_style():
    """中文风格 github🔍owner/repo 模式"""
    from knowledge_tracer import extract_references
    text = "SKILL在github🔍 XBuilderLAB/cheat-on-content #个人ip"
    refs = extract_references(text)
    gh = [r for r in refs if r["ref_type"] == "github"]
    assert len(gh) >= 1
    assert "XBuilderLAB/cheat-on-content" in gh[0]["ref_name"]


def test_extract_tool_framework():
    from knowledge_tracer import extract_references
    text = "本期介绍Gbrain的dream周期和skillify机制"
    refs = extract_references(text)
    tools = [r for r in refs if r["ref_type"] == "tool_framework"]
    assert len(tools) >= 1
    assert any("Gbrain" in t["ref_name"] for t in tools)


def test_extract_org_release():
    from knowledge_tracer import extract_references
    text = "DeepSeek正式发布DeepSeek-V4，性能大幅提升"
    refs = extract_references(text)
    orgs = [r for r in refs if r["ref_type"] == "org_release"]
    assert len(orgs) >= 1


def test_extract_person():
    from knowledge_tracer import extract_references
    text = "Sam Altman 回归 OpenAI，重新担任CEO"
    refs = extract_references(text)
    persons = [r for r in refs if r["ref_type"] == "person"]
    assert len(persons) >= 1


def test_extract_chinese_paper():
    """中文论文描述模式"""
    from knowledge_tracer import extract_references
    text = "一条视频搞懂deepseek最新论文engram"
    refs = extract_references(text)
    papers = [r for r in refs if r["ref_type"] == "paper_named"]
    assert len(papers) >= 1


def test_extract_empty_text():
    """空文本 → 空列表"""
    from knowledge_tracer import extract_references
    assert extract_references("") == []
    assert extract_references("   ") == []
    assert extract_references("纯中文内容无任何引用") == []


def test_extract_hashtag_noise():
    """只有 hashtags → 不产生虚假引用"""
    from knowledge_tracer import extract_references
    text = "#股市 #财经 #投资 #股票 #A股"
    refs = extract_references(text)
    # 不应该有 paper/github/org_release
    noise_types = {"paper_arxiv", "paper_named", "github", "org_release"}
    noisy = [r for r in refs if r["ref_type"] in noise_types]
    assert len(noisy) == 0


def test_extract_multiple_refs_same_text():
    """同一段文本多个引用"""
    from knowledge_tracer import extract_references
    text = (
        "DeepSeek最新论文engram解读，源码已开源github.com/deepseek-ai/engram，"
        "Andrej Karpathy 也转发了"
    )
    refs = extract_references(text)
    types = set(r["ref_type"] for r in refs)
    assert "github" in types
    assert "person" in types


def test_extract_git_not_github():
    """普通 'git' 单词不应触发 github 引用"""
    from knowledge_tracer import extract_references
    text = "这个功能需要git管理版本"
    refs = extract_references(text)
    gh = [r for r in refs if r["ref_type"] == "github"]
    assert len(gh) == 0


# ── score_reference 测试 ───────────────────────────────────


def test_score_reference_high_value_paper(tmp_path, monkeypatch):
    """论文引用 → 高分"""
    monkeypatch.setattr("knowledge_tracer.GAP_REGISTRY_FILE",
                        Path(__file__).parent.parent / ".." / "stock_data" / "knowledge" / "gap_registry.json")
    from knowledge_tracer import score_reference
    ref = {"ref_type": "paper_arxiv", "ref_name": "arXiv:2310.12345",
           "context": "RAG for multi-agent pipeline research paper"}
    result = score_reference(ref)
    assert result["score"] >= 3


def test_score_reference_unknown_type(tmp_path, monkeypatch):
    """未知类型引用 → 有评分不崩"""
    monkeypatch.setattr("knowledge_tracer.GAP_REGISTRY_FILE",
                        Path(__file__).parent.parent / ".." / "stock_data" / "knowledge" / "gap_registry.json")
    from knowledge_tracer import score_reference
    ref = {"ref_type": "unknown_type", "ref_name": "something random",
           "context": "no context"}
    result = score_reference(ref)
    assert result["score"] >= 1
    assert "matched_gaps" in result


# ── scan_archives 测试 ─────────────────────────────────────


def test_scan_archives_empty_dir(tmp_path, monkeypatch):
    """空归档目录 → 空列表"""
    empty = tmp_path / "empty_archive"
    empty.mkdir()
    monkeypatch.setattr("knowledge_tracer.ARCHIVE_DIR", empty)
    from knowledge_tracer import scan_archives
    assert scan_archives() == []


def test_scan_archives_corrupt_json(tmp_path, monkeypatch):
    """损坏的 JSON → 跳过不崩"""
    d = tmp_path / "archives"
    d.mkdir()
    (d / "corrupt.json").write_text("这不是json{{{", encoding="utf-8")
    monkeypatch.setattr("knowledge_tracer.ARCHIVE_DIR", d)
    from knowledge_tracer import scan_archives
    result = scan_archives()
    assert result == []  # 跳过损坏文件


def test_scan_archives_valid_content(tmp_path, monkeypatch):
    """正常归档 → 正确提取引用"""
    d = tmp_path / "archives"
    d.mkdir()
    data = {
        "nickname": "测试博主",
        "videos": [{
            "aweme_id": "123456",
            "desc": "本期介绍Gbrain的dream周期机制",
            "caption": "",
            "chapter_content": "",
        }]
    }
    (d / "test.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr("knowledge_tracer.ARCHIVE_DIR", d)
    from knowledge_tracer import scan_archives
    refs = scan_archives()
    assert len(refs) >= 1
    assert refs[0]["creator"] == "测试博主"


# ── record_trace_findings 测试 ─────────────────────────────


def test_record_trace_findings_dedup(tmp_path, monkeypatch):
    """同一引用重复记录 → 去重不重复写入"""
    monkeypatch.setattr("knowledge_tracer.PROSPECTOR_LOG", tmp_path / "prospector_log.json")
    monkeypatch.setattr("knowledge_tracer.GAP_REGISTRY_FILE",
                        Path(__file__).parent.parent / ".." / "stock_data" / "knowledge" / "gap_registry.json")
    from knowledge_tracer import record_trace_findings

    refs = [{
        "ref_type": "tool_framework",
        "ref_name": "Gbrain",
        "ref_url": "",
        "confidence": 0.9,
        "context": "Gbrain dream cycle",
        "creator": "九天Hector",
        "source_video": "123",
        "source_url": "",
        "discovered_at": "2026-05-27",
    }]

    # 第一次记录
    r1 = record_trace_findings(refs, min_score=1)
    assert len(r1) >= 1

    # 第二次记录（重复）
    r2 = record_trace_findings(refs, min_score=1)
    assert len(r2) == 0  # 全部去重


def test_record_trace_findings_min_score_filter(tmp_path, monkeypatch):
    """低于 min_score 的引用被过滤"""
    monkeypatch.setattr("knowledge_tracer.PROSPECTOR_LOG", tmp_path / "prospector_log.json")
    monkeypatch.setattr("knowledge_tracer.GAP_REGISTRY_FILE",
                        Path(__file__).parent.parent / ".." / "stock_data" / "knowledge" / "gap_registry.json")
    from knowledge_tracer import record_trace_findings

    refs = [{
        "ref_type": "person",
        "ref_name": "unknown person",
        "ref_url": "",
        "confidence": 0.5,
        "context": "some random mention",
        "creator": "测试博主",
        "source_video": "456",
        "source_url": "",
        "discovered_at": "2026-05-27",
    }]

    # min_score=5 → 应该全部被过滤（person类型最高得分也不到5）
    result = record_trace_findings(refs, min_score=5)
    assert len(result) == 0


# ── 全局边界条件 ───────────────────────────────────────────


def test_no_gap_registry_file(tmp_path, monkeypatch):
    """缺口文件不存在 → 评估不崩"""
    monkeypatch.setattr("knowledge_tracer.GAP_REGISTRY_FILE", tmp_path / "nonexistent.json")
    from knowledge_tracer import score_reference
    ref = {"ref_type": "paper_arxiv", "ref_name": "arXiv:2310.12345", "context": "test"}
    result = score_reference(ref)
    assert result["score"] >= 1


def test_trace_report_no_data(tmp_path, monkeypatch):
    """没有追溯发现时 → 报告不崩"""
    monkeypatch.setattr("knowledge_tracer.PROSPECTOR_LOG", tmp_path / "empty_log.json")
    # 写一个空的日志
    (tmp_path / "empty_log.json").write_text("[]", encoding="utf-8")
    from knowledge_tracer import analyze_gap_coverage
    coverage = analyze_gap_coverage()
    assert coverage["total_trace_findings"] == 0
    assert coverage["covered_gaps"] == 0
