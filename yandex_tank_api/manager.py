import os
import os.path
import errno
import multiprocessing
import logging
import traceback
import json

import common
import worker
import webserver

class TankRunner(object):
    """
    Manages the tank process and its working directory.
    """
    def __init__(self,
                 cfg,
                 manager_queue,
                 session,
                 test_id,
                 tank_config,
                 first_break):
        """
        Sets up working directory and tank queue
        Starts tank process
        """
        self.log = logging.getLogger(__name__)

        #Create the working directory if necessary and check that the test was not run yet
        work_dir=cfg['tests_dir']+'/'+test_id
        try:
            os.makedirs(work_dir)
        except OSError as err:
            if err.errno != errno.EEXIST :
                self.log.exception("Failed to create working directory %s",work_dir)
                raise
            else:
                if os.path.exists(work_dir+'/status.json'):
                    raise RuntimeError("Test already exists")
        #Create load.ini
        tank_config_file=open(work_dir+'/load.ini','w')
        tank_config_file.write(tank_config)

        #Create tank queue and put first break there
        self.tank_queue=multiprocessing.Queue()
        self.set_break(first_break)

        #Start tank process
        self.tank_process=multiprocessing.Process(target=worker.run,args=(self.tank_queue,manager_queue,work_dir,session,test_id))
        self.tank_process.start()

    def set_break(self,next_break):
        """Sends the next break to the tank process"""
        self.tank_queue.put({'break':next_break})

    def is_alive(self):
        """Check that the tank process didn't exit """
        return self.tank_process.exitcode is None

    def  get_exitcode(self):
        """Return tank exitcode"""
        return self.tank_process.exitcode

    def join(self):
        """Joins the tank process"""
        return self.tank_process.join()

    def stop(self):
        """Terminates the tank process"""
        self.tank_process.terminate()

    def __del__(self):
        self.stop()

class Manager(object):
    """
    Implements the message processing logic
    """

    def __init__(self,
                 cfg,
                 manager_queue,
                 webserver_queue,
                 TankRunnerClass=TankRunner):
        """Sets up initial state of Manager"""
        self.log = logging.getLogger(__name__)

        self.cfg=cfg
        self.manager_queue=manager_queue
        self.webserver_queue=webserver_queue

        self.TankRunner = TankRunnerClass
        self.reset_session()

    def reset_session(self):
        """
        Resets session state variables
        Should be called only when tank is not running
        """
        self.log.info("Resetting current session variables")
        self.session=None
        self.test=None
        self.tank_runner=None
        self.last_tank_status='not started'

    def manage_tank(self,msg):
        """Process command from webserver"""

        if 'session' not in msg:
            self.log.error("Bad command: session not specified")
            return

        if msg['cmd']=='stop':
            #Stopping tank
            if msg['session']==self.session:
                self.tank_runner.stop()
            else:
                self.log.error("Can stop only current session")
            return

        if msg['cmd']=='run':
           if self.session is not None:
               #New break for running session
               if msg['session']!=self.session:
                   raise RuntimeError("Webserver requested to start session when another one is already running")
               elif 'break' in msg:
                   self.tank_runner.set_break(msg['break'])
               else:
                   #Internal protocol error
                   self.log.error("Recieved run command without break")
           else:
               #Starting new session
               if 'test' not in msg or 'config' not in msg:
                   #Internal protocol error
                   self.log.error("Not enough data to start new session: both config and test should be present")
               else:
                   self.session=msg['session']
                   self.test=msg['test']
                   try:
                       self.tank_runner=self.TankRunner(cfg=self.cfg,
                                                         manager_queue=self.manager_queue,
                                                         session=self.session,
                                                         test_id=self.test,
                                                         tank_config=msg['config'],
                                                         first_break=msg['break']
                                                         )
                   except KeyboardInterrupt:
                       pass
                   except Exception as ex:
                       self.webserver_queue.put({'session':msg['session'],
                                                 'status':'failed',
                                                 'test':self.test,
                                                 'break':msg['break'],
                                                 'reason':'Failed to start tank:\n'+traceback.format_exc(ex) })


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
        
        handle_tank_exit=False

        while True:
            try:
                msg=self.manager_queue.get(block=True,timeout=self.cfg['tank_check_interval'] )
            except multiprocessing.queues.Empty:
                if handle_tank_exit:
                   # We detected tank death and made sure the queue is empty. Do what we should.
                   if self.last_tank_status=='running' or self.tank_runner.get_exitcode() !=0:
                       # Report unexpected death
                       self.webserver_queue.put({'session':self.session,
                                                  'test':self.test,
                                                  'status':'failed',
                                                  'reason':'Tank died unexpectedly. Last reported status: {0}, worker exitcode: {1} '.format(self.last_tank_status,self.tank_runner.get_exitcode())})
                   # In any case, reset the session
                   self.reset_session()
                   handle_tank_exit=False

                elif self.session is not None and not self.tank_runner.is_alive():
                    # Tank has died.
                    # Fetch any remaining messages and wait one more timeout
                    # before reporting unexpected death and resetting session
                    handle_tank_exit = True   
                   
                else:
                    #No messages. Either no session or tank is just quietly doing something.
                    continue

            #Process next message
            self.log.info("Recieved message:\n%s",json.dumps(msg) )

            if 'cmd' in msg:
                #Recieved command from server
                self.manage_tank(msg)
            elif 'status' in msg:
                # This is a status message from tank
                
                new_status=msg['status']
                # Check for transition from running to stopped 
                if self.last_tank_status not in ['success','failed'] \
                              and new_status in ['success','failed']:
                    self.log.info("Waiting for tank exit...")
                    self.tank_runner.join()
                    self.reset_session()
                
                self.last_tank_status=msg['status']
                # Notify webserver
                self.webserver_queue.put(msg)
            else:
                self.log.error("Strange message (not a command and not a status) ")


def run_server(options):
    """Runs the whole yandex-tank-api server """

    #Configure
    #TODO: un-hardcode cfg
    cfg={'tank_check_interval':1.0,
         'tests_dir':'/var/lib/yandex-tank-api/tests'}
    #TODO: really setup logging
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s: %(message)s")

    #TODO: daemonize

    #Create queues for manager and webserver
    manager_queue=multiprocessing.Queue()
    webserver_queue=multiprocessing.Queue()

    #Fork webserver
    webserver_process=multiprocessing.Process(target=webserver.main,args=(webserver_queue,manager_queue,cfg['tests_dir'],options.debug))
    webserver_process.start()

    #Run
    Manager(cfg,manager_queue,webserver_queue).run()
