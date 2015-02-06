import re
import html2text

from string import Template


def parse_datajson_entry(datajson, package, defaults):
    package["title"] = (defaults.get("Title Prefix") + ' ' +datajson.get("title", defaults.get("Title"))).strip()
    package["notes"] = html2text.html2text(datajson.get("description", defaults.get("Notes")))
    if not hasattr(datajson.get("keyword"), '__iter__'):
        package["tags"] = [{"name": t} for t in
                           datajson.get("keyword").split(",") if t.strip() != ""]
    else:
        package["tags"] = [{"name": t} for t in datajson.get("keyword")]
    #package["groups"] = [{"name": g} for g in
    #                     defaults.get("Groups",
    #                         [])]  # the complexity of permissions makes this useless, CKAN seems to ignore
    #package["organization"] = datajson.get("organization", defaults.get("Organization"))

    #extra(package, "Date Updated", datajson.get("modified"))
    #{'value': u'2014-12-11T22:42:37.741Z', 'key': 'Date Released'}
    #extra(package, "Date Released", datajson.get("issued"))

    if 'http://creativecommons.org/licenses/by/3.0/au' in datajson.get("license"):
        package['license_id'] = 'cc-by'
    #spatial: "146.9998,-41.5046,147.2943,-41.2383"

    package["data_state"] = "active"
    package['jurisdiction'] = "Commonwealth"
    package['spatial_coverage'] = datajson.get("spatial","GA1")
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

    package['contact_point'] =  datajson.get("contactPoint", "data.gov@finance.gov.au")
    package['temporal_coverage_from'] = datajson.get("issued")
    package['temporal_coverage_to'] = datajson.get("modified")
    package['update_freq'] = 'asNeeded'
    package["url"] = datajson.get("landingPage", datajson.get("webService", datajson.get("accessURL")))
    package["resources"] = []
    for d in datajson.get("distribution", []):
        for k in ("accessURL", "webService"):
            if d.get(k, "").strip() != "":
                r = {
                "url": d[k],
                "format": normalize_format(d.get("format", "Query Tool" if k == "webService" else "Unknown")),
                }
                extra(r, "Language", d.get("language"))
                extra(r, "Size", d.get("size"))

                # work-around for Socrata-style formats array
                try:
                    r["format"] = normalize_format(d["formats"][0]["label"])
                except:
                    pass

                r["name"] = r["format"]

                package["resources"].append(r)


def extra(package, key, value):
    if not value or len(value) == 0: return
    package.setdefault("extras", []).append({"key": key, "value": value})


def normalize_format(format):
    # Format should be a file extension. But sometimes Socrata outputs a MIME type.
    format = format.lower()
    m = re.match(r"((application|text)/(\S+))(; charset=.*)?", format)
    if m:
        if m.group(1) == "text/plain": return "Text"
        if m.group(1) == "application/zip": return "ZIP"
        if m.group(1) == "application/vnd.ms-excel": return "XLS"
        if m.group(1) == "application/x-msaccess": return "Access"
        return "Other"
    if format == "text": return "Text"
    return format.upper()  # hope it's one of our formats by converting to upprecase

