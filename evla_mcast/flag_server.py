from future.moves.urllib.parse import urlparse, urlunparse, urlencode
from future.moves.urllib.request import urlopen
from future.moves.urllib.error import HTTPError

import os
from lxml import etree, objectify

_install_dir = os.path.abspath(os.path.dirname(__file__))
_xsd_dir = os.path.join(_install_dir, 'xsd')
_antflagger_xsd = os.path.join(_xsd_dir, 'AntFlaggerMessage.xsd')
_antflagger_parser = objectify.makeparser(
        schema=etree.XMLSchema(file=_antflagger_xsd))

_flaghost = 'mchammer.evla.nrao.edu'
_antpath = 'evla-mcaf-production/dataset'

class FlagServer:
    def __init__(self, host=_flaghost, path=_antpath):
        self.host = host
        self.path = path

    def url(self, datasetId, startTime=None, endTime=None):
        """Returns the base url for the given data set."""
        # TODO fix up to use urlencode, urlunparse
        query = '?'
        if startTime is not None:
            query += 'startTime={0}&'.format(startTime)
        if endTime is not None:
            query += 'endTime={0}'.format(endTime)
        url = 'https://{0}/{1}/{2}/flags{3}'.format(
                self.host, self.path, datasetId, query)
        return url

    def _read(self, datasetId, startTime=None, endTime=None):
        """Query the server and return lxml.objectified response"""
        url = self.url(datasetId, startTime, endTime)
        xml = urlopen(url).read()
        response = objectify.fromstring(xml, parser=_antflagger_parser)
        return response
    
    def flagged_ants(self, datasetId, startTime, endTime=None):
        """Returns a list of flagged antennas for the given dataset, and
        start and end times (MJD)."""
        if endTime is None:
            endTime = startTime
        flags = self._read(datasetId, startTime, endTime)
        try:
            ants = sorted(set([f.attrib['antennas'] for f in flags.flag]))
        except AttributeError:
            # No flags
            ants = []
        return ants
