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


def safe_report_name(filename: str) -> str:
    source = Path(filename)
    stem = re.sub(r"[^A-Za-z0-9_-]+", "-", source.stem).strip("-") or "report"
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{timestamp}-{stem[:40]}{source.suffix.lower()}"


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
    </style>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("### 🌿 健康工作台")
    st.caption("数据仅保留在当前浏览器会话中，关闭后自动清除")
    page = st.radio(
        "导航",
        ["工作台首页", "体检报告", "血压评估", "健康记录", "工作台设置"],
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
    st.caption("支持 PDF、JPG、JPEG 和 PNG。文件仅在当前服务器会话中处理，所有结果都需要人工核对。")
    st.warning("建议先在本地删除姓名、身份证号、电话、住址和病历号。请勿上传不愿交由服务器处理的敏感报告。")

    uploaded_report = st.file_uploader(
        "上传体检报告",
        type=["pdf", "jpg", "jpeg", "png"],
        help="单个文件最大 20 MB；PDF 最多处理 30 页。",
    )
    if uploaded_report:
        file_bytes = uploaded_report.getvalue()
        file_size_mb = len(file_bytes) / 1024 / 1024
        st.caption(f"文件：{uploaded_report.name} · {file_size_mb:.2f} MB")
        if file_size_mb > 20:
            st.error("文件超过 20 MB，请压缩或拆分后再上传。")
        elif st.button("开始识别", type="primary", use_container_width=True):
            with st.spinner("正在本机提取报告内容，请稍候……"):
                try:
                    report_result = extract_report(file_bytes, Path(uploaded_report.name).suffix)
                    report_result["filename"] = uploaded_report.name
                    report_result["redacted_text"], report_result["sensitive"] = redact_sensitive_data(
                        report_result["text"]
                    )
                    report_result["indicators"] = find_common_indicators(report_result["redacted_text"])
                    st.session_state.report_result = report_result
                except Exception as exc:
                    st.error(f"识别失败：{exc}")

    report_result = st.session_state.get("report_result")
    if report_result:
        st.success(
            f"识别完成：{report_result['pages']} 页，处理方式为“{report_result['method']}”。"
        )
        for warning in report_result["warnings"]:
            st.warning(warning)
        if report_result["sensitive"]:
            st.warning(
                "系统检测并自动隐藏了以下隐私信息："
                + "、".join(report_result["sensitive"])
                + "。自动脱敏可能有遗漏，分享前仍需快速复核。"
            )
        st.subheader("识别到的常用指标")
        if report_result["indicators"]:
            st.data_editor(
                report_result["indicators"],
                use_container_width=True,
                hide_index=True,
                disabled=["指标", "单位", "状态"],
                key="report_indicators_editor",
            )
            st.caption("这些数值仅为机器识别结果，单位和参考范围以原报告为准。")
        else:
            st.info("暂未识别到支持的常用指标，你仍可查看并复制下方文本。")

        with st.expander("查看识别文本"):
            st.text_area(
                "自动脱敏后的识别结果（请核对数值）",
                value=report_result.get("redacted_text", report_result["text"]),
                height=320,
            )
        st.info("下一步：核对报告原文与识别值。当前不会自动作出诊断，也不会自动写入健康记录。")

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
