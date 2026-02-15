# 2024 Tax Return: CPA 结果 vs 本工具 差异分析

基于 CPA 提供的 `2024.pdf` 与工具输出的对比（金额单位：美元）。

---

## 一、联邦税 (Form 1040)

### 1. 收入 (Income)

| 项目 | CPA (2024.pdf) | 本工具 | 差异 | 可能原因 |
|------|-----------------|--------|------|----------|
| Wages | 2,069,937 | 2,069,937.14 | ✓ 一致 | |
| Interest income | **6,339** | **2,004.59** | **工具少约 4,334** | 工具可能少算了利息收入；CPA 侧有 CA 扣除「Taxable interest」4,334（即 U.S. Treasury 利息），联邦仍报 6,339。检查是否漏 1099-INT 或某张 1099 利息未纳入。 |
| Dividend income | **18,711** | **21,081.94** | **工具多约 2,371** | 可能多算/重复算某笔股息，或 qualified/ordinary 划分与 CPA 不同。需核对 1099-DIV 张数与金额。 |
| Taxable IRA / Retirement | 9 | 2.00 | ≈ 一致 | 四舍五入差异。 |
| Capital gain or loss | -3,000 | -3,000.00 | ✓ 一致 | |
| Other income | 600 | 600.00 | ✓ 一致 | |
| **Net Rental (Schedule E)** | （含在总所得中） | 2,988.64 | — | 工具单独列出 Schedule E 净租金 2,988.64；CPA 总所得 2,092,596 若已含租金则与工具 AGI 接近。 |
| **Total income / AGI** | **2,092,596** | **2,093,614.31** | 工具多约 1,018 | 主要来自：利息少 4,334 + 股息多 2,371 + 其他小项。 |

### 2. 扣除 (Deductions) — **差异最大**

| 项目 | CPA | 本工具 | 说明 |
|------|-----|--------|------|
| Taxes (SALT) | 10,000 | 10,000 | ✓ 一致（联邦 SALT 上限 1 万） |
| **Interest (房贷利息)** | **27,183** | **0** | **工具未计入房贷利息**。CPA 有 27,183，说明用了 1098 的 mortgage interest；工具显示 Mortgage Interest 0，可能 1098 未正确归类为「个人住房」或未提取/未合并到 Schedule A。 |
| **Contributions (慈善)** | **1,205** | **0** | **工具未计入慈善扣除**。可能漏提取 donation 收据或 config 未填 charitable_contributions。 |
| **Total itemized** | **38,388** | 10,000 | CPA 用 itemized（10k+27,183+1,205）；工具只有 SALT 10k，itemized 合计 10,000。 |
| Standard deduction | 29,200 | 29,200 | ✓ 一致 |
| **实际使用** | **Itemized 38,388** | **Standard 29,200** | **工具因缺少 mortgage + charitable 而用了标准扣除，比 CPA 少扣约 9,188。** |

### 3. 税额与付款

| 项目 | CPA | 本工具 | 差异 |
|------|-----|--------|------|
| Taxable income | 2,054,155 | 2,064,414.31 | 工具多约 10,259（因扣除少 9,188） |
| Tax before credits | 683,481 | 704,525.94 | 工具高（税率档 + 其他税） |
| Other taxes (Add'l Medicare + NIIT 等) | 17,499 | 16,759.82 + 876.86 ≈ 17,637 | 接近 |
| **Total tax** | **700,980** | **704,525.94** | 工具多约 3,546 |
| Federal withheld | **607,058** | **590,906.21** | **工具少算约 16,152**（可能漏某张 W-2/1099 的 withholding） |
| Estimated tax payments | **100,000** | **110,000** | 工具多 10,000（来自收据提取的 estimated；若以 CPA 为准可把 config 或提取结果调成 100k） |
| **Refund / Owed** | **Overpaid 6,078** | **Owed 3,619.73** | 方向相反：CPA 多缴 6,078，工具显示欠 3,619.73 |

---

## 二、加州税 (Form 540)

| 项目 | CPA | 本工具 | 差异 |
|------|-----|--------|------|
| CA AGI (after subtractions) | 2,088,262 | 2,089,280.02 | 接近（CA 扣除 U.S. Treasury 等） |
| Itemized before limitation | 86,062 | （工具内 45,177 等） | 计算口径不同 |
| CA itemized deductions | 17,212 | 9,035.43 | 工具较低（与联邦侧缺 mortgage/charitable 一致） |
| CA standard deduction | 11,080 | 10,726.00 | 接近 |
| **Used** | **Itemized 17,212** | **Standard 10,726** | 工具再次用 standard，扣除较少 |
| CA taxable income | 2,071,050 | 2,078,554.02 | 工具多约 7,504 |
| CA tax + Mental health | 228,240 | 230,426.00 | 工具多约 2,186 |
| CA withheld | 218,294 | 218,293.33 | ✓ 一致 |
| CA estimated | 10,000 | 0 | 工具为 0（config 里 ca_estimated_payments 为 0 或未从收据提取到 CA 预缴） |
| **Refund / Owed** | **Overpaid 54** | **Owed 12,132.67** | CPA 多缴 54，工具显示欠 12,132.67 |

---

## 三、差异原因归纳与建议

1. **利息收入少约 4,334**  
   - 检查是否漏报某张 1099-INT，或 U.S. Treasury 利息在工具里是否计入了「利息」且是否与 CPA 一致。  
   - 确认 config 或提取结果里没有误减掉应付税的利息。

2. **股息多约 2,371**  
   - 核对 1099-DIV 张数、每张金额，避免重复或错误归类。  
   - 确认 qualified vs ordinary 的划分与 CPA 一致。

3. **房贷利息 27,183 未计入（最关键之一）**  
   - 工具 Schedule A 显示 Mortgage Interest 0。  
   - 检查：个人住房 1098 是否被正确识别（未误标为 rental）；`config` 里是否有 `personal_mortgage_balance` 等影响利息可扣性的设置；1098 的 mortgage interest 是否被正确解析并写入 Schedule A。

4. **慈善扣除 1,205 未计入**  
   - 检查 donation 收据是否在「Charitable Contribution」类下被提取；或是否在 config 中填写 `charitable_contributions: 1205`（或实际金额）。

5. **联邦预缴与 withholding**  
   - 若以 CPA 为准：联邦 estimated 应为 100,000（不是 110,000）— 可把 config 的 `federal_estimated_payments` 设为 100000，并确保不重复加收据提取的金额。  
   - 联邦 withheld 工具比 CPA 少约 16,152：检查是否漏 W-2/1099 或某张的 withholding 提取错误。

6. **加州预缴**  
   - CPA 有 CA estimated 10,000，工具为 0：若属实，在 config 填 `ca_estimated_payments: 10000` 或从收据中正确提取 CA 预缴。

7. **Itemized vs Standard**  
   - 一旦补上 mortgage interest 27,183 和 charitable 1,205，工具的 itemized 会大于 standard，结果会与 CPA 一致采用 itemized，应税所得和税额会明显接近 CPA。

---

## 四、建议的 config / 数据修正（供你核对后填写）

- `charitable_contributions`: 1205（若与 CPA 一致）
- 确认 1098 个人住房利息 27,183 被正确归类并进入 Schedule A（检查 1098 分类与解析）。
- `federal_estimated_payments`: 100000（若以 CPA 100,000 为准）。
- `ca_estimated_payments`: 10000（若 CPA 的 CA 预缴 10,000 正确）。
- 核对 W-2/1099 的 withholding 与 CPA 607,058 一致（补漏或修正提取）。
- 核对利息 6,339、股息 18,711 的来源（补漏或去重）。

完成上述修正后重新跑一遍工具，再与 CPA 的 2024.pdf 逐行对比即可精确定位剩余差异。
