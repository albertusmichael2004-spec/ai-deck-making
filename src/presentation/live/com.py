"""Small compatibility helper for late-bound Office writable properties."""
def set_property(obj,name,value):
    try:setattr(obj,name,value)
    except AttributeError:
        import pythoncom
        obj._oleobj_.Invoke(obj._oleobj_.GetIDsOfNames(name),0,pythoncom.DISPATCH_PROPERTYPUT,False,value)
