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

class RunHandler(tornado.web.RequestHandler):
    def initialize(self, out_queue, sessions, working_dir):
        """
        sessions
            dict: session_id->session_status
        """
        self.out_queue = out_queue
        self.sessions = sessions
        self.working_dir = working_dir

    def post(self):

        test_id = self.get_argument("test", uuid.uuid4().hex)
        breakpoint = self.get_argument("break", "finished")
        session_id = uuid.uuid4().hex
        config = self.request.body

        self.set_header("Content-type", "application/json")

        #Check existing sessions
        running_session=None
        conflict_session=None
        for s in self.sessions.values():
            if s['status'] not in ['success','failed']:
                running_session=s
            if s['test']==test_id:
                conflict_session=s

        # 400 if invalid breakpoint
        if not breakpoint in common.test_stage_order:
            self.set_status(400)
            self.finish(json.dumps({'reason':'Invalid break point',
                                    'hint':
                                        {'breakpoints':common.test_stage_order}
                                   }))
            return

        # 409 if session with this test_id is already running
        if conflict_session is not None:
                self.set_status(409)
                self.finish(json.dumps(conflict_session))
                return

        # 409 if finished test with this test_id exists
        test_status_file=os.path.join(self.working_dir, test_id, 'status.json')
        if os.path.exists(test_status_file):
            self.set_status(409)
            self.finish(open(test_status_file).read())
            return


        # 503 if any running session exists (but no test_id conflict)
        if running_session is not None:
                self.set_status(503)
                self.finish(json.dumps(running_session))
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

        self.set_status(200)
        self.finish(json.dumps({
                               "test": test_id,
                               "session": session_id,
                               }))

    def get(self):
        breakpoint = self.get_argument("break", "finished")
        session_id = self.get_argument("session")
        self.set_header("Content-type", "application/json")

        # 400 if invalid breakpoint
        if not breakpoint in common.test_stage_order:
            self.set_status(400)
            self.finish(json.dumps({'reason':'Invalid break point',
                                    'hint':
                                        {'breakpoints':common.test_stage_order}
                                   }))
            return

        # 404 if no such session
        if not session_id in self.sessions:
            self.set_status(404)
            self.finish(json.dumps({'reason':'No session with this ID'}))
            return
        status_dict=self.sessions[session_id]

        # 500 if failed
        if status_dict['status'] == 'failed':
            self.set_status(500)
            self.finish(json.dumps(status_dict))
            return

        # 418 if in higher state or not running
        if status_dict['status'] == 'success' or common.is_A_earlier_than_B(breakpoint,status_dict['break']):
            reply={'reason':'I am a teapot! I know nothing of time-travel!',
                    'hint': {'breakpoints':common.test_stage_order} }
            reply.update(status_dict)
            self.set_status(418,reason="I'm a teapot!")
            self.finish(json.dumps(reply))
            return

        # Post run command to manager queue
        self.out_queue.put({'session':session_id,
                       'cmd':'run',
                       'break':breakpoint})

        self.set_status(200)

class StopHandler(tornado.web.RequestHandler):
    def initialize(self, out_queue, sessions, working_dir):
        self.out_queue = out_queue
        self.sessions = sessions

    def get(self):
        session_id = self.get_argument("session")
        if session_id:
            if session_id in self.sessions:
                if self.sessions[session_id]['status'] not in ['success','failed']:
                    self.out_queue.put({
                        'cmd': 'stop',
                        'session': session_id,
                    })
                    self.set_status(200)
                    return
                else:
                    self.set_status(409)
                    self.finish(json.dumps(
                        {
                            'reason': 'This session is already stopped',
                            'session': session_id,
                        }
                    ))
                    return
            else:
                self.set_status(404)
                self.finish(json.dumps({
                    'reason': 'No session with this ID found',
                    'session': session_id,
                }))
                return
        else:
            self.set_status(400)
            self.finish(json.dumps(
                {'reason': 'Specify an ID of a session you want to stop'}
            ))
            return


class StatusHandler(tornado.web.RequestHandler):
    def initialize(self, out_queue, sessions, working_dir):
        self.out_queue = out_queue
        self.sessions = sessions

    def get(self):
        print self.request.arguments

        session_id = self.get_argument("session",default=None)
        self.set_header("Content-type", "application/json")
        if session_id:
            if session_id in self.sessions:
                self.set_status(200)
                self.finish(json.dumps(
                    self.sessions[session_id]
                ))
            else:
                self.set_status(404)
                self.finish(json.dumps({
                    'reason': 'No session with this ID found',
                    'session': session_id,
                }))
        else:
            self.set_status(200)
            self.finish(json.dumps(
                self.sessions
            ))


class ArtifactHandler(tornado.web.RequestHandler):
    def initialize(self, out_queue, sessions, working_dir):
        self.out_queue = out_queue
        self.sessions = sessions
        self.working_dir = working_dir

    def get(self):
        test_id = self.get_argument("test")
        filename = self.get_argument("filename",None)


        # look for status.json (any test should have it)
        if not os.path.exists(os.path.join(self.working_dir, test_id, 'status.json')):
            self.set_header("Content-type", "application/json")
            self.set_status(404)
            self.finish(json.dumps({
                'reason': 'No test with this ID found',
                'test': test_id,
            }))
            return

        if filename:
            filepath = os.path.join(self.working_dir, test_id, filename)
            if os.path.exists(filepath):
                file_size = os.stat(filepath).st_size

                if file_size > TRANSFER_SIZE_LIMIT and any(s['status'] not in ['success','failed'] for s in self.sessions.values()):
                    self.set_header("Content-type", "application/json")
                    self.set_status(503)
                    self.finish(json.dumps({
                        'reason': 'File is too large and test is running',
                        'test': test_id,
                        'filename': filename,
                        'filesize': file_size,
                        'limit': TRANSFER_SIZE_LIMIT,
                    }))
                    return
                else:
                    self.set_header("Content-type", "application/octet-stream")
                    with open(filepath, 'rb') as f:
                        data = f.read()
                        self.write(data)
                    self.finish()
                    return
            else:
                self.set_header("Content-type", "application/json")
                self.set_status(404)
                self.finish(json.dumps({
                    'reason': 'No such file',
                    'test': test_id,
                    'filename': filename,
                }))
                return
        else:
            basepath = os.path.join(self.working_dir, test_id)
            onlyfiles = [
                f for f in os.listdir(basepath)
                if os.path.isfile(os.path.join(basepath, f))
            ]
            self.set_header("Content-type", "application/json")
            self.set_status(200)
            self.finish(json.dumps(onlyfiles))


class StaticHandler(tornado.web.RequestHandler):
    def initialize(self, template):
        self.template = template

    def get(self):
        self.render(self.template)


class ApiServer(object):
    def __init__(self, in_queue, out_queue, working_dir):
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
            debug=True,
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


def main(webserver_queue, manager_queue, test_directory):
    """Target for webserver process.
    The only function ever used by the Manager.

    webserver_queue
        Read statuses from Manager here.

    manager_queue
        Write commands for Manager there.

    test_directory
        Directory where tests are

    """
    ApiServer(webserver_queue, manager_queue, test_directory).serve()
