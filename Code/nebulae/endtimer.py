import timeit

class EndTimer(object):
    def __init__(self):
        self._start = timeit.default_timer()

    def end(self):
        return int((timeit.default_timer() - self._start) * 1000)