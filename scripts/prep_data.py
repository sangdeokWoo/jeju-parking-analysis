"""
제주 공급(주차장) 데모용 입력 데이터 준비.

출력
  web/data/parking.csv        주차장 좌표 (name, lat, lon, city) — 저장소의 2022 제주시/서귀포시 파일 병합
  web/data/jeju_emd.geojson   제주 43개 읍면동 경계 (name, gu) — OSM/Overpass

주의
  - 2022 주차장 파일에는 '주차면 수'가 없다. 이번 데모는 '공급 위치/밀도'까지만 본다.
    주차면 수가 포함된 전국주차장정보표준데이터(공공데이터포털 15012896)로 교체하면
    '수용 능력 대비 수요'까지 분석할 수 있다. (web/README.md 참고)
  - 경계 원본: web/data/_osm_jeju_raw.json (Overpass 응답).

실행: python web/scripts/prep_data.py
"""
import csv
import json
from pathlib import Path

from shapely.geometry import LineString, mapping
from shapely.ops import polygonize, unary_union

ROOT = Path(__file__).resolve().parent.parent          # web/
REPO = ROOT.parent                                      # 저장소 루트
DATA = ROOT / 'data'
DATA.mkdir(parents=True, exist_ok=True)

PARKING_DIR = REPO / 'data' / 'Jeju parking lot'
PARKING_FILES = {
    '제주시': '제주특별자치도_제주시_주차장정보_20210818_1630391997093_77385.csv',
    '서귀포시': '제주특별자치도_서귀포시_주차장정보_20220425_1650966840250_33855.csv',
}


def read_csv_any(path):
    for enc in ('utf-8-sig', 'cp949', 'euc-kr'):
        try:
            with open(path, encoding=enc, newline='') as f:
                return list(csv.reader(f)), enc
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f'인코딩 판별 실패: {path}')


def prep_parking():
    rows = []
    for city, fname in PARKING_FILES.items():
        data, enc = read_csv_any(PARKING_DIR / fname)
        header = [h.strip() for h in data[0]]
        ix = {k: header.index(k) for k in ('name', 'lat', 'lon')}
        n = 0
        for r in data[1:]:
            if not r or len(r) <= max(ix.values()):
                continue
            try:
                lat, lon = float(r[ix['lat']]), float(r[ix['lon']])
            except ValueError:
                continue
            if not (33.0 <= lat <= 33.65 and 126.0 <= lon <= 127.0):   # 제주 범위
                continue
            rows.append({'name': r[ix['name']].strip(), 'lat': lat, 'lon': lon, 'city': city})
            n += 1
        print(f'  {city}: {n}건 (enc={enc})')
    out = DATA / 'parking.csv'
    with open(out, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['name', 'lat', 'lon', 'city'])
        w.writeheader()
        w.writerows(rows)
    print(f'주차장 {len(rows)}건 -> {out.relative_to(REPO)}')


def ring_polygons(members, role):
    lines = [LineString([(p['lon'], p['lat']) for p in m['geometry']])
             for m in members
             if m.get('type') == 'way' and m.get('role', 'outer') == role
             and len(m.get('geometry', [])) >= 2]
    return list(polygonize(unary_union(lines))) if lines else []


def rel_geom(el):
    members = el.get('members', [])
    outer = ring_polygons(members, 'outer')
    if not outer:
        # role 태그가 없거나 어긋난 경우: 모든 way를 폴리곤화해 가장 큰 조각 사용
        lines = [LineString([(p['lon'], p['lat']) for p in m['geometry']])
                 for m in members
                 if m.get('type') == 'way' and len(m.get('geometry', [])) >= 2]
        polys = list(polygonize(unary_union(lines))) if lines else []
        if not polys:
            return None
        return max(polys, key=lambda g: g.area)
    geom = unary_union(outer)
    inner = ring_polygons(members, 'inner')
    if inner:
        geom = geom.difference(unary_union(inner))
    return geom


def prep_boundary():
    els = json.loads((DATA / '_osm_jeju_raw.json').read_text(encoding='utf-8'))['elements']
    gus = [(e['tags']['name'], rel_geom(e)) for e in els if e['tags'].get('admin_level') == '6']
    feats = []
    for e in els:
        if e['tags'].get('admin_level') != '8':
            continue
        g = rel_geom(e)
        if g is None or g.is_empty:
            continue
        c = g.representative_point()
        gu = next((n for n, gg in gus if gg is not None and gg.contains(c)), '')
        feats.append({'type': 'Feature', 'geometry': mapping(g),
                      'properties': {'name': e['tags']['name'], 'gu': gu}})
    feats.sort(key=lambda f: (f['properties']['gu'], f['properties']['name']))
    out = DATA / 'jeju_emd.geojson'
    out.write_text(json.dumps({'type': 'FeatureCollection', 'features': feats},
                              ensure_ascii=False), encoding='utf-8')
    from collections import Counter
    print(f'읍면동 {len(feats)}개 -> {out.relative_to(REPO)}  {dict(Counter(f["properties"]["gu"] for f in feats))}')


if __name__ == '__main__':
    prep_parking()
    prep_boundary()
