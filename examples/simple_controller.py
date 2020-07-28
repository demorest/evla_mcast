# This extrememly simple example sets the log level to debug and then
# runs the base controller class.  The result is log messages printed
# to stdout containing the raw XML for each multicast message received
# as well as the corresponding lxml data structure dumps.

import logging
import evla_mcast

# Set log format, level
logging.basicConfig(format="%(asctime)-15s %(levelname)8s %(message)s",
        level=logging.INFO)

class SimpleController(evla_mcast.Controller):

    def __init__(self):
        
        # Call base class init
        super(SimpleController, self).__init__()

        # Require two Observation XML documents in order to get
        # the scan stop time as well as basic scan metadata:
        self.scans_require = ['obs', 'stop']

    def handle_config(self, scan):

        # This function is called whenever a complete scan (according to 
        # requirements in self.scans_require) is defined.  In a real 
        # system this could launch appropriate processing jobs, etc.
        # Here we just print some metadata from the ScanConfig object.

        print("Observing source '%s' at (ra,dec)=(%.3f,%.3f) deg from MJD %.6f to %.6f" 
                % (scan.source, scan.ra_deg, scan.dec_deg, scan.startTime, scan.stopTime)
            )

c = SimpleController()
c.run()
