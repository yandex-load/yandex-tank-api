import tornado

#Test stage order, internal protocol description, etc...
import common

def run(webserver_queue, manager_queue):
    """Target for webserver process.
    The only function ever used by the Manager.

    webserver_queue
        Read statuses from Manager here.

    manager_queue
        Write commands for Manager there.
    
    """
    raise NotImplementedError("Webserver not implemented")
