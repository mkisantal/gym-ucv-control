class Config:
    STATE_SHAPE = [84, 84, 3]
    SPEED = 20  # cm/step
    GOAL_DIRECTION_REWARD = 1
    CRASH_REWARD = -10

    SIM_DIR = '/home/mate/ucv-pkg-outdoor-8-lite/LinuxNoEditor/outdoor_lite/Binaries/Linux/'
    SIM_NAME = 'outdoor_lite'

    RANDOM_SPAWN_LOCATIONS = True
    MAP_X_MIN = -4000
    MAP_X_MAX = 4000
    MAP_Y_MIN = -4000
    MAP_Y_MAX = 4000

    HOST = 'localhost'
    SIM_DIR_LIST = ['/home/mate/ucv-pkg-outdoor-8-lite/LinuxNoEditor/outdoor_lite/Binaries/Linux/',
                    '/home/mate/ucv-pkg-outdoor-8-lite/LinuxNoEditor/outdoor_lite/Binaries/Linux/']