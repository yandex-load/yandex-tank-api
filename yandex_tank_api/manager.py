import os.path
import os
import signal
import multiprocessing
import logging
import logging.handlers
import traceback
import json

import yandex_tank_api.common
import yandex_tank_api.worker
import yandex_tank_api.webserver


class TankRunner(object):

    """
    Manages the tank process and its working directory.
    """

    def __init__(self,
                 cfg,
                 manager_queue,
                 session_id,
                 tank_config,
                 first_break):
        """
        Sets up working directory and tank queue
        Starts tank process
        """
        self.log = logging.getLogger(__name__)

        work_dir = os.path.join(cfg['tests_dir'], session_id)
        load_ini_path = os.path.join(work_dir, 'load.ini')

        # Create load.ini
        tank_config_file = open(load_ini_path, 'w')
        tank_config_file.write(tank_config)

        # Create tank queue and put first break there
        self.tank_queue = multiprocessing.Queue()
        self.set_break(first_break)

        ignore_machine_defaults = cfg['ignore_machine_defaults']

        # Start tank process
        self.tank_process = multiprocessing.Process(
            target=yandex_tank_api.worker.run,
            args=(
                self.tank_queue,
                manager_queue,
                work_dir,
                session_id,
                ignore_machine_defaults
            ))
        self.tank_process.start()

    def set_break(self, next_break):
        """Sends the next break to the tank process"""
        self.tank_queue.put({'break': next_break})

    def is_alive(self):
        """Check that the tank process didn't exit """
        return self.tank_process.exitcode is None

    def get_exitcode(self):
        """Return tank exitcode"""
        return self.tank_process.exitcode

    def join(self):
        """Joins the tank process"""
        return self.tank_process.join()

    def stop(self):
        """Interrupts the tank process"""
        if self.is_alive():
            os.kill(self.tank_process.pid,signal.SIGINT)

    def __del__(self):
        self.stop()


class Manager(object):

    """
    Implements the message processing logic
    """

    def __init__(self,
                 cfg
                 ):
        """Sets up initial state of Manager"""
        self.log = logging.getLogger(__name__)

        self.cfg = cfg

        self.manager_queue = multiprocessing.Queue()
        self.webserver_queue = multiprocessing.Queue()

        self.webserver_process = multiprocessing.Process(
            target=yandex_tank_api.webserver.main,
            args=(self.webserver_queue,
                  self.manager_queue,
                  cfg['tests_dir'],
                  cfg['tornado_debug'])
        )
        self.webserver_process.daemon = True
        self.webserver_process.start()

        self.reset_session()

    def reset_session(self):
        """
        Resets session state variables
        Should be called only when tank is not running
        """
        self.log.info("Resetting current session variables")
        self.session_id = None
        self.tank_runner = None
        self.last_tank_status = 'not started'

    def _handle_cmd(self, msg):
        """Process command from webserver"""

        if 'session' not in msg:
            self.log.error("Bad command: session id not specified")
            return

        if msg['cmd'] == 'stop':
            # Stopping tank
            if msg['session'] == self.session_id:
                self.tank_runner.stop()
            else:
                self.log.error("Can stop only current session")
            return

        if msg['cmd'] == 'run':
            if self.session_id is not None:
                # New break for running session
                if msg['session'] != self.session_id:
                    raise RuntimeError(
                        "Webserver requested to start session "
                        "when another one is already running"
                    )
                elif 'break' in msg:
                    self.tank_runner.set_break(msg['break'])
                else:
                    # Internal protocol error
                    self.log.error("Recieved run command without break:\n%s",json.dumps(msg))
            else:
                # Starting new session
                if 'session' not in msg or 'config' not in msg:
                    # Internal protocol error
                    self.log.error(
                        "Not enough data to start new session: "
                        "both config and test should be present:%s\n",
                        json.dumps(msg)
                    )
                else:
                    try:
                        self.tank_runner = TankRunner(
                            cfg=self.cfg,
                            manager_queue=self.manager_queue,
                            session_id=msg['session'],
                            tank_config=msg['config'],
                            first_break=msg['break']
                        )
                    except KeyboardInterrupt:
                        pass
                    except Exception as ex:
                        self.webserver_queue.put({
                            'session': msg['session'],
                            'status': 'failed',
                            'break': msg['break'],
                            'reason': 'Failed to start tank:\n'
                            + traceback.format_exc(ex)
                        })
                    else:
                        self.session_id = msg['session']


            return

        raise self.log.error("Unknown command")

    def run(self):
        """
        Manager event loop.
        Processing messages from self.manager_queue
        Checking that tank is alive

        When we detect tank death, we need to empty the queue once again
        to fetch any remaining messages.
        """

        handle_tank_exit = False

        while True:
            try:
                msg = self.manager_queue.get(
                    block=True, timeout=self.cfg['tank_check_interval'])
            except multiprocessing.queues.Empty:
                if handle_tank_exit:
                    # We detected tank death and made sure the queue is empty.
                    # Do what we should.
                    if self.last_tank_status == 'running'\
                            or self.tank_runner.get_exitcode() != 0:
                        # Report unexpected death
                        self.webserver_queue.put({
                            'session': self.session_id,
                            'status': 'failed',
                            'reason': "Tank died unexpectedly. Last reported "
                            "status: % s, worker exitcode: % s" %
                            (self.last_tank_status,
                             self.tank_runner.get_exitcode())
                        })
                    # In any case, reset the session
                    self.reset_session()
                    handle_tank_exit = False

                elif self.session_id is not None\
                        and not self.tank_runner.is_alive():
                    # Tank has died.
                    # Fetch any remaining messages and wait one more timeout
                    # before reporting unexpected death and resetting session
                    handle_tank_exit = True
                elif not self.webserver_process.is_alive():
                    self.log.error("Webserver died unexpectedly.")
                    if self.tank_runner is not None:
                        self.log.warning("Stopping tank...")
                        self.tank_runner.stop()
                        self.tank_runner.join()
                    return
                else:
                    # No messages. Either no session or tank is just quietly
                    # doing something.
                    continue
        
            # Process next message
            self._handle_msg(msg)

    def _handle_msg(self, msg):
        """Handle message from manager queue"""
        self.log.info("Recieved message:\n%s", json.dumps(msg))
        if 'cmd' in msg:
            # Recieved command from server
            self._handle_cmd(msg)
        elif 'status' in msg:
            # This is a status message from tank
            self._handle_tank_status(msg)
        else:
            self.log.error(
                "Strange message (not a command and not a status) ")


    def _handle_tank_status(self, msg):
        """
        Wait for tank exit if it stopped.
        Remember new status and notify webserver.
        """
        new_status = msg['status']

        if self.last_tank_status not in ['success', 'failed'] \
                and new_status in ['success', 'failed']:
            self.log.info("Waiting for tank exit...")
            self.tank_runner.join()
            self.reset_session()

        self.last_tank_status = msg['status']

        self.webserver_queue.put(msg)

def run_server(options):
    """Runs the whole yandex-tank-api server """

    # Configure
    # TODO: un-hardcode cfg
    cfg = {
        'tank_check_interval': 1.0,
        'tests_dir': options.work_dir + '/tests',
        'ignore_machine_defaults': options.ignore_machine_defaults,
        'tornado_debug': options.debug
    }

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    if options.log_file is None:
        handler = logging.StreamHandler()
    else:
        handler = logging.handlers.RotatingFileHandler(
            options.log_file, maxBytes=1000000, backupCount=16)

    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s %(message)s"))
    root_logger.addHandler(handler)

    logger = logging.getLogger(__name__)
    try:
        logger.info("Starting server")
        Manager(cfg).run()
    except KeyboardInterrupt:
        logger.info("Interrupted, terminating")
    except Exception:
        logger.exception("Unhandled exception in manager.run_server:")
    except:
        logger.error("Caught something strange in manager.run_server")
