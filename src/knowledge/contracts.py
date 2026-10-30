from typing import Protocol


class KnowledgeRetriever(Protocol):
    def retrieve(self,query:str,limit:int=8,topic:str|None=None,kind:str|None=None)->list[dict]: ...
