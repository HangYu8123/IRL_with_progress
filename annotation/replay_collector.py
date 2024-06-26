# replay trajectory from dataset and collect progress data from user
import h5py
import os
import json
import robosuite as suite
from envs.pickplace import*
import numpy as np
from robosuite.controllers import load_controller_config
import argparse
from utils.demostration_utils import load_data_to_h5py
from utils.annotation_utils import write_to_json

ENV_META_EXCLUDE = ["env_version", "type"]

def replay_trajectory_and_collect_progress(dataset_path:str,
                      reply_demo_indicies:int,
                      collect_progress_times:int, 
                      **env_kwargs):
    '''
    replay trajectory from dataset and collect progress data from user
    write progress data to json file
    input: dataset_path: str, relative to human_demo folder
              reply_demo_numbers: int, number of demo to replay
              collect_progress_times: int, number of times to collect progress data
     '''
    # load dataset
    f:h5py.File = load_data_to_h5py(dataset_path)

    # get environment meta data
    env_name = json.loads(f["data"].attrs["env_args"])["env_name"]
    env_kwargs = json.loads(f["data"].attrs["env_args"])["env_kwargs"]
    # enable rendering
    env_kwargs["has_renderer"] = True

    # make environment
    env:PickPlaceCan = suite.make(
        env_name=env_name,
        **env_kwargs
    )

    # get demo keys
    filter_key = "train"
    demo_keys = [elem.decode("utf-8") for elem in np.array(f["mask/{}".format(filter_key)][:])]
    # print(demo_keys)
    # get demo keys to replay
    replay_demo_keys = ["demo_{}".format(i) for i in reply_demo_indicies if "demo_{}".format(i) in demo_keys]
    # print(replay_demo_keys)
    # replay demo, pause given times and collect progress data
    progress_data = dict()
    for key in replay_demo_keys:
        obs = np.array(f["data/{}/obs".format(key)])
        actions = np.array(f["data/{}/actions".format(key)])
        dones = np.array(f["data/{}/dones".format(key)])

        # set initial state
        initial_state = f["data/{}/states".format(key)][0]
        env.reset()
        env.sim.set_state_from_flattened(initial_state)
        env.sim.forward()
        env.render()

        pause_indices = np.linspace(0, len(actions), collect_progress_times+2, dtype=int)[1:-1]
        # replay demo
        for i in range(len(actions)):
            action = actions[i]
            print(i)
            # obs = obs[i]
            done = dones[i]
            env.step(action)
            env.render()
            if done:
                break
            
            # pause and collect progress data
            if i in pause_indices:
                progress_data[key] = progress_data.get(key, [])
                # get user input
                user_input = input("Please input the progress data: ")
                # user input must be a float, otherwise ask user to input again
                while not user_input.replace(".", "").isdigit():
                    user_input = input("Please input the progress data: ")
                
                single_data = dict(
                    step = i,
                    progress_data = float(user_input)
                )

                progress_data[key].append(single_data)
                # render the environment
                env.render()
    # write progress data to json file, each demo has a json file
    for key in progress_data.keys():
        write_to_json(progress_data[key], "{}.json".format(key))
    
    f.close()





if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset_path", type=str, default="can-pick/low_dim_v141.hdf5")
    parser.add_argument("--replay_demo_numbers", type=int, nargs="+", default=[1])
    parser.add_argument("--collect_progress_times", type=int, default=10)
    args = parser.parse_args()
    print(args.replay_demo_numbers)
    replay_trajectory_and_collect_progress(args.dataset_path, args.replay_demo_numbers, args.collect_progress_times)