from state.errors import StudioError,ErrorCode


def select_chart(relationship,categories=0,series=1,negative=False):
    if relationship=="ranking":return "bar"
    if relationship=="trend":return "line"
    if relationship=="composition":return "pie" if categories<=5 and series==1 and not negative else "stacked_bar"
    if relationship=="distribution":return "column"
    if relationship=="association":return "scatter"
    if relationship=="deviation":return "waterfall"
    if relationship=="flow":return "roadmap"
    raise StudioError(ErrorCode.DATA_VALIDATION_ERROR,"Unknown analytical relationship")
