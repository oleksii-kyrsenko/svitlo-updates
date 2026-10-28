"""Generic, bounded XLSX text extraction. No address matching or formula execution."""
import sys,json,zipfile,openpyxl
path=sys.argv[1]
with zipfile.ZipFile(path) as z:
    assert sum(x.file_size for x in z.infolist())<=32*1024*1024
    assert all(x.file_size<=12*1024*1024 for x in z.infolist())
book=openpyxl.load_workbook(path,read_only=True,data_only=False,keep_links=False)
sheets=[];count=0;chars=0
for sheet in book:
    assert sheet.max_column<=101 and sheet.max_row<=100000
    rows=[]
    for number,row in enumerate(sheet.iter_rows(),1):
        count+=1;assert count<=100000
        cells=[]
        for cell in row:
            assert cell.data_type!='f','Formulas are not supported'
            value='' if cell.value is None else str(cell.value)
            chars+=len(value);assert chars<=2000000
            cells.append(value)
        rows.append({'number':number,'cells':cells})
    sheets.append({'name':sheet.title,'rows':rows})
assert sheets
print(json.dumps({'sheets':sheets},ensure_ascii=False,separators=(',',':')))
book.close()
