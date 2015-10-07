import re
import html2text
import requests
import csv
import io

from string import Template

vicroadsmeta = {}
def utf_8_encoder(unicode_csv_data):
    for line in unicode_csv_data:
        yield line.encode('utf-8')
def parse_datajson_entry(datajson, package, defaults):
    package["title"] = (defaults.get("Title Prefix", '') + ' ' +
                        datajson.get("title", defaults.get("Title"))).strip()
    if datajson.get("description"):
        package["notes"] = html2text.html2text(datajson.get("description", ' '))
    if not hasattr(datajson.get("keyword"), '__iter__'):
        package["tags"] = [{"name": t} for t in
                           datajson.get("keyword", '').split(",") if t.strip() != ""]
    else:
        package["tags"] = [{"name": t} for t in datajson.get("keyword")]

    if 'http://creativecommons.org/licenses/by/3.0/au' in datajson.get("license",''):
        package['license_id'] = 'cc-by'
    elif 'http' in datajson.get("license", ''):
        license_text = requests.get(datajson.get("license")).content
        if 'opendata.arcgis.com' in license_text:
            license_text = requests.get(license_text).json()['description']
            package['citation'] = license_text
        if 'http://creativecommons.org/licenses/by/3.0/au' in license_text:
            package['license_id'] = 'cc-by'
        if 'http://creativecommons.org/licenses/by/4.0/' in license_text:
            package['license_id'] = 'cc-by-4'

    package["data_state"] = "active"
    package['jurisdiction'] = defaults.get("jurisdiction", "Commonwealth")
    if 'extras' not in package:
        package['extras'] = []
    if defaults.get("harvest_portal"):
        package['extras'].append({"key": 'harvest_portal', "value": defaults.get("harvest_portal")})
        package['extras'].append({"key": 'harvest_url', "value": datajson.get('landingPage') or datajson.get('identifier')})
    package['spatial_coverage'] = datajson.get("spatial", "GA1")
    try:
        bbox = datajson.get("spatial").split(',')
        xmin = float(bbox[0])
        xmax = float(bbox[2])
        ymin = float(bbox[1])
        ymax = float(bbox[3])
        # Construct a GeoJSON extent so ckanext-spatial can register the extent geometry

        # Some publishers define the same two corners for the bbox (ie a point),
        # that causes problems in the search if stored as polygon
        if xmin == xmax or ymin == ymax:
            package['spatial'] = Template('{"type": "Point", "coordinates": [$x, $y]}').substitute(
                x=xmin, y=ymin
            )
        else:
            package['spatial'] = Template('''{"type": "Polygon", "coordinates": [[[$xmin, $ymin], [$xmax, $ymin],
             [$xmax, $ymax], [$xmin, $ymax], [$xmin, $ymin]]]}''').substitute(
                        xmin=xmin, ymin=ymin, xmax=xmax, ymax=ymax)
    except:
        pass

    if "mbox" in datajson:
        package['contact_point'] = datajson.get("mbox")
    if datajson.get("contactPoint"):
        if 'hasEmail' in datajson.get("contactPoint"):
            package['contact_point'] = datajson.get("contactPoint")['hasEmail'].replace('mailto:','')
        else:
            package['contact_point'] = datajson.get("contactPoint")
    if 'contact_point' not in package or package['contact_point'] == '':
        package['contact_point'] = "data.gov@finance.gov.au"
    package['temporal_coverage_from'] = datajson.get("issued")
    package['temporal_coverage_to'] = datajson.get("modified")
    package['update_freq'] = 'asNeeded'
    package["url"] = datajson.get("landingPage", datajson.get("webService", datajson.get("accessURL")))
    package["resources"] = []
    for d in datajson.get("distribution", []):
        for k in ("downloadURL", "accessURL", "webService", "downloadUrl", "accessUrl"):
            if d.get(k, "").strip() != "":
                r = {
                    "url": d[k],
                    "format": normalize_format(d.get("format",
                                                     d.get('mediaType', "Query Tool"
                                                     if k == "webService" else "Unknown"))),
                }
                #extra(r, "Language", d.get("language"))
                #extra(r, "Size", d.get("size"))

                # work-around for Socrata-style formats array
                try:
                    r["format"] = normalize_format(d["formats"][0]["label"])
                except:
                    pass

                r["name"] = d.get('title', r["format"])
                if r["format"].lower() == 'wms':
                    url_parts = datajson.get("webService").split('/')
                    r['wms_layer'] = url_parts[-1]  # last item in the array
                package["resources"].append(r)
    if "vicroadsopendata" in datajson.get("identifier", ""):
        if len(vicroadsmeta) == 0:
            req = requests.get("http://data.vicroads.vic.gov.au/metadata/MetadataCatalogue.csv")
            with io.StringIO(req.text) as csvfile:
                reader = csv.reader(utf_8_encoder(csvfile))
                header = []
                for row in reader:
                    if len(header) == 0:
                        header = row
                    else:
                        data = {}
                        i = 0
                        for col in row:
                            data[header[i]] = col
                            i = i + 1
                        if data['Alternative_Title'].lower() != "":
                            vicroadsmeta[data['Alternative_Title'].lower()] = data
                        if data['Title'].lower() != "":
                            vicroadsmeta[data['Title'].lower()] = data
        package['geo_data'] = "Y"
        package["agency_program"] = "VicRoads"
        package["agency_program_url"] = "https://www.vicroads.vic.gov.au/"
        package["extract"] = " "
        title = datajson.get("title", "").lower()
        if title in vicroadsmeta:
            for r in package["resources"]:
                r['release_date'] = vicroadsmeta[title]["Last_Updated"] \
                                                  or vicroadsmeta[datajson.get("title")]["First_Date_Published"]
            if vicroadsmeta[title]["License"] == 'Internal use only':
                package["private"] = "true"
            package["extract"] = vicroadsmeta[title]["Abstract"] or " "
            package["update_frequency"] = vicroadsmeta[title]["Frequency_of_Updates"]
            package["geo_coverage"] = vicroadsmeta[title]["Geographic_Extent"]

#def extra(package, key, value):
#    if not value or len(value) == 0: return
#    package.setdefault("extras", []).append({"key": key, "value": value})


def normalize_format(format):
    # Format should be a file extension. But sometimes Socrata outputs a MIME type.
    format = format.lower().replace("ogc ","")
    m = re.match(r"((application|text)/(\S+))(; charset=.*)?", format)
    if m:
        result = m.group(1).replace(';', '')
        if result == "text/plain": return "txt"
        if result == "application/zip": return "zip"
        if result == "application/vnd.ms-excel": return "xls"
        if result == "application/x-msaccess": return "mdb"
        if result == "text/csv": return "csv"
        if result == "application/rdf+xml": return "rdf"
        if result == "application/json": return "json"
        if result == "application/xml": return "xml"
        if result == "application/unknown": return "other"
        return "Other"
    if format == "text": return "Text"
    return format.upper()  # hope it's one of our formats by converting to upprecase

