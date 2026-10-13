from __future__ import annotations

import csv
import io
from datetime import date, datetime
from pathlib import Path
import re
import sys
from typing import Any

import streamlit as st


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "workspace_data"
ANALYSIS_DIR = DATA_DIR / "analysis"
sys.path.insert(0, str(ROOT / "scripts"))

from render import GRADE_ICON, build_plan, classify_blood_pressure  # noqa: E402
from report_parser import (  # noqa: E402
    detect_sensitive_data,
    extract_report,
    find_common_indicators,
    redact_sensitive_data,
)


DEFAULT_PROFILE = {
    "workspace_name": "我的健康工作台",
    "focus": "稳步改善血压与生活习惯",
    "weekly_goal": "本周完成 5 次规范血压测量",
}


def parse_blood_pressure(text: str) -> tuple[int, int] | None:
    compact_text = re.sub(r"\s+", " ", text)
    slash_match = re.search(r"(?<!\d)(\d{2,3})\s*/\s*(\d{2,3})(?!\d)", compact_text)
    named_match = re.search(
        r"收缩压\D{0,15}(\d{2,3}).{0,40}?舒张压\D{0,15}(\d{2,3})",
        compact_text,
        re.IGNORECASE,
    )
    match = slash_match or named_match
    if not match:
        return None
    systolic, diastolic = map(int, match.groups())
    if 40 <= systolic <= 300 and 30 <= diastolic <= 200:
        return systolic, diastolic
    return None


def records_to_csv(records: list[dict[str, Any]]) -> bytes:
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=["日期", "时间", "收缩压", "舒张压", "分级", "备注"],
    )
    writer.writeheader()
    writer.writerows(records)
    return output.getvalue().encode("utf-8-sig")


def indicator_rows_to_csv(rows: list[dict[str, str]]) -> bytes:
    output = io.StringIO()
    fieldnames = ["年份", "报告", "指标", "识别值", "单位", "状态"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8-sig")


def safe_report_name(filename: str) -> str:
    source = Path(filename)
    stem = re.sub(r"[^A-Za-z0-9_-]+", "-", source.stem).strip("-") or "report"
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{timestamp}-{stem[:40]}{source.suffix.lower()}"


def infer_report_year(filename: str, text: str) -> str:
    """Prefer a year in the filename, then look near common report date labels."""
    filename_match = re.search(r"(?<!\d)(20\d{2})(?!\d)", filename)
    if filename_match:
        return filename_match.group(1)
    labeled_match = re.search(
        r"(?:体检日期|检查日期|报告日期|日期)\D{0,12}(20\d{2})",
        text,
    )
    if labeled_match:
        return labeled_match.group(1)
    text_match = re.search(r"(?<!\d)(20\d{2})[年./-]", text[:3000])
    return text_match.group(1) if text_match else "年份待确认"


def indicator_comparison_rows(results: list[dict[str, Any]]) -> list[dict[str, str]]:
    columns = [f"{item['year']} · {item['filename']}" for item in results]
    names = sorted(
        {indicator["指标"] for item in results for indicator in item["indicators"]}
    )
    rows: list[dict[str, str]] = []
    for name in names:
        row = {"指标": name}
        for item, column in zip(results, columns):
            matched = next(
                (indicator for indicator in item["indicators"] if indicator["指标"] == name),
                None,
            )
            row[column] = (
                f"{matched['识别值']} {matched['单位']}" if matched else "—"
            )
        rows.append(row)
    return rows


def indicator_trend_rows(results: list[dict[str, Any]]) -> list[dict[str, str]]:
    series: dict[str, list[tuple[str, str, float, str]]] = {}
    for item in results:
        for indicator in item["indicators"]:
            name = indicator["指标"]
            value = indicator["识别值"]
            unit = indicator["单位"]
            if name == "血压" and "/" in value:
                parts = value.split("/", 1)
                for label, part in zip(("血压-收缩压", "血压-舒张压"), parts):
                    if re.fullmatch(r"\d+(?:\.\d+)?", part.strip()):
                        series.setdefault(label, []).append(
                            (item["year"], item["filename"], float(part), unit)
                        )
                continue
            number = re.search(r"-?\d+(?:\.\d+)?", value)
            if number:
                series.setdefault(name, []).append(
                    (item["year"], item["filename"], float(number.group()), unit)
                )

    rows: list[dict[str, str]] = []
    for name, points in sorted(series.items()):
        if len(points) < 2:
            continue
        first, latest = points[0], points[-1]
        same_unit = first[3] == latest[3]
        delta = latest[2] - first[2]
        direction = "↑" if delta > 0 else "↓" if delta < 0 else "→"
        change = f"{direction} {abs(delta):g} {latest[3]}" if same_unit else "单位不同，需人工核对"
        rows.append(
            {
                "指标": name,
                "起始报告": f"{first[0]} · {first[2]:g} {first[3]}",
                "最近报告": f"{latest[0]} · {latest[2]:g} {latest[3]}",
                "数值变化": change,
                "说明": "仅描述数值变化，不代表改善或恶化",
            }
        )
    return rows


def build_comparison_markdown(results: list[dict[str, Any]]) -> str:
    rows = indicator_comparison_rows(results)
    trend_rows = indicator_trend_rows(results)
    lines = [
        "# 多年度体检指标比较",
        "",
        "> 自动识别结果仅供整理和健康管理参考。请逐项核对原报告，不能替代医生诊断。",
        "",
        "## 报告清单",
        "",
    ]
    for item in results:
        lines.append(
            f"- {item['year']}｜{item['filename']}｜{item['pages']} 页｜{item['method']}"
        )
    lines.extend(["", "## 指标对照", ""])
    if not rows:
        lines.append("暂未识别到支持比较的常用指标。")
        return "\n".join(lines)

    headers = list(rows[0].keys())
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(header, "—")) for header in headers) + " |")
    lines.extend(["", "## 首次与最近一次的数值变化", ""])
    if trend_rows:
        trend_headers = list(trend_rows[0].keys())
        lines.append("| " + " | ".join(trend_headers) + " |")
        lines.append("| " + " | ".join(["---"] * len(trend_headers)) + " |")
        for row in trend_rows:
            lines.append(
                "| " + " | ".join(str(row.get(header, "—")) for header in trend_headers) + " |"
            )
    else:
        lines.append("至少需要两份报告识别到同一数值指标，才能计算变化。")
    lines.extend(
        [
            "",
            "## 使用说明",
            "",
            "- 相同指标的单位、检测方法和参考范围可能随医院或年份变化，比较前必须核对原报告。",
            "- “年份待确认”的报告请根据原报告日期人工确认。",
            "- OCR 可能把小数点、单位或数字识别错误，任何异常结论都应以原报告和医生意见为准。",
        ]
    )
    return "\n".join(lines)


if "profile" not in st.session_state:
    st.session_state.profile = DEFAULT_PROFILE.copy()
if "records" not in st.session_state:
    st.session_state.records = []

profile: dict[str, str] = st.session_state.profile
records: list[dict[str, Any]] = st.session_state.records

st.set_page_config(page_title=profile["workspace_name"], page_icon="🌿", layout="wide")
st.markdown(
    """
    <style>
    .block-container {padding-top: 1.8rem; padding-bottom: 3rem; max-width: 1180px;}
    [data-testid="stSidebar"] {background: #f5f8f4;}
    .hero {padding: 1.4rem 1.6rem; border-radius: 18px; background: linear-gradient(120deg,#e9f7ef,#f7f4e8); margin-bottom: 1.2rem;}
    .hero h1 {margin: 0 0 .35rem 0; font-size: 2rem; color: #173b2b;}
    .hero p {margin: 0; color: #496558;}
    .card {padding: 1rem 1.1rem; border: 1px solid #e4ebe6; border-radius: 14px; background: white; min-height: 128px;}
    .eyebrow {font-size: .78rem; color: #6b8175; letter-spacing: .08em; text-transform: uppercase;}
    .big-number {font-size: 1.8rem; font-weight: 700; color: #173b2b; margin: .3rem 0;}
    @media (max-width: 640px) {
        .block-container {padding: 1rem .8rem 2.5rem;}
        [data-testid="stFileUploader"] section {min-height: 7rem;}
        [data-testid="stFileUploader"] button {min-height: 2.8rem; font-size: 1rem;}
    }
    </style>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("### 🌿 健康工作台")
    st.caption("数据仅保留在当前浏览器会话中，关闭后自动清除")
    requested_page = st.query_params.get("page", "")
    default_page_index = 1 if requested_page == "report" else 0
    page = st.radio(
        "导航",
        ["工作台首页", "体检报告", "血压评估", "健康记录", "工作台设置"],
        index=default_page_index,
        label_visibility="collapsed",
    )
    st.divider()
    st.warning("录入前请删除姓名、身份证号、电话、住址、病历号等信息。")

if page == "工作台首页":
    st.markdown(
        f"<div class='hero'><h1>{profile['workspace_name']}</h1>"
        f"<p>{profile['focus']}</p></div>",
        unsafe_allow_html=True,
    )
    total = len(records)
    latest = records[-1] if records else None
    red_count = sum(record["分级"].startswith("🔴") for record in records)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"<div class='card'><div class='eyebrow'>累计记录</div><div class='big-number'>{total}</div><div>条血压记录</div></div>", unsafe_allow_html=True)
    with col2:
        latest_value = f"{latest['收缩压']}/{latest['舒张压']}" if latest else "—"
        latest_hint = latest["日期"] if latest else "还没有记录"
        st.markdown(f"<div class='card'><div class='eyebrow'>最近血压</div><div class='big-number'>{latest_value}</div><div>{latest_hint}</div></div>", unsafe_allow_html=True)
    with col3:
        st.markdown(f"<div class='card'><div class='eyebrow'>需关注记录</div><div class='big-number'>{red_count}</div><div>红级结果，请按提示就医</div></div>", unsafe_allow_html=True)

    st.subheader("本周重点")
    st.info(f"🎯 {profile['weekly_goal']}")
    st.subheader("开始使用")
    left, right = st.columns(2)
    with left:
        st.markdown("**1. 评估一次血压**")
        st.caption("手动输入或从已脱敏的报告文本中识别血压，生成结构化健康管理方案。")
    with right:
        st.markdown("**2. 持续查看趋势**")
        st.caption("保存每次结果，在健康记录页查看历史并导出 CSV 留存。")

elif page == "体检报告":
    st.title("体检报告")
    st.info(
        "📱 微信上传：在微信中打开本页面，点击下方按钮，然后选择手机里的 PDF 或报告照片。"
    )
    st.caption("支持 PDF、JPG、JPEG 和 PNG。单个文件最大 20 MB；PDF 最多处理 30 页。")
    st.warning("建议先在本地删除姓名、身份证号、电话、住址和病历号。请勿上传不愿交由服务器处理的敏感报告。")

    uploaded_reports = st.file_uploader(
        "从微信或手机选择多份体检报告",
        type=["pdf", "jpg", "jpeg", "png"],
        accept_multiple_files=True,
        help="点击后可从手机文件、相册或微信保存的文件中选择。",
    )
    st.caption("如果报告在微信聊天里，请先长按文件或图片保存到手机，再回到这里选择上传。")
    if uploaded_reports:
        total_size_mb = sum(len(item.getvalue()) for item in uploaded_reports) / 1024 / 1024
        st.caption(f"已选择 {len(uploaded_reports)} 份报告，共 {total_size_mb:.2f} MB。")
        oversized = [item.name for item in uploaded_reports if len(item.getvalue()) > 20 * 1024 * 1024]
        if len(uploaded_reports) > 12:
            st.error("一次最多处理 12 份报告，请分批上传。")
        elif total_size_mb > 80:
            st.error("本批文件合计超过 80 MB，请分批上传。")
        elif oversized:
            st.error("以下文件超过单份 20 MB：" + "、".join(oversized))
        elif st.button("识别并比较全部报告", type="primary", use_container_width=True):
            results: list[dict[str, Any]] = []
            failures: list[str] = []
            progress = st.progress(0, text="准备识别……")
            for index, uploaded_report in enumerate(uploaded_reports):
                progress.progress(
                    index / len(uploaded_reports),
                    text=f"正在识别 {uploaded_report.name}……",
                )
                try:
                    file_bytes = uploaded_report.getvalue()
                    report_result = extract_report(file_bytes, Path(uploaded_report.name).suffix)
                    report_result["filename"] = uploaded_report.name
                    report_result["redacted_text"], report_result["sensitive"] = redact_sensitive_data(
                        report_result["text"]
                    )
                    report_result["year"] = infer_report_year(
                        uploaded_report.name, report_result["redacted_text"]
                    )
                    report_result["indicators"] = find_common_indicators(report_result["redacted_text"])
                    results.append(report_result)
                except Exception as exc:
                    failures.append(f"{uploaded_report.name}：{exc}")
            progress.progress(1.0, text="识别完成")
            results.sort(key=lambda item: (item["year"] == "年份待确认", item["year"], item["filename"]))
            st.session_state.report_results = results
            st.session_state.report_failures = failures

    report_results = st.session_state.get("report_results", [])
    report_failures = st.session_state.get("report_failures", [])
    if report_failures:
        st.error("部分报告识别失败：\n\n" + "\n\n".join(f"- {item}" for item in report_failures))

    if report_results:
        st.success(f"已识别 {len(report_results)} 份报告，并生成跨年度指标对照。")
        comparison_rows = indicator_comparison_rows(report_results)
        st.subheader("历年体检指标对照")
        if comparison_rows:
            st.dataframe(comparison_rows, use_container_width=True, hide_index=True)
        else:
            st.info("这些报告中暂未识别到支持比较的常用指标。")

        trend_rows = indicator_trend_rows(report_results)
        st.subheader("首次与最近一次的数值变化")
        if trend_rows:
            st.dataframe(trend_rows, use_container_width=True, hide_index=True)
            st.caption("箭头只表示数值方向，不代表健康状况改善或恶化。")
        else:
            st.info("至少需要两份报告识别到同一数值指标，才能计算变化。")

        comparison_markdown = build_comparison_markdown(report_results)
        flat_rows = [
            {
                "年份": item["year"],
                "报告": item["filename"],
                **indicator,
            }
            for item in report_results
            for indicator in item["indicators"]
        ]
        output_left, output_right = st.columns(2)
        with output_left:
            st.download_button(
                "下载比较结果（Markdown）",
                data=comparison_markdown.encode("utf-8"),
                file_name="体检指标历年比较.md",
                mime="text/markdown",
                use_container_width=True,
            )
        with output_right:
            st.download_button(
                "下载指标明细（CSV）",
                data=indicator_rows_to_csv(flat_rows),
                file_name="体检指标历年明细.csv",
                mime="text/csv",
                use_container_width=True,
            )

        st.subheader("逐份报告核对")
        for index, report_result in enumerate(report_results):
            with st.expander(f"{report_result['year']} · {report_result['filename']}"):
                st.caption(
                    f"{report_result['pages']} 页 · {report_result['method']} · 自动识别结果待核对"
                )
                for warning in report_result["warnings"]:
                    st.warning(warning)
                if report_result["sensitive"]:
                    st.warning("已自动隐藏：" + "、".join(report_result["sensitive"]))
                if report_result["indicators"]:
                    st.dataframe(report_result["indicators"], use_container_width=True, hide_index=True)
                st.text_area(
                    "自动脱敏后的识别文本",
                    value=report_result.get("redacted_text", report_result["text"]),
                    height=240,
                    key=f"report_text_{index}",
                )
        st.info("比较结果只用于整理趋势；跨医院或跨年份时，请先核对单位、检测方法和参考范围。")

    analysis_files = sorted(ANALYSIS_DIR.glob("*.md"), key=lambda item: item.stat().st_mtime, reverse=True) if ANALYSIS_DIR.exists() else []
    if analysis_files:
        latest_analysis = analysis_files[0]
        analysis_text = latest_analysis.read_text(encoding="utf-8")
        st.divider()
        st.subheader("综合统计与健康管理分析")
        st.markdown(analysis_text)
        st.download_button(
            "下载综合分析（Markdown）",
            data=analysis_text.encode("utf-8"),
            file_name=latest_analysis.name,
            mime="text/markdown",
            use_container_width=True,
        )

elif page == "血压评估":
    st.title("血压评估")
    st.caption("当前版本支持血压指标。单次结果不能替代规范测量、多次记录和医生评估。")
    if "systolic" not in st.session_state:
        st.session_state.systolic = 120
    if "diastolic" not in st.session_state:
        st.session_state.diastolic = 80

    with st.expander("从体检报告文本识别", expanded=False):
        report_text = st.text_area("粘贴已脱敏的报告", height=150, placeholder="示例：血压 145/95 mmHg")
        if st.button("识别血压", use_container_width=True):
            parsed = parse_blood_pressure(report_text)
            if not report_text.strip():
                st.warning("请先粘贴已脱敏的体检报告文本。")
            elif parsed:
                st.session_state.systolic, st.session_state.diastolic = parsed
                st.success(f"已识别血压：{parsed[0]}/{parsed[1]} mmHg，请核对。")
            else:
                st.warning("没有识别到有效血压，请核对报告或手动填写。")

    left, right = st.columns(2)
    with left:
        systolic = st.number_input("收缩压（mmHg）", min_value=40, max_value=300, step=1, key="systolic")
    with right:
        diastolic = st.number_input("舒张压（mmHg）", min_value=30, max_value=200, step=1, key="diastolic")
    note = st.text_input("备注（可选）", placeholder="例如：晨起、静坐后测量；请勿填写身份信息")

    if st.button("生成健康管理方案", type="primary", use_container_width=True):
        grade, detail = classify_blood_pressure(int(systolic), int(diastolic))
        st.session_state.current_result = {
            "systolic": int(systolic), "diastolic": int(diastolic), "grade": grade,
            "detail": detail, "note": note, "plan": build_plan(int(systolic), int(diastolic)),
        }

    result = st.session_state.get("current_result")
    if result:
        grade = result["grade"]
        message = f"{GRADE_ICON[grade]} {result['detail']}"
        if grade == "red":
            st.error(message)
        elif grade == "yellow":
            st.warning(message)
        else:
            st.success(message)
        st.markdown(result["plan"])
        action1, action2 = st.columns(2)
        with action1:
            if st.button("保存到健康记录", use_container_width=True):
                now = datetime.now()
                records.append({
                    "日期": date.today().isoformat(), "时间": now.strftime("%H:%M"),
                    "收缩压": result["systolic"], "舒张压": result["diastolic"],
                    "分级": f"{GRADE_ICON[grade]} {grade}", "备注": result["note"],
                })
                st.session_state.records = records
                st.success("记录已保存在当前浏览器会话中。")
        with action2:
            st.download_button(
                "下载 Markdown 方案", data=result["plan"].encode("utf-8"),
                file_name=f"blood-pressure-plan-{date.today().isoformat()}.md",
                mime="text/markdown", use_container_width=True,
            )

elif page == "健康记录":
    st.title("健康记录")
    st.caption("记录仅在当前浏览器会话中保存，关闭页面后会清除。需要长期留存时请导出 CSV。")
    if records:
        st.dataframe(list(reversed(records)), use_container_width=True, hide_index=True)
        st.download_button(
            "导出全部记录（CSV）", data=records_to_csv(records),
            file_name=f"blood-pressure-records-{date.today().isoformat()}.csv",
            mime="text/csv", use_container_width=True,
        )
        with st.expander("数据管理"):
            confirm_delete = st.checkbox("我确认要清空当前会话的全部血压记录")
            if st.button("清空全部记录", disabled=not confirm_delete):
                st.session_state.records = []
                st.success("全部记录已清空。")
                st.rerun()
    else:
        st.info("还没有记录。请先在“血压评估”中生成并保存一次结果。")

else:
    st.title("工作台设置")
    st.caption("这里只保存工作台显示偏好，请不要填写真实身份或病历信息。")
    with st.form("workspace_settings"):
        workspace_name = st.text_input("工作台名称", value=profile["workspace_name"], max_chars=30)
        focus = st.text_input("当前健康重点", value=profile["focus"], max_chars=60)
        weekly_goal = st.text_input("本周目标", value=profile["weekly_goal"], max_chars=80)
        submitted = st.form_submit_button("保存设置", type="primary", use_container_width=True)
    if submitted:
        updated_profile = {
            "workspace_name": workspace_name.strip() or DEFAULT_PROFILE["workspace_name"],
            "focus": focus.strip() or DEFAULT_PROFILE["focus"],
            "weekly_goal": weekly_goal.strip() or DEFAULT_PROFILE["weekly_goal"],
        }
        st.session_state.profile = updated_profile
        st.success("设置已保存在当前浏览器会话中。")
        st.rerun()

st.divider()
st.caption("本方案为健康管理参考，不替代医生诊断、治疗和用药建议。")
