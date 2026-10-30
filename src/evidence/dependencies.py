from state.errors import StudioError, ErrorCode


class DependencyGraph:
    def __init__(self, dependencies=None):
        self.dependencies = {} if dependencies is None else dependencies

    def register(self, consumer: str, inputs: list[str]):
        previous = self.dependencies.get(consumer)
        self.dependencies[consumer] = list(dict.fromkeys(inputs))
        try: self.order()
        except StudioError:
            if previous is None: self.dependencies.pop(consumer)
            else: self.dependencies[consumer] = previous
            raise

    def order(self):
        visiting, done, ordered = set(), set(), []
        def visit(node):
            if node in visiting: raise StudioError(ErrorCode.DATA_VALIDATION_ERROR, "Dependency cycle")
            if node in done: return
            visiting.add(node)
            for dependency in self.dependencies.get(node, []): visit(dependency)
            visiting.remove(node);done.add(node);ordered.append(node)
        for node in self.dependencies: visit(node)
        return ordered

    def affected(self, roots):
        affected = set(roots)
        for node in self.order():
            if any(item in affected for item in self.dependencies.get(node, [])): affected.add(node)
        return affected
