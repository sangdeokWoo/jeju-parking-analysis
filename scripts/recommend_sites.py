"""
제주 공영주차장 신설/증설 우선순위 + 후보 위치 추천 -> web/jeju_parking_recommend.html,
web/data/recommend_sites.csv

방법 (고양시 최대 커버리지 모형의 축소판; 수요가 행정동 단위라 후보는 행정동 내부에서 선정)
  1) 공백 분석(gap_analysis)의 '주차면당 유동인구'로 행정동 우선순위를 매긴다.
     - 공영주차장 0곳(유동인구 있음) → '신설' 최우선
     - 주차면당 유동인구가 높은 곳 → '증설'
  2) 우선순위 상위 행정동마다 '후보 지점'을 1곳 제시:
     행정동 안 100m 격자점 중 기존 공영주차장에서 가장 먼 지점(= 주차 사각지대).
     ※ 수요가 행정동 단위라 지점 자체는 '거리 기준' 휴리스틱이다. 사용 가능한 수요가
       격자/건물 단위로 올라오면(오픈API 등) 수요가중 최대 커버리지로 고도화한다.

실행: python web/scripts/gap_analysis.py && python web/scripts/recommend_sites.py
"""
import csv
import json
from pathlib import Path

import folium
import numpy as np
import shapely
from pyproj import Transformer
from scipy.spatial import cKDTree
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data'
TO_M = Transformer.from_crs(4326, 5179, always_xy=True)
TO_LL = Transformer.from_crs(5179, 4326, always_xy=True)
FONT = "'Noto Sans KR', -apple-system, 'Segoe UI', sans-serif"
TT = (f"font-family:{FONT};font-size:12px;background:#1e293b;color:#e2e8f0;"
      "border:none;border-radius:6px;padding:8px 12px;")
ESRI = ('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/'
        'World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}')
TOP_N = 8
CELL = 100   # 후보 탐색 격자 (m)


def to_m(lon, lat):
    x, y = TO_M.transform(np.asarray(lon, float), np.asarray(lat, float))
    return np.column_stack([np.atleast_1d(x), np.atleast_1d(y)])


def main():
    with open(DATA / 'parking_std.csv', encoding='utf-8-sig', newline='') as f:
        parking = list(csv.DictReader(f))
    with open(DATA / 'gap_ranking.csv', encoding='utf-8-sig', newline='') as f:
        gap = list(csv.DictReader(f))
    fc = json.loads((DATA / 'jeju_emd.geojson').read_text(encoding='utf-8'))
    by_name = {f['properties']['name']: f for f in fc['features']}

    # 주거지역(OSM landuse=residential) — 후보를 시가지 안으로 제한(산·오름 배제)
    res = shape(json.loads((DATA / 'jeju_residential.geojson').read_text(encoding='utf-8'))['geometry'])
    res_m = shapely.transform(res, lambda c: to_m(c[:, 0], c[:, 1]))
    shapely.prepare(res_m)

    S = to_m([p['lon'] for p in parking], [p['lat'] for p in parking])
    tree = cKDTree(S)

    # 우선순위: 공영없음 먼저, 그다음 주차면당 유동인구 큰 순 (gap_ranking 정렬 그대로)
    priority = gap[:TOP_N]
    sites = []
    for g in priority:
        feat = by_name.get(g['dong'])
        if feat is None:
            continue
        poly = shape(feat['geometry'])
        polym = shapely.transform(poly, lambda c: to_m(c[:, 0], c[:, 1]))
        x0, y0, x1, y1 = polym.bounds
        gx, gy = np.meshgrid(np.arange(x0, x1, CELL), np.arange(y0, y1, CELL))
        G = np.column_stack([gx.ravel(), gy.ravel()])
        shapely.prepare(polym)
        gp = shapely.points(G)
        in_res = shapely.contains(polym, gp) & shapely.contains(res_m, gp)   # 행정동 ∩ 주거지역
        if in_res.any():
            G, note = G[in_res], ''
            dist, _ = tree.query(G)             # 주거지 내 기존 공영주차장에서 가장 먼 지점
            j = int(dist.argmax())
        else:
            # 주거지 데이터 없는 동(외딴섬 등) → 중심점을 후보로, 산지 오판 방지
            G = np.array([list(polym.representative_point().coords)[0]])
            dist, _ = tree.query(G)
            j, note = 0, '주거지데이터없음·행정동중심'
        lon, lat = TO_LL.transform(G[j, 0], G[j, 1])
        sites.append({
            'rank': g['rank'], 'gu': g['gu'], 'dong': g['dong'],
            'action': '신설' if g['no_public_parking'] == 'Y' else '증설',
            'cur_lots': g['lots'], 'cur_spaces': g['spaces'],
            'floating_pop': g['floating_pop'], 'visitor_share_%': g['visitor_share_%'],
            'persons_per_space': g['persons_per_space'] or '',
            'cand_lat': round(lat, 6), 'cand_lon': round(lon, 6),
            'dist_to_nearest_m': int(round(dist[j])), 'note': note,
        })

    with open(DATA / 'recommend_sites.csv', 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(sites[0].keys()))
        w.writeheader()
        w.writerows(sites)

    # ── 지도 ──
    m = folium.Map(location=[33.38, 126.55], zoom_start=11, tiles=ESRI,
                   attr='Tiles &copy; Esri', control_scale=True)
    m.get_root().header.add_child(folium.Element(
        '<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700&display=swap" rel="stylesheet">'))

    pr_names = {s['dong'] for s in sites}
    folium.GeoJson(
        fc, name='우선순위 행정동',
        style_function=lambda f: ({'fillColor': '#e76f51', 'fillOpacity': 0.35,
                                   'color': '#e76f51', 'weight': 1.5}
                                  if f['properties']['name'] in pr_names
                                  else {'fillColor': '#1e293b', 'fillOpacity': 0.15,
                                        'color': 'rgba(255,255,255,0.12)', 'weight': 0.5}),
        tooltip=folium.GeoJsonTooltip(fields=['name', 'gu'], aliases=['행정동', '시'], style=TT),
    ).add_to(m)

    g_lot = folium.FeatureGroup(name='기존 공영주차장', show=True)
    for p in parking:
        folium.CircleMarker([float(p['lat']), float(p['lon'])], radius=1.5, weight=0,
                            fill=True, fill_color='#64748b', fill_opacity=0.6).add_to(g_lot)
    g_lot.add_to(m)

    g_rec = folium.FeatureGroup(name='추천 후보 지점', show=True)
    for s in sites:
        folium.Circle([s['cand_lat'], s['cand_lon']], radius=400, color='#38bdf8',
                      weight=1.5, dash_array='5 5', fill=True, fill_opacity=0.05).add_to(g_rec)
        folium.Marker(
            [s['cand_lat'], s['cand_lon']],
            icon=folium.DivIcon(html=(
                f'<div style="width:24px;height:24px;border-radius:50%;background:#38bdf8;'
                f'color:#0f172a;font:700 12px {FONT};display:flex;align-items:center;'
                f'justify-content:center;border:2px solid #fff;transform:translate(-12px,-12px)">'
                f'{s["rank"]}</div>')),
            tooltip=(f'<b>#{s["rank"]} {s["gu"]} {s["dong"]} · {s["action"]}</b><br>'
                     f'현재 공영 {s["cur_lots"]}곳 / {s["cur_spaces"]}면 · 방문비중 {s["visitor_share_%"]}%<br>'
                     f'후보: 기존 주차장에서 {s["dist_to_nearest_m"]:,}m<br>'
                     f'<a href="https://map.kakao.com/link/map/추천{s["rank"]},{s["cand_lat"]},{s["cand_lon"]}" '
                     f'target="_blank">카카오맵</a>'),
        ).add_to(g_rec)
    g_rec.add_to(m)
    folium.LayerControl(collapsed=True).add_to(m)

    rows = ''.join(
        f'<div style="display:flex;justify-content:space-between;margin-bottom:3px">'
        f'<span>{s["rank"]}. {s["dong"]} <span style="color:#64748b">{s["action"]}</span></span>'
        f'<span style="color:#38bdf8">{s["dist_to_nearest_m"]:,}m</span></div>'
        for s in sites)
    panel = f"""
<div style="position:fixed;top:12px;left:56px;z-index:1000;width:300px;
  background:rgba(10,14,20,0.95);border:1px solid rgba(255,255,255,0.08);border-radius:12px;
  padding:16px 18px;font-family:{FONT};color:#e2e8f0;font-size:12px;line-height:1.55;
  box-shadow:0 8px 32px rgba(0,0,0,0.6)">
  <div style="font-size:10px;letter-spacing:2px;color:#38bdf8;margin-bottom:6px">JEJU PARKING · RECOMMEND</div>
  <div style="font-size:16px;font-weight:700;margin-bottom:8px">공영주차장 신설·증설 우선순위</div>
  <div style="font-size:11px;color:#94a3b8;margin-bottom:10px">
    공백 분석 상위 {len(sites)}개 행정동. 후보 지점 = 행정동 안에서 기존 공영주차장과
    가장 먼 곳(주차 사각지대).</div>
  {rows}
  <div style="border-top:1px solid rgba(255,255,255,0.08);margin-top:8px;padding-top:8px;color:#94a3b8;font-size:11px">
    <span style="color:#38bdf8">●</span> 추천 후보(400m 반경) · <span style="color:#64748b">●</span> 기존 공영주차장<br>
    후보 지점은 거리 기준 휴리스틱. 격자·건물 단위 수요가 생기면 수요가중 최적화로 고도화.
  </div>
</div>"""
    m.get_root().html.add_child(folium.Element(panel))
    out = ROOT / 'jeju_parking_recommend.html'
    m.save(out)
    print(f'[OK] {out.name}')
    for s in sites:
        print(f'  #{s["rank"]} {s["gu"]} {s["dong"]} · {s["action"]}  '
              f'(현재 {s["cur_spaces"]}면, 방문비중 {s["visitor_share_%"]}%, '
              f'후보 거리 {s["dist_to_nearest_m"]:,}m)')


if __name__ == '__main__':
    main()
