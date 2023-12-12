from pathlib import Path
from typing import Tuple

import gym
import numpy as np
import tqdm
from absl import app, flags
from ml_collections import config_flags

import wandb
import wrappers
from dataset_utils import D4RLDataset, Log, split_into_trajectories
from evaluation import evaluate
from learner import Learner

FLAGS = flags.FLAGS

flags.DEFINE_string("env_name", "halfcheetah-expert-v2", "Environment name.")
flags.DEFINE_string("save_dir", "./results/", "Tensorboard logging dir.")
flags.DEFINE_integer("seed", 42, "Random seed.")
flags.DEFINE_integer("eval_episodes", 5, "Number of episodes used for evaluation.")
flags.DEFINE_integer("log_interval", 1000, "Logging interval.")
flags.DEFINE_integer("eval_interval", 10000, "Eval interval.")
flags.DEFINE_integer("batch_size", 256, "Mini batch size.")
flags.DEFINE_integer("max_steps", int(1e6), "Number of training steps.")
flags.DEFINE_string("mix_dataset", "None", "mix the dataset")
flags.DEFINE_boolean("tqdm", True, "Use tqdm progress bar.")
flags.DEFINE_string("alg", "PORelDICE", "the training algorithm")
flags.DEFINE_float("alpha", 1.0, "temperature")
flags.DEFINE_float("epsilon", -1.0, "epsilon")
config_flags.DEFINE_config_file(
    "config",
    "default.py",
    "File path to the training hyperparameter configuration.",
    lock_config=False,
)


def normalize(dataset): 
    trajs = split_into_trajectories(
        dataset.observations,
        dataset.actions,
        dataset.rewards,
        dataset.masks,
        dataset.dones_float,
        dataset.next_observations,
    )

    def compute_returns(traj):
        episode_return = 0
        for _, _, rew, _, _, _ in traj:
            episode_return += rew

        return episode_return

    trajs.sort(key=compute_returns)
    dataset.rewards /= compute_returns(trajs[-1]) - compute_returns(trajs[0])
    dataset.rewards *= 1000.0

    
def make_env_and_dataset(env_name: str, seed: int) -> Tuple[gym.Env, D4RLDataset]:
    env = gym.make(env_name)

    env = wrappers.EpisodeMonitor(env)
    env = wrappers.SinglePrecision(env)

    env.seed(seed=seed)
    env.action_space.seed(seed)
    env.observation_space.seed(seed)
    dataset = D4RLDataset(env)

    if "antmaze" in FLAGS.env_name:
        dataset.rewards -= 1.0
    elif (
        "halfcheetah" in FLAGS.env_name
        or "walker2d" in FLAGS.env_name
        or "hopper" in FLAGS.env_name
    ):
        # pass
        normalize(dataset)

    return env, dataset


def main(_):
    env, dataset = make_env_and_dataset(FLAGS.env_name, FLAGS.seed)
    kwargs = dict(FLAGS.config)
    kwargs["alpha"] = FLAGS.alpha
    kwargs["alg"] = FLAGS.alg
    kwargs["epsilon"] = FLAGS.epsilon
    agent = Learner(
        FLAGS.seed,
        env.observation_space.sample()[np.newaxis],
        env.action_space.sample()[np.newaxis],
        max_steps=FLAGS.max_steps,
        **kwargs,
    )
    kwargs["seed"] = FLAGS.seed
    kwargs["env_name"] = FLAGS.env_name

    wandb.init(
        project='project_name',
        entity='your_wandb_id',
        name=f"{FLAGS.env_name}",
        config=kwargs,
    )

    log = Log(Path("benchmark") / FLAGS.env_name, kwargs)
    log(f"Log dir: {log.dir}")
    for i in tqdm.tqdm(
        range(1, FLAGS.max_steps + 1), smoothing=0.1, disable=not FLAGS.tqdm
    ):
        batch = dataset.sample(FLAGS.batch_size)
        update_info = agent.update(batch)

        if i % FLAGS.log_interval == 0:
            wandb.log(update_info, i)

        if i % FLAGS.eval_interval == 0:
            normalized_return = evaluate(
                FLAGS.env_name, agent, env, FLAGS.eval_episodes
            )
            log.row({"normalized_return": normalized_return})
            wandb.log({"normalized_return": normalized_return}, i)

    log.close()
    wandb.finish()


if __name__ == "__main__":
    app.run(main)
