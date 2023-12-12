from typing import Dict

import d4rl
import flax.linen as nn
import gym
import numpy as np


def evaluate(
    env_name: str, agent: nn.Module, env: gym.Env, num_episodes: int
) -> Dict[str, float]:
    # stats = {'return': [], 'length': []}
    total_reward_ = []
    for _ in range(num_episodes):
        observation, done = env.reset(), False
        total_reward = 0.0
        while not done:
            action = agent.sample_actions(observation, temperature=0.0)
            observation, reward, done, info = env.step(action)
            total_reward += reward
        total_reward_.append(total_reward)

    average_return = np.array(total_reward_).mean()
    normalized_return = d4rl.get_normalized_score(env_name, average_return) * 100
    return normalized_return
