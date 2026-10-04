"""사용법:
    python -m landreport collect            # 전체 수집
    python -m landreport collect news law   # 일부만
    python -m landreport status             # 수집 현황·최근 오류
    python -m landreport analyze            # 2단계 분석 → data/analysis/analysis.{json,md}
"""
import argparse

from .analysis import build
from .collectors import land, laws, manual, news, trades
from .config import DATA_DIR, load_settings
from .store import Store

COLLECTORS = {
    "law": laws.collect,
    "land": land.collect,
    "trade": trades.collect,
    "news": news.collect,
    "manual": manual.collect,
}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="landreport")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect", help="자료 수집")
    c.add_argument("only", nargs="*", help=f"수집할 종류: {', '.join(COLLECTORS)} (생략 시 전체)")
    sub.add_parser("status", help="수집 현황")
    sub.add_parser("analyze", help="2단계 분석")
    args = ap.parse_args(argv)

    unknown = set(getattr(args, "only", [])) - set(COLLECTORS)
    if unknown:
        ap.error(f"알 수 없는 종류: {', '.join(sorted(unknown))}")

    store = Store(DATA_DIR)
    if args.cmd == "analyze":
        a = build.build(load_settings(), store)
        j, md = build.write(a, DATA_DIR / "analysis")
        print(f"분석 완료: {md}\n데이터 공백 {len(a['gaps'])}건")
        for g in a["gaps"]:
            print("  -", g)
        return
    if args.cmd == "collect":
        settings = load_settings()
        for name in args.only or COLLECTORS:
            print(COLLECTORS[name](settings, store).line())
    print("\n수집 현황 (종류 / 신뢰도 / 건수)")
    for row in store.summary():
        print("  ", *row)
    errors = store.recent_errors(10)
    if errors:
        print("\n최근 오류")
        for at, source, title, err in errors:
            print(f"   {at} [{source}] {title}: {err[:150]}")


if __name__ == "__main__":
    main()
