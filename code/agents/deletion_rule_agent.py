# code/agents/delition_rule_agent.py
# +---------------------------------------------------------------------------+
# |                            DELETION RULE AGENT                            |
# +---------------------------------------------------------------------------+


import pandas as pd


class DeletionRuleAgent:
    def __init__(self, deletion_rules: pd.DataFrame):
        self.rules = deletion_rules

        self.rule_id = None
        self.data_category = None
        self.condition = None
        self.required_action = None
        # TBD

    def apply(self):
        # TBD
        return None

    # Should we use LLM
