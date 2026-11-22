from pathlib import Path
from src.cli import main


def test_inspect_only_offline(capsys):
    root = Path(__file__).resolve().parents[1]
    exit_code = main(["--csv", str(root / "data/sample_sales.csv"), "--inspect-only"])
    out = capsys.readouterr().out
    assert exit_code == 0
    assert '"row_count": 14' in out
    assert '"Revenue"' in out


def test_cli_unknown_file(capsys):
    exit_code = main(["--csv", "/does/not/exist.csv", "--inspect-only"])
    assert exit_code == 2
    assert "FILE_NOT_FOUND" in capsys.readouterr().err


def test_terminal_output_removes_basic_markdown():
    from src.cli import format_terminal_answer
    content = "### 分析結果\n最高類別是 **Tech**，營收 **6000**。\n- 保留列表"
    result = format_terminal_answer(content)
    assert result.startswith("分析結果\n")
    assert "**" not in result
    assert "- 保留列表" in result
