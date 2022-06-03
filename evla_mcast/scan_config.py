from __future__ import print_function, division, absolute_import, unicode_literals
from builtins import bytes, dict, object, range, map, input, str
from future.utils import itervalues, viewitems, iteritems, listvalues, listitems
from io import open

import ast
from lxml import objectify
import os.path

from . import angles
from .mcast_clients import _ant_parser, _vci_parser, _obs_parser

import logging
logger = logging.getLogger(__name__)

# Code heavily based on earlier psrinfo_mcast.py by PD and S. Ransom.
#
# The main point of this part of the code is to take information from
# the vci and obs data structures (which are a literal parsing of the XML
# documents) and return relevant information in a more directly usable
# form for pulsar processing.  This includes picking out subbands that
# are configured to send VDIF to certain IP addresses, and performing
# the relevant sky frequency calculations for each.  Pulsar-related
# intents in the obs XML are parsed to recover the requested processing
# parameters as well.


class ScanConfig(object):
    """ This class defines a complete EVLA observing config,
    which in practice means both a VCI document and OBS document have been
    received.  Quantities relevant for pulsar processing are taken
    from the VCI and OBS and returned."""

    def __init__(self, vci=None, obs=None, ant=None,
                 requires=['obs', 'vci', 'ant', 'stop']):
        """ Sets the documents for a given scan.
        vci, obs, and ant arguments accept filenames or parsed xml string.

        The requires arguments is a list specifying which information is
        required for the ScanConfig to be complete.  It can contain any
        of 'obs', 'vci', 'ant' and 'stop'.  The default is for all
        four to be required.  When all requirements have been filled,
        ScanConfig.is_complete() will return True.
        """

        try:        
            if len(obs):
                logger.debug('Received obs doc')
                with open(obs, 'rb') as fobs:
                    obs = objectify.fromstring(fobs.read(), parser=_obs_parser)
                logger.info('Added obs doc from file {0}'.format(obs))
            if len(vci):
                logger.debug('Received vci doc')
                with open(vci, 'rb') as fvci:
                    vci = objectify.fromstring(fvci.read(), parser=_vci_parser)
                logger.info('Added vci doc from file {0}'.format(obs))
            if len(ant):
                logger.debug('Received ant doc')
                with open(ant, 'rb') as fant:
                    ant = objectify.fromstring(fant.read(), parser=_ant_parser)
                logger.info('Added ant doc from file {0}'.format(ant))
        except (IOError, TypeError):
            logger.debug('Assuming one or more doc was already parsed')

        self.stopTime = None

        self.requires = requires

        self._subscans = []

        self.set_vci(vci)
        self.set_obs(obs)
        self.set_ant(ant)

    def __repr__(self):
        defined = []
        if self.has_obs:
            defined.append('obs')
        if self.has_ant:
            defined.append('ant')
        if self.has_vci:
            defined.append('vci')
        if self.stopTime:
            defined.append('stop')
        return 'ScanConfig with {0} defined'.format(defined)

    @property
    def has_vci(self):
        return self.vci is not None

    @property
    def has_obs(self):
        return self.obs is not None

    @property
    def has_ant(self):
        return self.ant is not None

    def is_complete(self):
        if ('obs' in self.requires) and not self.has_obs:
            return False
        if ('vci' in self.requires) and not self.has_vci:
            return False
        if ('ant' in self.requires) and not self.has_ant:
            return False
        if ('stop' in self.requires) and self.stopTime is None:
            return False
        return True

    def set_vci(self, vci):
        self.vci = vci
        for ss in self._subscans:
            ss.set_vci(vci)

    def set_obs(self, obs):
        self.obs = obs
        if self.obs is None:
            self.intents = {}
        else:
            self.intents = self.parse_intents(obs.intent)

    def set_ant(self, ant):
        self.ant = ant
        for ss in self._subscans:
            ss.set_ant(ant)

    def is_subscan(self, config):
        # Return true if config appears to be a subscan in the same set as
        # this one.
        return (
                (self.datasetId == config.datasetId) and
                (self.configId == config.configId) and
                (self.scanNo == config.scanNo) and
                (self.subscanNo != config.subscanNo)
                )

    def add_subscan(self, obs):
        subconf = ScanConfig(obs=obs,vci=self.vci,ant=self.ant)

        # TODO other stuff that could go here:
        #  - check that subscan properties are consistent with main scan?

        self.update_stopTime(subconf.startTime)

        # Add new subscan to the list
        self._subscans.append(subconf)

    def update_stopTime(self, stopTime):
        # Fill in any missing stop time info both for this scan and all
        # subscans
        was_updated = False
        for ss in self.subscans:
            if ((ss.startTime < stopTime) and
                    ((ss.stopTime is None)
                        or (ss.stopTime > stopTime))):
                ss.stopTime = stopTime
                was_updated = True
        return was_updated

    @property
    def nsubscan(self):
        return 1 + len(self._subscans)

    @property
    def subscans(self):
        # List of all subscans (including first subscan)
        return [self,] + self._subscans

    def subscan(self,subscanNo):
        # Get a specific subscan, by number
        if subscanNo==self.subscanNo: 
            return self
        for sc in self._subscans:
            if subscanNo==sc.subscanNo:
                return sc
        return None

    @staticmethod
    def parse_intents(intents):
        d = {}
        for item in intents:
            k, v = str(item).split("=")
            if v[0] is "'" or v[0] is '"':
                d[k] = ast.literal_eval(v)
                # Or maybe we should just strip quotes?
            else:
                d[k] = v
        return d

    def get_intent(self, key, default=None):
        try:
            return self.intents[key]
        except KeyError:
            return default

    @property
    def configId(self):
        return self.obs.attrib['configId']

    @property
    def datasetId(self):
        return self.obs.attrib['datasetId']

    @property
    def scanId(self):
        return '%s.%d.%d' % (self.datasetId, self.scanNo, self.subscanNo)

    @property
    def scanNo(self):
        return int(self.obs.scanNo)

    @property
    def subscanNo(self):
        return int(self.obs.subscanNo)

    @property
    def observer(self):
        return self.get_intent("ObserverName", "Unknown")

    @property
    def projid(self):
        return self.get_intent("ProjectID", "Unknown")

    @property
    def scan_intent(self):
        return self.get_intent("ScanIntent", "None")

    @property
    def otf(self):
        return self.get_intent("OTF","0") == "1"

    @property
    def otf_rate_ra(self):
        return float(self.get_intent("AntennaRaRate","0").strip('"'))

    @property
    def otf_rate_dec(self):
        return float(self.get_intent("AntennaDecRate","0").strip('"'))

    @property
    def otf_duration(self):
        return float(self.get_intent("DurationOfStripe","0").strip('"'))

    @property
    def otf_source_field(self):
        return self.get_intent("SourceFieldSet","None").strip('"')

    @property
    def nchan(self):
        return int(self.get_intent("PsrNumChan", 32))

    @property
    def npol(self):
        return int(self.get_intent("PsrNumPol", 4))

    @property
    def foldtime(self):
        return float(self.get_intent("PsrFoldIntTime", 10.0))

    @property
    def foldbins(self):
        return int(self.get_intent("PsrFoldNumBins", 2048))

    @property
    def timeres(self):
        return float(self.get_intent("PsrSearchTimeRes", 1e-3))

    @property
    def nbitsout(self):
        return int(self.get_intent("PsrSearchNumBits", 8))

    @property
    def searchdm(self):
        return float(self.get_intent("PsrSearchDM", 0.0))

    @property
    def freqfac(self):
        return float(self.get_intent("PsrSearchFreqFac", 1))

    @property
    def parfile(self):
        return self.get_intent("TempoFileName", None)

    @property
    def calfreq(self):
        return float(self.get_intent("PsrCalFreq", 10.0))

    @property
    def raw_format(self):
        return self.get_intent("PsrRawFormat", "GUPPI")

    @property
    def source(self):
        return str(self.obs.name)
#        return self.obs.name.translate(string.maketrans(' *','__'))  # "AttributeError: no such child: translate"

    @property
    def ra_deg(self):
        return angles.r2d(self.obs.ra)

    @property
    def ra_hrs(self):
        return angles.r2h(self.obs.ra)

    @property
    def ra_str(self):
        return angles.fmt_angle(self.ra_hrs, ":", ":").lstrip('+-')

    @property
    def dec_deg(self):
        return angles.r2d(self.obs.dec)

    @property
    def dec_str(self):
        return angles.fmt_angle(self.dec_deg, ":", ":")

    @property
    def startLST(self):
        return self.obs.startLST * 86400.0

    @property
    def startTime(self):
        try:
            return float(self.obs.attrib["startTime"])
        except AttributeError:
            return 0.0

    #@property
    #def wait_time_sec(self):
    #    if self.startTime==0.0:
    #        return None
    #    else:
    #        return 86400.0*(self.startTime - mjd_now())

    @property
    def seq(self):
        return self.obs.attrib["seq"]

    @property
    def telescope(self):
        return "VLA"

    @property
    def baseBandNames(self):
        return [str(baseBand.attrib['swbbName']) for baseBand 
                in self.vci.stationInputOutput[0].baseBand]

    @property
    def binningPeriod(self):
        bp = {}
        for baseBand in self.vci.stationInputOutput[0].baseBand:
            try:
                if baseBand.binningPeriod is not None:
                    IFid = swbbName_to_IFid(baseBand.swbbName)
                    bp[IFid] = baseBand.binningPeriod
            except AttributeError:
                pass
        return bp

    @property
    def numBins(self):
        nb = {}
        for baseBand in self.vci.stationInputOutput[0].baseBand:
            try:
                if baseBand.phaseBinning[0].numBins is not None:
                    IFid = self.swbbName_to_IFid(baseBand.swbbName)
                    nb[IFid] = baseBand.phaseBinning[0].numBins
            except (AttributeError, IndexError):
                pass
        return nb

    @property
    def listOfStations(self):
        if self.has_vci:
            return [str(s.attrib["name"]) for s in self.vci.listOfStations.station]
        elif self.has_ant:
            return [str(s.attrib["name"]) for s in self.ant.AntennaProperties]
        else:
            return []

    @property
    def numAntenna(self):
        return len(self.listOfStations)

    @property
    def IFids(self):
        """Return a list of IFis from the OBS XML."""
        return [sslo.attrib["IFid"] for sslo in self.obs.sslo]

    def get_sslo(self, IFid):
        """Return the SSLO frequency in MHz for the given IFid.  This will
        correspond to the edge of the baseband.  Uses IFid naming convention
        as in OBS XML."""

        for sslo in self.obs.sslo:
            if sslo.attrib["IFid"] == IFid:
                return float(sslo.freq) # These (xml FloatElement) are in MHz
        return None

    def get_sideband(self, IFid):
        """Return the sideband sense (int; +1 or -1) for the given IFid.
        Uses IFid naming convention as in OBS XML."""

        for sslo in self.obs.sslo:
            if sslo.attrib["IFid"] == IFid:
                return int(sslo.attrib["Sideband"])  # 1 or -1
        return None

    def get_receiver(self, IFid):
        """Return the receiver name for the given IFid.
        Uses IFid naming convention as in OBS XML."""
        for sslo in self.obs.sslo:
            if sslo.attrib["IFid"] == IFid:
                return sslo.attrib["Receiver"]
        return None

    @staticmethod
    def swbbName_to_IFid(swbbName):
        """Converts values found in the VCI baseBand.swbbName property to
        matching values as used in the OBS sslo.IFid property.

        swbbNames are like AC_8BIT, A1C1_3BIT, etc.
        IFids are like AC, AC1, etc."""

        conversions = {
                'A1C1': 'AC1',
                'A2C2': 'AC2',
                'B1D1': 'BD1',
                'B2D2': 'BD2'
                }

        (bbname, bits) = swbbName.split('_')

        if bbname in conversions:
            return conversions[bbname]

        return bbname

    def get_subbands(self, only_vdif=False, match_ips=[]):
        """Return a list of SubBand objects for all matching subbands.
        Inputs:

          only_vdif: if True, return only subbands with VDIF output enabled.
                     (default: False)

          match_ips: Only return subbands with VDIF output routed to one of
                     the specified IP addresses.  If empty, all subbands
                     are returned.  non-empty match_ips implies only_vdif
                     always.
                     (default: [])
        """

        # TODO: raise an exception, or just return empty list?
        if not self.is_complete():
            raise RuntimeError("Complete configuration not available: "
                               "has_vci={0}, has_obs={1}, has_ant={2}, "
                               "stopTime={3}"
                               .format(self.has_vci, self.has_obs,
                                       self.has_ant, self.stopTime))

        subs = []

        for baseBand in self.vci.stationInputOutput[0].baseBand:
            swbbName = str(baseBand.attrib["swbbName"])
            IFid = self.swbbName_to_IFid(swbbName)
            for subBand in baseBand.subBand:
                if len(match_ips) or only_vdif:
                    # Need to get at vdif elements
                    # Not really sure what more than 1 summedArray means..
                    for summedArray in subBand.summedArray:
                        vdif = summedArray.vdif
                        if vdif:
                            if len(match_ips):
                                if (vdif.aDestIP in match_ips) or \
                                   (vdif.bDestIP in match_ips):
                                    # IPs match, add to list
                                    subs += [SubBand(subBand, self, IFid, vdif), ]
                            else:
                                # No IP list specified, keep all subbands
                                subs += [SubBand(subBand, self, IFid, vdif), ]
                else:
                    # No VDIF or IP list given, just keep everything
                    subs += [SubBand(subBand, self, IFid, vdif=None), ]

        return subs

    def get_antennas(self):
        """Return a list of antenna objects for this scan.  These will
        appear in the correct order relevant to the ordering of data
        in the BDF."""
        # TODO check ordering.  Is sorting done by 'widarID' or 'name'
        # or 'sid' (in listOfStations) in practice these seem to be similar.
        ants = []
        for a in self.ant.AntennaProperties:
            if a.attrib["name"] in self.listOfStations:
                ants += [Antenna(a), ]
        return sorted(ants, key=lambda a: int(a.widarID))


class SubBand(object):
    """This class defines relevant info for real-time pulsar processing
    of a single subband.  Most info is contained in the VCI subBand element,
    some is copied out for convenience.  Also the corresponding sky frequency
    is calculated, this depends on the baseBand properties, and LO settings
    (the latter only available in the OBS XML document).  Note, all frequencies
    coming out of this class are in MHz.

    Inputs:
        subBand: The VCI subBand element
        config:  The original ScanConfig object
        vdif:    The summedArray.vdif VCI element (optional)
        IFid:    The IF identification (as in OBS xml)
    """

    def __init__(self, subBand, config, IFid, vdif=None):
        self.IFid = IFid
        self.swIndex = int(subBand.attrib["swIndex"])
        self.sbid = int(subBand.attrib["sbid"])
        self.vdif = vdif
        # Note, all frequencies are in MHz here
        self.bw = 1e-6 * float(subBand.attrib["bw"])
        self.bb_center_freq = 1e-6 * float(subBand.attrib["centralFreq"]) # within the baseband
        ## The (original) infamous frequency calculation, copied here
        ## for posterity:
        ##self.skyctrfreq = self.bandedge[bb] + 1e-6 * self.sideband[bb] * \
        ##                  self.subbands[isub].centralFreq
        self.sky_center_freq = config.get_sslo(IFid) \
                             + config.get_sideband(IFid) * self.bb_center_freq
        self.receiver = config.get_receiver(IFid)

        # Infomation about the correlations below here

        # Note, this will fail if the subBand.pp elements are not
        # labelled with correct id attributes.  I belive this is
        # tested by CM.
        npp = len(subBand.polProducts.pp)
        self.pp = [None, ] * npp
        for pp in subBand.polProducts.pp:
            idx = int(pp.attrib['id'])-1
            self.pp[idx] = str(pp.attrib['correlation'])

        # Number of channels is specified separately for each pp.  I
        # do not think it is allowed for this to vary, so we will make
        # this a single value.
        # TODO: Also look for CBE frequency integration?
        self.spectralChannels = int(subBand.polProducts.pp[0].attrib['spectralChannels'])

        # Time resolution in seconds, two are specified.  The first is
        # the time step coming out of the correlator HW.  The second is
        # the final value recorded by the cbe.
        if IFid in list(config.binningPeriod.keys()):
            self.hw_time_res = \
                    1e-6 * config.binningPeriod[IFid] \
                    * int(subBand.polProducts.blbProdIntegration.attrib['ltaIntegFactor'])
        else:
            self.hw_time_res = \
                    1e-6 * float(subBand.polProducts.blbProdIntegration.attrib['minIntegTime'])\
                    * int(subBand.polProducts.blbProdIntegration.attrib['ccIntegFactor']) \
                    * int(subBand.polProducts.blbProdIntegration.attrib['ltaIntegFactor'])

        self.final_time_res = self.hw_time_res \
                    * int(subBand.polProducts.blbProdIntegration.attrib['cbeIntegFactor'])

    @property
    def npp(self):
        return len(self.pp)


class Antenna(object):
    """Holds info about an antenna, as described in the Antenna Properties
    Table.  Initialize with the AntennaProperties xml element."""
    # TODO should this be immutable (named tuple or similar?)

    def __init__(self, antprop):
        self.name = str(antprop.attrib['name'])
        self.widarID = int(antprop.widarID)
        self.pad = str(antprop.pad)
        self.X = float(antprop.X)
        self.Y = float(antprop.Y)
        self.Z = float(antprop.Z)
        self.offset = float(antprop.offset)

    @property
    def xyz(self):
        return [self.X, self.Y, self.Z]


# Test program
if __name__ == "__main__":
    import sys
    import vcixml_parser
    import obsxml_parser
    vcifile = sys.argv[1]
    obsfile = sys.argv[2]
    print("Parsing vci='%s' obs='%s'" % (vcifile, obsfile))
    vci = vcixml_parser.parse(vcifile)
    obs = obsxml_parser.parse(obsfile)
    config = ScanConfig(vci=vci, obs=obs)
    print("Found these subbands:")
    for sub in config.get_subbands(only_vdif=False):
        print("  IFid=%s swindex=%d sbid=%d vdif=%s bw=%.1f freq=%.1f" % (
                sub.IFid, sub.swIndex, sub.sbid, sub.vdif is not None,
                sub.bw, sub.sky_center_freq))
