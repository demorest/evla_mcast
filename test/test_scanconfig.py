import pytest
import evla_mcast
import os.path

_data_dir = os.path.abspath(os.path.dirname(__file__)) + '/data/'

def test_scan_config():
    sc = evla_mcast.scan_config.ScanConfig(vci=_data_dir+'test_vci.xml', obs=_data_dir+'test_obs.xml', ant=_data_dir+'test_antprop.xml', requires=['ant', 'vci', 'obs'])
    assert sc.numAntenna == 25
    assert sc.datasetId == 'L_realfast.57897.87981900463'
