import hashlib
from datetime import datetime,timezone

from state.io import read_json,write_json


class ResearchCache:
    def __init__(self,path):self.path=path;path.mkdir(parents=True,exist_ok=True)
    def get(self,key,ttl_seconds):
        path=self.path/(hashlib.sha256(key.encode()).hexdigest()+".json")
        if not path.exists():return None
        record=read_json(path)
        if (datetime.now(timezone.utc)-datetime.fromisoformat(record["cached_at"])).total_seconds()>ttl_seconds:return None
        return record["value"]
    def put(self,key,value):write_json(self.path/(hashlib.sha256(key.encode()).hexdigest()+".json"),{"cached_at":datetime.now(timezone.utc).isoformat(),"value":value})
