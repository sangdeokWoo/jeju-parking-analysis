"""
제주 주차 수요-공급 공백 분석 + 지도 -> web/jeju_parking_gap.html, web/data/gap_ranking.csv

공급: 전국주차장정보표준데이터 제주 공영주차장의 '주차면 수' (web/data/parking_std.csv)
수요: 읍면동 유동인구 (web/data/demand_emd.csv) — 2017~2020, 방법론·대용 지표
       ※ 현재값·관광객 포함 수요는 '제주_읍면동 유동인구' 오픈API(활용신청 키)로 교체 가능

지표
  주차면당 유동인구 = 유동인구 총량 / 주차면 수   (높을수록 수요 대비 공급 부족 = 혼잡 위험)
  고양시 프로젝트의 '편의점 1곳당 세대수'와 같은 발상.
  공영주차장 면수 0 -> '공영주차장 없음'으로 별도 표기.

실행: python web/scripts/prep_data.py && python web/scripts/prep_demand.py
      && python web/scripts/gap_analysis.py
"""
import csv
import json
from pathlib import Path

import folium
import numpy as np
import shapely
from branca.colormap import LinearColormap
from pyproj import Transformer
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data'
TO_M = Transformer.from_crs(4326, 5179, always_xy=True)
FONT = "'Noto Sans KR', -apple-system, 'Segoe UI', sans-serif"
TT = (f"font-family:{FONT};font-size:12px;background:#1e293b;color:#e2e8f0;"
      "border:none;border-radius:6px;padding:8px 12px;")
ESRI = ('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/'
        'World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}')


def norm(name):
    return name.strip().replace('일동', '1동').replace('이동', '2동').replace('삼동', '3동')


def main():
    with open(DATA / 'parking_std.csv', encoding='utf-8-sig', newline='') as f:
        parking = list(csv.DictReader(f))
    with open(DATA / 'demand_emd.csv', encoding='utf-8-sig', newline='') as f:
        demand = {r['dong']: r for r in csv.DictReader(f)}
    fc = json.loads((DATA / 'jeju_emd.geojson').read_text(encoding='utf-8'))
    geoms = [shape(f['geometry']) for f in fc['features']]
    for g in geoms:
        shapely.prepare(g)
    pts = shapely.points([[float(p['lon']), float(p['lat'])] for p in parking])
    spaces = np.array([int(p['spaces']) for p in parking])

    caps = np.zeros(len(geoms), int)
    nlot = np.zeros(len(geoms), int)
    assigned = np.zeros(len(pts), bool)
    for i, g in enumerate(geoms):
        hit = shapely.contains(g, pts) & ~assigned
        caps[i] = spaces[hit].sum()
        nlot[i] = hit.sum()
        assigned |= hit

    rows = []
    for i, f in enumerate(fc['features']):
        name = norm(f['properties']['name'])
        d = demand.get(name)
        total = int(d['total']) if d else 0
        vis = int(d['visitors']) if d else 0
        sp = int(caps[i])
        strain = round(total / sp, 1) if sp else None        # 주차면당 유동인구
        f['properties'].update(
            dong=f['properties']['name'], gu=f['properties']['gu'],
            lots=int(nlot[i]), spaces=sp,
            total=total, visitors=vis,
            vis_share=round(100 * vis / total, 1) if total else 0,
            strain=strain, no_public=(sp == 0 and total > 0),
            matched=bool(d))
        rows.append(f['properties'])

    rank = sorted(
        [r for r in rows if r['total'] > 0],
        key=lambda r: (-1 if r['no_public'] else 0, -(r['strain'] or 0)))

    with open(DATA / 'gap_ranking.csv', 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['rank', 'gu', 'dong', 'lots', 'spaces', 'floating_pop', 'visitors',
                    'visitor_share_%', 'persons_per_space', 'no_public_parking'])
        for k, r in enumerate(rank, 1):
            w.writerow([k, r['gu'], r['dong'], r['lots'], r['spaces'], r['total'],
                        r['visitors'], r['vis_share'],
                        '' if r['strain'] is None else r['strain'], 'Y' if r['no_public'] else ''])

    # ── 지도 ──
    m = folium.Map(location=[33.38, 126.55], zoom_start=11, tiles=ESRI,
                   attr='Tiles &copy; Esri', control_scale=True)
    m.get_root().header.add_child(folium.Element(
        '<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700&display=swap" rel="stylesheet">'))
    strains = [r['strain'] for r in rows if r['strain']]
    vmax = float(np.percentile(strains, 90))
    cmap = LinearColormap(['#0b2b26', '#2a9d8f', '#e9c46a', '#e76f51'],
                          vmin=0, vmax=vmax, caption='주차면당 유동인구 (높을수록 공급 부족)')

    def style(f):
        p = f['properties']
        if p['no_public']:
            return {'fillColor': '#7f1d1d', 'fillOpacity': 0.8, 'color': '#ef4444', 'weight': 1.5}
        if p['strain'] is None:
            return {'fillColor': '#334155', 'fillOpacity': 0.3, 'color': 'rgba(255,255,255,0.15)', 'weight': 1}
        return {'fillColor': cmap(min(p['strain'], vmax)), 'fillOpacity': 0.65,
                'color': 'rgba(255,255,255,0.25)', 'weight': 1}

    folium.GeoJson(
        fc, name='주차 공급 부족도 (행정동)', style_function=style,
        highlight_function=lambda f: {'weight': 2.5, 'color': '#38bdf8'},
        tooltip=folium.GeoJsonTooltip(
            fields=['dong', 'gu', 'lots', 'spaces', 'total', 'vis_share', 'strain'],
            aliases=['행정동', '시', '공영주차장', '주차면 수', '유동인구 지수',
                     '방문인구 비중(%)', '주차면당 유동인구'], style=TT),
    ).add_to(m)
    cmap.add_to(m)

    grp = folium.FeatureGroup(name='공영주차장 (원 크기=주차면 수)', show=True)
    for p in parking:
        sp = int(p['spaces'])
        folium.CircleMarker(
            [float(p['lat']), float(p['lon'])], radius=1.5 + (sp ** 0.5) / 5, weight=0,
            fill=True, fill_color='#38bdf8', fill_opacity=0.7,
            tooltip=f"{p['name']} · {sp}면").add_to(grp)
    grp.add_to(m)
    folium.LayerControl(collapsed=True).add_to(m)

    def strain_txt(r):
        return '공영없음' if r['no_public'] else format(r['strain'], ',.0f')

    top = ''.join(
        f'<div style="display:flex;justify-content:space-between;margin-bottom:3px">'
        f'<span>{k}. {r["dong"]} <span style="color:#64748b">{r["gu"]}</span></span>'
        f'<span style="color:#e76f51">{strain_txt(r)}</span></div>'
        for k, r in enumerate(rank[:6], 1))
    total_spaces = sum(int(p['spaces']) for p in parking)
    panel = f"""
<div style="position:fixed;top:12px;left:56px;z-index:1000;width:310px;
  background:rgba(10,14,20,0.95);border:1px solid rgba(255,255,255,0.08);border-radius:12px;
  padding:16px 18px;font-family:{FONT};color:#e2e8f0;font-size:12px;line-height:1.55;
  box-shadow:0 8px 32px rgba(0,0,0,0.6)">
  <div style="font-size:10px;letter-spacing:2px;color:#e76f51;margin-bottom:6px">JEJU PARKING · GAP</div>
  <div style="font-size:16px;font-weight:700;margin-bottom:8px">제주 주차 수요-공급 공백</div>
  <div style="font-size:11px;color:#94a3b8;margin-bottom:10px">
    공급: 공영주차장 <b>{total_spaces:,}면</b> · 수요: 읍면동 유동인구.
    지표 = <b>주차면당 유동인구</b>(높을수록 부족).</div>
  <div style="font-size:10px;color:#e76f51;letter-spacing:1px;margin-bottom:4px">공급 부족 상위 6 (주차면당 유동인구)</div>
  {top}
  <div style="border-top:1px solid rgba(255,255,255,0.08);margin-top:8px;padding-top:8px;color:#94a3b8;font-size:11px">
    <span style="color:#7f1d1d">■</span> 공영주차장 없음 &nbsp; <span style="color:#e76f51">■</span> 부족 &nbsp; <span style="color:#2a9d8f">■</span> 여유<br>
    수요 데이터는 2017~2020 유동인구(방법론 대용). 최신·관광객 포함 수요는
    제주 읍면동 유동인구 <b>오픈API</b>로 교체하면 됩니다. 일도1동은 경계 미제공으로 제외.
  </div>
</div>"""
    m.get_root().html.add_child(folium.Element(panel))
    out = ROOT / 'jeju_parking_gap.html'
    m.save(out)
    print(f'[OK] {out.name}  (행정동 {len(rows)}개, 수요매칭 {sum(1 for r in rows if r["matched"])}개)')
    print('공급 부족 상위 8:')
    for k, r in enumerate(rank[:8], 1):
        print(f'  {k}. {r["gu"]} {r["dong"]}  주차면 {r["spaces"]:>4}  '
              f'유동인구 {r["total"]:>11,}  주차면당 {strain_txt(r)}')


if __name__ == '__main__':
    main()
