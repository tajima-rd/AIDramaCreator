# core/model/agent/casting_director.py
"""CastingDirector。配役と演じ方を決める。"""

from core.model.agent.agent import Agent


class CastingDirector(Agent):
    """人物(Character)の配役(Cast)と、その役の演じ方(Performance)を決め、どの演者(Actor)に任せるかを決める。"""
