"""LangChain model callback recording usage and trace metadata without prompt content."""

from langchain_core.callbacks import BaseCallbackHandler


class UsageTracker(BaseCallbackHandler):
    raise_error = True

    def __init__(self, insights, agent_id, trace_id, model, input_rate=None, output_rate=None):
        self.insights = insights
        self.agent_id = agent_id
        self.trace_id = trace_id
        self.model = model
        self.input_rate = input_rate
        self.output_rate = output_rate
        self.tool_names = {}

    def on_tool_start(self, serialized, input_str, *, run_id, **kwargs):
        name = str((serialized or {}).get('name') or 'tool')[:200]
        self.tool_names[str(run_id)] = name
        self.insights.event(self.trace_id, 'tool', name, 'started')

    def on_tool_end(self, output, *, run_id, **kwargs):
        name = self.tool_names.pop(str(run_id), 'tool')
        self.insights.event(self.trace_id, 'tool', name, 'returned')

    def on_tool_error(self, error, *, run_id, **kwargs):
        name = self.tool_names.pop(str(run_id), 'tool')
        self.insights.event(self.trace_id, 'tool', name, f'failed:{type(error).__name__}'[:200])

    def on_llm_end(self, response, *, run_id, **kwargs):
        generation = response.generations[0][0] if response.generations and response.generations[0] else None
        message = getattr(generation, "message", None)
        usage = getattr(message, "usage_metadata", None)
        if usage is None:
            raw = (response.llm_output or {}).get("token_usage")
            if raw is not None and 'prompt_tokens' in raw and 'completion_tokens' in raw:
                usage = {"input_tokens": raw['prompt_tokens'], "output_tokens": raw['completion_tokens']}
        known = isinstance(usage, dict) and 'input_tokens' in usage and 'output_tokens' in usage
        self.insights.record_model_usage(
            self.agent_id, str(run_id), self.model,
            usage['input_tokens'] if known else 0, usage['output_tokens'] if known else 0,
            trace_id=self.trace_id, input_rate=self.input_rate, output_rate=self.output_rate,
            usage_known=known,
        )
        self.insights.event(self.trace_id, "model", self.model, "completed")

    def on_llm_error(self, error, *, run_id, **kwargs):
        self.insights.record_model_usage(self.agent_id, str(run_id), self.model,
                                        trace_id=self.trace_id, usage_known=False)
        self.insights.event(self.trace_id, "model", self.model, f"failed:{type(error).__name__}"[:200])
