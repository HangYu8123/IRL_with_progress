import numpy as np
import gymnasium as gym
from stable_baselines3 import PPO
from stable_baselines3.common.evaluation import evaluate_policy
from stable_baselines3.ppo import MlpPolicy

# from imitation.algorithms.adversarial.airl import AIRL
from IRL_lib_mod.airl import AIRL
from imitation.data import rollout
from imitation.data.wrappers import RolloutInfoWrapper
from imitation.policies.serialize import load_policy
from imitation.rewards.reward_nets import BasicShapedRewardNet
from imitation.util.networks import RunningNorm
from utils.irl_utils import make_vec_env_robosuite
from utils.demostration_utils import load_dataset_to_trajectories
import os
import h5py
import json
from robosuite.controllers import load_controller_config
from utils.demostration_utils import load_dataset_and_annotations_simutanously
from utils.annotation_utils import read_all_json
from imitation.util import logger as imit_logger
import imitation.scripts.train_adversarial as train_adversarial
import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--exp_name', type=str, default="default_experiment")
    
    args = parser.parse_args()
    project_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dataset_path = os.path.join(project_path,"human-demo/can-pick/low_dim_v141.hdf5")
    log_dir = os.path.join(project_path,f"logs/{args.exp_name}")
    print(dataset_path)
    f = h5py.File(dataset_path,'r')

    config_path = os.path.join(project_path,"configs/osc_position.json")
    with open(config_path, 'r') as cfg_file:
        configs = json.load(cfg_file)

    controller_config = load_controller_config(default_controller="OSC_POSE")
    env_meta = json.loads(f["data"].attrs["env_args"])
    SEED = 42
    make_env_kwargs = dict(
        robots="Panda",             # load a Sawyer robot and a Panda robot
        gripper_types="default",                # use default grippers per robot arm
        controller_configs=env_meta["env_kwargs"]["controller_configs"],   # each arm is controlled using OSC
        has_renderer=False,                      # on-screen rendering
        render_camera="frontview",              # visualize the "frontview" camera
        has_offscreen_renderer=False,           # no off-screen rendering
        control_freq=20,                        # 20 hz control for applied actions
        horizon=1000,                            # each episode terminates after 200 steps
        use_object_obs=True,                   # no observations needed
        use_camera_obs=False,
        reward_shaping=True,
    )
    envs = make_vec_env_robosuite(
        "PickPlaceCanModified",
        obs_keys = ["object-state","robot0_eef_pos", "robot0_eef_quat", "robot0_gripper_qpos"],
        rng=np.random.default_rng(SEED),
        n_envs=12,
        parallel=True,
        post_wrappers=[lambda env, _: RolloutInfoWrapper(env)],  # to compute rollouts
        env_make_kwargs=make_env_kwargs,

    )

    annotation_dict = read_all_json("progress_data")

    trajs = load_dataset_to_trajectories(["object","robot0_eef_pos", "robot0_eef_quat", "robot0_gripper_qpos"])
    trajs_for_shaping, annotation_list = load_dataset_and_annotations_simutanously(["object","robot0_eef_pos", "robot0_eef_quat", "robot0_gripper_qpos"],
                                                                       annotation_dict=annotation_dict,
                                                                       dataset_path=dataset_path)
    # type of reward shaping to use
    # change this to enable or disable reward shaping
    shape_reward = []
                                                                       
    learner = PPO(
        env=envs,
        policy=MlpPolicy,
        batch_size=1024,
        ent_coef=0.0,
        learning_rate=0.0005,
        gamma=0.95,
        clip_range=0.1,
        vf_coef=0.1,
        n_epochs=5,
        seed=SEED,
    )
    reward_net = BasicShapedRewardNet(
        observation_space=envs.observation_space,
        action_space=envs.action_space,
        normalize_input_layer=RunningNorm,
    )
    # logger that write tensroborad to logs dir
    logger = imit_logger.configure(folder=log_dir, format_strs=["tensorboard"])
    airl_trainer = AIRL(
        demonstrations=trajs,
        demo_batch_size=2048,
        gen_replay_buffer_capacity=1000000,
        n_disc_updates_per_round=64,
        venv=envs,
        gen_algo=learner,
        reward_net=reward_net,
        shape_reward = shape_reward,
        annotation_list=annotation_list,
        demostrations_for_shaping=trajs_for_shaping,
        custom_logger = logger,
        save_path = f"checkpoints/{args.exp_name}"
        # log_dir = log_dir,
        # init_tensorboard = True,
        # init_tensorboard_graph = True
    )

    # loss = airl_trainer.progress_shaping_loss()
    # print(loss)
    # loss.backward()
    envs.seed(SEED)
    learner_rewards_before_training, _ = evaluate_policy(
        learner, envs, 12, return_episode_rewards=True,
    )
    airl_trainer.train(8_000_000)  # Train for 2_000_000 steps to match expert.
    envs.seed(SEED)
    learner_rewards_after_training, _ = evaluate_policy(
        learner, envs, 12, return_episode_rewards=True,
    )

    # airl_trainer
    # learner.save(os.path.join(project_path,f"checkpoints/{args.exp_name}"))
    print("mean reward after training:", np.mean(learner_rewards_after_training))
    print("mean reward before training:", np.mean(learner_rewards_before_training))
