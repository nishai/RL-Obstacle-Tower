import random
import numpy as np
import gym
import os
import torch
from dqn.agent import DQNAgent
from dqn.replay_buffer import ReplayBuffer
from dqn.wrappers import *
import argparse
from environments.obstacle_tower.obstacle_tower_env import ObstacleTowerEnv, ObstacleTowerEvaluation


HUMAN_ACTIONS = (18, 6, 12, 36, 24, 30)
NUM_ACTIONS = len(HUMAN_ACTIONS)

class HumanActionEnv(gym.ActionWrapper):
    """
    An environment wrapper that limits the action space to
    looking left/right, jumping, and moving forward.
    """

    def __init__(self, env):
        super().__init__(env)
        self.actions = HUMAN_ACTIONS
        self.action_space = gym.spaces.Discrete(len(self.actions))

    def action(self, act):
        return self.actions[act]

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='DQN Atari')
    parser.add_argument('--checkpoint', type=str, default=None, help='Where checkpoint file should be loaded from (usually results/checkpoint.pth)')
    parser.add_argument('--seed', type=int, default=42, help='Random seed for training')
    parser.add_argument('--lr',type=float,default=1e-4,help="learning rate")
    # parser.add_argument('--continue', action='store_true')
    args = parser.parse_args()

    i = 0
    if not os.path.exists("results"):
        os.mkdir("results")
    while True:
        file_name = "results/experiment_"+str(i)
        if not os.path.exists(file_name):
            dir_to_make = file_name
            break
        i+=1

    os.mkdir(dir_to_make)
    save_loc = dir_to_make+"/"
    print("Saving results to", dir_to_make)
    hyper_params = {
        "discount-factor": 0.99,  # discount factor
        "num-steps":  15000000,  # total number of steps to run the environment for
        "batch-size": 64,  # number of transitions to optimize at the same time
        "learning-starts": 500000,  # number of steps before learning starts
        "learning-freq": 1,  # number of iterations between every optimization step
        "use-double-dqn": True,  # use double deep Q-learning
        "target-update-freq": 600,  # number of iterations between every target network update
        "eps-start": 1.0,  # e-greedy start threshold
        "eps-end": 0.01,  # e-greedy end threshold
        "eps-fraction": 0.1,  # fraction of num-steps
        "print-freq": 10,
    }

    np.random.seed(args.seed)
    random.seed(args.seed)
    config = {'starting-floor': 0, 'total-floors': 9, 'dense-reward': 1,
              'lighting-type': 0, 'visual-theme': 0, 'default-theme': 0, 'agent-perspective': 1, 'allowed-rooms': 0,
              'allowed-modules': 0,
              'allowed-floors': 0,
              }
    worker_id = int(np.random.randint(999, size=1))
    print(worker_id)
    env = ObstacleTowerEnv('./ObstacleTower/obstacletower', docker_training=False, worker_id=worker_id, retro=True, realtime_mode=False, config=config, greyscale=True)
    # assert "NoFrameskip" in hyper_params["env"], "Require environment with no frameskip"
    env.seed(args.seed)
    env = PyTorchFrame(env)
    env = FrameStack(env, 10)
    env = HumanActionEnv(env)

    replay_buffer = ReplayBuffer(int(5e4))

    agent = DQNAgent(
        env.observation_space,
        env.action_space,
        replay_buffer,
        use_double_dqn=hyper_params["use-double-dqn"],
        lr=args.lr,
        batch_size=hyper_params["batch-size"],
        gamma=hyper_params["discount-factor"],
    )


    if(args.checkpoint):
        print(f"Loading a policy - { args.checkpoint } ")
        agent.policy_network.load_state_dict(torch.load(args.checkpoint))
    eps_timesteps = hyper_params["eps-fraction"] * float(hyper_params["num-steps"])
    episode_rewards = [0.0]
    step_count = 0
    state = env.reset()
    for t in range(hyper_params["num-steps"]):
        fraction = min(1.0, float(t) / eps_timesteps)
        eps_threshold = hyper_params["eps-start"] + fraction * (hyper_params["eps-end"] - hyper_params["eps-start"])
        sample = random.random()
        if sample > eps_threshold:
            action = agent.act(np.array(state))
        else:
            action = env.action_space.sample()
        next_state, reward, done, _ = env.step(action)
        step_count +=1
        agent.memory.add(state, action, reward, next_state, float(done))
        state = next_state
        episode_rewards[-1] += reward
        if done:
            state = env.reset()
            episode_rewards.append(0.0)

        if t > hyper_params["learning-starts"] and t % hyper_params["learning-freq"] == 0:
            agent.optimise_td_loss()

        if t > hyper_params["learning-starts"] and t % hyper_params["target-update-freq"] == 0:
            agent.update_target_network()

        num_episodes = len(episode_rewards)
        if t % 200000 == 0:

            torch.save(agent.policy_network.state_dict(), os.path.join(save_loc, "checkpoint_"+str(t)+"_step.pth"))
            print("Saved Checkpoint after",t,"steps")

        if done and hyper_params["print-freq"] is not None and len(episode_rewards) % hyper_params["print-freq"] == 0:
            mean_100ep_reward = round(np.mean(episode_rewards[-101:-1]), 1)
            print("********************************************************")
            print("steps: {}".format(t))
            print("episodes: {}".format(num_episodes))
            print("mean 100 episode reward: {}".format(mean_100ep_reward))
            print("% time spent exploring: {}".format(int(100 * eps_threshold)))
            print("********************************************************")
            torch.save(agent.policy_network.state_dict(), os.path.join(save_loc, "checkpoint_"+str(num_episodes)+"_eps.pth"))
            np.savetxt(os.path.join(save_loc,"rewards.csv"), episode_rewards, delimiter=",")
    torch.save(agent.policy_network.state_dict(), os.path.join(save_loc, "final_checkpoint.pth"))
    np.savetxt(os.path.join(save_loc,"rewards.csv"), episode_rewards, delimiter=",")
