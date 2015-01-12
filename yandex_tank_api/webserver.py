#!/usr/bin/env python

import logging
import tornado.ioloop
import tornado.web
from pyjade.ext.tornado import patch_tornado
patch_tornado()

import os.path
import os
import json
import uuid
import multiprocessing

import common

from tornado import template


# TODO: make it configurable
TRANSFER_SIZE_LIMIT = 128 * 1024

class APIHandler(tornado.web.RequestHandler):
    """
    Parent class for API handlers
    """
    def initialize(self, out_queue, sessions, working_dir):
        """
        sessions
            dict: session_id->session_status
        """
        self.out_queue = out_queue
        self.sessions = sessions
        self.working_dir = working_dir

    def reply_json(self,status_code,reply):
        if status_code!=418:
            self.set_status(status_code)
        else:
            self.set_status(status_code,'I\'m a teapot!')
        self.set_header('Content-Type', 'application/json')
        reply_str=json.dumps(reply,indent=4)
        self.finish(reply_str)

    def write_error(self,status_code, **kwargs):
        if self.settings.get("debug"):
            tornado.web.RequestHandler(self,status_code, **kwargs)
            return

        self.set_header('Content-Type', 'application/json')
        if 'exc_info' in kwargs and status_code>=400 and status_code<500:
            self.reply_json(status_code,{'reason':str(kwargs['exc_info'][1]) })
        else:
            self.reply_json(status_code,{'reason':self._reason}) 


class RunHandler(APIHandler):

    def post(self):

        test_id = self.get_argument("test", uuid.uuid4().hex)
        breakpoint = self.get_argument("break", "finished")
        session_id = uuid.uuid4().hex
        config = self.request.body

        #Check existing sessions
        running_session=None
        conflict_session=None
        for s in self.sessions.values():
            if s['status'] not in ['success','failed']:
                running_session=s
            if s['test']==test_id:
                conflict_session=s

        # 400 if invalid breakpoint
        if not common.is_valid_break(breakpoint):
            self.reply_json(400,
                            {'reason':'Specified break is not a valid test stage name.',
                             'hint':{'breakpoints':common.get_valid_breaks()}
                            }
                           )
            return

        # 409 if session with this test_id is already running
        if conflict_session is not None:
            reply={'reason':'The test with this ID is already running.'}
            reply.update(conflict_session)
            self.reply_json(409,reply)
            return

        # 409 if finished test with this test_id exists
        test_status_file=os.path.join(self.working_dir, test_id, 'status.json')
        if os.path.exists(test_status_file):
            reply={'reason':'The test with this ID has already finished.'}
            reply.update(json.load(open(test_status_file)))
            self.reply_json(409,reply)
            return


        # 503 if any running session exists (but no test_id conflict)
        if running_session is not None:
            reply={'reason':'Another session is already running.'}
            reply.update(running_session)
            self.reply_json(503,reply)
            return

        #Remember that such session exists
        self.sessions[session_id]={'status':'starting',
                              'break':breakpoint,
                              'test': test_id}

        # Post run command to manager queue
        self.out_queue.put({'session':session_id,
                       'cmd':'run',
                       'break':breakpoint,
                       'test':test_id,
                       'config':config})

        self.reply_json(200,{
                               "test": test_id,
                               "session": session_id,
                               })

    def get(self):
        breakpoint = self.get_argument("break", "finished")
        session_id = self.get_argument("session")
        self.set_header("Content-type", "application/json")

        # 400 if invalid breakpoint
        if not common.is_valid_break(breakpoint):
            self.reply_json(400,{'reason':'Specified break is not a valid test stage name.',
                                    'hint':
                                        {'breakpoints':common.get_valid_breaks()}
                                   })
            return

        # 404 if no such session
        if not session_id in self.sessions:
            self.reply_json(404,{'reason':'No session with this ID.'})
            return
        status_dict=self.sessions[session_id]

        # 500 if failed
        if status_dict['status'] == 'failed':
            reply={'reason':'Session failed.'}
            reply.update(status_dict)
            self.reply_json(500,reply)
            return

        # 418 if in higher state or not running
        if status_dict['status'] == 'success' or common.is_A_earlier_than_B(breakpoint,status_dict['break']):
            reply={'reason':'I am a teapot! I know nothing of time-travel!',
                    'hint': {'breakpoints':common.get_valid_breaks()} }
            reply.update(status_dict)
            self.reply_json(418,reply)
            return

        # Post run command to manager queue
        self.out_queue.put({'session':session_id,
                       'cmd':'run',
                       'break':breakpoint})

        self.reply_json(200,{'reason':"Will try to set break before "+breakpoint})

class StopHandler(APIHandler):

    def get(self):
        session_id = self.get_argument("session")
        if session_id in self.sessions:
                if self.sessions[session_id]['status'] not in ['success','failed']:
                    self.out_queue.put({
                        'cmd': 'stop',
                        'session': session_id,
                    })
                    self.reply_json(200,{'reason':'Will try to stop tank process.'})
                    return
                else:
                    self.reply_json(409,
                        {
                            'reason': 'This session is already stopped.',
                            'session': session_id,
                        }
                    )
                    return
        else:
                self.reply_json(404,{
                    'reason': 'No session with this ID.',
                    'session': session_id,
                })
                return

class StatusHandler(APIHandler):

    def get(self):
        session_id = self.get_argument("session",default=None)
        if session_id:
            if session_id in self.sessions:
                self.reply_json(200,self.sessions[session_id])
            else:
                self.reply_json(404,{
                    'reason': 'No session with this ID.',
                    'session': session_id,
                })
        else:
            self.reply_json(200,self.sessions)

class ArtifactHandler(APIHandler):

    def get(self):
        test_id = self.get_argument("test")
        filename = self.get_argument("filename",None)

        # look for test directory
        if not os.path.exists(os.path.join(self.working_dir, test_id)):
            self.reply_json(404,{
                'reason': 'No test with this ID found',
                'test': test_id,
            })
            return

        # look for status.json (any test that went past lock stage should have it)
        if not os.path.exists(os.path.join(self.working_dir, test_id, 'status.json')):
            self.reply_json(404,{
                'reason': 'Test was not performed, no artifacts.',
                'test': test_id,
            })
            return

        if filename:
            filepath = os.path.join(self.working_dir, test_id, filename)
            if os.path.exists(filepath):
                file_size = os.stat(filepath).st_size

                if file_size > TRANSFER_SIZE_LIMIT and any(s['status'] not in ['success','failed'] for s in self.sessions.values()):
                    self.reply_json(503,{
                        'reason': 'File is too large and test is running',
                        'test': test_id,
                        'filename': filename,
                        'filesize': file_size,
                        'limit': TRANSFER_SIZE_LIMIT,
                    })
                    return
                else:
                    self.set_header("Content-type", "application/octet-stream")
                    with open(filepath, 'rb') as f:
                        data = f.read()
                        self.write(data)
                    self.finish()
                    return
            else:
                self.reply_json(404,{
                    'reason': 'No such file',
                    'test': test_id,
                    'filename': filename,
                })
                return
        else:
            basepath = os.path.join(self.working_dir, test_id)
            onlyfiles = [
                f for f in os.listdir(basepath)
                if os.path.isfile(os.path.join(basepath, f))
            ]
            self.reply_json(200,onlyfiles)


class StaticHandler(tornado.web.RequestHandler):
    def initialize(self, template):
        self.template = template

    def get(self):
        self.render(self.template)


class ApiServer(object):
    def __init__(self, in_queue, out_queue, working_dir, debug=False):
        self.in_queue = in_queue
        self.out_queue = out_queue
        self.working_dir = working_dir
        self.sessions = {}
        handler_params = dict(
            out_queue=self.out_queue,
            sessions=self.sessions,
            working_dir=self.working_dir,
        )
        self.app = tornado.web.Application(
            [
                (r"/run", RunHandler, handler_params),
                (r"/stop", StopHandler, handler_params),
                (r"/status", StatusHandler, handler_params),
                (r"/artifact", ArtifactHandler, handler_params),
                (r"/manager\.html$", StaticHandler, {"template": "manager.jade"})
            ],
            template_path=os.path.join(os.path.dirname(__file__), "templates"),
            static_path=os.path.join(os.path.dirname(__file__), "static"),
            debug=debug,
        )

    def update_status(self):
        try:
           while True:
               message = self.in_queue.get_nowait()
               session_id=message.get('session')
               del message['session']
               #Test ID and break are always present in message from Manager
               self.sessions[session_id] = message
        except multiprocessing.queues.Empty:
            pass

    def serve(self):
        self.app.listen(8888)
        ioloop = tornado.ioloop.IOLoop.instance()
        update_cb = tornado.ioloop.PeriodicCallback(self.update_status, 100, ioloop)
        update_cb.start()
        ioloop.start()

def main(webserver_queue, manager_queue, test_directory, debug):
    """Target for webserver process.
    The only function ever used by the Manager.

    webserver_queue
        Read statuses from Manager here.

    manager_queue
        Write commands for Manager there.

    test_directory
        Directory where tests are

    """
    ApiServer(webserver_queue, manager_queue, test_directory, debug).serve()
