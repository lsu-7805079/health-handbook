# 个人健康管理方案生成器

把血压数据转换成结构统一的健康管理参考方案。当前 MVP 只实现“高血压”一个指标，包含分级、饮食、素食方案、运动、睡眠、复查、红旗信号、记录表与 3 个月目标。

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

## 项目结构

```text
health-handbook/
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
