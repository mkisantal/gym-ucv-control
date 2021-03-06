from __future__ import print_function
from .config import Config
import math
import numpy as np
from time import sleep, localtime
from subprocess import Popen
import os
from random import sample, randint
import yaml
from io import BytesIO
from PIL import Image
from scipy.ndimage import zoom
import threading


from unrealcv import Client


def set_port(port, sim_dir):
    try:
        with open(sim_dir + 'unrealcv.ini', 'w') as ini_file:
            print('[UnrealCV.Core]', file=ini_file)
            print('Port={}'.format(str(port)), file=ini_file)
            print('Width=84', file=ini_file)
            print('Height=84', file=ini_file)
    except (OSError, IOError) as err:
        print(err)
        print('unrealcv.ini does not exist, launching Sim to create it')
        with open(os.devnull, 'w') as fp:
            sim = Popen(sim_dir + Config.SIM_NAME, stdout=fp)
        sleep(5)
        sim.terminate()
        set_port(port, sim_dir)


class Commander:
    def __init__(self, number):
        self.number = number
        self.name = 'worker_' + str(number)
        self.action_space = ('left', 'right', 'forward')
        self.state_space_size = Config.STATE_SHAPE
        self.speed = Config.SPEED
        self.episode_finished = False


        self.trajectory = []
        self.locations = None
        if not Config.RANDOM_SPAWN_LOCATIONS:
            with open(Config.SIM_DIR + 'locations.yaml', 'r') as loc_file:
                self.locations = yaml.load(loc_file)

        # self.port = 7000 + number * 100
        self.port = randint(2000, 7000)
        self.client = None
        self.sim = None
        while not self.start_sim():
            pass

        # logging cumulative steps, individually for agents :-/
        self.cumulative_steps = CumulativeStepsLogger()
        threading.Thread(target=lambda: self.cumulative_steps.work()).start()


    def start_sim(self, restart=False):
        if self.sim is not None:
            self.sim.terminate()
        if self.client is not None:
            self.client.disconnect()
        self.port += 1
        set_port(self.port, Config.SIM_DIR_LIST[self.number])
        sleep(2)
        print('[{}] Connection attempt on PORT {}.'.format(self.name, self.port))
        with open(os.devnull, 'w') as fp:
            self.sim = Popen(Config.SIM_DIR_LIST[self.number] + Config.SIM_NAME, stdout=fp)
        sleep(5)
        self.client = Client((Config.HOST, self.port))
        sleep(2)
        self.client.connect()
        sleep(2)
        got_connection = self.client.isconnected()
        if got_connection:
            if restart:
                self.reset_agent()
            else:
                self.new_episode()
            return True
        else:
            return False

    def shut_down(self):

        """ Disconnect client and terminate the game. """

        if self.client.isconnected():
            self.client.disconnect()
        if self.sim is not None:
            self.sim.terminate()
            self.sim = None

    def reset_agent(self):
        """ Reset the agent to continue interaction in the state where it was interrupted. """

        new_loc = self.trajectory[-1]["location"]
        new_rot = self.trajectory[-1]["rotation"]
        res1 = self.request('vset /camera/0/rotation {:.3f} {:.3f} {:.3f}'.format(*new_rot))
        assert res1
        res2 = self.request('vset /camera/0/location {:.2f} {:.2f} {:.2f}'.format(*new_loc))
        assert res2
        return

    def new_episode(self, save_trajectory=False, start=None, goal=None):
        """ Choose new start and goal locations, replace agent. """

        if save_trajectory:
            self.save_trajectory()

        # choose random respawn and goal locations, either randomly or from a list of predetermined locations
        random_heading = (0.0, randint(0, 360), 0.0)
        if Config.RANDOM_SPAWN_LOCATIONS:
            goal_x = randint(Config.MAP_X_MIN, Config.MAP_X_MAX)
            goal_y = randint(Config.MAP_Y_MIN, Config.MAP_Y_MAX)
            start_x, start_y = self.random_start_location(random_heading[1])
            start_loc = (start_x, start_y, 150)
            self.goal_location = (goal_x, goal_y, 150)
        else:
            if start is None or goal is None:
                idx_start, idx_goal = sample(range(0, len(self.locations) - 1), 2)
            else:
                idx_start = start
                idx_goal = goal
            start_loc = (self.locations[idx_start]['x'], self.locations[idx_start]['y'], self.locations[idx_start]['z'])
            self.goal_location = np.array(
                [self.locations[idx_goal]['x'], self.locations[idx_goal]['y'], self.locations[idx_goal]['z']])

        # reset trajectory
        self.trajectory = []
        loc = [float(v) for v in start_loc]
        rot = [float(v) for v in random_heading]
        self.trajectory.append(dict(location=loc, rotation=rot))

        # teleport agent
        self.request('vset /camera/0/location {:.2f} {:.2f} {:.2f}'.format(*start_loc))  # teleport agent
        self.request('vset /camera/0/rotation {:.3f} {:.3f} {:.3f}'.format(*random_heading))

        self.episode_finished = False
        return

    def random_start_location(self, heading):
        collision_at_start = True
        while collision_at_start:
            # spawn location is ok, if we can move forward a bit without colliding
            start_x = randint(Config.MAP_X_MIN, Config.MAP_X_MAX)
            start_y = randint(Config.MAP_Y_MIN, Config.MAP_Y_MAX)
            self.request('vset /camera/0/pose {} {} {} {} {} {}'.format(start_x, start_y, 150, 0, heading, 0))
            step = 50
            small_step_forward = (start_x + step * math.cos(math.radians(heading)),
                                  start_y + step * math.sin(math.radians(heading)), 150.0)
            self.request('vset /camera/0/moveto {} {} {}'.format(*small_step_forward))
            final_loc = [round(float(v), 2) for v in self.request('vget /camera/0/location').split(' ')]
            if final_loc == [round(v, 2) for v in small_step_forward]:
                # acceptable start location found
                collision_at_start = False
            else:
                sleep(1)
        return start_x, start_y

    def save_trajectory(self):
        filename = './trajectory_{}.yaml'.format(self.name)
        with open(filename, 'a+') as trajectory_file:
            traj_dict = {'traj': self.trajectory,
                         'goal': [float(self.goal_location[0]), float(self.goal_location[1])],
                         }  # TODO: add rewards
            yaml.dump([traj_dict], stream=trajectory_file, default_flow_style=False)

    def get_pos(self, print_pos=False):

        """ Get the last position from the stored trajectory, if trajectory is empty then request it from the sim. """

        if len(self.trajectory) == 0:
            rot = [float(v) for v in self.request('vget /camera/0/rotation').split(' ')]
            loc = [float(v) for v in self.request('vget /camera/0/location').split(' ')]
            self.trajectory.append(dict(location=loc, rotation=rot))
        else:
            loc = self.trajectory[-1]["location"]
            rot = self.trajectory[-1]["rotation"]

        if print_pos:
            print('Position x={} y={} z={}'.format(*loc))
            print('Rotation pitch={} heading={} roll={}'.format(*rot))

        return loc, rot

    def action(self, cmd):
        angle = 20.0  # degrees/step
        loc_cmd = [0.0, 0.0, 0.0]
        rot_cmd = [0.0, 0.0, 0.0]
        if cmd == 'left':
            loc_cmd[0] = self.speed
            rot_cmd[1] = -angle
        elif cmd == 'right':
            loc_cmd[0] = self.speed
            rot_cmd[1] = angle
        elif cmd == 'forward':
            loc_cmd[0] = self.speed
        elif cmd == 'backward':
            loc_cmd[0] = -self.speed

        reward = self.move(loc_cmd=loc_cmd, rot_cmd=rot_cmd)
        return reward

    def move(self, loc_cmd=(0.0, 0.0, 0.0), rot_cmd=(0.0, 0.0, 0.0)):
        loc, rot = self.get_pos()
        new_rot = [sum(x) % 360 for x in zip(rot, rot_cmd)]
        displacement = [loc_cmd[0] * math.cos(math.radians(rot[1])), loc_cmd[0] * math.sin(math.radians(rot[1])),
                        0.0]
        new_loc = [sum(x) for x in zip(loc, displacement)]
        collision = False

        if rot_cmd != (0.0, 0.0, 0.0):
            res = self.request('vset /camera/0/rotation {:.3f} {:.3f} {:.3f}'.format(*new_rot))
            assert (res == 'ok')
        if loc_cmd != (0.0, 0.0, 0.0):
            res = self.request('vset /camera/0/moveto {:.2f} {:.2f} {:.2f}'.format(*new_loc))
            final_loc = [float(v) for v in self.request('vget /camera/0/location').split(' ')]
            if final_loc != [round(v, 2) for v in new_loc]:
                collision = True
                new_loc = final_loc

        self.trajectory.append(dict(location=new_loc, rotation=new_rot))

        reward = self.calculate_reward(displacement, collision)
        return reward

    def request(self, message):

        res = self.client.request(message)
        # if res in 'None', try restarting sim
        while not res:
            print('[{}] sim error while trying to request {}'.format(self.name, message))
            success = self.start_sim(restart=True)
            if success:
                res = self.client.request(message)

        return res

    def calculate_reward(self, displacement, collision=False):
        reward = 0
        loc = np.array(self.trajectory[-1]['location'])
        prev_loc = np.array(self.trajectory[-2]['location'])
        disp = np.array(displacement)
        goal_distance = np.linalg.norm(np.subtract(loc, self.goal_location))
        if goal_distance < 200.0:  # closer than 2 meter to the goal
            return Config.GOAL_DIRECTION_REWARD  # TODO: terminate episode!
        norm_displacement = np.array(displacement) / self.speed
        norm_goal_vector = np.subtract(self.goal_location, prev_loc) \
                           / np.linalg.norm(np.subtract(self.goal_location, prev_loc))
        reward += np.dot(norm_goal_vector, norm_displacement) * Config.GOAL_DIRECTION_REWARD
        if collision:
            reward += Config.CRASH_REWARD
            self.episode_finished = True

        return reward

    @staticmethod
    def _read_npy(res):
        return np.load(BytesIO(res))

    @staticmethod
    def _read_png(res):
        img = Image.open(BytesIO(res))
        return np.asarray(img)

    @staticmethod
    def quantize_depth(depth_image):
        """ Depth classes """
        bins = [0, 1, 2, 3, 4, 5, 6, 7]  # TODO: better depth bins
        out = np.digitize(depth_image, bins) - np.ones(depth_image.shape, dtype=np.int8)
        return out

    @staticmethod
    def crop_and_resize(depth_image):
        # resize 84x84 to 16x16, crop center 8x16
        cropped = depth_image[21:63]
        resized = zoom(cropped, [0.095, 0.19], order=1)
        return resized

    def get_observation(self, grayscale=False, viewmode='lit'):

        """ Get image from the simulator. """

        if viewmode == 'depth':
            res = self.request('vget /camera/0/depth npy')
            depth_image = self._read_npy(res)
            cropped = self.crop_and_resize(depth_image)
            observation = self.quantize_depth(cropped)
        else:
            res = self.request('vget /camera/0/lit png')
            rgba = self._read_png(res)
            rgb = rgba[:, :, :3]
            normalized = (rgb - 127.5) / 127.5
            if grayscale is True:
                observation = np.mean(normalized, 2)
            else:
                observation = normalized
        return observation

    def get_goal_direction(self):

        """ Producing goal direction input for the agent. """

        location = np.array(self.trajectory[-1]['location'])
        goal_vector = np.subtract(self.goal_location, location)

        hdg = self.trajectory[-1]['rotation'][1]
        goal = math.degrees(math.atan2(goal_vector[1], goal_vector[0]))
        if goal < 0:
            goal += 360

        # sin(heading_error) is sufficient for directional input
        relative = math.sin(math.radians(goal - hdg))

        return np.expand_dims(np.expand_dims(relative, 0), 0)

    def is_episode_finished(self):
        return self.episode_finished


class CumulativeStepsLogger:       # TODO: remove this
    def __init__(self):
        self.counter = 0
        self.d = 0
        self.should_stop = False
        self.filename = '/home/mate/runs/step_count_log_sum_these_{}.csv'.format(randint(1, 1000))
        print('--- logging to {}'.format(self.filename))

    def increment(self):
        self.counter += 1

    def work(self):
        while not self.should_stop:
            sleep(10)
            diff = self.counter - self.d
            self.d = self.counter
            hour = localtime().tm_hour
            minute = localtime().tm_min
            with open(self.filename, 'a') as log_file:
                log_file.write('{}:{}, {}, {}\n'.format(hour, minute, self.counter, diff))


