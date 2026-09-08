from pathlib import Path


def test_readme_contains_portfolio_delivery_contract() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    required = [
        "## 运行",
        "## 环境变量",
        "## 测试与评测",
        "## API",
        "## 事件协议",
        "## 验证边界",
        "## 演示界面",
        "real_model_used=false",
    ]
    assert all(section in readme for section in required)
