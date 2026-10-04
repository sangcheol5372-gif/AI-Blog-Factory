"""양도소득세 간이 추정. 세무 신고용이 아니며, 결과에는 전제를 함께 붙인다.

반영: 기본세율(누진), 기본공제 250만원(인별), 8년 자경농지 감면(인별 연 1억 한도),
      비사업용 토지 중과(+10%p) 여부, 지방소득세 10%.
미반영(전제로 표기): 장기보유특별공제(상속 후 3년 미만 보유 가정 → 0),
      감면 5년 합산 2억 한도, 다른 양도 건과의 합산, 필요경비(별도 입력 시만).
"""
from dataclasses import asdict, dataclass

# (과세표준 상한, 세율, 누진공제) — 2023.1.1 이후 양도분
BRACKETS = [
    (14_000_000, 0.06, 0),
    (50_000_000, 0.15, 1_260_000),
    (88_000_000, 0.24, 5_760_000),
    (150_000_000, 0.35, 15_440_000),
    (300_000_000, 0.38, 19_940_000),
    (500_000_000, 0.40, 25_940_000),
    (1_000_000_000, 0.42, 35_940_000),
    (float("inf"), 0.45, 65_940_000),
]
BASIC_DEDUCTION = 2_500_000
SELF_FARMING_RELIEF_LIMIT = 100_000_000  # 인별 과세기간 한도
LOCAL_RATE = 0.10

ASSUMPTIONS = [
    "상속인별 지분 균등, 이 토지 외 같은 해 다른 양도 없음",
    "장기보유특별공제 0 (상속개시일부터 3년 미만 보유 가정)",
    "자경감면은 인별 연 1억 한도만 반영(5년 합산 2억 한도는 미반영)",
    "지방소득세: 낙관(감면 후 국세의 10%) / 보수(감면 전 산출세액의 10%, 지방세에는 자경감면이 없다고 가정) 두 경우를 함께 표시",
    "세율 적용 보유기간은 피상속인 취득일부터 기산(소득세법 제104조②) — 단기세율 미적용",
]


def progressive(base: float) -> float:
    for limit, rate, ded in BRACKETS:
        if base <= limit:
            return max(0.0, base * rate - ded)
    raise AssertionError


@dataclass
class TaxResult:
    heirs: int
    sale_price: int
    acquisition: int
    gain_total: int
    taxable_per_heir: int
    tax_before_relief_per_heir: int
    relief_per_heir: int
    national_per_heir: int
    local_per_heir: int
    total_tax: int
    net_proceeds: int
    total_tax_conservative: int
    net_proceeds_conservative: int

    def as_dict(self):
        return asdict(self)


def transfer_tax(sale_price: int, acquisition: int, heirs: int = 1, expenses: int = 0,
                 self_farming: bool = True, non_business: bool = False) -> TaxResult:
    gain_total = max(0, sale_price - acquisition - expenses)
    gain = gain_total / heirs
    taxable = max(0.0, gain - BASIC_DEDUCTION)
    tax = progressive(taxable) + (taxable * 0.10 if non_business else 0)
    relief = min(tax, SELF_FARMING_RELIEF_LIMIT) if self_farming else 0
    national = tax - relief
    local = national * LOCAL_RATE
    total = round((national + local) * heirs)
    total_cons = round((national + tax * LOCAL_RATE) * heirs)
    return TaxResult(
        heirs=heirs, sale_price=sale_price, acquisition=acquisition, gain_total=round(gain_total),
        taxable_per_heir=round(taxable), tax_before_relief_per_heir=round(tax),
        relief_per_heir=round(relief), national_per_heir=round(national), local_per_heir=round(local),
        total_tax=total, net_proceeds=sale_price - total,
        total_tax_conservative=total_cons, net_proceeds_conservative=sale_price - total_cons,
    )


def scenarios(sale_prices: dict[str, int], acquisitions: dict[str, int], heir_counts: list[int],
              self_farming: bool = True) -> list[dict]:
    out = []
    for sale_label, sale in sale_prices.items():
        for acq_label, acq in acquisitions.items():
            for n in heir_counts:
                r = transfer_tax(sale, acq, heirs=n, self_farming=self_farming).as_dict()
                out.append({"sale_basis": sale_label, "acquisition_basis": acq_label, **r})
    return out
