from ckanext.datajson.harvester_base import DatasetHarvesterBase
from ckanext.datajson.harvester_base import log

import urllib2, json


class DataJsonHarvester(DatasetHarvesterBase):
    '''
    A Harvester for /data.json files.
    '''

    HARVESTER_VERSION = "0.9ap"  # increment to force an update even if nothing has changed

    def info(self):
        return {
            'name': 'datajson',
            'title': '/data.json',
            'description': 'Harvests remote /data.json files',
        }

    def load_remote_catalog(self, harvest_job):
        try:
            catalog = json.load(urllib2.urlopen(harvest_job.source.url, None, 90))
        except urllib2.URLError as e:
            log.warn('Failed to fetch %s' % harvest_job.source.url)
            return []
        except ValueError as e:
            log.warn('Failed to parse %s' % harvest_job.source.url)
            return []

        if 'dataset' in catalog:
            return catalog['dataset']
        else:
            return catalog

    def set_dataset_info(self, pkg, dataset, harvester_config):
        from pod_to_package import parse_datajson_entry
        parse_datajson_entry(dataset, pkg, harvester_config)
