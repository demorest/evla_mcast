from __future__ import print_function, division, absolute_import #, unicode_literals # not casa compatible
from builtins import bytes, dict, object, range, map, input#, str # not casa compatible
from future.utils import itervalues, viewitems, iteritems, listvalues, listitems
from io import open
from future.moves.urllib.parse import urlparse, urlunparse, urlencode
from future.moves.urllib.request import urlopen
from future.moves.urllib.error import HTTPError

import os.path
import json
from lxml import etree, objectify
#import numpy as np
import logging
logger = logging.getLogger(__name__)
logger.setLevel(20)

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
                _flaghost, _antpath, datasetId, query)
        return url
    
    def get_ant_flags(self, datasetId, startTime=None, endTime=None):
        """Returns a list of flagged antennas for the given dataset, and
        start and end times (MJD).  Defaults to current time if time is
        not specified"""
        pass


def getblflags(datasetId, blarr, startTime=None, endTime=None):
    """ Call antenna flag server for given datasetId and return
    flags per baseline. Optional input are startTime and endTime.
    blarr is array of baselines to be flagged (see rfpipe state.blarr)
    that defines structure of returned flag array.
    """

    # set up query to flag server
    query = '?'
    if startTime is not None:
        query += 'startTime={0}&'.format(startTime)
    if endTime is not None:
        query += 'endTime={0}'.format(endTime)
    url = 'https://{0}/{1}/{2}/flags{3}'.format(_flaghost, _antpath, datasetId,
                                                query)

    logger.info("Querying flag server: " + url)

    # call server and parse response
    response_xml = urlopen(url).read()
    response = objectify.fromstring(response_xml, parser=_antflagger_parser)

    # find bad ants and baselines
    badants = set(sorted([int(flag.attrib['antennas'].lstrip('ea'))
                          for flag in response.findall('flag')]))

    flags = np.ones(len(blarr), dtype=int)
    for badant in badants:
        flags *= (badant != blarr).prod(axis=1)

    return flags
