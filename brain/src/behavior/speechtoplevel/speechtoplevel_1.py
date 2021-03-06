from __future__ import print_function

import datetime
import actionlib
import re
import time
import body

import rospy
from alice_msgs.msg import *
import basebehavior.behaviorimplementation
from JSGFParser import JSGFParser


class SpeechToplevel_x(basebehavior.behaviorimplementation.BehaviorImplementation):

    def implementation_init(self):
        print("Speech Behavior Started!")
        self.last_recogtime = 0
        self.state = 'idle'
        self.last_speech_obs = None  # contains the result and 2best form sphinx
        self.new_speech_obs = False  # is used for triggering the conversation
        self.body = body.bodycontroller.BodyController()

        self.grammar = JSGFParser('speech/hark-sphinx/grammar/command.gram')
        self.locations = self.grammar.findVariableItems("<location>", includeVars=False)
        self.objects = self.grammar.findVariableItems("<object>", includeVars=False)
        self.list_objects = []
        self.list_positions = []

        self.client = actionlib.SimpleActionClient("aliceapproach", aliceapproachAction)
        self.navigate = self.ab.tablenavigation({'aim': None})
        self.object_recognition = self.ab.subobjectrecognition({'command': 2})
        self.startNavigate = False
        self.startRec = False
        self.selected_behaviors = [("navigate", "self.startNavigate == True"),
                                   ("object_recognition", "self.startRec == True")]

    def implementation_update(self):
        self.update_last_speech_command()

        if self.state == 'all_objects':
            self.navigate = self.ab.tablenavigation({'aim': 'table1'})
            self.startNavigate = True
            self.state = 'ant1'

        elif self.state == 'ant1' and self.navigate.is_failed():
            self.navigate = self.ab.tablenavigation({'aim': 'table1'})

        elif self.state == 'ant1' and self.navigate.is_finished():
            self.next_state = 'ant2'
            self.next_goal = 'table2'
            self.state = 'start_recognition'
            self.current_table = 'table1'

        elif self.state == 'ant2' and self.navigate.is_failed():
            self.navigate = self.ab.tablenavigation({'aim': 'table2'})

        elif self.state == 'ant2' and self.navigate.is_finished():
            self.next_state = 'start'
            self.next_goal = 'start'
            self.state = 'start_recognition'
            self.current_table = 'table2'

        elif self.state == 'start' and self.navigate.is_failed():
            self.navigate = self.ab.tablenavigation({'aim': 'start'})

        elif self.state == 'start' and self.navigate.is_finished():
            self.state = 'idle'
            self.startNavigate = False
            print(self.list_objects)
            if self.object_name == 'all_objects':
                self.body.say('I have found ' + ' and '.join(self.list_objects) + ' in table one and table two.')
            else:
                if self.object_name in self.list_objects:
                    p = self.list_positions[self.list_objects.index(self.object_name)]
                    if p == min(self.list_positions):
                        position = 'left'
                    elif p == max(self.list_positions):
                        position = 'right'
                    else:
                        position = 'middle'
                    self.body.say('I have found ' + self.object_name + ' in the ' + position + '.')
                else:
                    self.body.say('I have not found ' + self.object_name + '.')

            self.list_objects = []
            self.list_positions = []

        if self.state == 'table1':
            self.navigate = self.ab.tablenavigation({'aim': 'table1'})
            self.startNavigate = True
            self.state = 'ont1'

        elif self.state == 'table2':
            self.navigate = self.ab.tablenavigation({'aim': 'table2'})
            self.startNavigate = True
            self.state = 'ont2'

        elif self.state == 'ont1' and self.navigate.is_failed():
            self.navigate = self.ab.tablenavigation({'aim': 'table1'})

        elif self.state == 'ont2' and self.navigate.is_failed():
            self.navigate = self.ab.tablenavigation({'aim': 'table2'})

        elif (self.state == 'ont1' or self.state == 'ont2') and self.navigate.is_finished():
            self.next_state = 'start'
            self.next_goal = 'start'
            self.state = 'start_recognition'

            if self.state == 'ont1':
                self.current_table = 'table1'
            elif self.state == 'ont2':
                self.current_table = 'table2'


        if self.state == 'start_rec':
            self.body.say('Start recognizing.')
            self.object_recognition = self.ab.subobjectrecognition({'command': 2})
            self.startRec = True
            self.state = 'recognizing'

        elif self.state == 'recognizing' and self.object_recognition.is_failed():
            self.object_recognition = self.ab.subobjectrecognition({'command': 2})

        elif self.state == 'recognizing' and self.object_recognition.is_finished():
            self.startRec = False
            _, item = self.m.get_last_observation('Items')
            self.list_objects.extend(str(item).split('*')[0].split('|'))
            self.list_positions.extend(str(item).split('*')[1].split('|'))
            self.list_positions = [int(i) for i in self.list_positions]
            self.state = self.next_state
            self.navigate = self.ab.tablenavigation({'aim': self.next_goal})


        if self.state == "start_recognition":
            self.body.say('Approach to the table.')
            if self.client.wait_for_server(rospy.Duration(0.1)):
                self.state = "send"
            else:
                print('Could not connect to alice approach server!')

        elif self.state == "send":
            goal = aliceapproachGoal()
            goal.plane = False
            self.client.send_goal(goal)
            self.state = "wait"

        elif self.state == "wait" and self.client.get_state() == actionlib.GoalStatus.ABORTED:  # something went wrong
            self.navigate = self.ab.tablenavigation({'aim': self.current_table})
            print('Something went wrong')
            self.state = 'renav'

        elif self.state == "wait" and self.client.get_state() == actionlib.GoalStatus.SUCCEEDED:
            print('Approach success')
            self.state = 'start_rec'
            
        elif self.state == 'renav' and self.navigate.is_failed():
            self.navigate = self.ab.tablenavigation({'aim': self.current_table})

        elif self.state == 'renav' and self.navigate.is_finished():
            self.state = 'start_recognition'



        if self.new_speech_obs:
            msg_opts_removed = self.remove_opts(self.last_speech_obs['message'])
            locations = self.find_location(msg_opts_removed)
            objects = self.find_object(msg_opts_removed)
            print(locations)
            print(objects)

            if locations is None or objects is None:
                self.body.say('Invalid command! Please give a new command.')

            elif len(locations) != 0 and len(objects) != 0:
                if len(locations) == 2 and len(objects) == 1:
                    if 'table one' in locations and 'table two' in locations and 'all objects' in objects:
                        self.body.say('I will go to table one and table two and find all objects')
                        self.object_name = 'all_objects'
                        self.state = 'all_objects'
                    else:
                        self.body.say('Invalid command! Please give a new command.')

                elif len(locations) == 1 and len(objects) == 1:
                    if 'table one' in locations and 'all objects' not in objects:
                        self.body.say('I will go to table one and find ' + objects[0])
                        self.object_name = objects[0]
                        self.state = 'table1'
                    elif 'table two' in locations and 'all objects' not in objects:
                        self.body.say('I will go to table two and find ' + objects[0])
                        self.object_name = objects[0]
                        self.state = 'table2'
                    else:
                        self.body.say('Invalid command! Please give a new command.')

                else:
                    self.body.say('Invalid command! Please give a new command.')

    # remove words that are between []'s
    def remove_opts(self, hypstr):
        return self.grammar.filterOptionals(hypstr)

    def find_location(self, string):
        regex_str = "(%s)" % '|'.join(self.locations)
        regex = re.compile(regex_str)
        match = re.split(regex, string)
        # print(match)
        if len(match) < 3:
            return None
        list_location = []
        for i in match:
            if i.startswith('table'):
                list_location.append(i)
        return list_location

    def find_object(self, string):
        regex_str = "(%s)" % '|'.join(self.objects)
        regex = re.compile(regex_str)
        match = re.split(regex, string)
        # print(match)
        if len(match) < 3:
            return None
        return [match[1]]

    def update_last_speech_command(self):
        # sets the new_command boolean and sets the last understood speech_observation
        if self.m.n_occurs('voice_command') > 0:
            (recogtime, obs) = self.m.get_last_observation("voice_command")
            if (obs is not None) and recogtime > self.last_recogtime:
                # print("[observation] = ", obs)
                self.last_speech_obs = obs
                self.last_recogtime = recogtime
                self.new_speech_obs = True
            else:
                self.new_speech_obs = False
