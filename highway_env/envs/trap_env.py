from typing import Dict, Text, Tuple, Optional

import numpy as np

from highway_env import utils
from highway_env.envs.common.abstract import AbstractEnv
from highway_env.envs.common.action import Action
from highway_env.road.road import Road, RoadNetwork
# from highway_env.utils import near_split
from highway_env.vehicle.controller_trap import TrapControlledVehicle
# from highway_env.vehicle.kinematics import Vehicle
from highway_env.vehicle.behavior import IDMVehicle
from highway_env.envs.common.graphics import EnvViewer

Observation = np.ndarray


class TrapEnv(AbstractEnv):
    """
    A highway driving environment.

    The vehicle is driving on a straight highway with several lanes, and is rewarded for reaching a high speed,
    staying on the rightmost lanes and avoiding collisions.
    """

    @classmethod
    def default_config(cls) -> dict:
        config = super().default_config()
        config.update({
            "observation": {
                "type": "Trap"
            },
            "action": {
                "type": "TrapAction",
                "longitudinal": True,
                "lateral": True,
            },
            "lanes_count": 3,
            "duration": 15,  # [s]
            "ego_spacing": 2,
            "vehicles_density": 1,
            "normalize_reward": True,
            "offroad_terminal": False,
            "simulation_frequency": 15,
            "policy_frequency": 1,
            "centering_position": [0.5, 0.5],
            "longi_aggr": True,
            "lateral_aggr": True,
            "init_state": None,
            "speed_limit": 30.0, 
        })
        return config

    def _reset(self) -> None:
        self._create_road()
        self._create_vehicles()

    def _create_road(self) -> None:
        """Create a road composed of straight adjacent lanes."""
        self.road = Road(network=RoadNetwork.straight_road_network(self.config["lanes_count"], speed_limit=70),
                         np_random=self.np_random, record_history=self.config["show_trajectories"])

    def _create_vehicles(self) -> None:
        if self.config["init_state"] is None:
            veh_len_ = 5.0 # [m]
            max_decel_ = 6.0 # [m/(s^2)]
            
            init_speed_range = [25.0, 35.0]
            init_rear_x_range = [0.0, 25.0 + veh_len_] # vehicle length = 5.0 [m]
            init_front_x_range = [25.0 + veh_len_, 50.0] # vehicle length = 5.0 [m]
            
            subject_init_x = 25 # m
            subject_init_lane = self.np_random.integers(0, 3)
            subject_init_spd = self.np_random.random() * (init_speed_range[1] - init_speed_range[0]) + init_speed_range[0]
            
            lane_0 = self.road.network.get_lane(("0", "1", 0))
            lane_1 = self.road.network.get_lane(("0", "1", 1))
            lane_2 = self.road.network.get_lane(("0", "1", 2))
            lanes = [lane_0, lane_1, lane_2]
            
            vehicles = [[], [], []] # list of (init_x, init_spd) tuples of each lane [0-2]
            
            subject_vehicle = IDMVehicle(
                self.road,
                position=lanes[subject_init_lane].position(subject_init_x, 0),
                speed=subject_init_spd,
                target_speed=self.config["speed_limit"],
                longi_aggr=self.config["longi_aggr"],
                lateral_aggr=self.config["lateral_aggr"],
            )
            subject_vehicle.color = (100, 200, 255) # BLUE
            self.road.vehicles.append(subject_vehicle)
            vehicles[subject_init_lane].append((subject_init_x, subject_init_spd))
            
            def reinit_ttc_check(vehs: list, init_x: float, init_spd: float):
                if len(vehs) == 0:
                    return False
                for v in vehs:
                    x = v[0]
                    spd = v[1]
                    x_diff = x - init_x - veh_len_
                    spd_diff = spd - init_spd
                    if abs(x - init_x) < veh_len_: 
                        return True
                    if x_diff * spd_diff >= 0.0:
                        continue
                    elif init_x > x and (spd ** 2 - init_spd ** 2) / 2 / max_decel_ > init_x - x - veh_len_:
                        return True
                    elif init_x < x and (init_spd ** 2 - spd ** 2) / 2 / max_decel_ > x - init_x - veh_len_:
                        return True
                return False
            
            self.controlled_vehicles = []
            # front vehicle number [1, 3]
            front_agent_num = self.np_random.integers(1, 4)
            for _ in range(front_agent_num):
                init_x = self.np_random.random() * (init_front_x_range[1] - init_front_x_range[0]) + init_front_x_range[0]
                init_lane = self.np_random.integers(0, 3)
                init_speed = self.np_random.random() * (init_speed_range[1] - init_speed_range[0]) + init_speed_range[0]
                while reinit_ttc_check(vehicles[init_lane], init_x, init_speed):
                    init_x = self.np_random.random() * (init_front_x_range[1] - init_front_x_range[0]) + init_front_x_range[0]
                    init_lane = self.np_random.integers(0, 3)
                    init_speed = self.np_random.random() * (init_speed_range[1] - init_speed_range[0]) + init_speed_range[0]
                veh = TrapControlledVehicle(
                    self.road,
                    position=lanes[init_lane].position(init_x, 0),
                    speed=init_speed,
                    target_speed=init_speed,
                )
                vehicles[init_lane].append((init_x, init_speed))
                self.controlled_vehicles.append(veh)
                self.road.vehicles.append(veh)
            # rear/parallel vehicle number [1, 3]
            rear_agent_num = self.np_random.integers(1, 4)
            for _ in range(rear_agent_num):
                init_x = self.np_random.random() * (init_rear_x_range[1] - init_rear_x_range[0]) + init_rear_x_range[0]
                init_lane = self.np_random.integers(0, 3)
                init_speed = self.np_random.random() * (init_speed_range[1] - init_speed_range[0]) + init_speed_range[0]
                while reinit_ttc_check(vehicles[init_lane], init_x, init_speed):
                    init_x = self.np_random.random() * (init_rear_x_range[1] - init_rear_x_range[0]) + init_rear_x_range[0]
                    init_lane = self.np_random.integers(0, 3)
                    init_speed = self.np_random.random() * (init_speed_range[1] - init_speed_range[0]) + init_speed_range[0]
                veh = TrapControlledVehicle(
                    self.road,
                    position=lanes[init_lane].position(init_x, 0),
                    speed=init_speed,
                    target_speed=init_speed,
                )
                vehicles[init_lane].append((init_x, init_speed))
                self.controlled_vehicles.append(veh)
                self.road.vehicles.append(veh)
            # print(f"generated {front_agent_num} front agent(s) and {rear_agent_num} rear agent(s)")
        else:
            lane_0 = self.road.network.get_lane(("0", "1", 0))
            lane_1 = self.road.network.get_lane(("0", "1", 1))
            lane_2 = self.road.network.get_lane(("0", "1", 2))
            lanes = [lane_0, lane_1, lane_2]
            
            init_states = self.config["init_state"]
            sv_init_state = init_states["sv"]
            pov_init_state = init_states["pov"]
            
            subject_vehicle = IDMVehicle(
                self.road,
                position=lanes[sv_init_state["lane"]].position(sv_init_state["x"], 0),
                speed=sv_init_state["speed"],
                target_speed=self.config["speed_limit"],
                longi_aggr=self.config["longi_aggr"],
                lateral_aggr=self.config["lateral_aggr"],
            )
            subject_vehicle.color = (100, 200, 255) # BLUE
            self.road.vehicles.append(subject_vehicle)
            
            self.controlled_vehicles = []
            for init_state in pov_init_state:
                veh = TrapControlledVehicle(
                    self.road,
                    position=lanes[init_state["lane"]].position(init_state["x"], 0),
                    speed=init_state["speed"],
                    target_speed=init_state["speed"],
                )
                self.controlled_vehicles.append(veh)
                self.road.vehicles.append(veh)

    def _reward(self, action: Action) -> float:
        reward = []
        for veh in self.controlled_vehicles:
            reward.append(self._rewards(veh))
        return reward

    def _rewards(self, veh: TrapControlledVehicle) -> float:
        """
        The reward is defined to foster driving at high speed, on the rightmost lanes, and to avoid collisions.
        :param action: the last action performed
        :return: the corresponding reward
        """
        r_max = 1.0
        r_min = -1.0
        
        reward = 0.
        
        agent_vehicle = veh
        subject_vehicle = self.road.vehicles[0]
        
        def normalize(r, r_min, r_max):
            r = (r - r_min) / (r_max - r_min)
            return np.clip(r, 0, 1.0)
        
        if agent_vehicle.crashed:
            reward = r_min
        elif agent_vehicle.lane_index[-1] == subject_vehicle.lane_index[-1] and agent_vehicle.position[0] > subject_vehicle.position[0]:
            nrd = 25.0    # no reward distance threshold [m]
            safe_margin = 1.0 # [m]
            safe_headway = 2.0 # [m]
            
            headway = agent_vehicle.position[0] - subject_vehicle.position[0] - agent_vehicle.LENGTH
            
            if headway < safe_headway:
                reward = r_min
            elif headway < safe_headway + safe_margin:
                reward = (r_max - r_min) / safe_margin * headway + r_min - safe_headway / safe_margin * (r_max - r_min)
            else:
                reward = max(0.0, r_max * (headway - nrd) / (safe_headway + safe_margin - nrd))
        elif abs(agent_vehicle.lane_index[-1] - subject_vehicle.lane_index[-1]) == 1 and abs(agent_vehicle.position[0] - subject_vehicle.position[0]) < agent_vehicle.LENGTH:
            reward = r_max * 0.75
                
        return normalize(reward, r_min, r_max)

    def _is_terminated(self) -> bool:
        """The episode is over if the ego vehicle crashed."""
        for v in self.road.vehicles:
            if v.crashed:
                return True
        return False

    def _is_truncated(self) -> bool:
        """The episode is truncated if the time limit is reached."""
        return self.time >= self.config["duration"]
    
    def _info(self, obs: Observation, action: Optional[Action] = None) -> dict:
        """
        Return a dictionary of additional information

        :param obs: current observation
        :param action: current action
        :return: info dict
        """
        info = {
            "crashed": [v.crashed for v in self.controlled_vehicles]
        }
        return info
    
    def render(self, mode: str = 'rgb_array') -> Optional[np.ndarray]:
        if self.viewer is None:
            self.viewer = EnvViewer(self)
        self.viewer.observer_vehicle = self.road.vehicles[0]    # set focus vehicle
        super().render(mode=mode)
    
