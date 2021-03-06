# Copyright (c) 2018, Christian Lanegger (lanegger.christian@gmail.com)
#
# SPDX-License-Identifier: Zlib
#
# This file is licensed under the terms of the zlib license.
# See the LICENSE.md file in the root of this repository
# for complete details. The contributors to this file maybe
# found in the SCM logs or in the AUTHORS.md file.

import rospy
import inspect
import time
from time import sleep
from threading import RLock
import Queue


from rospace_lib.clock import *
from rosgraph_msgs.msg import Clock


class SimTimePublisher(object):
    """
    Class handling the simulation time.

    The node driving the simulation time should call
    this class and use its methods to set up and update
    the simulation time.

    This class sets up the simulation time depending on the parameters given by
    ros and then initializes the other epoch_clock classes, to start the
    ros service, the time GUI and to ensure accesibility of the current
    simulation time for every ros node.

    Only one node can call this class!
    """

    _sim_time_setup_requested = False  # True if node requests to drive time

    def __init__(self):
        # Internal members:
        self._time_driving_node = ''    # name of node driving time
        self._epoch_now = None          # current epoch @ time step
        self._comp_time = None          # wall time passed in one iteration
        self._SimTime = None            # holds SimTimeUpdater object
        self._lock = RLock()            # lock for thread safety
        self._queue = Queue.Queue()      # queue to return epoch_now

    @property
    def datetime_oe_epoch(self):
        """Return initial epoch of orbital elements.

        Returns:
            datetime: epoch of orbital elements

        """
        if self._SimTime is not None:
            return self._SimTime.datetime_oe_epoch
        else:
            return None

    @property
    def time_shift_passed(self):
        """Return Bool if simulation time shift passed (desired initial time started).

        Returns:
            Bool: True if time_shift passed and simulation started

        """
        if self._SimTime is not None:
            return self._SimTime.time_shift_passed
        else:
            return None

    def _publish_sim_time(self):
        """Update and publish simulation time. Epoch_now is changed here."""
        msg_cl = Clock()
        [msg_cl, self._epoch_now] = self._SimTime.updateClock(msg_cl)
        self.pub_clock.publish(msg_cl)

    def set_up_simulation_time(self):
        """Set up simulation time. Has to be called by driving node before start.

        This method locks the use of all other methods of this class to the
        first node requesting to drive the simulation time. Once requested,
        no other node should influence the update of the simulation time.

        Also the time 0 is published to the clock topic, in case
        any node cannot handle if nothing is published to /clock.

        Returns:
            bool: if time shift is present. Can be used as condition to
                  for publishing messages only after time shift passed

        Raises:
            RuntimeError: if method called more than once per simulation

        """
        self._lock.acquire()

        if not SimTimePublisher._sim_time_setup_requested:
            SimTimePublisher._sim_time_setup_requested = True
            frame = inspect.currentframe().f_back
            filename = inspect.getframeinfo(frame)[0]
            self._time_driving_node = filename
            rospy.loginfo("Time is being driven by the node %s.",
                          str(self._time_driving_node))

            # get defined simulation parameters from yaml as dictionary
            sim_parameter = rospy.get_param("scenario/simulation_time")

            self._SimTime = SimTimeUpdater(**sim_parameter)

            rospy.loginfo("Epoch of init. Orbit Elements = " +
                          self._SimTime.datetime_oe_epoch.strftime("%Y-%m-%d %H:%M:%S"))
            rospy.loginfo("Realtime Factor = " + str(self._SimTime.realtime_factor))

            # set publish frequency & time step size as ros parameter before
            # setting /epoch parameter to ensure Epoch class finds them
            rospy.set_param('/publish_freq', self._SimTime.frequency)
            rospy.set_param('/time_step_size', str(self._SimTime.step_size))
            rospy.set_param('/epoch',
                            self._SimTime.datetime_oe_epoch.strftime("%Y-%m-%d %H:%M:%S"))

            self.pub_clock = rospy.Publisher('/clock', Clock, queue_size=10)

            # Start GUI clock service on new thread
            if rospy.has_param("/start_running"):
                self.ClockService = \
                    SimTimeService(self._SimTime.realtime_factor,
                                   self._SimTime.frequency,
                                   self._SimTime.step_size,
                                   rospy.get_param("/start_running"))
            else:
                self.ClockService = \
                    SimTimeService(self._SimTime.realtime_factor,
                                   self._SimTime.frequency,
                                   self._SimTime.step_size)

            self.epoch = Epoch()
            self._epoch_now = self.epoch.now()

        else:
            raise RuntimeError("Time is already being driven by " +
                               self._time_driving_node + ". Only one node " +
                               "can drive simulation time.")

        self._lock.release()

    def update_simulation_time(self):
        """Update simulation time.

        Driving node has to call this method at the very beginning of every
        iteration step.

        Also if any changes to time paramaters have been set in GUI they are
        updated here before publishing.

        This method also returns the current epoch as datetime object. This
        is done, since somethimes obtaining this object through the epoch
        class right after publishing returns the old object, resulting in
        skipping the next timestep.

        Returns:
            datetime.datetime: current epoch as datetime object

        Raises:
            RuntimeError: If used without the sleep_to_keep_frequency method

        """
        self._lock.acquire()

        if self._comp_time is not None:
            raise RuntimeError("sleep_to_keep_frequency() was not called " +
                               "at end of the loop of the driving node!")

        frame = inspect.currentframe().f_back
        file = inspect.getframeinfo(frame)[0]
        if SimTimePublisher._sim_time_setup_requested and \
                file == self._time_driving_node:
            self._comp_time = time.clock()

            if (self.ClockService.realtime_factor !=
                    self._SimTime.realtime_factor or
                self.ClockService.step_size !=  # frequency = 0 - RT doesn't change
                    self._SimTime.step_size):
                self._SimTime.updateTimeFactors(
                    self.ClockService.realtime_factor,
                    self.ClockService.frequency,
                    self.ClockService.step_size)
                self.epoch._changeFrequency(self.ClockService.frequency)
                self.epoch._changeStep(self.ClockService.step_size)

            if self.ClockService.SimRunning:
                # Wait for other nodes which subscribed to service (if any)
                while self.ClockService.syncSubscribers > 0:
                    if self.ClockService.readyCount >= \
                            self.ClockService.syncSubscribers:
                        self.ClockService.updateReadyCount(reset=True)
                        break

                # update clock
                self._publish_sim_time()

        self._queue.put(self._epoch_now)

        self._lock.release()

        return self._queue.get()

    def sleep_to_keep_frequency(self):
        """Sleep if simulation is quicker than requested. Warn if slower.

        Has to be called by driving node at the end of every iteration step!
        """
        self._lock.acquire()
        if self._SimTime.frequency > 0:
            # calculate reminding sleeping time
            sleep_time = 1 / self._SimTime.frequency - (time.clock() - self._comp_time)

            if sleep_time > 0:
                sleep(sleep_time)
            elif self.ClockService.syncSubscribers == 0:
                rospy.logwarn("Driving node too slow for publishing frequency.")

            self._comp_time = None
        else:
            self._comp_time = None

        self._lock.release()
