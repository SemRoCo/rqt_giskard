import re
from typing import List, Union, Dict, Tuple

import pydot
from py_trees import Status

import giskard_msgs.msg as giskard_msgs
from giskard_msgs.msg import ExecutionState
from giskardpy.data_types import TaskState
from giskardpy.god_map import god_map
from giskardpy.motion_graph.monitors.payload_monitors import CancelMotion
from giskardpy.motion_graph.monitors.monitor_manager import EndMotion
from giskardpy.tree.behaviors.plugin import GiskardBehavior
from giskardpy.tree.behaviors.publish_feedback import giskard_state_to_execution_state
from giskardpy.utils import logging
from giskardpy.utils.decorators import record_time, catch_and_raise_to_blackboard
from giskardpy.utils.utils import create_path, json_str_to_kwargs


def extract_monitor_names_from_condition(condition: str) -> List[str]:
    return re.findall(r"'(.*?)'", condition)


def search_for_monitor(monitor_name: str, execution_state: ExecutionState) -> giskard_msgs.Monitor:
    return [m for m in execution_state.monitors if m.name == monitor_name][0]


task_state_to_color: Dict[TaskState, str] = {
    TaskState.not_started: 'gray',
    TaskState.running: 'green',
    TaskState.on_hold: 'orange',
    TaskState.succeeded: 'palegreen',
    TaskState.failed: 'red'
}

monitor_state_to_color: Dict[Tuple[TaskState, int], str] = {
    (TaskState.not_started, 1): 'darkgreen',
    (TaskState.running, 1): 'green',
    (TaskState.on_hold, 1): 'turquoise',
    (TaskState.succeeded, 1): 'palegreen',
    (TaskState.failed, 1): 'gray',

    (TaskState.not_started, 0): 'darkred',
    (TaskState.running, 0): 'red',
    (TaskState.on_hold, 0): 'orange',
    (TaskState.succeeded, 0): 'lightpink',
    (TaskState.failed, 0): 'black'
}


def format_condition(condition: str) -> str:
    condition = condition.replace(' and ', '\nand ')
    condition = condition.replace(' or ', '\nor ')
    condition = condition.replace('1.0', 'True')
    condition = condition.replace('0.0', 'False')
    return condition


def format_monitor_msg(msg: giskard_msgs.Monitor) -> str:
    start_condition = format_condition(msg.start_condition)
    kwargs = json_str_to_kwargs(msg.kwargs)
    hold_condition = format_condition(kwargs['hold_condition'])
    end_condition = format_condition(kwargs['end_condition'])
    return (f'"\'{msg.name}\'\n'
            f'----------start_condition:----------\n'
            f'{start_condition}\n'
            f'----------hold_condition:-----------\n'
            f'{hold_condition}\n'
            f'-----------end_condition:-----------\n'
            f'{end_condition}"')


def format_task_msg(msg: giskard_msgs.MotionGoal) -> str:
    start_condition = format_condition(msg.start_condition)
    hold_condition = format_condition(msg.hold_condition)
    end_condition = format_condition(msg.end_condition)
    return (f'"\'{msg.name}\'\n'
            f'----------start_condition:----------\n'
            f'{start_condition}\n'
            f'----------hold_condition:-----------\n'
            f'{hold_condition}\n'
            f'-----------end_condition:-----------\n'
            f'{end_condition}"')


def format_msg(msg: Union[giskard_msgs.Monitor, giskard_msgs.MotionGoal]) -> str:
    if isinstance(msg, giskard_msgs.MotionGoal):
        return format_task_msg(msg)
    return format_monitor_msg(msg)


def execution_state_to_dot_graph(execution_state: ExecutionState) -> pydot.Dot:
    graph = pydot.Dot(graph_type='digraph')

    def add_or_get_node(thing: Union[giskard_msgs.Monitor, giskard_msgs.MotionGoal]):
        node_id = format_msg(thing)
        nodes = graph.get_node(node_id)
        if not nodes:
            if isinstance(thing, giskard_msgs.Monitor):
                if thing.monitor_class == EndMotion.__name__:
                    shape = 'doubleoctagon'
                elif thing.monitor_class == CancelMotion.__name__:
                    shape = 'tripleoctagon'
                # elif thing.monitor_class == ExpressionMonitor.__name__:
                #     shape = 'box'
                else:  # isinstance(thing, PayloadMonitor)
                    shape = 'octagon'
            else:  # isinstance(thing, Task)
                shape = 'ellipse'
            node = pydot.Node(node_id, shape=shape, color='black')
            graph.add_node(node)
        else:
            node = nodes[0]  # Get the first node from the list
        return node

    # Process monitors and their start_condition
    for i, monitor in enumerate(execution_state.monitors):
        kwargs = json_str_to_kwargs(monitor.kwargs)
        hold_condition = format_condition(kwargs['hold_condition'])
        end_condition = format_condition(kwargs['end_condition'])
        monitor_node = add_or_get_node(monitor)
        monitor_node.obj_dict['attributes']['color'] = monitor_state_to_color[
            (execution_state.monitor_life_cycle_state[i],
             execution_state.monitor_state[i])]
        free_symbols = extract_monitor_names_from_condition(monitor.start_condition)
        for sub_monitor_name in free_symbols:
            sub_monitor = search_for_monitor(sub_monitor_name, execution_state)
            sub_monitor_node = add_or_get_node(sub_monitor)
            graph.add_edge(pydot.Edge(sub_monitor_node, monitor_node, color='green'))
        free_symbols = extract_monitor_names_from_condition(hold_condition)
        for sub_monitor_name in free_symbols:
            sub_monitor = search_for_monitor(sub_monitor_name, execution_state)
            sub_monitor_node = add_or_get_node(sub_monitor)
            graph.add_edge(pydot.Edge(sub_monitor_node, monitor_node, color='orange'))
        free_symbols = extract_monitor_names_from_condition(end_condition)
        for sub_monitor_name in free_symbols:
            sub_monitor = search_for_monitor(sub_monitor_name, execution_state)
            sub_monitor_node = add_or_get_node(sub_monitor)
            graph.add_edge(pydot.Edge(sub_monitor_node, monitor_node, color='red', arrowhead='none', arrowtail='normal',
                                      dir='both'))

    # Process goals and their connections
    for i, task in enumerate(execution_state.tasks):
        # TODO add one collision avoidance task?
        goal_node = add_or_get_node(task)
        goal_node.obj_dict['attributes']['color'] = task_state_to_color[execution_state.task_state[i]]
        for monitor_name in extract_monitor_names_from_condition(task.start_condition):
            monitor = search_for_monitor(monitor_name, execution_state)
            monitor_node = add_or_get_node(monitor)
            graph.add_edge(pydot.Edge(monitor_node, goal_node, color='green'))

        for monitor_name in extract_monitor_names_from_condition(task.hold_condition):
            monitor = search_for_monitor(monitor_name, execution_state)
            monitor_node = add_or_get_node(monitor)
            graph.add_edge(pydot.Edge(monitor_node, goal_node, color='orange'))

        for monitor_name in extract_monitor_names_from_condition(task.end_condition):
            monitor = search_for_monitor(monitor_name, execution_state)
            monitor_node = add_or_get_node(monitor)
            graph.add_edge(pydot.Edge(goal_node, monitor_node, color='red', arrowhead='none', arrowtail='normal',
                                      dir='both'))

    return graph