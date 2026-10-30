"""Read-only inspection of open PowerPoint documents for timeout recovery."""
import json
import pythoncom
import win32com.client

pythoncom.CoInitialize()
try:
    application=win32com.client.GetActiveObject('PowerPoint.Application')
    rows=[]
    for index in range(1,int(application.Presentations.Count)+1):
        deck=application.Presentations.Item(index)
        rows.append({'path':str(deck.FullName),'saved':bool(deck.Saved),'read_only':bool(deck.ReadOnly)})
    print(json.dumps(rows,indent=2))
finally:
    pythoncom.CoUninitialize()
