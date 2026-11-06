"""
제주 주차장 '공급' 지도 -> web/jeju_parking_supply.html

데이터: 전국주차장정보표준데이터(공공데이터포털 15012896)에서 추출한
        제주 공영주차장 (web/data/parking_std.csv) — 주차면 수(spaces) 포함.
레이어: 읍면동별 '주차면 수 밀도' 코로플레스 + 주차장 마커(원 크기=주차면 수, 색=요금).

실행: python web/scripts/prep_data.py && python web/scripts/make_supply_map.py
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


def main():
    with open(DATA / 'parking_std.csv', encoding='utf-8-sig', newline='') as f:
        parking = list(csv.DictReader(f))
    fc = json.loads((DATA / 'jeju_emd.geojson').read_text(encoding='utf-8'))
    geoms = [shape(f['geometry']) for f in fc['features']]
    for g in geoms:
        shapely.prepare(g)
    pts = shapely.points([[float(p['lon']), float(p['lat'])] for p in parking])
    spaces = np.array([int(p['spaces']) for p in parking])

    counts = np.zeros(len(geoms), int)
    caps = np.zeros(len(geoms), int)
    assigned = np.zeros(len(pts), bool)
    for i, g in enumerate(geoms):
        hit = shapely.contains(g, pts) & ~assigned
        counts[i] = hit.sum()
        caps[i] = spaces[hit].sum()
        assigned |= hit
    for i, f in enumerate(fc['features']):
        gm = shapely.transform(geoms[i], lambda c: np.column_stack(TO_M.transform(c[:, 0], c[:, 1])))
        area = gm.area / 1e6
        f['properties'].update(count=int(counts[i]), spaces=int(caps[i]),
                               area_km2=round(area, 2),
                               density=round(caps[i] / area, 1) if area else 0)

    m = folium.Map(location=[33.38, 126.55], zoom_start=11, tiles=ESRI,
                   attr='Tiles &copy; Esri', control_scale=True)
    m.get_root().header.add_child(folium.Element(
        '<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700&display=swap" rel="stylesheet">'))

    dens = [f['properties']['density'] for f in fc['features']]
    cmap = LinearColormap(['#0b2b26', '#145a4f', '#2a9d8f', '#e9c46a'],
                          vmin=0, vmax=max(dens), caption='주차 공급 밀도 (주차면/km²)')
    folium.GeoJson(
        fc, name='읍면동별 주차면 수 밀도',
        style_function=lambda f: {'fillColor': cmap(f['properties']['density']),
                                  'fillOpacity': 0.6, 'color': 'rgba(255,255,255,0.25)', 'weight': 1},
        highlight_function=lambda f: {'weight': 2.5, 'color': '#38bdf8'},
        tooltip=folium.GeoJsonTooltip(
            fields=['name', 'gu', 'count', 'spaces', 'area_km2', 'density'],
            aliases=['읍면동', '시', '주차장 수', '주차면 수', '면적(km²)', '밀도(면/km²)'], style=TT),
    ).add_to(m)
    cmap.add_to(m)

    grp = folium.FeatureGroup(name='주차장 (원 크기=주차면 수, 색=요금)', show=True)
    for p in parking:
        sp = int(p['spaces'])
        fee = p.get('fee', '')
        color = '#f59e0b' if fee == '유료' else ('#a78bfa' if fee == '혼합' else '#38bdf8')
        folium.CircleMarker(
            [float(p['lat']), float(p['lon'])], radius=2 + (sp ** 0.5) / 4,
            weight=0.5, color='#0f172a', fill=True, fill_color=color, fill_opacity=0.8,
            tooltip=f"{p['name']}<br>주차면 {sp}면 · {fee or '구분없음'}<br>{p.get('type', '')}").add_to(grp)
    grp.add_to(m)
    folium.LayerControl(collapsed=True).add_to(m)

    ranked = sorted(fc['features'], key=lambda f: f['properties']['density'])
    low = ''.join(
        f'<div style="display:flex;justify-content:space-between;margin-bottom:3px">'
        f'<span>{f["properties"]["name"]} <span style="color:#64748b">{f["properties"]["gu"]}</span></span>'
        f'<span style="color:#f87171">{f["properties"]["density"]:.1f}</span></div>'
        for f in ranked[:6])
    panel = f"""
<div style="position:fixed;top:12px;left:56px;z-index:1000;width:300px;
  background:rgba(10,14,20,0.95);border:1px solid rgba(255,255,255,0.08);border-radius:12px;
  padding:16px 18px;font-family:{FONT};color:#e2e8f0;font-size:12px;line-height:1.55;
  box-shadow:0 8px 32px rgba(0,0,0,0.6)">
  <div style="font-size:10px;letter-spacing:2px;color:#2a9d8f;margin-bottom:6px">JEJU PARKING · SUPPLY</div>
  <div style="font-size:16px;font-weight:700;margin-bottom:8px">제주 공영주차장 공급 지도</div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:10px">
    <div><div style="color:#64748b;font-size:10px">공영주차장</div>
      <div style="font-size:17px;font-weight:700">{len(parking):,}개소</div></div>
    <div><div style="color:#64748b;font-size:10px">주차면 수 합계</div>
      <div style="font-size:17px;font-weight:700">{int(spaces.sum()):,}면</div></div>
  </div>
  <div style="font-size:10px;color:#f87171;letter-spacing:1px;margin-bottom:4px">공급 밀도 하위 6 (주차면/km²)</div>
  {low}
  <div style="border-top:1px solid rgba(255,255,255,0.08);margin-top:8px;padding-top:8px;color:#94a3b8;font-size:11px">
    출처: 전국주차장정보표준데이터(2026) 제주 공영주차장. <b>주차면 수</b> 반영.<br>
    <span style="color:#38bdf8">●</span> 무료 <span style="color:#f59e0b">●</span> 유료 <span style="color:#a78bfa">●</span> 혼합.
    다음 단계: <b>읍면동 유동인구</b>와 결합해 수요 대비 공백 분석.
  </div>
</div>"""
    m.get_root().html.add_child(folium.Element(panel))

    out = ROOT / 'jeju_parking_supply.html'
    m.save(out)
    print(f'[OK] {out.name}  주차장 {len(parking)}개소 / {int(spaces.sum()):,}면')
    print('공급밀도 하위5:', [(f['properties']['name'], f['properties']['density']) for f in ranked[:5]])


if __name__ == '__main__':
    main()
