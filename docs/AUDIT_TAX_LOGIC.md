# Tax Calculation Logic — Audit

本文档对当前税表计算逻辑做**深入审计**，覆盖数据流、收入、扣除、联邦税、州税与精度。

---

## 1. 数据流总览

```
Documents (PDF/CSV/Excel)
    → Parser (OCR/PDF) → data_extractor.extract_all()
    → TaxReturn (W-2, 1099-*, 1098, receipts…)
    → main: 收入汇总 + Config 覆盖 + 资本损失 carryover
    → Schedule E (租金) → Schedule A 数据准备
    → process_tax_return():
        Step 1: Schedule E (折旧、净租金)
        Step 2: Schedule A 数据 (SALT、房贷利息、慈善等)
        Step 3: FederalTaxCalculator.calculate()
        Step 4: calculate_state_tax(state_of_residence, …)
    → TaxCalculation (Federal + State) → Report
```

- **Config 覆盖顺序**：在 `process_tax_return` 之前应用：capital_loss_carryover → qualified_dividends / ordinary_dividends → other_income → estimated_payments → federal_withheld_adjustment → personal_mortgage_balance → primary_property_tax / charitable 等写入 Schedule A 数据。

---

## 2. 收入 (TaxableIncome)

| 字段 | 来源 | Config 覆盖 |
|------|------|-------------|
| wages | W-2 Box 1 汇总 | 无 |
| interest_income | 1099-INT (扣 US Treasury 在州税侧处理) | 无 |
| dividend_income | 1099-DIV Box 1a，composite 解析 | `ordinary_dividends` > 0 时**替换** |
| qualified_dividends | 1099-DIV Box 1b | `qualified_dividends` > 0 时**替换** |
| capital_gains | 1099-B gain_loss 汇总 + 1099-DIV Box 2a | 应用 carryover 后为“净”资本利得/损失 |
| short_term_capital_gains | 1099-B (is_short_term) | 无 |
| long_term_capital_gains | 1099-B (非 short_term) | 无 |
| other_income | 1099-MISC Box 3 + 1099-G (失业+州退税) | 有提取时用提取值；否则加 config.other_income |
| self_employment_income | 1099-NEC Box 1 | 无 |
| retirement_income | 1099-R 应税额 (Code G 已排除) | 无 |
| rental_income | Schedule E 净租金 (见下) | 无 |

- **total_income** = wages + interest + dividend + capital_gains + other + self_employment + retirement + rental（rental 可为负）。
- **1099-R**：distribution_code == "G" 不加入 retirement_income。

---

## 3. 资本利得与损失

- **Carryover**：`config.capital_loss_carryover` 先抵减当年 `income.capital_gains`；抵减后若为净损失，可扣除部分封顶 **$3,000**（MFS **$1,500**），超出部分进入 `_capital_loss_carryover_remaining`（仅存储，不自动带到下年）。
- **联邦 QD/LTCG 优惠税率**：  
  - 应税收入中“优惠部分”= qualified_dividends + 长期资本利得（含 1099-DIV Box 2a）。  
  - 代码中 **net_ltcg** = `income.capital_gains - income.short_term_capital_gains`（即 LTCG + 1099-DIV 资本利得分配），不再用 `long_term_capital_gains + capital_gains`，避免重复计算。
- **NIIT (3.8%)**：NII = interest + dividend_income + capital_gains（>0 部分）+ max(0, rental_income)。MAGI 超过阈值时，NIIT = 3.8% × min(NII, MAGI - threshold)。资本损失会减少 NII；rental 损失在 NII 中按 0 计。

---

## 4. Schedule E（租金）

- **折旧**：住宅租赁 27.5 年直线法，**mid-month convention**（首年/末年按 in-service 月数比例）。
- **净租金** = 租金收入 − 费用（含折旧）。
- **被动活动损失 (PAL)**：  
  - 初步 AGI > $150,000：租金净损失全部不允许，记入 pal_disallowed / pal_carryover。  
  - $100,000 < 初步 AGI ≤ $150,000：$25,000 特殊抵扣按 50% × (AGI − $100,000) 逐步减少。  
  - 初步 AGI = total_income − rental_income（未扣租金损失前）。

---

## 5. Schedule A 与扣除

- **标准扣除**：`federal_tax.STANDARD_DEDUCTION[tax_year][filing_status]`，65+/盲人有额外金额。
- **Itemized**：  
  - 医疗：超过 AGI 7.5% 部分。  
  - **SALT**：联邦 **$10,000** 上限（MFS $5,000）；含州税已缴、房产税、VLF 等。  
  - **房贷利息**：联邦 **$750,000** 债务上限（MFS $375,000），按 balance/limit 比例折算。  
  - 慈善、其他按规定汇总。
- **选用**：itemized 与 standard 比较，取大者作为 deduction_amount。
- **CA**：无 SALT $10k 上限；CA itemized 有高收入 phaseout（6% 递减，最高 80% 限制）。

---

## 6. 联邦税 (FederalTaxCalculator)

- **税率表**：`FEDERAL_TAX_BRACKETS_2024/2025`，按 filing_status。
- **SE 税**：净 SE 收入 × 92.35% 后，SS 部分适用 wage base（2025 $176,100），税率 12.4%；Medicare 2.9%；超过附加 Medicare 阈值再 0.9%。可扣除一半 SE 税 above-the-line。
- **附加 Medicare 税**：W-2 工资（优先用 Box 5 Medicare wages）超过阈值部分 × 0.9%。
- **Tax (Line 16)**：  
  - 若有 QD 或正 net_ltcg：`calculate_qdcg_tax()` — 普通收入按普通档位，QD+LTCG 按 0%/15%/20% **堆叠**在普通收入之上。  
  - 否则：普通累进税率。
- **NIIT**：见上。
- **tax_before_credits** = 所得税 + SE 税 + 附加 Medicare + NIIT。
- **Child Tax Credit**：$2,000/孩（17 岁以下），AGI 超过 phaseout 后每 $1,000 多减 $50。
- **tax_after_credits** = max(0, tax_before_credits − total_credits)。
- 所有金额输出 **round(..., 2)**。

---

## 7. 州税 (state_tax.calculate_state_tax)

- **无所得税州**：AK, FL, NV, NH, SD, TN, TX, WA, WY → 返回 None。
- **CA**：`california_tax.CaliforniaTaxCalculator`（Form 540，无 SALT 上限，itemized 限制，renter credit 等）。
- **NY**：`state_tax.NewYorkTaxCalculator`（IT-201，累进税率，SALT 上限 $10k 用于 itemized）。
- **NJ**：`NewJerseyTaxCalculator`（NJ-1040，累进 1.4%–10.75%，标准扣除 Single $10k / MFJ $20k）。
- **PA**：`PennsylvaniaTaxCalculator`（PA-40， flat 3.07%，无标准扣除）。
- 其他州：返回 None（报告提示未实现）。

州税 **estimated_payments** 按 jurisdiction（california, new_york, nj, pa）与 `state_of_residence` 匹配后汇总传入。

---

## 8. 精度与四舍五入

- 货币统一 **保留两位小数**，在 `TaxCalculation` 构造处对 gross_income、adjustments、agi、deductions、taxable_income、tax_before_credits、credits、tax_after_credits、withheld、estimated_payments、niit、child_tax_credit 等做 `round(..., 2)`。
- Schedule A / Schedule E 结果内部也按 2 位小数 round。
- 未使用 `decimal.Decimal`，浮点累积误差在常规金额下可接受，但若将来做高精度或税务稽查级复核，可考虑改为 Decimal。

---

## 9. 已修复问题（本次审计）

- **net_ltcg 重复计算**：原先 `net_ltcg = income.long_term_capital_gains + income.capital_gains` 导致长期资本利得被算两次。已改为 `net_ltcg = income.capital_gains - income.short_term_capital_gains`（即 LTCG + 1099-DIV Box 2a）。

---

## 10. 已知限制与边界

- **资本损失 carryover**：仅支持“一个”总 carryover 数，不区分 ST/LT carryover；剩余 carryover 不自动写入下年 config。
- **QD/LTCG**：未实现 28% 税率（collectibles）；未实现 unrecaptured §1250 gain 的 25% 档。
- **NIIT**：未考虑 S-corps/partnerships 的 NII 穿透；rental 损失在 NII 中按 0 计。
- **州税**：仅实现 CA、NY、NJ、PA；其他州无计算。
- **Form 1116**：境外税抵免未实现。
- **AMT**：未实现。
- **依赖与 EIC**：CTC 仅按 num_qualifying_children；EIC、ACTC、ODC 等未实现。

---

## 11. 关键文件索引

| 模块 | 职责 |
|------|------|
| `main.py` | 文档处理、收入汇总、config 覆盖、carryover、Schedule A 数据准备、调用 federal/state |
| `models.py` | TaxReturn, TaxableIncome, Deductions, TaxCredits, TaxCalculation, ScheduleAData, Form1098/1099-* |
| `federal_tax.py` | 联邦税率、标准扣除、QD/LTCG、NIIT、SE 税、附加 Medicare、CTC |
| `schedule_a.py` | Itemized（SALT 上限、房贷上限、VLF）、CA itemized 限制 |
| `schedule_e.py` | 租金折旧（27.5 年）、净租金、PAL 简化逻辑 |
| `california_tax.py` | CA 540 税率、扣除、credits |
| `state_tax.py` | 州税分发、NY/NJ/PA 计算器 |

测试：`python test_tax_calculation.py` 覆盖联邦、CA、Schedule A/E、carryover、NIIT、QD/LTCG、附加 Medicare 等。
