from ckan.lib.munge import munge_title_to_name

import re
import requests

from string import Template
from ckanext.datajson.harvester_base import DatasetHarvesterBase


def parse_datajson_entry(datajson, package, harvester_config):
    # Notes:
    # * the data.json field "identifier" is handled by the harvester
    package["title"] = (harvester_config["defaults"].get("Title Prefix", '') + ' ' +
                        datajson.get("title", harvester_config["defaults"].get("Title"))).strip()
    package["notes"] = datajson.get("description", package.get("notes"))
    package["author"] = datajson.get("publisher", package.get("author"))
    package["url"] = datajson.get("landingPage",
                                  datajson.get("webService", datajson.get("accessURL", package.get("url"))))

    package["groups"] = [{"name": g} for g in
                         harvester_config["defaults"].get("Groups",
                                                          [])]  # the complexity of permissions makes this useless, CKAN seems to ignore

    # custom license handling
    if 'http://creativecommons.org/licenses/by/3.0/au' in datajson.get("license", ''):
        package['license_id'] = 'cc-by'
    elif 'http' in datajson.get("license", ''):
        license_text = requests.get(datajson.get("license")).content
        if 'opendata.arcgis.com' in license_text:
            try:
                license_text = requests.get(license_text).json()['description']
            except:
                license_text = datajson.get("license")
            package['citation'] = license_text
            package['license_id'] = 'other'
        if 'http://creativecommons.org/licenses/by/3.0/au' in license_text:
            package['license_id'] = 'cc-by'
        if 'http://creativecommons.org/licenses/by/4.0/' in license_text:
            package['license_id'] = 'cc-by-4.0'

    package["data_state"] = "active"
    package['jurisdiction'] = harvester_config["defaults"].get("jurisdiction", "Commonwealth")
    package['spatial_coverage'] = datajson.get("spatial", "GA1")
    if not package['spatial_coverage'] or package['spatial_coverage'] == "":
        package['spatial_coverage'] = "GA1"
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
            package['contact_point'] = datajson.get("contactPoint")['hasEmail'].replace('mailto:', '')
        else:
            package['contact_point'] = datajson.get("contactPoint")
    if 'contact_point' not in package or package['contact_point'] == '' or not isinstance(package['contact_point'], basestring):
        package['contact_point'] = "data.gov@finance.gov.au"

    package['temporal_coverage_from'] = datajson.get("issued")
    package['temporal_coverage_to'] = datajson.get("modified")
    package['update_freq'] = 'asNeeded'

    # backwards-compatibility for files from Socrata
    if isinstance(datajson.get("keyword"), basestring):
        package["tags"] = [{"name": munge_title_to_name(t)} for t in
                           datajson.get("keyword").split(",") if t.strip() != ""]
    # field is provided correctly as an array...
    elif isinstance(datajson.get("keyword"), list):
        package["tags"] = [{"name": munge_title_to_name(t)} for t in
                           datajson.get("keyword") if t.strip() != ""]

    # harvest_portals
    if harvester_config["defaults"].get("harvest_portal"):
        extra(package, "harvest_portal", harvester_config["defaults"], "harvest_portal")
        package['extras'].append(
            {"key": 'harvest_url', "value": datajson.get('landingPage') or datajson.get('identifier')})

    # Add resources.
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


def extra(package, ckan_key, datajson, datajson_fieldname):
    value = datajson.get(datajson_fieldname)
    if not value: return
    DatasetHarvesterBase.set_extra(package, ckan_key, value)


def normalize_format(format, raise_on_unknown=False):
    # Format should be a file extension. But sometimes Socrata outputs a MIME type.
    if format is None:
        if raise_on_unknown: raise ValueError()
        return "Unknown"
    format = format.lower()
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
        if raise_on_unknown: raise ValueError()  # caught & ignored by caller
        return "Other"
    if format == "text": return "Text"
    if raise_on_unknown and "?" in format: raise ValueError()  # weird value we should try to filter out; exception is caught & ignored by caller
    return format.upper()  # hope it's one of our formats by converting to upprecase
