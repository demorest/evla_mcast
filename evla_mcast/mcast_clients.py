from __future__ import print_function, division, absolute_import, unicode_literals
from builtins import bytes, dict, object, range, map, input, str
from future.utils import itervalues, viewitems, iteritems, listvalues, listitems
from io import open
from future.moves.urllib.request import urlopen

import os
import struct
import logging
import asyncore
import socket
import contextlib
from lxml import etree, objectify

import logging
logger = logging.getLogger('mcast_clients')

_install_dir = os.path.abspath(os.path.dirname(__file__))
_xsd_dir = os.path.join(_install_dir, 'xsd')

_obs_xsd = os.path.join(_xsd_dir, 'observe', 'Observation.xsd')
_obs_parser = objectify.makeparser(schema=etree.XMLSchema(file=_obs_xsd))

_vci_xsd = os.path.join(_xsd_dir, 'vci', 'vciRequest.xsd')
_vci_parser = objectify.makeparser(schema=etree.XMLSchema(file=_vci_xsd))

_ant_xsd = os.path.join(_xsd_dir, 'observe', 'AntennaPropertyTable.xsd')
_ant_parser = objectify.makeparser(schema=etree.XMLSchema(file=_ant_xsd))

_delay_xsd = os.path.join(_xsd_dir, 'vci', 'vciStbDelayModel.xsd')
_delay_parser = objectify.makeparser(schema=etree.XMLSchema(file=_delay_xsd))

# Based on code originally in async_mcast.py by PD and S. Ransom
#
# These classes set up networking, and parse incoming Obs and VCI
# documents into appropriate data structures.

class McastClient(asyncore.dispatcher):
    """Generic class to receive the multicast XML docs."""

    def __init__(self, group, port, name=""):
        asyncore.dispatcher.__init__(self)
        self.name = name
        self.group = group
        self.port = port
        addrinfo = socket.getaddrinfo(group, None)[0]
        self.create_socket(addrinfo[0], socket.SOCK_DGRAM)
        self.set_reuse_addr()
        self.bind(('', port))
        mreq = socket.inet_pton(addrinfo[0], addrinfo[4][0]) + struct.pack('=I', socket.INADDR_ANY)
        self.socket.setsockopt(socket.IPPROTO_IP,
                               socket.IP_ADD_MEMBERSHIP, mreq)
        self.read = None
        logger.debug('%s listening on group=%s port=%d' % (self.name,
                     self.group, self.port))

    def handle_connect(self):
        logger.debug('connect %s group=%s port=%d' % (self.name,
                     self.group, self.port))

    def handle_close(self):
        logger.debug('close %s group=%s port=%d' % (self.name,
                     self.group, self.port))

    def writeable(self):
        return False

    def handle_read(self):
        self.read = self.recv(100000)
        logger.debug('read ' + self.name + ' ' + self.read.decode('utf-8'))
        try:
            self.parse()
        except Exception:
            logger.exception("error handling '%s' message" % self.name)

    def handle_error(self, type, val, trace):
        logger.error('unhandled exception: ' + repr(val))


class ObsClient(McastClient):
    """Receives Observation XML.

    If the controller input is given, the controller.add_obs(obs) method will
    be called for every document received.

    If use_configUrl is true, the VCI will be retrieved from the url given
    in the Observation document, parsed, and controller.add_vci(vci) will
    be called if a controller exists.
    """

    def __init__(self, controller=None, use_configUrl=True):
        McastClient.__init__(self, '239.192.3.2', 53001, 'obs')
        self.controller = controller
        self.use_configUrl = use_configUrl

    def parse(self):
        obs = objectify.fromstring(self.read, parser=_obs_parser)
        logger.info("Read obs configId={0}, seq={1}, t={2}"
                    .format(obs.attrib['configId'], obs.attrib['seq'], obs.attrib['startTime']))
        logger.debug('Obs data structure:\n' + objectify.dump(obs))

        if self.use_configUrl:
            url = obs.attrib['configUrl']
            logger.info("Retrieving vci from {0}".format(url))
            try:
                with contextlib.closing(urlopen(url)) as uo:
                    vciread = uo.read()
                logger.debug('Retrieved vci {0}'.format(vciread))
                vci = objectify.fromstring(vciread, parser=_vci_parser)
                logger.debug('VCI data structure:\n' + objectify.dump(vci))
                if self.controller is not None:
                    self.controller.add_vci(vci)
            except Exception as e:
                logger.warn("Error retrieving VCI from {0}. {1}"
                            .format(url, e))

        if self.controller is not None:
            self.controller.add_obs(obs)


class AntClient(McastClient):
    """Receives AntennaProperties XML.

    If the controller input is given, the controller.add_ant(ant) method will
    be called for every document received.
    """

    def __init__(self, controller=None):
        McastClient.__init__(self, '239.192.3.1', 53000, 'ant')
        self.controller = controller

    def parse(self):
        result = objectify.fromstring(self.read, parser=_ant_parser)
        logger.info("Read ant datasetId={0}"
                    .format(result.attrib['datasetId']))

        if self.controller is not None:
            self.controller.add_ant(result)
        logger.debug('Ant data structure:\n{0}'.format(objectify.dump(result)))

class DelayClient(McastClient):
    """Recieves EVLA delay model XML for a single StB.
    
    Will call the controller.add_delay() method when received.
    """

    # There are 128 ports in use for the different antenna/IFs
    # port number = 53500 + ant_num*4 + if_num
    # ant_num is the "ea" number; (0 is unused)
    # if_num (0,1,2,3) == (A,C,B,D)
    # for 3-bit 0=A1C1, 1=B1D1, 2=A2C2, 3=B2D2

    def __init__(self, antenna, ifid, controller=None):
        try:
            antenna = antenna.lstrip('ea')
        except AttributeError:
            # not a string
            pass
        ant_id = int(antenna)
        # ifif accept strings?  will anyone use it?
        port = 53500 + 4*ant_id + ifid
        McastClient.__init__(self, '239.192.3.5', port, 'del')
        self.controller = controller

    def parse(self):
        result = objectify.fromstring(self.read, parser=_delay_parser)
        # maybe this should be debug?
        logger.info("Read delay model idString={0} seq={1} t0={2}"
                .format(result.attrib['idString'], result.attrib['sequenceNum'], result.attrib['t0']))

        if self.controller is not None:
            self.controller.add_delay(result)

        logger.debug('Delay data structure:\n{0}'.format(objectify.dump(result)))

# TODO make a class that handles all 128 delay connections

# This is how these would be used in a program.  Note that no controller
# is passed, so the only action taken here is to print log messages when
# each XML document comes in.
if __name__ == '__main__':
    logging.basicConfig(format="%(asctime)-15s %(levelname)8s %(message)s",
                       level=logging.DEBUG)
    ant_client = AntClient()
    obs_client = ObsClient()
    del_client = DelayClient('ea01',0)
    try:
        asyncore.loop()
    except KeyboardInterrupt:
        # Just exit without the trace barf on control-C
        logger.info('got SIGINT, exiting')
