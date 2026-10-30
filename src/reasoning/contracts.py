from typing import Protocol


class ReasoningProvider(Protocol):
    def complete(self,prompt:str,schema:dict)->dict: ...


class ReasoningStrategy(Protocol):
    def propose(self,context:dict,schema:dict)->dict: ...
