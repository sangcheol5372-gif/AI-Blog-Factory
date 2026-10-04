# 군산 신관동 토지 매각 보고서 파이프라인

```
[1] 자료수집 ✅  →  [2] 분석  →  [3] 기초 용역보고서(실무자)  →  [4] 과장 검토  →  [5] 부장 검토 → 제출
```

## 대상 필지 (전북 군산시 신관동, 도시지역/자연녹지)
408-5, 409-3, 410-2, 423-3, 579 — 기준시가 합계 268,102,300원 / 평가액 507,565,000 ~ 563,000,000원.
세부 값은 `config/parcels.toml`.

## 1단계: 자료 수집

| 종류 | 출처 | 키 | 신뢰도 |
|---|---|---|---|
| `law` | 국가법령정보센터 — 법령 14종 + 군산시 도시계획 조례 | `LAW_OC` | primary |
| `land` | VWorld — 필지별 토지이용계획·토지특성(지목·면적·도로접면)·개별공시지가 | `VWORLD_KEY` | primary |
| `trade` | 국토부 토지 매매 실거래가 — 군산시 최근 36개월 | `DATA_GO_KR_KEY` | primary |
| `news` | Google News RSS — 현대차 새만금, 농지법 개정 등 | 불필요 | secondary |
| `manual` | `data/manual/` 에 직접 넣은 파일 | 불필요 | primary / user |

뉴스는 `secondary`(보도 내용)로 분류됩니다. 이후 검토 단계에서는 1차 출처로 확인된 내용만 보고서에 사실로 쓸 수 있습니다.

### 실행
```bash
cd land-report
cp .env.example .env        # 키 입력
python3 -m landreport collect            # 전체
python3 -m landreport collect news law   # 일부
python3 -m landreport status
python3 -m unittest discover -s tests -t .
```
Python 3.11 이상, 외부 패키지 없음. 결과는 `data/raw/<종류>/*.json`(출처 URL·수집시각·해시 포함)과 `data/index.sqlite` 에 저장됩니다. API 키는 저장할 때 `***` 로 가려집니다.
