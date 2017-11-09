import gym
from gym import spaces
from gym.utils import seeding
from .ucv_utils import Commander


class UcvEnv(gym.Env):
    metadata = {'render.modes': ['human']}

    def __init__(self, number=0):
        self.cmd = Commander(number)
        self.action_space = spaces.Discrete(len(self.cmd.action_space))
        # TODO: vanilla A2C can accept only input images
        # self.observation_space = spaces.Tuple((spaces.Box(low=0, high=255, shape=self.cmd.state_space_size),
        #                                       spaces.Box(low=-1, high=1, shape=1)))
        self.observation_space = spaces.Box(low=0, high=255, shape=self.cmd.state_space_size)

    def _step(self, action):
        reward = self.cmd.action(self.cmd.action_space[action])
        done = self.cmd.is_episode_finished()
        # TODO: vanilla A2C can accept only input images
        # state = (self.cmd.get_observation(viewmode='lit'), self.cmd.get_goal_direction())
        state = (self.cmd.get_observation(viewmode='lit'))
        self.cmd.cumulative_steps.increment()   # TODO: remove this
        return state, reward, done, {}

    def _reset(self):
        self.cmd.new_episode()
        # TODO: vanilla A2C can accept only input images
        # state = (self.cmd.get_observation(viewmode='lit'), self.cmd.get_goal_direction())
        state = (self.cmd.get_observation(viewmode='lit'))
        return state

    def _close(self):
        self.cmd.shut_down()
        self.cmd.cumulative_steps.should_stop = True    # TODO: remove this

    # def _render(self, mode='human', close=False):
    #     pass
    #
    # def _seed(self):
    #     pass
