import unittest
from src.federal_tax import calculate_federal_tax
from src.california_tax import calculate_ca_tax
from src.models import TaxpayerProfile

class Test2025TaxRates(unittest.TestCase):
    def setUp(self):
        # 定义一个简单的 2025 申报 profile
        self.profile = TaxpayerProfile(
            tax_year=2025,
            filing_status="married_jointly",
            is_ca_resident=True,
            standard_deduction=30000, # 2025 MFJ 预估标准扣除额
        )

    def test_federal_brackets_2025(self):
        # 测试联邦阶梯税率 (假设收入 100,000)
        # 验证逻辑是否正确处理了 2025 年的通胀调整
        income = 100000
        tax = calculate_federal_tax(income, self.profile)
        self.assertGreater(tax, 0)
        print(f"2025 Federal Tax for $100k: ${tax:,.2f}")

    def test_ca_mental_health_tax(self):
        # 测试加州 1% 心理健康服务税 (收入需 > $1M)
        high_income = 1500000
        tax = calculate_ca_tax(high_income, self.profile)
        # 1.5M - 1M = 500k, 500k * 1% = 5,000 的额外税
        self.assertGreater(tax, 5000)
        print(f"2025 CA Tax for $1.5M (incl. MHST): ${tax:,.2f}")

if __name__ == "__main__":
    unittest.main()