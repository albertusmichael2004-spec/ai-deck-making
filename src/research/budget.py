from time import monotonic

from state.errors import StudioError,ErrorCode


class ResearchBudget:
    def __init__(self,limits):self.limits=limits;self.started=monotonic();self.used={"queries":0,"fetches":0,"tokens":0}
    def consume(self,kind,amount=1):
        limit=self.limits["max_"+kind]
        if monotonic()-self.started>=self.limits["max_seconds"] or self.used[kind]+amount>limit:
            raise StudioError(ErrorCode.RESEARCH_BUDGET_EXHAUSTED,"Research budget exhausted",kind=kind,used=self.used[kind],limit=limit)
        self.used[kind]+=amount
    def time_available(self):return monotonic()-self.started<self.limits["max_seconds"]
    def check_model(self):
        if self.used["tokens"]>=self.limits["max_tokens"] or not self.time_available():
            raise StudioError(ErrorCode.RESEARCH_BUDGET_EXHAUSTED,"No model budget remains")
    def account(self,kind,amount):
        """Record actual metered provider usage, including a final in-flight call."""
        self.used[kind]+=amount
        if self.used[kind]>=self.limits["max_"+kind] or not self.time_available():
            raise StudioError(ErrorCode.RESEARCH_BUDGET_EXHAUSTED,"Metered research budget reached",kind=kind,used=self.used[kind],limit=self.limits["max_"+kind])
    def account_usage(self,usage):
        for kind,amount in usage.items():self.used[kind]+=amount
        exhausted=[kind for kind in usage if self.used[kind]>=self.limits["max_"+kind]]
        if exhausted or not self.time_available():raise StudioError(ErrorCode.RESEARCH_BUDGET_EXHAUSTED,"Metered research budget reached",used=dict(self.used),exhausted=exhausted)
