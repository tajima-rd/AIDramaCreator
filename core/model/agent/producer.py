# core/model/agent/producer.py
"""Producer。利用者(人)が担当する。"""

from core.model.agent.agent import Agent


class Producer(Agent):
    """前提を与え、尺・制約を管理し、ほかのエージェントの提案を反映・却下する。"""
