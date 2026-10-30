#!/usr/bin/env python3
"""Prepare an offline Thames centreline derived from OS Open Rivers.

Source: OS Open Rivers (© Crown copyright and database right 2026),
made available under the Open Government Licence v3.
Service: https://services.arcgis.com/qHLhLQrcvEnxjtPr/arcgis/rest/services/OS_OpenRivers/FeatureServer/0
OS product: https://www.ordnancesurvey.co.uk/products/os-open-rivers

OS Open Rivers maps approximate watercourse CENTRELINES, not exact riverbanks.
Fail closed if the query or downstream geometry validation cannot be completed.
"""
import json
import math
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from shapely.geometry import LineString, shape
from shapely.ops import linemerge, unary_union

ENDPOINT="https://services.arcgis.com/qHLhLQrcvEnxjtPr/arcgis/rest/services/OS_OpenRivers/FeatureServer/0/query"
PARAMS={
    "where":"name1 LIKE '%Thames%' OR name2 LIKE '%Thames%' OR form = 'tidalRiver'",
    "geometry":"-0.65,51.25,0.45,51.74",
    "geometryType":"esriGeometryEnvelope",
    "spatialRel":"esriSpatialRelIntersects",
    "inSR":"4326",
    "outSR":"4326",
    "outFields":"*",
    "f":"geojson",
    "returnGeometry":"true",
    "returnZ":"false",
    "returnM":"false",
    "resultRecordCount":"2000",
    "geometryPrecision":"6",
}

def main():
    request=Request(ENDPOINT+"?"+urlencode(PARAMS),headers={"User-Agent":"LostInLondon/1.0 (OS Open Rivers attribution in source)"})
    with urlopen(request, timeout=75) as response:
        payload=json.load(response)
    if payload.get("error"):
        raise RuntimeError("ArcGIS query failed: "+str(payload["error"]))
    features=payload.get("features",[])
    if len(features)<3 or len(features)>=2000:
        raise ValueError("Unexpected OS Open Rivers feature count: "+str(len(features)))
    lines=[]
    for feature in features:
        if not feature.get("geometry"):
            continue
        g=shape(feature["geometry"])
        if g.geom_type=="LineString":
            lines.append(g)
        elif g.geom_type=="MultiLineString":
            lines.extend(g.geoms)
    if not lines:
        raise ValueError("No Thames lines returned")
    merged=linemerge(unary_union(lines))
    routes=list(merged.geoms) if hasattr(merged,"geoms") else [merged]
    routes.sort(key=lambda line:line.length,reverse=True)
    for i, g in enumerate(routes[:18]):
        print(f'Component {i}: {len(g.coords)} vertices, lon {g.bounds[0]:.5f}..{g.bounds[2]:.5f}, lat {g.bounds[1]:.5f}..{g.bounds[3]:.5f}, length {g.length:.5f}',flush=True)
    river=routes[0]
    if not isinstance(river,LineString):
        raise ValueError("Missing continuous Thames centreline")
    if river.coords[0][0]>river.coords[-1][0]:
        river=LineString(list(river.coords)[::-1])
    simplified=river.simplify(0.00010,preserve_topology=True)
    coords=[[round(y,6),round(x,6)] for x,y in simplified.coords]
    lo=min(c[1] for c in coords)
    hi=max(c[1] for c in coords)
    if lo > -0.42 or hi < 0.20 or len(coords) < 80:
        raise ValueError(f"Insufficient Thames extent, vertices={len(coords)}, longitude={lo}..{hi}, segments={len(features)}")
    # Extrapolated closure points are only outside the game's London envelope.
    def edge(to_x,first):
        (y1,x1),(y2,x2)=(coords[0],coords[1]) if first else (coords[-2],coords[-1])
        slope=(y2-y1)/(x2-x1) if abs(x2-x1)>0.00001 else 0
        y=(y1+(to_x-x1)*slope) if first else (y2+(to_x-x2)*slope)
        return [round(max(51.30,min(51.65,y)),6),to_x]
    coords=[edge(-0.70,True),*coords,edge(0.70,False)]
    js=(
        "/* Ordnance Survey OS Open Rivers (generalised centreline), OGL v3.\n"
        " * Contains OS data © Crown copyright and database right 2026.\n"
        " * Generated from ArcGIS OS_OpenRivers service; see scripts/generate_thames.py.\n"
        " */\n"
        "window.LONDON_THAMES_OS_CENTRELINE = "+json.dumps(coords,separators=(",",":"))+";\n"
    )
    Path("thames-geometry.js").write_text(js,encoding="utf-8")
    print(f"Generated {len(coords)} positions, {len(features)} segments, longitude {lo}..{hi}")

if __name__=="__main__":
    main()
