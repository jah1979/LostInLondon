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
    # Retain individual authoritative links, preserving their OS flow
    # direction, rather than joining/discarding river sections at branch nodes.
    import re
    app=Path("app.js").read_text(encoding="utf-8")
    match=re.search(r"const THAMES_CENTRELINE = (\[[^\n]*\]);",app)
    if not match:
        raise RuntimeError("Coarse reference line missing; cannot validate official Thames links")
    reference=json.loads(match.group(1))
    guide=LineString([(lon,lat) for lat,lon in reference])
    thames_links=[]
    for f in features:
        p=f.get("properties") or {}
        geom=f.get("geometry")
        if not geom:
            continue
        g=shape(geom)
        sections=[g] if g.geom_type=="LineString" else list(g.geoms) if g.geom_type=="MultiLineString" else []
        name=((p.get("name1") or "")+" "+(p.get("name2") or "")).lower()
        is_named="thames" in name
        for part in sections:
            # The guide is only a corridor filter, NEVER the final geometry.
            # Limit unnamed tidal tributaries; named Thames links get a wider margin.
            if part.distance(guide) > (0.027 if is_named else 0.012):
                continue
            geom=part.simplify(0.000035,preserve_topology=True)
            points=[[round(y,6),round(x,6)] for x,y in geom.coords]
            if len(points)>1:
                thames_links.append(points)
    if len(thames_links)<50:
        raise ValueError(f"Too few official Thames links: {len(thames_links)}")
    # Every OS Open Rivers link is digitised in water flow direction.
    # Left bank is conventionally north of the Thames, right bank south.
    def side_of(lat,lon):
        scale_lon=111.2*math.cos(lat*math.pi/180)
        scale_lat=111.2
        x=lon*scale_lon;y=lat*scale_lat
        nearest=float('inf'); sign=0
        for points in thames_links:
            for (ay,ax),(by,bx) in zip(points,points[1:]):
                ax*=scale_lon;bx*=scale_lon
                ay*=scale_lat;by*=scale_lat
                dx=bx-ax;dy=by-ay; length=dx*dx+dy*dy
                t=max(0,min(1,((x-ax)*dx+(y-ay)*dy)/length)) if length else 0
                d=math.hypot(x-ax-t*dx,y-ay-t*dy)
                if d<nearest:
                    nearest=d
                    sign=dx*(y-ay)-dy*(x-ax)
        return "river" if nearest < .05 else "north" if sign>=0 else "south"
    fixtures=[
        ("Camden",51.5393,-.1426,"north"),
        ("Westminster",51.5021,-.1261,"north"),
        ("Hackney",51.5441,-.0557,"north"),
        ("Canary Wharf",51.505,-.020,"north"),
        ("Brixton",51.4627,-.1145,"south"),
        ("Tooting",51.4282,-.1676,"south"),
        ("Greenwich",51.4826,-.0077,"south"),
        ("South Bank",51.503,-.1166,"south"),
        ("Waterloo",51.503,-.114,"south"),
        ("O2 Peninsula",51.5028,.0034,"south"),
        ("Woolwich",51.4898,.0659,"south"),
        ("Battersea",51.472,-.164,"south"),
        ("Richmond",51.4613,-.3037,"south"),
        ("Wimbledon",51.4214,-.2064,"south"),
    ]
    errors=[]
    for name,lat,lon,expected in fixtures:
        actual=side_of(lat,lon)
        print(f"Validate {name}: {actual} expected={expected}",flush=True)
        if actual!=expected:
            errors.append(name)
    if errors:
        raise ValueError("Official OS-link classification requires review at: "+", ".join(errors))
    west=min(p[1] for link in thames_links for p in link)
    east=max(p[1] for link in thames_links for p in link)
    if west > -.50 or east < .28:
        raise ValueError(f"Official Thames coverage too small: {west} to {east}")
    js=(
        "/* Source: Ordnance Survey OS Open Rivers (generalised links, digitised with flow). OGL v3.\n"
        " * Contains OS data © Crown copyright and database right 2026.\n"
        " * Compiled by scripts/generate_thames.py from publicly accessible OS_OpenRivers layer.\n"
        " * Approximate centreline geometry, NOT surveyed river-bank polygons.\n"
        " */\n"
        "window.LONDON_THAMES_OS_LINKS = "+json.dumps(thames_links,separators=(",",":"))+";\n"
    )
    Path("thames-geometry.js").write_text(js,encoding="utf-8")
    print(f"Generated {len(thames_links)} Thames links, OS source longitude {west}..{east}; {len(features)} source features")

if __name__=="__main__":
    main()
