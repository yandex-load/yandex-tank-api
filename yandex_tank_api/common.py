"""
Commands from HTTP Server (from manager_queue):
    Run the test to the next break:
        {
        'session': '1a2b4f3c'
        'cmd':'run',
        'break': --- see break requests for tank
        'test': --- only when creating new session
        'config': --- only when creating new  session
        }
    Stop the test
        {
        'session': '1a2b4f3c'
        'cmd':'stop'
        }


Status reported by tank (from manager_queue):
    {
     'session': '1a2b4f3c'
     'test': 'DEATHSTAR-10-12345'
     'status': 'running'|'success'|'failure'
     'current_stage': --- current stage (from test_stage_order)
     'break': --- stage to make a break before
     'failures': --- [ {'stage': stage-at-which-failed,'reason': reason of failure },
                       {'stage':stage-of-next-failure,'reason':...},
                       ... ]
     }
=====

Break requests (into tank_queue):
    {'break': --- any stage from test_stage_order }

====
Status reported to HTTP Server (into webserver_queue):
    {
    'session': '1a2b4f3c'
    'test': 'DEATHSTAR-10-12345'
    'status': 'running'|'success'|'failed' (from tank or from  manager)
               running: the tank is running
               success: tank has exited and no failures occured
               failed: tank has exited and there were failures

    'stage': --- optional, from tank only.
                 This is the last stage that was executed.
    'break': --- optional, from tank only. The next break.
    'reason' : --- optional (from manager)
    'failures': --- optional, from tank only
    }
"""

import functools

TEST_STAGE_ORDER_AND_DEPS = [('init', set()), ('lock', 'init'),
                             ('configure', 'lock'), ('prepare', 'configure'),
                             ('start', 'prepare'), ('poll', 'start'),
                             ('end', 'lock'), ('postprocess', 'end'),
                             ('unlock', 'lock'), ('finished', set())]

TEST_STAGE_ORDER = [stage for stage, _ in TEST_STAGE_ORDER_AND_DEPS]
TEST_STAGE_DEPS = {stage: dep for stage, dep in TEST_STAGE_ORDER_AND_DEPS}


def is_a_earlier_than_b(stage_a, stage_b):
    """Slow but reliable"""
    return TEST_STAGE_ORDER.index(stage_a) < TEST_STAGE_ORDER.index(stage_b)


def get_valid_breaks():
    return TEST_STAGE_ORDER


def is_valid_break(brk):
    return brk in TEST_STAGE_ORDER


def memoized(fn):
    name = '__{}'.format(fn.__name__)

    @functools.wraps(fn)
    def fn_memoized(self):
        if not hasattr(self, name):
            setattr(self, name, fn(self))
        return getattr(self, name)

    return property(fn_memoized)
