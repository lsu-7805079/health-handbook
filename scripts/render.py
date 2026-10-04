from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
GRADE_ORDER = {"green": 0, "yellow": 1, "red": 2}
GRADE_ICON = {"green": "🟢", "yellow": "🟡", "red": "🔴"}


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def classify_blood_pressure(systolic: int, diastolic: int) -> tuple[str, str]:
    """Return (grade, detail), taking the higher-risk component."""
    if systolic >= 180 or diastolic >= 120:
        return "red", "达到紧急阈值，请立即就医或呼叫当地急救服务"
    if systolic >= 140 or diastolic >= 90:
        return "red", "明显异常，建议尽快就医"
    if systolic >= 120 or diastolic >= 80:
        return "yellow", "临界/轻度异常，建议生活方式干预并与医生确认"
    return "green", "正常，继续保持健康生活方式"


def bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def build_plan(systolic: int, diastolic: int) -> str:
    indicator = load_yaml(ROOT / "data" / "indicators" / "hypertension.yaml")
    recipes = load_yaml(ROOT / "recipes" / "vegetarian.yaml")
    template = (ROOT / "templates" / "plan_template.md").read_text(encoding="utf-8")

    grade, detail = classify_blood_pressure(systolic, diastolic)
    recipe = recipes[indicator["name"]]
    reference = indicator["reference"]
    reference_text = (
        f"正常 {reference['normal']}；临界 {reference['elevated']}；"
        f"异常 {reference['high']}；紧急 {reference['urgent']} mmHg"
    )

    values = {
        "OVERVIEW_ROW": f"| 血压 | {systolic}/{diastolic} mmHg | {reference_text} | {detail} |",
        "GRADE_ICON": GRADE_ICON[grade],
        "GRADE_LABEL": indicator["grades"][grade],
        "DIET_PRINCIPLES": bullets(indicator["diet_general"]["principles"]),
        "EAT_MORE": bullets(indicator["diet_general"]["eat_more"]),
        "EAT_LESS": bullets(indicator["diet_general"]["eat_less"]),
        "DIET_CAUTIONS": bullets(indicator["diet_general"]["cautions"]),
        "VEG_PLATE": recipe["餐盘原则"],
        "VEG_AVOID": "、".join(recipe["避开食物"]),
        "VEG_SEASONING": "、".join(recipe["低盐调味"]),
        "VEG_BREAKFAST": recipe["一日食谱"]["早餐"],
        "VEG_LUNCH": recipe["一日食谱"]["午餐"],
        "VEG_DINNER": recipe["一日食谱"]["晚餐"],
        "VEG_CAUTIONS": bullets(recipe["注意事项"]),
        "EXERCISE_AEROBIC": indicator["exercise"]["aerobic"],
        "EXERCISE_STRENGTH": indicator["exercise"]["strength"],
        "EXERCISE_FLEXIBILITY": indicator["exercise"]["flexibility_balance"],
        "EXERCISE_CONTRAINDICATIONS": indicator["exercise"]["contraindications"],
        "SLEEP_STRESS": bullets(indicator["sleep_stress"]),
        "MONITOR_HOME": indicator["monitoring"]["home"],
        "REVIEW_ITEMS": indicator["monitoring"]["review_items"],
        "REVIEW_TIME": indicator["monitoring"]["review_time"],
        "RED_FLAGS": bullets(indicator["red_flags"]),
        "DISCLAIMER": indicator["disclaimer"],
    }

    for key, value in values.items():
        template = template.replace("{{" + key + "}}", str(value))
    return template


def main() -> None:
    parser = argparse.ArgumentParser(description="生成高血压健康调理方案")
    parser.add_argument("--systolic", type=int, default=145, help="收缩压 mmHg")
    parser.add_argument("--diastolic", type=int, default=95, help="舒张压 mmHg")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "docs" / "indicators" / "hypertension.md",
        help="输出 Markdown 路径",
    )
    args = parser.parse_args()

    if not 40 <= args.systolic <= 300 or not 30 <= args.diastolic <= 200:
        parser.error("输入值超出本工具允许的录入范围，请核对后重试")

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_plan(args.systolic, args.diastolic), encoding="utf-8")
    print(f"已生成：{output}")


if __name__ == "__main__":
    main()

