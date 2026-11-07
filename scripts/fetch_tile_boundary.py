#!/usr/bin/env python3
"""Fetch an OSM administrative city boundary by relation ID from Nominatim."""
import argparse
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--relation',type=int,required=True)
    ap.add_argument('--name',required=True)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    url=f'https://nominatim.openstreetmap.org/lookup?osm_ids=R{args.relation}&format=json&polygon_geojson=1&addressdetails=0'
    request=Request(url,headers={'User-Agent':'borodianka-map-static-tiles/1.0 (https://github.com/truephp/borodianka-map)',
        'Accept':'application/json','Accept-Language':'uk'})
    error=None
    for attempt in range(4):
        try:
            with urlopen(request,timeout=90) as response:
                result=json.load(response)
            break
        except Exception as exc:
            error=exc
            time.sleep(3*(attempt+1))
    else:
        raise RuntimeError(f'Nominatim lookup failed: {error}')
    if len(result)!=1:
        raise ValueError(f'Expected 1 OSM relation, got {len(result)}')
    item=result[0]
    if int(item.get('osm_id',-1))!=args.relation or item.get('osm_type')!='relation':
        raise ValueError('OSM relation ID mismatch')
    if args.name.casefold() not in (item.get('display_name') or '').casefold():
        raise ValueError('OSM relation is not the requested city: '+str(item.get('display_name')))
    geometry=item.get('geojson')
    if geometry is None or geometry.get('type') not in ('Polygon','MultiPolygon'):
        raise ValueError('OSM relation has no polygon boundary')
    from shapely.geometry import shape
    polygon=shape(geometry)
    if not polygon.is_valid or polygon.is_empty:
        raise ValueError('Administrative boundary is not valid')
    lon_min,lat_min,lon_max,lat_max=polygon.bounds
    if not (33<lon_min<36 and 33<lon_max<36 and 47<lat_min<50 and 47<lat_max<50):
        raise ValueError(f'Suspicious city bounds: {polygon.bounds}')
    output={'type':'FeatureCollection','features':[{'type':'Feature',
        'properties':{'id':args.relation,'name':args.name,'source':'OpenStreetMap'},
        'geometry':geometry}]}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(output,ensure_ascii=False)+'\n',encoding='utf-8')
    print(f'Loaded {args.name}, relation {args.relation}, area {polygon.area:.5f} square degrees, bounds {polygon.bounds}')

if __name__=='__main__':
    main()
