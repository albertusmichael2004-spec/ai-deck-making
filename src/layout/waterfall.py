def waterfall_series(values):
    """Floating stacked intervals, including movements crossing zero."""
    columns=[[] for _ in range(7)];running=values[0]
    for index,value in enumerate(values):
        if index in {0,len(values)-1}:parts=[0,0,0,0,0,0,value]
        else:
            following=running+value;low,high=sorted([running,following])
            positive=max(0,high)-max(0,low);negative=min(0,low)-min(0,high)
            parts=[max(0,low),min(0,high),positive if value>=0 else 0,negative if value>=0 else 0,positive if value<0 else 0,negative if value<0 else 0,0];running=following
        for column,part in zip(columns,parts,strict=True):column.append(part)
    return list(zip(["Base positive","Base negative","Increase above zero","Increase below zero","Decrease above zero","Decrease below zero","Total"],columns,strict=True))
