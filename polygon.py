from glob import glob
import os
import csv
import traceback
from typing import Dict, List
from shapely.geometry import Polygon, MultiPolygon
import re
import json
from lxml import etree
from shapely.geometry.linestring import LineString
from shapely.geometry.multilinestring import MultiLineString
from shapely.geometry.multipoint import MultiPoint
from shapely.geometry.point import Point

log = print

# filename : tag
SUBTYPE_MAP = {
    "andentopografiflade": "andentopografitype",
    "andentopografipunkt": "andentopografitype",
    }

def main():

    aarhus_polys = []
    with open("aarhus_kommune_polygon_data.txt") as f:
        # MULTIPOLYGON (((575518.74 6243397.64, 575517.86 6243400.14...
        d = f.read()
        for m in re.findall(r"\(\(([\d\. ,]+)\)\)", d):
            mp = []
            for x, y in (x.strip().split(' ') for x in m.split(',')):
                mp.append((float(x), float(y)))
            aarhus_polys.append(Polygon(mp))
        
    aarhus_multi_poly = MultiPolygon(aarhus_polys)

    gml_dir = r"C:\Users\az61622\Aarhus kommune\FNK-Aarhus Stadsarkiv-Digitalt Arkiv - Dokumenter\GeoData\DKstednavneBearbejdedeNohist_GML321_20211205080020"
    gml_files = glob(os.path.join(gml_dir, "*.gml"))

    gml_polys: List[Dict] = []


    for g_file in gml_files:
        soup = etree.parse(g_file)

        filename = os.path.split(g_file)[1]
        print("Parsing", filename)
        filename = os.path.splitext(filename)[0]

        # if any(x in filename for x in ("andentopografi", "landskabsform")):
        #     continue

        count = 0

        for g in soup.iterfind(".//{*}featureMember"):
            geotype = "POLYGON"
            pdata = []
            for tag, sgtype, mgtype, primary in (
                ("posList", "POLYGON", "MULTIPOLYGON", "PolygonPatch"),
                ("posList", "LINESTRING", "MULTILINESTRING", "LineString"),
                ("pos", "POINT", "MULTIPOINT", ""),
            ):
                if primary:
                    if g.find(".//{*}" + primary) is None:
                        continue
                sf = g.findall(".//{*}" + tag)
                if len(sf):
                    geotype = sgtype
                    if len(sf) > 1:
                        geotype = mgtype
                    pdata = sf
                    break

            if not pdata:
                continue

            name = g.find(".//{*}navn_1_skrivemaade").text
            if not name:
                continue

            # print("Parsing", name)
            gp = []
            for p in pdata:
                parsed_p = []
                polys = str(p.text).split(' ')
                x = y = ''
                while polys:
                    i = polys.pop(0)
                    if i == '0':
                        continue
                    if not x:
                        x = i
                    else:
                        y = i
                    if x and y:
                        parsed_p.append((float(x), float(y)))
                        x = y = ''
                gp.append(parsed_p)

            d = {
                'geotype': geotype, # Point, Polygon, MultiPolygon
                # print Polygon object
                'coords': gp,
                'type': filename,
                'objectid': g.find(".//{*}objectid").text,
                'gmlid': g.find(".//{*}gmlid").text,
                'name': name
            }

            d["subtype"] = ""
            subtype_key = SUBTYPE_MAP.get(filename, "")
            t = None
            if subtype_key:
                t = g.find(".//{*}" + subtype_key)
            if t is None:
                # with s
                t = g.find(".//{*}" + f"{filename}stype")
            if t is None:
                # without s
                t = g.find(".//{*}" + f"{filename}type")
            if t is not None:
                d["subtype"] = t.text
            
            gml_polys.append(d)
            count += 1
        
        print("Parsed", count, "locations")
        # free memory
        soup.getroot().clear()

    found = []

    for n, pa in enumerate(gml_polys):
        Shape = None
        MultiShape = None
        if "polygon" in pa['geotype'].lower():
            Shape = Polygon
            MultiShape = MultiPolygon
        elif "point" in pa['geotype'].lower():
            Shape = Point
            MultiShape = MultiPoint
        elif "linestring" in pa['geotype'].lower():
            Shape = LineString
            MultiShape = MultiLineString
        else:
            raise NotImplementedError(pa['geotype'])

        coords = [Shape(c) for c in pa['coords']]
        gml_pa = None
        if len(coords) > 1:
            gml_pa = MultiShape(coords)
        else:
            gml_pa = coords[0]

        for c in coords:
            if aarhus_multi_poly.intersects(c):
                pa['coords'] = str(gml_pa)
                found.append(pa) 
                break

    print("Found", len(found), "places")

    with open('stednavne.json', 'w', encoding="utf-8") as f:
        json.dump(found, f, indent=1, ensure_ascii = False)

    export_csv('stednavne.csv', found)

# export to csv
def export_csv(path, data: List[Dict[str, str]]):
    """
    Export data to a csv
    """
    log("Exporting to CSV...")
    try:
        with open(path, "w", newline='') as f:
            w = csv.DictWriter(f, ["name", "type", "subtype", "gmlid", "objectid", "geotype", "coords"])
            w.writeheader()
            
            # sort by count
            for d in sorted(data, key=lambda x: x["name"]):
                w.writerow(d)

        log(f"Exported CSV to {path}")
    except Exception as e:
        traceback.print_exc()
        raise SystemExit("ERROR: above error occurred during CSV write")