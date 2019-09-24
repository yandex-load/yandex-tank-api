"""
Tank worker process for yandex-tank-api
Based on ConsoleWorker from yandex-tank
"""

import signal
import fnmatch
import logging
import os
import os.path
import traceback
import json
import yaml
import itertools as itt
import time

import yandextank.core as tankcore
import yandextank.core.consoleworker as core_console
import threading

# Yandex.Tank.Api modules

# Test stage order, internal protocol description, etc...
import yandex_tank_api.common as common


_log = logging.getLogger(__name__)


class InterruptTest(BaseException):
    """Raised by sigterm handler"""

    def __init__(self, remove_break=False):
        super(InterruptTest, self).__init__()
        self.remove_break = remove_break


class TankCore(tankcore.TankCore):
    """
    We do not use tankcore.TankCore itself
    to let plugins know that they are executed under API server.

    Typical check in the plugin looks like this:

    def _core_with_tank_api(self):
        core_class = str(self.core.__class__)
        return core_class == 'yandex_tank_api.worker.TankCore'
    """

    def __init__(self, tank_worker, configs, **kwargs):
        super(TankCore, self).__init__(configs, threading.Event(), **kwargs)
        self.tank_worker = tank_worker

    def publish(self, publisher, key, value):
        super(TankCore, self).publish(publisher, key, value)
        self.tank_worker.report_status('running', False)


class TankWorker(object):
    """    Worker class that runs tank core until the next breakpoint   """

    def __init__(
            self, tank_queue, manager_queue, working_dir, lock_dir, session_id,
            ignore_machine_defaults, configs_location):

        # Parameters from manager
        self.tank_queue = tank_queue
        self.manager_queue = manager_queue
        self.working_dir = working_dir
        self.session_id = session_id
        self.ignore_machine_defaults = ignore_machine_defaults
        self.configs_location = configs_location

        # State variables
        self.break_at = 'lock'
        self.stage = 'not started'
        self.failures = []
        self.retcode = None
        self.done_stages = set()
        self.lock_dir = lock_dir
        self.lock = None

        print(lock_dir)

    @property
    def locked(self):
        return bool(self.lock and self.lock.is_locked(self.core.lock_dir))

    @common.memoized
    def core(self):
        print(self.__get_configs())
        c = TankCore(self, self.__get_configs())
        c.lock_dir = self.lock_dir
        c.__setattr__('__session_id', self.session_id)
        return c

    def __add_log_file(self, logger, loglevel, filename):
        """Adds FileHandler to logger; adds filename to artifacts"""
        self.core.add_artifact_file(filename)
        handler = logging.FileHandler(filename)
        handler.setLevel(loglevel)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s %(message)s"))
        logger.addHandler(handler)

    def __setup_logging(self):
        """
        Logging setup.
        Should be called only after the lock is acquired.
        """
        logger = logging.getLogger('')
        logger.setLevel(logging.DEBUG)

        self.__add_log_file(logger, logging.DEBUG, os.path.join(self.core.artifacts_dir, 'tank.log'))
        self.__add_log_file(logger, logging.INFO, os.path.join(self.core.artifacts_dir, 'tank_brief.log'))

    @staticmethod
    def __get_configs_from_dir(config_dir):
        """
        Returns configs from specified directory, sorted alphabetically
        """
        configs = []
        try:
            conf_names = os.listdir(config_dir)
            conf_names.sort()
            for filename in conf_names:
                if fnmatch.fnmatch(filename, '*.yaml'):
                    config_path = os.path.realpath(
                        config_dir + os.sep + filename)
                    _log.debug("Adding config file: %s", config_path)
                    with open(config_path) as config_file:
                        try:
                            configs.append(yaml.safe_load(config_file))
                        except yaml.YAMLError:
                            _log.error('Failed to unyaml a config at {}'.format(config_path))

        except OSError:
            _log.warning(
                "Failed to get configs from %s", config_dir, exc_info=True)

        return configs

    def __get_configs(self):
        """Returns list of all configs for this test"""
        configs = list(
            itt.chain(
                [core_console.load_core_base_cfg()]
                    if not self.ignore_machine_defaults else [],
                self.__get_configs_from_dir('{}/yandex-tank/'.format(self.configs_location))
                    if not self.ignore_machine_defaults else [],
                self.__get_configs_from_dir('.'),
                )
        )
        return configs

    def __preconfigure(self):
        """Logging and TankCore setup"""
        self.__setup_logging()
        self.core.load_plugins()

    def __get_lock(self):
        """Get lock and remember that we succeded in getting lock"""
        while not self.core.interrupted.is_set():
            try:
                self.lock = tankcore.tankcore.Lock(self.core.test_id, self.core.lock_dir).acquire(self.core.lock_dir,
                                                               self.core.config.get_option(self.core.SECTION, 'ignore_lock'))
                break
            except tankcore.tankcore.LockError:
                if not self.core.wait_lock:
                    raise RuntimeError("Lock file present, cannot continue")
                _log.warning(
                    "Couldn't get lock. Will retry in 5 seconds...")
                time.sleep(5)
        else:
            raise KeyboardInterrupt

    def __end(self):
        return self.core.plugins_end_test(self.retcode)

    def __postprocess(self):
        return self.core.plugins_post_process(self.retcode)

    def __release_lock(self):
        if self.lock is not None:
            self.lock.release()

    def get_next_break(self):
        """
        Read the next break from tank queue
        Check it for sanity
        """
        while True:
            msg = self.tank_queue.get()
            # Check that there is a break in the message
            if 'break' not in msg:
                _log.error(
                    'No break specified in the recieved message from manager')
                continue
            brk = msg['break']
            # Check taht the name is valid
            if not common.is_valid_break(brk):
                _log.error(
                    'Manager requested break at an unknown stage: %s', brk)
            # Check that the break is later than br
            elif common.is_a_earlier_than_b(brk, self.break_at):
                _log.error(
                    'Recieved break %s which is earlier than '
                    'current next break %s', brk, self.break_at)
            else:
                _log.info(
                    'Changing the next break from %s to %s', self.break_at, brk)
                self.break_at = brk
                return

    def answer(self, plugin, attr):
        """
        answers for /ask handler
        :param plugin: core plugin
        :param attr: plugin attr name
        :return: attr value or None
        """
        try:
            plugin = self.core.plugins[plugin]
            a = plugin.__dict__.get(attr)
        except KeyError as exc:
            a = repr(exc)

        msg = {
            'plugin': plugin,
            'attr': attr,
            'answer': a
        }
        self.manager_queue.put(msg)
        if self.locked:
            with open('{}.{}'.format(plugin, attr), 'w') as f:
                json.dump(msg, f, indent=4)

    def report_status(self, status, stage_completed):
        """Report status to manager and dump status.json, if required"""
        msg = {
            'status': 'prepared' if self.break_at == 'start' and self.stage == 'prepare' and stage_completed else status,
            'session': self.session_id,
            'current_stage': self.stage,
            'stage_completed': stage_completed,
            'break': self.break_at,
            'failures': self.failures,
            'retcode': self.retcode,
            'tank_status': self.core.status,
        }
        self.manager_queue.put(msg)
        if self.locked:
            with open('status.json', 'w') as f:
                json.dump(msg, f, indent=4)

    def process_failure(self, reason):
        """
        Act on failure of current test stage:
        - log it
        - add to failures list
        """
        _log.error('Failure in stage %s:\n%s', self.stage, reason)
        self.failures.append({'stage': self.stage, 'reason': reason})

    def _execute_stage(self, stage):
        """Really execute stage and set retcode"""
        new_retcode = {
            'init': self.__preconfigure,
            'lock': self.__get_lock,
            'configure': self.core.plugins_configure,
            'prepare': self.core.plugins_prepare_test,
            'start': self.core.plugins_start_test,
            'poll': self.core.wait_for_finish,
            'end': self.__end,
            'postprocess': self.__postprocess,
            'unlock': self.__release_lock
        }[stage]()
        if new_retcode is not None:
            self.retcode = new_retcode

    def next_stage(self, stage):
        """
        Report stage completion.
        Switch to the next test stage if allowed.
        Run it or skip it
        """

        while not common.is_a_earlier_than_b(stage, self.break_at):
            # We have reached the set break
            # Waiting until another, later, break is set by manager
            self.get_next_break()
        self.stage = stage
        self.report_status('running', False)
        if stage == common.TEST_STAGE_ORDER[0] or common.TEST_STAGE_DEPS[
                stage] in self.done_stages:
            try:
                self._execute_stage(stage)
            except InterruptTest as exc:
                self.retcode = self.retcode or 1
                self.process_failure('Interrupted')
                if exc.remove_break:
                    self.break_at = 'finished'
            except Exception as ex:
                self.retcode = self.retcode or 1
                _log.exception(
                    'Exception occured, trying to exit gracefully...')
                self.process_failure('Exception:' + traceback.format_exc())
            else:
                self.done_stages.add(stage)
        else:
            self.process_failure('skipped')

        self.report_status('running', True)

    def perform_test(self):
        """Perform the test sequence via TankCore"""
        for stage in common.TEST_STAGE_ORDER[:-1]:
            self.next_stage(stage)
        self.stage = 'finished'
        self.report_status('failed' if self.failures else 'success', True)
        _log.info('Done performing test with code %s', self.retcode)


def signal_handler(signum, _):
    """ required for everything to be released safely on SIGTERM and SIGINT"""
    if signum == signal.SIGINT:
        raise InterruptTest(remove_break=False)
    raise InterruptTest(remove_break=True)


def run(
        tank_queue, manager_queue, work_dir, lock_dir, session_id,
        ignore_machine_defaults, configs_location):
    """
    Target for tank process.
    This is the only function from this module ever used by Manager.

    tank_queue
        Read next break from here

    manager_queue
        Write tank status there

    """
    os.chdir(work_dir)
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    TankWorker(
        tank_queue, manager_queue, work_dir, lock_dir, session_id,
        ignore_machine_defaults, configs_location).perform_test()
