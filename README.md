# 个人健康管理工作台

一个本地运行的个人健康管理工作台。当前版本支持工作台首页、血压评估、健康记录和个性化设置，并能把血压数据转换成结构统一的健康管理参考方案。

工作台设置与健康记录仅保留在当前浏览器会话中，关闭页面后自动清除。需要长期留存时可导出 CSV。

> 使用前请删除姓名、身份证号、电话、住址、病历号等隐私信息。本工具不用于诊断、治疗或调整用药。

## 环境要求

- Python 3.10 或更高版本

## 安装与运行网页

在项目目录中执行：

```bash
python -m venv .venv
```

Windows PowerShell：

```powershell
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

命令执行后，浏览器通常会自动打开 `http://localhost:8501`。

## 直接生成 Markdown

下面的命令会用示例血压 `145/95 mmHg` 生成文档：

```powershell
python scripts/render.py --systolic 145 --diastolic 95
```

输出文件：`docs/indicators/hypertension.md`。

也可以指定输出位置：

```powershell
python scripts/render.py --systolic 128 --diastolic 82 --output my-plan.md
```

## 分级逻辑

- 绿级：收缩压 `<120` 且舒张压 `<80`
- 黄级：未达到红级，且收缩压 `120-139` 或舒张压 `80-89`
- 红级：收缩压 `>=140` 或舒张压 `>=90`
- 紧急提示：收缩压 `>=180` 或舒张压 `>=120`

两个数值按风险更高的一项分级。以上阈值来自本项目 PRD；实际判断需结合规范测量、多次记录、既往病史及医生评估。

## 工作台功能

- 首页：查看记录数量、最近血压、需关注记录和本周目标。
- 体检报告：上传 PDF、JPG、JPEG 或 PNG，在本机提取文字并识别常用指标。
- 血压评估：手动录入或从已脱敏文本识别血压，生成并下载方案。
- 健康记录：本机保存、列表查看和 CSV 导出。
- 工作台设置：修改工作台名称、健康重点和本周目标。

体检报告只在当前服务器会话中处理，不保存原始文件。公网使用时，请先删除姓名、身份证号、电话、住址和病历号等敏感信息。

## 项目结构

```text
健康管理工具/
├─ AGENTS.md
├─ README.md
├─ requirements.txt
├─ app.py
├─ data/indicators/hypertension.yaml
├─ recipes/vegetarian.yaml
├─ templates/plan_template.md
├─ scripts/render.py
└─ docs/indicators/hypertension.md
```

## 安全边界

- 不提供药物或补剂剂量。
- 不建议自行停药、换药或调整剂量。
- 红级结果提示尽快就医；紧急阈值或红旗症状提示立即就医。
- 不确定的医学项目保留 `TODO：待医生评估`。

---

免责声明：本方案为健康管理参考，不替代医生诊断、治疗和用药建议。
