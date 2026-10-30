from typing import Protocol


class SearchProvider(Protocol):
    def search(self,query:str,limit:int)->list[dict]: ...


class FetchProvider(Protocol):
    def fetch(self,url:str)->dict: ...


class ExtractionProvider(Protocol):
    def extract(self,document:dict,question:dict)->list[dict]: ...
