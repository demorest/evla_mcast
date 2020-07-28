# This extrememly simple example sets the log level to debug and then
# runs the base controller class.  The result is log messages printed
# to stdout containing the raw XML for each multicast message received
# as well as the corresponding lxml data structure dumps.

import logging
import evla_mcast

logging.basicConfig(format="%(asctime)-15s %(levelname)8s %(message)s",
        level=logging.DEBUG)

c = evla_mcast.Controller()
c.run()
