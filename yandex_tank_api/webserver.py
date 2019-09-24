#!/usr/bin/env python
"""
Yandex.Tank HTTP API: request handling code
"""

import tornado.httpserver
import tornado.ioloop
import tornado.web
import os.path
import os
import json
import uuid
import multiprocessing
import datetime
import time
import yaml
import yandex_tank_api.common as common
from retrying import retry
from yandextank.validator.validator import TankConfig
from yandextank.core.consoleworker import load_core_base_cfg, load_local_base_cfgs

TRANSFER_SIZE_LIMIT = 128 * 1024
DEFAULT_HEARTBEAT_TIMEOUT = 600


class APIHandler(tornado.web.RequestHandler):  # pylint: disable=R0904
    """
    Parent class for API handlers
    """

    def initialize(self, server):  # pylint: disable=W0221
        """
        sessions
            dict: session_id->session_status
        """
        # pylint: disable=W0201
        server.read_status_updates()
        self.srv = server

    def reply_json(self, status_code, reply):
        """
        Reply with a json and a specified code
        """
        self.set_status(status_code)
        self.set_header('Content-Type', 'application/json')
        reply_str = json.dumps(reply, indent=4)
        self.finish(reply_str)

    def reply_reason(self, code, reason):
        return self.reply_json(code, {'reason': reason})

    def write_error(self, status_code, **kwargs):
        if self.settings.get('debug'):
            tornado.web.RequestHandler(self, status_code, **kwargs)
            return

        self.set_header('Content-Type', 'application/json')
        if 'exc_info' in kwargs and 400 <= status_code < 500:
            self.reply_json(status_code, {'reason': str(kwargs['exc_info'][1])})
        else:
            self.reply_json(status_code, {'reason': self._reason})


class ValidateConfgiHandler(APIHandler):  # pylint: disable=R0904
    """
    Handles POST /validate
    """

    def post(self):
        config = self.request.body
        try:
            config = yaml.safe_load(config)
            assert isinstance(config, dict), 'Config must be YAML dict'
        except yaml.YAMLError:
            self.reply_reason(400, 'Config is not a valid YAML')
            return
        except AssertionError as aexc:
            self.reply_reason(400, repr(aexc))
            return
        _, errors, configinitial = TankConfig(
            [load_core_base_cfg()] + load_local_base_cfgs() + [config],
            with_dynamic_options=False
        ).validate()

        self.reply_json(200, {'config': yaml.safe_dump(config), 'errors': errors})
        return


class RunHandler(APIHandler):  # pylint: disable=R0904
    """
    Handles POST /run and get /run
    """

    def post(self):

        offered_test_id = self.get_argument(
            'test', datetime.datetime.now().strftime('%Y%m%d%H%M%S'))
        breakpoint = self.get_argument('break', 'finished')
        hb_timeout = self.get_argument('heartbeat', None)

        config = self.request.body

        # 503 if any running session exists
        if self.srv.running_id is not None:
            reply = {'reason': 'Another session is already running.'}
            reply.update(self.srv.running_status)
            self.reply_json(503, reply)
            return

        # 400 if invalid breakpoint
        if not common.is_valid_break(breakpoint):
            self.reply_json(
                400, {
                    'reason': 'Specified break is not a valid test stage name.',
                    'hint': {
                        'breakpoints': common.get_valid_breaks()
                    }
                })
            return
        try:
            session_id = self.srv.create_session_dir(offered_test_id)
        except RuntimeError as err:
            self.reply_reason(500, str(err))
            return

        # Remember that such session exists
        self.srv.set_session_status(
            session_id, {'status': 'starting',
                         'break': breakpoint})
        # Post run command to manager queue
        self.srv.cmd({
            'session': session_id,
            'cmd': 'run',
            'break': breakpoint,
            'config': config
        })

        self.srv.heartbeat(session_id, hb_timeout)
        self.reply_json(200, {'session': session_id})

    def get(self):
        breakpoint = self.get_argument('break', 'finished')
        session_id = self.get_argument('session')
        hb_timeout = self.get_argument('heartbeat', None)

        self.set_header('Content-type', 'application/json')

        # 400 if invalid breakpoint
        if not common.is_valid_break(breakpoint):
            self.reply_json(
                400, {
                    'reason': 'Specified break is not a valid test stage name.',
                    'hint': {
                        'breakpoints': common.get_valid_breaks()
                    }
                })
            return

        # 404 if no such session
        try:
            status_dict = self.srv.status(session_id)
        except KeyError:
            self.reply_reason(404, 'No session with this ID.')
            return

        if session_id != self.srv.running_id:
            self.reply_reason(
                418,
                'I\'m a teapot! Can\'t set break for session that\'s not running!')
            return

        # 418 if in higher state
        if common.is_a_earlier_than_b(breakpoint, status_dict['break']):
            reply = {
                'reason': 'I\'m a teapot! I know nothing of time-travel!',
                'hint': {
                    'breakpoints': common.get_valid_breaks()
                }
            }
            reply.update(status_dict)
            self.reply_json(418, reply)
            return

        # Post run command to manager queue
        self.srv.cmd({'session': session_id, 'cmd': 'run', 'break': breakpoint})

        self.srv.heartbeat(session_id, hb_timeout)
        self.reply_reason(200, 'Will try to set break before ' + breakpoint)


class StopHandler(APIHandler):  # pylint: disable=R0904
    """
    Handles GET /stop
    """

    def get(self):
        session_id = self.get_argument('session')

        try:
            self.srv.status(session_id)
        except KeyError:
            self.reply_reason(404, 'No session with this ID.')
            return
        if self.srv.running_id == session_id:
            self.srv.cmd({'cmd': 'stop', 'session': session_id})
            self.reply_reason(200, 'Will try to stop tank process.')
            return
        else:
            self.reply_reason(409, 'This session is already stopped.')
            return


class StatusHandler(APIHandler):  # pylint: disable=R0904
    """
    Handle GET /status?
    """

    def get(self):
        session_id = self.get_argument('session', default=None)
        if session_id:
            try:
                status = self.srv.status(session_id)
            except KeyError:
                self.reply_reason(404, 'No session with this ID.')
            self.srv.heartbeat(session_id)
            self.reply_json(200, status)
        else:
            self.reply_json(200, self.srv.all_sessions)


class UploadHandler(APIHandler):  # pylint: disable=R0904
    """
    Handles POST /upload
    """

    def post(self):
        session_id = self.get_argument('session')
        if session_id != self.srv.running_id:
            self.reply_reason(404, 'Specified session is not running')
            return

        filename = self.get_argument('filename')
        contents = self.request.body

        filepath = self.srv.session_file(session_id, filename)
        tmp_path = filepath + str(uuid.uuid4())

        with open(tmp_path, 'wb') as upload_file:
            upload_file.write(contents)
        os.rename(tmp_path, filepath)

        self.srv.heartbeat(session_id)
        self.reply_reason(200, 'File uploaded')


class ArtifactHandler(APIHandler):  # pylint: disable=R0904
    """
    Handle GET /atrifact?
    """

    def get(self):
        session_id = self.get_argument('session')

        filename = self.get_argument('filename', None)
        maxsize = self.get_argument('maxsize', None)

        # look for test directory
        if not os.path.exists(self.srv.session_dir(session_id)):
            self.reply_reason(404, 'No session with this ID found')
            return

        # look for status.json (any test that went past lock stage should have
        # it)
        if self.srv.is_empty_session(session_id):
            self.reply_reason(404, 'Test was not performed, no artifacts.')
            return

        if not filename:
            basepath = self.srv.session_dir(session_id)
            onlyfiles = [
                f for f in os.listdir(basepath)
                if os.path.isfile(os.path.join(basepath, f))
            ]
            self.reply_json(200, onlyfiles)
            return

        filepath = self.srv.session_file(session_id, filename)
        if not os.path.exists(filepath):
            self.reply_reason(404, 'No such file in test artifacts')
            return
        file_size = os.stat(filepath).st_size

        if maxsize is not None and file_size > maxsize:
            self.reply_json(
                409, {
                    'reason':
                    'File does not fit into the size limit specified by the client.',
                    'filesize': file_size
                })
            return

        if file_size > TRANSFER_SIZE_LIMIT:
            try:
                cur_stage = self.srv.running_status['current_stage']
            except KeyError:
                pass
            else:
                if common.is_a_earlier_than_b(cur_stage, 'postprocess'):
                    self.reply_json(
                        503, {
                            'reason':
                            'File is too large and a session is running',
                            'running_session': self.srv.running_id,
                            'filesize': file_size,
                            'limit': TRANSFER_SIZE_LIMIT
                        })
                    return
        self.set_header('Content-type', 'application/octet-stream')
        with open(filepath, 'rb') as artifact_file:
            while True:
                data = artifact_file.read(TRANSFER_SIZE_LIMIT)
                if not data:
                    break
                self.write(data)
                self.flush()
        self.finish()
        self.srv.heartbeat(session_id)


class StaticHandler(tornado.web.RequestHandler):  # pylint: disable=R0904
    """
    Handle /manager.html
    """

    def initialize(self, template):  # pylint: disable=W0221
        self.template = template  # pylint: disable=W0201

    def get(self):
        self.render(self.template)


class ApiServer(object):
    """ API server class"""

    def __init__(self, in_queue, out_queue, working_dir, debug=False):
        self._in_queue = in_queue
        self._out_queue = out_queue
        self._working_dir = working_dir
        self._running_id = None
        self._sessions = {}
        self._hb_deadline = None
        self._hb_timeout = DEFAULT_HEARTBEAT_TIMEOUT

        handler_params = dict(server=self)

        handlers = [
            (r'/validate', ValidateConfgiHandler, handler_params),
            (r'/run', RunHandler, handler_params),
            (r'/stop', StopHandler, handler_params),
            (r'/status', StatusHandler, handler_params),
            (r'/artifact', ArtifactHandler, handler_params),
            (r'/upload', UploadHandler, handler_params),
            (r'/manager\.html$', StaticHandler, dict(template='manager.jade'))
        ]

        self.app = tornado.web.Application(
            handlers,
            template_path=os.path.join(os.path.dirname(__file__), 'templates'),
            static_path=os.path.join(os.path.dirname(__file__), 'static'),
            debug=debug, )

    def read_status_updates(self):
        """Read status messages from manager"""
        try:
            while True:
                message = self._in_queue.get_nowait()
                session_id = message.get('session')
                del message['session']
                self.set_session_status(session_id, message)
        except multiprocessing.queues.Empty:
            pass

    def check(self):
        """Read status messages from manager and check heartbeat"""
        self.read_status_updates()

        if self._running_id and self._hb_deadline is not None\
                and time.time() > self._hb_deadline:

            self.cmd({
                'cmd': 'run',
                'session': self._running_id,
                'break': 'finished'
            })
            self.cmd({'cmd': 'stop', 'session': self._running_id})

    def set_session_status(self, session_id, new_status):
        """Remember session status and change running_id"""

        if new_status['status'] in ['success', 'failed']:
            if self._running_id == session_id:
                self._running_id = None
        else:
            self._running_id = session_id

        self._sessions[session_id] = new_status

    def heartbeat(self, session_id, new_timeout=None):
        """
        Set new heartbeat timeout (if sepcified)
        and reset heartbeat deadline
        """
        if new_timeout is not None:
            self._hb_timeout = new_timeout
        if session_id == self._running_id and self._running_id is not None:
            self._hb_deadline = time.time() + self._hb_timeout

    def session_dir(self, session_id):
        """Return working directory for given session id"""
        return os.path.join(self._working_dir, session_id)

    def session_file(self, session_id, filename):
        """Return file path for given session id"""
        return os.path.join(self._working_dir, session_id, filename)

    @retry(stop_max_attempt_number=10, retry_on_exception=lambda e: isinstance(e, OSError))
    def create_session_dir(self, offered_id):
        """
        Returns generated session id
        Should only be used if no tests are running
        """
        if not offered_id:
            offered_id = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
        session_id = '{}_{}'.format(offered_id, uuid.uuid4().hex)
        session_dir = self.session_dir(session_id)
        os.makedirs(session_dir)
        return session_id

    def is_empty_session(self, session_id):
        """Return true if the session did not get past the lock stage"""
        return not os.path.exists(self.session_file(session_id, 'status.json'))

    def cmd(self, message):
        """Put commad into manager queue"""
        self._out_queue.put(message)

    @property
    def all_sessions(self):
        """Get session status by ID, can raise KeyError"""
        return self._sessions

    def status(self, session_id):
        """Get session status by ID, can raise KeyError"""
        return self._sessions[session_id]

    @property
    def running_id(self):
        """Return ID of running session"""
        return self._running_id

    @property
    def running_status(self):
        """Return status of running session , can raise KeyError"""
        return self.status(self._running_id)

    def serve(self):
        """
        Run tornado ioloop
        """
        server = tornado.httpserver.HTTPServer(self.app)
        server.listen(8888)
        tornado.ioloop.IOLoop.current().start()


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
