"""의존성 설치 전에도 실행할 수 있는 최소 정적 smoke test."""

from pathlib import Path
import ast
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_python_files_compile():
    for path in [ROOT / "run.py", *ROOT.glob("app/**/*.py")]:
        ast.parse(path.read_text(encoding="utf-8"))


def test_javascript_syntax():
    node = subprocess.run(["node", "--version"], capture_output=True, text=True)
    if node.returncode != 0:
        return
    for path in (ROOT / "app/static/js").glob("*.js"):
        result = subprocess.run(
            ["node", "--check", str(path)], capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr
