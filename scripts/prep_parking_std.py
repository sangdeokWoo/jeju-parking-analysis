"""
공급 데이터 준비 -> web/data/parking_std.csv

출처: 공공데이터포털 '전국주차장정보표준데이터' (ID 15012896, 국토교통부, 무료, 반기 갱신).
      2022년 저장소 파일(이름·좌표만)과 달리 '주차구획수(주차면 수)'와 요금·구분을 포함.
      공공데이터포털에서 CSV를 내려받아 Downloads 폴더에 둔 상태에서 실행.
      (파일명: 전국주차장정보표준데이터.csv, cp949 인코딩)

제주 범위(위도 33.0~33.65, 경도 126.0~127.0)로 필터링.

실행: python web/scripts/prep_parking_std.py
"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data'
SRC = Path.home() / 'Downloads' / '전국주차장정보표준데이터.csv'
COLS = ['주차장명', '주차장구분', '소재지도로명주소', '소재지지번주소',
        '주차구획수', '요금정보', '위도', '경도', '관리기관명']


def main():
    if not SRC.exists():
        raise SystemExit(f'표준데이터 CSV가 없습니다: {SRC}\n'
                         '공공데이터포털 15012896에서 CSV를 내려받아 Downloads에 두세요.')
    rows = list(csv.reader(open(SRC, encoding='cp949', newline='')))
    h = [x.strip() for x in rows[0]]
    ix = {c: h.index(c) for c in COLS}
    out = []
    for r in rows[1:]:
        if len(r) <= max(ix.values()):
            continue
        addr = r[ix['소재지도로명주소']] or r[ix['소재지지번주소']]
        if '제주' not in addr:
            continue
        try:
            lat, lon = float(r[ix['위도']]), float(r[ix['경도']])
        except ValueError:
            continue
        if not (33.0 <= lat <= 33.65 and 126.0 <= lon <= 127.0):
            continue
        try:
            cap = int(float(r[ix['주차구획수']]))
        except ValueError:
            cap = 0
        out.append({'name': r[ix['주차장명']].strip(), 'type': r[ix['주차장구분']].strip(),
                    'spaces': cap, 'fee': r[ix['요금정보']].strip(),
                    'lat': lat, 'lon': lon, 'addr': addr.strip(),
                    'org': r[ix['관리기관명']].strip()})
    dst = DATA / 'parking_std.csv'
    with open(dst, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['name', 'type', 'spaces', 'fee', 'lat', 'lon', 'addr', 'org'])
        w.writeheader()
        w.writerows(out)
    print(f'제주 공영주차장 {len(out)}개소 / 주차면 {sum(o["spaces"] for o in out):,}면 -> {dst.relative_to(ROOT.parent)}')


if __name__ == '__main__':
    main()
