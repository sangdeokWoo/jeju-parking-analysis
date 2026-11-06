"""
제주 '수요' 데이터(유동인구) 준비 -> web/data/demand_emd.csv

출처: 공공데이터포털 '제주특별자치도_주제3_상권분석을 위한 유동인구에 따른 카드 매출액 변화
      데이터 활용_매쉬업결과' (제주빅데이터센터). 읍면동 × 년월 × 업종 × 성별 구조이며
      거주/근무/방문 인구는 (년월, 읍면동)별로 동일하게 반복된다.
      ※ 시점 2017-01~2020-04 (40개월). 현재값은 아니며 '방법론·수요 대용' 용도.
         최신 수요는 '제주_읍면동 단위 내국인/외국인 유동인구' 오픈API(2026-10, 활용신청 키 필요)로 교체.

유동인구 = 01~24시 정각 측정 인구의 월 합계(머문시간/60분). 절대 인원수가 아니라 상대 체류량 지표.

행정동명 숫자 표기를 OSM 경계와 맞춘다(일동→1동, 이동→2동).

실행: (Downloads에 매쉬업 CSV가 있는 상태에서) python web/scripts/prep_demand.py
"""
import csv
import glob
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data'
DOWNLOADS = Path.home() / 'Downloads'
PATTERN = '제주특별자치도_주제3_상권분석*매쉬업결과*.csv'


def norm(name):
    return (name.strip().replace('일동', '1동').replace('이동', '2동').replace('삼동', '3동'))


def main():
    hits = sorted(glob.glob(str(DOWNLOADS / PATTERN)))
    if not hits:
        raise SystemExit(f'매쉬업 CSV를 찾을 수 없습니다: {DOWNLOADS / PATTERN}')
    src = hits[-1]
    rows = list(csv.reader(open(src, encoding='cp949', newline='')))
    h = [x.strip() for x in rows[0]]
    ix = {c: h.index(c) for c in ['년월', '읍면동명', '거주인구', '근무인구', '방문인구']}

    seen = {}
    for r in rows[1:]:
        if len(r) <= max(ix.values()):
            continue
        key = (r[ix['년월']], r[ix['읍면동명']].strip())
        if key in seen:
            continue
        try:
            seen[key] = (float(r[ix['거주인구']]), float(r[ix['근무인구']]), float(r[ix['방문인구']]))
        except ValueError:
            continue

    agg = defaultdict(lambda: ([], [], []))
    months = set()
    for (ym, dong), vals in seen.items():
        months.add(ym)
        for k in range(3):
            agg[norm(dong)][k].append(vals[k])

    out = DATA / 'demand_emd.csv'
    with open(out, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['dong', 'residents', 'workers', 'visitors', 'total'])
        for dong in sorted(agg):
            res, wrk, vis = (round(statistics.mean(agg[dong][k])) for k in range(3))
            w.writerow([dong, res, wrk, vis, res + wrk + vis])
    print(f'수요 {len(agg)}개 행정동 -> {out.relative_to(ROOT.parent)}  '
          f'(기간 {min(months)}~{max(months)}, {len(months)}개월, 출처 {Path(src).name})')


if __name__ == '__main__':
    main()
