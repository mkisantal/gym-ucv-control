from gym.envs.registration import register

register(
    id='ucv-v0',
    entry_point='gym_ucv.envs:UcvEnv',
)
