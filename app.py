from pathlib import Path
import re
import sys

import streamlit as st


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))

from render import GRADE_ICON, build_plan, classify_blood_pressure  # noqa: E402


st.set_page_config(page_title="个人健康管理方案生成器", page_icon="❤️", layout="wide")
st.title("个人健康管理方案生成器")
st.caption("当前版本仅支持血压指标。请勿输入姓名、身份证号、电话、住址或病历号等隐私信息。")

indicator = st.selectbox("选择指标", ["高血压"])

if "systolic" not in st.session_state:
    st.session_state.systolic = 120
if "diastolic" not in st.session_state:
    st.session_state.diastolic = 80

report_text = st.text_area(
    "粘贴体检报告",
    height=180,
    placeholder=(
        "请先删除姓名、身份证号、电话、住址和病历号等信息，再粘贴报告。\n\n"
        "示例：血压 145/95 mmHg\n"
        "或：收缩压 145 mmHg，舒张压 95 mmHg"
    ),
    help="当前版本只从文本中识别血压，其他指标将在后续版本支持。",
)

if st.button("从报告中识别血压", use_container_width=True):
    compact_text = re.sub(r"\s+", " ", report_text)
    slash_match = re.search(r"(?<!\d)(\d{2,3})\s*/\s*(\d{2,3})(?!\d)", compact_text)
    named_match = re.search(
        r"收缩压\D{0,15}(\d{2,3}).{0,40}?舒张压\D{0,15}(\d{2,3})",
        compact_text,
        re.IGNORECASE,
    )
    match = slash_match or named_match

    if not report_text.strip():
        st.warning("请先粘贴已脱敏的体检报告文本。")
    elif match:
        parsed_systolic, parsed_diastolic = map(int, match.groups())
        if 40 <= parsed_systolic <= 300 and 30 <= parsed_diastolic <= 200:
            st.session_state.systolic = parsed_systolic
            st.session_state.diastolic = parsed_diastolic
            st.success(f"已识别血压：{parsed_systolic}/{parsed_diastolic} mmHg，请核对后再生成方案。")
        else:
            st.warning("识别到的数值超出录入范围，请核对报告并手动填写。")
    else:
        st.warning("暂未识别到血压，请使用下方输入框手动填写。")

left, right = st.columns(2)
with left:
    systolic = st.number_input(
        "收缩压（mmHg）", min_value=40, max_value=300, step=1, key="systolic"
    )
with right:
    diastolic = st.number_input(
        "舒张压（mmHg）", min_value=30, max_value=200, step=1, key="diastolic"
    )

if st.button("生成健康调理方案", type="primary", use_container_width=True):
    grade, detail = classify_blood_pressure(int(systolic), int(diastolic))
    if grade == "red":
        st.error(f"{GRADE_ICON[grade]} {detail}")
    elif grade == "yellow":
        st.warning(f"{GRADE_ICON[grade]} {detail}")
    else:
        st.success(f"{GRADE_ICON[grade]} {detail}")

    plan = build_plan(int(systolic), int(diastolic))
    st.markdown(plan)
    st.download_button(
        "下载 Markdown",
        data=plan.encode("utf-8"),
        file_name="hypertension_plan.md",
        mime="text/markdown",
        use_container_width=True,
    )

st.divider()
st.caption("本方案为健康管理参考，不替代医生诊断、治疗和用药建议。")
