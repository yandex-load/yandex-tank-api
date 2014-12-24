"""
Tank worker process for yandex-tank-api
Based on ConsoleWorker from yandex-tank
"""

import datetime
import fnmatch
import logging
import os
import sys
import time
import traceback
import signal
from optparse import OptionParser

#Yandex.Tank modules
#TODO: split yandex-tank and make python-way install
sys.path.append('/usr/lib/yandex-tank')
import tankcore.TankCore

#Yandex.Tank.Api modules

#Test stage order, internal protocol description, etc...
import common


def signal_handler(sig, frame):
    """ Converts SIGTERM and SIGINT into KeyboardInterrupt() exception """
    raise KeyboardInterrupt()

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

class TankWorker:
    """    Worker class that runs tank core until the next breakpoint   """

    IGNORE_LOCKS = "ignore_locks"

    def __init__(self, tank_queue, manager_queue, working_dir):

        self.log = logging.getLogger(__name__)
        self.working_dir = working_dir

        self.core = tankcore.TankCore()

    def __add_log_file(self,logger,loglevel,filename):
        """Adds FileHandler to logger; adds filename to artifacts"""
        full_filename=self.working_dir+os.sep+filename

        self.core.add_artifact_file(full_filename)

        handler = logging.FileHandler(full_filename)
        handler.setLevel(loglevel)
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s %(message)s"))
        logger.addHandler(handler)

    def __setup_logging(self):
        """
        Logging setup.
        Should be called only after the lock is acquired.
        """
        logger = logging.getLogger('')
        logger.setLevel(logging.DEBUG)

        self.__add_log_file(logger,logging.DEBUG,'tank.log')
        self.__add_log_file(logger,logging.INFO,'tank_brief.log')

    def __get_configs_from_dir(self,config_dir):
        """ 
        Returns configs from specified directory, sorted alphabetically
        """
        configs = []
        try:
            conf_files = os.listdir(config_dir)
            conf_files.sort()
            for filename in conf_files:
                if fnmatch.fnmatch(filename, '*.ini'):
                    config_file = os.path.realpath(self.baseconfigs_location + os.sep + filename)
                    self.log.debug("Adding config file: %s",config_file)
                    configs += [config_file]
        except OSError:
            self.log.error("Failed to get configs from %s",config_dir)

       return configs

    def __get_configs(self):
        """Returns list of all configs for this test"""
        configs=[]
        for cfg_dir in  ['/etc/yandex-tank/', 
                         '/etc/yandex-tank-api/defaults',
                          self.working_dir,
                          '/etc/yandex-tank-api/override']:
            configs += self.__get_configs_from_dir(cfg_dir)
        return configs


    def __preconfigure(self):
        """Logging and TankCore setup"""
        self.__setup_logging()
        self.core.load_configs( self.__get_configs() )
        self.core.load_plugins()

    def report_status()
        """Report status to manager"""
        self.manager_queue.put({'status':self.status,
                                'current_stage':self.stage,
                                'break':self.break_at,
                                'failures':self.failures})
 
    def failure(self,reason):
        """Set and report the first failure"""
        self.failures.append({'stage':self.stage,'reason':reason})
        self.report_status()

    def set_stage(self,stage):
        """Unconditionally switch stage and report status to manager"""
        self.stage=stage
        self.report_status()
       
    def next_stage(stage):
        """Switch to next test stage if allowed"""
        while not common.is_A_earlier_than_B(stage,self.break_at):
            #We have reached the set break
            #Waiting until another, later, break is set by manager
            self.get_next_break()
        self.switch_stage(stage)
        
    def perform_test(self):
        """Perform the test sequence via TankCore"""
        retcode = 1

        self.set_stage('lock')

        try:
            self.core.get_lock(self.options.ignore_lock)
        except Exception:
            self.failure('Failed to obtain lock')
            return retcode

        try:
            self.__preconfigure()

            self.next_stage('configure')
            self.core.plugins_configure()

            self.next_stage('prepare')
            self.core.plugins_prepare_test()

            self.next_stage('start')
            self.core.plugins_start_test()

            self.next_stage('poll')
            retcode = self.core.wait_for_finish()

        except KeyboardInterrupt:
            self.failure("Interrupted")
            self.log.info("Interrupted, trying to exit gracefully...")

        except Exception as ex:
            self.failure("Exception:" + traceback.format_exc(ex) )
            self.log.exception("Exception occured:")
            self.log.info("Trying to exit gracefully...")

        finally:
            try:
                self.next_stage('end')
                retcode = self.core.plugins_end_test(retcode)

                #We do NOT call post_process if end_test failed
                #Not sure if it is the desired behaviour
                self.next_stage('postprocess')
                retcode = self.core.plugins_post_process(retcode)
            except KeyboardInterrupt:
                self.failure("Interrupted")
                self.log.info("Interrupted during test shutdown...")
            except Exception as ex:
                self.failure("Exception:" + traceback.format_exc(ex) )
                self.log.exception("Exception occured while finishing test")
            finally:            
                self.next_stage('unlock')
                self.core.release_lock()
        self.log.info("Done performing test with code %s", retcode)

        return retcode

    def run():
        self.break_at='lock'
        self.stage='started' #Not reported anywhere to anybody
        self.failures=[]

        try:
           retcode = perform_test()

        self.set_stage('

def run(tank_queue,manager_queue,work_dir):
    """
    Target for tank process.
    This is the only function from this module ever used by Manager.

    tank_queue
        Read next break from here

    manager_queue
        Write tank status there
       
    """

    pass
