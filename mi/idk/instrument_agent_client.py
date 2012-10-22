"""
@file mi/idk/instrument_agent_client.py
@author Bill French
@brief Helper class start the instrument_agent_client
"""

__author__ = 'Bill French'
__license__ = 'Apache 2.0'

import os
import signal
import subprocess
import time
from gevent import spawn
from gevent.event import AsyncResult

from mi.core.log import get_logger ; log = get_logger()

# Set testing to false because the capability container tries to clear out
# couchdb if we are testing. Since we don't care about couchdb for the most
# part we can ignore this. See initialize_ion_int_tests() for implementation.
# If you DO care about couch content make sure you do a force_clean when needed.
from pyon.core import bootstrap
bootstrap.testing = False;

from mi.idk.config import Config

from mi.idk.exceptions import TestNoDeployFile
from mi.idk.exceptions import NoContainer
from mi.idk.exceptions import MissingConfig
from mi.idk.exceptions import MissingExecutable
from mi.idk.exceptions import FailedToLaunch


from pyon.util.int_test import IonIntegrationTestCase
from pyon.container.cc import Container
from pyon.util.context import LocalContextMixin

from interface.services.icontainer_agent import ContainerAgentClient
from pyon.agent.agent import ResourceAgentClient
from interface.services.dm.ipubsub_management_service import PubsubManagementServiceClient
from interface.services.dm.idataset_management_service import DatasetManagementServiceClient

from pyon.ion.stream import StandaloneStreamSubscriber

from pyon.event.event import EventSubscriber

#from interface.objects import StreamQuery

DEFAULT_DEPLOY = 'res/deploy/r2deploy.yml'

class FakeProcess(LocalContextMixin):
    """
    A fake process used because the test case is not an ion process.
    """
    name = ''
    id=''
    process_type = ''

class InstrumentAgentClient(object):
    """
    Launch a capability container and instrument agent client
    """
    container = Container.instance

    def start_client(self, name, module, cls, config, resource_id, deploy_file = DEFAULT_DEPLOY, message_headers=None):
        """
        @brief Start up the instrument agent client
        """
        self.start_container(deploy_file=deploy_file)

        # Start instrument agent.
        log.debug("Starting Instrument Agent Client")
        container_client = ContainerAgentClient(node=self.container.node,
            to_name=self.container.name)

        instrument_agent_pid = container_client.spawn_process(
            name=name,
            module=module,
            cls=cls,
            config=config,
            headers=message_headers)
        log.info('Agent pid=%s.', instrument_agent_pid)

        ia_client = ResourceAgentClient(resource_id, process=FakeProcess())

        log.info('Got ia client %s.', str(ia_client))

        self.instrument_agent_client = ia_client


    def start_container(self, deploy_file = DEFAULT_DEPLOY):
        """
        @brief Launch the instrument agent
        """
        log.info("Startup Instrument Agent")

        self.start_couchdb()
        self.start_rabbitmq_server()

        # No need to start the container twice
        self.container = Container.instance
        if self.container:
            return

        if not os.path.exists(deploy_file):
            raise TestNoDeployFile(deploy_file)

        # Derive a special test case so we can instantiate a testcase object.
        # then we can run start_container which initialized the capability container
        # There will eventually be a better way to do this I'm sure.
        class _StartContainer(IonIntegrationTestCase):
            def runTest(self): pass

        testcase = _StartContainer()

        # Start container.
        log.info("Starting the capability container")
        testcase._start_container()
        container = testcase.container

        log.debug( "Capability container id: %s" % testcase.container.id )

        # Bring up services in a deploy file (no need to message)
        log.info("Initialize container with %s" % deploy_file)
        container.start_rel_from_url(deploy_file)

        self.container = container

    def stop_container(self):
        log.info("Stop the instrument agent")

        if not self.container:
            log.warn("Container not running.")
            return

        # Derive a special test case so we can instantiate a testcase object.
        # then we can run start_container which initiallized the capability container
        class _StartContainer(IonIntegrationTestCase):
            def runTest(self): pass

        testcase = _StartContainer()
        testcase.container = self.container
        testcase._stop_container()

        self.stop_couchdb()
        self.stop_rabbitmq_server()

        self.container = None

    def start_couchdb(self):
        """
        @brief Start the instrument agent
        """
        # Do nothing if rabbit is already running
        log.debug("****************************STARTING COUCHDB****************************")
        pid = self._read_pidfile(self._pid_filename("couchdb"))
        if pid:
            return

        cmd = Config().get("couchdb")
        if not cmd:
            raise MissingConfig("couchdb")

        self._run_process(cmd, '-b', self._pid_filename("couchdb"), False)

    def stop_couchdb(self):
        """
        @brief Stop the instrument agent
        """
        log.info("Stopping CouchDB")
        pid = self._read_pidfile(self._pid_filename("couchdb"))

        if not pid > 0:
            return

        cmd = Config().get("couchdb")
        if not cmd:
            raise MissingConfig("couchdb")

        self._run_process(cmd, '-k')

        os.remove(self._pid_filename("couchdb"))
        time.sleep(2) # couch requires some refractory time

    def start_rabbitmq_server(self):
        """
        @brief Start the instrument agent
        """
        # Do nothing if rabbit is already running
        pid = self._read_pidfile(self._pid_filename("rabbitmq"))
        if pid:
            return

        cmd = Config().get("rabbitmq")
        if not cmd:
            raise MissingConfig("rabbitmq")

        # The rabbit startup file is a script that starts the erl program.  If
        # erl isn't in the path the server doesn't start.
        # TODO: put this in a config parameter
        os.environ['PATH'] = "%s:%s" % (os.environ['PATH'], "/usr/local/bin")
        self._run_process(cmd, '-detached', self._pid_filename("rabbitmq"), False)

    def stop_rabbitmq_server(self):
        """
        @brief Stop the instrument agent
        """
        log.info("Stopping RabbitMQ")
        pid = self._read_pidfile(self._pid_filename("rabbitmq"))

        if not pid > 0:
            return

        log.debug("-- send sigterm to pid %s", pid)
        try:
            os.kill(pid, signal.SIGTERM)
        except:
            pass

        os.remove(self._pid_filename("rabbitmq"))

    def _run_process(self, cmd, args = None, pidfile = None, raise_error = True):
        """
        @brief Start an external process and store the PID
        """
        if not args: args = ''
        name = os.path.basename(cmd)
        log.info("Start process: %s" % name)
        log.debug( "cmd: %s %s" % (cmd, args))

        if not os.path.exists(cmd):
            raise MissingExecutable(cmd)

        command_line = "%s %s" % (cmd, args);

        process = subprocess.Popen(command_line, shell=True, stdout=subprocess.PIPE)

        # Wait for the process to complete
        
        start_time = time.time()
        while process.poll() == None:
            if start_time + 10 < time.time():
                log.error("Failed to launch application: %s " % command_line)
                if (raise_error):
                    raise FailedToLaunch(command_line)
                break
            time.sleep(.1)
        
        # This causes blocking behavior because the process does not close.
        # Dump output
        #for line in process.stdout:
        #    log.debug(line.rstrip())

        log.debug("Process pid: %d returncode: %d" % (process.pid, process.returncode))
        if process.pid > 0:
            if pidfile:
                self._write_pidfile(process.pid, pidfile)
        else:
            log.error( "Failed to launch application: %s " % command_line)
            if(raise_error):
                raise FailedToLaunch(command_line)


    def _write_pidfile(self, pid, pidfile):
        log.debug("write pid %d to file %s" % (pid, pidfile))
        outfile = open(pidfile, "w")
        outfile.write("%s" % pid)
        outfile.close()

    def _read_pidfile(self, pidfile):
        log.debug( "read pidfile %s" % pidfile)
        try:
            infile = open(pidfile, "r")
            pid = infile.read()
            infile.close()
        except IOError, e:
            return None

        if pid:
            return int(pid)
        else:
            return 0

    def _pid_filename(self, name):
        return "%s/%s_%d.pid" % (Config().get('tmp_dir'), name, os.getpid())

class InstrumentAgentDataSubscribers(object):
    """
    Setup Instrument Agent Publishers
    """
    def __init__(self, packet_config = None, stream_definition = None, original = True, encoding = "ION R2"):
        log.info("Start data subscribers")

        if packet_config == None:
            packet_config = {}


        self.no_samples = None
        self.async_data_result = AsyncResult()

        self.data_greenlets = []
        self.stream_config = {}
        self.raw_samples_received = []
        self.parsed_samples_received = []
        self.data_subscribers = {}
        self.container = Container.instance
        if not self.container:
            raise NoContainer()

        self._build_stream_config()        

    def _build_stream_config(self):
        """
        """
        # Create a pubsub client to create streams.
        pubsub_client = PubsubManagementServiceClient(node=self.container.node)
        dataset_management = DatasetManagementServiceClient() 
        
        # Create streams and subscriptions for each stream named in driver.
        self.stream_config = {}

        streams = {
            #'ctd_parsed' : 'ctd_parsed_param_dict',
            #'ctd_raw' : 'ctd_raw_param_dict',
            'parsed' : 'ctd_parsed_param_dict',
            'raw' : 'ctd_raw_param_dict',
        }

        for (stream_name, param_dict_name) in streams.iteritems():
            pd_id = dataset_management.read_parameter_dictionary_by_name(param_dict_name, id_only=True)

            stream_def_id = pubsub_client.create_stream_definition(name=stream_name,
                                                                   parameter_dictionary_id=pd_id)
            pd = pubsub_client.read_stream_definition(stream_def_id).parameter_dictionary
            
            stream_id, stream_route = pubsub_client.create_stream(name=stream_name,
                                                exchange_point='science_data',
                                                stream_definition_id=stream_def_id)

            stream_config = dict(stream_route=stream_route,
                                 routing_key=stream_route.routing_key,
                                 exchange_point=stream_route.exchange_point,
                                 stream_id=stream_id,
                                 stream_definition_ref=stream_def_id,
                                 parameter_dictionary=pd)
            self.stream_config[stream_name] = stream_config    

    def start_data_subscribers(self, count):
        """
        """        
        # Create a pubsub client to create streams.
        pubsub_client = PubsubManagementServiceClient(node=self.container.node)
                
        # Create streams and subscriptions for each stream named in driver.
        self.data_subscribers = {}
        self.parsed_samples_received = []
        self.raw_samples_received = []
        self.async_data_result = AsyncResult()

        # A callback for processing subscribed-to data.
        def recv_data(message, stream_route, stream_id):
            log.info('Received message on %s (%s,%s)', stream_id,
                     stream_route.exchange_point,
                     stream_route.routing_key)
            if stream_route.routing_key == self.stream_config['parsed']['routing_key']:
                self.parsed_samples_received.append(message)
            elif stream_route.routing_key == self.stream_config['raw']['routing_key']:
                self.raw_samples_received.append(message)
                
            # set when both kinds of messages have at least the required number
            if (len(self.parsed_samples_received) >= count) and \
                (len(self.raw_samples_received) >= count):
                self.async_data_result.set()

        for (stream_name, stream_config) in self.stream_config.iteritems():
            stream_id = stream_config['stream_id']
            # Create subscriptions for each stream.
            exchange_name = '%s_queue' % stream_name
            self._purge_queue(exchange_name)
            sub = StandaloneStreamSubscriber(exchange_name, recv_data)
            sub.start()
            self.data_subscribers[stream_name] = sub
            sub_id = pubsub_client.create_subscription(name=exchange_name, stream_ids=[stream_id])
            pubsub_client.activate_subscription(sub_id)
            sub.subscription_id = sub_id # Bind the subscription to the standalone subscriber (easier cleanup, not good in real practice)

    def _purge_queue(self, queue):
        xn = self.container.ex_manager.create_xn_queue(queue)
        xn.purge()

    def stop_data_subscribers(self):
        for subscriber in self.data_subscribers.values():
            pubsub_client = PubsubManagementServiceClient()
            if hasattr(subscriber,'subscription_id'):
                try:
                    pubsub_client.deactivate_subscription(subscriber.subscription_id)
                except:
                    pass
                pubsub_client.delete_subscription(subscriber.subscription_id)
            subscriber.stop()

    def _listen(self, sub):
        """
        Pass in a subscriber here, this will make it listen in a background greenlet.
        """
        gl = spawn(sub.listen)
        self.data_greenlets.append(gl)
        sub._ready_event.wait(timeout=5)
        return gl

class InstrumentAgentEventSubscribers(object):
    """
    Create subscribers for agent and driver events.
    """
    log.info("Start event subscribers")
    def __init__(self, instrument_agent_resource_id = None):
        # Start event subscribers, add stop to cleanup.
        self.no_events = None
        self.events_received = []
        self.async_event_result = AsyncResult()
        self.event_subscribers = []

        def consume_event(*args, **kwargs):
            log.debug('#**#**# Event subscriber (consume_event) recieved ION event: args=%s, kwargs=%s, event=%s.',
                str(args), str(kwargs), str(args[0]))

            log.debug("self.no_events = " + str(self.no_events))
            log.debug("self.event_received = " + str(self.events_received))

            self.events_received.append(args[0])
            if self.no_events and self.no_events == len(self.events_received):
                log.debug("CALLING self.async_event_result.set()")
                self.async_event_result.set()


        self.event_subscribers = EventSubscriber(
            event_type='ResourceAgentEvent', callback=consume_event,
            origin=instrument_agent_resource_id)
        self.event_subscribers.start()
        self.event_subscribers._ready_event.wait(timeout=5)

