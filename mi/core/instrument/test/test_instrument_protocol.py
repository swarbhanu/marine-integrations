#!/usr/bin/env python

"""
@package mi.core.instrument.test.test_instrument_protocol
@file mi/core/instrument/test/test_instrument_protocol.py
@author Steve Foley
@brief Test cases for the base instrument protocol module
"""

__author__ = 'Steve Foley'
__license__ = 'Apache 2.0'

import logging
from nose.plugins.attrib import attr
from mi.core.log import get_logger ; log = get_logger()
from mi.core.instrument.instrument_protocol import InstrumentProtocol
#from mi.core.instrument.data_particle import DataParticle
from mi.instrument.satlantic.par_ser_600m.ooicore.driver import SAMPLE_REGEX
from mi.instrument.satlantic.par_ser_600m.ooicore.driver import SatlanticPARDataParticle
from pyon.util.unit_test import IonUnitTestCase

@attr('UNIT', group='mi')
class TestUnitInstrumentProtocol(IonUnitTestCase):
    """
    Test cases for instrument protocol class. Functions in this class provide
    instrument protocol unit tests and provide a tutorial on use of
    the protocol interface.
    """ 
    def setUp(self):
        """
        """
        self.callback_result = None
        
        def protocol_callback(self, arg):
            callback_result = arg
            
        self.protocol = InstrumentProtocol(protocol_callback)
    
    def test_extraction(self):
        sample_line = "SATPAR0229,10.01,2206748544,234"
        result = self.protocol._extract_sample(SatlanticPARDataParticle,
                                               SAMPLE_REGEX,
                                               sample_line,
                                               publish=False)
    
        self.assertTrue(result['parsed'])
        self.assertTrue(result['raw'])

        # Test the format of the result in the individual driver tests. Here,
        # just tests that the result is there.
        
    def test_publish_raw(self):
        """
        Tests to see if raw data is appropriately published back out to
        the InstrumentAgent via the event callback.
        """
        # build a packet
        # have it published by the protocol (force state if needed)
        # delay?
        # catch it in the  callback
        # confirm it came back
        # compare response to original packet
        
        self.assertTrue(False)
    
    def test_publish_parsed_data(self):
        """
        Tests to see if parsed data is appropriately published back to the
        InstrumentAgent via the event callback.
        """
        # similar to above
        self.assertTrue(False)

    def test_publish_engineering_data(self):
        """
        Tests to see if engineering data is appropriately published back to the
        InstrumentAgent via the event callback.
        """
        # similar to above
        self.assertTrue(False)    
        
    