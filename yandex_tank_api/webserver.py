#!/usr/bin/env python
"""
Yandex.Tank HTTP API: request handling code
"""

import tornado.ioloop
import tornado.web
try:
    from pyjade.ext.tornado import patch_tornado
    patch_tornado()
    USE_JADE = True
except:  # pylint: disable=W0702
    USE_JADE = False

import os.path
import os
import json
import uuid
import multiprocessing
import datetime

import yandex_tank_api.common as common

# TODO: make transfer size limit configurable
TRANSFER_SIZE_LIMIT = 128 * 1024


class APIHandler(tornado.web.RequestHandler):  # pylint: disable=R0904

    """
    Parent class for API handlers
    """

    def initialize(self, out_queue, sessions, working_dir):  # pylint: disable=W0221
        """
        sessions
            dict: session_id->session_status
        """
        # pylint: disable=W0201
        self.out_queue = out_queue
        self.sessions = sessions
        self.working_dir = working_dir

    def reply_json(self, status_code, reply):
        """
        Reply with a json and a specified code
        """
        if status_code != 418:
            self.set_status(status_code)
        else:
            self.set_status(status_code, 'I\'m a teapot!')
        self.set_header('Content-Type', 'application/json')
        reply_str = json.dumps(reply, indent=4)
        self.finish(reply_str)

    def write_error(self, status_code, **kwargs):
        if self.settings.get("debug"):
            tornado.web.RequestHandler(self, status_code, **kwargs)
            return

        self.set_header('Content-Type', 'application/json')
        if 'exc_info' in kwargs and status_code >= 400 and status_code < 500:
            self.reply_json(
                status_code, {'reason': str(kwargs['exc_info'][1])})
        else:
            self.reply_json(status_code, {'reason': self._reason})


class RunHandler(APIHandler):  # pylint: disable=R0904

    """
    Handles POST /run and get /run
    """

    def post(self):

        offered_test_id = self.get_argument("test", uuid.uuid4().hex)
        breakpoint = self.get_argument("break", "finished")
        config = self.request.body

        # Check existing sessions
        running_test = None
        for test in self.sessions.values():
            if test['status'] not in ['success', 'failed']:
                running_test = test

        # 503 if any running session exists
        if running_test is not None:
            reply = {'reason': 'Another test is already running.'}
            reply.update(running_test)
            self.reply_json(503, reply)
            return

        # 400 if invalid breakpoint
        if not common.is_valid_break(breakpoint):
            self.reply_json(
                400,
                {'reason': 'Specified break is not a valid test stage name.',
                 'hint': {'breakpoints': common.get_valid_breaks()}}
            )
            return
        try:
            session_id = self._generate_session_id(offered_test_id)
        except RuntimeError as err:
            self.reply_json(503, {'reason': str(err)})
            return


        # Remember that such session exists
        self.sessions[session_id] = {
            'status': 'starting',
            'break': breakpoint,
            'test': session_id
        }
        # Post run command to manager queue
        self.out_queue.put({'session': session_id,
                            'cmd': 'run',
                            'break': breakpoint,
                            'test': session_id,
                            'config': config})

        self.reply_json(200, {
            "test": session_id,
            "session": session_id,
        })

    def _generate_session_id(self, offered_id):
        """
        Should only be used if no tests are running
        """
        if not offered_id:
            offered_id = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        #This should use one or two attempts in typical cases
        for n_attempt in xrange(10000000000):
            session_id = "%s_%10d" % (offered_id, n_attempt)
            test_status_file = os.path.join(
                self.working_dir,
                session_id,
                'status.json'
            )
            if not os.path.exists(test_status_file):
                return session_id
            n_attempt += 1
        raise RuntimeError("Failed to generate session id")

    def get(self):
        breakpoint = self.get_argument("break", "finished")
        session_id = self.get_argument("session")
        self.set_header("Content-type", "application/json")

        # 400 if invalid breakpoint
        if not common.is_valid_break(breakpoint):
            self.reply_json(
                400, {
                    'reason': 'Specified break is not a valid test stage name.',
                    'hint':
                    {'breakpoints': common.get_valid_breaks()}
                })
            return

        # 404 if no such session
        if not session_id in self.sessions:
            self.reply_json(404, {'reason': 'No session with this ID.'})
            return
        status_dict = self.sessions[session_id]

        # 500 if failed
        if status_dict['status'] == 'failed':
            reply = {'reason': 'Session failed.'}
            reply.update(status_dict)
            self.reply_json(500, reply)
            return

        # 418 if in higher state or not running
        if status_dict['status'] == 'success' or\
                common.is_A_earlier_than_B(breakpoint, status_dict['break']):
            reply = {'reason': 'I am a teapot! I know nothing of time-travel!',
                     'hint': {'breakpoints': common.get_valid_breaks()}}
            reply.update(status_dict)
            self.reply_json(418, reply)
            return

        # Post run command to manager queue
        self.out_queue.put({'session': session_id,
                            'cmd': 'run',
                            'break': breakpoint})

        self.reply_json(
            200, {'reason': "Will try to set break before " + breakpoint})


class StopHandler(APIHandler):  # pylint: disable=R0904

    """
    Handles GET /stop
    """

    def get(self):
        session_id = self.get_argument("session")
        if session_id in self.sessions:
            if self.sessions[session_id]['status'] not in ['success', 'failed']:
                self.out_queue.put({
                    'cmd': 'stop',
                    'session': session_id,
                })
                self.reply_json(
                    200, {'reason': 'Will try to stop tank process.'})
                return
            else:
                self.reply_json(
                    409,
                    {'reason': 'This session is already stopped.',
                     'session': session_id}
                )
                return
        else:
            self.reply_json(404, {
                'reason': 'No session with this ID.',
                'session': session_id,
            })
            return


class StatusHandler(APIHandler):  # pylint: disable=R0904

    """
    Handle GET /status?
    """

    def get(self):
        session_id = self.get_argument("session", default=None)
        if session_id:
            if session_id in self.sessions:
                self.reply_json(200, self.sessions[session_id])
            else:
                self.reply_json(404, {
                    'reason': 'No session with this ID.',
                    'session': session_id,
                })
        else:
            self.reply_json(200, self.sessions)


class ArtifactHandler(APIHandler):  # pylint: disable=R0904

    """
    Handle GET /atrifact?
    """

    def get(self):
        session_id = self.get_argument("test", self.get_argument("session"))

        filename = self.get_argument("filename", None)

        # look for test directory
        if not os.path.exists(os.path.join(self.working_dir, session_id)):
            self.reply_json(404, {
                'reason': 'No test with this ID found',
                'test': session_id,
            })
            return

        # look for status.json (any test that went past lock stage should have
        # it)
        if not os.path.exists(os.path.join(
                self.working_dir,
                session_id,
                'status.json'
        )):
            self.reply_json(404, {
                'reason': 'Test was not performed, no artifacts.',
                'test': session_id,
            })
            return

        if filename:
            filepath = os.path.join(self.working_dir, session_id, filename)
            if os.path.exists(filepath):
                file_size = os.stat(filepath).st_size

                if file_size > TRANSFER_SIZE_LIMIT and\
                    any(s['status'] not in ['success', 'failed'] and
                        common.is_A_earlier_than_B(
                            s['current_stage'],
                            'postprocess')
                        for s in self.sessions.values()
                        ):
                    self.reply_json(503, {
                        'reason': 'File is too large and test is running',
                        'test': session_id,
                        'filename': filename,
                        'filesize': file_size,
                        'limit': TRANSFER_SIZE_LIMIT,
                    })
                    return
                else:
                    self.set_header("Content-type", "application/octet-stream")
                    with open(filepath, 'rb') as artifact_file:
                        data = artifact_file.read()
                        self.write(data)
                    self.finish()
                    return
            else:
                self.reply_json(404, {
                    'reason': 'No such file',
                    'test': session_id,
                    'filename': filename,
                })
                return
        else:
            basepath = os.path.join(self.working_dir, session_id)
            onlyfiles = [
                f for f in os.listdir(basepath)
                if os.path.isfile(os.path.join(basepath, f))
            ]
            self.reply_json(200, onlyfiles)


class StaticHandler(tornado.web.RequestHandler):  # pylint: disable=R0904

    """
    Handle /manager.html
    """

    def initialize(self, templ):  # pylint: disable=W0221
        self.template = templ  # pylint: disable=W0201

    def get(self):
        self.render(self.template)


class ApiServer(object):
    """ API server class"""

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

        handlers = [
            (r"/run", RunHandler, handler_params),
            (r"/stop", StopHandler, handler_params),
            (r"/status", StatusHandler, handler_params),
            (r"/artifact", ArtifactHandler, handler_params)
        ]

        if USE_JADE:
            handlers.append(
                (r"/manager\.html$", StaticHandler,
                 {"template": "manager.jade"})
            )

        self.app = tornado.web.Application(
            handlers,
            template_path=os.path.join(os.path.dirname(__file__), "templates"),
            static_path=os.path.join(os.path.dirname(__file__), "static"),
            debug=debug,
        )

    def update_status(self):
        """Read status messages from manager"""
        try:
            while True:
                message = self.in_queue.get_nowait()
                session_id = message.get('session')
                del message['session']
                # Test ID and break are always present in message from Manager
                self.sessions[session_id] = message
        except multiprocessing.queues.Empty:
            pass

    def serve(self):
        """
        Run tornado ioloop
        """
        self.app.listen(8888)
        ioloop = tornado.ioloop.IOLoop.instance()
        update_cb = tornado.ioloop.PeriodicCallback(
            self.update_status, 100, ioloop)
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
