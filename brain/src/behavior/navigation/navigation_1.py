from __future__ import print_function

import math
import os
import random

import basebehavior.behaviorimplementation
import rospy
import tf
from geometry_msgs.msg import PoseStamped


class Navigation_x(basebehavior.behaviorimplementation.BehaviorImplementation):

    def implementation_init(self):
        self.waypoint = ['hallway1', 'waypoint1', 'arena1']
        self.aim_point = -1
        self.state_back_up = None
        self.stuck_position = None

        self.startNavigating = False
        self.data_path = '/brain/data/locations/lab.dat'
        # /home/borg/sudo/brain/data/locations
        self.storedLocations = {}
        self.read_stored_locations(os.environ['BORG'] + self.data_path)

        self.goto_movebase = self.ab.GotoMoveBase({'fileLocations': self.data_path})
        self.goto = self.ab.gotowrapper({})
        self.stuck = self.ab.sublabnavigation({})

        self.selected_behaviors = [
            ("goto_movebase", "True"),
            ("goto", "self.startNavigating == True"),
            ("stuck", "True"),
        ]

        self.state = 'enter'
        self.transform = tf.TransformListener()

    def implementation_update(self):
        if self.stuck.is_failed() and (self.state.startswith('go_to') or self.state == 'stuck'):
            print("Alice stuck!!!")

            if not self.state == 'stuck':
                self.state_back_up = self.state
                self.state = 'stuck'
                self.stuck_position = self.find_behind_point()
                self.set_goal(self.stuck_position)
            else:
                x = random.randint(0, 2)
                y = random.randint(0, 2)
                self.stuck_position = self.find_behind_point(x, y)
                self.set_goal(self.stuck_position)
            self.stuck = self.ab.sublabnavigation({})

        # elif self.state == 'stuck' and self.goto.is_finished():
        elif self.state == 'stuck' and self.check_if_close_to_the_goal(x=self.stuck_position['x'],
                                                                       y=self.stuck_position['y']):
            self.state = self.state_back_up
            self.set_goal(self.waypoint[self.aim_point])

        if self.state == 'enter':
            self.state = 'go_to_hall'
            self.aim_point = 0
            self.set_goal(self.waypoint[self.aim_point])
            self.startNavigating = True
            self.stuck = self.ab.sublabnavigation({})

        elif self.state == 'go_to_hall' and self.goto.is_finished():
            self.state = 'go_to_way'
            self.aim_point = 1
            self.body.say('I am navigating')
            self.set_goal(self.waypoint[self.aim_point])

        # elif self.state == 'go_to_hall' and self.goto.is_failed():
        #     self.set_goal(self.waypoint[1])

        elif self.state == 'go_to_way' and self.goto.is_finished():
            self.time = rospy.Time.now()
            self.state = 'wait3'
            self.body.say('I have arrived')

        # elif self.state == 'go_to_way' and self.goto.is_failed():
        #     self.set_goal(self.waypoint[0])
        #     self.body.say('I failed')
        #     self.body.say('I am navigating')

        elif self.state == 'wait3' and rospy.Time.now() - self.time > rospy.Duration(3):
            self.state = 'go_to_arena'
            self.aim_point = 2
            self.body.say('I am navigating')
            self.set_goal(self.waypoint[self.aim_point])

        elif self.state == 'go_to_arena' and self.goto.is_finished():
            self.time = rospy.Time.now()
            self.state = 'wait5'
            self.body.say('I have arrived')

        # elif self.state == 'go_to_arena' and self.goto.is_failed():
        #     self.set_goal(self.waypoint[2])
        #     self.body.say('I failed')

        elif self.state == 'wait5' and rospy.Time.now() - self.time > rospy.Duration(5):
            self.state = 'go_to_way2'
            self.aim_point = 1
            self.set_goal(self.waypoint[self.aim_point])
            self.body.say('I am navigating')

        elif self.state == 'go_to_way2' and self.check_if_close_to_the_goal(self.waypoint[1]):
            self.state = 'go_to_hall2'
            self.aim_point = 0
            self.set_goal(self.waypoint[self.aim_point])
            self.startNavigating = True

        elif self.state == 'go_to_hall2' and self.goto.is_finished():
            self.body.say('I have arrived')
            self.startNavigating = False
            self.set_finished()

    def check_if_close_to_the_goal(self, goal=None, x=None, y=None):
        self.transform.waitForTransform('/map', '/base_link', rospy.Time(0), rospy.Duration(0.5))
        trans, rot = self.transform.lookupTransform('/map', '/base_link', rospy.Time(0))

        if goal:
            distance = math.pow((self.storedLocations[goal]['x'] - trans[0]), 2) + math.pow(
                (self.storedLocations[goal]['y'] - trans[1]), 2)
        else:
            distance = math.pow((x - trans[0]), 2) + math.pow((y - trans[1]), 2)

        if distance <= 0.5:
            return True
        else:
            return False

    def set_goal(self, goal):
        self.goto = self.ab.gotowrapper({'goal': goal, 'error_range': -1})

    def read_stored_locations(self, fileName):
        """ Read file with stored locations during navigation training """

        # First line containing keys is omitted
        # Locations must be presented per line
        # Each location is stored as a dictionary {name: {x, y, angle}}
        try:
            fileHandle = open(fileName, 'r')
        except:
            print("Cannot open location file " + fileName)
            return

        firstLineSkipped = False
        for line in fileHandle.readlines():
            line = line.rstrip("\n")  # remove endline

            # Skip first line with keys
            if not firstLineSkipped:
                firstLineSkipped = True
                continue

                # Read location
            values = line.split(',')

            # Skip when line does not contain 4 arguments
            if len(values) != 4:
                continue

            # Skip comment lines
            if len(values[0]) > 0 and values[0][0] == '#':
                continue

            # Store location
            propDict = {'x': float(values[1]), 'y': float(values[2]), 'angle': float(values[3])}
            self.storedLocations[values[0]] = propDict
            print("Location loaded: " + values[0] + " " + str(propDict))

        fileHandle.close()

    def find_behind_point(self, x=-2.0, y=0):
        self.transform.waitForTransform('/base_link', '/map', rospy.Time(0), rospy.Duration(0.2))
        new_point = PoseStamped()
        new_point.header.frame_id = 'base_link'
        new_point.header.stamp = rospy.Time(0)
        new_point.pose.position.x = x
        new_point.pose.position.y = y

        p = self.transform.transformPose('map', new_point)

        quaternion = (
            p.pose.orientation.x,
            p.pose.orientation.y,
            p.pose.orientation.z,
            p.pose.orientation.w
        )

        euler = tf.transformations.euler_from_quaternion(quaternion)

        return {'x': p.pose.position.x, 'y': p.pose.position.y, 'angle': math.degrees(euler[2])}