#  This file is part of the myhdl library, a Python package for using
#  Python as a Hardware Description Language.
#
#  Copyright (C) 2003 Jan Decaluwe
#
#  The myhdl library is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public License as
#  published by the Free Software Foundation; either version 2.1 of the
#  License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful, but
#  WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#  Lesser General Public License for more details.

#  You should have received a copy of the GNU Lesser General Public
#  License along with this library; if not, write to the Free Software
#  Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA

""" Module that provides the Simulation class """

__author__ = "Jan Decaluwe <jan@jandecaluwe.com>"
__version__ = "$Revision$"
__date__ = "$Date$"

from __future__ import generators
import sys
import exceptions

import _simulator as sim
from _simulator import _siglist, _futureEvents
from Signal import Signal, _SignalWrap, _WaiterList
from delay import delay
from types import GeneratorType

schedule = _futureEvents.append
            
class Simulation(object):

    """ Simulation class.

    Methods:
    run -- run a simulation for some duration

    """

    def __init__(self, *args):
        """ Construct a simulation object.

        *args -- list of arguments. Each argument is a generator or
                 a nested sequence of generators.

        """
        sim._time = 0
        self._waiters = _flatten(*args)
        del _futureEvents[:]
        del _siglist[:]
        self.cosim = sim._cosim

    def run(self, duration=None, quiet=0):
        
        """ Run the simulation for some duration.

        duration -- specified simulation duration (default: forever)
        quiet -- don't print StopSimulation messages (default: off)
        
        """
        
        waiters = self._waiters
        maxTime = None
        if duration:
            stop = _Waiter(None)
            stop.hasRun = 1
            maxTime = sim._time + duration
            schedule((maxTime, stop))

        cosim = self.cosim
        running = 0
            
        t = sim._time
        while 1:
            try:
                for s in _siglist:
                    waiters.extend(s._update())
                del _siglist[:]

                if cosim and running:
                    cosim._put()
                
                while waiters:
                    waiter = waiters.pop(0)
                    if waiter.hasRun or not waiter.hasGreenLight():
                        continue
                    try:
                        clauses, clone = waiter.next()
                    except StopIteration:
                        if waiter.caller:
                            waiters.append(waiter.caller)
                        continue
                    for clause in clauses:
                        if type(clause) is _WaiterList:
                            clause.append(clone)
                        elif isinstance(clause, Signal):
                            clause._eventWaiters.append(clone)
                        elif type(clause) is delay:
                            schedule((t + clause._time, clone))
                        elif type(clause) is GeneratorType:
                            waiters.append(_Waiter(clause, clone))
                        elif type(clause) is join:
                            waiters.append(_Waiter(clause._generator(), clone))
                        elif clause is None:
                            waiters.append(clone)
                        else:
                            raise TypeError, "Incorrect yield clause type"

                if cosim:
                    cosim._get()

                if _siglist: continue
                if t == maxTime:
                    raise StopSimulation, "Simulated for duration %s" % duration

                if _futureEvents:
                    _futureEvents.sort()
                    t = sim._time = _futureEvents[0][0]
                    while _futureEvents:
                        newt, event = _futureEvents[0]
                        if newt == t:
                            if type(event) is _Waiter:
                                waiters.append(event)
                            else:
                                waiters.extend(event.apply())
                            del _futureEvents[0]
                        else:
                            break
                else:
                    raise StopSimulation, "No more events"
                
            except StopSimulation, e:
                if not quiet:
                    kind, value, traceback = sys.exc_info()
                    msg = str(kind)
                    msg = msg[msg.rindex('.')+1:]
                    if str(e):
                        msg += ": %s" % e
                    print msg
                if _futureEvents:
                    return 1
                return 0
                
 
def _flatten(*args):
    res = []
    for arg in args:
        if type(arg) is GeneratorType:
            res.append(_Waiter(arg))
        else:
            for item in arg:
                res.extend(_flatten(item))
    return res


class _Waiter(object):
    
    def __init__(self, generator, caller=None, semaphore=None):
        self.generator = generator
        self.hasRun = 0
        self.caller = caller
        self.semaphore = None
        
    def next(self):
        self.hasRun = 1
        clone = _Waiter(self.generator, self.caller, self.semaphore)
        clause = self.generator.next()
        if type(clause) is tuple:
            return clause, clone
        elif type(clause) is join:
            n = len(clause._args)
            clone.semaphore = _Semaphore(n)
            return clause._args, clone
        else:
            return (clause,), clone
    
    def hasGreenLight(self):
        if self.semaphore:
            self.semaphore.val -= 1
            if self.semaphore.val != 0:
                return 0
        return 1
    
    def clone(self):
        return _Waiter(self.generator, self.caller, self.semaphore)
    
        
class _Semaphore(object):
    def __init__(self, val=1):
        self.val = val
        
        
class StopSimulation(exceptions.Exception):
    """ Basic exception to stop a Simulation """
    pass


class join(object):

    """ Join trigger objects to form a single trigger object. """
    
    def __init__(self, *args):
        """ Construct join object

        *args -- list of trigger object arguments.
        
        """        
        
        self._args = args
        
    def _generator(self):
        yield join(*self._args)
        
