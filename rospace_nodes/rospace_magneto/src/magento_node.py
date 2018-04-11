#!/usr/bin/env python
#  @copyright Copyright (c) 2018, Michael Pantic (michael.pantic@gmail.com)
#
# @license zlib license
#
# This file is licensed under the terms of the zlib license.
# See the LICENSE.md file in the root of this repository
# for complete details.
import rospy
from geometry_msgs.msg import Vector3Stamped, WrenchStamped

from rospace_lib.actuators import *


def callback_B_field(data):
    B_field_vector = np.zeros(3)
    B_field_vector[0] = data.vector.x
    B_field_vector[1] = data.vector.y
    B_field_vector[2] = data.vector.z

    torquer.set_B_field(B_field_vector)

    # get current torque
    torque = torquer.get_torque()

    msg = WrenchStamped()
    msg.header.stamp = data.header.stamp
    msg.wrench.torque.x = torque

    pubTorque.publish(msg)


def callback_I_magneto(data):
    I_vector = np.zeros(3)
    I_vector[0] = data.vector.x
    I_vector[1] = data.vector.y
    I_vector[2] = data.vector.z

    torquer.set_I(I_vector[0])


if __name__ == '__main__':
    try:
        torquer = OneAxisMagnetoTorquer()
        rospy.init_node('imu_node', anonymous=True)

        last_callback_time = rospy.Time(0,0)
        pubTorque = rospy.Publisher("force", WrenchStamped, queue_size=10)
        subsB = rospy.Subscriber("B_field", Vector3Stamped, callback_B_field)
        subsI = rospy.Subscriber("I_magneto", Vector3Stamped, callback_I_magneto)

    except rospy.ROSInterruptException:
        pass