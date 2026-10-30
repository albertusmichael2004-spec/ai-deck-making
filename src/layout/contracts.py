from typing import Protocol


class LayoutCompiler(Protocol):
    def compile(self,deck:dict,slide:dict,source_notes=())->dict: ...
