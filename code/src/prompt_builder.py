# code/src/prompt_builder.py


from src.constants import OUTCOME_PROMPT


class PromptBuilder:
    def __init__(self):
        self.prompt = ""

    def _build(self, dataset: dict) -> str:

        # Build the XML data from activity dataset that will be inserted into the prompt.

        # Convert dataset to XML data
        xml_data = []

        self.prompt = self._format(xml_data)

    def _format(self, xml_data) -> str:
        return OUTCOME_PROMPT.format(evidence_data=xml_data)
